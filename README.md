# ☕ Brew & Co. — Cafe Management System
**Python · Flask · PostgreSQL · Vanilla JS**

A full-stack POS (Point-of-Sale) system built for small to mid-sized cafes. Handles everything from order-taking and billing to automated receipts and sales analytics — no third-party services required.

---

## Features

### Order Management
- Browse menu by category with live search
- Add / remove items, adjust quantities on the fly
- Apply discounts before billing
- One-click bill generation or direct payment with auto-receipt

### Menu Management (via API)
- CRUD endpoints for categories and items
- Toggle item availability without deleting
- Seeded with 18 real menu items across 5 categories on first run

### Receipts
- Auto-generated itemised receipt per order
- Shows subtotal, 5% GST, discount, and grand total
- Print-ready modal

### Sales Reporting
- Revenue, order count, average ticket size, tax collected
- Top-5 selling items (by quantity and revenue)
- Daily revenue bar chart — switchable between Today / 7 days / 30 days

### Order History
- Paginated table of all billed and paid orders
- Filter by status; open any order's receipt inline

---

## Tech Stack

| Layer    | Technology                  |
|----------|-----------------------------|
| Backend  | Python 3.11+, Flask 3, PostgreSQL |
| Frontend | HTML5, CSS3 (custom), Vanilla JS (ES2020) |
| Database | PostgreSQL via `psycopg2` (Neon in production) |
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
│   └── index.html        # single-file SPA
├── requirements.txt       # used by Vercel's build (mirrors backend/requirements.txt)
├── vercel.json            # routes /api/** to api/index.py, everything else to frontend/
├── schema.sql             # standalone DB schema reference (app also self-creates this)
├── .env.example           # copy to .env locally with your DATABASE_URL
└── README.md
```

`api/` and `backend/` currently hold identical copies of `app.py` — `api/` is what Vercel deploys, `backend/` is what you run locally. Edit one, then copy your changes into the other before committing.

---

## Getting Started

### 1. Clone / download

```bash
git clone https://github.com/yourname/cafe-pos.git
cd cafe-pos
```

### 2. Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env         # then edit .env with your Postgres DATABASE_URL
python app.py
```

The server starts at **http://localhost:5000**.
Tables and the 18-item demo menu (plus 30 days of sample orders) are created automatically against whatever database `DATABASE_URL` points to, the first time you run it.

### 3. Frontend

Open `frontend/index.html` directly in your browser — no build step needed.

---

## API Reference

### Menu
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/menu` | Full menu with categories |
| POST | `/api/menu/items` | Add a menu item |
| PUT | `/api/menu/items/:id` | Update name / price / availability |
| DELETE | `/api/menu/items/:id` | Remove an item |

### Orders
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/orders` | Create a new order |
| GET | `/api/orders` | List orders (filter by `?status=`) |
| GET | `/api/orders/:id` | Order detail with line items |
| PATCH | `/api/orders/:id/status` | Update status (`open → billed → paid`) |
| GET | `/api/orders/:id/receipt` | Formatted receipt object |

### Reports
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/reports/sales?period=today\|week\|month` | Revenue summary + top items + daily chart |
| GET | `/api/reports/order-history?page=1&per_page=15` | Paginated history |

---

## Database Schema

```sql
categories   (id, name, icon)
menu_items   (id, category_id, name, description, price, available, created_at)
orders       (id, table_no, customer, status, subtotal, tax, discount, total, ...)
order_items  (id, order_id, item_id, quantity, unit_price, line_total)
```

Foreign key constraints are enforced by Postgres (`ON DELETE CASCADE` for order line items, `ON DELETE RESTRICT` for categories/menu items so historical orders can't be orphaned).

---

## Screenshots

> Frontend runs entirely in-browser. Open `frontend/index.html` after starting the backend.

- **POS View** — category sidebar, menu grid, live cart panel
- **Reports View** — KPI cards, top-items leaderboard, daily bar chart
- **History View** — paginated order log with inline receipt viewer

---

## Author

Built as a portfolio project demonstrating:
- RESTful API design with Flask
- Relational DB design and raw SQL queries
- Single-page frontend architecture (no framework)
- Real-time bill calculation and receipt generation
- Business analytics via aggregated SQL reporting

## 🌐 Live Demo
[https://cafe-pos-lake.vercel.app](https://cafe-pos-lake.vercel.app)
