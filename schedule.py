import requests
from icalendar import Calendar
import sqlite3
from os import getenv
from datetime import datetime, timedelta
from validation import get_link_with_current_hash

peremen_minutes = 10  # время перемены, которое нужно добавить к времени занятия


async def refresh_schedule(): # обновить расписание
    """
    Обновляет расписание для всех групп, используя URL, сохраненные в базе данных.
    Функция выполняет следующие шаги:
    1. Получает список всех групп из базы данных.
    2. Для каждой группы извлекает URL, связанный с ней.
    3. Для каждой группы вызывает функцию `get_schedule`, чтобы обновить расписание.
    """
    conn = sqlite3.connect(getenv("DATABASE_NAME"))
    cursor = conn.cursor()
    groups = cursor.execute("SELECT GroupName FROM All_groups").fetchall()  # Получаем все строки в виде списка кортежей
    for group in groups:
        group_name = group[0]
        group_number = cursor.execute("SELECT Url FROM Session WHERE GroupName = ?", (group_name,)).fetchone()[0]
        url = await get_link_with_current_hash() + group_number
        await get_schedule(url, group_name)
    conn.close()


async def get_schedule(url, groupname):
    """
    Получает расписание для конкретной группы, парсит iCal контент и сохраняет его в базе данных.
    Функция выполняет следующие шаги:
    1. Отправляет HTTP-запрос на указанный URL для получения расписания.
    2. Извлекает расписание в формате iCal и парсит его.
    3. Для каждого события в расписании, если оно соответствует определенным критериям, передает данные в `generate_schedule`.

    Параметры:
    1) url: URL, по которому доступно расписание группы в формате iCal;
    2) groupname: Название группы, для которой обновляется расписание.
    """
    response = requests.get(url, timeout=5)
    if response.status_code == 200:
        data = response.json()
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
                    location = component.get('location')
                    exdate = component.get('exdate').dts
                    exd = [i.dt.replace(tzinfo=None) for i in exdate] # список datetime исключений
                    # Передаём даты в виде объектов datetime
                    await generate_schedule(dtstart.replace(tzinfo=None), dtend.replace(tzinfo=None),
                                            summary, teacher_fio, location, groupname, exd)
    else:
        print(f"⚠ Ошибка {response.status_code} для {url}")


async def generate_schedule(start_date, end_date, description, teacher, location, groupname, exdate): # Генерируем расписание на ближайшие две недели
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
    if current_date.month > 1:  # Конец семестра: если после января, конец семестра - май
        end_of_semester = datetime(current_date.year, 6, 16)
    else:
        end_of_semester = datetime(current_date.year, 2, 4)
    conn = sqlite3.connect(getenv("DATABASE_NAME"))
    cursor = conn.cursor()
    end_date += timedelta(minutes=peremen_minutes)
    while start_date <= end_of_semester:
        if current_date <= start_date:
            exists = cursor.execute("""SELECT 1 FROM TIMETABLE WHERE GroupName = ?
             AND TeacherFIO = ? AND Task = ? AND Start_Month = ? AND Start_Day = ? AND Start_Hour = ? 
             AND Start_Minute = ? AND LOCATION = ?""", (
            groupname, teacher, description, start_date.month, start_date.day, start_date.hour, start_date.minute,
            location)).fetchone()
            if not exists and start_date not in exdate:
                cursor.execute("""INSERT INTO TIMETABLE (GroupName, TeacherFIO, Task, 
                Start_Month, Start_Day, Start_Hour, Start_Minute, End_Month, End_Day, End_Hour, End_Minute, location) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (groupname, teacher, description, start_date.month, start_date.day,
                 start_date.hour, start_date.minute, end_date.month, end_date.day, end_date.hour, end_date.minute, location))
                conn.commit()
            break
        # Добавляем 2 недели
        start_date += timedelta(weeks=2)
        end_date += timedelta(weeks=2)
    conn.commit()
    conn.close()
