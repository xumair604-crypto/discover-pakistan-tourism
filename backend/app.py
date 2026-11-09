"""
Discover Pakistan Tourism: booking and website-content backend.

A small Flask app with a SQLite database, built to run on PythonAnywhere.

Public API (called by the website on GitHub Pages):
    GET  /api/health          simple status check
    GET  /api/content         published tours, offers, hotels and venues
    POST /api/bookings        save an enquiry or trip-builder request

Owner area (same server):
    GET  /admin               the admin dashboard
    /api/admin/...            login, bookings and content management

Settings live in instance/settings.json, created by `python manage.py init`.
"""
import csv
import io
import json
import os
import re
import secrets
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from functools import wraps

from flask import Flask, Response, g, jsonify, redirect, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
SETTINGS_FILE = os.path.join(INSTANCE_DIR, "settings.json")

STATUSES = ("new", "contacted", "quoted", "confirmed", "completed", "cancelled")
SOURCES = ("enquiry", "trip_builder")
REF_RE = re.compile(r"^DP-[A-Z0-9]{4,10}$")
SLUG_RE = re.compile(r"^[a-z0-9-]{2,40}$")
ICON_RE = re.compile(r"^[a-z-]{2,40}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

BOOKING_TEXT_FIELDS = {
    # field: (max length, required)
    "name": (120, True),
    "phone": (40, True),
    "email": (200, False),
    "service": (80, False),
    "destination": (400, False),
    "guests": (40, False),
    "travelling_from": (120, False),
    "message": (3000, False),
}
DETAIL_KEYS = ("start", "style", "transport", "hotels", "places", "meals", "days")

# Field rules for website content. Types: text, choice, url, int, bool, plan, lines.
ENTITIES = {
    "tours": {
        "key": "id",
        "slug_key": True,
        "json": ("plan", "incl", "excl"),
        "fields": {
            "title": {"type": "text", "max": 200, "required": True},
            "region": {"type": "text", "max": 60, "required": True},
            "length": {"type": "choice", "choices": ("day", "short", "long"), "default": "short"},
            "days": {"type": "text", "max": 40},
            "summary": {"type": "text", "max": 600},
            "season": {"type": "text", "max": 120},
            "start_from": {"type": "text", "max": 120},
            "img": {"type": "url", "max": 600},
            "alt": {"type": "text", "max": 300},
            "plan": {"type": "plan"},
            "incl": {"type": "lines"},
            "excl": {"type": "lines"},
            "note": {"type": "text", "max": 1000, "nullable": True},
            "sort": {"type": "int", "default": 100},
            "published": {"type": "bool", "default": True},
        },
    },
    "offers": {
        "key": "id",
        "fields": {
            "title": {"type": "text", "max": 200, "required": True},
            "body": {"type": "text", "max": 1000},
            "sort": {"type": "int", "default": 100},
            "published": {"type": "bool", "default": True},
        },
    },
    "hotels": {
        "key": "id",
        "fields": {
            "name": {"type": "text", "max": 200, "required": True},
            "details": {"type": "text", "max": 300},
            "icon": {"type": "icon", "default": "buildings"},
            "sort": {"type": "int", "default": 100},
            "published": {"type": "bool", "default": True},
        },
    },
    "venues": {
        "key": "id",
        "fields": {
            "name": {"type": "text", "max": 200, "required": True},
            "details": {"type": "text", "max": 300},
            "sort": {"type": "int", "default": 100},
            "published": {"type": "bool", "default": True},
        },
    },
}

SCHEMA = """
create table if not exists admins (
    id            integer primary key autoincrement,
    username      text not null unique collate nocase,
    password_hash text not null,
    created_at    text not null,
    last_login    text
);
create table if not exists bookings (
    id              integer primary key autoincrement,
    ref             text not null unique,
    created_at      text not null,
    updated_at      text not null,
    source          text not null default 'enquiry',
    name            text not null,
    phone           text not null,
    email           text,
    service         text,
    destination     text,
    travel_date     text,
    guests          text,
    travelling_from text,
    message         text,
    details         text not null default '{}',
    status          text not null default 'new',
    quoted_rate     text,
    admin_notes     text
);
create index if not exists bookings_created on bookings (created_at desc);
create table if not exists tours (
    id         text primary key,
    sort       integer not null default 100,
    published  integer not null default 1,
    region     text not null,
    length     text not null default 'short',
    days       text not null default '',
    title      text not null,
    summary    text not null default '',
    season     text not null default '',
    start_from text not null default '',
    img        text not null default '',
    alt        text not null default '',
    plan       text not null default '[]',
    incl       text not null default '[]',
    excl       text not null default '[]',
    note       text,
    updated_at text not null
);
create table if not exists offers (
    id         integer primary key autoincrement,
    sort       integer not null default 100,
    published  integer not null default 1,
    title      text not null,
    body       text not null default '',
    updated_at text not null
);
create table if not exists hotels (
    id         integer primary key autoincrement,
    sort       integer not null default 100,
    published  integer not null default 1,
    name       text not null,
    details    text not null default '',
    icon       text not null default 'buildings',
    updated_at text not null
);
create table if not exists venues (
    id         integer primary key autoincrement,
    sort       integer not null default 100,
    published  integer not null default 1,
    name       text not null,
    details    text not null default '',
    updated_at text not null
);
create table if not exists hits (
    bucket text not null,
    at     real not null
);
create index if not exists hits_bucket on hits (bucket, at);
"""


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ValidationError(Exception):
    pass


# ---------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------
def connect(path):
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    return conn


def init_db(path, seed_file=None):
    """Create tables, and load starting content if the content tables are empty."""
    conn = connect(path)
    conn.executescript(SCHEMA)
    if seed_file and os.path.exists(seed_file):
        with open(seed_file, encoding="utf-8") as fh:
            seed = json.load(fh)
        stamp = now_iso()
        if not conn.execute("select 1 from tours limit 1").fetchone():
            for i, t in enumerate(seed.get("tours", [])):
                conn.execute(
                    "insert into tours (id, sort, published, region, length, days, title, summary, season, start_from,"
                    " img, alt, plan, incl, excl, note, updated_at) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (t["id"], (i + 1) * 10, 1, t["region"], t["length"], t["days"], t["title"], t["summary"], t["season"],
                     t["start_from"], t["img"], t["alt"], json.dumps(t["plan"]), json.dumps(t["incl"]),
                     json.dumps(t["excl"]), t.get("note"), stamp))
        for table, cols in (("offers", ("title", "body")), ("hotels", ("name", "details", "icon")), ("venues", ("name", "details"))):
            if not conn.execute(f"select 1 from {table} limit 1").fetchone():
                for i, item in enumerate(seed.get(table, [])):
                    names = ("sort",) + cols + ("updated_at",)
                    conn.execute(
                        f"insert into {table} ({', '.join(names)}) values ({', '.join('?' * len(names))})",
                        ((i + 1) * 10,) + tuple(item[c] for c in cols) + (stamp,))
    conn.commit()
    conn.close()


def get_db():
    if "db" not in g:
        g.db = connect(g.app_config["DATABASE"])
    return g.db


def row_out(entity, row):
    d = dict(row)
    for col in ENTITIES.get(entity, {}).get("json", ()):
        d[col] = json.loads(d[col] or "[]")
    if "published" in d:
        d["published"] = bool(d["published"])
    return d


def booking_out(row):
    d = dict(row)
    d["details"] = json.loads(d.get("details") or "{}")
    return d


# ---------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------
def clean_text(value, max_len, required=False, label="Field"):
    if value is None:
        value = ""
    if not isinstance(value, (str, int, float)):
        raise ValidationError(f"{label} must be text.")
    value = str(value).strip()
    if required and not value:
        raise ValidationError(f"{label} is required.")
    if len(value) > max_len:
        raise ValidationError(f"{label} is too long (maximum {max_len} characters).")
    return value


def clean_details(details):
    if not isinstance(details, dict):
        return {}
    out = {}
    for key in DETAIL_KEYS:
        v = details.get(key)
        if isinstance(v, list):
            items = [clean_text(x, 200, label=key) for x in v[:30] if isinstance(x, (str, int, float))]
            out[key] = [x for x in items if x]
        elif isinstance(v, (str, int, float)):
            out[key] = clean_text(v, 400, label=key)
    return out


def clean_booking(data):
    if not isinstance(data, dict):
        raise ValidationError("Invalid request.")
    out = {}
    for field, (max_len, required) in BOOKING_TEXT_FIELDS.items():
        label = field.replace("_", " ").capitalize()
        out[field] = clean_text(data.get(field), max_len, required, label) or None
    travel_date = str(data.get("travel_date") or "").strip()
    out["travel_date"] = None
    if travel_date:
        if not DATE_RE.match(travel_date):
            raise ValidationError("Travel date must look like 2026-12-31.")
        try:
            date.fromisoformat(travel_date)
        except ValueError:
            raise ValidationError("Travel date is not a real date.")
        out["travel_date"] = travel_date
    source = data.get("source")
    out["source"] = source if source in SOURCES else "enquiry"
    out["details"] = json.dumps(clean_details(data.get("details")), ensure_ascii=False)
    if len(out["details"]) > 8000:
        raise ValidationError("Too much detail in this request.")
    return out


def clean_entity(entity, data, creating):
    spec = ENTITIES[entity]
    if not isinstance(data, dict):
        raise ValidationError("Invalid request.")
    out = {}
    for field, rule in spec["fields"].items():
        if field not in data:
            if creating:
                if rule.get("required"):
                    raise ValidationError(f"{field.replace('_', ' ').capitalize()} is required.")
                if "default" in rule:
                    out[field] = rule["default"]
            continue
        v, t, label = data[field], rule["type"], field.replace("_", " ").capitalize()
        if t == "text":
            v = clean_text(v, rule["max"], rule.get("required"), label)
            if rule.get("nullable") and not v:
                v = None
        elif t == "url":
            v = clean_text(v, rule["max"], False, "Photo link")
            if v and not v.startswith("https://"):
                raise ValidationError("The photo link must start with https://")
        elif t == "choice":
            if v not in rule["choices"]:
                raise ValidationError(f"{label} must be one of: {', '.join(rule['choices'])}.")
        elif t == "icon":
            if not isinstance(v, str) or not ICON_RE.match(v):
                raise ValidationError("Icon name is not valid.")
        elif t == "int":
            try:
                v = int(v)
            except (TypeError, ValueError):
                raise ValidationError(f"{label} must be a whole number.")
            if not -100000 <= v <= 100000:
                raise ValidationError(f"{label} is out of range.")
        elif t == "bool":
            v = 1 if v in (True, 1, "1", "true", "on") else 0
        elif t == "lines":
            if not isinstance(v, list) or len(v) > 40:
                raise ValidationError(f"{label} must be a list of up to 40 lines.")
            v = json.dumps([clean_text(x, 300, label=label) for x in v if str(x).strip()], ensure_ascii=False)
        elif t == "plan":
            if not isinstance(v, list) or len(v) > 30:
                raise ValidationError("The plan must have up to 30 days.")
            plan = []
            for item in v:
                if not isinstance(item, (list, tuple)) or len(item) != 2:
                    raise ValidationError("Each plan line needs a day and a description.")
                plan.append([clean_text(item[0], 40, label="Day"), clean_text(item[1], 600, True, "Plan description")])
            v = json.dumps(plan, ensure_ascii=False)
        out[field] = v
    return out


# ---------------------------------------------------------------------
# Rate limiting (stored in SQLite so it works across server processes)
# ---------------------------------------------------------------------
def client_ip():
    if g.app_config.get("TRUST_X_REAL_IP"):
        ip = request.headers.get("X-Real-IP") or (request.headers.get("X-Forwarded-For", "").split(",")[0].strip())
        if ip:
            return ip
    return request.remote_addr or "unknown"


def too_many(bucket, limit, window_seconds):
    db = get_db()
    cutoff = time.time() - window_seconds
    db.execute("delete from hits where at < ?", (time.time() - 86400,))
    count = db.execute("select count(*) from hits where bucket = ? and at >= ?", (bucket, cutoff)).fetchone()[0]
    return count >= limit


def record_hit(bucket):
    get_db().execute("insert into hits (bucket, at) values (?, ?)", (bucket, time.time()))
    get_db().commit()


def new_ref():
    return "DP-" + "".join(secrets.choice(REF_ALPHABET) for _ in range(6))


# ---------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def create_app(test_config=None):
    app = Flask(__name__, instance_path=INSTANCE_DIR)
    app.config.update(
        DATABASE=os.path.join(INSTANCE_DIR, "dpt.sqlite3"),
        SEED_FILE=os.path.join(BASE_DIR, "seed.json"),
        SECRET_KEY=None,
        ALLOWED_ORIGINS=["https://xumair604-crypto.github.io"],
        SESSION_COOKIE_NAME="dpt_admin",
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        MAX_CONTENT_LENGTH=64 * 1024,
        TRUST_X_REAL_IP=True,
        BOOKINGS_PER_IP_PER_HOUR=20,
        LOGIN_FAILURES_PER_15_MIN=8,
    )
    app.config.update(load_settings())
    if test_config:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("No SECRET_KEY. Run `python manage.py init` first.")
    os.makedirs(os.path.dirname(app.config["DATABASE"]), exist_ok=True)
    init_db(app.config["DATABASE"], app.config.get("SEED_FILE"))

    @app.before_request
    def _attach_config():
        g.app_config = app.config

    @app.teardown_appcontext
    def _close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    # ---------- Headers: security and cross-site access for the public API ----------
    public_paths = ("/api/health", "/api/content", "/api/bookings")

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.path in public_paths:
            origin = request.headers.get("Origin")
            if origin and origin in app.config["ALLOWED_ORIGINS"]:
                resp.headers["Access-Control-Allow-Origin"] = origin
                resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
                resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
                resp.headers["Access-Control-Max-Age"] = "86400"
            resp.headers["Vary"] = "Origin"
            if request.path == "/api/content":
                resp.headers["Cache-Control"] = "public, max-age=60"
        else:
            resp.headers["X-Frame-Options"] = "DENY"
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.errorhandler(ValidationError)
    def _validation(err):
        return jsonify(error=str(err)), 400

    @app.errorhandler(413)
    def _too_large(_err):
        return jsonify(error="Request too large."), 413

    # ---------- Public API ----------
    @app.route("/api/health")
    def health():
        return jsonify(ok=True)

    @app.route("/api/content")
    def content():
        db = get_db()
        out = {}
        for entity in ENTITIES:
            rows = db.execute(f"select * from {entity} where published = 1 order by sort, rowid").fetchall()
            out[entity] = [row_out(entity, r) for r in rows]
            for item in out[entity]:
                item.pop("updated_at", None)
                item.pop("published", None)
        return jsonify(out)

    @app.route("/api/bookings", methods=["POST", "OPTIONS"])
    def create_booking():
        if request.method == "OPTIONS":
            return ("", 204)
        origin = request.headers.get("Origin")
        if origin and origin not in app.config["ALLOWED_ORIGINS"] and origin != request.host_url.rstrip("/"):
            return jsonify(error="This website is not allowed to send bookings."), 403
        # Accept JSON sent as application/json or text/plain (text/plain avoids
        # a browser pre-check, so the booking still sends while WhatsApp opens).
        data = request.get_json(force=True, silent=True)
        if not isinstance(data, dict):
            return jsonify(error="Invalid request."), 400
        if str(data.get("website") or "").strip():
            return jsonify(ok=True, ref=new_ref()), 201  # spam trap: pretend success, store nothing
        bucket = "booking:" + client_ip()
        if too_many(bucket, app.config["BOOKINGS_PER_IP_PER_HOUR"], 3600):
            return jsonify(error="Too many requests. Please contact us on WhatsApp."), 429
        row = clean_booking(data)
        db = get_db()
        ref = str(data.get("ref") or "")
        if not REF_RE.match(ref) or db.execute("select 1 from bookings where ref = ?", (ref,)).fetchone():
            ref = new_ref()
        stamp = now_iso()
        cols = ["ref", "created_at", "updated_at", "source", "travel_date", "details"] + list(BOOKING_TEXT_FIELDS)
        values = [ref, stamp, stamp, row["source"], row["travel_date"], row["details"]] + [row[f] for f in BOOKING_TEXT_FIELDS]
        db.execute(f"insert into bookings ({', '.join(cols)}) values ({', '.join('?' * len(cols))})", values)
        db.commit()
        record_hit(bucket)
        return jsonify(ok=True, ref=ref), 201

    # ---------- Owner area ----------
    def current_admin():
        admin_id = session.get("admin_id")
        if not admin_id:
            return None
        return get_db().execute("select id, username from admins where id = ?", (admin_id,)).fetchone()

    def require_admin(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            admin = current_admin()
            if not admin:
                session.clear()
                return jsonify(error="Please sign in."), 401
            if request.method not in ("GET", "HEAD"):
                token = request.headers.get("X-CSRF-Token", "")
                if not token or not secrets.compare_digest(token, session.get("csrf", "")):
                    return jsonify(error="Your session expired. Please reload the page."), 403
            g.admin = admin
            return view(*args, **kwargs)
        return wrapper

    @app.route("/")
    def home():
        return redirect("/admin")

    @app.route("/admin")
    def admin_page():
        return render_template("admin.html")

    @app.route("/api/admin/login", methods=["POST"])
    def login():
        data = request.get_json(silent=True) or {}
        username = str(data.get("username") or "").strip()
        password = str(data.get("password") or "")
        bucket = "login:" + client_ip()
        if too_many(bucket, app.config["LOGIN_FAILURES_PER_15_MIN"], 900):
            return jsonify(error="Too many failed attempts. Wait 15 minutes and try again."), 429
        row = get_db().execute("select id, username, password_hash from admins where username = ?", (username,)).fetchone()
        if not row or not check_password_hash(row["password_hash"], password):
            record_hit(bucket)
            return jsonify(error="Wrong username or password."), 401
        session.clear()
        session.permanent = True
        session["admin_id"] = row["id"]
        session["csrf"] = secrets.token_urlsafe(32)
        get_db().execute("update admins set last_login = ? where id = ?", (now_iso(), row["id"]))
        get_db().commit()
        return jsonify(user=row["username"], csrf=session["csrf"])

    @app.route("/api/admin/me")
    def me():
        admin = current_admin()
        if not admin:
            return jsonify(error="Please sign in."), 401
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        return jsonify(user=admin["username"], csrf=session["csrf"])

    @app.route("/api/admin/logout", methods=["POST"])
    @require_admin
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.route("/api/admin/password", methods=["POST"])
    @require_admin
    def change_password():
        data = request.get_json(silent=True) or {}
        current, new = str(data.get("current") or ""), str(data.get("new") or "")
        row = get_db().execute("select password_hash from admins where id = ?", (g.admin["id"],)).fetchone()
        if not check_password_hash(row["password_hash"], current):
            return jsonify(error="Your current password is not correct."), 400
        if len(new) < 10:
            return jsonify(error="The new password must be at least 10 characters."), 400
        get_db().execute("update admins set password_hash = ? where id = ?", (generate_password_hash(new), g.admin["id"]))
        get_db().commit()
        return jsonify(ok=True)

    # Bookings
    @app.route("/api/admin/bookings")
    @require_admin
    def list_bookings():
        rows = get_db().execute("select * from bookings order by created_at desc, id desc limit 2000").fetchall()
        return jsonify([booking_out(r) for r in rows])

    @app.route("/api/admin/bookings/<int:booking_id>", methods=["PATCH", "DELETE"])
    @require_admin
    def edit_booking(booking_id):
        db = get_db()
        if not db.execute("select 1 from bookings where id = ?", (booking_id,)).fetchone():
            return jsonify(error="Booking not found."), 404
        if request.method == "DELETE":
            db.execute("delete from bookings where id = ?", (booking_id,))
            db.commit()
            return jsonify(ok=True)
        data = request.get_json(silent=True) or {}
        updates = {}
        if "status" in data:
            if data["status"] not in STATUSES:
                raise ValidationError("Unknown status.")
            updates["status"] = data["status"]
        if "quoted_rate" in data:
            updates["quoted_rate"] = clean_text(data["quoted_rate"], 200, label="Rate") or None
        if "admin_notes" in data:
            updates["admin_notes"] = clean_text(data["admin_notes"], 5000, label="Notes") or None
        if not updates:
            raise ValidationError("Nothing to update.")
        updates["updated_at"] = now_iso()
        db.execute(f"update bookings set {', '.join(k + ' = ?' for k in updates)} where id = ?", list(updates.values()) + [booking_id])
        db.commit()
        return jsonify(booking_out(db.execute("select * from bookings where id = ?", (booking_id,)).fetchone()))

    @app.route("/api/admin/bookings.csv")
    @require_admin
    def bookings_csv():
        rows = get_db().execute("select * from bookings order by created_at desc, id desc").fetchall()
        cols = ["ref", "created_at", "status", "name", "phone", "email", "service", "destination", "travel_date",
                "guests", "travelling_from", "message", "quoted_rate", "admin_notes", "details", "source"]
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(cols)

        def safe(v):
            v = "" if v is None else str(v)
            return "'" + v if v[:1] in ("=", "+", "-", "@") else v  # stop spreadsheet formula injection
        for r in rows:
            writer.writerow([safe(r[c]) for c in cols])
        name = f"bookings-{date.today().isoformat()}.csv"
        return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    # Website content
    @app.route("/api/admin/<entity>", methods=["GET", "POST"])
    @require_admin
    def entity_collection(entity):
        if entity not in ENTITIES:
            return jsonify(error="Not found."), 404
        spec, db = ENTITIES[entity], get_db()
        if request.method == "GET":
            rows = db.execute(f"select * from {entity} order by sort, rowid").fetchall()
            return jsonify([row_out(entity, r) for r in rows])
        data = request.get_json(silent=True) or {}
        values = clean_entity(entity, data, creating=True)
        if spec.get("slug_key"):
            key = str(data.get("id") or "").strip()
            if not SLUG_RE.match(key):
                raise ValidationError("Short ID can only use lowercase letters, numbers and dashes (2 to 40 characters).")
            if db.execute(f"select 1 from {entity} where id = ?", (key,)).fetchone():
                raise ValidationError("That Short ID is already used by another tour.")
            values = {"id": key, **values}
        values["updated_at"] = now_iso()
        cur = db.execute(f"insert into {entity} ({', '.join(values)}) values ({', '.join('?' * len(values))})", list(values.values()))
        db.commit()
        new_key = values.get("id", cur.lastrowid)
        return jsonify(row_out(entity, db.execute(f"select * from {entity} where id = ?", (new_key,)).fetchone())), 201

    @app.route("/api/admin/<entity>/<key>", methods=["PATCH", "DELETE"])
    @require_admin
    def entity_item(entity, key):
        if entity not in ENTITIES:
            return jsonify(error="Not found."), 404
        db = get_db()
        if not db.execute(f"select 1 from {entity} where id = ?", (key,)).fetchone():
            return jsonify(error="Not found."), 404
        if request.method == "DELETE":
            db.execute(f"delete from {entity} where id = ?", (key,))
            db.commit()
            return jsonify(ok=True)
        values = clean_entity(entity, request.get_json(silent=True) or {}, creating=False)
        if not values:
            raise ValidationError("Nothing to update.")
        values["updated_at"] = now_iso()
        db.execute(f"update {entity} set {', '.join(k + ' = ?' for k in values)} where id = ?", list(values.values()) + [key])
        db.commit()
        return jsonify(row_out(entity, db.execute(f"select * from {entity} where id = ?", (key,)).fetchone()))

    return app
