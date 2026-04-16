from flask import Flask, request, jsonify, render_template, send_file, redirect, session
import sqlite3
import pandas as pd
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = 'supersecretkey'

print("🚀 System Ready")

# ---------------- USERS ----------------
USERS = {
    "admin": {"password": "admin123", "role": "admin"},
    "staff1": {"password": "123", "role": "staff"},
    "staff2": {"password": "123", "role": "staff"}
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------- DATABASE ----------------
def get_db():
    auditorium = session.get('auditorium')
    department = session.get('department')

    if not auditorium or not department:
        return None

    db_name = f"{auditorium}_{department}.db"
    db_path = os.path.join(BASE_DIR, db_name)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
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

    conn.commit()
    conn.close()

    return db_path


# ---------------- LOGIN CHECK ----------------
@app.before_request
def check_login():
    allowed = ['login', 'static']

    if request.endpoint not in allowed:
        if 'user' not in session:
            return redirect('/login')


# ---------------- LOGIN ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form['username']
        pwd = request.form['password']

        if user in USERS and USERS[user]["password"] == pwd:
            session.clear()
            session['user'] = user
            session['role'] = USERS[user]["role"]

            return redirect('/select_auditorium')

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
    return redirect('/login')


# ---------------- SELECT AUDITORIUM ----------------
@app.route('/select_auditorium', methods=['GET', 'POST'])
def select_auditorium():
    if request.method == 'POST':
        session['auditorium'] = request.form['auditorium']
        return redirect('/select_department')

    return render_template('select_auditorium.html')


# ---------------- SELECT DEPARTMENT ----------------
@app.route('/select_department', methods=['GET', 'POST'])
def select_department():
    if request.method == 'POST':
        session['department'] = request.form['department']

        db = get_db()
        if db:
            return redirect('/upload')

    return render_template('select_department.html')


# ---------------- UPLOAD ----------------
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    db = get_db()
    if not db:
        return redirect('/select_auditorium')

    if request.method == 'POST':
        file = request.files.get('file')

        if not file or file.filename == '':
            return "Please upload a valid Excel file"

        df = pd.read_excel(file)

        conn = sqlite3.connect(db, check_same_thread=False)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM students")

        for _, row in df.iterrows():
            cursor.execute("""
                INSERT INTO students (id, srn, name, section, seat)
                VALUES (?, ?, ?, ?, ?)
            """, (
                str(row.get('id') or row.get('PRN')),
                str(row.get('srn') or row.get('SRN')),
                row.get('name') or row.get('Name'),
                row.get('section') or row.get('Section'),
                str(row.get('seat') or row.get('Seat')).replace("-", "").strip()
            ))

        conn.commit()
        conn.close()

        return redirect('/grid')

    return render_template('upload.html')


# ---------------- GRID ----------------
@app.route('/grid')
def grid():
    if not session.get('auditorium') or not session.get('department'):
        return redirect('/select_auditorium')

    return render_template(
        'index.html',
        role=session.get('role'),
        auditorium=session.get('auditorium'),
        department=session.get('department')
    )


# ---------------- SCAN ----------------
@app.route('/scan', methods=['POST'])
def scan():
    db = get_db()
    if not db:
        return jsonify({"error": "Session expired"}), 400

    data = request.get_json()
    student_id = data.get('student_id')

    time_now = datetime.now().strftime("%H:%M:%S")

    conn = sqlite3.connect(db, check_same_thread=False)
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
        status = "IN"

    elif not check_out:
        cursor.execute("UPDATE students SET check_out=? WHERE id=?", (time_now, student_id))
        status = "OUT"

    else:
        conn.close()
        return jsonify({"status": "DONE"})

    conn.commit()
    conn.close()

    return jsonify({"name": name, "seat": seat, "status": status})


# ---------------- SEATS ----------------
@app.route('/seats')
def seats():
    db = get_db()
    conn = sqlite3.connect(db)
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


# ---------------- DOWNLOAD ----------------
@app.route('/download')
def download():
    db = get_db()
    conn = sqlite3.connect(db)

    df = pd.read_sql_query("""
        SELECT id as PRN, srn as SRN, name as Name, 
               section as Section, seat as Seat,
               check_in as CheckIn, check_out as CheckOut,
               remark as Remarks
        FROM students
    """, conn)

    conn.close()

    file = f"{session.get('auditorium')}_{session.get('department')}.xlsx"
    df.to_excel(file, index=False)

    return send_file(file, as_attachment=True)


# ---------------- RUN ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=True)