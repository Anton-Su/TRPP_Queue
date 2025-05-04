import json
from icalendar import Calendar
import requests
import sqlite3
from os import getenv
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

#output_file = "valid_schedules.txt" # на случай сохранения в файле
# base_url = "https://schedule-of.mirea.ru/_next/data/PuqjJjkncpbeEq4Xieazm/index.json?s=1_"


async def get_link_with_current_hash():
    """
    Получает действительную базовую ссылку на расписание с текущим хэшем.
    """
    url = 'https://schedule-of.mirea.ru/'
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            script = soup.find('script', id='__NEXT_DATA__')
            json_data = json.loads(script.string)
            return f"https://schedule-of.mirea.ru/_next/data/{json_data.get('buildId')}/index.json?s=1_"
    except requests.RequestException as e:
        print(f"❌ Ошибка получения хеша {url}: {e}")
        return None


async def form_correctslinks(stop, scheduler, bot):
    """
    Очищает базу данных.
    Функция выполняет следующие действия:
    1. Очищает таблицы базы данных: `Session`, `Users`, `Ochered`, `All_groups`, `Timetable`.
    2. Удаляет ботов из групп (если есть)
    """
    conn = sqlite3.connect(getenv("DATABASE_NAME"))
    cursor = conn.cursor()
    group_ids = [row[0] for row in cursor.execute("SELECT group_id FROM All_groups").fetchall()]
    for group_id in group_ids:
        if group_id:
            await bot.send_message(group_id, "Запущен процесс обновления ссылок, не беспокоить в течение двух часов")
            await bot.leave_chat(group_id)
    cursor.execute("DELETE FROM Session;")
    cursor.execute("DELETE FROM Users;")
    cursor.execute("DELETE FROM Ochered;")
    cursor.execute("DELETE FROM All_groups;")
    cursor.execute("DELETE FROM Timetable;")
    conn.commit()
    conn.close()
    return await form_correctslinksstep_two(stop, scheduler)


async def form_correctslinksstep_two(stop, scheduler):
    """
    Формирует правильные ссылки и записывает данные о группах и расписаниях в базу данных.
    Функция выполняет следующие действия:
    1. Для каждого URL, сгенерированного на основе числа от 0 до `stop`, выполняет HTTP-запрос.
    2. Если ответ успешен (код 200), извлекает информацию о расписании в формате iCal и преобразует его.
    3. Если расписание содержит более 5 событий, считается, что у этой группы есть занятия, название группы и URL сохранются в таблицу `Session`.
    4. Если миреа.ру не отвечает - повторяет запрос через час
    """
    base_url = await get_link_with_current_hash()
    if not base_url:
        print(f"❌ Не могу получить данные групп, попробую ещё раз через час")
        scheduler.add_job(form_correctslinksstep_two, 'date', run_date=datetime.now() + timedelta(minutes=60),
                          kwargs= {"stop": stop, "scheduler": scheduler})
        return
    conn = sqlite3.connect(getenv("DATABASE_NAME"))
    cursor = conn.cursor()
    for i in range(stop):
        url = f"{base_url}{i:03d}"  # Формируем URL
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
    conn.commit()
    conn.close()
