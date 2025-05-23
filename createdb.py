import sqlite3
import os


def create():
    """Создает базу данных SQLite и необходимые таблицы."""
    DB_NAME = os.getenv("DATABASE_NAME")
    if os.path.exists(DB_NAME):
        return False
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Session (
    GroupName TEXT (14) PRIMARY KEY UNIQUE NOT NULL,
    Url INTEGER (4) UNIQUE NOT NULL);
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS All_groups (
    GroupName TEXT (14) UNIQUE NOT NULL,
    group_id INTEGER,
    thread_id INTEGER);
    ''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS Users (
    Id INTEGER PRIMARY KEY UNIQUE NOT NULL,
    GroupName TEXT (14) NOT NULL,
    Name TEXT (30) NOT NULL,
    Surname TEXT (40) NOT NULL,
    Middle_name TEXT (50));
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Ochered (
    Numseance INTEGER NOT NULL,
    Id INTEGER NOT NULL,
    Poryadok INTEGER NOT NULL);
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Timetable (
    GroupName TEXT (14) NOT NULL REFERENCES Session (GroupName),
    TeacherFIO NOT NULL,
    Task TEXT (30) NOT NULL,
    Start_Month INTEGER (3) NOT NULL,
    Start_Day INTEGER (3) NOT NULL,
    Start_Hour INTEGER (3) NOT NULL,
    Start_Minute INTEGER (3) NOT NULL,
    End_Month INTEGER (3) NOT NULL,
    End_Day INTEGER (3) NOT NULL,
    End_Hour INTEGER (3) NOT NULL,
    End_Minute INTEGER (3) NOT NULL,
    Location TEXT (81) NOT NULL,
    Id INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE NOT NULL,
    message_id INTEGER);
    ''')
    conn.commit()
    conn.close()
    return True
