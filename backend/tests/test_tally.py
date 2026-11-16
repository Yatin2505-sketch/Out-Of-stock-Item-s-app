"""Tally Prime purchase-bill import + copy-to-another-supplier."""
import sys
import importlib
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tally_import import parse_purchase_bills  # noqa: E402


def voucher(guid, vtype, date, number, party, items, cancelled="No"):
    inv = "".join(
        f"""<ALLINVENTORYENTRIES.LIST>
              <STOCKITEMNAME>{i}</STOCKITEMNAME>
              <ACTUALQTY> 10 Strip</ACTUALQTY>
              <BATCHALLOCATIONS.LIST><BATCHNAME>B1</BATCHNAME></BATCHALLOCATIONS.LIST>
            </ALLINVENTORYENTRIES.LIST>"""
        for i in items
    )
    return f"""<TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER REMOTEID="{guid}" VCHTYPE="{vtype}" ACTION="Create">
        <DATE>{date}</DATE>
        <GUID>{guid}</GUID>
        <VOUCHERTYPENAME>{vtype}</VOUCHERTYPENAME>
        <VOUCHERNUMBER>{number}</VOUCHERNUMBER>
        <PARTYLEDGERNAME>{party}</PARTYLEDGERNAME>
        <ISCANCELLED>{cancelled}</ISCANCELLED>
        <NARRATION>Bill&#4; ref</NARRATION>
        <UDF:VCHREMARK.LIST DESC="`Remark`"><UDF:VCHREMARK>x</UDF:VCHREMARK></UDF:VCHREMARK.LIST>
        <LEDGERENTRIES.LIST><LEDGERNAME>{party}</LEDGERNAME><ISPARTYLEDGER>Yes</ISPARTYLEDGER></LEDGERENTRIES.LIST>
        {inv}
      </VOUCHER>
    </TALLYMESSAGE>"""


def tally_file(vouchers, encoding="utf-16"):
    body = "".join(vouchers)
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>
<BODY><IMPORTDATA><REQUESTDESC><REPORTNAME>Vouchers</REPORTNAME></REQUESTDESC>
<REQUESTDATA>{body}</REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>"""
    return xml.encode(encoding)


SAMPLE = tally_file([
    voucher("g1", "Purchase", "20261101", "P-1", "Kishoram Agencies", ["Dolo 650", "Pan 40"]),
    voucher("g2", "Purchase", "20261105", "P-2", "Kishoram Agencies", ["Dolo 650"]),
    voucher("g3", "Purchase", "20261110", "P-3", "Shree Medicos", ["Dolo 650", "Crocin Advance"]),
    voucher("g4", "Purchase", "20261111", "P-4", "Ghost Traders", ["Cancelled Item"], cancelled="Yes"),
    voucher("g5", "Purchase Order", "20261112", "PO-1", "Order Only Co", ["Ordered Item"]),
    voucher("g6", "Sales", "20261112", "S-1", "Some Customer", ["Dolo 650"]),
])


def test_parser_handles_tally_quirks():
    bills = list(parse_purchase_bills(SAMPLE))
    assert [b.party for b in bills] == ["Kishoram Agencies", "Kishoram Agencies", "Shree Medicos"]
    assert bills[0].items == ["Dolo 650", "Pan 40"]
    assert bills[0].date == "2026-11-01"
    # also plain UTF-8 without declaration
    utf8 = tally_file([voucher("x", "Purchase", "20260101", "1", "A", ["B"])], encoding="utf-8")
    assert [b.items for b in parse_purchase_bills(utf8)] == [["B"]]


def test_tally_import_and_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKBOOK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ADMIN_USERNAME", "papa")
    monkeypatch.setenv("ADMIN_PASSWORD", "pw1234")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    import server
    server = importlib.reload(server)

    with TestClient(server.app) as c:
        a = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"username": "papa", "password": "pw1234"}).json()["token"]}
        c.post("/api/users", json={"username": "ravi", "name": "Ravi", "password": "p123"}, headers=a)
        e = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"username": "ravi", "password": "p123"}).json()["token"]}

        # A medicine that already has a default supplier set by the admin
        manual = c.post("/api/suppliers", json={"name": "Manual Choice"}, headers=a).json()["id"]
        c.post("/api/medicines", json={"name": "Pan 40", "company": "Alkem", "default_supplier_id": manual}, headers=a)

        r = c.post("/api/medicines/import/tally", files={"file": ("DayBook.xml", SAMPLE)}, headers=a)
        assert r.status_code == 200, r.text
        res = r.json()
        assert res["bills_found"] == 3 and res["bills_new"] == 3
        assert res["new_suppliers"] == 2  # Kishoram, Shree (cancelled/order/sales ignored)
        assert res["new_medicines"] == 2  # Dolo 650, Crocin Advance (Pan 40 existed)

        meds = {m["name"]: m for m in c.get("/api/medicines", headers=a).json()}
        assert set(meds) == {"Dolo 650", "Pan 40", "Crocin Advance"}
        # Dolo: 2 bills from Kishoram, 1 from Shree -> default Kishoram, Shree remembered as other
        assert meds["Dolo 650"]["default_supplier_name"] == "Kishoram Agencies"
        assert meds["Dolo 650"]["other_suppliers"] == ["Shree Medicos"]
        # Admin's own choice is respected; Tally party added as an alternative
        assert meds["Pan 40"]["default_supplier_name"] == "Manual Choice"
        assert meds["Pan 40"]["other_suppliers"] == ["Kishoram Agencies"]

        # Importing the same file again doesn't double count
        again = c.post("/api/medicines/import/tally", files={"file": ("DayBook.xml", SAMPLE)}, headers=a).json()
        assert again["bills_new"] == 0 and again["bills_already_imported"] == 3

        # Opt-in: make defaults follow Tally's most-used party
        newer = tally_file([voucher(f"n{i}", "Purchase", "20261113", f"N{i}", "Kishoram Agencies", ["Pan 40"]) for i in range(2)])
        c.post("/api/medicines/import/tally", files={"file": ("x.xml", newer)}, data={"update_defaults": "true"}, headers=a)
        pan = [m for m in c.get("/api/medicines", params={"q": "Pan 40"}, headers=a).json()][0]
        assert pan["default_supplier_name"] == "Kishoram Agencies"

        # Bad file
        assert c.post("/api/medicines/import/tally", files={"file": ("x.xml", b"not xml")}, headers=a).status_code == 400

        # Employee notes Dolo -> goes to Kishoram; admin sees Shree as an alternative
        log = c.post("/api/logs", json={"medicine_name": "dolo 650", "quantity": "2"}, headers=e).json()
        sups = {s["name"]: s["id"] for s in c.get("/api/suppliers", headers=a).json()}
        assert log["supplier_id"] == sups["Kishoram Agencies"]
        admin_logs = c.get("/api/logs", headers=a).json()
        assert [s["name"] for s in admin_logs[0]["alt_suppliers"]] == ["Shree Medicos"]
        assert "alt_suppliers" not in c.get("/api/logs", headers=e).json()[0]  # employees never see suppliers

        # Copy in the same column, and copy straight to another supplier
        assert c.post(f"/api/logs/{log['id']}/copy", json={}, headers=e).status_code == 403
        same = c.post(f"/api/logs/{log['id']}/copy", json={}, headers=a).json()
        assert same["supplier_id"] == sups["Kishoram Agencies"] and same["id"] != log["id"]
        other = c.post(f"/api/logs/{log['id']}/copy", json={"supplier_id": sups["Shree Medicos"]}, headers=a).json()
        assert other["supplier_id"] == sups["Shree Medicos"] and other["quantity"] == "2"
        assert [s["name"] for s in other["alt_suppliers"]] == ["Kishoram Agencies"]
        assert len(c.get("/api/logs", headers=a).json()) == 3
        # Copies don't touch the medicine's default
        dolo = [m for m in c.get("/api/medicines", params={"q": "Dolo"}, headers=a).json()][0]
        assert dolo["default_supplier_name"] == "Kishoram Agencies"
        text = c.get("/api/logs/export/text", headers=a).json()["text"]
        assert "*Shree Medicos*" in text and "*Kishoram Agencies*" in text
