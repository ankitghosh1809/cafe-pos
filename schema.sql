-- ============================================================
--  Brew & Co. Cafe Management System — Database Schema
--  Engine : PostgreSQL 14+ (tested against 16, incl. Neon)
--
--  NOTE: api/app.py (and backend/app.py) create this same schema
--  automatically on startup via CREATE TABLE IF NOT EXISTS, and
--  seed demo data the first time the database is empty. You do
--  NOT need to run this file for the app to work. It's kept here
--  as a standalone reference — e.g. to inspect the schema, or to
--  run manually in the Neon SQL editor before the app ever connects.
-- ============================================================

-- ------------------------------------------------------------
--  1. Categories
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categories (
    id   SERIAL        PRIMARY KEY,
    name VARCHAR(100)  NOT NULL UNIQUE,
    icon VARCHAR(10)   NOT NULL DEFAULT '☕'
);

-- ------------------------------------------------------------
--  2. Menu Items
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS menu_items (
    id          SERIAL         PRIMARY KEY,
    category_id INTEGER        NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    name        VARCHAR(200)   NOT NULL,
    description TEXT,
    price       NUMERIC(10,2)  NOT NULL CHECK (price >= 0),
    available   SMALLINT       NOT NULL DEFAULT 1,
    image_key   VARCHAR(40)    NOT NULL DEFAULT 'default',
    created_at  TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_menu_category ON menu_items(category_id);

-- ------------------------------------------------------------
--  3. Orders
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    id             SERIAL        PRIMARY KEY,
    table_no       VARCHAR(20),
    customer       VARCHAR(150),
    status         VARCHAR(20)   NOT NULL DEFAULT 'open'
                   CHECK (status IN ('open', 'billed', 'paid', 'cancelled')),
    subtotal       NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    tax            NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    discount       NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    total          NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    payment_method VARCHAR(20),
    placed_by      VARCHAR(10)   NOT NULL DEFAULT 'customer',
    notes          TEXT,
    created_at     TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    billed_at      TIMESTAMP     NULL DEFAULT NULL,
    paid_at        TIMESTAMP     NULL DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_date   ON orders((created_at::date));

-- ------------------------------------------------------------
--  4. Order Line Items
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS order_items (
    id         SERIAL        PRIMARY KEY,
    order_id   INTEGER       NOT NULL REFERENCES orders(id)     ON DELETE CASCADE,
    item_id    INTEGER       NOT NULL REFERENCES menu_items(id) ON DELETE RESTRICT,
    quantity   INTEGER       NOT NULL DEFAULT 1 CHECK (quantity > 0),
    unit_price NUMERIC(10,2) NOT NULL,
    line_total NUMERIC(10,2) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_oi_order ON order_items(order_id);
