from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import io
import re
import csv
import uuid
import logging
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

JWT_ALGORITHM = "HS256"
UNASSIGNED = "unassigned"

# ---------- Mongo ----------
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---------- Helpers ----------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]

def create_access_token(user_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=12),
        "type": "access",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def new_id() -> str:
    return str(uuid.uuid4())

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token")
        user = await db.users.find_one({"id": payload["sub"]})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user.pop("_id", None)
        user.pop("password_hash", None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user

# ---------- Models ----------
class LoginIn(BaseModel):
    email: EmailStr
    password: str

class UserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str
    role: str = "employee"

class UserOut(BaseModel):
    id: str
    email: str
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

class LogUpdate(BaseModel):
    medicine_name: Optional[str] = None
    quantity: Optional[str] = None

class PasteImport(BaseModel):
    text: str
    delimiter: str = ","

# ---------- Auth Endpoints ----------
@api_router.post("/auth/login")
async def login(payload: LoginIn, response: Response):
    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user["id"], user["role"])
    response.set_cookie(
        key="access_token", value=token, httponly=True, secure=True,
        samesite="none", max_age=43200, path="/"
    )
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "token": token,
    }

@api_router.post("/auth/logout")
async def logout(response: Response, _: dict = Depends(get_current_user)):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}

@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return {
        "id": user["id"], "email": user["email"], "name": user["name"], "role": user["role"]
    }

# ---------- Users (Admin) ----------
@api_router.get("/users", response_model=List[UserOut])
async def list_users(_: dict = Depends(require_admin)):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(1000)
    return users

@api_router.post("/users", response_model=UserOut)
async def create_user(payload: UserCreate, _: dict = Depends(require_admin)):
    email = payload.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already exists")
    if payload.role not in ("admin", "employee"):
        raise HTTPException(status_code=400, detail="Invalid role")
    user_doc = {
        "id": new_id(),
        "email": email,
        "name": payload.name.strip(),
        "role": payload.role,
        "password_hash": hash_password(payload.password),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(user_doc)
    user_doc.pop("password_hash")
    user_doc.pop("_id", None)
    return user_doc

@api_router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin: dict = Depends(require_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    res = await db.users.delete_one({"id": user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}

# ---------- Suppliers ----------
@api_router.get("/suppliers", response_model=List[SupplierOut])
async def list_suppliers(_: dict = Depends(get_current_user)):
    docs = await db.suppliers.find({}, {"_id": 0}).sort("name", 1).to_list(1000)
    return docs

@api_router.post("/suppliers", response_model=SupplierOut)
async def create_supplier(payload: SupplierIn, _: dict = Depends(require_admin)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    existing = await db.suppliers.find_one({"name": name})
    if existing:
        existing.pop("_id", None)
        return existing
    doc = {"id": new_id(), "name": name}
    await db.suppliers.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.delete("/suppliers/{supplier_id}")
async def delete_supplier(supplier_id: str, _: dict = Depends(require_admin)):
    res = await db.suppliers.delete_one({"id": supplier_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Supplier not found")
    # Clear default_supplier_id from medicines and current-day logs stays assigned but ok
    await db.medicines.update_many({"default_supplier_id": supplier_id}, {"$set": {"default_supplier_id": None}})
    return {"ok": True}

# ---------- Medicines ----------
async def _decorate_medicine(m: dict) -> dict:
    m.pop("_id", None)
    if m.get("default_supplier_id"):
        sup = await db.suppliers.find_one({"id": m["default_supplier_id"]}, {"_id": 0, "name": 1})
        m["default_supplier_name"] = sup["name"] if sup else None
    else:
        m["default_supplier_name"] = None
    return m

@api_router.get("/medicines", response_model=List[MedicineOut])
async def list_medicines(q: Optional[str] = None, limit: int = 500, _: dict = Depends(get_current_user)):
    query = {}
    if q:
        pat = re.escape(q.strip())
        query = {"$or": [
            {"name": {"$regex": pat, "$options": "i"}},
            {"company": {"$regex": pat, "$options": "i"}},
        ]}
    docs = await db.medicines.find(query).sort("name", 1).to_list(limit)
    out = []
    for d in docs:
        out.append(await _decorate_medicine(d))
    return out

@api_router.get("/medicines/suggest")
async def suggest_medicines(q: str, user: dict = Depends(get_current_user)):
    if not q or len(q.strip()) < 1:
        return []
    pat = re.escape(q.strip())
    docs = await db.medicines.find(
        {"$or": [
            {"name": {"$regex": pat, "$options": "i"}},
            {"company": {"$regex": pat, "$options": "i"}},
        ]}
    ).limit(15).to_list(15)
    # Employees never see supplier info
    is_admin = user.get("role") == "admin"
    out = []
    for d in docs:
        item = {"id": d["id"], "name": d["name"], "company": d.get("company", "")}
        if is_admin:
            item["default_supplier_id"] = d.get("default_supplier_id")
        out.append(item)
    return out

@api_router.post("/medicines", response_model=MedicineOut)
async def create_medicine(payload: MedicineIn, _: dict = Depends(require_admin)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    doc = {
        "id": new_id(),
        "name": name,
        "company": (payload.company or "").strip(),
        "default_supplier_id": payload.default_supplier_id,
    }
    await db.medicines.insert_one(doc)
    return await _decorate_medicine(doc)

@api_router.put("/medicines/{medicine_id}", response_model=MedicineOut)
async def update_medicine(medicine_id: str, payload: MedicineIn, _: dict = Depends(require_admin)):
    upd = {
        "name": payload.name.strip(),
        "company": (payload.company or "").strip(),
        "default_supplier_id": payload.default_supplier_id,
    }
    res = await db.medicines.update_one({"id": medicine_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    doc = await db.medicines.find_one({"id": medicine_id})
    return await _decorate_medicine(doc)

@api_router.delete("/medicines/{medicine_id}")
async def delete_medicine(medicine_id: str, _: dict = Depends(require_admin)):
    res = await db.medicines.delete_one({"id": medicine_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}

async def _get_or_create_supplier(name: str) -> Optional[str]:
    if not name:
        return None
    name = name.strip()
    if not name:
        return None
    existing = await db.suppliers.find_one({"name": name})
    if existing:
        return existing["id"]
    sup = {"id": new_id(), "name": name}
    await db.suppliers.insert_one(sup)
    return sup["id"]

async def _import_rows(rows: list) -> dict:
    """rows: list of dicts with keys medicine_name/name, company, supplier/default_supplier"""
    added, updated, skipped = 0, 0, 0
    for r in rows:
        name = (r.get("name") or r.get("medicine_name") or r.get("Medicine Name") or "").strip()
        if not name:
            skipped += 1
            continue
        company = (r.get("company") or r.get("Company") or "").strip()
        sup_name = (r.get("supplier") or r.get("default_supplier") or r.get("Default Supplier") or r.get("Supplier") or "").strip()
        supplier_id = await _get_or_create_supplier(sup_name) if sup_name else None
        existing = await db.medicines.find_one({"name": name, "company": company})
        if existing:
            await db.medicines.update_one(
                {"id": existing["id"]},
                {"$set": {"default_supplier_id": supplier_id or existing.get("default_supplier_id")}},
            )
            updated += 1
        else:
            doc = {"id": new_id(), "name": name, "company": company, "default_supplier_id": supplier_id}
            await db.medicines.insert_one(doc)
            added += 1
    return {"added": added, "updated": updated, "skipped": skipped}

@api_router.post("/medicines/import/csv")
async def import_csv(file: UploadFile = File(...), _: dict = Depends(require_admin)):
    content = await file.read()
    text = content.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    rows = [dict(r) for r in reader]
    result = await _import_rows(rows)
    return result

@api_router.post("/medicines/import/xlsx")
async def import_xlsx(file: UploadFile = File(...), _: dict = Depends(require_admin)):
    from openpyxl import load_workbook
    content = await file.read()
    wb = load_workbook(filename=io.BytesIO(content), data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        headers = [str(h or "").strip() for h in next(rows_iter)]
    except StopIteration:
        return {"added": 0, "updated": 0, "skipped": 0}
    rows = []
    for r in rows_iter:
        rows.append({headers[i]: (r[i] if i < len(r) else "") for i in range(len(headers))})
    result = await _import_rows(rows)
    return result

@api_router.post("/medicines/import/paste")
async def import_paste(payload: PasteImport, _: dict = Depends(require_admin)):
    lines = [l for l in payload.text.splitlines() if l.strip()]
    if not lines:
        return {"added": 0, "updated": 0, "skipped": 0}
    delim = payload.delimiter or ","
    reader = csv.reader(lines, delimiter=delim)
    all_rows = list(reader)
    # Detect header
    header_candidates = [c.lower().strip() for c in all_rows[0]]
    header_keys = {"name", "medicine name", "medicine_name", "company", "supplier", "default supplier", "default_supplier"}
    if any(h in header_keys for h in header_candidates):
        headers = [h.strip() for h in all_rows[0]]
        data_rows = all_rows[1:]
    else:
        headers = ["name", "company", "supplier"]
        data_rows = all_rows
    rows = []
    for r in data_rows:
        rows.append({headers[i]: (r[i] if i < len(r) else "") for i in range(len(headers))})
    result = await _import_rows(rows)
    return result

# ---------- Logs (Daily notes) ----------
@api_router.post("/logs")
async def create_log(payload: LogCreate, user: dict = Depends(get_current_user)):
    name = payload.medicine_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Medicine name required")
    quantity = payload.quantity.strip()
    supplier_id = None
    medicine_id = payload.medicine_id
    company = ""
    if medicine_id:
        med = await db.medicines.find_one({"id": medicine_id})
        if med:
            name = med["name"]
            company = med.get("company", "")
            supplier_id = med.get("default_supplier_id")
    else:
        # Try to match by name
        med = await db.medicines.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}})
        if med:
            medicine_id = med["id"]
            name = med["name"]
            company = med.get("company", "")
            supplier_id = med.get("default_supplier_id")

    doc = {
        "id": new_id(),
        "medicine_id": medicine_id,
        "medicine_name": name,
        "company": company,
        "quantity": quantity,
        "supplier_id": supplier_id,
        "date": today_str(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "added_by_id": user["id"],
        "added_by_name": user["name"],
        "status": "assigned" if supplier_id else "unassigned",
    }
    await db.logs.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.get("/logs")
async def list_logs(date: Optional[str] = None, user: dict = Depends(get_current_user)):
    d = date or today_str()
    query = {"date": d}
    if user.get("role") != "admin":
        query["added_by_id"] = user["id"]
    docs = await db.logs.find(query, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return docs

@api_router.put("/logs/{log_id}/assign")
async def assign_log_supplier(log_id: str, payload: LogAssignSupplier, _: dict = Depends(require_admin)):
    log = await db.logs.find_one({"id": log_id})
    if not log:
        raise HTTPException(status_code=404, detail="Not found")
    upd = {
        "supplier_id": payload.supplier_id,
        "status": "assigned" if payload.supplier_id else "unassigned",
    }
    if payload.remember and payload.supplier_id:
        if log.get("medicine_id") and await db.medicines.find_one({"id": log["medicine_id"]}):
            await db.medicines.update_one(
                {"id": log["medicine_id"]}, {"$set": {"default_supplier_id": payload.supplier_id}}
            )
        else:
            med = {
                "id": new_id(),
                "name": log["medicine_name"],
                "company": log.get("company", ""),
                "default_supplier_id": payload.supplier_id,
            }
            await db.medicines.insert_one(med)
            upd["medicine_id"] = med["id"]
    await db.logs.update_one({"id": log_id}, {"$set": upd})
    doc = await db.logs.find_one({"id": log_id}, {"_id": 0})
    return doc

@api_router.put("/logs/{log_id}")
async def update_log(log_id: str, payload: LogUpdate, _: dict = Depends(require_admin)):
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
    res = await db.logs.update_one({"id": log_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return await db.logs.find_one({"id": log_id}, {"_id": 0})

@api_router.delete("/logs")
async def delete_logs_bulk(date: Optional[str] = None, supplier_id: Optional[str] = None, _: dict = Depends(require_admin)):
    """Delete every note for a day, or only those under one supplier
    (supplier_id='unassigned' targets the Unassigned column)."""
    q = {"date": date or today_str()}
    if supplier_id:
        q["supplier_id"] = None if supplier_id == UNASSIGNED else supplier_id
    res = await db.logs.delete_many(q)
    return {"deleted": res.deleted_count}

@api_router.delete("/logs/{log_id}")
async def delete_log(log_id: str, user: dict = Depends(get_current_user)):
    q = {"id": log_id}
    if user.get("role") != "admin":
        q["added_by_id"] = user["id"]
    res = await db.logs.delete_one(q)
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}

# ---------- Export ----------
@api_router.get("/logs/export/text")
async def export_text(date: Optional[str] = None, supplier_id: Optional[str] = None, _: dict = Depends(require_admin)):
    d = date or today_str()
    q = {"date": d}
    if supplier_id:
        q["supplier_id"] = None if supplier_id == UNASSIGNED else supplier_id
    logs = await db.logs.find(q, {"_id": 0}).to_list(5000)
    suppliers = {s["id"]: s["name"] for s in await db.suppliers.find({}, {"_id": 0}).to_list(1000)}

    # Group
    grouped = {}
    for l in logs:
        sid = l.get("supplier_id") or UNASSIGNED
        grouped.setdefault(sid, []).append(l)

    lines = [f"Order List — {d}", ""]
    for sid, items in grouped.items():
        sup_name = "Unassigned" if sid == UNASSIGNED else suppliers.get(sid, "Unknown")
        lines.append(f"*{sup_name}*")
        for i, it in enumerate(items, 1):
            comp = f" ({it['company']})" if it.get("company") else ""
            lines.append(f"{i}. {it['medicine_name']}{comp} — Qty left: {it.get('quantity', '')}")
        lines.append("")
    return {"text": "\n".join(lines)}

@api_router.get("/logs/export/pdf")
async def export_pdf(date: Optional[str] = None, supplier_id: Optional[str] = None, _: dict = Depends(require_admin)):
    d = date or today_str()
    q = {"date": d}
    if supplier_id:
        q["supplier_id"] = None if supplier_id == UNASSIGNED else supplier_id
    logs = await db.logs.find(q, {"_id": 0}).sort("supplier_id", 1).to_list(5000)
    suppliers = {s["id"]: s["name"] for s in await db.suppliers.find({}, {"_id": 0}).to_list(1000)}

    grouped = {}
    for l in logs:
        sid = l.get("supplier_id") or UNASSIGNED
        grouped.setdefault(sid, []).append(l)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.5*cm, bottomMargin=1.5*cm, leftMargin=1.5*cm, rightMargin=1.5*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title", parent=styles["Title"], textColor=colors.HexColor("#4A5D4E"), fontSize=22, spaceAfter=12)
    section_style = ParagraphStyle("Section", parent=styles["Heading2"], textColor=colors.HexColor("#2C312E"), fontSize=14, spaceBefore=14, spaceAfter=6)
    story = []
    story.append(Paragraph(f"Daily Order List", title_style))
    story.append(Paragraph(f"Date: {d}", styles["Normal"]))
    story.append(Spacer(1, 0.4*cm))

    for sid, items in grouped.items():
        sup_name = "Unassigned" if sid == UNASSIGNED else suppliers.get(sid, "Unknown")
        story.append(Paragraph(sup_name, section_style))
        data = [["#", "Medicine", "Company", "Qty left"]]
        for i, it in enumerate(items, 1):
            data.append([str(i), it["medicine_name"], it.get("company", ""), it.get("quantity", "")])
        t = Table(data, colWidths=[1*cm, 8*cm, 5*cm, 4*cm])
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
    fname = f"order-list-{d}.pdf"
    return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={fname}"})

# ---------- Startup ----------
async def seed_admin():
    email = os.environ.get("ADMIN_EMAIL", "admin@example.com").lower()
    password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": email})
    if existing is None:
        await db.users.insert_one({
            "id": new_id(),
            "email": email,
            "name": "Admin",
            "role": "admin",
            "password_hash": hash_password(password),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(f"Seeded admin user {email}")
    elif not verify_password(password, existing["password_hash"]):
        await db.users.update_one({"email": email}, {"$set": {"password_hash": hash_password(password)}})
        logger.info(f"Updated admin password for {email}")

@app.on_event("startup")
async def on_startup():
    await db.users.create_index("email", unique=True)
    await db.medicines.create_index("name")
    await db.suppliers.create_index("name", unique=True)
    await db.logs.create_index("date")
    await db.logs.create_index("supplier_id")
    await seed_admin()

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

app.include_router(api_router)

# CORS
frontend_url = os.environ.get("FRONTEND_URL", "*")
cors_origins_env = os.environ.get("CORS_ORIGINS", "*")
if cors_origins_env == "*":
    allow_origins = ["*"]
else:
    allow_origins = cors_origins_env.split(",")
if frontend_url and frontend_url != "*" and frontend_url not in allow_origins:
    allow_origins.append(frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
