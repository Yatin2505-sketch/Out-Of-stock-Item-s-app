# Stockbook — Pharmacy Stock Ordering App

## Original Problem Statement
A pharmacy stock-ordering app for father, self and employees. Employees enter medicine name + quantity left; the app auto-categorises each entry under its designated supplier. Unknown medicines go to an "Unassigned" column. Admin manages suppliers/medicines (imported from Tally), drags items across supplier columns, and exports the daily order list per supplier.

## Users
- Admin (father, me): full access, kanban board, DB, imports, exports, user management.
- Employee: only medicine name + quantity, sees own daily notes.

## Tech
- Backend: FastAPI + MongoDB (motor). JWT auth (cookie + Bearer fallback).
- Frontend: React 19, react-router-dom v7, @hello-pangea/dnd, sonner, Cormorant Garamond + Manrope.
- PDF: reportlab. Excel: openpyxl.

## Core requirements (Static)
- Two roles (admin, employee) with strict data hiding for employees (no supplier info).
- Medicine DB seeded via CSV/XLSX upload or paste-text; manual add supported.
- Daily log = medicine notes for a given day, auto-linked to default supplier if match found.
- Kanban board grouped by supplier + "Unassigned" column with drag-and-drop between columns.
- Per-day date picker.
- Export: WhatsApp text and PDF (per-supplier or full day).

## What's implemented (2026-08-21)
- Auth: bcrypt + JWT, admin seed from env, /api/auth/login, /me, /logout.
- Users CRUD (admin).
- Suppliers CRUD.
- Medicines CRUD + `/suggest` autocomplete (employees don't see supplier).
- Imports: CSV, XLSX, paste-text.
- Logs create/list/delete + assign supplier (drag-drop) + date filtering.
- Exports: text + PDF.
- Frontend: Login, Employee minimal entry, Admin kanban, Medicine DB, Settings.

## Backlog (P1)
- Employee view: show supplier hints hidden with dashes (already hidden — OK).
- Bulk actions on kanban cards (assign multiple at once).
- Historical analytics (which medicine gets low often).
- Undo delete / edit qty inline.
- WhatsApp direct-send integration (currently: copy to clipboard).
- PWA / offline shift.

## Next tasks after 1st finish
- Testing agent pass end-to-end.
- Address any critical failures.
- Ship.
