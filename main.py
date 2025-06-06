import os
import uuid
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
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    roll_no = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(200), nullable=False)
    result_image = db.Column(db.String(200), nullable=False)


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
    Handles the form from home.html. Looks up the student by roll_no and email.
    If found → render result.html with the image. Otherwise flash + redirect.
    """
    roll_no = request.form.get("roll_no", "").strip()
    email = request.form.get("email", "").strip()
    student = Student.query.filter_by(roll_no=roll_no, email=email).first()
    if not student:
        flash("No record found for that Roll Number and Email.", "error")
        return redirect(url_for("home"))

    return render_template("result.html", student=student)


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
        name = request.form["name"].strip()
        roll_no = request.form["roll_no"].strip()
        email = request.form["email"].strip()
        file = request.files["result_image"]
        if file and file.filename:
            filename = f"{uuid.uuid4().hex}_{file.filename}"
            save_path = os.path.join(app.static_folder, "results", filename)
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            file.save(save_path)
        else:
            flash("Result image is required.", "error")
            return redirect(request.url)
        s = Student(name=name, roll_no=roll_no, email=email, result_image=filename)
        db.session.add(s)
        db.session.commit()
        flash("Student added.", "success")
        return redirect(url_for("admin"))
    return render_template("admin_edit.html", student=None)


@app.route("/admin/edit/<int:student_id>", methods=["GET", "POST"])
@login_required
def admin_edit(student_id):
    """
    Edit an existing student. On GET → load the form pre‐filled. On POST → save changes.
    """
    student = Student.query.get_or_404(student_id)

    if request.method == "POST":
        student.roll_no = request.form["roll_no"].strip()
        student.email = request.form["email"].strip()
        file = request.files.get("result_image")
        if file and file.filename:
            filename = f"{uuid.uuid4().hex}_{file.filename}"
            save_path = os.path.join(app.static_folder, "results", filename)
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            file.save(save_path)
            student.result_image = filename
        db.session.commit()
        flash("Student updated.", "success")
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
