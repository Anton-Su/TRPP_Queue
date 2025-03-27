from icalendar import Calendar
import requests
import sqlite3


#output_file = "valid_schedules.txt" # пока что будем сохранять типа в файле, потом в БД переведу
base_url = "https://schedule-of.mirea.ru/_next/data/PuqjJjkncpbeEq4Xieazm/index.json?s=1_"


def form_correctslinks(stop=10000):
    conn = sqlite3.connect("queue.db")
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
                        cursor.execute("INSERT INTO Session (GroupName, Url) VALUES (?, ?)",(group, url))
                        #f.write(group + '?' + url + '\n')
            else:
                print(f"⚠ Ошибка {response.status_code} для {url}")
        except requests.RequestException as e:
            print(f"❌ Ошибка запроса {url}: {e}")
    conn.commit()
    conn.close()
    #f.close()
