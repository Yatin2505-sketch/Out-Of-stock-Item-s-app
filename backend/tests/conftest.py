import os
import re
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL is missing from env and /app/frontend/.env")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def api_url():
    return API


@pytest.fixture(scope="session")
def admin_credentials():
    path = Path("/app/memory/test_credentials.md")
    if not path.exists():
        pytest.skip("Missing /app/memory/test_credentials.md")
    content = path.read_text(encoding="utf-8")
    email = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?Email(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    pwd = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?Password(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    if not email or not pwd:
        pytest.skip("No email/password in test_credentials.md")
    return {"email": email.group(1), "password": pwd.group(1)}


@pytest.fixture(scope="session")
def admin_token(admin_credentials):
    r = requests.post(f"{API}/auth/login", json=admin_credentials, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"Admin login failed {r.status_code}: {r.text[:300]}")
    token = r.json().get("token")
    if not token:
        pytest.fail("Login response missing token")
    return token


@pytest.fixture(scope="session")
def admin_client(admin_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def anon_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# --- Shared test resources (worker-safe: each xdist worker builds its own) ---
import uuid  # noqa: E402


@pytest.fixture(scope="session")
def tag():
    return uuid.uuid4().hex[:8]


@pytest.fixture(scope="session")
def supplier(admin_client, tag):
    name = f"TEST_Supplier_{tag}"
    r = admin_client.post(f"{API}/suppliers", json={"name": name})
    assert r.status_code == 200, r.text
    doc = r.json()
    yield doc
    admin_client.delete(f"{API}/suppliers/{doc['id']}")


@pytest.fixture(scope="session")
def medicine(admin_client, supplier, tag):
    name = f"TEST_Med_{tag}"
    r = admin_client.post(
        f"{API}/medicines",
        json={"name": name, "company": "TEST_Co", "default_supplier_id": supplier["id"]},
    )
    assert r.status_code == 200, r.text
    doc = r.json()
    yield doc
    admin_client.delete(f"{API}/medicines/{doc['id']}")


@pytest.fixture(scope="session")
def employee(admin_client, tag):
    email = f"test_emp_{tag}@test.com"
    password = "employee123"
    r = admin_client.post(
        f"{API}/users",
        json={"email": email, "name": "TEST Employee", "password": password, "role": "employee"},
    )
    assert r.status_code == 200, r.text
    doc = r.json()
    doc["password"] = password
    login = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert login.status_code == 200, login.text
    doc["token"] = login.json()["token"]
    yield doc
    admin_client.delete(f"{API}/users/{doc['id']}")


@pytest.fixture(scope="session")
def employee_client(employee):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {employee['token']}", "Content-Type": "application/json"})
    return s
