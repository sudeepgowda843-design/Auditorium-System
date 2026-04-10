import pandas as pd
import sqlite3
from datetime import date

df = pd.read_excel("/Users/vishalkirangowda/Desktop/Attendance System/MBA.xlsx")
df.columns = df.columns.str.strip()

today = str(date.today())

conn = sqlite3.connect("students.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS students (
    id TEXT,
    srn TEXT,
    name TEXT,
    section TEXT,
    seat TEXT,
    check_in TEXT,
    check_out TEXT,
    remark TEXT,
    date TEXT,
    PRIMARY KEY (id, date)
)
""")

for _, row in df.iterrows():
    seat = str(row['Seat Number']).replace("-", "").strip()

    cursor.execute("""
        INSERT OR IGNORE INTO students 
        (id, srn, name, section, seat, check_in, check_out, remark, date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(row['PRN']),
        str(row['SRN']),
        row['Name'],
        row['Section'],
        seat,
        None,
        None,
        None,
        today
    ))

conn.commit()
conn.close()

print("✅ Data imported successfully!")