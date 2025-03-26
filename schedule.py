import requests
from icalendar import Calendar
import sqlite3
from datetime import datetime, timedelta


async def refresh_schedule(): # обновить расписание
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    groups = cursor.execute("SELECT GroupName FROM All_groups").fetchall()  # Получаем все строки в виде списка кортежей
    for group in groups:
        group_name = group[0]
        url = cursor.execute("SELECT Url FROM Session WHERE GroupName = ?", (group_name,)).fetchone()[0]
        await get_schedule(url, group_name)
    conn.close()


async def get_schedule(url, groupname):
    response = requests.get(url, timeout=5)
    if response.status_code == 200:
        data = response.json()
        schedule_info = data["pageProps"]["scheduleLoadInfo"]
        if schedule_info:
            schedule_info = schedule_info[0]
            schedule = schedule_info["iCalContent"]
            realschedule = Calendar.from_ical(schedule)
            for component in realschedule.walk():
                if component.name == "VEVENT" and str(component.get('description')) and len(str(component.get('description')).split('\n')) == 2:
                    teacher_fio = str(component.get('description')).split('\n')[0].replace('Преподаватель: ', '')
                    dtstart = component.get('dtstart').dt
                    summary = component.get('summary').replace('ПР ', "", 1)
                    location = component.get('location')
                    exdate = component.get('exdate').dts
                    exd = [i.dt.replace(tzinfo=None) for i in exdate] # список datetime исключений
                    # Передаём даты в виде объектов datetime
                    await generate_schedule(dtstart.replace(tzinfo=None), summary, teacher_fio, location, groupname, exd)
    else:
        print(f"⚠ Ошибка {response.status_code} для {url}")


async def generate_schedule(start_date, description, teacher, location, groupname, exdate): # Генерируем расписание на ближайшие две недели
    current_date = datetime.now()
    if current_date.month > 1:  # Конец семестра: если после января, конец семестра - май
        end_of_semester = datetime(current_date.year, 6, 16)
    else:
        end_of_semester = datetime(current_date.year, 2, 4)
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    while start_date <= end_of_semester:
        if current_date <= start_date:
            exists = cursor.execute("""SELECT 1 FROM TIMETABLE WHERE GroupName = ? AND TeacherFIO = ? AND TASK = ? AND MONTH = ? AND DAY = ? AND HOUR = ? AND MINUTE = ? AND LOCATION = ?""", (
            groupname, teacher, description, start_date.month, start_date.day, start_date.hour, start_date.minute,
            location)).fetchone()
            if not exists and start_date not in exdate:
                cursor.execute("""INSERT INTO TIMETABLE (GroupName, TeacherFIO, TASK, MONTH, DAY, HOUR, MINUTE, LOCATION) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (groupname, teacher, description, start_date.month, start_date.day, start_date.hour, start_date.minute, location))
                conn.commit()
            break
        start_date += timedelta(weeks=2) # Добавляем 2 недели
    conn.commit()
    conn.close()
