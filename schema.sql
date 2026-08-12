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
    modifiers   JSONB,         -- optional list of {name, type, required, options:[{label, delta}]}
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
    kitchen_status VARCHAR(20)   NOT NULL DEFAULT 'new'
                   CHECK (kitchen_status IN ('new','preparing','ready','served')),
    subtotal       NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    tax            NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    discount       NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    discount_percent NUMERIC(5,2) NOT NULL DEFAULT 0,
    total          NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    payment_method VARCHAR(20),
    payment_ref    VARCHAR(120),
    razorpay_order_id VARCHAR(64),  -- set when online checkout starts; verified against on payment
    receipt_token  VARCHAR(64),     -- required to view this order's receipt unless authenticated as owner
    placed_by      VARCHAR(10)   NOT NULL DEFAULT 'customer',
    notes          TEXT,
    created_at     TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    billed_at      TIMESTAMP     NULL DEFAULT NULL,
    paid_at        TIMESTAMP     NULL DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_date   ON orders((created_at::date));
-- Guarantees at most one open tab per table, even under concurrent
-- requests — see README changelog.
CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_one_open_per_table ON orders(table_no) WHERE status = 'open';

-- ------------------------------------------------------------
--  4. Order Line Items
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS order_items (
    id         SERIAL        PRIMARY KEY,
    order_id   INTEGER       NOT NULL REFERENCES orders(id)     ON DELETE CASCADE,
    item_id    INTEGER       NOT NULL REFERENCES menu_items(id) ON DELETE RESTRICT,
    quantity   INTEGER       NOT NULL DEFAULT 1 CHECK (quantity > 0),
    unit_price NUMERIC(10,2) NOT NULL,
    line_total NUMERIC(10,2) NOT NULL,
    modifiers  JSONB          -- resolved selections for this line: [{group, option, delta}]
);

CREATE INDEX IF NOT EXISTS idx_oi_order ON order_items(order_id);

-- ------------------------------------------------------------
--  5. Table Server Assignments
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS table_servers (
    table_no    VARCHAR(10) PRIMARY KEY,
    server_name VARCHAR(100) NOT NULL DEFAULT 'Unassigned'
);

-- ------------------------------------------------------------
--  6. Discount Requests (customer asks, owner approves a %)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS discount_requests (
    id               SERIAL PRIMARY KEY,
    table_no         VARCHAR(10) NOT NULL,
    order_id         INTEGER REFERENCES orders(id) ON DELETE CASCADE,
    requested_amount NUMERIC(10,2) NOT NULL,
    status           VARCHAR(20) NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','approved','denied','used')),
    discount_percent NUMERIC(5,2),
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at      TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_discount_req_order ON discount_requests(order_id, status);

-- ------------------------------------------------------------
--  7. Reviews (server + cafe rating, left after paying)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reviews (
    id            SERIAL PRIMARY KEY,
    order_id      INTEGER REFERENCES orders(id) ON DELETE SET NULL,
    table_no      VARCHAR(10),
    server_name   VARCHAR(100),
    server_rating SMALLINT CHECK (server_rating BETWEEN 1 AND 5),
    cafe_rating   SMALLINT CHECK (cafe_rating BETWEEN 1 AND 5),
    comment       TEXT,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
