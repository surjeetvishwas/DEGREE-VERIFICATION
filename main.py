import os
from flask import (
    Flask, render_template, request,
    redirect, url_for, flash, session
)
from flask_sqlalchemy import SQLAlchemy

# ─── CONFIG ───────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = "replace_this_with_something_random"

# Ensure the “static/images” folder exists for storing the logo
os.makedirs(os.path.join(app.root_path, "static", "images"), exist_ok=True)

# Ensure a “data” directory exists for our SQLite file
os.makedirs(os.path.join(app.root_path, "data"), exist_ok=True)

# SQLite database path
DB_PATH = os.path.join(app.root_path, "data", "students.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# ─── MODELS ───────────────────────────────────────────────────────────────────
class Subject(db.Model):
    __tablename__ = "subjects"
    id            = db.Column(db.Integer, primary_key=True)
    student_id    = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    semester      = db.Column(db.Integer, nullable=False)
    code          = db.Column(db.String(20),  nullable=False)
    name          = db.Column(db.String(200), nullable=False)
    max_exam      = db.Column(db.Integer, nullable=False)
    max_sess      = db.Column(db.Integer, nullable=False)
    max_total     = db.Column(db.Integer, nullable=False)
    marks_exam    = db.Column(db.Integer, nullable=False)
    marks_sess    = db.Column(db.Integer, nullable=False)
    marks_total   = db.Column(db.Integer, nullable=False)


class Student(db.Model):
    __tablename__ = "students"
    id             = db.Column(db.Integer, primary_key=True)

    # Basic personal details:
    name           = db.Column(db.String(200), nullable=False)
    father_name    = db.Column(db.String(200), nullable=False)
    mother_name    = db.Column(db.String(200), nullable=False)

    faculty        = db.Column(db.String(200), nullable=False)  # e.g. “Law College Dehradun”
    roll_no        = db.Column(db.String(50),  unique=True, nullable=False)
    enrollment_no  = db.Column(db.String(50),  unique=True, nullable=False)

    course_year    = db.Column(db.String(200), nullable=False)  # e.g. “LL.B.(Hons.) ‐II SEMESTER”

    # Cumulative fields at bottom:
    total_credits_registered = db.Column(db.Integer, default=0)
    total_credits_earned     = db.Column(db.Integer, default=0)
    sgpa                    = db.Column(db.Float,   default=0.0)  # e.g. 8.0
    cgpa                    = db.Column(db.Float,   default=0.0)  # e.g. 6.6
    result_overall          = db.Column(db.String(20), nullable=False)  # e.g. “Pass”

    subjects      = db.relationship(
        "Subject",
        cascade="all, delete-orphan",
        backref="student",
        lazy=True
    )


# Create tables if not present
with app.app_context():
    db.create_all()


# ─── UTILITY DECORATOR ───────────────────────────────────────────────────────
def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


# ─── PUBLIC ROUTES ───────────────────────────────────────────────────────────
@app.route("/")
def home():
    """
    Public ‘Degree Verification’ page (home.html):
    - A single “Roll Number” input + “Get Result” button
    """
    return render_template("home.html")


@app.route("/result", methods=["POST"])
def result():
    """
    Handles the form from home.html. Looks up the student by roll_no.
    If found → render result.html with all fields. Otherwise flash + redirect.
    """
    roll_no = request.form.get("roll_no", "").strip()
    if not roll_no:
        flash("Please enter a valid Roll Number.", "error")
        return redirect(url_for("home"))

    student = Student.query.filter_by(roll_no=roll_no).first()
    if not student:
        flash("No record found for that Roll Number.", "error")
        return redirect(url_for("home"))

    # Calculate the “Total Marks Obtained” and “Total Max Marks” columns in Python:
    total_max = sum(sub.max_total for sub in student.subjects)
    total_obt = sum(sub.marks_total for sub in student.subjects)

    return render_template(
        "result.html",
        student=student,
        total_max=total_max,
        total_obt=total_obt
    )


# ─── AUTH ROUTES ─────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    """
    A simple login for admin. Default credentials:
      username: superadmin
      password: India@123
    """
    if request.method == "POST":
        if (
            request.form.get("username") == "superadmin"
            and request.form.get("password") == "India@123"
        ):
            session["admin_logged_in"] = True
            return redirect(url_for("admin"))
        flash("Invalid credentials", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ─── ADMIN PANEL ─────────────────────────────────────────────────────────────
@app.route("/admin")
@login_required
def admin():
    """
    Admin dashboard: shows a table of all students by descending ID,
    with “Edit” and “Delete” links. Also, an “Add New Student” button.
    """
    students = Student.query.order_by(Student.id.desc()).all()
    return render_template("admin.html", students=students)


@app.route("/admin/add", methods=["GET", "POST"])
@login_required
def admin_add():
    """
    Add a new Student + his Subjects. On GET → show a blank form (admin_edit.html).
    On POST → Validate + insert Student and all associated Subject rows.
    """
    if request.method == "POST":
        # 1) Create the Student record
        s = Student(
            name           = request.form["name"].strip(),
            father_name    = request.form["father_name"].strip(),
            mother_name    = request.form["mother_name"].strip(),
            faculty        = request.form["faculty"].strip(),
            roll_no        = request.form["roll_no"].strip(),
            enrollment_no  = request.form["enrollment_no"].strip(),
            course_year    = request.form["course_year"].strip(),
            result_overall = request.form["result_overall"].strip()
        )
        db.session.add(s)
        db.session.flush()  # To get s.id for subjects

        # 2) Add all Subject rows:
        #    We expect parallel lists of form data:
        codes       = request.form.getlist("subj_code[]")
        names       = request.form.getlist("subj_name[]")
        semesters   = request.form.getlist("subj_semester[]")
        max_exam    = request.form.getlist("subj_max_exam[]")
        max_sess    = request.form.getlist("subj_max_sess[]")
        max_total   = request.form.getlist("subj_max_total[]")
        marks_exam  = request.form.getlist("subj_marks_exam[]")
        marks_sess  = request.form.getlist("subj_marks_sess[]")
        marks_total = request.form.getlist("subj_marks_total[]")

        for i in range(len(codes)):
            subj = Subject(
                student_id    = s.id,
                semester      = int(semesters[i]),
                code          = codes[i],
                name          = names[i],
                max_exam      = int(max_exam[i]),
                max_sess      = int(max_sess[i]),
                max_total     = int(max_total[i]),
                marks_exam    = int(marks_exam[i]),
                marks_sess    = int(marks_sess[i]),
                marks_total   = int(marks_total[i])
            )
            db.session.add(subj)
        db.session.commit()
        flash("Student and subjects added successfully.", "success")
        return redirect(url_for("admin"))

    # GET → show blank “add/edit” form
    return render_template("admin_edit.html", student=None)


@app.route("/admin/edit/<int:student_id>", methods=["GET", "POST"])
@login_required
def admin_edit(student_id):
    """
    Edit an existing student. On GET → load the form pre‐filled. On POST → save changes.
    """
    student = Student.query.get_or_404(student_id)

    if request.method == "POST":
        # 1) Update Student fields
        student.name            = request.form["name"].strip()
        student.father_name     = request.form["father_name"].strip()
        student.mother_name     = request.form["mother_name"].strip()
        student.faculty         = request.form["faculty"].strip()
        student.roll_no         = request.form["roll_no"].strip()
        student.enrollment_no   = request.form["enrollment_no"].strip()
        student.course_year     = request.form["course_year"].strip()
        student.result_overall  = request.form["result_overall"].strip()

        # 2) Delete old subjects and re‐insert new ones
        Subject.query.filter_by(student_id=student.id).delete()
        codes       = request.form.getlist("subj_code[]")
        names       = request.form.getlist("subj_name[]")
        semesters   = request.form.getlist("subj_semester[]")
        max_exam    = request.form.getlist("subj_max_exam[]")
        max_sess    = request.form.getlist("subj_max_sess[]")
        max_total   = request.form.getlist("subj_max_total[]")
        marks_exam  = request.form.getlist("subj_marks_exam[]")
        marks_sess  = request.form.getlist("subj_marks_sess[]")
        marks_total = request.form.getlist("subj_marks_total[]")

        for i in range(len(codes)):
            subj = Subject(
                student_id    = student.id,
                semester      = int(semesters[i]),
                code          = codes[i],
                name          = names[i],
                max_exam      = int(max_exam[i]),
                max_sess      = int(max_sess[i]),
                max_total     = int(max_total[i]),
                marks_exam    = int(marks_exam[i]),
                marks_sess    = int(marks_sess[i]),
                marks_total   = int(marks_total[i])
            )
            db.session.add(subj)

        db.session.commit()
        flash("Student record updated successfully.", "success")
        return redirect(url_for("admin"))

    # GET → render form pre‐filled
    return render_template("admin_edit.html", student=student)


@app.route("/admin/delete/<int:student_id>", methods=["POST"])
@login_required
def admin_delete(student_id):
    student = Student.query.get_or_404(student_id)
    db.session.delete(student)
    db.session.commit()
    flash("Student deleted.", "success")
    return redirect(url_for("admin"))


# ─── RUN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True)
