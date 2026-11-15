
from flask import Flask, render_template, request, redirect, url_for, flash
from database import get_connection
import mysql.connector
import re
import os
from dotenv import load_dotenv
from datetime import datetime
from flask_wtf.csrf import CSRFProtect

# Load environment variables
load_dotenv(override=True)

app = Flask(__name__)

# Secure Flask secret key
app.secret_key = os.getenv("FLASK_SECRET_KEY")

if not app.secret_key:
    raise RuntimeError("FLASK_SECRET_KEY is missing from .env")

csrf = CSRFProtect(app)
# ----------------------------------------
# SERVER-SIDE FORM VALIDATION
# ----------------------------------------

def validate_student_form(form):

    roll_no = form.get("roll_no", "").strip()
    first_name = form.get("first_name", "").strip()
    last_name = form.get("last_name", "").strip() or None
    email = form.get("email", "").strip() or None
    gender = form.get("gender", "").strip() or None
    course = form.get("course", "").strip()
    semester = form.get("semester", "").strip()
    phone = form.get("phone", "").strip() or None
    admission_date = form.get("admission_date", "").strip()

    # Required fields
    if not roll_no:
        return None, "Roll number is required."

    if not first_name:
        return None, "First name is required."

    if not course:
        return None, "Course is required."

    if not semester:
        return None, "Semester is required."

    if not admission_date:
        return None, "Admission date is required."

    # Database field length validation
    if len(roll_no) > 20:
        return None, "Roll number cannot exceed 20 characters."

    if len(first_name) > 50:
        return None, "First name cannot exceed 50 characters."

    if last_name and len(last_name) > 50:
        return None, "Last name cannot exceed 50 characters."

    if email and len(email) > 100:
        return None, "Email cannot exceed 100 characters."

    if len(course) > 50:
        return None, "Course cannot exceed 50 characters."

    if phone and len(phone) > 15:
        return None, "Phone number cannot exceed 15 characters."

    # Semester validation
    try:
        semester = int(semester)

        if semester < 1 or semester > 8:
            return None, "Semester must be between 1 and 8."

    except ValueError:
        return None, "Semester must be a valid number."

    # Email validation
    if email:
        email_pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

        if not re.fullmatch(email_pattern, email):
            return None, "Please enter a valid email address."

    # Phone validation
    if phone:
        phone_digits = re.sub(r"\D", "", phone)

        if not re.fullmatch(r"[0-9+\-\s()]+", phone):
            return None, "Phone number contains invalid characters."

        if not 7 <= len(phone_digits) <= 15:
            return None, "Phone number must contain 7 to 15 digits."

    # Gender validation
    if gender and gender not in ["Male", "Female", "Other"]:
        return None, "Please select a valid gender."

    # Admission date validation
    try:
        datetime.strptime(admission_date, "%Y-%m-%d")
    except ValueError:
        return None, "Please enter a valid admission date."

    student_data = (
        roll_no,
        first_name,
        last_name,
        email,
        gender,
        course,
        semester,
        phone,
        admission_date
    )

    return student_data, None


# ----------------------------------------
# HOME / DYNAMIC DASHBOARD
# ----------------------------------------

@app.route("/")
def home():

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("SELECT COUNT(*) AS total_students FROM students")
        total_students = cursor.fetchone()["total_students"]

        cursor.execute("""
            SELECT COUNT(DISTINCT course) AS total_courses
            FROM students
        """)
        total_courses = cursor.fetchone()["total_courses"]

        cursor.execute("""
            SELECT COUNT(DISTINCT semester) AS active_semesters
            FROM students
        """)
        active_semesters = cursor.fetchone()["active_semesters"]

        cursor.execute("""
            SELECT student_id, roll_no, first_name, last_name,
                   course, semester
            FROM students
            ORDER BY student_id DESC
            LIMIT 5
        """)
        recent_students = cursor.fetchall()

    finally:
        cursor.close()
        connection.close()

    return render_template(
        "index.html",
        total_students=total_students,
        total_courses=total_courses,
        active_semesters=active_semesters,
        recent_students=recent_students
    )


# ----------------------------------------
# DISPLAY, SEARCH AND FILTER STUDENTS
# ----------------------------------------

@app.route("/students")
def students():

    search = request.args.get("q", "").strip()
    course_filter = request.args.get("course", "").strip()
    semester_filter = request.args.get("semester", "").strip()

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT DISTINCT course
            FROM students
            WHERE course IS NOT NULL AND course != ''
            ORDER BY course
        """)
        courses = [row["course"] for row in cursor.fetchall()]

        cursor.execute("""
            SELECT DISTINCT semester
            FROM students
            WHERE semester IS NOT NULL
            ORDER BY semester
        """)
        semesters = [row["semester"] for row in cursor.fetchall()]

        query = "SELECT * FROM students WHERE 1=1"
        values = []

        if search:
            query += """
                AND (
                    first_name LIKE %s
                    OR last_name LIKE %s
                    OR roll_no LIKE %s
                )
            """
            search_value = f"%{search}%"
            values.extend([search_value] * 3)

        if course_filter:
            query += " AND course = %s"
            values.append(course_filter)

        if semester_filter:
            query += " AND semester = %s"
            values.append(semester_filter)

        query += " ORDER BY student_id DESC"

        cursor.execute(query, tuple(values))
        students = cursor.fetchall()

    finally:
        cursor.close()
        connection.close()

    return render_template(
        "students.html",
        students=students,
        courses=courses,
        semesters=semesters,
        search=search,
        course_filter=course_filter,
        semester_filter=semester_filter
    )


# ----------------------------------------
# ADD A NEW STUDENT
# ----------------------------------------

@app.route("/add-student", methods=["GET", "POST"])
def add_student():

    if request.method == "POST":

        student_data, error = validate_student_form(request.form)

        if error:
            flash(error, "error")
            return redirect(url_for("add_student"))

        connection = None
        cursor = None

        try:
            connection = get_connection()
            cursor = connection.cursor()

            query = """
                INSERT INTO students
                (roll_no, first_name, last_name, email,
                 gender, course, semester, phone, admission_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """

            cursor.execute(query, student_data)
            connection.commit()

            flash("Student added successfully!", "success")
            return redirect(url_for("students"))

        except mysql.connector.IntegrityError:
            flash(
                "Roll number or email already exists. Please check the details.",
                "error"
            )

        except mysql.connector.Error:
            flash("Unable to add student. Please try again.", "error")

        finally:
            if cursor:
                cursor.close()

            if connection and connection.is_connected():
                connection.close()

    return render_template("add_student.html")


# ----------------------------------------
# EDIT AN EXISTING STUDENT
# ----------------------------------------

@app.route("/edit-student/<int:student_id>", methods=["GET", "POST"])
def edit_student(student_id):

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        if request.method == "POST":

            student_data, error = validate_student_form(request.form)

            if error:
                flash(error, "error")
                return redirect(
                    url_for("edit_student", student_id=student_id)
                )

            query = """
                UPDATE students
                SET roll_no = %s,
                    first_name = %s,
                    last_name = %s,
                    email = %s,
                    gender = %s,
                    course = %s,
                    semester = %s,
                    phone = %s,
                    admission_date = %s
                WHERE student_id = %s
            """

            values = student_data + (student_id,)

            cursor.execute(query, values)
            connection.commit()

            flash("Student information updated successfully!", "success")
            return redirect(url_for("students"))

        cursor.execute(
            "SELECT * FROM students WHERE student_id = %s",
            (student_id,)
        )

        student = cursor.fetchone()

    except mysql.connector.IntegrityError:
        if connection and connection.is_connected():
            connection.rollback()

        flash(
            "Roll number or email already belongs to another student.",
            "error"
        )
        return redirect(url_for("edit_student", student_id=student_id))

    except mysql.connector.Error:
        if connection and connection.is_connected():
            connection.rollback()

        flash("Unable to update student. Please try again.", "error")
        return redirect(url_for("students"))

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()

    if student is None:
        return "Student not found", 404

    return render_template("edit_student.html", student=student)


# ----------------------------------------
# DELETE AN EXISTING STUDENT
# ----------------------------------------

@app.route("/delete-student/<int:student_id>", methods=["POST"])
def delete_student(student_id):

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute(
            "DELETE FROM students WHERE student_id = %s",
            (student_id,)
        )

        if cursor.rowcount == 0:
            flash("Student not found.", "error")
        else:
            connection.commit()
            flash("Student deleted successfully!", "success")

    except mysql.connector.Error:
        if connection and connection.is_connected():
            connection.rollback()

        flash("Unable to delete student. Please try again.", "error")

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()

    return redirect(url_for("students"))


# ----------------------------------------
# RUN FLASK APPLICATION
# ----------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
