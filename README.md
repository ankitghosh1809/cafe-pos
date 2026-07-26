# ☕ Brew & Co. — Cafe Management System
**Python · Flask · PostgreSQL · Vanilla JS**

A full-stack POS (Point-of-Sale) system built for small to mid-sized cafes. Handles order-taking, checkout with payment collection, receipts, sales analytics, and menu management — split into a password-free customer portal and a password-protected owner portal — with no third-party services required.

---

## Features

### Two portals, one app
- **Landing screen** lets whoever opens the site choose **Customer** or **Owner**.
- **Customer portal** — menu browsing and ordering only. No password, no admin surface.
- **Owner portal** — password-protected. Everything else lives here: taking orders on the owner's behalf, menu management, sales reports, and order history (including deleting past orders).
- Shortcuts: opening the site at `#customer` or `#owner` jumps straight to that portal.

### Order Management
- Browse menu by category with live search, small icon for every item
- Add / remove items, adjust quantities on the fly
- Table selector is a dropdown, Table 1–10
- Apply discounts before checkout
- **Single "Place Order" checkout**: pick Cash / Card / UPI inline and the order is placed and marked paid in one step — no separate "Bill" step

### Menu Management (Owner portal)
- Add items with a name, price, description, category and a small icon (33 to choose from)
- Toggle availability, delete items (blocked with a clear message if the item has order history)
- Seeded with 40 menu items across 5 categories on first run

### Receipts
- Auto-generated itemised receipt per order, including payment method
- Shows subtotal, 5% GST, discount, and grand total
- Print-ready modal

### Sales Reporting (Owner portal)
- Revenue, order count, average ticket size, tax collected
- Top-5 selling items (by quantity and revenue)
- Daily revenue bar chart — switchable between Today / 7 days / 30 days

### Order History (Owner portal)
- Sorted by date (toggle newest/oldest first)
- Small calendar to jump to any specific day's orders
- Delete a past order record
- Shows who placed each order (customer / owner) and how it was paid

---

## Performance

The original version opened a brand-new database connection for **every single query** — loading the menu alone opened 6 separate connections (1 for categories + 1 per category). Against a remote Postgres instance (Neon), each new connection pays a real network round trip + TLS handshake, so this added up fast.

This version uses a small pooled connection (reused across queries, with automatic retry if Neon has dropped an idle connection) and consolidates what used to be several queries into one wherever possible:
- Menu load: 6 queries → 1 (single `JOIN` instead of one query per category)
- Placing an order: up to 8 queries → 3 (batched line-item insert + a single combined order+items read-back)
- Order history: 2 queries → 1 (row count folded into the same query via a window function)

Measured locally against Postgres with an artificial ~55ms connection-setup delay added (to approximate the network+handshake cost of a remote Neon connection), this cut menu-load time by roughly 85–99% and order-placement time by roughly 98%, depending on cache state. The menu response is also cached in-memory for 30 seconds (invalidated instantly on any menu edit), and Reports/History cache their last result for 20 seconds so flipping between tabs doesn't re-hit the database every time.

For production, also point `DATABASE_URL` at Neon's **pooled** connection string (the `-pooler` host Neon gives you) rather than the direct one — it stacks with the pooling above.

---

## Tech Stack

| Layer    | Technology                  |
|----------|-----------------------------|
| Backend  | Python 3.11+, Flask 3, PostgreSQL (pooled via `psycopg2.pool`) |
| Frontend | HTML5, CSS3 (custom), Vanilla JS (ES2020) |
| Database | PostgreSQL via `psycopg2` (Neon in production) |
| Auth     | Stdlib HMAC-signed tokens (no extra dependency) — see [Owner password](#owner-password-required-for-the-owner-portal) |
| Fonts    | Playfair Display + DM Sans (Google Fonts) |

---

## Project Structure

```
cafe-pos/
├── api/
│   ├── index.py          # Vercel serverless entry point
│   └── app.py            # Flask app — all routes (deployed copy)
├── backend/
│   ├── app.py             # same Flask app, for local dev
│   └── requirements.txt
├── frontend/
│   └── index.html        # single-file SPA (icons, portals, everything)
├── requirements.txt       # used by Vercel's build (mirrors backend/requirements.txt)
├── vercel.json            # routes /api/** to api/index.py, everything else to frontend/
├── schema.sql             # standalone DB schema reference (app also self-creates/migrates this)
├── .env.example           # copy to .env locally — DATABASE_URL + OWNER_PASSWORD
└── README.md
```

`api/` and `backend/` hold identical copies of `app.py` — `api/` is what Vercel deploys, `backend/` is what you run locally. Edit one, then copy your changes into the other before committing.

---

## Getting Started

### 1. Clone / download

```bash
git clone https://github.com/ankitghosh1809/cafe-pos.git
cd cafe-pos
```

### 2. Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env         # then edit .env — see below
python app.py
```

The server starts at **http://localhost:5000**.
Tables are created (or migrated, if the database already exists from before this update) automatically against whatever `DATABASE_URL` points to. On a brand-new database, the 40-item demo menu plus 30 days of sample orders are seeded too.

### Owner password (required for the Owner portal)

Set `OWNER_PASSWORD` in `.env` (or in Vercel's environment variables for the deployed site):

```
OWNER_PASSWORD=choose-a-real-password-here
```

There is deliberately **no built-in default password** — this repo is public, so a hardcoded fallback would mean anyone reading the source could log into any deployment that forgot to set one. Until `OWNER_PASSWORD` is set, the Owner login screen will show a message saying so instead of a generic "wrong password."

Optionally also set `SECRET_KEY` (any long random string) — used to sign owner login tokens. If you don't set one, it's derived from `OWNER_PASSWORD` so tokens still survive server restarts; a dedicated `SECRET_KEY` is still the more correct choice for a real deployment.

### 3. Frontend

Open `frontend/index.html` directly in your browser — no build step needed. You'll land on the portal picker; choose **Customer** or **Owner**.

---

## API Reference

### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/owner/login` | `{password}` → `{token, expires_in}`. Owner-only routes need `Authorization: Bearer <token>` |
| GET | `/api/owner/verify` | Checks whether the current token is still valid |

### Menu
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/menu` | Full menu with categories (public — cached 30s) |
| POST | `/api/menu/items` 🔒 | Add a menu item (`image_key` picks its icon) |
| PUT | `/api/menu/items/:id` 🔒 | Update name / price / availability / icon |
| DELETE | `/api/menu/items/:id` 🔒 | Remove an item (409 if it has order history) |

### Orders
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/orders` | Create an order. Include `payment_method` (`cash`/`card`/`upi`) to place **and pay** in one step |
| GET | `/api/orders` 🔒 | List orders (filter by `?status=`) |
| GET | `/api/orders/:id` | Order detail with line items |
| DELETE | `/api/orders/:id` 🔒 | Delete an order record |
| PATCH | `/api/orders/:id/status` 🔒 | Manually override status |
| GET | `/api/orders/:id/receipt` | Formatted receipt object, includes payment method |

### Reports
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/reports/sales?period=today\|week\|month` 🔒 | Revenue summary + top items + daily chart |
| GET | `/api/reports/order-history?page=1&per_page=15&sort=desc&date=YYYY-MM-DD` 🔒 | Paginated, sortable, optionally filtered to one day |

🔒 = requires `Authorization: Bearer <owner token>`

---

## Database Schema

```sql
categories   (id, name, icon)
menu_items   (id, category_id, name, description, price, available, image_key, created_at)
orders       (id, table_no, customer, status, subtotal, tax, discount, total,
              payment_method, placed_by, notes, created_at, billed_at, paid_at)
order_items  (id, order_id, item_id, quantity, unit_price, line_total)
```

Foreign key constraints are enforced by Postgres (`ON DELETE CASCADE` for order line items, `ON DELETE RESTRICT` for categories/menu items so historical orders can't be orphaned). `image_key`, `payment_method`, and `placed_by` are added automatically via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` on startup, so upgrading an existing database is a non-event.

---

## Screenshots

> Frontend runs entirely in-browser. Open `frontend/index.html` after starting the backend.

- **Landing** — Customer / Owner picker
- **POS View** — category sidebar, menu grid with icons, live cart panel, one-step checkout
- **Menu Management** — add/toggle/delete items (Owner)
- **Reports View** — KPI cards, top-items leaderboard, daily bar chart (Owner)
- **History View** — sortable, calendar-filterable order log with delete (Owner)

---

## Author

Built as a portfolio project demonstrating:
- RESTful API design with Flask, including a lightweight auth layer built from stdlib primitives
- Relational DB design, raw SQL queries, and safe zero-downtime schema migrations
- Connection-pooling and query-count optimization against a real remote Postgres provider (Neon)
- Single-page frontend architecture (no framework) with role-gated views
- Real-time bill calculation, payment collection, and receipt generation
- Business analytics via aggregated SQL reporting

## 🌐 Live Demo
[https://cafe-pos-lake.vercel.app](https://cafe-pos-lake.vercel.app)
