import sqlite3
from datetime import datetime
from os import getenv

async def delete_old_sessions(): # удалить просроченное (на случай перезапуска с уже норм составленным расписанием)
    """
    Удаляет просроченные записи из базы данных (время сеансов раньше текущего момента).
    Эта функция выполняет проверку всех записей в таблице `Timetable` и удаляет те, которые уже прошли по сравнению с текущим временем.
    Просроченные записи удаляются из таблиц `Timetable` и `Ochered`.
    """

    conn = sqlite3.connect(getenv("DATABASE_NAME"))
    cursor = conn.cursor()
    current_date = datetime.now()
    hour, minute, day, month = current_date.hour, current_date.minute, current_date.day, current_date.month
    result = cursor.execute("SELECT Id FROM Timetable WHERE Start_Month < ? OR (Start_Month = ? AND Start_Day < ?) OR (Start_Month = ? AND Start_Day = ? AND Start_Hour < ?) OR (Start_Month = ? AND Start_Day = ? AND Start_Hour = ? AND Start_Minute < ?)",
                            (month, month, day, month, day, hour, month, day, hour, minute)).fetchall()
    if result:
        cursor.execute("DELETE FROM Timetable WHERE Start_Month < ? OR (Start_Month = ? AND Start_Day < ?) OR (Start_Month = ? AND Start_Day = ? AND Start_Hour < ?) OR (Start_Month = ? AND Start_Day = ? AND Start_Hour = ? AND Start_Minute < ?)",
                   (month, month, day, month, day, hour, month, day, hour, minute))
        ids = [row[0] for row in result]  # Преобразуем список кортежей в список ID
        cursor.execute(f"DELETE FROM Timetable WHERE Id IN ({','.join(['?'] * len(ids))})", ids)
        cursor.execute(f"DELETE FROM Ochered WHERE Numseance IN ({','.join(['?'] * len(ids))})", ids)
        conn.commit()
    conn.close()