"""End-to-end API tests for the self-hosted (SQLite) Stockbook backend.

Run from the backend folder:  python -m pytest
"""
import io
import sys
import importlib
from pathlib import Path

import openpyxl
from fastapi.testclient import TestClient


def test_full_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKBOOK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ADMIN_USERNAME", "papa")
    monkeypatch.setenv("ADMIN_PASSWORD", "pw1234")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import server
    server = importlib.reload(server)

    def ok(name, cond):
        assert cond, name

    with TestClient(server.app) as c:
        H=lambda t:{"Authorization":f"Bearer {t}"}
        ok("bad login 401", c.post("/api/auth/login",json={"username":"papa","password":"x"}).status_code==401)
        a=H(c.post("/api/auth/login",json={"username":"PAPA","password":"pw1234"}).json()["token"])
        r=c.post("/api/users",json={"username":"ravi","name":"Ravi","password":"p123"},headers=a); ok("create user", r.status_code==200)
        uid=r.json()["id"]
        ok("dup user 400", c.post("/api/users",json={"username":"Ravi","name":"R","password":"p123"},headers=a).status_code==400)
        ok("reset pw", c.put(f"/api/users/{uid}/password",json={"password":"newpw"},headers=a).status_code==200)
        e=H(c.post("/api/auth/login",json={"username":"ravi","password":"newpw"}).json()["token"])
        ok("me", c.get("/api/auth/me",headers=e).json()["username"]=="ravi")
        ok("emp no users 403", c.get("/api/users",headers=e).status_code==403)
        imp=c.post("/api/medicines/import/paste",json={"text":"name,company,supplier\nDolo 650,Micro Labs,Shree Agencies\nPan 40,Alkem,Mahaveer Pharma\n50%_test,X,"},headers=a).json()
        ok("paste import "+str(imp), imp=={"added":3,"updated":0,"skipped":0})
        wb=openpyxl.Workbook(); ws=wb.active; ws.append(["Medicine Name","Company","Supplier"]); ws.append(["Crocin","GSK","Shree Agencies"]); b=io.BytesIO(); wb.save(b)
        ok("xlsx import", c.post("/api/medicines/import/xlsx",files={"file":("m.xlsx",b.getvalue())},headers=a).json()["added"]==1)
        ok("csv import", c.post("/api/medicines/import/csv",files={"file":("m.csv",b"name,company,supplier\nCrocin,GSK,Other\n")},headers=a).json()["updated"]==1)
        sups={s["name"]:s["id"] for s in c.get("/api/suppliers",headers=e).json()}
        ok("suppliers created", set(sups)=={"Shree Agencies","Mahaveer Pharma","Other"})
        sg=c.get("/api/medicines/suggest",params={"q":"micro"},headers=e).json()
        ok("suggest by company, no supplier for emp", sg and "default_supplier_id" not in sg[0])
        ok("suggest admin has supplier", "default_supplier_id" in c.get("/api/medicines/suggest",params={"q":"dolo"},headers=a).json()[0])
        ok("LIKE wildcard escaped", [m["name"] for m in c.get("/api/medicines",params={"q":"%_"},headers=a).json()]==["50%_test"])
        l1=c.post("/api/logs",json={"medicine_name":"dolo 650","quantity":"2 strips"},headers=e).json()
        ok("auto categorised", l1["supplier_id"]==sups["Shree Agencies"] and l1["company"]=="Micro Labs")
        l2=c.post("/api/logs",json={"medicine_name":"Brand New Syrup","quantity":"1"},headers=e).json()
        ok("unknown -> unassigned", l2["supplier_id"] is None and l2["status"]=="unassigned")
        el=c.get("/api/logs",headers=e).json()
        ok("employee logs hide supplier", len(el)==2 and all("supplier_id" not in x for x in el))
        c.put(f"/api/logs/{l1['id']}/assign",json={"supplier_id":sups["Other"]},headers=a)
        dolo=[m for m in c.get("/api/medicines",params={"q":"dolo"},headers=a).json()][0]
        ok("drag keeps default", dolo["default_supplier_name"]=="Shree Agencies")
        r=c.put(f"/api/logs/{l2['id']}/assign",json={"supplier_id":sups["Mahaveer Pharma"],"remember":True},headers=a).json()
        l3=c.post("/api/logs",json={"medicine_name":"brand new syrup","quantity":"0"},headers=e).json()
        ok("remember creates medicine", r["medicine_id"] and l3["supplier_id"]==sups["Mahaveer Pharma"])
        ok("emp edit 403", c.put(f"/api/logs/{l1['id']}",json={"quantity":"9"},headers=e).status_code==403)
        ok("admin edit", c.put(f"/api/logs/{l1['id']}",json={"quantity":"9"},headers=a).json()["quantity"]=="9")
        la=c.post("/api/logs",json={"medicine_name":"Pan 40","quantity":"3"},headers=a).json()
        ok("emp cannot delete others", c.delete(f"/api/logs/{la['id']}",headers=e).status_code==404)
        ok("emp deletes own", c.delete(f"/api/logs/{l3['id']}",headers=e).status_code==200)
        t=c.get("/api/logs/export/text",headers=a).json()["text"]; ok("text export", "*Other*" in t and "Dolo 650" in t)
        p=c.get("/api/logs/export/pdf",headers=a); ok("pdf export", p.content[:4]==b"%PDF")
        ok("emp bulk 403", c.delete("/api/logs",headers=e).status_code==403)
        ok("bulk supplier", c.delete("/api/logs",params={"supplier_id":sups["Other"]},headers=a).json()["deleted"]==1)
        c.delete(f"/api/suppliers/{sups['Mahaveer Pharma']}",headers=a)
        left=c.get("/api/logs",headers=a).json()
        ok("deleting supplier moves items to unassigned", all(x["supplier_id"] is None for x in left) and len(left)==2)
        ok("bulk all", c.delete("/api/logs",params={"supplier_id":"unassigned"},headers=a).json()["deleted"]==2)
        ok("health", c.get("/api/health").json()=={"ok":True})
