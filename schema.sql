-- ============================================================
--  Brew & Co. Cafe Management System — Database Schema
--  Engine : MySQL 8.0+
-- ============================================================

CREATE DATABASE IF NOT EXISTS cafe_pos;
USE cafe_pos;

-- ------------------------------------------------------------
--  1. Categories
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categories (
    id    INT           NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name  VARCHAR(100)  NOT NULL UNIQUE,
    icon  VARCHAR(10)   NOT NULL DEFAULT '☕'
);

-- ------------------------------------------------------------
--  2. Menu Items
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS menu_items (
    id          INT            NOT NULL AUTO_INCREMENT PRIMARY KEY,
    category_id INT            NOT NULL,
    name        VARCHAR(200)   NOT NULL,
    description TEXT,
    price       DECIMAL(10,2)  NOT NULL CHECK (price >= 0),
    available   TINYINT(1)     NOT NULL DEFAULT 1,
    created_at  DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE RESTRICT
);

CREATE INDEX idx_menu_category ON menu_items(category_id);

-- ------------------------------------------------------------
--  3. Orders
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    id         INT           NOT NULL AUTO_INCREMENT PRIMARY KEY,
    table_no   VARCHAR(20),
    customer   VARCHAR(150),
    status     ENUM('open', 'billed', 'paid', 'cancelled') NOT NULL DEFAULT 'open',
    subtotal   DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    tax        DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    discount   DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    total      DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    notes      TEXT,
    created_at DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    billed_at  DATETIME      NULL DEFAULT NULL,
    paid_at    DATETIME      NULL DEFAULT NULL
);

CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_date   ON orders(DATE(created_at));

-- ------------------------------------------------------------
--  4. Order Line Items
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS order_items (
    id         INT           NOT NULL AUTO_INCREMENT PRIMARY KEY,
    order_id   INT           NOT NULL,
    item_id    INT           NOT NULL,
    quantity   INT           NOT NULL DEFAULT 1 CHECK (quantity > 0),
    unit_price DECIMAL(10,2) NOT NULL,
    line_total DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(id)     ON DELETE CASCADE,
    FOREIGN KEY (item_id)  REFERENCES menu_items(id) ON DELETE RESTRICT
);

CREATE INDEX idx_oi_order ON order_items(order_id);
