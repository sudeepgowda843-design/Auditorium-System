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

# ---------------- DB PATH FIX ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "students.db")


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


# -------------------------------
# SCAN (AUTO + BUTTON)
# -------------------------------
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

    # CHECK-IN
    if not check_in:
        cursor.execute("""
            UPDATE students SET check_in=? 
            WHERE id=?
        """, (time_now, student_id))

        conn.commit()
        conn.close()

        return jsonify({"name": name, "seat": seat, "status": "IN"})

    # CHECK-OUT
    elif not check_out:
        cursor.execute("""
            UPDATE students SET check_out=? 
            WHERE id=?
        """, (time_now, student_id))

        conn.commit()
        conn.close()

        return jsonify({"name": name, "seat": seat, "status": "OUT"})

    conn.close()
    return jsonify({"status": "DONE"})


# -------------------------------
# LOAD SEATS
# -------------------------------
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


# -------------------------------
# GET STUDENT
# -------------------------------
@app.route('/student/<seat>')
def get_student(seat):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name, remark FROM students WHERE seat=?
    """, (seat,))

    student = cursor.fetchone()
    conn.close()

    if not student:
        return jsonify({"error": "No student"})

    return jsonify({
        "name": student[0],
        "seat": seat,
        "remark": student[1]
    })


# -------------------------------
# DISCIPLINE
# -------------------------------
@app.route('/discipline', methods=['POST'])
def discipline():
    data = request.get_json()
    seat = data.get('seat')
    action = data.get('action')

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE students SET remark=? 
        WHERE seat=?
    """, (action, seat))

    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})


# -------------------------------
# DOWNLOAD EXCEL
# -------------------------------
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
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)