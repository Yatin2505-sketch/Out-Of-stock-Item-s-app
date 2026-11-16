"""Stockbook backend.

Self-hosted: all data lives in one SQLite file on this computer
(data/stockbook.db by default). No external database or cloud service is used.
The built React app is served from ./static, so one program runs everything.
"""
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import io
import csv
import uuid
import secrets
import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import bcrypt
import jwt
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from xml.sax.saxutils import escape as xml_escape

from tally_import import parse_purchase_bills

JWT_ALGORITHM = "HS256"
UNASSIGNED = "unassigned"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("stockbook")

# ---------- Storage ----------
DATA_DIR = Path(os.environ.get("STOCKBOOK_DATA_DIR") or (ROOT_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "stockbook.db"
FRONTEND_DIR = Path(os.environ.get("STOCKBOOK_FRONTEND_DIR") or (ROOT_DIR / "static"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'employee')),
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS suppliers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS medicines (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    company TEXT NOT NULL DEFAULT '',
    default_supplier_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_medicines_name ON medicines(name COLLATE NOCASE);
CREATE TABLE IF NOT EXISTS logs (
    id TEXT PRIMARY KEY,
    medicine_id TEXT,
    medicine_name TEXT NOT NULL,
    company TEXT NOT NULL DEFAULT '',
    quantity TEXT NOT NULL DEFAULT '',
    supplier_id TEXT,
    date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    added_by_id TEXT NOT NULL,
    added_by_name TEXT NOT NULL,
    status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_logs_date ON logs(date);
CREATE INDEX IF NOT EXISTS idx_logs_supplier ON logs(supplier_id);
-- Every supplier a medicine can come from (one medicine may have several).
-- bills = number of Tally purchase bills seen; the default stays in medicines.default_supplier_id.
CREATE TABLE IF NOT EXISTS medicine_suppliers (
    medicine_id TEXT NOT NULL,
    supplier_id TEXT NOT NULL,
    bills INTEGER NOT NULL DEFAULT 0,
    last_date TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (medicine_id, supplier_id)
);
CREATE INDEX IF NOT EXISTS idx_medsup_supplier ON medicine_suppliers(supplier_id);
-- Tally bills already imported, so importing the same file twice doesn't double-count.
CREATE TABLE IF NOT EXISTS tally_bills (
    key TEXT PRIMARY KEY,
    imported_at TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def open_db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_db():
    with open_db() as conn:
        yield conn


def init_db():
    with open_db() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        # Make sure every existing default supplier is also in the supplier list
        conn.execute(
            "INSERT OR IGNORE INTO medicine_suppliers (medicine_id, supplier_id) "
            "SELECT id, default_supplier_id FROM medicines WHERE default_supplier_id IS NOT NULL"
        )


def row(r: Optional[sqlite3.Row]) -> Optional[dict]:
    return dict(r) if r is not None else None


def rows(rs) -> List[dict]:
    return [dict(r) for r in rs]


def like_pattern(q: str) -> str:
    q = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{q}%"


# ---------- Helpers ----------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _load_jwt_secret() -> str:
    env = os.environ.get("JWT_SECRET")
    if env:
        return env
    f = DATA_DIR / "jwt_secret.txt"
    if f.exists():
        return f.read_text().strip()
    s = secrets.token_hex(32)
    f.write_text(s)
    return s


JWT_SECRET = _load_jwt_secret()
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"


def create_access_token(user_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=12),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def today_str() -> str:
    # Local time of the shop computer, so a "day" matches the shop's day.
    return datetime.now().strftime("%Y-%m-%d")


def new_id() -> str:
    return str(uuid.uuid4())


def get_current_user(request: Request, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token")
    user = row(conn.execute(
        "SELECT id, username, name, role, created_at FROM users WHERE id = ?", (payload["sub"],)
    ).fetchone())
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user


# ---------- Models ----------
class LoginIn(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    name: str
    password: str
    role: str = "employee"


class PasswordReset(BaseModel):
    password: str


class UserOut(BaseModel):
    id: str
    username: str
    name: str
    role: str
    created_at: str


class SupplierIn(BaseModel):
    name: str


class SupplierOut(BaseModel):
    id: str
    name: str


class MedicineIn(BaseModel):
    name: str
    company: Optional[str] = ""
    default_supplier_id: Optional[str] = None


class MedicineOut(BaseModel):
    id: str
    name: str
    company: Optional[str] = ""
    default_supplier_id: Optional[str] = None
    default_supplier_name: Optional[str] = None
    # Other suppliers this medicine is also bought from (names), e.g. from Tally bills
    other_suppliers: List[str] = []


class LogCreate(BaseModel):
    medicine_id: Optional[str] = None  # if selected from suggestions
    medicine_name: str  # fallback if new / unknown
    quantity: str


class LogAssignSupplier(BaseModel):
    supplier_id: Optional[str] = None  # None = unassigned
    # Off by default: moving a card never changes the medicine database.
    # When True, the chosen supplier is also saved as the medicine's default
    # (creating the medicine if it was a brand-new, unknown item).
    remember: bool = False


class LogCopy(BaseModel):
    # Where to put the copy: a supplier id, "unassigned", or omitted = same column
    supplier_id: Optional[str] = None


class LogUpdate(BaseModel):
    medicine_name: Optional[str] = None
    quantity: Optional[str] = None


class PasteImport(BaseModel):
    text: str
    delimiter: str = ","


app = FastAPI(title="Stockbook")
api_router = APIRouter(prefix="/api")


@api_router.get("/health")
def health():
    return {"ok": True}


# ---------- Auth ----------
@api_router.post("/auth/login")
def login(payload: LoginIn, response: Response, conn: sqlite3.Connection = Depends(get_db)):
    username = payload.username.strip()
    user = row(conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone())
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token(user["id"], user["role"])
    response.set_cookie(
        key="access_token", value=token, httponly=True, secure=COOKIE_SECURE,
        samesite="lax", max_age=43200, path="/",
    )
    return {
        "id": user["id"],
        "username": user["username"],
        "name": user["name"],
        "role": user["role"],
        "token": token,
    }


@api_router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@api_router.get("/auth/me")
def me(user: dict = Depends(get_current_user)):
    return {"id": user["id"], "username": user["username"], "name": user["name"], "role": user["role"]}


# ---------- Users (Admin) ----------
@api_router.get("/users", response_model=List[UserOut])
def list_users(_: dict = Depends(require_admin), conn: sqlite3.Connection = Depends(get_db)):
    return rows(conn.execute(
        "SELECT id, username, name, role, created_at FROM users ORDER BY name COLLATE NOCASE"
    ))


@api_router.post("/users", response_model=UserOut)
def create_user(payload: UserCreate, _: dict = Depends(require_admin), conn: sqlite3.Connection = Depends(get_db)):
    username = payload.username.strip()
    if not username or not payload.name.strip() or not payload.password:
        raise HTTPException(status_code=400, detail="Name, username and password are required")
    if payload.role not in ("admin", "employee"):
        raise HTTPException(status_code=400, detail="Invalid role")
    if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        raise HTTPException(status_code=400, detail="Username already exists")
    doc = {
        "id": new_id(),
        "username": username,
        "name": payload.name.strip(),
        "role": payload.role,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    conn.execute(
        "INSERT INTO users (id, username, name, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (doc["id"], doc["username"], doc["name"], doc["role"], hash_password(payload.password), doc["created_at"]),
    )
    return doc


@api_router.put("/users/{user_id}/password")
def reset_password(user_id: str, payload: PasswordReset, _: dict = Depends(require_admin), conn: sqlite3.Connection = Depends(get_db)):
    if len(payload.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")
    cur = conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(payload.password), user_id))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


@api_router.delete("/users/{user_id}")
def delete_user(user_id: str, admin: dict = Depends(require_admin), conn: sqlite3.Connection = Depends(get_db)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


# ---------- Suppliers ----------
@api_router.get("/suppliers", response_model=List[SupplierOut])
def list_suppliers(_: dict = Depends(get_current_user), conn: sqlite3.Connection = Depends(get_db)):
    return rows(conn.execute("SELECT id, name FROM suppliers ORDER BY name COLLATE NOCASE"))


def _link_supplier(conn: sqlite3.Connection, medicine_id: Optional[str], supplier_id: Optional[str]):
    if medicine_id and supplier_id:
        conn.execute(
            "INSERT OR IGNORE INTO medicine_suppliers (medicine_id, supplier_id) VALUES (?, ?)",
            (medicine_id, supplier_id),
        )


def _get_or_create_supplier(conn: sqlite3.Connection, name: str) -> Optional[str]:
    name = (name or "").strip()
    if not name:
        return None
    existing = conn.execute("SELECT id FROM suppliers WHERE name = ?", (name,)).fetchone()
    if existing:
        return existing["id"]
    sid = new_id()
    conn.execute("INSERT INTO suppliers (id, name) VALUES (?, ?)", (sid, name))
    return sid


@api_router.post("/suppliers", response_model=SupplierOut)
def create_supplier(payload: SupplierIn, _: dict = Depends(require_admin), conn: sqlite3.Connection = Depends(get_db)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    return {"id": _get_or_create_supplier(conn, name), "name": name}


@api_router.delete("/suppliers/{supplier_id}")
def delete_supplier(supplier_id: str, _: dict = Depends(require_admin), conn: sqlite3.Connection = Depends(get_db)):
    cur = conn.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Supplier not found")
    conn.execute("UPDATE medicines SET default_supplier_id = NULL WHERE default_supplier_id = ?", (supplier_id,))
    conn.execute("DELETE FROM medicine_suppliers WHERE supplier_id = ?", (supplier_id,))
    # Items noted under this supplier move back to Unassigned instead of an orphan column.
    conn.execute("UPDATE logs SET supplier_id = NULL, status = 'unassigned' WHERE supplier_id = ?", (supplier_id,))
    return {"ok": True}


# ---------- Medicines ----------
MEDICINE_SELECT = """
SELECT m.id, m.name, m.company, m.default_supplier_id, s.name AS default_supplier_name
FROM medicines m LEFT JOIN suppliers s ON s.id = m.default_supplier_id
"""


def _supplier_links(conn: sqlite3.Connection, medicine_ids: List[str]) -> dict:
    """medicine_id -> [{id, name}] of every linked supplier, most-bought first."""
    out = {}
    ids = list({i for i in medicine_ids if i})
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        q = ("SELECT ms.medicine_id, s.id, s.name FROM medicine_suppliers ms "
             "JOIN suppliers s ON s.id = ms.supplier_id "
             f"WHERE ms.medicine_id IN ({','.join('?' * len(chunk))}) "
             "ORDER BY ms.bills DESC, ms.last_date DESC, s.name COLLATE NOCASE")
        for r in conn.execute(q, chunk):
            out.setdefault(r["medicine_id"], []).append({"id": r["id"], "name": r["name"]})
    return out


def _with_other_suppliers(conn: sqlite3.Connection, meds: List[dict]) -> List[dict]:
    links = _supplier_links(conn, [m["id"] for m in meds])
    for m in meds:
        m["other_suppliers"] = [s["name"] for s in links.get(m["id"], []) if s["id"] != m.get("default_supplier_id")]
    return meds


def _get_medicine(conn: sqlite3.Connection, medicine_id: str) -> Optional[dict]:
    m = row(conn.execute(MEDICINE_SELECT + " WHERE m.id = ?", (medicine_id,)).fetchone())
    return _with_other_suppliers(conn, [m])[0] if m else None


@api_router.get("/medicines", response_model=List[MedicineOut])
def list_medicines(q: Optional[str] = None, limit: int = 500, _: dict = Depends(get_current_user), conn: sqlite3.Connection = Depends(get_db)):
    sql, params = MEDICINE_SELECT, []
    if q and q.strip():
        pat = like_pattern(q)
        sql += " WHERE m.name LIKE ? ESCAPE '\\' OR m.company LIKE ? ESCAPE '\\'"
        params += [pat, pat]
    sql += " ORDER BY m.name COLLATE NOCASE LIMIT ?"
    params.append(max(1, min(limit, 20000)))
    return _with_other_suppliers(conn, rows(conn.execute(sql, params)))


@api_router.get("/medicines/suggest")
def suggest_medicines(q: str = "", user: dict = Depends(get_current_user), conn: sqlite3.Connection = Depends(get_db)):
    if not q.strip():
        return []
    pat = like_pattern(q)
    found = rows(conn.execute(
        "SELECT id, name, company, default_supplier_id FROM medicines "
        "WHERE name LIKE ? ESCAPE '\\' OR company LIKE ? ESCAPE '\\' "
        "ORDER BY name COLLATE NOCASE LIMIT 15",
        (pat, pat),
    ))
    # Employees never see supplier info
    if user.get("role") != "admin":
        for f in found:
            f.pop("default_supplier_id", None)
    return found


@api_router.post("/medicines", response_model=MedicineOut)
def create_medicine(payload: MedicineIn, _: dict = Depends(require_admin), conn: sqlite3.Connection = Depends(get_db)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    mid = new_id()
    conn.execute(
        "INSERT INTO medicines (id, name, company, default_supplier_id) VALUES (?, ?, ?, ?)",
        (mid, name, (payload.company or "").strip(), payload.default_supplier_id),
    )
    _link_supplier(conn, mid, payload.default_supplier_id)
    return _get_medicine(conn, mid)


@api_router.put("/medicines/{medicine_id}", response_model=MedicineOut)
def update_medicine(medicine_id: str, payload: MedicineIn, _: dict = Depends(require_admin), conn: sqlite3.Connection = Depends(get_db)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    cur = conn.execute(
        "UPDATE medicines SET name = ?, company = ?, default_supplier_id = ? WHERE id = ?",
        (name, (payload.company or "").strip(), payload.default_supplier_id, medicine_id),
    )
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Not found")
    _link_supplier(conn, medicine_id, payload.default_supplier_id)
    return _get_medicine(conn, medicine_id)


@api_router.delete("/medicines/{medicine_id}")
def delete_medicine(medicine_id: str, _: dict = Depends(require_admin), conn: sqlite3.Connection = Depends(get_db)):
    cur = conn.execute("DELETE FROM medicines WHERE id = ?", (medicine_id,))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Not found")
    conn.execute("DELETE FROM medicine_suppliers WHERE medicine_id = ?", (medicine_id,))
    return {"ok": True}


def _cell(v) -> str:
    return "" if v is None else str(v).strip()


def _import_rows(conn: sqlite3.Connection, data: list) -> dict:
    """data: list of dicts with keys name/medicine_name, company, supplier/default_supplier."""
    added, updated, skipped = 0, 0, 0
    for r in data:
        name = _cell(r.get("name") or r.get("medicine_name") or r.get("Medicine Name") or r.get("Name"))
        if not name:
            skipped += 1
            continue
        company = _cell(r.get("company") or r.get("Company"))
        sup_name = _cell(r.get("supplier") or r.get("default_supplier") or r.get("Default Supplier") or r.get("Supplier"))
        supplier_id = _get_or_create_supplier(conn, sup_name) if sup_name else None
        existing = conn.execute(
            "SELECT id, default_supplier_id FROM medicines WHERE name = ? AND company = ?", (name, company)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE medicines SET default_supplier_id = ? WHERE id = ?",
                (supplier_id or existing["default_supplier_id"], existing["id"]),
            )
            _link_supplier(conn, existing["id"], supplier_id)
            updated += 1
        else:
            mid = new_id()
            conn.execute(
                "INSERT INTO medicines (id, name, company, default_supplier_id) VALUES (?, ?, ?, ?)",
                (mid, name, company, supplier_id),
            )
            _link_supplier(conn, mid, supplier_id)
            added += 1
    return {"added": added, "updated": updated, "skipped": skipped}


@api_router.post("/medicines/import/csv")
def import_csv(file: UploadFile = File(...), _: dict = Depends(require_admin), conn: sqlite3.Connection = Depends(get_db)):
    text = file.file.read().decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    return _import_rows(conn, [dict(r) for r in reader])


@api_router.post("/medicines/import/xlsx")
def import_xlsx(file: UploadFile = File(...), _: dict = Depends(require_admin), conn: sqlite3.Connection = Depends(get_db)):
    from openpyxl import load_workbook
    wb = load_workbook(filename=io.BytesIO(file.file.read()), data_only=True, read_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        headers = [_cell(h) for h in next(rows_iter)]
    except StopIteration:
        return {"added": 0, "updated": 0, "skipped": 0}
    data = [{headers[i]: (r[i] if i < len(r) else "") for i in range(len(headers))} for r in rows_iter]
    return _import_rows(conn, data)


@api_router.post("/medicines/import/paste")
def import_paste(payload: PasteImport, _: dict = Depends(require_admin), conn: sqlite3.Connection = Depends(get_db)):
    lines = [l for l in payload.text.splitlines() if l.strip()]
    if not lines:
        return {"added": 0, "updated": 0, "skipped": 0}
    all_rows = list(csv.reader(lines, delimiter=payload.delimiter or ","))
    header_candidates = [c.lower().strip() for c in all_rows[0]]
    header_keys = {"name", "medicine name", "medicine_name", "company", "supplier", "default supplier", "default_supplier"}
    if any(h in header_keys for h in header_candidates):
        headers = [h.strip() for h in all_rows[0]]
        data_rows = all_rows[1:]
    else:
        headers = ["name", "company", "supplier"]
        data_rows = all_rows
    data = [{headers[i]: (r[i] if i < len(r) else "") for i in range(len(headers))} for r in data_rows]
    return _import_rows(conn, data)


@api_router.post("/medicines/import/tally")
def import_tally(
    file: UploadFile = File(...),
    update_defaults: bool = Form(False),
    _: dict = Depends(require_admin),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Learn which items come from which party, from Tally Prime purchase bills (XML export).

    Every party an item was bought from is remembered. The default supplier is
    only set for items that don't have one yet, unless update_defaults is on;
    then it becomes the party with the most bills.
    """
    raw = file.file.read()
    try:
        bills = list(parse_purchase_bills(raw))
    except Exception as e:  # malformed / not a Tally XML file
        logger.warning("Tally import failed: %s", e)
        raise HTTPException(status_code=400, detail="Could not read this file. Please export from Tally as XML (Data Interchange).")
    if not bills:
        raise HTTPException(status_code=400, detail="No purchase bills with items were found in this file.")

    result = {"bills_found": len(bills), "bills_new": 0, "bills_already_imported": 0,
              "new_medicines": 0, "new_suppliers": 0, "links": 0, "defaults_set": 0}
    known_suppliers = {r["name"] for r in conn.execute("SELECT name FROM suppliers")}
    touched = set()
    now = datetime.now(timezone.utc).isoformat()
    for bill in bills:
        if conn.execute("SELECT 1 FROM tally_bills WHERE key = ?", (bill.key,)).fetchone():
            result["bills_already_imported"] += 1
            continue
        conn.execute("INSERT INTO tally_bills (key, imported_at) VALUES (?, ?)", (bill.key, now))
        result["bills_new"] += 1
        if bill.party not in known_suppliers:
            known_suppliers.add(bill.party)
            result["new_suppliers"] += 1
        sid = _get_or_create_supplier(conn, bill.party)
        for item in bill.items:
            med = conn.execute("SELECT id FROM medicines WHERE name = ? COLLATE NOCASE LIMIT 1", (item,)).fetchone()
            if med:
                mid = med["id"]
            else:
                mid = new_id()
                conn.execute("INSERT INTO medicines (id, name, company, default_supplier_id) VALUES (?, ?, '', NULL)", (mid, item))
                result["new_medicines"] += 1
            existed = conn.execute(
                "SELECT 1 FROM medicine_suppliers WHERE medicine_id = ? AND supplier_id = ?", (mid, sid)
            ).fetchone()
            if existed:
                conn.execute(
                    "UPDATE medicine_suppliers SET bills = bills + 1, last_date = MAX(last_date, ?) "
                    "WHERE medicine_id = ? AND supplier_id = ?", (bill.date, mid, sid))
            else:
                conn.execute(
                    "INSERT INTO medicine_suppliers (medicine_id, supplier_id, bills, last_date) VALUES (?, ?, 1, ?)",
                    (mid, sid, bill.date))
                result["links"] += 1
            touched.add(mid)

    for mid in touched:
        current = conn.execute("SELECT default_supplier_id FROM medicines WHERE id = ?", (mid,)).fetchone()
        if current["default_supplier_id"] and not update_defaults:
            continue
        top = conn.execute(
            "SELECT supplier_id FROM medicine_suppliers WHERE medicine_id = ? "
            "ORDER BY bills DESC, last_date DESC LIMIT 1", (mid,)
        ).fetchone()
        if top and top["supplier_id"] != current["default_supplier_id"]:
            conn.execute("UPDATE medicines SET default_supplier_id = ? WHERE id = ?", (top["supplier_id"], mid))
            result["defaults_set"] += 1
    return result


# ---------- Logs (daily short-item notes) ----------
def _add_alt_suppliers(conn: sqlite3.Connection, logs: List[dict]) -> List[dict]:
    """Admin only: the other suppliers this medicine can also be ordered from."""
    links = _supplier_links(conn, [l["medicine_id"] for l in logs])
    for l in logs:
        l["alt_suppliers"] = [s for s in links.get(l["medicine_id"], []) if s["id"] != l["supplier_id"]]
    return logs


def _get_log(conn: sqlite3.Connection, log_id: str) -> Optional[dict]:
    return row(conn.execute("SELECT * FROM logs WHERE id = ?", (log_id,)).fetchone())


@api_router.post("/logs")
def create_log(payload: LogCreate, user: dict = Depends(get_current_user), conn: sqlite3.Connection = Depends(get_db)):
    name = payload.medicine_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Medicine name required")
    med = None
    if payload.medicine_id:
        med = conn.execute("SELECT * FROM medicines WHERE id = ?", (payload.medicine_id,)).fetchone()
    if med is None:
        # Try an exact (case-insensitive) name match
        med = conn.execute("SELECT * FROM medicines WHERE name = ? COLLATE NOCASE LIMIT 1", (name,)).fetchone()
    medicine_id, company, supplier_id = None, "", None
    if med is not None:
        medicine_id, name, company, supplier_id = med["id"], med["name"], med["company"] or "", med["default_supplier_id"]

    doc = {
        "id": new_id(),
        "medicine_id": medicine_id,
        "medicine_name": name,
        "company": company,
        "quantity": payload.quantity.strip(),
        "supplier_id": supplier_id,
        "date": today_str(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "added_by_id": user["id"],
        "added_by_name": user["name"],
        "status": "assigned" if supplier_id else "unassigned",
    }
    cols = ", ".join(doc.keys())
    conn.execute(f"INSERT INTO logs ({cols}) VALUES ({', '.join('?' * len(doc))})", list(doc.values()))
    return doc


@api_router.get("/logs")
def list_logs(date: Optional[str] = None, user: dict = Depends(get_current_user), conn: sqlite3.Connection = Depends(get_db)):
    sql, params = "SELECT * FROM logs WHERE date = ?", [date or today_str()]
    if user.get("role") != "admin":
        sql += " AND added_by_id = ?"
        params.append(user["id"])
    found = rows(conn.execute(sql + " ORDER BY created_at DESC", params))
    if user.get("role") == "admin":
        _add_alt_suppliers(conn, found)
    else:
        # Employees never see supplier info
        for f in found:
            f.pop("supplier_id", None)
            f.pop("status", None)
    return found


@api_router.put("/logs/{log_id}/assign")
def assign_log_supplier(log_id: str, payload: LogAssignSupplier, _: dict = Depends(require_admin), conn: sqlite3.Connection = Depends(get_db)):
    log = _get_log(conn, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Not found")
    medicine_id = log["medicine_id"]
    if payload.remember and payload.supplier_id:
        if medicine_id and conn.execute("SELECT 1 FROM medicines WHERE id = ?", (medicine_id,)).fetchone():
            conn.execute("UPDATE medicines SET default_supplier_id = ? WHERE id = ?", (payload.supplier_id, medicine_id))
        else:
            medicine_id = new_id()
            conn.execute(
                "INSERT INTO medicines (id, name, company, default_supplier_id) VALUES (?, ?, ?, ?)",
                (medicine_id, log["medicine_name"], log["company"] or "", payload.supplier_id),
            )
        _link_supplier(conn, medicine_id, payload.supplier_id)
    conn.execute(
        "UPDATE logs SET supplier_id = ?, status = ?, medicine_id = ? WHERE id = ?",
        (payload.supplier_id, "assigned" if payload.supplier_id else "unassigned", medicine_id, log_id),
    )
    return _add_alt_suppliers(conn, [_get_log(conn, log_id)])[0]


@api_router.put("/logs/{log_id}")
def update_log(log_id: str, payload: LogUpdate, _: dict = Depends(require_admin), conn: sqlite3.Connection = Depends(get_db)):
    upd = {}
    if payload.medicine_name is not None:
        name = payload.medicine_name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Medicine name required")
        upd["medicine_name"] = name
    if payload.quantity is not None:
        upd["quantity"] = payload.quantity.strip()
    if not upd:
        raise HTTPException(status_code=400, detail="Nothing to update")
    sets = ", ".join(f"{k} = ?" for k in upd)
    cur = conn.execute(f"UPDATE logs SET {sets} WHERE id = ?", list(upd.values()) + [log_id])
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return _add_alt_suppliers(conn, [_get_log(conn, log_id)])[0]


@api_router.post("/logs/{log_id}/copy")
def copy_log(log_id: str, payload: LogCopy, _: dict = Depends(require_admin), conn: sqlite3.Connection = Depends(get_db)):
    """Duplicate an entry, e.g. to order the same medicine from a second supplier.
    A copy never changes the medicine's default supplier."""
    log = _get_log(conn, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Not found")
    if payload.supplier_id is None:
        supplier_id = log["supplier_id"]
    elif payload.supplier_id == UNASSIGNED:
        supplier_id = None
    else:
        if not conn.execute("SELECT 1 FROM suppliers WHERE id = ?", (payload.supplier_id,)).fetchone():
            raise HTTPException(status_code=400, detail="Supplier not found")
        supplier_id = payload.supplier_id
    doc = dict(log)
    doc.update({
        "id": new_id(),
        "supplier_id": supplier_id,
        "status": "assigned" if supplier_id else "unassigned",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    cols = ", ".join(doc.keys())
    conn.execute(f"INSERT INTO logs ({cols}) VALUES ({', '.join('?' * len(doc))})", list(doc.values()))
    return _add_alt_suppliers(conn, [doc])[0]


def _log_filter(date: Optional[str], supplier_id: Optional[str]):
    sql, params = "date = ?", [date or today_str()]
    if supplier_id == UNASSIGNED:
        sql += " AND supplier_id IS NULL"
    elif supplier_id:
        sql += " AND supplier_id = ?"
        params.append(supplier_id)
    return sql, params


@api_router.delete("/logs")
def delete_logs_bulk(date: Optional[str] = None, supplier_id: Optional[str] = None, _: dict = Depends(require_admin), conn: sqlite3.Connection = Depends(get_db)):
    """Delete every note for a day, or only those under one supplier
    (supplier_id='unassigned' targets the Unassigned column)."""
    where, params = _log_filter(date, supplier_id)
    cur = conn.execute(f"DELETE FROM logs WHERE {where}", params)
    return {"deleted": cur.rowcount}


@api_router.delete("/logs/{log_id}")
def delete_log(log_id: str, user: dict = Depends(get_current_user), conn: sqlite3.Connection = Depends(get_db)):
    sql, params = "DELETE FROM logs WHERE id = ?", [log_id]
    if user.get("role") != "admin":
        sql += " AND added_by_id = ?"
        params.append(user["id"])
    if conn.execute(sql, params).rowcount == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


# ---------- Export ----------
def _grouped_logs(conn: sqlite3.Connection, date: Optional[str], supplier_id: Optional[str]):
    where, params = _log_filter(date, supplier_id)
    logs = rows(conn.execute(f"SELECT * FROM logs WHERE {where} ORDER BY created_at", params))
    suppliers = {s["id"]: s["name"] for s in rows(conn.execute("SELECT id, name FROM suppliers"))}
    grouped = {}
    for l in logs:
        grouped.setdefault(l["supplier_id"] or UNASSIGNED, []).append(l)
    named = []
    for sid, items in grouped.items():
        named.append(("Unassigned" if sid == UNASSIGNED else suppliers.get(sid, "Unknown"), items))
    return named


@api_router.get("/logs/export/text")
def export_text(date: Optional[str] = None, supplier_id: Optional[str] = None, _: dict = Depends(require_admin), conn: sqlite3.Connection = Depends(get_db)):
    d = date or today_str()
    lines = [f"Order List — {d}", ""]
    for sup_name, items in _grouped_logs(conn, d, supplier_id):
        lines.append(f"*{sup_name}*")
        for i, it in enumerate(items, 1):
            comp = f" ({it['company']})" if it.get("company") else ""
            lines.append(f"{i}. {it['medicine_name']}{comp} — Qty left: {it.get('quantity', '')}")
        lines.append("")
    return {"text": "\n".join(lines)}


@api_router.get("/logs/export/pdf")
def export_pdf(date: Optional[str] = None, supplier_id: Optional[str] = None, _: dict = Depends(require_admin), conn: sqlite3.Connection = Depends(get_db)):
    d = date or today_str()
    grouped = _grouped_logs(conn, d, supplier_id)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm, leftMargin=1.5 * cm, rightMargin=1.5 * cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title", parent=styles["Title"], textColor=colors.HexColor("#4A5D4E"), fontSize=22, spaceAfter=12)
    section_style = ParagraphStyle("Section", parent=styles["Heading2"], textColor=colors.HexColor("#2C312E"), fontSize=14, spaceBefore=14, spaceAfter=6)
    story = [Paragraph("Daily Order List", title_style), Paragraph(f"Date: {d}", styles["Normal"]), Spacer(1, 0.4 * cm)]

    for sup_name, items in grouped:
        story.append(Paragraph(xml_escape(sup_name), section_style))
        data = [["#", "Medicine", "Company", "Qty left"]]
        for i, it in enumerate(items, 1):
            data.append([str(i), it["medicine_name"], it.get("company", ""), it.get("quantity", "")])
        t = Table(data, colWidths=[1 * cm, 8 * cm, 5 * cm, 4 * cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4A5D4E")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F9F8F6"), colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E1DB")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(t)

    if not grouped:
        story.append(Paragraph("No items noted on this date.", styles["Normal"]))

    doc.build(story)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=order-list-{d}.pdf"})


# ---------- Startup ----------
def seed_admin():
    """Create the first admin account if there are no users yet."""
    with open_db() as conn:
        if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return
        username = (os.environ.get("ADMIN_USERNAME") or "admin").strip()
        password = os.environ.get("ADMIN_PASSWORD")
        note = ""
        if not password:
            password = secrets.token_urlsafe(8)
            note = f"Username: {username}\nPassword: {password}\n"
            (DATA_DIR / "FIRST_LOGIN.txt").write_text(
                "Stockbook first admin login (delete this file after you change the password)\n" + note
            )
        conn.execute(
            "INSERT INTO users (id, username, name, role, password_hash, created_at) VALUES (?, ?, ?, 'admin', ?, ?)",
            (new_id(), username, "Admin", hash_password(password), datetime.now(timezone.utc).isoformat()),
        )
        logger.info("Created first admin user '%s'%s", username, " — see data/FIRST_LOGIN.txt" if note else "")


@app.on_event("startup")
def on_startup():
    init_db()
    seed_admin()
    logger.info("Data file: %s", DB_PATH)


app.include_router(api_router)

# Only needed when running the React dev server separately (npm start).
_cors = os.environ.get("CORS_ORIGINS")
if _cors:
    from starlette.middleware.cors import CORSMiddleware
    app.add_middleware(CORSMiddleware, allow_origins=_cors.split(","), allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])

# ---------- Serve the built web app ----------
if (FRONTEND_DIR / "index.html").exists():
    if (FRONTEND_DIR / "static").is_dir():
        app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (FRONTEND_DIR / full_path).resolve()
        if full_path and candidate.is_file() and FRONTEND_DIR.resolve() in candidate.parents:
            return FileResponse(str(candidate))
        return FileResponse(str(FRONTEND_DIR / "index.html"))
else:
    logger.warning("No built web app found in %s — only the API is available.", FRONTEND_DIR)
