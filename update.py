import requests
from icalendar import Calendar
from datetime import datetime, timedelta


def get_schedule():
    for i in range(1, 2):
        url = "" # взять из БД
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
                        if isinstance(dtstart, datetime):  # Форматирование дат (если объект datetime, выводим только дату)
                            dtstart_str = dtstart.strftime(
                                '%Y-%m-%d %H:%M') if dtstart.hour or dtstart.minute else dtstart.strftime('%Y-%m-%d')
                        else:
                            dtstart_str = str(dtstart)
                        if isinstance(dtend, datetime):
                            dtend_str = dtend.strftime(
                                '%Y-%m-%d %H:%M') if dtend.hour or dtend.minute else dtend.strftime('%Y-%m-%d')
                        else:
                            dtend_str = str(dtend)
                        if description: # темка C БД
                            test = description.split('\n')
                            if len(test) == 2:
                                teacher_fio = test[0].replace('Преподаватель: ', '')
                                print(f"Дата начала: {dtstart_str}")
                                print(f"Дата окончания: {dtend_str}")
                                print(f"Описание: {summary}")
                                print(f"ФИО: {teacher_fio}")
                                print(f"Место проведения: {location}")
                                print("-" * 50)
        else:
            print(f"⚠ Ошибка {response.status_code} для {url}")



def generate_schedule(start_date, end_date, description, teacher, location):
    # Определяем конец семестра
    current_date = datetime.now()
    if current_date.month > 1: # Если месяц позже января (например, февраль и далее), то конец семестра - май
        end_of_semester = datetime(current_date.year, 5, 31)
    else:
        end_of_semester = datetime(current_date.year, 9, 30)
    # Генерируем расписание
    full_schedule = []
    while start_date <= end_of_semester:
        print((start_date, end_date, description, teacher, location))
        start_date += timedelta(weeks=2)  # Добавляем 2 недели
        end_date += timedelta(weeks=2)

print("Расписание до конца семестра сохранено в 'полное_расписание.txt'")