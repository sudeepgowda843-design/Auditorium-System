from flask import Flask, render_template, request, redirect, session, jsonify, send_file
import sqlite3
import pandas as pd

app = Flask(__name__)
app.secret_key = "secret123"

AUDITORIUMS = ["1A", "1B", "2A", "2B"]

# ======================
# HELPERS
# ======================

def normalize_seat(seat):
    return str(seat).strip().upper().replace(" ", "").replace("-", "")

def get_db():
    if "auditorium" not in session or "department" not in session:
        return None
    return f"{session['auditorium']}_{session['department']}.db"

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
        status TEXT DEFAULT 'absent'
    )
    """)

    conn.commit()
    conn.close()

# ======================
# LOGIN
# ======================

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        session.clear()

        if username == "admin" and password == "admin":
            session['role'] = 'admin'
            return redirect('/select_auditorium')

        elif username == "staff" and password == "staff":
            session['role'] = 'staff'
            return redirect('/select_auditorium')

        else:
            return "Invalid Login"

    return render_template('login.html')

# ======================
# SELECT AUDITORIUM
# ======================

@app.route('/select_auditorium', methods=['GET', 'POST'])
def select_auditorium():
    if 'role' not in session:
        return redirect('/')

    if request.method == 'POST':
        session['auditorium'] = request.form['auditorium']
        return redirect('/select_department')

    return render_template('select_auditorium.html', auditoriums=AUDITORIUMS)

# ======================
# SELECT DEPARTMENT
# ======================

@app.route('/select_department', methods=['GET', 'POST'])
def select_department():
    if 'role' not in session:
        return redirect('/')

    if request.method == 'POST':
        session['department'] = request.form['department']

        if session['role'] == 'admin':
            return redirect('/upload')
        else:
            return redirect('/grid')

    return render_template('select_department.html')

# ======================
# UPLOAD (ADMIN ONLY)
# ======================

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if session.get('role') != 'admin':
        return redirect('/grid')

    db = get_db()
    if not db:
        return redirect('/select_auditorium')

    if request.method == 'POST':
        file = request.files['file']
        df = pd.read_excel(file)

        init_db(db)

        conn = sqlite3.connect(db)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM students")

        for _, row in df.iterrows():
            seat = normalize_seat(row.get('seat') or row.get('Seat'))

            cursor.execute("""
                INSERT INTO students (id, srn, name, section, seat)
                VALUES (?, ?, ?, ?, ?)
            """, (
                str(row.get('id') or row.get('PRN')),
                str(row.get('srn') or row.get('SRN')),
                row.get('name') or row.get('Name'),
                row.get('section') or row.get('Section'),
                seat
            ))

        conn.commit()
        conn.close()

        return redirect('/grid')

    return render_template('upload.html')

# ======================
# GRID
# ======================

@app.route('/grid')
def grid():
    db = get_db()
    if not db:
        return redirect('/')

    init_db(db)

    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    cursor.execute("SELECT seat, status FROM students")
    data = cursor.fetchall()

    conn.close()

    seats = {seat: status for seat, status in data}

    return render_template('index.html', seats=seats)

# ======================
# GET STUDENT
# ======================

@app.route('/get_student/<seat>')
def get_student(seat):
    db = get_db()
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    seat = normalize_seat(seat)

    cursor.execute("SELECT name, srn, status FROM students WHERE seat=?", (seat,))
    student = cursor.fetchone()

    conn.close()

    if student:
        return jsonify({
            "name": student[0],
            "srn": student[1],
            "status": student[2]
        })
    else:
        return jsonify({"error": "Not found"})

# ======================
# MARK
# ======================

@app.route('/mark/<seat>', methods=['POST'])
def mark(seat):
    db = get_db()
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    seat = normalize_seat(seat)

    cursor.execute("""
        UPDATE students
        SET status = CASE
            WHEN status='present' THEN 'absent'
            ELSE 'present'
        END
        WHERE seat=?
    """, (seat,))

    conn.commit()
    conn.close()

    return jsonify({"success": True})

# ======================
# RESET (ADMIN ONLY)
# ======================
@app.route('/reset', methods=['POST'])
def reset():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"})

    db = get_db()

    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    cursor.execute("UPDATE students SET status='OUT', remark=NULL")

    conn.commit()
    conn.close()

    return jsonify({"success": True})

# ======================
# LOGOUT
# ======================

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ======================

if __name__ == '__main__':
    app.run(debug=True)