import contextlib
import requests
from icalendar import Calendar
from datetime import datetime, timedelta
import asyncio
from os import getenv
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from validation import form_correctslinks
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import sqlite3


load_dotenv() # получаю значение токена из специального файла
TOKEN = getenv("BOT_TOKEN")
dp = Dispatcher()
scheduler = AsyncIOScheduler()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s") # устанавливаю логгирование
logger = logging.getLogger(__name__)
bot = Bot(token=TOKEN)
kbregister = ReplyKeyboardMarkup( # Создаем кнопку, которую видит только зарегистрированный пользователь
    keyboard=[
        [KeyboardButton(text="Помощь"), KeyboardButton(text="Выйти")],
        [KeyboardButton(text="Забронировать"), KeyboardButton(text="Cтатистика")]
    ],
    resize_keyboard=True)
kbnotregister = ReplyKeyboardMarkup( # Создаем кнопку, которую видит только незарегистрированный пользователь
    keyboard=[
        [KeyboardButton(text="Помощь"), KeyboardButton(text="Регистрация")]
    ],
    resize_keyboard=True)


class RegisterState(StatesGroup): # Определяем состояния для FSM
    group = State()
    name = State()
    surname = State()
    middle_name = State()


async def dindin(): # заглушка для реализации обработки начала занятия
    print(1213213123)
    pass


async def dandalan(): # заглушка для реализации обработки конца занятия
    print(1213132112222222222)
    pass


async def generatescheduler_to_currect_day(): # установка будильников на текущий день
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    current_date = datetime.now()
    Hour_minute = cursor.execute("SELECT DISTINCT Hour, Minute FROM Timetable WHERE Month = ? AND Day = ?",
                                 (current_date.month, current_date.day)).fetchall()  # Получаем все строки в виде списка кортежей
    if Hour_minute:
        for hour, minute in Hour_minute:
            existing_job = scheduler.get_job(f"{hour}_{minute}")
            if not existing_job: # если id такого не встречалось
                start_date = datetime(current_date.year, current_date.month, current_date.day, hour, minute)
                end_date = start_date + timedelta(minutes=90)
                scheduler.add_job(dindin, 'date', run_date=start_date, id=f"{hour}_{minute}")
                scheduler.add_job(dandalan, 'date', run_date=end_date, id=f"{end_date.hour}_{end_date.minute}")


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
        cursor.execute(
            "DELETE FROM Ochered WHERE Numseance = ?)",(result, ))
        conn.commit()
    conn.close()


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
                            teacher_fio = test[0].replace('Преподаватель: ', '')
                            # Передаём даты в виде объектов datetime
                            await generate_schedule(dtstart.replace(tzinfo=None), dtend.replace(tzinfo=None), summary,
                                                    teacher_fio, location, groupName)
    else:
        print(f"⚠ Ошибка {response.status_code} для {url}")


async def generate_schedule(start_date, end_date, description, teacher, location, groupName): # Генерируем расписание на ближайшие две недели
    current_date = datetime.now()
    if current_date.month > 1:  # Конец семестра: если после января, конец семестра - май
        end_of_semester = datetime(current_date.year, 5, 31)
    else:
        end_of_semester = datetime(current_date.year, 9, 30)
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    while start_date <= end_of_semester:
        if current_date <= start_date:
            exists = cursor.execute("""SELECT 1 FROM TIMETABLE WHERE GroupName = ? AND TeacherFIO = ? AND TASK = ? AND MONTH = ? AND DAY = ? AND HOUR = ? AND MINUTE = ? AND LOCATION = ?""", (
            groupName, teacher, description, start_date.month, start_date.day, start_date.hour, start_date.minute,
            location)).fetchone()
            if not exists:
                cursor.execute("""INSERT INTO TIMETABLE (GroupName, TeacherFIO, TASK, MONTH, DAY, HOUR, MINUTE, LOCATION) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (groupName, teacher, description, start_date.month, start_date.day, start_date.hour, start_date.minute, location))
                conn.commit()
            break
        start_date += timedelta(weeks=2) # Добавляем 2 недели
        end_date += timedelta(weeks=2)
    conn.commit()
    conn.close()


@dp.message(Command("/stats")) # Команда посмотреть статистику
@dp.message(lambda message: message.text == "Cтатистика") # Обрабатываем и "Cтатистика"
async def command_start_handler(message: Message) -> None:
    user_id = message.from_user.id
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    Group = cursor.execute("SELECT GroupName FROM Users WHERE Id = ?", (user_id,)).fetchone()[0]
    Numseance_Poryadok = cursor.execute("SELECT Numseance, Poryadok FROM Ochered WHERE Id = ?", (user_id,)).fetchall()
    results = []
    current_date = datetime.now()
    year = current_date.year
    for Num, Poryadok in Numseance_Poryadok:
        subject, teacherfio, month, date, hour, minite, location = cursor.execute("SELECT Task, TeacherFIO, Month, Day, Hour, Minute, Location FROM Timetable WHERE GroupName = ? AND Id = ?", (Group, Num)).fetchall()[0]
        results.append(f"{Poryadok} место в очереди, {location} {str(hour).rjust(2, '0')}:{str(minite).rjust(2, '0')} {str(date).rjust(2, '0')}.{str(month).rjust(2, '0')}.{year} - {subject} - ведёт {teacherfio}")
    results.insert(0, f"Всего активных записей: {len(results)}")
    conn.commit()
    conn.close()
    await message.answer("\n".join(results), reply_markup=kbregister)


@dp.message(Command("exit"))  # Команда выйти из системы
@dp.message(lambda message: message.text == "Выйти")  # Обрабатываем и "Выйти"
async def command_start_handler(message: Message) -> None:
    user_id = message.from_user.id
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    Group = cursor.execute("SELECT GroupName FROM Users WHERE Id = ?", (user_id,)).fetchone()[0]
    Count = len(cursor.execute("SELECT Id FROM Users WHERE GroupName = ?", (Group,)).fetchall())
    numseances = cursor.execute("SELECT DISTINCT Numseance FROM Ochered WHERE Id = ?", (user_id,)).fetchall() # Получаем все numseance, в которых пользователь был записан
    cursor.execute("DELETE FROM Ochered WHERE Id = ?", (user_id,))
    # Пересчитываем порядок (Poryadok) для всех numseance, в которых был пользователь
    for (numseance,) in numseances:
        records = cursor.execute("""SELECT Id FROM Ochered WHERE Numseance = ? ORDER BY Poryadok ASC""", (numseance,)).fetchall()
        for index, (record_id,) in enumerate(records, start=1):
            cursor.execute("UPDATE Ochered SET Poryadok = ? WHERE Id = ?", (index, record_id))
    # Удаляем пользователя из Users
    cursor.execute("DELETE FROM Users WHERE Id = ?", (user_id,))
    # Если он был последним участником группы, удаляем все данные группы
    if Count == 1:
        cursor.execute("DELETE FROM All_groups WHERE GroupName = ?", (Group,))
        cursor.execute("DELETE FROM Timetable WHERE GroupName = ?", (Group,))
        await message.answer("Группа распущена")
    conn.commit()
    conn.close()
    await message.answer("Очень жаль с вами расставаться, юзер, возвращайтесь поскорее", reply_markup=kbnotregister)


@dp.message(Command("start")) # Начальная команда
async def command_start_handler(message: Message) -> None:
    await message.answer("Привет! Я бот, который регулирует процесс очереди, записываю, отписываю, слежу, и всё такое. Просто зарегистрируйся, и ты сможешь записываться на занятия, и больше не будешь полагаться на авось", reply_markup=kbnotregister)


@dp.message(Command("help")) # Функция для обработки команды /help
@dp.message(lambda message: message.text == "Помощь")  # Обрабатываем и "Помощь"
async def send_help(message: Message):
    #await message.answer("ААААА! Альтушкааааа в белых чулочкаааах", reply_markup=kbnotregister)
    await message.answer("Через 20 лет вы будете больше разочарованы теми вещами, которые вы не делали, чем теми, которые вы сделали. Так отчальте от тихой пристани. Почувствуйте попутный ветер в вашем парусе. Двигайтесь вперед, действуйте, открывайте!", reply_markup=kbnotregister)


@dp.callback_query(F.data.startswith("back_to_calendar_"))
async def back_to_calendar(callback: CallbackQuery):
    user_id = callback.from_user.id
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    group = cursor.execute("SELECT GroupName FROM Users WHERE Id = ?", (user_id,)).fetchone()  # Получаем группу пользователя
    if not group:
        await callback.answer("Вы не зарегистрированы!", reply_markup=kbnotregister)
        return
    raspisanie = cursor.execute("SELECT DISTINCT Month, Day FROM Timetable WHERE GroupName = ? ORDER BY Month ASC, Day ASC", (group[0],)).fetchall()
    conn.close()
    keyboard = generate_calendar(raspisanie)
    await callback.message.edit_text("Определитесь с датой:", reply_markup=keyboard)


def generate_calendar(raspisanie): # Функция для генерации клавиатуры-календаря
    days_of_week = {
        "Monday": "Понедельник",
        "Tuesday": "Вторник",
        "Wednesday": "Среда",
        "Thursday": "Четверг",
        "Friday": "Пятница",
        "Saturday": "Суббота",
        "Sunday": "Воскресенье"
    }
    keyboard = []
    for raspisanieday in raspisanie:
        current_date = datetime.now()
        day = datetime(current_date.year, raspisanieday[0], raspisanieday[1])
        day_name = days_of_week[day.strftime("%A")]  # Получаем русское название
        button = InlineKeyboardButton(
            text=f"{day.strftime('%d.%m.%Y')} ({day_name})",
            callback_data=f"date_{day.strftime('%Y-%m-%d')}"
        )
        keyboard.append([button])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


@dp.message(Command("record")) # команда записи/отмены записи
@dp.message(lambda message: message.text == "Забронировать") # обрабатываем и "Забронировать"
async def command_start_handler(message: types.Message) -> None:
    user_id = message.from_user.id
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    group = cursor.execute("SELECT GroupName FROM Users WHERE Id = ?",(user_id,)).fetchone() # Получаем группу пользователя
    if not group:
        await message.answer("Вы не зарегистрированы!", reply_markup=kbnotregister)
        return
    raspisanie = cursor.execute("SELECT DISTINCT Month, DAY FROM Timetable WHERE GroupName = ? ORDER BY Month ASC, Day ASC", (group[0],)).fetchall()
    keyboard = generate_calendar(raspisanie)
    conn.close()
    await message.answer("Определитесь с датой:", reply_markup=keyboard)


@dp.callback_query(F.data.startswith("date_")) # Обработчик выбора даты
async def show_schedule(callback: CallbackQuery):
    selected_date = callback.data.split("_")[1]  # Дата в формате YYYY-MM-DD
    user_id = callback.from_user.id
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    groupName = cursor.execute("SELECT GroupName FROM Users WHERE Id = ?", (user_id,)).fetchone()[0] # Получаем группу пользователя
    subjects = cursor.execute("""SELECT Task, Month, Day, Hour, Minute, Location FROM Timetable WHERE GroupName = ? AND Month = ? AND Day = ?""",
                              (groupName, selected_date.split("-")[1], selected_date.split("-")[2])).fetchall() # Получаем расписание на выбранную дату
    conn.close()
    keyboard = []
    for subject in subjects:
        task, month, day, hour, minute, location = subject
        # Формируем текст кнопки с названием предмета, временем и местом
        text = f"{location} {str(hour).rjust(2, '0')}:{str(minute).rjust(2, '0')} - {task}"
        button = InlineKeyboardButton(
            text=text[0:60],  # Реальные данные предмета
            callback_data=f"subject_{month}_{day}_{hour}_{minute}_{location}_{groupName}"  # Передаем в callback_data параметры
        )
        keyboard.append([button])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_to_calendar_{selected_date}")])
    await callback.message.edit_text("Выберите предмет:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


@dp.callback_query(F.data.startswith("subject_"))  # Обработчик выбора предмета
async def handle_subject(callback: CallbackQuery):
    _, month, day, hour, minute, location, group_Name = callback.data.split("_")
    user_id = callback.from_user.id
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    numseance = cursor.execute("SELECT Id FROM Timetable WHERE GroupName = ? AND Month = ? AND Day = ? AND Hour = ? AND Minute = ? AND Location = ?",(group_Name, month, day, hour, minute, location)).fetchone()[0]
    result = cursor.execute("""SELECT MAX(Poryadok) FROM Ochered WHERE numseance = ?""", (numseance,)).fetchone()
    if result[0] is not None:
        new_poryadok = result[0] + 1 # Если записи найдены, result[0] будет наибольшим Poryadok
    else:
        new_poryadok = 1
    if cursor.execute("SELECT 1 FROM Ochered WHERE Numseance = ? AND Id = ?", (numseance, user_id)).fetchone():
        cursor.execute("DELETE FROM Ochered WHERE Numseance = ? AND Id = ?", (numseance, user_id))
        # Получаем все оставшиеся записи, отсортированные по Poryadok
        records = cursor.execute("""SELECT Id FROM Ochered WHERE numseance = ? ORDER BY Poryadok ASC""", (numseance,)).fetchall()
        # Пересчитываем Poryadok заново
        for index, (record_id,) in enumerate(records, start=1):
            cursor.execute("""UPDATE Ochered SET Poryadok = ? WHERE Id = ?""", (index, record_id))
        conn.commit()
        conn.close()
        await callback.answer("Запись отменена!")
        return
    cursor.execute("""INSERT INTO Ochered (Numseance, Id, Poryadok) VALUES (?, ?, ?)""", (numseance, user_id, new_poryadok))
    conn.commit()
    conn.close()
    await callback.answer(f"Успешно! Ваш номер в очереди: {new_poryadok}")
    keyboard = [[InlineKeyboardButton(text="⬅️ Назад", callback_data=f"date_{datetime.now().year}-{month}-{day}")]]
    await callback.message.edit_text("Успешно. Ещё?",reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


@dp.message(Command("register")) # Обработчик команды /register
@dp.message(lambda message: message.text == "Регистрация")  # Обрабатываем и "Регистрация"
async def register(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    GroupName = cursor.execute("SELECT GroupName FROM Users WHERE ID = ?", (user_id,)).fetchone()
    if not GroupName:
        await message.answer("Введите вашу группу:")
        await state.set_state(RegisterState.group)
    else:
        await message.answer("Вы уже зарегистрированы!", reply_markup=kbregister)
    conn.close()


@dp.message(RegisterState.group) # Обработка ввода группы
async def process_group(message: types.Message, state: FSMContext):
    await state.update_data(group=message.text.upper())
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    url = cursor.execute("SELECT Url FROM Session WHERE GroupName = ?", (message.text.upper(),)).fetchone()
    conn.close()
    if not url:
        await message.answer("⚠ Ошибка: Такой группы не существует. Попробуйте еще раз.")
        await state.clear()
        return
    await message.answer("Введите ваше имя:")
    await state.set_state(RegisterState.name)


@dp.message(RegisterState.name) # Обработка ввода имени
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.capitalize())
    await message.answer("Введите вашу фамилию:")
    await state.set_state(RegisterState.surname)


@dp.message(RegisterState.surname) # Обработка ввода фамилии
async def process_surname(message: types.Message, state: FSMContext):
    await state.update_data(surname=message.text.capitalize())
    await message.answer("Введите ваше отчество (если нет, напишите '-'): ")
    await state.set_state(RegisterState.middle_name)


@dp.message(RegisterState.middle_name) # Обработка ввода отчества и сохранение в БД
async def process_middle_name(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    middle_name = message.text.capitalize() if message.text != "-" else None
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    cursor.execute("""INSERT INTO Users (ID, GroupName, NAME, SURNAME, MIDDLE_NAME) VALUES (?, ?, ?, ?, ?)""",
                   (message.from_user.id, user_data['group'], user_data['name'], user_data['surname'], middle_name))
    conn.commit()
    exists = cursor.execute("SELECT 1 FROM All_groups WHERE GroupName = ?", (user_data['group'],)).fetchone()
    if not exists: # подгрузить расписание группы
        cursor.execute("""INSERT INTO All_groups (GroupName) VALUES (?)""", (user_data['group'],))
        conn.commit()
        cursor.execute("SELECT Url FROM Session WHERE GroupName = ?", (user_data['group'],))
        url = cursor.fetchone()[0]
        await get_schedule(url, user_data['group'])
        await generatescheduler_to_currect_day()
    conn.close()
    await message.answer("✅ Регистрация завершена!", reply_markup=kbregister)
    await state.clear()


async def main() -> None: # Run the bot
    await delete_old_sessions()
    await refresh_schedule()
    await generatescheduler_to_currect_day() # начальные три дейтсвия
    scheduler.add_job(refresh_schedule, day_of_week='sun', trigger='cron', hour=0, minute=30)
    scheduler.add_job(form_correctslinks, 'cron', month=1, day=10, hour=0, minute=30)
    scheduler.add_job(form_correctslinks, 'cron', month=9, day=10, hour=0, minute=30)
    scheduler.add_job(generatescheduler_to_currect_day, trigger='cron', hour=7, minute=30)
    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())