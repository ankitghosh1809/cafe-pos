# ☕ Brew & Co. — Cafe Management System
**Python · Flask · PostgreSQL · Vanilla JS**

A full-stack POS (Point-of-Sale) system built for small to mid-sized cafes. Handles order-taking, checkout with payment collection, receipts, sales analytics, a kitchen ticket queue, and menu management — split into a password-free customer portal, a password-protected owner portal, and a lighter-weight kitchen/staff portal — with no third-party services required beyond an optional payment gateway.

---

## What changed in this update

A full security and reliability pass, plus several new features. If you're upgrading an existing deployment, the short version:

- **Fixed a price-tampering bug**: the "Place Order" endpoint used to trust whatever `unit_price` the client sent instead of looking it up from the menu — anyone could pay whatever they wanted for anything by editing the request. Prices (and now modifier price deltas) are always resolved server-side.
- **Fixed a stored-XSS vulnerability**: review comments were rendered unescaped in the owner's Reviews panel, right next to the owner's auth token in `localStorage`. All user-generated text is now HTML-escaped before rendering.
- **Removed the legacy `POST /api/orders` endpoint** — it was unauthenticated, unused by the UI, and let anyone insert fabricated "paid" orders straight into sales reports.
- **Closed an IDOR**: order/receipt lookups are no longer freely enumerable by sequential ID — receipts now need the order's own access token (returned to whoever placed it), and the plain order-detail endpoint is owner-only.
- **Fixed a race condition** that could let two near-simultaneous "Place Order" calls create two parallel open tabs for the same table, silently orphaning one.
- Error responses no longer leak raw exception/DB text to the client.
- **The customer portal is now mobile-responsive** — it was previously a fixed 3-column desktop layout, which mattered because customers are meant to order from their own phones via a table link.
- **New: item modifiers** (size, add-ons) with server-validated pricing.
- **New: Kitchen Display** with a lightweight staff/kitchen login separate from the owner password.
- **New: real server-side Razorpay payment verification** (was previously client-trusted only — see [Razorpay Payments](#razorpay-payments)).
- **New:** per-table QR/deep-link ordering, CSV export for order history, live-updating owner dashboard (was navigation-triggered only), and a pytest suite + CI.
- Seed menu prices are now realistic INR figures (the old seed data used USD-style price points like "2.50" under a ₹ symbol).

---

## Features

### Three portals, one app
- **Landing screen** lets whoever opens the site choose **Customer**, **Kitchen**, or **Owner**.
- **Customer portal** — menu browsing and ordering only. No password, no admin surface. Mobile-friendly.
- **Kitchen portal** — password-protected with a separate, lower-privilege password. Live ticket queue only; can't touch the menu, reports, order history, or discount requests.
- **Owner portal** — password-protected. Everything else lives here, plus everything Kitchen can do.
- Shortcuts: opening the site at `#customer`, `#kitchen`, or `#owner` jumps straight to that portal. `#customer/T5` opens the customer portal locked to Table 5 (see [QR / table links](#qr--table-links)).

### Order Management
- Browse menu by category with live search, small icon for every item
- Items with **modifiers** (e.g. Size, Add-ons) open a quick customize picker; price updates live as you choose
- Add / remove items, adjust quantities on the fly
- Table selector is a dropdown, Table 1–10 (hidden/locked when opened via a per-table link)
- Apply discounts before checkout
- **Single "Place Order" checkout**: pick Cash / Card / UPI / Online inline and the order is placed and marked paid in one step

### Item Modifiers
- Owner defines option groups per item when adding it — "pick one" (e.g. Size) or "pick any" (e.g. Add-ons), each option with its own price delta
- Prices are always resolved server-side from the item's own stored modifier definitions — a request can say *which* options it wants, never what they cost

### Kitchen Display
- Live queue of every table with an active tab, oldest first, auto-refreshing
- Each ticket shows items, quantities, modifiers, and time elapsed
- One tap advances a ticket through New → Preparing → Ready → Served
- Accessible from the Kitchen portal (staff password) or the Owner portal (Kitchen tab)

### Menu Management (Owner portal)
- Add items with a name, price, description, category, optional modifiers, and a small icon (33 to choose from)
- Toggle availability, delete items (blocked with a clear message if the item has order history)
- Seeded with 40 menu items across 5 categories on first run

### Receipts
- Auto-generated itemised receipt per order, including payment method and any modifiers chosen
- Shows subtotal, 5% GST, discount, and grand total
- Print-ready modal

### Sales Reporting (Owner portal)
- Revenue, order count, average ticket size, tax collected
- Top-5 selling items (by quantity and revenue)
- Daily revenue bar chart — switchable between Today / 7 days / 30 days

### Order History (Owner portal)
- Sorted by date (toggle newest/oldest first)
- Small calendar to jump to any specific day's orders
- **Export to CSV** for accounting/reconciliation
- Delete a past order record
- Shows who placed each order (customer / owner) and how it was paid

### Table Tabs
- Each table keeps a running, unpaid "tab" — the customer can order in multiple
  rounds (coffee now, dessert later) and everything accumulates onto one bill
- Switching tables shows that table's own in-progress order only; nothing
  bleeds between tables
- A database-level constraint (not just application logic) guarantees at most
  one open tab per table, even under concurrent requests
- While ordering, the customer never sees a running total — prices only
  appear at **View Bill & Pay**, which pulls the real accumulated tab

### QR / Table Links
- Owner → Menu → Tables & Servers has a **Copy ordering link** button per table
- That link (`#customer/T5`) opens the customer portal pre-locked to that table — no table dropdown, no risk of a customer accidentally (or deliberately) ordering onto a different table's tab
- Paste the link into any QR generator to print a physical code per table

### Payment (Cash / Card / UPI / Online via Razorpay)
- Customers choose **Cash** or **Online** at Pay Bill; Owner also has **Card** and **UPI** for recording counter payments
- Online payment opens Razorpay Checkout for a server-computed order (see [Razorpay Payments](#razorpay-payments)) and is signature-verified server-side before being accepted

### Discount Requests
- Customer can request a discount on their current tab from the Pay Bill screen
- Owner sees it on the **Requests** tab with the table number and live order
  amount, and approves with a specific percentage (or declines)
- Once approved, the percentage is applied automatically to that table's bill
- The owner dashboard now polls in the background, so a new request shows up without needing to switch views

### Servers &amp; Reviews
- Each table (1–10) has an assigned server, managed from Owner → Menu →
  Tables &amp; Servers
- The customer sees "Your server: [name]" once they pick a table
- After paying, the customer can rate the server and the cafe (1–5 stars) and
  leave a comment; Owner sees all reviews plus averages under Reports

---

## Tech Stack

| Layer    | Technology                  |
|----------|-----------------------------|
| Backend  | Python 3.11+, Flask 3, PostgreSQL (pooled via `psycopg2.pool`) |
| Frontend | HTML5, CSS3 (custom, responsive), Vanilla JS (ES2020) |
| Database | PostgreSQL via `psycopg2` (Neon in production) |
| Auth     | Stdlib HMAC-signed tokens (no extra dependency) — two roles, owner and staff |
| Payments | Razorpay Checkout + server-side order creation/signature verification (stdlib `urllib`, no SDK dependency) |
| Testing  | pytest against a real Postgres instance; GitHub Actions CI |
| Fonts    | Playfair Display + DM Sans (Google Fonts) |

---

## Project Structure

```
cafe-pos/
├── .github/workflows/
│   └── tests.yml          # CI: pytest + api/backend drift check, on every push
├── api/
│   ├── index.py            # Vercel serverless entry point
│   └── app.py               # Flask app — deployed copy, kept in sync via scripts/sync_backend.sh
├── backend/
│   ├── app.py                # Flask app — THE source of truth, edit this one
│   ├── requirements.txt
│   └── tests/                # pytest suite (real Postgres, not mocked)
├── frontend/
│   └── index.html          # single-file SPA (icons, portals, everything)
├── scripts/
│   └── sync_backend.sh     # copies backend/app.py -> api/app.py; --check mode for CI
├── requirements.txt         # used by Vercel's build (mirrors backend/requirements.txt)
├── vercel.json               # routes /api/** to api/index.py, everything else to frontend/
├── schema.sql                 # standalone DB schema reference (app also self-creates/migrates this)
├── .env.example                # copy to .env locally
└── README.md
```

### Why `api/app.py` is a separate file, not an import

This project's `vercel.json` uses Vercel's legacy `builds` array config. Per Vercel's own docs, once `builds` is specified, **only that builder's own output is bundled** — `functions`/`includeFiles` (the mechanism that would let `api/index.py` cleanly import `../backend/app.py`) can't even be combined with `builds`. Rather than gamble with the only deployment path this app has, `api/app.py` stays a real, physical file, and staying in sync is enforced by tooling instead of memory:

```bash
./scripts/sync_backend.sh          # copy backend/app.py -> api/app.py
./scripts/sync_backend.sh --check  # fails if they've drifted (what CI runs)
```

Run the first one after editing `backend/app.py`, before committing. CI will catch it if you forget.

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
Tables are created (or migrated, if the database already exists from before this update) automatically against whatever `DATABASE_URL` points to. On a brand-new database, the 40-item demo menu plus 30 days of sample orders are seeded too. If you're upgrading a database that already has orders in it, migration also folds any duplicate open tabs it finds down to one per table (a pre-existing bug this update fixes — see [changelog](#what-changed-in-this-update)) before adding the constraint that prevents new ones.

### Owner password (required for the Owner portal)

Set `OWNER_PASSWORD` in `.env` (or in Vercel's environment variables for the deployed site):

```
OWNER_PASSWORD=choose-a-real-password-here
```

There is deliberately **no built-in default password** — this repo is public, so a hardcoded fallback would mean anyone reading the source could log into any deployment that forgot to set one. Until `OWNER_PASSWORD` is set, the Owner login screen will show a message saying so instead of a generic "wrong password."

### Staff / Kitchen password (optional, required for the Kitchen portal)

```
STAFF_PASSWORD=a-different-password-for-kitchen-staff
```

Same "no default" reasoning as above. Until this is set, the Kitchen login screen will say so. An owner token also works on every staff/kitchen route, so the owner never needs a second login.

Optionally also set `SECRET_KEY` (any long random string) — used to sign login tokens. If you don't set one, it's derived from `OWNER_PASSWORD` so tokens still survive server restarts; a dedicated `SECRET_KEY` is still the more correct choice for a real deployment.

### 3. Frontend

Open `frontend/index.html` directly in your browser — no build step needed. You'll land on the portal picker; choose **Customer**, **Kitchen**, or **Owner**.

### 4. Running tests

```bash
cd backend
pip install pytest
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/cafepos_test  # a scratch DB — TRUNCATEd between every test
export OWNER_PASSWORD=testowner123
export STAFF_PASSWORD=teststaff123
export SECRET_KEY=any-string-for-local-testing
pytest
```

Tests run against a real Postgres database (not a mock or SQLite stand-in) since the app leans on Postgres-specific features — JSONB, partial unique indexes, window functions — that a fake would let slide silently. CI (`.github/workflows/tests.yml`) spins up a disposable Postgres service container automatically; nothing extra to configure there.

---

## Razorpay Payments

The "Online" payment option uses [Razorpay Checkout](https://razorpay.com/docs/payments/payment-gateway/web-integration/standard/). The flow is now the real, server-verified one:

1. Tapping "Online" calls `POST /api/tables/:no/create-payment-order`, which computes the table's actual current total **server-side** and asks Razorpay to mint an order for exactly that amount.
2. Checkout opens using that server-created order — it can only ever charge what the table actually owes, never a client-supplied figure.
3. On completion, `POST /api/tables/:no/pay` verifies Razorpay's signature with HMAC-SHA256 against the `key_secret`, checked against the `razorpay_order_id` **this server minted for this order** (not one echoed back by the request) — Razorpay's own docs specifically call out verifying against your own stored order_id rather than a client-supplied one, since a signature from a real but unrelated payment could otherwise be replayed to settle a different bill.

To turn this on, add both to your environment (locally in `.env`, and in Vercel):

```
RAZORPAY_KEY_ID=rzp_...
RAZORPAY_KEY_SECRET=...          # never commit this or paste it in chat
```

`key_id` is safe client-side (same idea as a Stripe publishable key) and is served to the frontend via `GET /api/config`; `key_secret` never leaves the server. Until both are set, the Online option is hidden from checkout and `create-payment-order` returns a clear "not configured" error rather than silently failing.

---

## API Reference

### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/owner/login` | `{password}` → `{token, expires_in}`. Owner-only routes need `Authorization: Bearer <token>` |
| GET | `/api/owner/verify` | Checks whether the current token is still valid |
| POST | `/api/staff/login` | `{password}` → `{token, expires_in}`. Lower-privilege role: Kitchen queue only |
| GET | `/api/config` | Public runtime config (Razorpay `key_id`, whether online payment is configured) |

### Menu
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/menu` | Full menu with categories and modifiers (public — cached 30s) |
| POST | `/api/menu/items` 🔒 | Add a menu item (`image_key` picks its icon, `modifiers` optional) |
| PUT | `/api/menu/items/:id` 🔒 | Update name / price / availability / icon / modifiers |
| DELETE | `/api/menu/items/:id` 🔒 | Remove an item (409 if it has order history) |

### Orders
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/orders` 🔒 | List orders (filter by `?status=`) |
| GET | `/api/orders/:id` 🔒 | Order detail with line items |
| DELETE | `/api/orders/:id` 🔒 | Delete an order record |
| PATCH | `/api/orders/:id/status` 🔒 | Manually override status |
| PATCH | `/api/orders/:id/kitchen-status` 🔧 | Advance kitchen ticket status (`new`/`preparing`/`ready`/`served`) |
| GET | `/api/orders/:id/receipt?token=...` | Formatted receipt — needs the order's own `receipt_token` unless called as owner |

### Tables &amp; Tabs
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/tables` | All 10 tables with their assigned server |
| PUT | `/api/tables/:no/server` 🔒 | Assign/rename a table's server |
| GET | `/api/tables/status` 🔒 | Which tables have an open tab right now, for how much, and kitchen status |
| GET | `/api/tables/:no/tab` | The table's current running order (or `null`) |
| POST | `/api/tables/:no/items` | Append items to the table's tab — `{items:[{item_id, quantity, modifiers?}]}`, price always resolved server-side |
| POST | `/api/tables/:no/create-payment-order` | Step 1 of online payment — mints a Razorpay order for the table's real current total |
| POST | `/api/tables/:no/pay` | Settle the tab: `{payment_method, razorpay_payment_id?, razorpay_signature?}` |

### Kitchen
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/kitchen/queue` 🔧 | Active tickets (open tabs not yet served), oldest first |

### Discount Requests
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/tables/:no/discount-request` | Customer asks for a discount on their current tab |
| GET | `/api/tables/:no/discount-status` | Poll the latest request's status for that table |
| GET | `/api/discount-requests?status=pending` 🔒 | Owner's queue |
| POST | `/api/discount-requests/:id/resolve` 🔒 | `{action: "approve"\|"deny", discount_percent?}` |

### Reviews
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/reviews` | Submit a rating (`server_rating`/`cafe_rating` 1–5, `comment`) |
| GET | `/api/reviews` 🔒 | All reviews + average ratings |

### Reports
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/reports/sales?period=today\|week\|month` 🔒 | Revenue summary + top items + daily chart |
| GET | `/api/reports/order-history?page=1&per_page=15&sort=desc&date=YYYY-MM-DD` 🔒 | Paginated, sortable, optionally filtered to one day |
| GET | `/api/reports/order-history/export?date=YYYY-MM-DD` 🔒 | Same data as CSV |

🔒 = requires owner token. 🔧 = requires owner **or** staff token.

---

## Database Schema

```sql
categories        (id, name, icon)
menu_items        (id, category_id, name, description, price, available, image_key, modifiers, created_at)
orders             (id, table_no, customer, status, kitchen_status, subtotal, tax, discount, discount_percent,
                    total, payment_method, payment_ref, razorpay_order_id, receipt_token, placed_by, notes,
                    created_at, billed_at, paid_at)
order_items        (id, order_id, item_id, quantity, unit_price, line_total, modifiers)
table_servers      (table_no, server_name)
discount_requests  (id, table_no, order_id, requested_amount, status, discount_percent, created_at, resolved_at)
reviews            (id, order_id, table_no, server_name, server_rating, cafe_rating, comment, created_at)
```

Foreign key constraints are enforced by Postgres (`ON DELETE CASCADE` for order line items/discount requests, `ON DELETE RESTRICT` for categories/menu items so historical orders can't be orphaned). A partial unique index (`orders(table_no) WHERE status='open'`) guarantees at most one open tab per table at the database level, not just in application logic.

Every new column/table across every feature round is added automatically via `CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` on startup, so upgrading an existing database is a non-event — nothing is dropped or re-seeded. The one-open-tab constraint specifically checks for and resolves any pre-existing duplicate open orders before adding itself, so it won't fail to apply on a database that's been live since before this fix.

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

## Screenshots

> Frontend runs entirely in-browser. Open `frontend/index.html` after starting the backend.

- **Landing** — Customer / Kitchen / Owner picker
- **POS View** — category sidebar, menu grid with icons and modifier picker, live cart panel, one-step checkout
- **Kitchen Display** — live ticket queue with one-tap status advance
- **Menu Management** — add/toggle/delete items, modifier editor (Owner)
- **Reports View** — KPI cards, top-items leaderboard, daily bar chart (Owner)
- **History View** — sortable, calendar-filterable order log with CSV export and delete (Owner)

---

## Author

Built as a portfolio project demonstrating:
- RESTful API design with Flask, including a two-role auth layer built from stdlib primitives
- Relational DB design, raw SQL queries, and safe zero-downtime schema migrations — including self-healing a pre-existing data-integrity bug during migration rather than just failing on it
- Security-conscious backend design: server-authoritative pricing, output escaping, access-token-gated resource access, and third-party payment signature verification
- Connection-pooling and query-count optimization against a real remote Postgres provider (Neon)
- Single-page frontend architecture (no framework) with role-gated views and a responsive, mobile-first ordering flow
- Real-time bill calculation, payment collection, and receipt generation
- Business analytics via aggregated SQL reporting
- Automated testing (pytest against a real database) and CI (GitHub Actions)

## 🌐 Live Demo
[https://cafe-pos-lake.vercel.app](https://cafe-pos-lake.vercel.app)
