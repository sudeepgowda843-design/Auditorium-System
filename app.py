from flask import Flask, render_template, request, redirect, jsonify, session, send_file
import psycopg2
from psycopg2.extras import execute_values
import pandas as pd
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "secret123"

DATABASE_URL = os.environ.get("DATABASE_URL")

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


# =========================
# DATABASE HELPERS
# =========================

def get_conn():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set. Add it in Render Environment Variables or export it locally."
        )
    return psycopg2.connect(DATABASE_URL)


def normalize_seat(seat):
    if not seat:
        return None
    return str(seat).replace("-", "").replace(" ", "").upper().strip()


def get_active_event_id():
    return session.get("event_id")


def init_db():
    conn = get_conn()
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
        event_id SERIAL PRIMARY KEY,
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
        id SERIAL PRIMARY KEY,
        event_id INTEGER REFERENCES events(event_id) ON DELETE CASCADE,
        PRN TEXT REFERENCES students_master(PRN),
        Seat TEXT,
        status TEXT DEFAULT 'OUT',
        remark TEXT,
        mentor_action TEXT,
        UNIQUE(event_id, PRN),
        UNIQUE(event_id, Seat)
    )
    """)

    conn.commit()
    cursor.close()
    conn.close()


init_db()


def mentor_exists(dept, mentor_name):
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM students_master
        WHERE UPPER(Department)=UPPER(%s)
        AND Mentor=%s
        AND Status='Active'
    """, (dept, mentor_name))

    count = cursor.fetchone()[0]

    cursor.close()
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

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM students_master
        WHERE UPPER(Department)=UPPER(%s)
    """, (dept,))
    total_students = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM students_master
        WHERE UPPER(Department)=UPPER(%s)
        AND Status='Active'
    """, (dept,))
    active_students = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(DISTINCT Mentor)
        FROM students_master
        WHERE UPPER(Department)=UPPER(%s)
        AND Mentor IS NOT NULL
        AND Mentor != ''
    """, (dept,))
    total_mentors = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM events
        WHERE UPPER(department)=UPPER(%s)
    """, (dept,))
    total_events = cursor.fetchone()[0]

    cursor.close()
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

        required_columns = [
            "PRN", "SRN", "Name", "Department",
            "Section", "Batch", "Mentor", "Status"
        ]

        missing = [col for col in required_columns if col not in df.columns]

        if missing:
            return f"Missing columns in Excel: {missing}"

        values = []

        for _, row in df.iterrows():
            prn = str(row.get("PRN", "")).strip()

            if not prn or prn.lower() == "nan":
                continue

            values.append((
                prn,
                str(row.get("SRN", "")).strip(),
                str(row.get("Name", "")).strip(),
                str(row.get("Department", "")).strip().upper(),
                str(row.get("Section", "")).strip(),
                str(row.get("Batch", "")).strip(),
                str(row.get("Mentor", "")).strip(),
                str(row.get("Status", "Active")).strip()
            ))

        if not values:
            return "No valid student records found in Excel"

        conn = get_conn()
        cursor = conn.cursor()

        execute_values(cursor, """
            INSERT INTO students_master
            (PRN, SRN, Name, Department, Section, Batch, Mentor, Status)
            VALUES %s
            ON CONFLICT (PRN)
            DO UPDATE SET
                SRN=EXCLUDED.SRN,
                Name=EXCLUDED.Name,
                Department=EXCLUDED.Department,
                Section=EXCLUDED.Section,
                Batch=EXCLUDED.Batch,
                Mentor=EXCLUDED.Mentor,
                Status=EXCLUDED.Status
        """, values)

        conn.commit()
        cursor.close()
        conn.close()

        return redirect('/admin_dashboard')

    return render_template('master_upload.html')



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

        conn = get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO events
            (event_name, event_date, auditorium, department, created_by, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING event_id
        """, (
            event_name,
            event_date,
            auditorium,
            department,
            created_by,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        event_id = cursor.fetchone()[0]

        conn.commit()
        cursor.close()
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

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT event_id, event_name, event_date, auditorium, department
        FROM events
        WHERE UPPER(department)=UPPER(%s)
        ORDER BY event_id DESC
    """, (dept,))

    events = cursor.fetchall()

    if request.method == 'POST':
        event_id = request.form.get("event_id")

        cursor.execute("""
            SELECT auditorium, department
            FROM events
            WHERE event_id=%s
        """, (event_id,))

        event = cursor.fetchone()

        cursor.close()
        conn.close()

        if not event:
            return "Invalid Event"

        session["event_id"] = int(event_id)
        session["auditorium"] = event[0]
        session["department"] = event[1]

        if role == "mentor":
            return redirect('/mentor_dashboard')

        return redirect('/grid')

    cursor.close()
    conn.close()

    return render_template('select_event.html', events=events)


# =========================
# UPLOAD EVENT GRID
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

        conn = get_conn()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM event_seating WHERE event_id=%s", (event_id,))

        seating_values = []
        missing_students = []

        for _, row in df.iterrows():
            prn = str(row.get("PRN", "")).strip()
            srn = str(row.get("SRN", "")).strip()
            seat = normalize_seat(row.get("Seat"))

            if not seat:
                continue

            if prn and prn.lower() != "nan":
                cursor.execute("""
                    SELECT PRN
                    FROM students_master
                    WHERE PRN=%s
                    AND UPPER(Department)=UPPER(%s)
                    AND Status='Active'
                """, (prn, dept))
            else:
                cursor.execute("""
                    SELECT PRN
                    FROM students_master
                    WHERE SRN=%s
                    AND UPPER(Department)=UPPER(%s)
                    AND Status='Active'
                """, (srn, dept))

            student = cursor.fetchone()

            if not student:
                missing_students.append(prn or srn)
                continue

            seating_values.append((
                event_id,
                student[0],
                seat,
                "OUT",
                "",
                ""
            ))

        if seating_values:
            execute_values(cursor, """
                INSERT INTO event_seating
                (event_id, PRN, Seat, status, remark, mentor_action)
                VALUES %s
                ON CONFLICT (event_id, PRN)
                DO UPDATE SET
                    Seat=EXCLUDED.Seat,
                    status=EXCLUDED.status,
                    remark=EXCLUDED.remark,
                    mentor_action=EXCLUDED.mentor_action
            """, seating_values)

        conn.commit()
        cursor.close()
        conn.close()

        if missing_students:
            return f"Upload completed, but these students were not found in master database: {missing_students[:50]}"

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

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT es.Seat, sm.Name, es.status
        FROM event_seating es
        JOIN students_master sm ON es.PRN = sm.PRN
        WHERE es.event_id=%s
    """, (event_id,))

    rows = cursor.fetchall()

    cursor.close()
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

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT es.id, sm.Name, es.Seat, es.status
        FROM event_seating es
        JOIN students_master sm ON es.PRN = sm.PRN
        WHERE es.event_id=%s
        AND (sm.SRN=%s OR sm.PRN=%s)
    """, (event_id, student_id, student_id))

    student = cursor.fetchone()

    if not student:
        cursor.close()
        conn.close()
        return jsonify({"error": "Student not found in this event"})

    seating_id, name, seat, old_status = student
    new_status = "IN" if old_status != "IN" else "OUT"

    cursor.execute("""
        UPDATE event_seating
        SET status=%s
        WHERE id=%s
    """, (new_status, seating_id))

    conn.commit()
    cursor.close()
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

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT sm.Name, sm.SRN, es.status, es.remark
        FROM event_seating es
        JOIN students_master sm ON es.PRN = sm.PRN
        WHERE es.event_id=%s
        AND es.Seat=%s
    """, (event_id, seat))

    student = cursor.fetchone()

    cursor.close()
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

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE event_seating
        SET remark=%s
        WHERE event_id=%s
        AND Seat=%s
    """, (action, event_id, seat))

    conn.commit()
    cursor.close()
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

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT sm.PRN, sm.SRN, sm.Name, sm.Section, sm.Batch,
               es.Seat, es.status, es.remark, es.mentor_action
        FROM event_seating es
        JOIN students_master sm ON es.PRN = sm.PRN
        WHERE es.event_id=%s
        AND sm.Mentor=%s
        AND sm.Status='Active'
        ORDER BY sm.Section, sm.Name
    """, (event_id, mentor_name))

    rows = cursor.fetchall()

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

    action_taken = len([s for s in students if s["mentor_action"]])
    action_pending = total_students - action_taken

    discipline_cases = len([s for s in students if s["remark"]])
    attendance_percentage = round((present_students / total_students) * 100, 2) if total_students else 0

    cursor.execute("""
        SELECT es.remark, COUNT(*)
        FROM event_seating es
        JOIN students_master sm ON es.PRN = sm.PRN
        WHERE es.event_id=%s
        AND sm.Mentor=%s
        AND es.remark IS NOT NULL
        AND es.remark != ''
        GROUP BY es.remark
    """, (event_id, mentor_name))
    discipline_rows = cursor.fetchall()

    cursor.execute("""
        SELECT sm.PRN,
               sm.Name,
               COUNT(es.id) AS total_events,
               SUM(CASE WHEN es.status='IN' THEN 1 ELSE 0 END) AS attended_events
        FROM event_seating es
        JOIN students_master sm ON es.PRN = sm.PRN
        WHERE sm.Mentor=%s
        AND sm.Status='Active'
        GROUP BY sm.PRN, sm.Name
        ORDER BY sm.Name
    """, (mentor_name,))
    student_attendance_rows = cursor.fetchall()

    cursor.close()
    conn.close()

    discipline_labels = [r[0] for r in discipline_rows]
    discipline_counts = [r[1] for r in discipline_rows]

    student_names = [r[1] for r in student_attendance_rows]
    student_attendance_percentages = [
        round((r[3] / r[2]) * 100, 2) if r[2] else 0
        for r in student_attendance_rows
    ]

    return render_template(
        'mentor_dashboard.html',
        mentor_name=mentor_name,
        students=students,
        total_students=total_students,
        present_students=present_students,
        absent_students=absent_students,
        attendance_percentage=attendance_percentage,
        action_taken=action_taken,
        action_pending=action_pending,
        discipline_cases=discipline_cases,
        discipline_labels=discipline_labels,
        discipline_counts=discipline_counts,
        student_names=student_names,
        student_attendance_percentages=student_attendance_percentages
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

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM students_master
        WHERE PRN=%s
        AND Mentor=%s
        AND Status='Active'
    """, (prn, mentor_name))

    allowed = cursor.fetchone()[0]

    if not allowed:
        cursor.close()
        conn.close()
        return jsonify({"error": "Unauthorized student"})

    cursor.execute("""
        UPDATE event_seating
        SET mentor_action=%s
        WHERE event_id=%s
        AND PRN=%s
    """, (action, event_id, prn))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"success": True})


# =========================
# FOMC DASHBOARD
# =========================

@app.route('/fomc_dashboard')
def fomc_dashboard():
    if session.get("role") != "fomc":
        return redirect('/')

    department_filter = request.args.get("department", "ALL")
    event_filter = request.args.get("event_id", "ALL")
    mentor_filter = request.args.get("mentor", "ALL")

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT Department
        FROM students_master
        WHERE Department IS NOT NULL AND Department != ''
        ORDER BY Department
    """)
    departments = [row[0] for row in cursor.fetchall()]

    cursor.execute("""
        SELECT event_id, event_name, event_date, auditorium, department
        FROM events
        ORDER BY event_id DESC
    """)
    events = cursor.fetchall()

    cursor.execute("""
        SELECT DISTINCT Mentor
        FROM students_master
        WHERE Mentor IS NOT NULL AND Mentor != ''
        ORDER BY Mentor
    """)
    mentors = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT COUNT(*) FROM students_master")
    total_students = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM students_master WHERE Status='Active'")
    active_students = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(DISTINCT Department)
        FROM students_master
        WHERE Department IS NOT NULL AND Department != ''
    """)
    total_departments = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(DISTINCT Mentor)
        FROM students_master
        WHERE Mentor IS NOT NULL AND Mentor != ''
    """)
    total_mentors = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM events")
    total_events = cursor.fetchone()[0]

    conditions = []
    params = []

    if department_filter != "ALL":
        conditions.append("UPPER(sm.Department)=UPPER(%s)")
        params.append(department_filter)

    if event_filter != "ALL":
        conditions.append("e.event_id=%s")
        params.append(event_filter)

    if mentor_filter != "ALL":
        conditions.append("sm.Mentor=%s")
        params.append(mentor_filter)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    discipline_where = where_clause
    discipline_params = list(params)

    if discipline_where:
        discipline_where += " AND es.remark IS NOT NULL AND es.remark != ''"
    else:
        discipline_where = "WHERE es.remark IS NOT NULL AND es.remark != ''"

    cursor.execute(f"""
        SELECT sm.Department,
               COUNT(es.id) AS total_assigned,
               SUM(CASE WHEN es.status='IN' THEN 1 ELSE 0 END) AS present_count
        FROM event_seating es
        JOIN students_master sm ON es.PRN = sm.PRN
        JOIN events e ON es.event_id = e.event_id
        {where_clause}
        GROUP BY sm.Department
        ORDER BY sm.Department
    """, params)
    dept_attendance_rows = cursor.fetchall()

    cursor.execute(f"""
        SELECT e.event_name,
               e.event_date,
               COUNT(es.id) AS total_assigned,
               SUM(CASE WHEN es.status='IN' THEN 1 ELSE 0 END) AS present_count
        FROM event_seating es
        JOIN students_master sm ON es.PRN = sm.PRN
        JOIN events e ON es.event_id = e.event_id
        {where_clause}
        GROUP BY e.event_id, e.event_name, e.event_date
        ORDER BY e.event_date DESC
    """, params)
    event_attendance_rows = cursor.fetchall()

    cursor.execute(f"""
        SELECT sm.Mentor,
               COUNT(es.id) AS total_cases,
               SUM(CASE WHEN es.mentor_action IS NOT NULL AND es.mentor_action != '' THEN 1 ELSE 0 END) AS action_taken
        FROM event_seating es
        JOIN students_master sm ON es.PRN = sm.PRN
        JOIN events e ON es.event_id = e.event_id
        {where_clause}
        GROUP BY sm.Mentor
        HAVING sm.Mentor IS NOT NULL AND sm.Mentor != ''
        ORDER BY action_taken DESC
    """, params)
    mentor_action_rows = cursor.fetchall()

    cursor.execute(f"""
        SELECT sm.Department,
               COUNT(es.remark) AS discipline_count
        FROM event_seating es
        JOIN students_master sm ON es.PRN = sm.PRN
        JOIN events e ON es.event_id = e.event_id
        {discipline_where}
        GROUP BY sm.Department
        ORDER BY discipline_count DESC
    """, discipline_params)
    discipline_rows = cursor.fetchall()

    cursor.execute(f"""
        SELECT sm.PRN,
               sm.SRN,
               sm.Name,
               sm.Department,
               sm.Section,
               sm.Batch,
               sm.Mentor,
               COUNT(es.id) AS total_events,
               SUM(CASE WHEN es.status='IN' THEN 1 ELSE 0 END) AS attended_events,
               SUM(CASE WHEN es.status!='IN' THEN 1 ELSE 0 END) AS missed_events,
               SUM(CASE WHEN es.remark IS NOT NULL AND es.remark != '' THEN 1 ELSE 0 END) AS discipline_count,
               SUM(CASE WHEN es.mentor_action IS NOT NULL AND es.mentor_action != '' THEN 1 ELSE 0 END) AS action_taken_count
        FROM event_seating es
        JOIN students_master sm ON es.PRN = sm.PRN
        JOIN events e ON es.event_id = e.event_id
        {where_clause}
        GROUP BY sm.PRN, sm.SRN, sm.Name, sm.Department, sm.Section, sm.Batch, sm.Mentor
        ORDER BY missed_events DESC, sm.Name
    """, params)
    student_rows = cursor.fetchall()

    cursor.close()
    conn.close()

    dept_labels = [row[0] for row in dept_attendance_rows]
    dept_percentages = [
        round((row[2] / row[1]) * 100, 2) if row[1] else 0
        for row in dept_attendance_rows
    ]

    event_labels = [f"{row[0]} ({row[1]})" for row in event_attendance_rows]
    event_percentages = [
        round((row[3] / row[2]) * 100, 2) if row[2] else 0
        for row in event_attendance_rows
    ]

    mentor_labels = [row[0] for row in mentor_action_rows]
    mentor_action_taken = [row[2] for row in mentor_action_rows]
    mentor_pending = [row[1] - row[2] for row in mentor_action_rows]

    discipline_labels = [row[0] for row in discipline_rows]
    discipline_counts = [row[1] for row in discipline_rows]

    student_stats = []
    for row in student_rows:
        total = row[7]
        attended = row[8]
        missed = row[9]
        attendance_percentage = round((attended / total) * 100, 2) if total else 0

        student_stats.append({
            "PRN": row[0],
            "SRN": row[1],
            "Name": row[2],
            "Department": row[3],
            "Section": row[4],
            "Batch": row[5],
            "Mentor": row[6],
            "TotalEvents": total,
            "Attended": attended,
            "Missed": missed,
            "AttendancePercentage": attendance_percentage,
            "DisciplineCount": row[10],
            "ActionTakenCount": row[11]
        })

    return render_template(
        'fomc_dashboard.html',
        total_students=total_students,
        active_students=active_students,
        total_departments=total_departments,
        total_mentors=total_mentors,
        total_events=total_events,
        departments=departments,
        events=events,
        mentors=mentors,
        selected_department=department_filter,
        selected_event=event_filter,
        selected_mentor=mentor_filter,
        dept_labels=dept_labels,
        dept_percentages=dept_percentages,
        event_labels=event_labels,
        event_percentages=event_percentages,
        mentor_labels=mentor_labels,
        mentor_action_taken=mentor_action_taken,
        mentor_pending=mentor_pending,
        discipline_labels=discipline_labels,
        discipline_counts=discipline_counts,
        student_stats=student_stats
    )


# =========================
# DOWNLOAD EVENT REPORT
# =========================

@app.route('/download')
def download():
    event_id = get_active_event_id()

    if not event_id:
        return redirect('/select_event')

    conn = get_conn()

    df = pd.read_sql_query("""
        SELECT e.event_name, e.event_date, e.auditorium,
               sm.PRN, sm.SRN, sm.Name, sm.Department, sm.Section, sm.Batch, sm.Mentor,
               es.Seat, es.status, es.remark, es.mentor_action
        FROM event_seating es
        JOIN students_master sm ON es.PRN = sm.PRN
        JOIN events e ON es.event_id = e.event_id
        WHERE es.event_id=%s
    """, conn, params=(event_id,))

    conn.close()

    file_path = "event_attendance_report.xlsx"
    df.to_excel(file_path, index=False)

    return send_file(file_path, as_attachment=True)


# =========================
# RESET EVENT
# =========================

@app.route('/reset', methods=['POST'])
def reset():
    if session.get("role") != "admin":
        return jsonify({"error": "Unauthorized"})

    event_id = get_active_event_id()

    if not event_id:
        return jsonify({"error": "No active event"})

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE event_seating
        SET status='OUT', remark=NULL, mentor_action=NULL
        WHERE event_id=%s
    """, (event_id,))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"success": True})


# =========================
# LOGOUT
# =========================

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


# =========================
# RUN
# =========================

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=True)