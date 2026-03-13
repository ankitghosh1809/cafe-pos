-- ============================================================
--  Brew & Co. Cafe Management System — Database Schema
--  Engine : SQLite 3  |  journal_mode : WAL
-- ============================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------
--  1. Categories
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categories (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT    NOT NULL UNIQUE,
    icon  TEXT    NOT NULL DEFAULT '☕'
);

-- ------------------------------------------------------------
--  2. Menu Items
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS menu_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL
                        REFERENCES categories(id) ON DELETE RESTRICT,
    name        TEXT    NOT NULL,
    description TEXT,
    price       REAL    NOT NULL CHECK (price >= 0),
    available   INTEGER NOT NULL DEFAULT 1 CHECK (available IN (0, 1)),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_menu_category ON menu_items(category_id);

-- ------------------------------------------------------------
--  3. Orders
--     status flow: open → billed → paid
--                  open → cancelled
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    table_no   TEXT,
    customer   TEXT,
    status     TEXT    NOT NULL DEFAULT 'open'
                       CHECK (status IN ('open', 'billed', 'paid', 'cancelled')),
    subtotal   REAL    NOT NULL DEFAULT 0,
    tax        REAL    NOT NULL DEFAULT 0,   -- 5 % GST
    discount   REAL    NOT NULL DEFAULT 0,
    total      REAL    NOT NULL DEFAULT 0,
    notes      TEXT,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    billed_at  TEXT,
    paid_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_date   ON orders(date(created_at));

-- ------------------------------------------------------------
--  4. Order Line Items
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS order_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL
                       REFERENCES orders(id) ON DELETE CASCADE,
    item_id    INTEGER NOT NULL
                       REFERENCES menu_items(id) ON DELETE RESTRICT,
    quantity   INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    unit_price REAL    NOT NULL,           -- snapshot of price at time of order
    line_total REAL    NOT NULL            -- quantity * unit_price
);

CREATE INDEX IF NOT EXISTS idx_oi_order ON order_items(order_id);

-- ============================================================
--  Useful reporting queries
-- ============================================================

-- Daily revenue (last 30 days)
-- SELECT date(created_at) AS day,
--        COUNT(*)          AS orders,
--        SUM(total)        AS revenue
-- FROM   orders
-- WHERE  status = 'paid'
--   AND  date(created_at) >= date('now', '-30 days')
-- GROUP  BY day
-- ORDER  BY day;

-- Top-5 selling items (by quantity)
-- SELECT mi.name,
--        SUM(oi.quantity)   AS qty_sold,
--        SUM(oi.line_total) AS revenue
-- FROM   order_items oi
-- JOIN   menu_items mi ON mi.id = oi.item_id
-- JOIN   orders     o  ON o.id  = oi.order_id
-- WHERE  o.status = 'paid'
-- GROUP  BY mi.id
-- ORDER  BY qty_sold DESC
-- LIMIT  5;
