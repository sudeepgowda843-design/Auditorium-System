from flask import Flask, render_template, request, redirect, jsonify, session, send_file
import sqlite3
import pandas as pd
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "secret123"

# =========================
# USERS
# =========================
USERS = {
    "FOMC": {
        "fomc": {"password": "fomc@2026", "role": "fomc"}
    },
    "MBA": {
        "admin": {"password": "pesu@2026", "role": "admin"},
        "student1": {"password": "mba123", "role": "student"},
        "student2": {"password": "mba456", "role": "student"}
    },
    "BCOM": {
        "admin": {"password": "bcom@2026", "role": "admin"},
        "student1": {"password": "bcom111", "role": "student"},
        "student2": {"password": "bcom222", "role": "student"}
    },
    "LAW": {
        "admin": {"password": "law@2026", "role": "admin"},
        "student1": {"password": "law111", "role": "student"},
        "student2": {"password": "law222", "role": "student"}
    },
    "BBA": {
        "admin": {"password": "bba@2026", "role": "admin"},
        "student1": {"password": "bba111", "role": "student"},
        "student2": {"password": "bba222", "role": "student"}
    },
    "PSYCHOLOGY": {
        "admin": {"password": "psy@2026", "role": "admin"},
        "student1": {"password": "psy111", "role": "student"},
        "student2": {"password": "psy222", "role": "student"}
    }
}

MENTOR_PASSWORD = "mentor@2026"
MASTER_DB = "auditorium_system.db"

AUDITORIUM_CONFIG = {
    "1A": {"default_cols": 22, "rows": list("ABCDEFGHIJKLMNOPQRSTU"), "extra_rows": {"V": 15, "W": 13}},
    "1B": {"default_cols": 22, "rows": list("ABCDEFGHIJKLMNOPQRSTU"), "extra_rows": {"V": 16, "W": 13}},
    "2A": {"default_cols": 22, "rows": list("ABCDEFGHIJKLMNOPQRSTU"), "extra_rows": {}},
    "2B": {"default_cols": 22, "rows": list("ABCDEFGHIJKLMNOPQRSTU"), "extra_rows": {}}
}


# =========================
# HELPERS
# =========================
def normalize_seat(seat):
    if not seat:
        return None
    return str(seat).replace("-", "").replace(" ", "").upper().strip()


def get_active_event_id():
    return session.get("event_id")


def init_master_db():
    conn = sqlite3.connect(MASTER_DB)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS students_master (
        PRN TEXT PRIMARY KEY,
        SRN TEXT,
        Name TEXT,
        Department TEXT,
        Section TEXT,
        Batch TEXT,
        Mentor TEXT,
        Status TEXT DEFAULT 'Active'
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_name TEXT,
        event_date TEXT,
        auditorium TEXT,
        department TEXT,
        created_by TEXT,
        created_at TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS event_seating (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER,
        PRN TEXT,
        Seat TEXT,
        status TEXT DEFAULT 'OUT',
        remark TEXT,
        mentor_action TEXT,
        FOREIGN KEY(event_id) REFERENCES events(event_id),
        UNIQUE(event_id, PRN),
        UNIQUE(event_id, Seat)
    )
    """)

    conn.commit()
    conn.close()


init_master_db()


def mentor_exists(dept, mentor_name):
    conn = sqlite3.connect(MASTER_DB)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM students_master
        WHERE UPPER(Department)=UPPER(?)
        AND Mentor=?
        AND Status='Active'
    """, (dept, mentor_name))

    count = cursor.fetchone()[0]
    conn.close()
    return count > 0


# =========================
# LOGIN
# =========================
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        dept = request.form.get("department")
        username = request.form.get("username")
        password = request.form.get("password")

        dept_users = USERS.get(dept)

        if dept_users and username in dept_users:
            user = dept_users[username]

            if user["password"] == password:
                session.clear()
                session["department"] = dept
                session["role"] = user["role"]
                session["username"] = username

                if user["role"] == "fomc":
                    return redirect('/fomc_dashboard')

                if user["role"] == "admin":
                    return redirect('/admin_dashboard')

                return redirect('/select_event')

        if password == MENTOR_PASSWORD and mentor_exists(dept, username):
            session.clear()
            session["department"] = dept
            session["role"] = "mentor"
            session["username"] = username
            session["mentor_name"] = username

            return redirect('/select_event')

        return "Invalid Credentials ❌"

    return render_template('login.html')


# =========================
# ADMIN DASHBOARD
# =========================
@app.route('/admin_dashboard')
def admin_dashboard():
    if session.get("role") != "admin":
        return redirect('/')

    dept = session.get("department")

    conn = sqlite3.connect(MASTER_DB)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM students_master WHERE UPPER(Department)=UPPER(?)", (dept,))
    total_students = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM students_master WHERE UPPER(Department)=UPPER(?) AND Status='Active'", (dept,))
    active_students = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(DISTINCT Mentor)
        FROM students_master
        WHERE UPPER(Department)=UPPER(?)
        AND Mentor IS NOT NULL
        AND Mentor != ''
    """, (dept,))
    total_mentors = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM events
        WHERE UPPER(department)=UPPER(?)
    """, (dept,))
    total_events = cursor.fetchone()[0]

    conn.close()

    return render_template(
        'admin_dashboard.html',
        total_students=total_students,
        active_students=active_students,
        total_mentors=total_mentors,
        total_departments=1,
        total_events=total_events
    )


# =========================
# MASTER UPLOAD
# =========================
@app.route('/upload_master', methods=['GET', 'POST'])
def upload_master():
    if session.get("role") != "admin":
        return redirect('/')

    if request.method == 'POST':
        file = request.files.get('file')

        if not file or file.filename == '':
            return "Please upload a valid master Excel file"

        df = pd.read_excel(file)
        df.columns = df.columns.str.strip()

        required_columns = ["PRN", "SRN", "Name", "Department", "Section", "Batch", "Mentor", "Status"]
        missing = [col for col in required_columns if col not in df.columns]

        if missing:
            return f"Missing columns in Excel: {missing}"

        conn = sqlite3.connect(MASTER_DB)
        cursor = conn.cursor()

        for _, row in df.iterrows():
            prn = str(row.get("PRN", "")).strip()
            srn = str(row.get("SRN", "")).strip()
            name = str(row.get("Name", "")).strip()
            department = str(row.get("Department", "")).strip().upper()
            section = str(row.get("Section", "")).strip()
            batch = str(row.get("Batch", "")).strip()
            mentor = str(row.get("Mentor", "")).strip()
            status = str(row.get("Status", "Active")).strip()

            if not prn:
                continue

            cursor.execute("""
                INSERT OR REPLACE INTO students_master
                (PRN, SRN, Name, Department, Section, Batch, Mentor, Status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (prn, srn, name, department, section, batch, mentor, status))

        conn.commit()
        conn.close()

        return redirect('/admin_dashboard')

    return render_template('master_upload.html')


@app.route('/download_master')
def download_master():
    if session.get("role") not in ["admin", "fomc"]:
        return redirect('/')

    conn = sqlite3.connect(MASTER_DB)
    df = pd.read_sql_query("SELECT * FROM students_master", conn)
    conn.close()

    file_path = "student_master_download.xlsx"
    df.to_excel(file_path, index=False)

    return send_file(file_path, as_attachment=True)


# =========================
# EVENT CREATION
# =========================
@app.route('/create_event', methods=['GET', 'POST'])
def create_event():
    if session.get("role") != "admin":
        return redirect('/')

    if request.method == 'POST':
        event_name = request.form.get("event_name")
        event_date = request.form.get("event_date")
        auditorium = request.form.get("auditorium")
        department = session.get("department")
        created_by = session.get("username")

        conn = sqlite3.connect(MASTER_DB)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO events
            (event_name, event_date, auditorium, department, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            event_name,
            event_date,
            auditorium,
            department,
            created_by,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        event_id = cursor.lastrowid

        conn.commit()
        conn.close()

        session["event_id"] = event_id
        session["auditorium"] = auditorium

        return redirect('/upload_event_grid')

    return render_template('create_event.html')


# =========================
# SELECT EVENT
# =========================
@app.route('/select_event', methods=['GET', 'POST'])
def select_event():
    role = session.get("role")
    dept = session.get("department")

    if role not in ["student", "mentor", "admin"]:
        return redirect('/')

    conn = sqlite3.connect(MASTER_DB)
    cursor = conn.cursor()

    if role == "admin":
        cursor.execute("""
            SELECT event_id, event_name, event_date, auditorium, department
            FROM events
            WHERE UPPER(department)=UPPER(?)
            ORDER BY event_id DESC
        """, (dept,))
    else:
        cursor.execute("""
            SELECT event_id, event_name, event_date, auditorium, department
            FROM events
            WHERE UPPER(department)=UPPER(?)
            ORDER BY event_id DESC
        """, (dept,))

    events = cursor.fetchall()
    conn.close()

    if request.method == 'POST':
        event_id = request.form.get("event_id")

        conn = sqlite3.connect(MASTER_DB)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT auditorium, department
            FROM events
            WHERE event_id=?
        """, (event_id,))

        event = cursor.fetchone()
        conn.close()

        if not event:
            return "Invalid Event"

        session["event_id"] = int(event_id)
        session["auditorium"] = event[0]
        session["department"] = event[1]

        if role == "mentor":
            return redirect('/mentor_dashboard')

        return redirect('/grid')

    return render_template('select_event.html', events=events)


# =========================
# UPLOAD EVENT GRID: PRN + Seat only
# =========================
@app.route('/upload_event_grid', methods=['GET', 'POST'])
def upload_event_grid():
    if session.get("role") != "admin":
        return redirect('/')

    event_id = get_active_event_id()
    dept = session.get("department")

    if not event_id:
        return redirect('/create_event')

    if request.method == 'POST':
        file = request.files.get('file')

        if not file or file.filename == '':
            return "Upload valid Excel"

        df = pd.read_excel(file)
        df.columns = df.columns.str.strip()

        if "Seat" not in df.columns:
            return "Excel must contain Seat column"

        if "PRN" not in df.columns and "SRN" not in df.columns:
            return "Excel must contain PRN or SRN column"

        conn = sqlite3.connect(MASTER_DB)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM event_seating WHERE event_id=?", (event_id,))

        missing_students = []

        for _, row in df.iterrows():
            prn = str(row.get("PRN", "")).strip()
            srn = str(row.get("SRN", "")).strip()
            seat = normalize_seat(row.get("Seat"))

            if not seat:
                continue

            if prn:
                cursor.execute("""
                    SELECT PRN
                    FROM students_master
                    WHERE PRN=?
                    AND UPPER(Department)=UPPER(?)
                    AND Status='Active'
                """, (prn, dept))
            else:
                cursor.execute("""
                    SELECT PRN
                    FROM students_master
                    WHERE SRN=?
                    AND UPPER(Department)=UPPER(?)
                    AND Status='Active'
                """, (srn, dept))

            student = cursor.fetchone()

            if not student:
                missing_students.append(prn or srn)
                continue

            final_prn = student[0]

            cursor.execute("""
                INSERT OR REPLACE INTO event_seating
                (event_id, PRN, Seat, status, remark, mentor_action)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                event_id,
                final_prn,
                seat,
                "OUT",
                "",
                ""
            ))

        conn.commit()
        conn.close()

        if missing_students:
            return f"Upload completed, but these students were not found in master database: {missing_students}"

        return redirect('/grid')

    return render_template('upload_event_grid.html')


# =========================
# GRID
# =========================
@app.route('/grid')
def grid():
    auditorium = session.get("auditorium")

    if not auditorium or auditorium not in AUDITORIUM_CONFIG:
        return redirect('/select_event')

    config = AUDITORIUM_CONFIG[auditorium]

    return render_template(
        'index.html',
        rows=config["rows"],
        default_cols=config["default_cols"],
        extra_rows=config["extra_rows"]
    )


# =========================
# SEATS API
# =========================
@app.route('/seats')
def get_seats():
    event_id = get_active_event_id()

    if not event_id:
        return jsonify([])

    conn = sqlite3.connect(MASTER_DB)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT es.Seat, sm.Name, es.status
        FROM event_seating es
        JOIN students_master sm ON es.PRN = sm.PRN
        WHERE es.event_id=?
    """, (event_id,))

    rows = cursor.fetchall()
    conn.close()

    return jsonify([
        {"seat": r[0], "name": r[1], "status": r[2]}
        for r in rows
    ])


# =========================
# SCAN
# =========================
@app.route('/scan', methods=['POST'])
def scan():
    data = request.get_json()
    student_id = str(data.get("student_id", "")).strip()
    event_id = get_active_event_id()

    if not event_id:
        return jsonify({"error": "No active event selected"})

    conn = sqlite3.connect(MASTER_DB)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT es.id, sm.Name, es.Seat, es.status
        FROM event_seating es
        JOIN students_master sm ON es.PRN = sm.PRN
        WHERE es.event_id=?
        AND (sm.SRN=? OR sm.PRN=?)
    """, (event_id, student_id, student_id))

    student = cursor.fetchone()

    if not student:
        conn.close()
        return jsonify({"error": "Student not found in this event"})

    seating_id, name, seat, old_status = student
    new_status = "IN" if old_status != "IN" else "OUT"

    cursor.execute("""
        UPDATE event_seating
        SET status=?
        WHERE id=?
    """, (new_status, seating_id))

    conn.commit()
    conn.close()

    return jsonify({
        "name": name,
        "seat": seat,
        "status": new_status
    })


# =========================
# STUDENT BY SEAT
# =========================
@app.route('/student/<seat>')
def get_student(seat):
    event_id = get_active_event_id()
    seat = normalize_seat(seat)

    if not event_id:
        return jsonify({"error": "No active event"})

    conn = sqlite3.connect(MASTER_DB)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT sm.Name, sm.SRN, es.status, es.remark
        FROM event_seating es
        JOIN students_master sm ON es.PRN = sm.PRN
        WHERE es.event_id=?
        AND es.Seat=?
    """, (event_id, seat))

    student = cursor.fetchone()
    conn.close()

    if student:
        return jsonify({
            "name": student[0],
            "srn": student[1],
            "status": student[2],
            "remark": student[3]
        })

    return jsonify({"error": "Not found"})


# =========================
# DISCIPLINE
# =========================
@app.route('/discipline', methods=['POST'])
def discipline():
    data = request.get_json()
    seat = normalize_seat(data.get("seat"))
    action = data.get("action")
    event_id = get_active_event_id()

    if not event_id:
        return jsonify({"error": "No active event"})

    conn = sqlite3.connect(MASTER_DB)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE event_seating
        SET remark=?
        WHERE event_id=?
        AND Seat=?
    """, (action, event_id, seat))

    conn.commit()
    conn.close()

    return jsonify({"success": True})


# =========================
# MENTOR DASHBOARD
# =========================
@app.route('/mentor_dashboard')
def mentor_dashboard():
    if session.get("role") != "mentor":
        return redirect('/grid')

    event_id = get_active_event_id()
    mentor_name = session.get("mentor_name")

    if not event_id:
        return redirect('/select_event')

    conn = sqlite3.connect(MASTER_DB)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT sm.PRN, sm.SRN, sm.Name, sm.Section, sm.Batch,
               es.Seat, es.status, es.remark, es.mentor_action
        FROM event_seating es
        JOIN students_master sm ON es.PRN = sm.PRN
        WHERE es.event_id=?
        AND sm.Mentor=?
        AND sm.Status='Active'
        ORDER BY sm.Section, sm.Name
    """, (event_id, mentor_name))

    rows = cursor.fetchall()
    conn.close()

    students = []
    for r in rows:
        students.append({
            "PRN": r[0],
            "SRN": r[1],
            "name": r[2],
            "Section": r[3],
            "Batch": r[4],
            "Seat": r[5],
            "status": r[6],
            "remark": r[7],
            "mentor_action": r[8]
        })

    total_students = len(students)
    present_students = len([s for s in students if s["status"] == "IN"])
    absent_students = total_students - present_students

    return render_template(
        'mentor_dashboard.html',
        mentor_name=mentor_name,
        students=students,
        total_students=total_students,
        present_students=present_students,
        absent_students=absent_students
    )


# =========================
# MENTOR ACTION
# =========================
@app.route('/mentor_action', methods=['POST'])
def mentor_action():
    if session.get("role") != "mentor":
        return jsonify({"error": "Unauthorized"})

    data = request.get_json()
    prn = str(data.get("prn")).strip()
    action = data.get("action")
    event_id = get_active_event_id()
    mentor_name = session.get("mentor_name")

    conn = sqlite3.connect(MASTER_DB)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM students_master
        WHERE PRN=?
        AND Mentor=?
        AND Status='Active'
    """, (prn, mentor_name))

    allowed = cursor.fetchone()[0]

    if not allowed:
        conn.close()
        return jsonify({"error": "Unauthorized student"})

    cursor.execute("""
        UPDATE event_seating
        SET mentor_action=?
        WHERE event_id=?
        AND PRN=?
    """, (action, event_id, prn))

    conn.commit()
    conn.close()

    return jsonify({"success": True})


# =========================
# FOMC DASHBOARD
# =========================
@app.route('/fomc_dashboard')
def fomc_dashboard():
    if session.get("role") != "fomc":
        return redirect('/')

    conn = sqlite3.connect(MASTER_DB)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM students_master")
    total_students = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM students_master WHERE Status='Active'")
    active_students = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT Department) FROM students_master WHERE Department IS NOT NULL AND Department != ''")
    total_departments = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT Mentor) FROM students_master WHERE Mentor IS NOT NULL AND Mentor != ''")
    total_mentors = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM events")
    total_events = cursor.fetchone()[0]

    cursor.execute("""
        SELECT sm.Department,
               COUNT(es.id) as total,
               SUM(CASE WHEN es.status='IN' THEN 1 ELSE 0 END) as present
        FROM event_seating es
        JOIN students_master sm ON es.PRN = sm.PRN
        GROUP BY sm.Department
        ORDER BY sm.Department
    """)
    dept_attendance_rows = cursor.fetchall()

    cursor.execute("""
        SELECT sm.Mentor,
               COUNT(es.id) as total,
               SUM(CASE WHEN es.mentor_action IS NOT NULL AND es.mentor_action != '' THEN 1 ELSE 0 END) as action_taken
        FROM event_seating es
        JOIN students_master sm ON es.PRN = sm.PRN
        WHERE sm.Mentor IS NOT NULL AND sm.Mentor != ''
        GROUP BY sm.Mentor
        ORDER BY action_taken DESC
    """)
    mentor_action_rows = cursor.fetchall()

    cursor.execute("""
        SELECT sm.Department, COUNT(es.remark)
        FROM event_seating es
        JOIN students_master sm ON es.PRN = sm.PRN
        WHERE es.remark IS NOT NULL AND es.remark != ''
        GROUP BY sm.Department
    """)
    discipline_rows = cursor.fetchall()

    cursor.execute("""
        SELECT sm.PRN, sm.SRN, sm.Name, sm.Department, sm.Mentor,
               COUNT(es.id) as total_events,
               SUM(CASE WHEN es.status!='IN' THEN 1 ELSE 0 END) as absent_count
        FROM event_seating es
        JOIN students_master sm ON es.PRN = sm.PRN
        GROUP BY sm.PRN
        HAVING absent_count >= 2
        ORDER BY absent_count DESC
        LIMIT 20
    """)
    risk_students = cursor.fetchall()

    conn.close()

    dept_labels = [r[0] for r in dept_attendance_rows]
    dept_percentages = [
        round((r[2] / r[1]) * 100, 2) if r[1] else 0
        for r in dept_attendance_rows
    ]

    mentor_labels = [r[0] for r in mentor_action_rows]
    mentor_action_taken = [r[2] for r in mentor_action_rows]
    mentor_pending = [r[1] - r[2] for r in mentor_action_rows]

    discipline_labels = [r[0] for r in discipline_rows]
    discipline_counts = [r[1] for r in discipline_rows]

    return render_template(
        'fomc_dashboard.html',
        total_students=total_students,
        active_students=active_students,
        total_departments=total_departments,
        total_mentors=total_mentors,
        total_events=total_events,
        dept_labels=dept_labels,
        dept_percentages=dept_percentages,
        mentor_labels=mentor_labels,
        mentor_action_taken=mentor_action_taken,
        mentor_pending=mentor_pending,
        discipline_labels=discipline_labels,
        discipline_counts=discipline_counts,
        risk_students=risk_students
    )


# =========================
# DOWNLOAD EVENT REPORT
# =========================
@app.route('/download')
def download():
    event_id = get_active_event_id()

    if not event_id:
        return redirect('/select_event')

    conn = sqlite3.connect(MASTER_DB)

    df = pd.read_sql_query("""
        SELECT e.event_name, e.event_date, e.auditorium,
               sm.PRN, sm.SRN, sm.Name, sm.Department, sm.Section, sm.Batch, sm.Mentor,
               es.Seat, es.status, es.remark, es.mentor_action
        FROM event_seating es
        JOIN students_master sm ON es.PRN = sm.PRN
        JOIN events e ON es.event_id = e.event_id
        WHERE es.event_id=?
    """, conn, params=(event_id,))

    conn.close()

    file_path = "event_attendance_report.xlsx"
    df.to_excel(file_path, index=False)

    return send_file(file_path, as_attachment=True)


@app.route('/reset', methods=['POST'])
def reset():
    if session.get("role") != "admin":
        return jsonify({"error": "Unauthorized"})

    event_id = get_active_event_id()

    if not event_id:
        return jsonify({"error": "No active event"})

    conn = sqlite3.connect(MASTER_DB)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE event_seating
        SET status='OUT', remark=NULL, mentor_action=NULL
        WHERE event_id=?
    """, (event_id,))

    conn.commit()
    conn.close()

    return jsonify({"success": True})


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


if __name__ == '__main__':
    app.run(debug=True)