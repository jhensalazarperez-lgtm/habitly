import os
import secrets
import sqlite3
import uuid
from datetime import date, timedelta
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory, render_template, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)

# In production (Render), set SECRET_KEY as an environment variable so
# sessions survive restarts. Locally, it falls back to a random key each
# run, which is fine since nobody needs to stay logged in across restarts
# on your own machine.
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

# DATA_DIR lets deployment point the database and uploads at a persistent
# disk (e.g. Render's mounted disk at /data) instead of the app folder,
# which gets wiped on every redeploy. Locally this just defaults to the
# project folder, so nothing changes when you run it on your own machine.
DATA_DIR = os.environ.get("DATA_DIR", os.path.dirname(__file__))
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "habit_tracker.db")
UPLOAD_FOLDER = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_FILE_SIZE_MB = 5

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE_MB * 1024 * 1024

DEFAULT_COLORS = ["#723be8", "#d99c3f", "#3f9c8b", "#d85a70", "#4a90d9"]
THEME_COLORS = ["#723be8", "#d99c3f", "#3f9c8b", "#d85a70", "#4a90d9", "#1a1a1a", "#2f6fa8"]

APP_NAME = "Habitly"
APP_TAGLINE = "Build consistency, one day at a time."


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            category TEXT,
            color TEXT NOT NULL DEFAULT '#723be8',
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS habit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            duration_minutes INTEGER,
            notes TEXT,
            photo_filename TEXT,
            FOREIGN KEY (habit_id) REFERENCES habits (id) ON DELETE CASCADE
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS profile (
            user_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL DEFAULT 'Your Name',
            bio TEXT,
            avatar_filename TEXT,
            theme_color TEXT NOT NULL DEFAULT '#723be8',
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )

    conn.commit()
    conn.close()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def calculate_streak(log_dates):
    if not log_dates:
        return 0
    unique_dates = sorted({date.fromisoformat(d) for d in log_dates}, reverse=True)
    today = date.today()
    if unique_dates[0] not in (today, today - timedelta(days=1)):
        return 0
    streak = 1
    for i in range(len(unique_dates) - 1):
        gap = (unique_dates[i] - unique_dates[i + 1]).days
        if gap == 1:
            streak += 1
        else:
            break
    return streak


def calculate_best_streak(log_dates):
    if not log_dates:
        return 0
    unique_dates = sorted({date.fromisoformat(d) for d in log_dates})
    best = current = 1
    for i in range(1, len(unique_dates)):
        gap = (unique_dates[i] - unique_dates[i - 1]).days
        if gap == 1:
            current += 1
            best = max(best, current)
        else:
            current = 1
    return best


def week_activity(log_dates):
    date_set = {date.fromisoformat(d) for d in log_dates}
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    days = []
    for i in range(7):
        day = monday + timedelta(days=i)
        days.append({"date": day.isoformat(), "logged": day in date_set})
    return days


def habit_belongs_to_current_user(conn, habit_id):
    row = conn.execute(
        "SELECT user_id FROM habits WHERE id = ?", (habit_id,)
    ).fetchone()
    return row is not None and row["user_id"] == session.get("user_id")


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def login_required_page(f):
    """For page routes: redirect to /login if not signed in."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return wrapper


def login_required_api(f):
    """For /api/* routes: return 401 JSON if not signed in."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Not signed in."}), 401
        return f(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Auth pages
# ---------------------------------------------------------------------------

@app.route("/signup", methods=["GET", "POST"])
def signup_page():
    if request.method == "GET":
        if "user_id" in session:
            return redirect(url_for("index"))
        return render_template("signup.html", app_name=APP_NAME, tagline=APP_TAGLINE, error=None)

    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    confirm = request.form.get("confirm_password") or ""

    if not email or not password:
        return render_template("signup.html", app_name=APP_NAME, tagline=APP_TAGLINE, error="Email and password are required.")
    if len(password) < 6:
        return render_template("signup.html", app_name=APP_NAME, tagline=APP_TAGLINE, error="Password must be at least 6 characters.")
    if password != confirm:
        return render_template("signup.html", app_name=APP_NAME, tagline=APP_TAGLINE, error="Passwords don't match.")

    conn = get_db()
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        conn.close()
        return render_template("signup.html", app_name=APP_NAME, tagline=APP_TAGLINE, error="An account with that email already exists.")

    password_hash = generate_password_hash(password)
    conn.execute(
        "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
        (email, password_hash, date.today().isoformat()),
    )
    conn.commit()
    user_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]

    default_name = email.split("@")[0]
    conn.execute(
        "INSERT INTO profile (user_id, name, bio, theme_color) VALUES (?, ?, '', ?)",
        (user_id, default_name, THEME_COLORS[0]),
    )
    conn.commit()
    conn.close()

    session["user_id"] = user_id
    return redirect(url_for("index"))


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "GET":
        if "user_id" in session:
            return redirect(url_for("index"))
        return render_template("login.html", app_name=APP_NAME, tagline=APP_TAGLINE, error=None)

    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", app_name=APP_NAME, tagline=APP_TAGLINE, error="Incorrect email or password.")

    session["user_id"] = user["id"]
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

@app.route("/")
@login_required_page
def index():
    return render_template("index.html", app_name=APP_NAME, tagline=APP_TAGLINE)


# ---------------------------------------------------------------------------
# Profile endpoints (scoped to the signed-in user)
# ---------------------------------------------------------------------------

@app.route("/api/profile", methods=["GET"])
@login_required_api
def get_profile():
    conn = get_db()
    row = conn.execute("SELECT * FROM profile WHERE user_id = ?", (session["user_id"],)).fetchone()
    conn.close()
    return jsonify(
        {
            "name": row["name"],
            "bio": row["bio"],
            "avatar_url": f"/uploads/{row['avatar_filename']}" if row["avatar_filename"] else None,
            "theme_color": row["theme_color"],
        }
    )


@app.route("/api/profile", methods=["POST"])
@login_required_api
def update_profile():
    user_id = session["user_id"]
    name = (request.form.get("name") or "").strip() or "Your Name"
    bio = request.form.get("bio") or ""

    conn = get_db()
    current = conn.execute(
        "SELECT avatar_filename, theme_color FROM profile WHERE user_id = ?", (user_id,)
    ).fetchone()
    avatar_filename = current["avatar_filename"] if current else None
    theme_color = current["theme_color"] if current else THEME_COLORS[0]

    submitted_color = request.form.get("theme_color")
    if submitted_color and submitted_color in THEME_COLORS:
        theme_color = submitted_color

    avatar = request.files.get("avatar")
    if avatar and avatar.filename:
        if not allowed_file(avatar.filename):
            conn.close()
            return jsonify({"error": "Unsupported file type."}), 400
        ext = avatar.filename.rsplit(".", 1)[1].lower()
        if avatar_filename:
            old_path = os.path.join(app.config["UPLOAD_FOLDER"], avatar_filename)
            if os.path.exists(old_path):
                os.remove(old_path)
        avatar_filename = f"{uuid.uuid4().hex}.{ext}"
        avatar.save(os.path.join(app.config["UPLOAD_FOLDER"], secure_filename(avatar_filename)))

    conn.execute(
        "UPDATE profile SET name = ?, bio = ?, avatar_filename = ?, theme_color = ? WHERE user_id = ?",
        (name, bio, avatar_filename, theme_color, user_id),
    )
    conn.commit()
    conn.close()

    return jsonify(
        {
            "name": name,
            "bio": bio,
            "avatar_url": f"/uploads/{avatar_filename}" if avatar_filename else None,
            "theme_color": theme_color,
        }
    )


# ---------------------------------------------------------------------------
# Habit endpoints (scoped to the signed-in user)
# ---------------------------------------------------------------------------

@app.route("/api/habits", methods=["GET"])
@login_required_api
def get_habits():
    user_id = session["user_id"]
    conn = get_db()
    habits = conn.execute(
        "SELECT * FROM habits WHERE user_id = ? ORDER BY created_at ASC", (user_id,)
    ).fetchall()

    result = []
    today_str = date.today().isoformat()
    for habit in habits:
        logs = conn.execute(
            "SELECT date FROM habit_logs WHERE habit_id = ?", (habit["id"],)
        ).fetchall()
        log_dates = [row["date"] for row in logs]
        result.append(
            {
                "id": habit["id"],
                "name": habit["name"],
                "category": habit["category"],
                "color": habit["color"],
                "created_at": habit["created_at"],
                "streak": calculate_streak(log_dates),
                "best_streak": calculate_best_streak(log_dates),
                "total_logs": len(set(log_dates)),
                "logged_today": today_str in log_dates,
            }
        )
    conn.close()
    return jsonify(result)


@app.route("/api/habits", methods=["POST"])
@login_required_api
def create_habit():
    user_id = session["user_id"]
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Habit name is required."}), 400

    category = (data.get("category") or "").strip() or None

    conn = get_db()
    existing_count = conn.execute(
        "SELECT COUNT(*) AS n FROM habits WHERE user_id = ?", (user_id,)
    ).fetchone()["n"]
    color = data.get("color") or DEFAULT_COLORS[existing_count % len(DEFAULT_COLORS)]

    conn.execute(
        "INSERT INTO habits (user_id, name, category, color, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, name, category, color, date.today().isoformat()),
    )
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    conn.close()
    return jsonify({"id": new_id, "name": name, "category": category, "color": color}), 201


@app.route("/api/habits/<int:habit_id>", methods=["PUT"])
@login_required_api
def update_habit(habit_id):
    conn = get_db()
    if not habit_belongs_to_current_user(conn, habit_id):
        conn.close()
        return jsonify({"error": "Habit not found."}), 404

    data = request.get_json(silent=True) or {}
    habit = conn.execute("SELECT * FROM habits WHERE id = ?", (habit_id,)).fetchone()

    name = (data.get("name") or habit["name"]).strip()
    category = data.get("category", habit["category"])
    color = data.get("color", habit["color"])

    conn.execute(
        "UPDATE habits SET name = ?, category = ?, color = ? WHERE id = ?",
        (name, category, color, habit_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"id": habit_id, "name": name, "category": category, "color": color})


@app.route("/api/habits/<int:habit_id>", methods=["DELETE"])
@login_required_api
def delete_habit(habit_id):
    conn = get_db()
    if not habit_belongs_to_current_user(conn, habit_id):
        conn.close()
        return jsonify({"error": "Habit not found."}), 404
    conn.execute("DELETE FROM habits WHERE id = ?", (habit_id,))
    conn.commit()
    conn.close()
    return jsonify({"deleted": True})


# ---------------------------------------------------------------------------
# Stats endpoints
# ---------------------------------------------------------------------------

@app.route("/api/habits/<int:habit_id>/stats", methods=["GET"])
@login_required_api
def habit_stats(habit_id):
    conn = get_db()
    if not habit_belongs_to_current_user(conn, habit_id):
        conn.close()
        return jsonify({"error": "Habit not found."}), 404

    logs = conn.execute(
        "SELECT date, duration_minutes FROM habit_logs WHERE habit_id = ?", (habit_id,)
    ).fetchall()
    conn.close()

    log_dates = [row["date"] for row in logs]
    total_minutes = sum(row["duration_minutes"] or 0 for row in logs)

    return jsonify(
        {
            "current_streak": calculate_streak(log_dates),
            "best_streak": calculate_best_streak(log_dates),
            "total_logs": len(set(log_dates)),
            "total_minutes": total_minutes,
            "week": week_activity(log_dates),
        }
    )


@app.route("/api/stats/summary", methods=["GET"])
@login_required_api
def summary_stats():
    user_id = session["user_id"]
    conn = get_db()
    habits = conn.execute("SELECT id FROM habits WHERE user_id = ?", (user_id,)).fetchall()

    best_overall = 0
    total_logs_overall = 0
    for habit in habits:
        logs = conn.execute(
            "SELECT date FROM habit_logs WHERE habit_id = ?", (habit["id"],)
        ).fetchall()
        log_dates = [row["date"] for row in logs]
        best_overall = max(best_overall, calculate_best_streak(log_dates))
        total_logs_overall += len(set(log_dates))

    conn.close()
    return jsonify(
        {
            "total_habits": len(habits),
            "best_streak_overall": best_overall,
            "total_logs_overall": total_logs_overall,
        }
    )


# ---------------------------------------------------------------------------
# Log endpoints (scoped via their parent habit's ownership)
# ---------------------------------------------------------------------------

@app.route("/api/habits/<int:habit_id>/logs", methods=["GET"])
@login_required_api
def get_logs(habit_id):
    conn = get_db()
    if not habit_belongs_to_current_user(conn, habit_id):
        conn.close()
        return jsonify({"error": "Habit not found."}), 404

    logs = conn.execute(
        "SELECT * FROM habit_logs WHERE habit_id = ? ORDER BY date DESC", (habit_id,)
    ).fetchall()
    conn.close()

    result = []
    for log in logs:
        result.append(
            {
                "id": log["id"],
                "date": log["date"],
                "duration_minutes": log["duration_minutes"],
                "notes": log["notes"],
                "photo_url": f"/uploads/{log['photo_filename']}" if log["photo_filename"] else None,
            }
        )
    return jsonify(result)


@app.route("/api/habits/<int:habit_id>/logs", methods=["POST"])
@login_required_api
def create_log(habit_id):
    conn = get_db()
    if not habit_belongs_to_current_user(conn, habit_id):
        conn.close()
        return jsonify({"error": "Habit not found."}), 404

    log_date = request.form.get("date") or date.today().isoformat()
    duration = request.form.get("duration_minutes") or None
    notes = request.form.get("notes") or None

    photo_filename = None
    photo = request.files.get("photo")
    if photo and photo.filename:
        if not allowed_file(photo.filename):
            conn.close()
            return jsonify({"error": "Unsupported file type."}), 400
        ext = photo.filename.rsplit(".", 1)[1].lower()
        photo_filename = f"{uuid.uuid4().hex}.{ext}"
        safe_path = os.path.join(app.config["UPLOAD_FOLDER"], secure_filename(photo_filename))
        photo.save(safe_path)

    conn.execute(
        """
        INSERT INTO habit_logs (habit_id, date, duration_minutes, notes, photo_filename)
        VALUES (?, ?, ?, ?, ?)
        """,
        (habit_id, log_date, duration, notes, photo_filename),
    )
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    conn.close()

    return jsonify(
        {
            "id": new_id,
            "date": log_date,
            "duration_minutes": duration,
            "notes": notes,
            "photo_url": f"/uploads/{photo_filename}" if photo_filename else None,
        }
    ), 201


@app.route("/api/logs/<int:log_id>", methods=["DELETE"])
@login_required_api
def delete_log(log_id):
    conn = get_db()
    row = conn.execute(
        """
        SELECT habit_logs.photo_filename, habits.user_id
        FROM habit_logs JOIN habits ON habit_logs.habit_id = habits.id
        WHERE habit_logs.id = ?
        """,
        (log_id,),
    ).fetchone()

    if not row or row["user_id"] != session["user_id"]:
        conn.close()
        return jsonify({"error": "Log not found."}), 404

    if row["photo_filename"]:
        photo_path = os.path.join(app.config["UPLOAD_FOLDER"], row["photo_filename"])
        if os.path.exists(photo_path):
            os.remove(photo_path)

    conn.execute("DELETE FROM habit_logs WHERE id = ?", (log_id,))
    conn.commit()
    conn.close()
    return jsonify({"deleted": True})


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    # Uploaded photos are served without an auth check so <img> tags can
    # load them directly; filenames are randomized UUIDs, so they aren't
    # guessable.
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# ---------------------------------------------------------------------------
# PWA files — served from the root path (not /static/) so the service
# worker's scope covers the entire app, not just the static folder.
# ---------------------------------------------------------------------------

@app.route("/manifest.json")
def manifest():
    return send_from_directory(app.static_folder, "manifest.json")


@app.route("/sw.js")
def service_worker():
    return send_from_directory(app.static_folder, "sw.js")


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# This runs every time the module is loaded — whether via `python app.py`
# (local dev) or via `gunicorn app:app` (production/Render). Gunicorn never
# executes the `if __name__ == "__main__":` block below, so init_db() has
# to live out here to guarantee the database tables actually get created
# before any request comes in.
# ---------------------------------------------------------------------------
init_db()

if __name__ == "__main__":
    app.run(debug=True)
