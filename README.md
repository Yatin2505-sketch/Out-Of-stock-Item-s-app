# Stockbook — Pharmacy Short Item List

A small private app for noting medicines that are running low. Each item is
automatically sorted under its supplier, so the admin can send each supplier
their order list (WhatsApp text or PDF).

- **Employees** type a medicine name and the quantity left. They never see suppliers.
- **Admins** see a board of supplier columns, an unclassified list for new items,
  and can drag, edit, delete, import the Tally medicine list and manage logins.

## Self-hosted and private
Everything runs on your own computer. All data is in one file
(`backend/data/stockbook.db`). No external database, analytics or cloud service.

**Setting it up on the shop's Windows computer:** see [SETUP-WINDOWS.md](SETUP-WINDOWS.md).

## For developers
- Backend: FastAPI + SQLite (`backend/server.py`), maintenance commands in `backend/manage.py`.
- Frontend: React (`frontend/`). The production build is committed in `backend/static/`
  so the shop computer doesn't need Node.js. After changing the frontend:
  `cd frontend && yarn install && yarn build && rm -rf ../backend/static && cp -r build ../backend/static`
- Run locally: `cd backend && pip install -r requirements.txt && python manage.py run`
- Tests: `cd backend && pip install pytest httpx && python -m pytest`
