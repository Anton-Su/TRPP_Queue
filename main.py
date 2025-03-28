from datetime import datetime, timedelta
from os import getenv
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from validation import form_correctslinks
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from schedule import refresh_schedule, get_schedule
from deletion import delete_old_sessions
import sqlite3
import logging
import asyncio


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
    ], resize_keyboard=True)
kbnotregister = ReplyKeyboardMarkup( # Создаем кнопку, которую видит только незарегистрированный пользователь
    keyboard=[
        [KeyboardButton(text="Помощь"), KeyboardButton(text="Регистрация")]
    ], resize_keyboard=True)


class RegisterState(StatesGroup): # Определяем состояния для FSM
    group = State()
    name = State()
    surname = State()
    middle_name = State()


async def dindin(): # заглушка для реализации обработки начала занятия
    print("Пары в период такой-то начались")
    pass


async def dandalan(): # заглушка для реализации обработки конца занятия
    print("Пары в период такой-то закончились")
    pass


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
    keyboard.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="remove_keyboard")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def generatescheduler_to_currect_day(): # установка будильников на текущий день
    conn = sqlite3.connect(getenv("DATABASE_URL"))
    cursor = conn.cursor()
    current_date = datetime.now()
    hour_minute = cursor.execute("SELECT DISTINCT Hour, Minute FROM Timetable WHERE Month = ? AND Day = ?",
                                 (current_date.month, current_date.day)).fetchall()  # Получаем все строки в виде списка кортежей
    if hour_minute:
        for hour, minute in hour_minute:
            existing_job = scheduler.get_job(f"{hour}_{minute}")
            if not existing_job: # если id такого не встречалось
                start_date = datetime(current_date.year, current_date.month, current_date.day, hour, minute)
                end_date = start_date + timedelta(minutes=90)
                scheduler.add_job(dindin, 'date', run_date=start_date, id=f"{hour}_{minute}")
                scheduler.add_job(dandalan, 'date', run_date=end_date, id=f"{end_date.hour}_{end_date.minute}")


@dp.message(Command("stats")) # Команда посмотреть статистику
@dp.message(lambda message: message.text == "Cтатистика") # Обрабатываем и "Статистика"
async def command_start_handler(message: Message) -> None:
    user_id = message.from_user.id
    conn = sqlite3.connect(getenv("DATABASE_URL"))
    cursor = conn.cursor()
    results = []
    year = datetime.now().year
    result = cursor.execute("""
        SELECT T.Task, T.TeacherFIO, T.Month, T.Day, T.Hour, T.Minute, T.Location, O.Poryadok
        FROM Timetable T
        JOIN Ochered O ON T.Id = O.Numseance
        WHERE O.Id = ?
        ORDER BY T.Month ASC, T.Day ASC, T.Hour ASC, T.Minute ASC
    """, (user_id,)).fetchall()
    for index, (subject, teacherfio, month, date, hour, minite, location, Poryadok) in enumerate(result, start=1):
        results.append(
            f"{index}. {Poryadok} место в очереди, {str(date).rjust(2, '0')}.{str(month).rjust(2, '0')}.{year} {str(hour).rjust(2, '0')}:{str(minite).rjust(2, '0')}\n«{subject}», проходит в «{location}», ведёт {teacherfio}")
    conn.commit()
    conn.close()
    results.insert(0, f'Всего активных записей: {len(results)}')
    await message.answer("\n".join(results), reply_markup=kbregister)


@dp.message(Command("exit"))  # Команда выйти из системы
@dp.message(lambda message: message.text == "Выйти")  # Обрабатываем и "Выйти"
async def command_start_handler(message: Message) -> None:
    user_id = message.from_user.id
    conn = sqlite3.connect(getenv("DATABASE_URL"))
    cursor = conn.cursor()
    group = cursor.execute("SELECT GroupName FROM Users WHERE Id = ?", (user_id,)).fetchone()[0]
    count = len(cursor.execute("SELECT Id FROM Users WHERE GroupName = ?", (group,)).fetchall())
    numseances = cursor.execute("SELECT DISTINCT Numseance FROM Ochered WHERE Id = ?", (user_id,)).fetchall() # Получаем все numseance, в которых пользователь был записан
    cursor.execute("DELETE FROM Ochered WHERE Id = ?", (user_id,))
    # Пересчитываем порядок (Poryadok) для всех numseance, в которых был пользователь
    for (numseance,) in numseances:
        records = cursor.execute("""SELECT Id FROM Ochered WHERE Numseance = ? ORDER BY Poryadok ASC""", (numseance,)).fetchall()
        for index, (record_id,) in enumerate(records, start=1):
            cursor.execute("UPDATE Ochered SET Poryadok = ? WHERE Id = ?", (index, record_id))
    cursor.execute("DELETE FROM Users WHERE Id = ?", (user_id,))
    if count == 1: # Если он был последним участником группы, удаляем все данные группы
        cursor.execute("DELETE FROM All_groups WHERE GroupName = ?", (group,))
        cursor.execute("DELETE FROM Timetable WHERE GroupName = ?", (group,))
        await message.answer(f"Юзер, довожу до вашего сведения: с вашим уходом группа «{group}» распущена!")
    conn.commit()
    conn.close()
    await message.answer("😢😢😢Очень жаль с вами расставаться, Юзер, возвращайтесь поскорее!!!!!", reply_markup=kbnotregister)


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
    await show_calendar(user_id=callback.from_user.id, callback=callback)


async def show_calendar(user_id: int, message: types.Message = None, callback: CallbackQuery = None): #Универсальная функция для показа календаря (из команды и callback-запроса
    conn = sqlite3.connect(getenv("DATABASE_URL"))
    cursor = conn.cursor()
    group = cursor.execute("SELECT GroupName FROM Users WHERE Id = ?", (user_id,)).fetchone()
    if not group:
        if message:
            return await message.answer("Вы не зарегистрированы!", reply_markup=kbnotregister)
        return await callback.answer("Вы не зарегистрированы!", reply_markup=kbnotregister)
    raspisanie = cursor.execute(
        "SELECT DISTINCT Month, Day FROM Timetable WHERE GroupName = ? ORDER BY Month ASC, Day ASC",
        (group[0],)).fetchall()
    conn.close()
    keyboard = generate_calendar(raspisanie)
    if message: # Определяем, как отправить сообщение
        await message.answer("Определитесь с датой:", reply_markup=keyboard)
    elif callback:
        await callback.message.edit_text("Определитесь с датой:", reply_markup=keyboard)


@dp.message(Command("record")) # команда записи/отмены записи
@dp.message(lambda message: message.text == "Забронировать") # обрабатываем и "Забронировать"
async def command_start_handler(message: types.Message) -> None:
    await show_calendar(user_id=message.from_user.id, message=message)


@dp.callback_query(F.data.startswith("remove_keyboard"))
async def remove_keyboard(callback: CallbackQuery): #  Удаляет всю inline-клавиатуру после нажатия на кнопку.
    await callback.message.delete()


@dp.callback_query(F.data.startswith("date_")) # Обработчик выбора даты
async def show_schedule(callback: CallbackQuery):
    selected_date = callback.data.split("_")[1]  # Дата в формате YYYY-MM-DD
    user_id = callback.from_user.id
    conn = sqlite3.connect(getenv("DATABASE_URL"))
    cursor = conn.cursor()
    groupname = cursor.execute("SELECT GroupName FROM Users WHERE Id = ?", (user_id,)).fetchone()[0] # Получаем группу пользователя
    subjects = cursor.execute("""SELECT Task, Month, Day, Hour, Minute, Location FROM Timetable WHERE GroupName = ? AND Month = ? AND Day = ?""",
                              (groupname, selected_date.split("-")[1], selected_date.split("-")[2])).fetchall() # Получаем расписание на выбранную дату
    conn.close()
    keyboard = []
    for subject in subjects:
        task, month, day, hour, minute, location = subject
        # Формируем текст кнопки с названием предмета, временем и местом
        text = f"{location} {str(hour).rjust(2, '0')}:{str(minute).rjust(2, '0')} - {task}"
        button = InlineKeyboardButton(
            text=text[0:60],  # Реальные данные предмета
            callback_data=f"subject_{month}_{day}_{hour}_{minute}_{location}_{groupname}"  # Передаем в callback_data параметры
        )
        keyboard.append([button])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_to_calendar_{selected_date}")])
    keyboard.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="remove_keyboard")])
    await callback.message.edit_text("Выберите предмет:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


@dp.callback_query(F.data.startswith("subject_"))  # Обработчик выбора предмета
async def handle_subject(callback: CallbackQuery):
    _, month, day, hour, minute, location, groupname = callback.data.split("_")
    user_id = callback.from_user.id
    conn = sqlite3.connect(getenv("DATABASE_URL"))
    cursor = conn.cursor()
    numseance = cursor.execute("SELECT Id FROM Timetable WHERE GroupName = ? AND Month = ? AND Day = ? AND Hour = ? AND Minute = ? AND Location = ?",(groupname, month, day, hour, minute, location)).fetchone()[0]
    result = cursor.execute("""SELECT MAX(Poryadok) FROM Ochered WHERE numseance = ?""", (numseance,)).fetchone()
    if result[0] is not None:
        new_poryadok = result[0] + 1 # Если записи найдены, result[0] будет наибольшим Poryadok
    else:
        new_poryadok = 1
    if cursor.execute("SELECT 1 FROM Ochered WHERE Numseance = ? AND Id = ?", (numseance, user_id)).fetchone():
        cursor.execute("DELETE FROM Ochered WHERE Numseance = ? AND Id = ?", (numseance, user_id))
        # Получаем все оставшиеся записи, отсортированные по Poryadok
        records = cursor.execute("""SELECT Id FROM Ochered WHERE numseance = ? ORDER BY Poryadok ASC""", (numseance,)).fetchall()
        for index, (record_id,) in enumerate(records, start=1): # Пересчитываем Poryadok заново
            cursor.execute("""UPDATE Ochered SET Poryadok = ? WHERE Id = ?""", (index, record_id))
        conn.commit()
        conn.close()
        return await callback.answer("Запись отменена!")
    cursor.execute("""INSERT INTO Ochered (Numseance, Id, Poryadok) VALUES (?, ?, ?)""", (numseance, user_id, new_poryadok))
    conn.commit()
    conn.close()
    await callback.answer(f"Успешно! Ваш номер в очереди: {new_poryadok}")


@dp.message(Command("register")) # Обработчик команды /register
@dp.message(lambda message: message.text == "Регистрация")  # Обрабатываем и "Регистрация"
async def register(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    conn = sqlite3.connect(getenv("DATABASE_URL"))
    cursor = conn.cursor()
    groupname = cursor.execute("SELECT GroupName FROM Users WHERE ID = ?", (user_id,)).fetchone()
    if not groupname:
        await message.answer("Введите вашу группу:")
        await state.set_state(RegisterState.group)
    else:
        await message.answer("Вы уже зарегистрированы!", reply_markup=kbregister)
    conn.close()


@dp.message(RegisterState.group) # Обработка ввода группы
async def process_group(message: types.Message, state: FSMContext):
    await state.update_data(group=message.text.upper())
    conn = sqlite3.connect(getenv("DATABASE_URL"))
    cursor = conn.cursor()
    url = cursor.execute("SELECT Url FROM Session WHERE GroupName = ?", (message.text.upper(),)).fetchone()
    conn.close()
    if not url:
        await message.answer("⚠ Ошибка: Такой группы не существует. Попробуйте еще раз.", reply_markup=kbnotregister)
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
    conn = sqlite3.connect(getenv("DATABASE_URL"))
    cursor = conn.cursor()
    cursor.execute("""INSERT INTO Users (ID, GroupName, NAME, SURNAME, MIDDLE_NAME) VALUES (?, ?, ?, ?, ?)""",
                   (message.from_user.id, user_data['group'], user_data['name'], user_data['surname'], middle_name))
    conn.commit()
    if not cursor.execute("SELECT 1 FROM All_groups WHERE GroupName = ?", (user_data['group'],)).fetchone(): # подгрузить расписание группы
        cursor.execute("""INSERT INTO All_groups (GroupName) VALUES (?)""", (user_data['group'],))
        conn.commit()
        cursor.execute("SELECT Url FROM Session WHERE GroupName = ?", (user_data['group'],))
        url = cursor.fetchone()[0]
        await get_schedule(url, user_data['group'])
        await generatescheduler_to_currect_day()
    conn.close()
    await message.answer("✅ Регистрация завершена!", reply_markup=kbregister)
    await state.clear()


async def main_async() -> None: # Run the bot
    await delete_old_sessions()
    await refresh_schedule()
    await generatescheduler_to_currect_day() # начальные три действия
    scheduler.add_job(refresh_schedule, day_of_week='sun', trigger='cron', hour=0, minute=30)
    scheduler.add_job(form_correctslinks, 'cron', month=9, day=1, hour=0, minute=30)
    scheduler.add_job(generatescheduler_to_currect_day, trigger='cron', hour=7, minute=30)
    scheduler.start()
    await dp.start_polling(bot)


def main() -> None:
    asyncio.run(main_async())

if __name__ == '__main__':
    main()