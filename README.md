# ☕ Brew & Co. — Cafe Management System
**Python · Flask · SQLite · Vanilla JS**

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
| Backend  | Python 3.11+, Flask 3, SQLite |
| Frontend | HTML5, CSS3 (custom), Vanilla JS (ES2020) |
| Database | SQLite via Python `sqlite3`  |
| Fonts    | Playfair Display + DM Sans (Google Fonts) |

---

## Project Structure

```
cafe_pos/
├── backend/
│   ├── app.py            # Flask app — all routes
│   ├── requirements.txt
│   └── cafe.db           # auto-created on first run
├── frontend/
│   └── index.html        # single-file SPA
├── schema.sql            # standalone DB schema reference
└── README.md
```

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
python app.py
```

The server starts at **http://localhost:5000**.  
`cafe.db` is created automatically with seed data on the first run.

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

Foreign key constraints and a WAL journal are enabled by default.

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
