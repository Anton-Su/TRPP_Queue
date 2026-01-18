from datetime import datetime, timedelta
from os import getenv
import json
from icalendar import Calendar
import aiohttp
import aiosqlite

from bs4 import BeautifulSoup


# output_file = "valid_schedules.txt" # на случай сохранения в файле
# base_url = "https://schedule-of.mirea.ru/_next/data/PuqjJjkncpbeEq4Xieazm/index.json?s=1_"


async def get_link_with_current_hash():
    """
    Получает действительную базовую ссылку на расписание с текущим хэшем.
    """
    url = "https://schedule-of.mirea.ru/"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    text = await response.text()
                    soup = BeautifulSoup(text, "html.parser")
                    script = soup.find("script", id="__NEXT_DATA__")
                    json_data = json.loads(script.string)
                    return f"https://schedule-of.mirea.ru/_next/data/{json_data.get('buildId')}/index.json?s=1_"
    except Exception as e:
        print(f"❌ Ошибка получения хеша {url}: {e}")
        return None


async def form_correctslinks(stop, scheduler, bot):
    print("Процесс удаления соединений запущен")
    """
    Очищает базу данных (асинхронная версия с aiosqlite).
    Функция выполняет следующие действия:
    1. Очищает таблицы базы данных: `Session`, `Users`, `Ochered`, `All_groups`, `Timetable`.
    2. Удаляет ботов из групп (если есть)
    """
    async with aiosqlite.connect(getenv("DATABASE_NAME")) as conn:
        async with conn.cursor() as cursor:
            # Получаем список group_id
            await cursor.execute("SELECT group_id FROM All_groups")
            group_ids = [row[0] for row in await cursor.fetchall()]
            for group_id in group_ids:  # Отправляем сообщения и выходим из чатов
                if group_id:
                    try:
                        await bot.send_message(
                            group_id,
                            "Запущен процесс обновления ссылок (конец полугодия), не беспокоить в течение часа",
                        )
                        await bot.leave_chat(group_id)
                    except Exception as e:
                        print(f"Ошибка при работе с чатом {group_id}: {e}")
            # Очищаем таблицы
            await cursor.execute("DELETE FROM Session;")
            await cursor.execute("DELETE FROM Users;")
            await cursor.execute("DELETE FROM Ochered;")
            await cursor.execute("DELETE FROM All_groups;")
            await cursor.execute("DELETE FROM Timetable;")
            await cursor.execute("DELETE FROM GroupCreaters;")
            await conn.commit()
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
    print("Процесс синхронизаций ссылок запущен")
    base_url = await get_link_with_current_hash()
    if not base_url:
        print("❌ Не могу получить данные групп, снова попробую через час")
        scheduler.add_job(
            form_correctslinksstep_two,
            "date",
            run_date=datetime.now() + timedelta(minutes=60),
            kwargs={"stop": stop, "scheduler": scheduler},
        )
        return
    async with aiosqlite.connect(getenv("DATABASE_NAME")) as conn:
        async with conn.cursor() as cursor:
            async with aiohttp.ClientSession() as session:
                for i in range(stop):
                    url = f"{base_url}{i:03d}"  # Формируем URL
                    try:
                        async with session.get(
                            url, timeout=aiohttp.ClientTimeout(total=5)
                        ) as response:
                            if response.status == 200:
                                data = await response.json()
                                schedule_info = data["pageProps"]["scheduleLoadInfo"]
                                if schedule_info:
                                    group = schedule_info[0]["title"]
                                    schedule = schedule_info[0]["iCalContent"]
                                    realschedule = Calendar.from_ical(schedule)
                                    if (
                                        len(realschedule.walk()) > 5
                                    ):  # расписание реально дано
                                        await cursor.execute(
                                            "INSERT INTO Session (GroupName, Url) VALUES (?, ?)",
                                            (group, i),
                                        )  # так как хэш временный, мы не может сохранить всё, сохраним только последние цифры
                                        await conn.commit()
                            else:
                                print(f"⚠ Ошибка {response.status} для {url}")
                    except Exception as e:
                        print(f"⚠ Ошибка для {url}: {e}")
    print("Процесс синхронизации ссылок окончен!!!")
