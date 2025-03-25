import requests
from icalendar import Calendar
from datetime import datetime, timedelta
import asyncio
from os import getenv
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, \
    CallbackQuery
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

def dindin():
    # заглушка для реализации обработки начала занятия
    # возможно, вызывать вторую такую функция для обработки конца занятия (удаление строк с данными), если занятие состоялось (очередь сформирвоалось), настроить это здесь
    #scheduler.add_job(dindin, 'cron', month=start_date.month, day=start_date.day, hour=start_date.hour, minute=start_date.minute) многоразово
    #scheduler.add_job(dindin, 'date', run_date=start_date)  одноразово
    pass


kb = ReplyKeyboardMarkup( # Создаем кнопки
    keyboard=[
        [KeyboardButton(text="Помощь"), KeyboardButton(text="Авторизация")],
        [KeyboardButton(text="Забронировать"), KeyboardButton(text="Выйти")],
        [KeyboardButton(text="Cтатистика")]
    ],
    resize_keyboard=True
)


async def refresh_schedule():
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
                    if description:
                        test = description.split('\n')
                        if len(test) == 2:
                            teacher_fio = test[0].replace('Преподаватель: ', '')
                            # Передаём даты в виде объектов datetime
                            await generate_schedule(dtstart.replace(tzinfo=None), dtend.replace(tzinfo=None), summary,
                                                    teacher_fio, location, groupName)
    else:
        print(f"⚠ Ошибка {response.status_code} для {url}")


async def generate_schedule(start_date, end_date, description, teacher, location, groupName):
    # Определяем конец семестра
    current_date = datetime.now()
    if current_date.month > 1:  # Если после января, конец семестра - май
        end_of_semester = datetime(current_date.year, 5, 31)
    else:
        end_of_semester = datetime(current_date.year, 9, 30)
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    # Генерируем расписание
    while start_date <= end_of_semester:
        if current_date <= start_date:
            exists = cursor.execute("""
                            SELECT 1 FROM TIMETABLE 
                            WHERE GroupName = ? AND TeacherFIO = ? AND TASK = ? 
                            AND MONTH = ? AND DAY = ? AND HOUR = ? AND MINUTE = ? AND LOCATION = ?
                        """, (
            groupName, teacher, description, start_date.month, start_date.day, start_date.hour, start_date.minute,
            location)).fetchone()
            if not exists:
                cursor.execute("""
                INSERT INTO TIMETABLE (GroupName, TeacherFIO, TASK, MONTH, DAY, HOUR, MINUTE, LOCATION) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (groupName, teacher, description, start_date.month, start_date.day, start_date.hour, start_date.minute, location)
                )
                conn.commit()
                scheduler.add_job(dindin, 'date', run_date=start_date)
            break
        # Добавляем 2 недели
        start_date += timedelta(weeks=2)
        end_date += timedelta(weeks=2)
    conn.commit()


@dp.message(Command("/stats")) # Command handler
@dp.message(lambda message: message.text == "Cтатистика")
async def command_start_handler(message: Message) -> None:
    user_id = message.from_user.id
    # conn = sqlite3.connect("queue.db")
    # cursor = conn.cursor()
    # Group = cursor.execute("SELECT GroupName FROM Users WHERE Id = ?", (user_id,)).fetchone()[0]
    #
    #
    #
    # Count = len(cursor.execute("SELECT Id FROM Users WHERE GroupName = ?", (Group,)).fetchall())
    # cursor.execute("DELETE FROM Users WHERE Id = ?", (user_id,))
    # if Count == 1:
    #     cursor.execute("DELETE FROM All_groups WHERE GroupName = ?", (Group,))
    #     cursor.execute("DELETE FROM Timetable WHERE GroupName = ?", (Group,))
    #     await message.answer("Группа распущена")
    # conn.commit()
    # conn.close()
    await message.answer("Очень жаль с вами расставаться, юзер", reply_markup=kb)



@dp.message(Command("stop")) # Command handler
@dp.message(lambda message: message.text == "Выйти")
async def command_start_handler(message: Message) -> None:
    user_id = message.from_user.id
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    Group = cursor.execute("SELECT GroupName FROM Users WHERE Id = ?", (user_id,)).fetchone()[0]
    Count = len(cursor.execute("SELECT Id FROM Users WHERE GroupName = ?", (Group,)).fetchall())
    cursor.execute("DELETE FROM Users WHERE Id = ?", (user_id,))
    if Count == 1:
        cursor.execute("DELETE FROM All_groups WHERE GroupName = ?", (Group,))
        cursor.execute("DELETE FROM Timetable WHERE GroupName = ?", (Group,))
        await message.answer("Группа распущена")
    conn.commit()
    conn.close()
    await message.answer("Очень жаль с вами расставаться, юзер", reply_markup=kb)


@dp.message(Command("start")) # Command handler
async def command_start_handler(message: Message) -> None:
    await message.answer("Привет! Я бот, который регулирует процесс очереди", reply_markup=kb)


@dp.message(Command("help")) # Функция для обработки команды /help
@dp.message(lambda message: message.text == "Помощь")  # Обрабатываем и "Помощь"
async def send_help(message: Message):
    await message.answer("ААААА! Альтушкааааа в белых чулочкаааах", reply_markup=kb)


# Определяем состояния для FSM
class RegisterState(StatesGroup):
    group = State()
    name = State()
    surname = State()
    middle_name = State()


@dp.callback_query(F.data.startswith("back_to_calendar_"))
async def back_to_calendar(callback: CallbackQuery):
    selected_date = callback.data.split("_")[3]  # Извлекаем выбранную дату (формат YYYY-MM-DD)
    user_id = callback.from_user.id
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    group = cursor.execute("SELECT GroupName FROM Users WHERE Id = ?", (user_id,)).fetchone()  # Получаем группу пользователя
    if not group:
        await callback.answer("Вы не зарегистрированы!")
        return
    raspisanie = cursor.execute("SELECT DISTINCT Month, Day FROM Timetable WHERE GroupName = ? ORDER BY Month ASC, Day ASC", (group[0],)).fetchall()
    conn.close()
    keyboard = generate_calendar(raspisanie)
    await callback.message.edit_text("Определитесь с датой:", reply_markup=keyboard)


# Функция для генерации клавиатуры-календаря
def generate_calendar(raspisanie):
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


@dp.message(Command("show"))
@dp.message(lambda message: message.text == "Забронировать")
async def command_start_handler(message: types.Message) -> None:
    user_id = message.from_user.id
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    group = cursor.execute("SELECT GroupName FROM Users WHERE Id = ?",(user_id,)).fetchone() # Получаем группу пользователя
    if not group:
        await message.answer("Вы не зарегистрированы!")
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
    subjects = cursor.execute("""
        SELECT Task, Month, Day, Hour, Minute, Location
        FROM Timetable
        WHERE GroupName = ? AND Month = ? AND Day = ?
    """, (groupName, selected_date.split("-")[1], selected_date.split("-")[2])).fetchall() # Получаем расписание на выбранную дату
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
    await callback.message.edit_text("Выберите предмет:",
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


@dp.callback_query(F.data.startswith("subject_"))  # Обработчик выбора предмета
async def handle_subject(callback: CallbackQuery):
    _, month, day, hour, minute, location, group_Name = callback.data.split("_")
    user_id = callback.from_user.id
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    numseance = cursor.execute("SELECT Id FROM Timetable WHERE GroupName = ? AND Month = ? AND Day = ? AND Hour = ? AND Minute = ? AND Location = ?",(group_Name, month, day, hour, minute, location)).fetchone()[0]
    result = cursor.execute("""
         SELECT MAX(Poryadok)
         FROM Ochered
         WHERE numseance = ?
     """, (numseance,)).fetchone()
    if result[0] is not None:
        new_poryadok = result[0] + 1 # Если записи найдены, result[0] будет наибольшим Poryadok
    else:
        new_poryadok = 1
    if cursor.execute("SELECT 1 FROM Ochered WHERE Numseance = ? AND Id = ?", (numseance, user_id)).fetchone():
        cursor.execute("DELETE FROM Ochered WHERE Numseance = ? AND Id = ?", (numseance, user_id))
        # Получаем все оставшиеся записи, отсортированные по Poryadok
        records = cursor.execute("""
                SELECT Id FROM Ochered 
                WHERE numseance = ? 
                ORDER BY Poryadok ASC
            """, (numseance,)).fetchall()
        # Пересчитываем Poryadok заново
        for index, (record_id,) in enumerate(records, start=1):
            cursor.execute("""
                    UPDATE Ochered 
                    SET Poryadok = ? 
                    WHERE Id = ?
                """, (index, record_id))
        conn.commit()
        conn.close()
        await callback.answer("Минус запись!")
        return
    cursor.execute("""
            INSERT INTO Ochered (Numseance, Id, Poryadok)
            VALUES (?, ?, ?)
        """, (numseance, user_id, new_poryadok))
    conn.commit()
    conn.close()
    await callback.answer(f"Успешно! Ваш номер в очереди: {new_poryadok}")
    keyboard = [
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"date_{datetime.now().year}-{month}-{day}")]
    ]
    await callback.message.edit_text("Again?",
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


# Обработчик команды /register
@dp.message(Command("register"))
@dp.message(lambda message: message.text == "Авторизация")  # Обрабатываем и "Авторизация"
async def register(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    conn = sqlite3.connect("queue.db")
    cursor = conn.cursor()
    GroupName = cursor.execute("SELECT GroupName FROM Users WHERE ID = ?", (user_id,)).fetchone()
    if not GroupName:
        await message.answer("Введите вашу группу:")
        await state.set_state(RegisterState.group)
    else:
        await message.answer("Вы уже зарегистрированы!")
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
    cursor.execute("""
        INSERT INTO Users (ID, GroupName, NAME, SURNAME, MIDDLE_NAME) 
        VALUES (?, ?, ?, ?, ?)""",
                   (message.from_user.id, user_data['group'], user_data['name'], user_data['surname'], middle_name)
                   )
    conn.commit()
    exists = cursor.execute("SELECT 1 FROM All_groups WHERE GroupName = ?", (user_data['group'],)).fetchone()
    if not exists: # подгрузить расписание
        cursor.execute("""INSERT INTO All_groups (GroupName) VALUES (?)""", (user_data['group'],))
        conn.commit()
        cursor.execute("SELECT Url FROM Session WHERE GroupName = ?", (user_data['group'],))
        url = cursor.fetchone()[0]
        await get_schedule(url, user_data['group'])
    conn.close()
    await message.answer("✅ Регистрация завершена!", reply_markup=kb)
    await state.clear()


@dp.message() # Функция для обработки любого текстового сообщения
async def echo_message(message: Message):
    await message.answer(f"Вы написали: {message.text}")


async def main() -> None: # Run the bot
    scheduler.add_job(form_correctslinks, 'cron', hour=15, minute=15)
    scheduler.add_job(refresh_schedule, day_of_week='sun', trigger='cron', hour=0, minute=30)
    scheduler.add_job(form_correctslinks, 'cron', month=1, day=10, hour=0, minute=30)
    scheduler.add_job(form_correctslinks, 'cron', month=9, day=10, hour=0, minute=30)
    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
