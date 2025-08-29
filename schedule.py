import aiohttp
from icalendar import Calendar
import aiosqlite
from os import getenv
from datetime import datetime, timedelta
from validation import get_link_with_current_hash


peremen_minutes = 10  # время перемены, которое нужно добавить к времени занятия (в минутах)


async def refresh_schedule():  # обновить расписание
    """
    Обновляет расписание для всех групп, используя URL, сохраненные в базе данных.
    Функция выполняет следующие шаги:
    1. Получает список всех групп из базы данных.
    2. Для каждой группы извлекает URL, связанный с ней.
    3. Для каждой группы вызывает функцию `get_schedule`, чтобы обновить расписание.
    """
    currect_hash = await get_link_with_current_hash()
    if not currect_hash:
        return
    print(currect_hash)
    async with aiosqlite.connect(getenv("DATABASE_NAME")) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT GroupName FROM All_groups")
            groups = await cursor.fetchall()  # Получаем все строки в виде списка кортежей
            for group in groups:
                group_name = group[0]
                await cursor.execute("SELECT Url FROM Session WHERE GroupName = ?", (group_name,))
                group_number = (await cursor.fetchone())[0]
                if group_number is None:
                    continue
                url = currect_hash + str(group_number)
                await get_schedule(url, group_name)


async def sync(group_name):  # обновить расписание по запросу
    """
    Обновляет расписание для одной группы, используя URL, сохраненные в базе данных.
    В качестве параметра выступает group_name
    Функция выполняет следующие шаги:
    1. Извлекает URL, связанный с группой.
    2. вызывает функцию `get_schedule`, чтобы обновить расписание.
    """
    async with aiosqlite.connect(getenv("DATABASE_NAME")) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT Url FROM Session WHERE GroupName = ?", (group_name,))
            group_number = (await cursor.fetchone())[0]
            if group_number is not None:
                currect_hash = await get_link_with_current_hash()
                if not currect_hash:
                    return
                url = currect_hash + str(group_number)
                await get_schedule(url, group_name)


async def get_schedule(url, groupname):
    """
    Получает расписание для конкретной группы, парсит iCal контент и сохраняет его в базе данных.
    """
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    data = await response.json()
                    schedule_info = data["pageProps"]["scheduleLoadInfo"]
                    if schedule_info:
                        schedule_info = schedule_info[0]
                        schedule = schedule_info["iCalContent"]
                        realschedule = Calendar.from_ical(schedule)
                        for component in realschedule.walk():
                            if (component.name == "VEVENT" and str(component.get('description'))
                                    and len(str(component.get('description')).split('\n')) == 2):
                                teacher_fio = str(component.get('description')).split('\n')[0].replace('Преподаватель: ', '')
                                dtstart = component.get('dtstart').dt
                                dtend = component.get('dtend').dt
                                summary = component.get('summary').replace('ПР ', "", 1)
                                location = component.get('location').strip('Дистанционно ')
                                try:
                                    exdate = component.get('exdate').dts
                                    exd = [i.dt.replace(tzinfo=None) for i in exdate] # список datetime исключений
                                    await generate_schedule(dtstart.replace(tzinfo=None), dtend.replace(tzinfo=None),
                                                            summary, teacher_fio, location, groupname, exd)
                                except AttributeError:
                                    # сессия, детка
                                    async with aiosqlite.connect(getenv("DATABASE_NAME")) as conn:
                                        async with conn.cursor() as cursor:
                                            start_date = dtstart.replace(tzinfo=None)
                                            end_date = dtend.replace(tzinfo=None)
                                            # if summary.startswith("З"):
                                            #     summary = summary.replace("З", "ЗАЧ")
                                            if summary.startswith("Э"):
                                                summary = summary.replace("Э", "ЭКЗ")
                                            await cursor.execute("""SELECT 1 FROM TIMETABLE WHERE GroupName = ?
                                                                 AND TeacherFIO = ? AND Task = ? AND Start_Month = ? AND Start_Day = ? AND Start_Hour = ?
                                                                 AND Start_Minute = ? AND LOCATION = ?""", (
                                            groupname, teacher_fio, summary, start_date.month, start_date.day,
                                            start_date.hour, start_date.minute, location))
                                            exists = await cursor.fetchone()
                                            if not exists:
                                                await cursor.execute("""INSERT INTO TIMETABLE (GroupName, TeacherFIO, Task,
                                                                    Start_Month, Start_Day, Start_Hour, Start_Minute, End_Month, End_Day, End_Hour, End_Minute, location)
                                                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                                                     (groupname, teacher_fio, summary, start_date.month,
                                                                      start_date.day,
                                                                      start_date.hour, start_date.minute,
                                                                      end_date.month, end_date.day,
                                                                      end_date.hour, end_date.minute, location))
                                                await conn.commit()
                else:
                    print(f"⚠ Ошибка {response.status} для {url}")
        except Exception as e:
            print(f"⚠ Ошибка при обработке {url}: {e}")


async def generate_schedule(start_date, end_date, description, teacher, location, groupname, exdate):  # Генерируем расписание на ближайшие две недели
    """
    Генерирует расписание для указанной группы на ближайшие две недели.
    Эта функция выполняет следующие шаги:
    1. Рассчитывает конечную дату семестра (май или февраль).
    2. Проверяет, если дата мероприятия находится после текущей даты.
    3. Вставляет события в базу данных, если их еще нет, исключая даты из списка `exdate`.

    Параметры:
    1) start_date: Начальная дата для создания расписания;
    2) end_date: Конечная дата для создания расписания;
    3) description: Описание предмета или задачи;
    4) teacher: ФИО преподавателя;
    5) location: Местоположение занятия;
    6) groupname: Название группы;
    7) exdate: Список дат исключений.
    """
    current_date = datetime.now()
    if 2 <= current_date.month <= 7:  # весенний семестр
        end_of_semester = datetime(current_date.year, 7, 10)
    else:  # зимний семестр
        if current_date.month >= 8:
            end_of_semester = datetime(current_date.year + 1, 2, 4)
        else:
            end_of_semester = datetime(current_date.year, 2, 4)
    #print(end_of_semester)
    end_date += timedelta(minutes=peremen_minutes)
    async with aiosqlite.connect(getenv("DATABASE_NAME")) as conn:
        async with conn.cursor() as cursor:
            while start_date <= end_of_semester:
                if current_date <= start_date:
                    await cursor.execute("""SELECT 1 FROM TIMETABLE WHERE GroupName = ?
                     AND TeacherFIO = ? AND Task = ? AND Start_Month = ? AND Start_Day = ? AND Start_Hour = ? 
                     AND Start_Minute = ? AND LOCATION = ?""", (groupname, teacher, description, start_date.month, start_date.day, start_date.hour, start_date.minute, location))
                    exists = await cursor.fetchone()
                    if not exists and start_date not in exdate:
                        await cursor.execute("""INSERT INTO TIMETABLE (GroupName, TeacherFIO, Task, 
                        Start_Month, Start_Day, Start_Hour, Start_Minute, End_Month, End_Day, End_Hour, End_Minute, location) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                             (groupname, teacher, description, start_date.month, start_date.day,
                                              start_date.hour, start_date.minute, end_date.month, end_date.day,
                                              end_date.hour, end_date.minute, location))
                        await conn.commit()
                    break
                # Добавляем 2 недели (интервал)
                start_date += timedelta(weeks=2)
                end_date += timedelta(weeks=2)