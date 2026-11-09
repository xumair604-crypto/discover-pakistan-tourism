"""
Setup and owner accounts for the Discover Pakistan Tourism backend.

    python manage.py init                      create settings and the database
    python manage.py create-admin USERNAME     add an owner login (asks for a password)
    python manage.py set-password USERNAME     reset an owner's password
    python manage.py delete-admin USERNAME     remove an owner login
    python manage.py list-admins               show owner logins
    python manage.py add-origin URL            allow another website address to send bookings
    python manage.py backup                    copy the database to instance/backups/
"""
import argparse
import getpass
import json
import os
import secrets
import shutil
import sys
from datetime import datetime

from werkzeug.security import generate_password_hash

import app as backend

DEFAULT_ORIGINS = ["https://xumair604-crypto.github.io"]


def read_settings():
    return backend.load_settings()


def write_settings(settings):
    os.makedirs(backend.INSTANCE_DIR, exist_ok=True)
    with open(backend.SETTINGS_FILE, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2)
    try:
        os.chmod(backend.SETTINGS_FILE, 0o600)
    except OSError:
        pass


def db_path():
    return read_settings().get("DATABASE", os.path.join(backend.INSTANCE_DIR, "dpt.sqlite3"))


def ask_password():
    while True:
        pw = getpass.getpass("Password (at least 10 characters): ")
        if len(pw) < 10:
            print("Too short, try again.")
            continue
        if pw != getpass.getpass("Type it again: "):
            print("The passwords did not match, try again.")
            continue
        return pw


def cmd_init(args):
    settings = read_settings()
    if not settings.get("SECRET_KEY"):
        settings["SECRET_KEY"] = secrets.token_hex(32)
        print("Created a new secret key.")
    settings.setdefault("ALLOWED_ORIGINS", DEFAULT_ORIGINS)
    write_settings(settings)
    backend.init_db(db_path(), os.path.join(backend.BASE_DIR, "seed.json"))
    print(f"Database ready at {db_path()}")
    print("Allowed websites:", ", ".join(settings["ALLOWED_ORIGINS"]))
    print("Next: python manage.py create-admin <username>")


def cmd_create_admin(args):
    conn = backend.connect(db_path())
    if conn.execute("select 1 from admins where username = ?", (args.username,)).fetchone():
        sys.exit(f"An owner called {args.username} already exists. Use set-password to change the password.")
    pw = ask_password()
    conn.execute("insert into admins (username, password_hash, created_at) values (?, ?, ?)",
                 (args.username, generate_password_hash(pw), backend.now_iso()))
    conn.commit()
    print(f"Owner {args.username} can now sign in at /admin.")


def cmd_set_password(args):
    conn = backend.connect(db_path())
    if not conn.execute("select 1 from admins where username = ?", (args.username,)).fetchone():
        sys.exit(f"No owner called {args.username}.")
    conn.execute("update admins set password_hash = ? where username = ?", (generate_password_hash(ask_password()), args.username))
    conn.commit()
    print("Password updated.")


def cmd_delete_admin(args):
    conn = backend.connect(db_path())
    cur = conn.execute("delete from admins where username = ?", (args.username,))
    conn.commit()
    print("Removed." if cur.rowcount else f"No owner called {args.username}.")


def cmd_list_admins(args):
    conn = backend.connect(db_path())
    rows = conn.execute("select username, created_at, last_login from admins order by username").fetchall()
    if not rows:
        print("No owners yet. Use create-admin.")
    for r in rows:
        print(f"{r['username']:<24} created {r['created_at']}   last sign-in {r['last_login'] or 'never'}")


def cmd_add_origin(args):
    origin = args.url.rstrip("/")
    if not origin.startswith("https://") or origin.count("/") != 2:
        sys.exit("Give just the site address, like https://www.example.com (no path).")
    settings = read_settings()
    origins = settings.setdefault("ALLOWED_ORIGINS", list(DEFAULT_ORIGINS))
    if origin not in origins:
        origins.append(origin)
    write_settings(settings)
    print("Allowed websites:", ", ".join(origins), "\nReload the web app for this to take effect.")


def cmd_backup(args):
    folder = os.path.join(backend.INSTANCE_DIR, "backups")
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, f"dpt-{datetime.now().strftime('%Y%m%d-%H%M%S')}.sqlite3")
    src = backend.connect(db_path())
    dst = backend.connect(target)
    src.backup(dst)
    dst.close()
    print("Backup saved to", target)


def main():
    parser = argparse.ArgumentParser(description="Discover Pakistan Tourism backend tools")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init").set_defaults(func=cmd_init)
    for name, func in (("create-admin", cmd_create_admin), ("set-password", cmd_set_password), ("delete-admin", cmd_delete_admin)):
        p = sub.add_parser(name)
        p.add_argument("username")
        p.set_defaults(func=func)
    sub.add_parser("list-admins").set_defaults(func=cmd_list_admins)
    p = sub.add_parser("add-origin")
    p.add_argument("url")
    p.set_defaults(func=cmd_add_origin)
    sub.add_parser("backup").set_defaults(func=cmd_backup)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
