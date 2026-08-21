"""Stockbook backend regression suite (iteration 2).

Covers: auth (login/me/logout, cookie flags), suppliers, medicines CRUD +
suggest privacy, logs create/assign/delete, exports (text/pdf), RBAC.
Shared resources come from session fixtures in conftest.py so the suite is
safe under pytest-xdist loadscope.
"""
import uuid

import pytest
import requests


# ---------------- Auth module ----------------
class TestAuth:
    def test_login_success_and_cookie(self, api_url, admin_credentials):
        r = requests.post(f"{api_url}/auth/login", json=admin_credentials, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["email"] == admin_credentials["email"].lower()
        assert data["role"] == "admin"
        assert isinstance(data["token"], str) and len(data["token"]) > 20
        set_cookie = r.headers.get("set-cookie", "")
        assert "access_token=" in set_cookie, f"no access_token cookie: {set_cookie}"
        assert "HttpOnly" in set_cookie, f"cookie not HttpOnly: {set_cookie}"
        assert "Secure" in set_cookie
        assert "samesite=none" in set_cookie.lower()

    def test_login_invalid_password(self, api_url, admin_credentials):
        r = requests.post(
            f"{api_url}/auth/login",
            json={"email": admin_credentials["email"], "password": "wrong-pass-xyz"},
            timeout=30,
        )
        assert r.status_code == 401
        assert "detail" in r.json()

    def test_me_with_bearer_header(self, api_url, admin_client, admin_credentials):
        r = admin_client.get(f"{api_url}/auth/me")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["email"] == admin_credentials["email"].lower()
        assert d["role"] == "admin"
        assert "_id" not in d and "password_hash" not in d

    def test_me_unauthenticated(self, api_url, anon_client):
        assert anon_client.get(f"{api_url}/auth/me").status_code == 401

    def test_me_invalid_token(self, api_url):
        r = requests.get(f"{api_url}/auth/me", headers={"Authorization": "Bearer not.a.jwt"}, timeout=30)
        assert r.status_code == 401

    def test_logout_clears_cookie(self, api_url, admin_credentials):
        s = requests.Session()
        r = s.post(f"{api_url}/auth/login", json=admin_credentials, timeout=30)
        assert r.status_code == 200
        token = r.json()["token"]
        lo = s.post(f"{api_url}/auth/logout", headers={"Authorization": f"Bearer {token}"}, timeout=30)
        assert lo.status_code == 200 and lo.json() == {"ok": True}
        sc = lo.headers.get("set-cookie", "")
        assert 'access_token=""' in sc or "access_token=;" in sc, f"cookie not cleared: {sc}"
        me = s.get(f"{api_url}/auth/me", timeout=30)
        assert me.status_code == 401, f"expected 401 after logout, got {me.status_code}"

    def test_brute_force_lockout(self, api_url, admin_credentials):
        """Playbook expects lockout after 5 failed attempts."""
        codes = []
        for _ in range(6):
            r = requests.post(
                f"{api_url}/auth/login",
                json={"email": admin_credentials["email"], "password": "bad-pass-000"},
                timeout=30,
            )
            codes.append(r.status_code)
        assert 429 in codes or 423 in codes, f"No lockout observed, codes={codes}"

    def test_admin_password_still_valid_after_failures(self, api_url, admin_credentials):
        r = requests.post(f"{api_url}/auth/login", json=admin_credentials, timeout=30)
        assert r.status_code == 200


# ---------------- Suppliers module ----------------
class TestSuppliers:
    def test_list_requires_auth(self, api_url, anon_client):
        assert anon_client.get(f"{api_url}/suppliers").status_code == 401

    def test_create_and_list_supplier(self, api_url, admin_client, supplier):
        lst = admin_client.get(f"{api_url}/suppliers")
        assert lst.status_code == 200
        rows = lst.json()
        assert any(s["id"] == supplier["id"] and s["name"] == supplier["name"] for s in rows)
        assert all("_id" not in s for s in rows)

    def test_create_empty_name_rejected(self, api_url, admin_client):
        assert admin_client.post(f"{api_url}/suppliers", json={"name": "   "}).status_code == 400

    def test_create_duplicate_returns_existing(self, api_url, admin_client, supplier):
        r = admin_client.post(f"{api_url}/suppliers", json={"name": supplier["name"]})
        assert r.status_code == 200
        assert r.json()["id"] == supplier["id"]


# ---------------- Medicines module ----------------
class TestMedicines:
    def test_medicine_decorates_supplier_name(self, api_url, admin_client, supplier, medicine):
        assert medicine["default_supplier_name"] == supplier["name"]
        lst = admin_client.get(f"{api_url}/medicines", params={"q": medicine["name"]})
        assert lst.status_code == 200
        found = [m for m in lst.json() if m["id"] == medicine["id"]]
        assert found, "medicine not persisted"
        assert found[0]["default_supplier_name"] == supplier["name"]

    def test_update_medicine_persists(self, api_url, admin_client, supplier, medicine):
        r = admin_client.put(
            f"{api_url}/medicines/{medicine['id']}",
            json={"name": medicine["name"], "company": "TEST_Co2", "default_supplier_id": supplier["id"]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["company"] == "TEST_Co2"
        lst = admin_client.get(f"{api_url}/medicines", params={"q": medicine["name"]}).json()
        assert any(m["id"] == medicine["id"] and m["company"] == "TEST_Co2" for m in lst)

    def test_update_missing_medicine_404(self, api_url, admin_client):
        r = admin_client.put(f"{api_url}/medicines/{uuid.uuid4()}", json={"name": "TEST_x"})
        assert r.status_code == 404

    def test_delete_missing_medicine_404(self, api_url, admin_client):
        assert admin_client.delete(f"{api_url}/medicines/{uuid.uuid4()}").status_code == 404

    def test_admin_suggest_includes_supplier(self, api_url, admin_client, medicine):
        r = admin_client.get(f"{api_url}/medicines/suggest", params={"q": medicine["name"]})
        assert r.status_code == 200
        items = r.json()
        assert items, "expected suggestions"
        assert "default_supplier_id" in items[0]

    def test_delete_medicine_and_verify_removal(self, api_url, admin_client, tag):
        r = admin_client.post(f"{api_url}/medicines", json={"name": f"TEST_Del_{tag}", "company": "TEST_Co"})
        assert r.status_code == 200
        mid = r.json()["id"]
        assert admin_client.delete(f"{api_url}/medicines/{mid}").status_code == 200
        lst = admin_client.get(f"{api_url}/medicines", params={"q": f"TEST_Del_{tag}"}).json()
        assert all(m["id"] != mid for m in lst)


# ---------------- Users + employee privacy/RBAC ----------------
class TestUsersAndPrivacy:
    def test_employee_user_listed_without_hash(self, api_url, admin_client, employee):
        lst = admin_client.get(f"{api_url}/users")
        assert lst.status_code == 200
        rows = lst.json()
        assert any(u["email"] == employee["email"] for u in rows)
        assert all("password_hash" not in u and "_id" not in u for u in rows)

    def test_duplicate_email_rejected(self, api_url, admin_client, employee):
        r = admin_client.post(
            f"{api_url}/users",
            json={"email": employee["email"], "name": "dup", "password": "x123456", "role": "employee"},
        )
        assert r.status_code == 400

    def test_invalid_role_rejected(self, api_url, admin_client, tag):
        r = admin_client.post(
            f"{api_url}/users",
            json={"email": f"test_bad_{tag}@test.com", "name": "x", "password": "x123456", "role": "superuser"},
        )
        assert r.status_code == 400

    def test_employee_suggest_omits_supplier(self, api_url, employee_client, medicine):
        r = employee_client.get(f"{api_url}/medicines/suggest", params={"q": medicine["name"]})
        assert r.status_code == 200
        items = r.json()
        assert items, "employee should see suggestions"
        for it in items:
            assert "default_supplier_id" not in it, "PRIVACY LEAK: supplier exposed to employee"

    @pytest.mark.parametrize(
        "method,path,body",
        [
            ("post", "/suppliers", {"name": "TEST_x"}),
            ("post", "/medicines", {"name": "TEST_x"}),
            ("get", "/users", None),
            ("get", "/logs/export/text", None),
            ("get", "/logs/export/pdf", None),
        ],
    )
    def test_employee_rbac_forbidden(self, api_url, employee_client, method, path, body):
        r = getattr(employee_client, method)(f"{api_url}{path}", json=body, timeout=30)
        assert r.status_code == 403, f"{path} -> {r.status_code}"

    def test_employee_sees_only_own_logs(self, api_url, employee_client, admin_client, tag):
        # employee note
        e = employee_client.post(
            f"{api_url}/logs", json={"medicine_name": f"TEST_EmpOnly_{tag}", "quantity": "2"}
        )
        assert e.status_code == 200, e.text
        emp_log = e.json()["id"]
        # admin note
        a = admin_client.post(
            f"{api_url}/logs", json={"medicine_name": f"TEST_AdminOnly_{tag}", "quantity": "9"}
        )
        assert a.status_code == 200
        admin_log = a.json()["id"]

        emp_ids = [x["id"] for x in employee_client.get(f"{api_url}/logs").json()]
        assert emp_log in emp_ids
        assert admin_log not in emp_ids, "employee can see admin's logs"

        admin_ids = [x["id"] for x in admin_client.get(f"{api_url}/logs").json()]
        assert emp_log in admin_ids and admin_log in admin_ids

        # employee cannot delete other's log
        assert employee_client.delete(f"{api_url}/logs/{admin_log}").status_code == 404
        assert employee_client.delete(f"{api_url}/logs/{emp_log}").status_code == 200
        assert admin_client.delete(f"{api_url}/logs/{admin_log}").status_code == 200


# ---------------- Logs module ----------------
class TestLogs:
    def test_create_log_known_medicine_autolinks(self, api_url, admin_client, supplier, medicine):
        r = admin_client.post(
            f"{api_url}/logs",
            json={"medicine_id": None, "medicine_name": medicine["name"].lower(), "quantity": "3 strips"},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["medicine_id"] == medicine["id"]
        assert d["supplier_id"] == supplier["id"]
        assert d["status"] == "assigned"
        assert d["quantity"] == "3 strips"
        assert "_id" not in d
        assert admin_client.delete(f"{api_url}/logs/{d['id']}").status_code == 200

    def test_create_log_unknown_medicine_unassigned(self, api_url, admin_client, tag):
        r = admin_client.post(
            f"{api_url}/logs", json={"medicine_id": None, "medicine_name": f"TEST_Unknown_{tag}", "quantity": "1"}
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["supplier_id"] is None and d["status"] == "unassigned"
        assert admin_client.delete(f"{api_url}/logs/{d['id']}").status_code == 200

    def test_create_log_empty_name_rejected(self, api_url, admin_client):
        assert admin_client.post(f"{api_url}/logs", json={"medicine_name": "  ", "quantity": "1"}).status_code == 400

    def test_list_logs_by_date_param(self, api_url, admin_client):
        r = admin_client.get(f"{api_url}/logs", params={"date": "2000-01-01"})
        assert r.status_code == 200
        assert r.json() == []

    def test_assign_and_unassign(self, api_url, admin_client, supplier, tag):
        c = admin_client.post(f"{api_url}/logs", json={"medicine_name": f"TEST_Move_{tag}", "quantity": "1"})
        assert c.status_code == 200
        lid = c.json()["id"]
        assert c.json()["status"] == "unassigned"

        r = admin_client.put(f"{api_url}/logs/{lid}/assign", json={"supplier_id": supplier["id"]})
        assert r.status_code == 200, r.text
        assert r.json()["supplier_id"] == supplier["id"] and r.json()["status"] == "assigned"

        back = admin_client.put(f"{api_url}/logs/{lid}/assign", json={"supplier_id": None})
        assert back.status_code == 200
        assert back.json()["supplier_id"] is None and back.json()["status"] == "unassigned"

        rows = admin_client.get(f"{api_url}/logs").json()
        row = [x for x in rows if x["id"] == lid][0]
        assert row["status"] == "unassigned"
        assert admin_client.delete(f"{api_url}/logs/{lid}").status_code == 200

    def test_assign_missing_log_404(self, api_url, admin_client):
        assert admin_client.put(f"{api_url}/logs/{uuid.uuid4()}/assign", json={"supplier_id": None}).status_code == 404

    def test_delete_missing_log_404(self, api_url, admin_client):
        assert admin_client.delete(f"{api_url}/logs/{uuid.uuid4()}").status_code == 404


# ---------------- Exports module ----------------
class TestExports:
    def test_export_text_grouped(self, api_url, admin_client, supplier, medicine, tag):
        c = admin_client.post(
            f"{api_url}/logs", json={"medicine_id": medicine["id"], "medicine_name": medicine["name"], "quantity": "7"}
        )
        assert c.status_code == 200
        lid = c.json()["id"]
        try:
            r = admin_client.get(f"{api_url}/logs/export/text")
            assert r.status_code == 200, r.text
            text = r.json()["text"]
            assert "Order List" in text
            assert f"*{supplier['name']}*" in text, text
            assert medicine["name"] in text
            assert "Qty left: 7" in text
        finally:
            admin_client.delete(f"{api_url}/logs/{lid}")

    def test_export_text_filter_unassigned(self, api_url, admin_client, tag):
        c = admin_client.post(f"{api_url}/logs", json={"medicine_name": f"TEST_Un_{tag}", "quantity": "4"})
        assert c.status_code == 200
        lid = c.json()["id"]
        try:
            r = admin_client.get(f"{api_url}/logs/export/text", params={"supplier_id": "unassigned"})
            assert r.status_code == 200
            text = r.json()["text"]
            assert "*Unassigned*" in text, text
            assert f"TEST_Un_{tag}" in text
        finally:
            admin_client.delete(f"{api_url}/logs/{lid}")

    def test_export_pdf_bytes(self, api_url, admin_client):
        r = admin_client.get(f"{api_url}/logs/export/pdf")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content[:4] == b"%PDF"
        assert len(r.content) > 1000

    def test_export_pdf_empty_date_ok(self, api_url, admin_client):
        r = admin_client.get(f"{api_url}/logs/export/pdf", params={"date": "2000-01-01"})
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"


# ---------------- Import module ----------------
class TestImports:
    def test_paste_import_with_header(self, api_url, admin_client, tag):
        med = f"TEST_Paste_{tag}"
        sup = f"TEST_PasteSup_{tag}"
        payload = {"text": f"name,company,supplier\n{med},TEST_Co,{sup}", "delimiter": ","}
        r = admin_client.post(f"{api_url}/medicines/import/paste", json=payload)
        assert r.status_code == 200, r.text
        assert r.json()["added"] == 1
        lst = admin_client.get(f"{api_url}/medicines", params={"q": med}).json()
        assert lst and lst[0]["default_supplier_name"] == sup
        # cleanup
        admin_client.delete(f"{api_url}/medicines/{lst[0]['id']}")
        sups = admin_client.get(f"{api_url}/suppliers").json()
        for s in sups:
            if s["name"] == sup:
                admin_client.delete(f"{api_url}/suppliers/{s['id']}")

    def test_csv_import_multipart(self, api_url, admin_token, tag):
        med = f"TEST_Csv_{tag}"
        csv_bytes = f"Medicine Name,Company,Default Supplier\n{med},TEST_Co,TEST_CsvSup_{tag}\n".encode()
        r = requests.post(
            f"{api_url}/medicines/import/csv",
            headers={"Authorization": f"Bearer {admin_token}"},
            files={"file": ("meds.csv", csv_bytes, "text/csv")},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        assert r.json()["added"] == 1
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {admin_token}"})
        lst = s.get(f"{api_url}/medicines", params={"q": med}, timeout=30).json()
        assert lst and lst[0]["default_supplier_name"] == f"TEST_CsvSup_{tag}"
        s.delete(f"{api_url}/medicines/{lst[0]['id']}", timeout=30)
        for sup in s.get(f"{api_url}/suppliers", timeout=30).json():
            if sup["name"] == f"TEST_CsvSup_{tag}":
                s.delete(f"{api_url}/suppliers/{sup['id']}", timeout=30)
