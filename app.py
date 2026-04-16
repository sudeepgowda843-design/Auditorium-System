from flask import Flask, render_template, request, redirect, jsonify, session, send_file
import sqlite3
import pandas as pd
import os

app = Flask(__name__)
app.secret_key = "secret123"

# 🔥 DB BASE PATH
DB_FOLDER = "databases"
os.makedirs(DB_FOLDER, exist_ok=True)

# 🔥 AUDITORIUM CONFIG
AUDITORIUM_CONFIG = {
    "1A": {
        "default_cols": 22,
        "rows": list("ABCDEFGHIJKLMNOPQRSTU"),
        "extra_rows": {"V": 15, "W": 13}
    },
    "1B": {
        "default_cols": 22,
        "rows": list("ABCDEFGHIJKLMNOPQRSTU"),
        "extra_rows": {"V": 16, "W": 13}
    },
    "2A": {
        "default_cols": 22,
        "rows": list("ABCDEFGHIJKLMNOPQRSTU"),
        "extra_rows": {}
    },
    "2B": {
        "default_cols": 22,
        "rows": list("ABCDEFGHIJKLMNOPQRSTU"),
        "extra_rows": {}
    }
}

# 🔥 GET CURRENT DB
def get_db():
    audi = session.get("auditorium")
    dept = session.get("department")

    if not audi or not dept:
        return None

    return f"{DB_FOLDER}/{audi}_{dept}.db"

# 🔥 NORMALIZE SEAT
def normalize_seat(seat):
    if not seat:
        return None
    return str(seat).replace("-", "").replace(" ", "").upper()

# 🔥 INIT DB
def init_db(db):
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id TEXT,
        srn TEXT,
        name TEXT,
        section TEXT,
        seat TEXT PRIMARY KEY,
        status TEXT DEFAULT 'OUT',
        remark TEXT
    )
    """)

    conn.commit()
    conn.close()

# =========================
# 🔐 LOGIN
# =========================
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form.get("username")
        password = request.form.get("password")

        if user == "admin" and password == "admin":
            session["role"] = "admin"
        else:
            session["role"] = "staff"

        return redirect('/select_auditorium')

    return render_template('login.html')

# =========================
# 🎯 SELECT AUDITORIUM
# =========================
@app.route('/select_auditorium', methods=['GET', 'POST'])
def select_auditorium():
    if request.method == 'POST':
        session["auditorium"] = request.form.get("auditorium")
        return redirect('/select_department')

    return render_template('select_auditorium.html')

# =========================
# 🎯 SELECT DEPARTMENT
# =========================
@app.route('/select_department', methods=['GET', 'POST'])
def select_department():
    if request.method == 'POST':
        session["department"] = request.form.get("department")

        db = get_db()
        init_db(db)

        if session.get("role") == "admin":
            return redirect('/upload')
        else:
            return redirect('/grid')

    return render_template('select_department.html')

# =========================
# 📤 UPLOAD EXCEL (ADMIN)
# =========================
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if session.get("role") != "admin":
        return redirect('/grid')

    db = get_db()
    if not db:
        return redirect('/select_auditorium')

    if request.method == 'POST':
        file = request.files.get('file')

        if not file or file.filename == '':
            return "Upload valid Excel"

        df = pd.read_excel(file)

        conn = sqlite3.connect(db)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM students")

        for _, row in df.iterrows():
            seat = normalize_seat(row.get('seat') or row.get('Seat'))

            cursor.execute("""
                INSERT INTO students (id, srn, name, section, seat, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                str(row.get('id') or row.get('PRN')),
                str(row.get('srn') or row.get('SRN')),
                row.get('name') or row.get('Name'),
                row.get('section') or row.get('Section'),
                seat,
                "OUT"
            ))

        conn.commit()
        conn.close()

        return redirect('/grid')

    return render_template('upload.html')

# =========================
# 🎯 GRID PAGE (UPDATED)
# =========================
@app.route('/grid')
def grid():
    audi = session.get("auditorium")
    config = AUDITORIUM_CONFIG.get(audi)

    return render_template(
        'index.html',
        rows=config["rows"],
        default_cols=config["default_cols"],
        extra_rows=config["extra_rows"]
    )

# =========================
# 📡 GET ALL SEATS
# =========================
@app.route('/seats')
def get_seats():
    db = get_db()
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    cursor.execute("SELECT seat, name, status FROM students")
    rows = cursor.fetchall()

    conn.close()

    return jsonify([
        {"seat": r[0], "name": r[1], "status": r[2]}
        for r in rows
    ])

# =========================
# 🔍 SCAN STUDENT
# =========================
@app.route('/scan', methods=['POST'])
def scan():
    data = request.get_json()
    student_id = data.get("student_id")

    db = get_db()
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name, seat, status 
        FROM students 
        WHERE srn=? OR id=?
    """, (student_id, student_id))

    student = cursor.fetchone()

    if not student:
        conn.close()
        return jsonify({"error": "Student not found"})

    new_status = "IN" if student[2] != "IN" else "OUT"

    cursor.execute("""
        UPDATE students SET status=? WHERE seat=?
    """, (new_status, student[1]))

    conn.commit()
    conn.close()

    return jsonify({
        "name": student[0],
        "seat": student[1],
        "status": new_status
    })

# =========================
# 🪑 CLICK SEAT
# =========================
@app.route('/student/<seat>')
def get_student(seat):
    db = get_db()
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    seat = normalize_seat(seat)

    cursor.execute("""
        SELECT name, srn, status, remark 
        FROM students WHERE seat=?
    """, (seat,))

    student = cursor.fetchone()
    conn.close()

    if student:
        return jsonify({
            "name": student[0],
            "srn": student[1],
            "status": student[2],
            "remark": student[3]
        })
    else:
        return jsonify({"error": "Not found"})

# =========================
# ⚠️ DISCIPLINE
# =========================
@app.route('/discipline', methods=['POST'])
def discipline():
    data = request.get_json()

    seat = normalize_seat(data.get("seat"))
    action = data.get("action")

    db = get_db()
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE students SET remark=? WHERE seat=?
    """, (action, seat))

    conn.commit()
    conn.close()

    return jsonify({"success": True})

# =========================
# 📥 DOWNLOAD
# =========================
@app.route('/download')
def download():
    db = get_db()
    conn = sqlite3.connect(db)

    df = pd.read_sql_query("SELECT * FROM students", conn)

    file_path = "attendance.xlsx"
    df.to_excel(file_path, index=False)

    conn.close()

    return send_file(file_path, as_attachment=True)

# =========================
# 🔄 RESET
# =========================
@app.route('/reset', methods=['POST'])
def reset():
    if session.get("role") != "admin":
        return jsonify({"error": "Unauthorized"})

    db = get_db()
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    cursor.execute("UPDATE students SET status='OUT', remark=NULL")

    conn.commit()
    conn.close()

    return jsonify({"success": True})

# =========================
# 🚪 LOGOUT
# =========================
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# =========================
# 🚀 RUN
# =========================
if __name__ == '__main__':
    app.run(debug=True)