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


async def get_schedule(url, groupName):
    response = requests.get(url, timeout=5)
    if response.status_code == 200:
        data = response.json()
        schedule_info = data["pageProps"]["scheduleLoadInfo"]
        if schedule_info:
            schedule_info = schedule_info[0]
            schedule = schedule_info["iCalContent"]
            realschedule = Calendar.from_ical(schedule)
            for component in realschedule.walk():
                if component.name == "VEVENT":
                    dtstart = component.get('dtstart').dt
                    dtend = component.get('dtend').dt
                    summary = component.get('summary').replace('ПР ', "", 1)
                    description = str(component.get('description'))
                    location = component.get('location')
                    if description:
                        test = description.split('\n')
                        if len(test) == 2:
                            EXDATE = component.get('exdate').dts
                            Exd = [i.dt.replace(tzinfo=None) for i in EXDATE] # список datetime исключений
                            teacher_fio = test[0].replace('Преподаватель: ', '')
                            # Передаём даты в виде объектов datetime
                            await generate_schedule(dtstart.replace(tzinfo=None), dtend.replace(tzinfo=None), summary,
                                                    teacher_fio, location, groupName, Exd)
    else:
        print(f"⚠ Ошибка {response.status_code} для {url}")


async def generate_schedule(start_date, end_date, description, teacher, location, groupName, EXDATE): # Генерируем расписание на ближайшие две недели
    current_date = datetime.now()
    if current_date.month > 1:  # Конец семестра: если после января, конец семестра - май
        end_of_semester = datetime(current_date.year, 5, 31)
    else:
        end_of_semester = datetime(current_date.year, 12, 31)
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    while start_date <= end_of_semester:
        if current_date <= start_date:
            exists = cursor.execute("""SELECT 1 FROM TIMETABLE WHERE GroupName = ? AND TeacherFIO = ? AND TASK = ? AND MONTH = ? AND DAY = ? AND HOUR = ? AND MINUTE = ? AND LOCATION = ?""", (
            groupName, teacher, description, start_date.month, start_date.day, start_date.hour, start_date.minute,
            location)).fetchone()
            if not exists and start_date not in EXDATE:
                cursor.execute("""INSERT INTO TIMETABLE (GroupName, TeacherFIO, TASK, MONTH, DAY, HOUR, MINUTE, LOCATION) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (groupName, teacher, description, start_date.month, start_date.day, start_date.hour, start_date.minute, location))
                conn.commit()
            break
        start_date += timedelta(weeks=2) # Добавляем 2 недели
        end_date += timedelta(weeks=2)
    conn.commit()
    conn.close()


async def delete_old_sessions(): # удалить просроченное (на случай перезапуска с уже норм составленным расписанием)
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    current_date = datetime.now()
    hour, minute, day, month = current_date.hour, current_date.minute, current_date.day, current_date.month
    result = cursor.execute("SELECT ID FROM Timetable WHERE Month < ? OR (Month = ? AND Day < ?) OR (Month = ? AND Day = ? AND Hour < ?) OR (Month = ? AND Day = ? AND Hour = ? AND Minute < ?)",
                   (month, month, day, month, day, hour, month, day, hour, minute)).fetchall()
    if result:
        cursor.execute("DELETE FROM Timetable WHERE Month < ? OR (Month = ? AND Day < ?) OR (Month = ? AND Day = ? AND Hour < ?) OR (Month = ? AND Day = ? AND Hour = ? AND Minute < ?)",
                   (month, month, day, month, day, hour, month, day, hour, minute))
        ids = [row[0] for row in result]  # Преобразуем список кортежей в список ID
        cursor.execute(f"DELETE FROM Timetable WHERE ID IN ({','.join(['?'] * len(ids))})", ids)
        cursor.execute(f"DELETE FROM Ochered WHERE Numseance IN ({','.join(['?'] * len(ids))})", ids)
        conn.commit()
    conn.close()
