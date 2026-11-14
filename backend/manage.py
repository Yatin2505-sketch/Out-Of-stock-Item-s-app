"""Stockbook maintenance commands.

    python manage.py run             start the app (also prints the addresses to open)
    python manage.py create-admin    create an admin, or reset the password of an existing user
    python manage.py backup          save a dated copy of all data
    python manage.py restore FILE    replace all data with a backup (stop the app first)
"""
import os
import sys
import socket
import shutil
import sqlite3
import getpass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

import server  # noqa: E402  (loads .env, creates data folder)

PORT = int(os.environ.get("STOCKBOOK_PORT", "8000"))
KEEP_BACKUPS = int(os.environ.get("KEEP_BACKUPS", "60"))


def backup_dir() -> Path:
    d = Path(os.environ.get("BACKUP_DIR") or (ROOT / "backups"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def local_addresses():
    addrs = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addrs.add(info[4][0])
    except OSError:
        pass
    try:  # the address used to reach the internet / LAN
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        addrs.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(a for a in addrs if not a.startswith("127."))


def cmd_run():
    import uvicorn
    print("=" * 60)
    print(" Stockbook is starting. Keep this window open.")
    print(" Open one of these addresses in a phone or computer browser:")
    print(f"   On this computer:  http://localhost:{PORT}")
    for a in local_addresses():
        label = "Tailscale (anywhere)" if a.startswith("100.") else "Shop Wi-Fi"
        print(f"   {label + ':':20s} http://{a}:{PORT}")
    print(f" Data file: {server.DB_PATH}")
    print("=" * 60)
    uvicorn.run(server.app, host="0.0.0.0", port=PORT, log_level="warning")


def cmd_create_admin():
    server.init_db()
    print("Create an admin login (or reset the password of an existing user).")
    username = input("Username (e.g. papa): ").strip()
    if not username:
        print("No username given — nothing changed.")
        return 1
    while True:
        pw = getpass.getpass("Password (typing is hidden): ")
        if len(pw) < 4:
            print("  Please use at least 4 characters.")
            continue
        if pw != getpass.getpass("Type the password again: "):
            print("  The two passwords did not match, try again.")
            continue
        break
    with server.open_db() as conn:
        existing = conn.execute("SELECT id, name FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (server.hash_password(pw), existing["id"]))
            print(f"Password updated for existing user '{username}'.")
        else:
            name = input("Display name (e.g. Papa): ").strip() or username
            conn.execute(
                "INSERT INTO users (id, username, name, role, password_hash, created_at) VALUES (?, ?, ?, 'admin', ?, ?)",
                (server.new_id(), username, name, server.hash_password(pw), datetime.now(timezone.utc).isoformat()),
            )
            print(f"Admin '{username}' created.")
    first = server.DATA_DIR / "FIRST_LOGIN.txt"
    if first.exists():
        first.unlink()
    return 0


def cmd_backup():
    server.init_db()
    dest = backup_dir() / f"stockbook-{datetime.now():%Y-%m-%d_%H%M%S}.db"
    src = sqlite3.connect(str(server.DB_PATH))
    dst = sqlite3.connect(str(dest))
    with dst:
        src.backup(dst)  # safe even while the app is running
    src.close()
    dst.close()
    old = sorted(backup_dir().glob("stockbook-*.db"))
    for f in old[:-KEEP_BACKUPS] if KEEP_BACKUPS > 0 else []:
        f.unlink()
    print(f"Backup saved: {dest}")
    return 0


def cmd_restore(path: str):
    src = Path(path)
    if not src.is_file():
        print(f"File not found: {src}")
        return 1
    # Sanity check that it is a Stockbook database
    try:
        c = sqlite3.connect(str(src))
        c.execute("SELECT count(*) FROM logs").fetchone()
        c.close()
    except sqlite3.Error:
        print("That file is not a Stockbook backup.")
        return 1
    if server.DB_PATH.exists():
        cmd_backup()  # keep a copy of the current data, just in case
    for suffix in ("-wal", "-shm"):
        p = Path(str(server.DB_PATH) + suffix)
        if p.exists():
            p.unlink()
    shutil.copyfile(str(src), str(server.DB_PATH))
    print(f"Restored data from {src}. Start the app again.")
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd == "run":
        return cmd_run()
    if cmd == "create-admin":
        return cmd_create_admin()
    if cmd == "backup":
        return cmd_backup()
    if cmd == "restore" and len(argv) == 2:
        return cmd_restore(argv[1])
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)
