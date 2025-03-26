import sqlite3
from datetime import datetime


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
        ids = [row[0] for row in result]  # Преобразуем список кортежей в список ID
        cursor.execute(f"DELETE FROM Timetable WHERE ID IN ({','.join(['?'] * len(ids))})", ids)
        cursor.execute(f"DELETE FROM Ochered WHERE Numseance IN ({','.join(['?'] * len(ids))})", ids)
        conn.commit()
    conn.close()