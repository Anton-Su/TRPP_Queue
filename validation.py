import json
from icalendar import Calendar
import requests
import sqlite3
from os import getenv
from bs4 import BeautifulSoup

#output_file = "valid_schedules.txt" # на случай сохранения в файле
# base_url = "https://schedule-of.mirea.ru/_next/data/PuqjJjkncpbeEq4Xieazm/index.json?s=1_"


async def get_link_with_current_hash():
    """
    Получает действительную базовую ссылку на расписание с текущим хэшем.
    """
    url = 'https://schedule-of.mirea.ru/'
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    script = soup.find('script', id='__NEXT_DATA__')
    json_data = json.loads(script.string)
    return f"https://schedule-of.mirea.ru/_next/data/{json_data.get('buildId')}/index.json?s=1_"


async def form_correctslinks(base_url, stop=10000):
    """
    Формирует правильные ссылки и записывает данные о группах и расписаниях в базу данных.
    Функция выполняет следующие действия:
    1. Очищает таблицы базы данных: `Session`, `Users`, `Ochered`, `All_groups`, `Timetable`.
    2. Для каждого URL, сгенерированного на основе числа от 0 до `stop`, выполняет HTTP-запрос.
    3. Если ответ успешен (код 200), извлекает информацию о расписании в формате iCal и преобразует его.
    4. Если расписание содержит более 5 событий, считается, что у этой группы есть занятия, название группы и URL сохранются в таблицу `Session`.
    """
    conn = sqlite3.connect(getenv("DATABASE_NAME"))
    cursor = conn.cursor()
    cursor.execute("DELETE FROM Session;")
    cursor.execute("DELETE FROM Users;")
    cursor.execute("DELETE FROM Ochered;")
    cursor.execute("DELETE FROM All_groups;")
    cursor.execute("DELETE FROM Timetable;")
    conn.commit()
    for i in range(stop):
        url = f"{base_url}{i:03d}"  # Формируем URL
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                schedule_info = data["pageProps"]["scheduleLoadInfo"]
                if schedule_info:
                    group = schedule_info[0]["title"]
                    schedule = schedule_info[0]["iCalContent"]
                    realschedule = Calendar.from_ical(schedule)
                    if len(realschedule.walk()) > 5: # расписание реально дано
                        cursor.execute("INSERT INTO Session (GroupName, Url) VALUES (?, ?)",(group, i)) # так как хэш временный, мы не может сохранить всё, сохраним только последние цифры
                        #f.write(group + '?' + url + '\n')
            else:
                print(f"⚠ Ошибка {response.status_code} для {url}")
        except requests.RequestException as e:
            print(f"❌ Ошибка запроса {url}: {e}")
    conn.commit()
    conn.close()
    #f.close()
