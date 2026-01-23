import aiohttp
import aiosqlite

from icalendar import Calendar
from os import getenv
from validation import get_link_with_current_hash
from datetime import datetime, timedelta


peremen_minutes = (
    10  # время перемены, которое нужно добавить к времени занятия (в минутах)
)


async def refresh_schedule():  # обновить расписание
    """
    Обновляет расписание для всех групп, используя URL, сохраненные в базе данных.
    Функция выполняет следующие шаги:
    1. Получает список всех групп из базы данных.
    2. Для каждой группы извлекает URL, связанный с ней.
    3. Для каждой группы вызывает функцию `get_schedule`, чтобы обновить расписание.
    """
    current_hash = await get_link_with_current_hash()
    if not current_hash:
        return
    print(current_hash)
    async with aiosqlite.connect(getenv("DATABASE_NAME")) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT GroupName FROM All_groups")
            groups = (
                await cursor.fetchall()
            )  # Получаем все строки в виде списка кортежей
            for group in groups:
                group_name = group[0]
                await cursor.execute(
                    "SELECT Url FROM Session WHERE GroupName = ?", (group_name,)
                )
                group_number = (await cursor.fetchone())[0]
                if group_number is None:
                    continue
                url = current_hash + str(group_number)
                await get_schedule(url, group_name)


async def sync(group_name):  # обновить расписание по запросу
    """
    Обновляет расписание для одной группы, используя URL, сохраненные в базе данных.
    В качестве параметра выступает group_name.
    Функция выполняет следующие шаги:
    1. Извлекает URL, связанный с группой.
    2. вызывает функцию `get_schedule`, чтобы обновить расписание.
    """
    async with aiosqlite.connect(getenv("DATABASE_NAME")) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT Url FROM Session WHERE GroupName = ?", (group_name,)
            )
            group_number = (await cursor.fetchone())[0]
            if group_number is not None:
                current_hash = await get_link_with_current_hash()
                if not current_hash:
                    return
                url = current_hash + str(group_number)
                await get_schedule(url, group_name)


async def get_schedule(url, group_name):
    """
    Получает расписание для конкретной группы, парсит iCal контент и сохраняет его в базе данных.
    """
    async with (aiohttp.ClientSession() as session):
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    schedule_info = data["pageProps"]["scheduleLoadInfo"]
                    if schedule_info:
                        schedule_info = schedule_info[0]
                        schedule = schedule_info["iCalContent"]
                        real_schedule = Calendar.from_ical(schedule)
                        for component in real_schedule.walk():
                            if (
                                component.name == "VEVENT"
                                and str(component.get("description"))
                                and len(str(component.get("description")).split("\n"))
                                == 2
                            ):
                                teacher_fio = (
                                    str(component.get("description"))
                                    .split("\n", maxsplit=1)[0]
                                    .replace("Преподаватель: ", "")
                                )
                                dt_start = component.get("dtstart").dt
                                start_time = dt_start.replace(tzinfo=None)
                                until = start_time
                                dt_end = component.get("dtend").dt
                                end_time = dt_end.replace(tzinfo=None)
                                summary = component.get("summary").replace("ПР ", "", 1)
                                location = component.get("location").strip(
                                    "Дистанционно "
                                )
                                exd = None
                                interval = 0
                                reg_detector = component.get("RRULE")
                                if reg_detector:
                                    freq = reg_detector.get("FREQ")[0]
                                    day_to_week = 7 if freq == "WEEKLY" else 1
                                    interval = reg_detector.get("INTERVAL")[0] * day_to_week
                                    until = reg_detector.get("UNTIL")[0]
                                    until = until.replace(tzinfo=None)
                                    ex_date = component.get("exdate").dts
                                    exd = [
                                        i.dt.replace(tzinfo=None) for i in ex_date
                                    ]  # список datetime исключений
                                if not reg_detector and summary.startswith("Э"):
                                    summary = summary.replace("Э", "Экз", 1)
                                await generate_schedule(
                                    start_time,
                                    end_time,
                                    summary,
                                    teacher_fio,
                                    location,
                                    group_name,
                                    until,
                                    exd,
                                    interval,
                                )
                else:
                    print(f"⚠ Ошибка {response.status} для {url}")
        except Exception as e:
            print(f"⚠ Ошибка при обработке {url}: {e}")


async def generate_schedule(
    start_time, end_time, description, teacher, location, group_name, until, ex_date, interval
):
    # Генерируем расписание на ближайшие две недели
    """
    Генерирует расписание для указанной группы на ближайшие две недели.
    Эта функция выполняет следующие шаги:
    1. Рассчитывает конечную дату семестра (май или февраль).
    2. Проверяет, если дата мероприятия находится после текущей даты.
    3. Вставляет события в базу данных, если их еще нет, исключая даты из списка `exdate`.

    Параметры:
    1) start_time: Начальная дата для создания расписания;
    2) end_time: Конечная дата для создания расписания;
    3) description: Описание предмета или задачи;
    4) teacher: ФИО преподавателя;
    5) location: Местоположение занятия;
    6) group_name: Название группы;
    7) until: Дата окончания регулярных пар.
    8) ex_date: Список дат исключений.
    9) interval: Интервал в днях для повторяющихся событий.
    """
    if ex_date is None:
        ex_date = []
    current_date = datetime.now()
    end_time += timedelta(minutes=peremen_minutes)
    async with aiosqlite.connect(getenv("DATABASE_NAME")) as conn:
        async with conn.cursor() as cursor:
            while start_time <= until:
                if current_date <= start_time:
                    await cursor.execute(
                        """SELECT 1 FROM TIMETABLE WHERE GroupName = ?
                     AND TeacherFIO = ? AND Task = ? AND Start_Year = ? AND Start_Month = ? AND Start_Day = ? AND Start_Hour = ? 
                     AND Start_Minute = ? AND LOCATION = ?""",
                        (
                            group_name,
                            teacher,
                            description,
                            start_time.year,
                            start_time.month,
                            start_time.day,
                            start_time.hour,
                            start_time.minute,
                            location,
                        ),
                    )
                    exists = await cursor.fetchone()
                    if not exists and start_time not in ex_date:
                        await cursor.execute(
                            """INSERT INTO TIMETABLE (GroupName, TeacherFIO, Task, Start_Year,
                        Start_Month, Start_Day, Start_Hour, Start_Minute, End_Year, End_Month, End_Day, End_Hour, End_Minute, location) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                group_name,
                                teacher,
                                description,
                                start_time.year,
                                start_time.month,
                                start_time.day,
                                start_time.hour,
                                start_time.minute,
                                end_time.year,
                                end_time.month,
                                end_time.day,
                                end_time.hour,
                                end_time.minute,
                                location,
                            ),
                        )
                        await conn.commit()
                if interval == 0: # ОДНОРАЗОВОЕ СОБЫТИЕ (ЭКЗАМЕН/ЗАЧ/КОНС)
                    break
                # Добавляем x дней (интервал)
                start_time += timedelta(days=interval)
                end_time += timedelta(days=interval)
