from flask import Flask, request, jsonify, render_template, send_file, redirect, session
import sqlite3
import pandas as pd
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = 'supersecretkey'

print("🚀 System Ready")

# ---------------- LOGIN USERS ----------------
USERS = {
    "admin": {"password": "admin123", "role": "admin"},
    "staff1": {"password": "123", "role": "staff"},
    "staff2": {"password": "123", "role": "staff"}
}

# ---------------- DB PATH ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "students.db")

# 🔥 FLAG (IMPORTANT)
db_loaded = False


# ---------------- LOAD EXCEL INTO DB ----------------
def load_excel_to_db():
    excel_path = os.path.join(BASE_DIR, "MBA.xlsx")

    print("📂 Looking for Excel at:", excel_path)

    if not os.path.exists(excel_path):
        print("❌ MBA.xlsx NOT FOUND")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # RESET TABLE
    cursor.execute("DROP TABLE IF EXISTS students")

    cursor.execute("""
        CREATE TABLE students (
            id TEXT PRIMARY KEY,
            srn TEXT,
            name TEXT,
            section TEXT,
            seat TEXT,
            check_in TEXT,
            check_out TEXT,
            remark TEXT
        )
    """)

    df = pd.read_excel(excel_path)

    print("📊 Loading Fresh Data...")

    for _, row in df.iterrows():
        cursor.execute("""
            INSERT INTO students (id, srn, name, section, seat)
            VALUES (?, ?, ?, ?, ?)
        """, (
            str(row.get('PRN', '')).strip(),
            str(row.get('SRN', '')).strip(),
            str(row.get('Name', '')).strip(),
            str(row.get('Section', '')).strip(),
            str(row.get('Seat Number', '')).replace("-", "").strip()
        ))

    conn.commit()
    conn.close()

    print("✅ Fresh Data Loaded Successfully")


# 🔥 RUN ONLY ON FIRST REQUEST (Flask 3 FIX)
@app.before_request
def initialize_once():
    global db_loaded
    if not db_loaded:
        print("🔄 First request → loading database...")
        load_excel_to_db()
        db_loaded = True


# ---------------- LOGIN ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form['username']
        pwd = request.form['password']

        if user in USERS and USERS[user]["password"] == pwd:
            session['user'] = user
            session['role'] = USERS[user]["role"]
            return redirect('/')

        return "Invalid Credentials"

    return render_template('login.html')


# ---------------- LOGOUT ----------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# ---------------- HOME ----------------
@app.route('/')
def home():
    if 'user' not in session:
        return redirect('/login')
    return render_template('index.html', role=session['role'])


# ---------------- SCAN ----------------
@app.route('/scan', methods=['POST'])
def scan():
    data = request.get_json()
    student_id = data.get('student_id')

    time_now = datetime.now().strftime("%H:%M:%S")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name, seat, check_in, check_out 
        FROM students WHERE id=?
    """, (student_id,))

    student = cursor.fetchone()

    if not student:
        conn.close()
        return jsonify({"error": "Student not found"}), 404

    name, seat, check_in, check_out = student

    if not check_in:
        cursor.execute("UPDATE students SET check_in=? WHERE id=?", (time_now, student_id))
        conn.commit()
        conn.close()
        return jsonify({"name": name, "seat": seat, "status": "IN"})

    elif not check_out:
        cursor.execute("UPDATE students SET check_out=? WHERE id=?", (time_now, student_id))
        conn.commit()
        conn.close()
        return jsonify({"name": name, "seat": seat, "status": "OUT"})

    conn.close()
    return jsonify({"status": "DONE"})


# ---------------- SEATS ----------------
@app.route('/seats')
def seats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT seat, check_in, check_out FROM students")
    rows = cursor.fetchall()
    conn.close()

    result = []

    for seat, check_in, check_out in rows:
        if not seat:
            continue

        seat = seat.replace("-", "").strip()

        if check_in and not check_out:
            status = "IN"
        elif check_out:
            status = "OUT"
        else:
            status = "NONE"

        result.append({"seat": seat, "status": status})

    return jsonify(result)


# ---------------- STUDENT ----------------
@app.route('/student/<seat>')
def get_student(seat):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT name, remark FROM students WHERE seat=?", (seat,))
    student = cursor.fetchone()
    conn.close()

    if not student:
        return jsonify({"error": "No student"})

    return jsonify({
        "name": student[0],
        "seat": seat,
        "remark": student[1]
    })


# ---------------- DISCIPLINE ----------------
@app.route('/discipline', methods=['POST'])
def discipline():
    data = request.get_json()
    seat = data.get('seat')
    action = data.get('action')

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("UPDATE students SET remark=? WHERE seat=?", (action, seat))

    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})


# ---------------- DOWNLOAD ----------------
@app.route('/download')
def download():
    conn = sqlite3.connect(DB_PATH)

    df = pd.read_sql_query("""
        SELECT id as PRN, srn as SRN, name as Name, 
               section as Section, seat as Seat,
               check_in as CheckIn, check_out as CheckOut,
               remark as Remarks
        FROM students
    """, conn)

    conn.close()

    file = "attendance.xlsx"
    df.to_excel(file, index=False)

    return send_file(file, as_attachment=True)


# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)