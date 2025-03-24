import requests
from icalendar import Calendar
from datetime import datetime, timedelta


def get_schedule(url):
    response = requests.get(url, timeout=5)
    if response.status_code == 200:
        data = response.json()
        schedule_info = data["pageProps"]["scheduleLoadInfo"]
        if schedule_info:
            schedule_info = schedule_info[0]
            groups = schedule_info["title"]
            schedule = schedule_info["iCalContent"]
            realschedule = Calendar.from_ical(schedule)
            for component in realschedule.walk():
                if component.name == "VEVENT":
                    dtstart = component.get('dtstart').dt
                    dtend = component.get('dtend').dt
                    summary = component.get('summary').replace('ПР ', "", 1)
                    description = str(component.get('description'))
                    location = component.get('location')
                    dtstart_str = dtstart.strftime("%Y-%m-%d %H:%M:%S")
                    dtend_str = dtend.strftime("%Y-%m-%d %H:%M:%S")
                    if description:
                        test = description.split('\n')
                        if len(test) == 2:
                            teacher_fio = test[0].replace('Преподаватель: ', '')
                            print(f"Дата начала: {dtstart_str}")
                            print(f"Дата окончания: {dtend_str}")
                            print(f"Описание: {summary}")
                            print(f"ФИО: {teacher_fio}")
                            print(f"Место проведения: {location}")
                            print("-" * 50)
                            # Передаём даты в виде объектов datetime
                            generate_schedule(dtstart.replace(tzinfo=None), dtend.replace(tzinfo=None), summary, teacher_fio, location)
    else:
        print(f"⚠ Ошибка {response.status_code} для {url}")


def generate_schedule(start_date, end_date, description, teacher, location):
    # Определяем конец семестра
    current_date = datetime.now()
    if current_date.month > 1:  # Если после января, конец семестра - май
        end_of_semester = datetime(current_date.year, 5, 31)
    else:
        end_of_semester = datetime(current_date.year, 9, 30)
    #datetimeObject.astimezone()
    # Генерируем расписание
    full_schedule = []
    while start_date <= end_of_semester:
        if current_date <= start_date:
            print(start_date, end_date, description, teacher, location)
        # Добавляем 2 недели
        start_date += timedelta(weeks=2)
        end_date += timedelta(weeks=2)