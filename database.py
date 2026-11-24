import sqlite3
from pathlib import Path
DB=Path(__file__).with_name('energy.db')
def connect():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init():
    with connect() as c:
        c.executescript('CREATE TABLE IF NOT EXISTS appliances(id INTEGER PRIMARY KEY,name TEXT, watts REAL, qty INTEGER,hours REAL); CREATE TABLE IF NOT EXISTS history(month TEXT PRIMARY KEY,units REAL); CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY,rate REAL,factor REAL,demo INTEGER);')
        if not c.execute('SELECT 1 FROM settings').fetchone():
            c.execute('INSERT INTO settings VALUES(1,8,0.7,1)'); seed(c)
def seed(c):
    c.executemany('INSERT INTO appliances(name,watts,qty,hours) VALUES(?,?,?,?)',[('Air conditioner',1500,1,6),('Ceiling fan',75,2,8),('Television',100,1,4),('Refrigerator (average draw)',50,1,24)])
    c.executemany('INSERT INTO history VALUES(?,?)',[('2026-08',310),('2026-09',345),('2026-10',330)])
