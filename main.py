from datetime import datetime
from os import getenv
import re
from aiogram.types import ChatMemberUpdated
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup,
                           CallbackQuery, BotCommand)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from validation import form_correctslinks, get_link_with_current_hash, form_correctslinksstep_two
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from schedule import refresh_schedule, get_schedule, sync
from createdb import create
import aiosqlite
import logging
import asyncio


load_dotenv() # получаю значение токена из специального файла
TOKEN = getenv("BOT_TOKEN")
DATABASE_NAME = getenv("DATABASE_NAME")
dp = Dispatcher()
scheduler = AsyncIOScheduler()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s") # устанавливаю логгирование
logger = logging.getLogger(__name__)
bot = Bot(token=TOKEN)
kbregister = ReplyKeyboardMarkup( # Создаем кнопку, которую видит только зарегистрированный пользователь
    keyboard=[
        [KeyboardButton(text="Создать"), KeyboardButton(text="Выйти")],
        [KeyboardButton(text="Забронировать"), KeyboardButton(text="Cтатистика")]
    ], resize_keyboard=True, one_time_keyboard=False)
kbnotregister = ReplyKeyboardMarkup( # Создаем кнопку, которую видит только незарегистрированный пользователь
    keyboard=[
        [KeyboardButton(text="Помощь"), KeyboardButton(text="Регистрация")]
    ], resize_keyboard=True, one_time_keyboard=False)
kbpass = ReplyKeyboardMarkup( # Создаем кнопку, на которую должен нажать человек, когда он закончил
    keyboard=[
        [KeyboardButton(text="Сдал")]
    ], resize_keyboard=True, one_time_keyboard=True)

MARKDOWN_V2_SPECIAL_CHARS = r"_*[\]()~`>#+-=|{}.!"


def add_job_if_not_exists(job_tag, job_func, run_date):
    if not any(job.id == job_tag for job in scheduler.get_jobs()):
        scheduler.add_job(job_func, 'date', run_date=run_date,
                          kwargs={"month": run_date.month, "date": run_date.day,
                                  "hour": run_date.hour, "minute": run_date.minute}, id=job_tag)


def escape_md(text: str) -> str:
    """
    Экранирует специальные символы MarkdownV2 в строке text, потому что кто-то решил удалить фф-ю из aiogram
    """
    escaped_text = re.sub(
        rf"([{re.escape(MARKDOWN_V2_SPECIAL_CHARS)}])",
        r"\\\1",
        text
    )
    return escaped_text


class RegisterState(StatesGroup):
    """
    Класс состояний для регистрации пользователя в FSM (Finite State Machine).
    Содержит следующие состояния:
    - group: Ввод группы пользователя.
    - name: Ввод имени пользователя.
    - surname: Ввод фамилии пользователя.
    - middle_name: Ввод отчества пользователя.
    """
    group = State()
    name = State()
    surname = State()
    middle_name = State()


class AddState(StatesGroup):
    """
    Класс состояний для регистрации добавления пары в FSM (Finite State Machine).
    Содержит следующие состояния:
    - groupname: Номер группы
    - start: Дата начала пары.
    - end: Дата конца пары.
    - title: Название пары
    - location: Где находится пара
    """
    groupname = State()
    start = State()
    end = State()
    title = State()
    location = State()


async def lighttriggerlistupdate(id_zanyatia: int):
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(f'SELECT Id FROM Ochered WHERE Numseance = ? limit 1', (id_zanyatia,))
            _next_user = await cursor.fetchone()
            if _next_user[0]:
                await bot.send_message(_next_user[0], "Привет, твоя очередь", reply_markup=kbpass)


async def triggerlistupdate(chat_id: int, message_id: int, personality_id: int):
    """
    Фф-я, созданная для обработки очереди. Вызывается
    После каждого нажатия кнопки или иного события, затрагивающего очередь.
    """
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(f'SELECT Id, GroupName, Task FROM Timetable WHERE message_id = ?', (message_id,))
            _class = await cursor.fetchone()
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Записаться", callback_data=f"query_handler_reg_{_class[0]}"),
                     InlineKeyboardButton(text="Поменяться", callback_data=f"query_ustuply_pass_{_class[0]}"),
                     InlineKeyboardButton(text="✅", callback_data=f"query_handler_pass_{_class[0]}")
                     ]
                ]
            )
            await cursor.execute("SELECT NAME, Surname, Middle_name, Id FROM Users WHERE GroupName = ?", (_class[1],))
            _people = await cursor.fetchall()
            await cursor.execute("SELECT Poryadok, Id FROM Ochered WHERE Numseance = ? ORDER BY Poryadok", (_class[0],))
            _schedule = await cursor.fetchall()
            people_dict = {person[3]: person for person in _people}
            __people = []
            for _, person_id in _schedule:
                if person_id in people_dict:
                    __people.append(people_dict[person_id])
            queue_lines = []
            for i in __people:
                text = escape_md(f"{i[0]} {i[1]} {i[2]}")
                nameandid = f'[{text}](tg://user?id={i[3]})'
                queue_lines.append(nameandid)
            queue_text = '\n'.join(queue_lines)
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=keyboard,
                parse_mode="MarkdownV2",
                text=f'У {escape_md(_class[1])} началось занятие: {escape_md(_class[2])}\n\nОчередь:\n{queue_text}')
            if __people and (personality_id == 1 or __people[0][3] == personality_id):
                await bot.send_message(__people[0][3], "Привет, твоя очередь", reply_markup=kbpass)


async def dindin(month: int, date: int, hour: int, minute: int):
    """
    Фф-я для обработки начала занятия.
    - Вызывается по расписанию в указанное время. Устраивает спам-рассылку с очередью.
    """
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT Id, GroupName, Task FROM Timetable WHERE Start_Month = ? AND Start_Day = ? AND Start_Hour = ? AND Start_Minute = ?",
                (month, date, hour, minute))
            _class = await cursor.fetchall()
            await conn.commit()
    for i in _class:
        async with aiosqlite.connect(DATABASE_NAME) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT group_id, thread_id FROM All_groups Where GroupName = ?", (i[1],))
                chat_id_thread = (await cursor.fetchall())[0]
                if chat_id_thread[0] is not None:
                    msg = await bot.send_message(chat_id=chat_id_thread[0], message_thread_id=chat_id_thread[1], text=f"Генерация очереди пары...")
                    try:
                        await bot.pin_chat_message(chat_id_thread[0], msg.message_id)
                    except TelegramBadRequest:
                        await bot.send_message(chat_id=chat_id_thread[0], text="Бот не смог закрепить сообщение, сделайте его админом", reply_to_message_id=msg.message_id, allow_sending_without_reply=True)
                    await cursor.execute("UPDATE Timetable SET message_id = ? WHERE Id = ?", (msg.message_id, i[0]))
                    await conn.commit()
                    await triggerlistupdate(chat_id_thread[0], msg.message_id, 1)
                else:
                    await lighttriggerlistupdate(i[0])



# todo: разобраться с фейковым callback
@dp.callback_query(F.data.startswith("query_handler_reg_"))
async def query_handler_reg(call: CallbackQuery):
    """
    ФФ-я для записи пользователя, используя инлайн клавиатуру.
    """
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            # Проверка регистрации пользователя
            await cursor.execute("SELECT * FROM Users WHERE Id = ?", (call.from_user.id,))
            if await cursor.fetchone() is None:
                return await call.answer("Вы не зарегистрированы!", show_alert=True)
            _class_id = call.data.split("_")[-1]
            await cursor.execute("SELECT * FROM Ochered WHERE Id = ? AND Numseance = ?", (call.from_user.id, _class_id))
            # Получение данных о занятии
            await cursor.execute("SELECT Start_Month, Start_Day, Start_Hour, Start_Minute, Location, GroupName FROM Timetable "
                                 "WHERE Id = ?", (_class_id,))
            _class_data = (await cursor.fetchall())[0]
            call_data = types.CallbackQuery(
                id=call.id,
                from_user=call.from_user,
                data=f'subject_{_class_data[0]}_{_class_data[1]}_{_class_data[2]}_{_class_data[3]}_{_class_data[4]}_{_class_data[5]}',
                message=call.message,
                chat_instance=call.chat_instance
            )
            try:
                await handle_subject(call_data)
            except Exception:
                pass
            await triggerlistupdate(call.message.chat.id, call.message.message_id, call.from_user.id)
    return await call.answer("Done!")


@dp.callback_query(F.data.startswith("query_ustuply_pass_"))
async def query_ustuply_pass(call: CallbackQuery):
    """
    Фф-я для уступления места юзеру.
    """
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            # Проверка регистрации пользователя
            await cursor.execute("SELECT * FROM Users WHERE Id = ?", (call.from_user.id,))
            if await cursor.fetchone() is None:
                return await call.answer("Вы не зарегистрированы!", show_alert=True)
            numseance = call.data.split("_")[-1]
            await cursor.execute("SELECT Poryadok FROM Ochered WHERE Id = ? AND Numseance = ?", (call.from_user.id, numseance))
            row = await cursor.fetchone()
            if row is None:
                return await call.answer("Вы не регистрировались на данную пару!", show_alert=True)
            current_poryadok = row[0]
            await cursor.execute("""
                SELECT Id, Poryadok FROM Ochered WHERE Numseance = ? AND Poryadok > ?
                ORDER BY Poryadok LIMIT 1""", (numseance, current_poryadok))
            next_user = await cursor.fetchone()
            if next_user:
                next_user_id, next_poryadok = next_user
                # Меняем местами Poryadok
                await cursor.execute("""
                    UPDATE Ochered SET Poryadok = -1 WHERE Id = ? AND Numseance = ?""", (call.from_user.id, numseance))
                await cursor.execute("""
                    UPDATE Ochered SET Poryadok = ? WHERE Id = ? AND Numseance = ?""", (current_poryadok, next_user_id, numseance))
                await cursor.execute("""
                    UPDATE Ochered SET Poryadok = ? WHERE Id = ? AND Numseance = ?""", (next_poryadok, call.from_user.id, numseance))
                await conn.commit()
                await call.answer("Вы поменялись.")
                return await triggerlistupdate(call.message.chat.id, call.message.message_id, next_user_id)
            return await call.answer("За вами никого нет.", show_alert=True)


@dp.callback_query(F.data.startswith("query_handler_pass_"))
async def query_handler_pass(call: CallbackQuery):
    """
    Фф-я для сдачи записи пользователя.
    """
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            # Проверка регистрации пользователя
            await cursor.execute("SELECT * FROM Users WHERE Id = ?", (call.from_user.id,))
            if await cursor.fetchone() is None:
                return await call.answer("Вы не зарегистрированы!", show_alert=True)
            _class_id = call.data.split("_")[-1]
            await cursor.execute("SELECT * FROM Ochered WHERE Numseance = ? order by Poryadok limit 1", (_class_id,))
            result = await cursor.fetchone()
            if result is None:
                return await call.answer("Очередь пустая!", show_alert=True)
            if result[1] != call.from_user.id:
                return await call.answer("Вы не первый на данную пару!", show_alert=True)
            # Получение данных о занятии
            await cursor.execute("SELECT Start_Month, Start_Day, Start_Hour, Start_Minute, Location, GroupName FROM Timetable WHERE Id = ?", (_class_id,))
            _class_data = (await cursor.fetchall())[0]
            call_data = types.CallbackQuery(
                id=call.id,
                from_user=call.from_user,
                data=f'subject_{_class_data[0]}_{_class_data[1]}_{_class_data[2]}_{_class_data[3]}_{_class_data[4]}_{_class_data[5]}',
                message=call.message,
                chat_instance=call.chat_instance
            )
            try:
                await handle_subject(call_data)
            except Exception:
                pass
            await triggerlistupdate(call.message.chat.id, call.message.message_id, 1)
    await bot.send_message(chat_id=call.from_user.id, text="Надеюсь, реально сдал", reply_markup=kbregister)
    return await call.answer("Надеюсь, реально сдал", show_alert=True)


@dp.message(lambda message: message.text == "Сдал")  # Обработка псевдонима
@dp.message(Command("pass"))
async def handle_pass(message: Message):
    """Обрабатывает процесс сдачи пользователя в личных сообщениях (не через группу)"""
    user_id = message.from_user.id
    current_time = datetime.now()
    current_month = current_time.month
    current_day = current_time.day
    current_hour = current_time.hour
    current_minute = current_time.minute
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT GroupName FROM Users WHERE Id = ?", (user_id,))
            GroupName = (await cursor.fetchone())[0]
            await cursor.execute("""
                SELECT Id
                FROM Timetable
                WHERE (Start_Month < ? OR (Start_Month = ? AND Start_Day < ?)
                    OR (Start_Month = ? AND Start_Day = ? AND Start_Hour < ?)
                    OR (Start_Month = ? AND Start_Day = ? AND Start_Hour = ? AND Start_Minute <= ?))
                    AND (End_Month > ? OR (End_Month = ? AND End_Day > ?)
                    OR (End_Month = ? AND End_Day = ? AND End_Hour > ?)
                    OR (End_Month = ? AND End_Day = ? AND End_Hour = ? AND End_Minute >= ?))
                    AND GroupName = ?
                """, (current_month, current_month, current_day, current_month, current_day, current_hour,
                      current_month, current_day, current_hour, current_minute, current_month, current_month,
                      current_day, current_month, current_day, current_hour, current_month, current_day,
                      current_hour, current_minute, GroupName))
            class_id = (await cursor.fetchone())[0]
            await cursor.execute("SELECT Id FROM Ochered WHERE Numseance = ? ORDER BY Poryadok LIMIT 1", (class_id,))
            first = (await cursor.fetchone())
            if first and first[0] == user_id:
                await cursor.execute("DELETE FROM Ochered WHERE Numseance = ? AND Id = ?", (class_id, user_id))
                await conn.commit()
                await message.answer("Надеюсь, реально сдал!", reply_markup=kbregister)
                await cursor.execute("SELECT message_id FROM Timetable Where Id = ?", (class_id,))
                message_id = (await cursor.fetchall())[0]
                if message_id[0] is None:
                    return await lighttriggerlistupdate(class_id)
                await cursor.execute("SELECT group_id FROM All_groups Where GroupName = ?", (GroupName,))
                chat_id_thread = (await cursor.fetchall())[0]
                return await triggerlistupdate(chat_id_thread[0], message_id[0], 1)
    if first:
        return await message.answer("Ещё не время!")
    return await message.answer("Мы не нашли вас в очереди!")


async def dandalan(month: int, date: int, hour: int, minute: int):
    """
    Функция для обработки окончания занятия.
    Вызывается в конце занятия.
    Удаляет все упоминания о занятии.
    """
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT GroupName, Id, message_id FROM Timetable WHERE End_Month = ? AND End_Day = ?"
                                 "AND End_Hour = ? AND End_Minute = ?", (month, date, hour, minute))
            _class = await cursor.fetchall()
            for group_name, _, message_id in _class:
                await cursor.execute("SELECT id FROM Ochered WHERE Numseance = ? limit 1", (_,))
                last_people = await cursor.fetchone()
                if last_people is not None:
                    await bot.send_message(last_people[0], "Пара закончилась", reply_markup=kbregister)
                await cursor.execute("DELETE FROM Ochered WHERE Numseance = ?", (_,))
                await cursor.execute("SELECT group_id FROM All_groups WHERE GroupName = ?", (group_name,))
                chat_id = await cursor.fetchone()
                if chat_id:
                    await bot.delete_message(chat_id[0], message_id)
            await cursor.execute("DELETE FROM Timetable WHERE End_Month = ? AND End_Day = ? AND End_Hour = ? AND End_Minute = ?",
                                 (month, date, hour, minute))
            await conn.commit()


async def delete_old_sessions():  # удалить просроченное (на случай перезапуска с уже норм составленным расписанием)
    """
    Удаляет просроченные записи из базы данных (время сеансов раньше текущего момента).
    Эта функция выполняет проверку всех записей в таблице `Timetable` и удаляет те, которые уже прошли по сравнению с текущим временем.
    Просроченные записи удаляются из таблиц `Timetable` и `Ochered`.
    - Вызывает функцию dandalan
    """
    async with aiosqlite.connect(getenv("DATABASE_NAME")) as conn:
        async with conn.cursor() as cursor:
            current_date = datetime.now()
            hour, minute, day, month = current_date.hour, current_date.minute, current_date.day, current_date.month
            # Получаем пары, которые уже начались
            await cursor.execute("""SELECT DISTINCT End_Month, End_Day, End_Hour, End_Minute FROM Timetable 
            WHERE Start_Month < ? OR (Start_Month = ? AND Start_Day < ?) OR (Start_Month = ? AND Start_Day = ? AND Start_Hour < ?) OR (Start_Month = ? AND Start_Day = ? AND Start_Hour = ? AND Start_Minute <= ?)""",
                                 (month, month, day, month, day, hour, month, day, hour, minute))
            result = await cursor.fetchall()
            for end_month, end_day, end_hour, end_minute in result:
                end_datetime = datetime(current_date.year, end_month, end_day, end_hour, end_minute)
                if current_date >= end_datetime:
                    await dandalan(end_month, end_day, end_hour, end_minute)
                else:
                    add_job_if_not_exists(f"end_{end_month:02d}_{end_day:02d}_{end_hour:02d}_{end_minute:02d}", dandalan, end_datetime)


async def generate_calendar(raspisanie): # Функция для генерации клавиатуры-календаря
    """
    Генерирует Inline-клавиатуру с датами на основе переданного расписания.
    Возвращает Inline-клавиатуру с кнопками дат и кнопкой закрытия.
    """
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


async def generatescheduler_to_currect_day():  # установка будильников на текущий день
    """
    Устанавливает будильники (запланированные задачи) на текущий день, используя расписание из базы данных.
    - Подключается к базе данных и получает время запланированных событий.
    - Проверяет, существуют ли уже задачи с таким временем.
    - Если задачи нет, создаёт две задачи:
    1. `dindin` запускается в указанное время.
    2. `dandalan` запускается обычно через 90 (+10) минут после первой (если данные получены из сайта mirea.ru).
    """
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            current_date = datetime.now()
            await cursor.execute("SELECT DISTINCT Start_Hour, Start_Minute FROM Timetable "
                                 "WHERE Start_Month = ? AND Start_Day = ?", (current_date.month, current_date.day))
            start_hour_minute = await cursor.fetchall()
            await cursor.execute(
                "SELECT DISTINCT End_Hour, End_Minute FROM Timetable WHERE Start_Month = ? AND Start_Day = ?",
                (current_date.month, current_date.day))
            end_hour_minute = await cursor.fetchall()
    for start_hour, start_minute in start_hour_minute:
        start_date = datetime(current_date.year, current_date.month, current_date.day, start_hour, start_minute)
        add_job_if_not_exists(f"start_{start_date.month:02d}_{start_date.day:02d}_{start_date.hour:02d}_{start_date.minute:02d}", dindin, start_date)
    for end_hour, end_minute in end_hour_minute:
        end_date = datetime(current_date.year, current_date.month, current_date.day, end_hour, end_minute)
        add_job_if_not_exists(f"end_{end_date.month:02d}_{end_date.day:02d}_{end_date.hour:02d}_{end_date.minute:02d}", dandalan, end_date)


@dp.my_chat_member()
async def on_bot_added_or_delete_to_group(event: ChatMemberUpdated):
    """Автоматически привязывают юзера к группе
    - Вызывается при добавлении бота в группу
    - Вызывается при удалении бота из группы
    """
    if event.chat.type == "private":
        return
    bot_id = (await bot.me()).id
    if event.new_chat_member.user.id != bot_id:
        return None
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            chat_id = event.chat.id
            user_id = event.from_user.id
            if event.new_chat_member.status in ("member", "administrator"):
                try:
                    await cursor.execute("SELECT GroupName FROM Users WHERE Id = ?", (user_id,))
                    user_group = (await cursor.fetchone())[0]
                    await cursor.execute("SELECT group_id FROM All_groups WHERE GroupName = ?", (user_group,))
                    existing_chat_id = (await cursor.fetchone())[0]
                    await bot.get_chat(existing_chat_id)
                    if existing_chat_id != chat_id:
                        await bot.send_message(chat_id, f"{user_group} уже привязан к другой группе.")
                        return await bot.leave_chat(chat_id)
                    return None
                except TypeError:
                    await bot.send_message(chat_id, "Прикалываешься? Юзер не зарегистрирован в системе.")
                    return await bot.leave_chat(chat_id)
                except Exception:
                    await cursor.execute("UPDATE All_groups SET group_id = ?, thread_id = NULL WHERE GroupName = ?", (chat_id, user_group))
                    await conn.commit()
                    return await bot.send_message(chat_id, f"Теперь бот привязан к группе {user_group}.")
            elif event.new_chat_member.status in ("kicked", "left"):
                await cursor.execute("UPDATE All_groups SET group_id = NULL, thread_id = NULL WHERE group_id = ?", (chat_id,))
                await conn.commit()
    return None


@dp.message(Command("link"))
async def link(message: Message):
    """Привязывает бота к определённому топику
    - Если группа обычная (топиков нет), возвращает NULL
     """
    if message.chat.type == "private":
        return
    user_id = message.from_user.id
    thread_id = message.message_thread_id
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            try:
                await cursor.execute("SELECT GroupName FROM Users WHERE Id = ?", (user_id,))
                user_group = (await cursor.fetchone())[0]
                await cursor.execute("SELECT group_id FROM All_groups WHERE GroupName = ?", (user_group,))
                chat_id = (await cursor.fetchone())[0]
                await bot.get_chat(chat_id)
                if message.chat.id == chat_id:
                    await cursor.execute("UPDATE All_groups SET group_id = ?, thread_id = ? WHERE GroupName = ?", (chat_id, thread_id, user_group))
                    await conn.commit()
                    return await message.answer(f"Теперь бот привязан к этому топику группы {user_group}.")
            except TypeError:
                return await message.answer("Вы не зарегистрированы.", reply_markup=kbnotregister)


@dp.message(Command("unlink"))
async def unlink(message: Message):
    """Удаляет бота из группы (команда админа)"""
    if message.chat.type == "private":
        return
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("creator", "administrator"):
        return await message.answer("Вы не админ!")
    chat_id = message.chat.id
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            try:
                await cursor.execute("SELECT Id FROM Users WHERE Id = ?", (message.from_user.id,))
                if not await cursor.fetchone():
                    return await message.answer("Вы не зарегистрированы.", reply_markup=kbnotregister)
                await cursor.execute("SELECT GroupName FROM All_groups WHERE group_id = ?", (chat_id,))
                group_name = (await cursor.fetchone())[0]
                await cursor.execute(
                    "UPDATE All_groups SET group_id = NULL, thread_id = NULL WHERE group_id = ?", (chat_id,))
                await conn.commit()
                await bot.send_message(chat_id, f"Бот отвязан от {group_name}.")
                return await bot.leave_chat(chat_id)
            except TypeError:
                return await message.answer("А чат вообще был к чему-то привязан?")


@dp.message(Command("stats"))  # Команда посмотреть статистику
@dp.message(lambda message: message.text == "Cтатистика")  # Обрабатываем и "Статистика"
async def command_start_handler(message: Message) -> None:
    """Обрабатывает команду /stats, отправляя пользователю его график записей."""
    user_id = message.from_user.id
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
                await cursor.execute("""
                    SELECT T.Task, T.TeacherFIO, T.Start_Month, 
                        T.Start_Day, T.Start_Hour, T.Start_Minute, 
                        T.End_Hour, T.End_Minute, T.Location,
                        (
                            SELECT COUNT(*) + 1
                            FROM Ochered O2
                            WHERE O2.Numseance = O.Numseance
                            AND O2.Poryadok < O.Poryadok
                        ) AS ActualPosition
                    FROM Timetable T
                    JOIN Ochered O ON T.Id = O.Numseance
                    WHERE O.Id = ?
                    ORDER BY T.Start_Month, T.Start_Day, T.Start_Hour, T.Start_Minute
                """, (user_id,))
                result = await cursor.fetchall()
    results = []
    year = datetime.now().year
    count = False
    for index, (subject, teacherfio, start_month, start_date, start_hour, start_minute,
                end_hour, end_minute, location, actual_position) in enumerate(result, start=1):
        # Форматирование даты и времени
        start_time = f"{str(start_date).rjust(2, '0')}.{str(start_month).rjust(2, '0')}.{year} " \
                     f"{str(start_hour).rjust(2, '0')}:{str(start_minute).rjust(2, '0')}"
        end_time = f"{str(end_hour).rjust(2, '0')}:{str(end_minute).rjust(2, '0')}"
        if teacherfio != 'Someone':
            results.append(
                f"{index}. {actual_position} место в очереди, {start_time} - {end_time}*\n"
                f"«{subject}», проходит в «{location}», ведёт {teacherfio}")
            count = True
        else:
            results.append(
                f"{index}. {actual_position} место в очереди, {start_time} - {end_time}\n"
                f"«{subject}», проходит в «{location}». ЭТА ПАРА БЫЛА СОЗДАНА ВРУЧНУЮ")
    if not result:
        await message.answer("На данный момент вы не записаны ни на одно занятие")
        return
    if count:
        results.append("\n*Длительность занятия увеличена на 10 минут, чтобы учесть время перерыва")
    results.insert(0, f'Всего активных записей: {len(result)}')
    await message.answer("\n".join(results))

"""
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣯⣫⣡⡿⡵⣫⣾⣿⡿⣋⣥⣶⣷⣾⣿⣿⣵⣦⣌⠻⣿⣿⣿⣿⣷⣻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢷⠝⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠯⢱⣫⢗⡞⢕⣿⣿⢿⣾⣿⣿⣿⣿⢿⣿⣿⣿⣿⣿⣿⣜⣿⡽⣿⣿⣷⣿⣿⣿⣿⣿⣷⣹⣿⣟⢿⣿⣿⣿⣯⣇⡸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⡟⢠⣏⡟⢟⡾⣾⣿⢳⣿⡿⣷⣿⡿⡫⣾⣿⢿⣿⣿⣿⣿⣿⢻⣿⢿⣿⣿⣧⢿⣿⣿⣿⣿⣯⣿⣿⢸⣿⣿⣿⣇⡘⡽⣌⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⡿⠀⣿⡰⡞⣿⢳⣿⣷⣿⢟⣿⣿⢏⣬⣾⡇⢿⡏⢿⣿⣿⣿⣿⡏⣿⡌⣿⣿⣿⡟⣿⣿⣿⣿⣿⣿⣿⡇⢻⣿⣿⣿⡁⢷⢿⡌⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⢃⠀⢣⣽⣱⡿⣿⡏⣿⣏⣾⡟⣵⣿⣿⣿⣿⡜⣯⢊⢿⣿⣿⣿⣷⣿⡇⣮⢿⣿⣿⣹⣿⣿⣿⣿⣿⣿⣷⢸⣿⣿⣿⣧⣿⡘⣿⢹⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⠼⢠⡽⣿⣿⠇⣿⢸⣟⣾⢯⣾⣿⣿⣿⣿⣿⣷⡜⣯⣎⢻⣿⣿⣿⣿⡇⣿⡎⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡎⣿⢻⣿⣿⣸⡇⢿⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣧⢞⡻⣕⢸⢧⣿⣿⢸⣿⣿⣿⢄⢶⣯⣽⢿⣿⣿⣿⣿⣿⣌⢮⢒⠛⣛⡿⣿⢁⢿⣿⡼⣿⣿⣿⣷⣿⣿⣿⣿⣿⣧⢿⠘⣿⣿⣧⡇⠞⣸⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣾⣾⠆⣤⠘⣷⢹⣿⢹⡇⣏⣿⣷⣾⣯⣼⣿⣿⣿⣿⣟⣑⣓⡙⢣⡉⠆⡟⣼⣦⣻⣧⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠸⡆⣿⣿⣿⢗⡖⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⢧⢫⣰⣿⢋⡇⣮⠘⠻⢞⢿⣷⣾⣻⣿⣿⣿⣿⣿⣿⣿⡿⢆⣙⡼⢀⠻⣛⡷⣻⣽⢻⣿⣿⣿⣿⣿⣿⣿⡏⢸⣿⣿⣽⣿⡘⡇⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⡟⣮⢿⡿⣿⣏⣧⠸⠀⢰⣀⢉⠒⠝⢣⣿⣿⣿⣿⣿⣿⣿⣡⣿⡑⠡⠤⠈⠊⠻⢷⠉⣾⡟⣽⣿⣿⣿⣿⢿⡇⡚⣩⣭⡭⠽⠷⠤⣭⡭⠭⣭⣭⡭⠭⢭⣝⢻
⣿⣿⣿⣿⣿⣿⣿⡇⣿⡇⢣⡏⣿⣝⡀⡇⣷⡹⣌⠳⠤⠌⢻⣿⣿⣿⣿⣿⣿⠟⠁⣀⠉⣉⠉⠉⡤⢠⡤⡀⣐⣿⣿⣻⣿⡿⣼⠃⣻⣭⣿⣶⣶⢳⣗⣶⣿⣿⣶⡶⣖⡴⣫⣴⣿
⣿⣿⣿⣿⣿⣿⣿⣧⢻⡇⢦⢏⢘⡟⣆⢻⢸⣿⣮⣯⣭⣿⣿⣿⣿⣿⣿⠟⡡⣢⣾⡻⣷⣽⣛⣛⡤⣃⣼⣳⣿⡿⣳⡟⣸⣧⣇⢺⣿⣿⣿⡿⣫⣿⠾⡟⣻⣭⡵⣺⣵⣾⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣄⢷⢸⣣⣣⡻⡿⣆⠃⠛⢿⣿⣿⣟⣽⣛⣿⣯⣴⣿⣿⣿⣿⣿⣿⣶⣶⠞⢈⡿⢡⣿⢿⣿⣟⢰⣟⡌⠀⣺⣿⠛⢉⣪⣥⣶⠿⢛⣭⣾⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡍⣷⠈⢤⠻⡙⣧⣳⣄⣭⣿⣸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣟⣥⢎⡾⣵⣿⣵⣿⠯⣲⡟⠍⢠⣶⣿⡭⠶⢟⣋⣭⣶⣿⣈⣝⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣮⣇⠸⣦⠡⠈⠋⢿⣿⣿⣷⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠫⢋⠜⣿⣿⡟⡡⠚⠋⠐⠖⢀⡭⡥⣰⢸⣿⣿⣿⣿⣿⣧⡜⡝⢿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣟⡞⣴⡿⣱⢸⣆⢀⢹⣿⣿⣿⡿⠿⢿⣿⣿⣿⣿⣿⣿⣿⣵⡏⢊⣿⠟⣫⡔⢀⢀⣮⠎⢰⢟⢹⡇⡏⠏⣿⣿⡏⣿⣆⢻⡽⢘⣎⢻⡿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⡺⣽⡿⡇⠊⣿⢏⣷⡝⢽⢿⣿⣯⣯⣿⣿⣿⣿⣿⣿⣿⣿⣿⡰⣚⣵⠿⢋⣴⣏⣜⣎⠆⢯⢧⣿⢸⣷⠂⢻⣿⣿⠘⣿⣕⠻⢯⠻⣆⠙⢿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣫⡾⢷⣿⣾⣿⣿⢏⣾⣿⢳⣷⡜⢽⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠿⢃⢉⣠⣾⣿⠏⢬⢮⠈⢶⡏⣸⣿⣼⣿⣜⡈⣿⣿⣧⢻⣿⣦⠮⡟⣗⡯⣎⠻⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣻⠷⢋⢴⣿⢿⣿⡿⢣⣾⣿⢧⣹⣟⣽⣷⣅⠙⢿⣿⡿⠿⠛⣛⣭⠴⣺⠵⢿⣻⣭⢄⡠⡳⡃⣬⡎⡇⣿⣿⢿⣿⣿⣻⡘⣿⣿⡌⣿⣿⣧⣓⡝⣿⠎⢳⡜⢿
⣿⣿⣿⡿⣿⢽⣾⢵⣰⣫⡿⣵⣿⠟⣡⣿⣿⣳⣷⢯⣾⡏⣸⣟⡖⡂⠠⣤⣤⣤⣤⣶⣶⡾⠿⣻⡻⠁⢈⢊⣜⣼⡟⡄⣧⢿⣿⢸⡞⣿⣷⢷⣜⣿⣿⡘⣿⣿⣧⡈⠺⣧⡈⢿⣾
⣿⢟⠙⣈⣵⢟⣽⣿⣽⣫⣾⡿⡹⣵⣷⡿⣵⡟⣴⣿⠯⢖⣻⣼⡇⠙⣶⠶⠶⠶⡶⠶⣶⣿⡟⣫⢀⣴⣢⡟⣼⣿⣷⡇⢸⡾⣿⡇⡱⠘⣿⣎⣿⣮⢿⣷⡨⡿⣿⣷⣶⡔⢕⠸⣿
⣾⢦⣾⣿⣷⣽⢟⢞⣷⡿⡫⢔⣾⣿⢋⣞⣿⣿⠋⡅⠤⠾⠿⠶⠒⡇⣿⣿⣿⣿⣿⣿⡿⣫⢞⣵⡿⣷⠟⢴⣿⣿⣰⡾⢺⣇⠹⣇⠘⣅⢮⢿⡘⣿⣷⡻⣷⠑⣝⢿⣿⣿⡧⣳⣟
⣷⢿⡿⣻⡿⣫⣾⡿⣏⣺⣪⣿⠟⣡⣿⢏⣶⢿⣴⣾⢍⡩⢟⣟⣳⣀⠿⣿⣿⣿⡿⡯⡟⡵⢟⢛⣾⡯⣼⠊⢹⣿⠔⣰⡄⢿⡴⡽⡔⣤⠪⣓⠓⢝⣿⣿⣾⢷⣈⣷⡟⢿⣿⣿⣾
⣿⣿⣿⣻⡴⣟⣽⣿⡿⣵⢿⢕⣾⣽⣿⣟⣯⣽⣿⣷⣯⣾⡿⢡⣶⣽⣛⣿⡿⢯⣾⢋⣿⣟⣛⣿⣟⣵⣿⢰⢸⣿⣸⣿⣿⡜⣿⡴⣬⡌⠳⠬⡻⢷⡪⣿⣿⣿⣷⡷⣝⣿⣽⣿⣿
"""


@dp.message(Command("exit"))  # Команда выйти из системы
@dp.message(lambda message: message.text == "Выйти")  # Обрабатываем и "Выйти"
async def command_start_handler(message: Message) -> None:
    """
    Обрабатывает выход пользователя из системы и удаляет его данные.
    - Удаляет пользователя из всех очередей (таблицы `Ochered`).
    - Удаляет пользователя из таблицы `Users`.
    - Если он был последним в группе, удаляет данные группы (`All_groups`, `Timetable`).
    """
    user_id = message.from_user.id
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT GroupName FROM Users WHERE Id = ?", (user_id,))
            group = (await cursor.fetchone())[0]
            await cursor.execute("SELECT COUNT(*) FROM Users WHERE GroupName = ?", (group,))
            count = (await cursor.fetchone())[0]
            await cursor.execute("DELETE FROM Ochered WHERE Id = ?", (user_id,))
            await cursor.execute("DELETE FROM Users WHERE Id = ?", (user_id,))
            if count == 1:
                await cursor.execute("SELECT group_id FROM All_groups WHERE GroupName = ?", (group,))
                group_id = (await cursor.fetchone())[0]
                if group_id:
                    await bot.leave_chat(group_id)
                await cursor.execute("DELETE FROM All_groups WHERE GroupName = ?", (group,))
                await cursor.execute("DELETE FROM Timetable WHERE GroupName = ?", (group,))
                await message.answer(f"Юзер, довожу до вашего сведения: с вашим уходом группа «{group}» распущена!")
            await conn.commit()
    await message.answer("😢😢😢Очень жаль с вами расставаться, Юзер, возвращайтесь поскорее!!!!!", reply_markup=kbnotregister)


@dp.message(Command("start")) # Начальная команда
async def command_start_handler(message: Message) -> None:
    """Обрабатывает команду /start, приветствует пользователя и предлагает зарегистрироваться."""
    await message.answer("Привет! Я бот, который регулирует процесс очереди, записываю, отписываю, закрепляю, слежу, и всё такое. Просто зарегистрируйся, добавь бота в группу вашей группы и следуй командам, "
                         "и ты сможешь записываться на занятия, и больше не будешь полагаться на авось", reply_markup=kbnotregister)


@dp.message(Command("help")) # Функция для обработки команды /help
@dp.message(lambda message: message.text == "Помощь")  # Обрабатываем и "Помощь"
async def send_help(message: Message):
    """Обрабатывает команду /help, отправляет шуточное мотивационное сообщение."""
    #await message.answer("ААААА! Альтушкааааа в белых чулочкаааах", reply_markup=kbnotregister)
    #await message.answer("Не делай добра, не получишь и зла!", reply_markup=kbnotregister)
    user_id = message.from_user.id
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT GroupName FROM Users WHERE ID = ?", (user_id,))
            groupname = await cursor.fetchone()
    if not groupname:
        return await message.answer("Похоже, вы не зарегистрированы! Пропишите команду /register, затем создайте тематическую группу и добавьте в неё бота", reply_markup=kbnotregister)
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT group_id FROM All_groups WHERE GroupName = ?", (groupname[0],))
            group_id = await cursor.fetchone()
    if not group_id[0]:
        return await message.answer(
            "Похоже, группы, в которую ваш бот добавлен, ещё не существует! Это сулит ограничением возможности до минимума. Добавьте бота в группу через 'добавить в группу'!",
            reply_markup=kbregister)
    await message.answer("Через 20 лет вы будете больше разочарованы теми вещами, которые вы не делали, чем теми, которые вы сделали. "
                         "Так отчальте от тихой пристани. Почувствуйте попутный ветер в вашем парусе. Двигайтесь вперед, действуйте, открывайте!", reply_markup=kbregister)



@dp.callback_query(F.data.startswith("back_to_calendar_"))
async def back_to_calendar(callback: CallbackQuery):
    """Обрабатывает кнопку назад в inline клавиатуре."""
    await show_calendar(user_id=callback.from_user.id, callback=callback)


async def show_calendar(user_id: int, message: types.Message = None, callback: CallbackQuery = None):  # Универсальная функция для показа календаря (из команды и callback-запроса
    """
    Универсальная функция для отображения календаря пользователю.
    - Извлекает расписание (уникальные даты) из базы данных.
    - Генерирует интерактивную клавиатуру-календарь.
    - Отправляет или редактирует сообщение с календарем в зависимости от типа вызова (команда или callback-запрос).
    """
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT GroupName FROM Users WHERE Id = ?", (user_id,))
            group = await cursor.fetchone()
            if not group:
                if message:
                    return await message.answer("Вы не зарегистрированы!", reply_markup=kbnotregister)
                return await callback.answer("Вы не зарегистрированы!", show_alert=True)
            await cursor.execute("SELECT DISTINCT Start_Month, Start_Day FROM Timetable "
                                 "WHERE GroupName = ? ORDER BY Start_Month, Start_Day", (group[0],))
            raspisanie = await cursor.fetchall()
    keyboard = await generate_calendar(raspisanie)
    if message:
        await message.answer("Определитесь с датой:", reply_markup=keyboard)
    elif callback:
        await callback.message.edit_text("Определитесь с датой:", reply_markup=keyboard)


@dp.message(Command("record")) # команда записи/отмены записи
@dp.message(lambda message: message.text == "Забронировать") # обрабатываем и "Забронировать"
async def command_start_handler(message: types.Message) -> None:
    """Обрабатывает команду /record, вызывая функцию для отображения календаря."""
    await show_calendar(user_id=message.from_user.id, message=message)


@dp.callback_query(F.data.startswith("remove_keyboard"))
async def remove_keyboard(callback: CallbackQuery):
    """Удаляет inline-клавиатуру после нажатия на кнопку "удалить"."""
    await callback.message.delete()


@dp.callback_query(F.data.startswith("date_"))  # Обработчик выбора даты
async def show_schedule(callback: CallbackQuery):
    """
    Обрабатывает выбор даты пользователем и отображает расписание на этот день.
    - Извлекает выбранную дату из callback-запроса.
    - Получает расписание занятий для данной группы на выбранную дату.
    - Генерирует кнопки с предметами, их временем и местом проведения.
    - Позволяет пользователю выбрать предмет или вернуться к календарю.
    """
    selected_date = callback.data.split("_")[1]
    user_id = callback.from_user.id
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT GroupName FROM Users WHERE Id = ?", (user_id,))
            groupname = (await cursor.fetchone())[0]
            await cursor.execute("""
                SELECT Task, Start_Month, Start_Day, Start_Hour, Start_Minute, Location 
                FROM Timetable 
                WHERE GroupName = ? AND Start_Month = ? AND Start_Day = ?
                """, (groupname, selected_date.split("-")[1], selected_date.split("-")[2]))
            subjects = await cursor.fetchall()
    keyboard = []
    for subject in subjects:
        task, month, day, hour, minute, location = subject
        text = f"{location} {str(hour).rjust(2, '0')}:{str(minute).rjust(2, '0')} - {task}"
        button = InlineKeyboardButton(
            text=text[0:60],
            callback_data=f"subject_{month}_{day}_{hour}_{minute}_{location}_{groupname}"
        )
        keyboard.append([button])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_to_calendar_{selected_date}")])
    keyboard.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="remove_keyboard")])
    await callback.message.edit_text("Выберите предмет:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


@dp.callback_query(F.data.startswith("subject_"))  # Обработчик выбора предмета
async def handle_subject(callback: CallbackQuery):
    """
    Обрабатывает выбор предмета пользователем.
    - Извлекает информацию о выбранном предмете из callback-запроса.
    - Определяет, записан ли пользователь на этот предмет.
    - Если записан, удаляет его из очереди.
    - Если не записан, добавляет его в очередь с новым порядковым номером.
    """
    _, month, day, hour, minute, location, groupname = callback.data.split("_")
    user_id = callback.from_user.id
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT Id FROM Timetable WHERE GroupName = ? AND Start_Month = ? "
                "AND Start_Day = ? AND Start_Hour = ? AND Start_Minute = ? AND Location = ?",
                (groupname, month, day, hour, minute, location))
            numseance = (await cursor.fetchone())[0]
            await cursor.execute("SELECT MAX(Poryadok) FROM Ochered WHERE numseance = ?", (numseance,))
            result = await cursor.fetchone()
            new_poryadok = (result[0] + 1) if result[0] is not None else 1
            await cursor.execute("SELECT 1 FROM Ochered WHERE Numseance = ? AND Id = ?", (numseance, user_id))
            if await cursor.fetchone():
                await cursor.execute("DELETE FROM Ochered WHERE Numseance = ? AND Id = ?", (numseance, user_id))
                await conn.commit()
                return await callback.answer("Запись отменена!")
            await cursor.execute("INSERT INTO Ochered (Numseance, Id, Poryadok) VALUES (?, ?, ?)", (numseance, user_id, new_poryadok))
            await conn.commit()
            await cursor.execute("SELECT COUNT(*) FROM Ochered WHERE Numseance = ?", (numseance,))
            queue_position = (await cursor.fetchone())[0]
            await callback.answer(f"Успешно! Ваш номер в очереди: {queue_position}")


@dp.message(Command("register"))  # Обработчик команды /register
@dp.message(lambda message: message.text == "Регистрация")  # Обрабатываем и "Регистрация"
async def register(message: types.Message, state: FSMContext):
    """
    Обрабатывает команду /register.
    - Проверяет, зарегистрирован ли пользователь в базе данных.
    - Если нет, запрашивает у пользователя название группы и переводит FSM в состояние RegisterState.group.
    """
    user_id = message.from_user.id
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT GroupName FROM Users WHERE ID = ?", (user_id,))
            groupname = await cursor.fetchone()
            if not groupname:
                await message.answer("Введите вашу группу:")
                await state.set_state(RegisterState.group)
            else:
                await message.answer("Вы уже зарегистрированы!", reply_markup=kbregister)


@dp.message(Command("sync"))
@dp.message(lambda message: message.text == "Обновить")
async def new_register(message: types.Message) -> None:
    """Обрабатывает команду /sync, обновляя расписание группы юзера по запросу."""
    user_id = message.from_user.id
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT GroupName FROM Users WHERE ID = ?", (user_id,))
            groupname = await cursor.fetchone()
    if groupname:
        await sync(groupname[0])
        await message.answer("Запрос выполнен!", reply_markup=kbregister)
    else:
        await message.answer("Вы не зарегистрированы. Сначала выполните регистрацию.", reply_markup=kbnotregister)


@dp.message(Command("add_pair"))
@dp.message(lambda message: message.text == "Создать")
async def new_register(message: types.Message, state: FSMContext):
    """
    Обрабатывает добавлением юзером своей, неофициальной пары.
    - Если юзер зарегистрирован, пропускает дальше
    """
    user_id = message.from_user.id
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT GroupName FROM Users WHERE ID = ?", (user_id,))
            groupname = await cursor.fetchone()
    if groupname:
        await state.update_data(groupname=groupname[0])
        await message.answer("Введите дату начала пары в формате: ДД.ММ ЧЧ:ММ (например, 02.09 12:30)")
        await state.set_state(AddState.start)
    else:
        await message.answer("Вы не зарегистрированы. Сначала выполните регистрацию.", reply_markup=kbnotregister)


@dp.message(AddState.start)
async def process_start(message: types.Message, state: FSMContext):
    """
    Обрабатывает ввод начала добавленного занятия.
    - Если оно верно введено и не раньше текущего времени, то будет переход на конец занятия
    """
    try:
        user_input = message.text.strip()
        parsed = datetime.strptime(user_input, "%d.%m %H:%M")
        start_date = datetime(year=datetime.now().year, month=parsed.month, day=parsed.day, hour=parsed.hour, minute=parsed.minute)
        if start_date < datetime.now():
            await message.answer("Нельзя выбрать прошедшее время. Введите дату и время в будущем.")
            return
        await state.update_data(start=start_date)
        await message.answer("Введите время окончания пары в формате: ЧЧ:ММ (Например, 14:40)")
        await state.set_state(AddState.end)
    except ValueError:
        await message.answer("Неверный формат даты. Попробуйте снова: ДД.ММ ЧЧ:ММ")


@dp.message(AddState.end)
async def process_end(message: types.Message, state: FSMContext):
    """
    Обрабатывает ввод конца добавленного занятия.
    - Если оно верно введено и не раньше начала, то будет переход на название занятия
    """
    try:
        user_input = message.text.strip()
        time_only = datetime.strptime(user_input, "%H:%M").time()
        data = await state.get_data()
        start_date = data["start"]
        # Формируем полноценную дату окончания с той же датой, что и у начала пары
        end_date = datetime(year=start_date.year, month=start_date.month, day=start_date.day, hour=time_only.hour, minute=time_only.minute)
        if end_date <= start_date:
            await message.answer("Дата окончания должна быть позже начала. Попробуйте снова.")
            return
        await state.update_data(end=end_date)
        await message.answer("Введите название пары")
        await state.set_state(AddState.title)
    except ValueError:
        await message.answer("Неверный формат времени. Попробуйте снова: ЧЧ:ММ")


@dp.message(AddState.title)
async def process_title(message: types.Message, state: FSMContext):
    """
    Обрабатывает ввод названия добавленного занятия.
    """
    await state.update_data(title=message.text.capitalize())
    await message.answer("Введите место проведения пары")
    await state.set_state(AddState.location)


@dp.message(AddState.location)
async def process_location(message: types.Message, state: FSMContext):
    """
    Обрабатывает ввод локации добавленного занятия (обрезает до 14 символов).
    - Если в группе пользователя нет пересечений занятий, добавляет новое занятие в базу данных
    - Добавляет временные слоты (если раньше слотов с таким id не было)
    """
    await state.update_data(location=message.text.strip()[:14])
    data = await state.get_data()
    groupname, title = data['groupname'], data['title']
    location, start_date, end_date = data['location'], data['start'], data['end']
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            new_start_minutes = start_date.hour * 60 + start_date.minute
            new_end_minutes = end_date.hour * 60 + end_date.minute
            await cursor.execute("""SELECT 1 FROM Timetable WHERE GroupName = ? AND Start_Month = ? AND Start_Day = ?
                      AND End_Month = ? AND End_Day = ? AND ((Start_Hour * 60 + Start_Minute) < ? AND (End_Hour * 60 + End_Minute) > ?)""",
                                 (groupname, start_date.month, start_date.day, end_date.month, end_date.day, new_end_minutes, new_start_minutes))
            conflict_pair = await cursor.fetchone()
            if conflict_pair:
                await message.answer(f"Не забивай на свои же пары, студент {groupname}!")
                await state.clear()
                return
            await cursor.execute("""INSERT INTO Timetable (GroupName, TeacherFIO, Task, Start_Month, Start_Day, 
            Start_Hour, Start_Minute, End_Month, End_Day, End_Hour, End_Minute, location) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                 (groupname, "Someone", title, start_date.month, start_date.day,
                                  start_date.hour, start_date.minute, end_date.month, end_date.day, end_date.hour,
                                  end_date.minute, location))
            await conn.commit()
    start_tag = f"start_{start_date.month:02d}_{start_date.day:02d}_{start_date.hour:02d}_{start_date.minute:02d}"
    end_tag = f"end_{end_date.month:02d}_{end_date.day:02d}_{end_date.hour:02d}_{end_date.minute:02d}"
    # Проверка: есть ли уже такие слоты в планировщике
    add_job_if_not_exists(start_tag, dindin, start_date)
    add_job_if_not_exists(end_tag, dandalan, end_date)
    await message.answer("Пара успешно добавлена!", reply_markup=kbregister)
    await state.clear()


@dp.message(RegisterState.group)  # Обработка ввода группы
async def process_group(message: types.Message, state: FSMContext):
    """
    Обрабатывает ввод группы пользователя и проверяет ее наличие в базе данных.
    - Получает введенную пользователем группу.
    - Проверяет, существует ли группа в базе данных.
    - Если группа существует, запрашивает ввод имени пользователя.
    - Если группа не существует, отправляет ошибку и очищает состояние.
    """
    await state.update_data(group=message.text.upper())
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT Url FROM Session WHERE GroupName = ?", (message.text.upper(),))
            group_number = await cursor.fetchone()
    if not group_number:
        await message.answer("⚠ Ошибка: Такой группы не существует. Попробуйте еще раз.", reply_markup=kbnotregister)
        await state.clear()
        return
    await message.answer("Введите ваше имя:")
    await state.set_state(RegisterState.name)


@dp.message(RegisterState.name) # Обработка ввода имени
async def process_name(message: types.Message, state: FSMContext):
    """Обрабатывает ввод имени пользователя и переходит к вводу фамилии."""
    await state.update_data(name=message.text.capitalize())
    await message.answer("Введите вашу фамилию:")
    await state.set_state(RegisterState.surname)


@dp.message(RegisterState.surname) # Обработка ввода фамилии
async def process_surname(message: types.Message, state: FSMContext):
    """Обрабатывает ввод фамилии пользователя и переходит к вводу отчества."""
    await state.update_data(surname=message.text.capitalize())
    await message.answer("Введите ваше отчество (если нет, напишите '-'): ")
    await state.set_state(RegisterState.middle_name)


@dp.message(RegisterState.middle_name)  # Обработка ввода отчества и сохранение в БД
async def process_middle_name(message: types.Message, state: FSMContext):
    """
    Обрабатывает ввод отчества пользователя, сохраняет данные в базе и завершает регистрацию.
    - После успешного ввода отчества сохраняет все данные пользователя в таблице `Users`.
    - Если группа еще не существует в таблице `All_groups`, добавляет группу и подгружает расписание.
    - Завершает регистрацию, отправляя сообщение пользователю и очищая состояние.
    """
    user_data = await state.get_data()
    middle_name = message.text.capitalize() if message.text != "-" else ''
    async with aiosqlite.connect(DATABASE_NAME) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""INSERT INTO Users (ID, GroupName, NAME, SURNAME, MIDDLE_NAME) VALUES (?, ?, ?, ?, ?)""",
                (message.from_user.id, user_data['group'], user_data['name'], user_data['surname'], middle_name))
            await conn.commit()
            await cursor.execute("SELECT 1 FROM All_groups WHERE GroupName = ?", (user_data['group'],))
            if not await cursor.fetchone():
                await cursor.execute("""INSERT INTO All_groups (GroupName) VALUES (?)""", (user_data['group'],))
                await conn.commit()
                await cursor.execute("SELECT Url FROM Session WHERE GroupName = ?", (user_data['group'],))
                url_data = await cursor.fetchone()
                current_hash = await get_link_with_current_hash()
                if not current_hash:
                    await message.answer("✅ Регистрация завершена, группа создана, но сайт миреа точка ру не отвечает, расписание не подгружено "
                                         "(maybe, bot hosts not in Russia?)", reply_markup=kbregister)
                    return
                url = current_hash + str(url_data[0])
                await get_schedule(url, user_data['group'])
                await generatescheduler_to_currect_day()
    await message.answer("✅ Регистрация завершена!", reply_markup=kbregister)
    await state.clear()


async def main_async() -> None: # Run the bot
    """
    Основная асинхронная функция для запуска бота и настройки задач.
    - Закрепляет основные команды взаимодействия юзера с ботом
    - Выполняет начальные действия, такие как удаление старых сессий, обновление расписания и генерация будильников для текущего дня.
    - Добавляет задачи в планировщик для регулярного обновления расписания и выполнения других задач в заданное время.
    - Запускает основной цикл бота, который обрабатывает сообщения от пользователей.
    Моментальные задачи:
    - `create`: создаёт таблицы в базе данных (и саму базу), если они не существуют.
    - `delete_old_sessions`: удаляет старые сессии.
    - `refresh_schedule`: обновляет расписание.
    - `generatescheduler_to_currect_day`: генерирует будильники на текущий день.
    - Регулярные задачи:
    - Обновление расписания каждое воскресенье в 00:30.
    - Генерация правильных ссылок 1 сентября в 00:30 и 2 февраля в 00:30. Вторая делается из расчёта на то, что 4 курс второго семестра не имеет расписания.
    - Генерация расписания пар на текущий день каждый день в 07:30.
    Если база данных не создана, вызывается функция `form_correctslinksstep_two` с параметрами 7000 и `scheduler`.
    """
    await bot.set_my_commands([
        BotCommand(command="/add_pair", description="Добавить уникальное занятие"),
        BotCommand(command="/link", description="Привязать бота к топику"),
        BotCommand(command="/unlink", description="Отвязать бота от чата"),
        BotCommand(command="/pass", description="Подтвердить посещение"),
        BotCommand(command="/help", description="Ценный совет"),
        BotCommand(command="/start", description="Начальная команда"),
        BotCommand(command="/register", description="Зарегистрироваться в системе"),
        BotCommand(command="/stats", description="Статистика"),
        BotCommand(command="/exit", description="Выход из системы"),
        BotCommand(command="/record", description="Забронировать / отменить бронь"),
        BotCommand(command="/sync", description="Синхронизировать расписание"),
    ])
    bd = create()
    await delete_old_sessions()
    await refresh_schedule()
    if bd:
        await form_correctslinksstep_two(7000, scheduler)
    await generatescheduler_to_currect_day() # начальные три действия
    scheduler.add_job(refresh_schedule, trigger='cron', hour=0, minute=30)
    scheduler.add_job(form_correctslinks, 'cron', month=9, day=1, hour=0, minute=30, kwargs= {"stop": 7000, "scheduler": scheduler, "bot": bot})
    scheduler.add_job(generatescheduler_to_currect_day, trigger='cron', hour=7, minute=30)
    scheduler.add_job(form_correctslinks, 'cron', month=2, day=1, hour=0, minute=30, kwargs= {"stop": 7000, "scheduler": scheduler, "bot": bot})
    scheduler.start()
    await dp.start_polling(bot)


def main() -> None:
    asyncio.run(main_async())


if __name__ == '__main__':
    main()
