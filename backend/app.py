import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import psycopg2.extras
import psycopg2.extensions
import psycopg2.pool
import psycopg2.errors
from psycopg2.extras import execute_values
import os
from dotenv import load_dotenv
from datetime import datetime, date, timedelta
import random
import time
import hmac
import hashlib
import base64
import json
from functools import wraps

# Postgres NUMERIC columns (price, subtotal, tax, total, ...) come back from
# psycopg2 as decimal.Decimal by default. Flask's JSON encoder then renders
# those as *strings* (e.g. "3.50") to avoid float rounding in transit, which
# silently breaks arithmetic wherever a value read from the API flows back
# into a calculation (e.g. unit_price in a new order). Casting NUMERIC -> float
# at the driver level keeps every money field a real JSON number end-to-end.
DEC2FLOAT = psycopg2.extensions.new_type(
    psycopg2.extensions.DECIMAL.values, "DEC2FLOAT",
    lambda value, curs: float(value) if value is not None else None,
)
psycopg2.extensions.register_type(DEC2FLOAT)

load_dotenv()
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}}, allow_headers=["Content-Type", "Authorization"])
TAX_RATE = 0.05
VALID_PAYMENT_METHODS = {"cash", "card", "upi"}

# ══════════════════════════════════════════════════════════════════════════
# CONNECTION HANDLING — pooled, with stale-connection retry
# ══════════════════════════════════════════════════════════════════════════
# The single biggest performance fix in this file: the old code called
# psycopg2.connect() fresh for *every single query* (get_menu() alone opened
# 6 connections — 1 for categories + 1 per category for items). Against a
# remote DB (Neon) each new connection pays a real network round trip + TLS
# handshake + occasional compute-wake cost, so pages that ran several
# queries paid that tax several times over. A small pool means requests
# reuse an already-open connection instead of re-paying that cost.

def _db_url():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Add it in Vercel → Settings → Environment Variables."
        )
    return db_url

def _raw_connect():
    """A one-off, unpooled connection — used only for the one-time startup
    schema/seed check, which runs once at import time, not per-request."""
    return psycopg2.connect(_db_url(), connect_timeout=8)

_pool = None

def _get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            1, 5, dsn=_db_url(), connect_timeout=8,
            keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3,
        )
    return _pool

class _Conn:
    """Borrow a pooled connection; always hand it back afterwards — unless
    it turned out to be dead (Neon can drop idle connections server-side),
    in which case discard it instead of returning a broken connection to
    the pool for the next request to trip over."""
    def __enter__(self):
        self.pool = _get_pool()
        self.conn = self.pool.getconn()
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None and isinstance(exc, (psycopg2.OperationalError, psycopg2.InterfaceError)):
            try:
                self.pool.putconn(self.conn, close=True)
            except Exception:
                pass
            return False
        try:
            if exc_type:
                self.conn.rollback()
            else:
                self.conn.commit()
        except Exception:
            pass
        try:
            self.pool.putconn(self.conn)
        except Exception:
            pass
        return False


def query(sql, params=None, fetch=False, retries=1):
    """Run one statement on a pooled connection. Retries once (with a fresh
    connection) if the pooled one turned out to be stale."""
    last_err = None
    for _ in range(retries + 1):
        try:
            with _Conn() as conn:
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute(sql, params or ())
                if fetch:
                    result = [dict(r) for r in cur.fetchall()]
                else:
                    row = cur.fetchone()
                    result = list(row.values())[0] if row else cur.rowcount
                cur.close()
                return result
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            last_err = e
            continue
    raise last_err


def run(fn, retries=1):
    """Run fn(conn) on ONE checked-out pooled connection — for handlers that
    need several statements to happen atomically / in a single round-trip
    budget (e.g. insert an order + batch-insert its line items + read the
    combined result back), instead of paying a separate pool checkout for
    every statement."""
    last_err = None
    for _ in range(retries + 1):
        try:
            with _Conn() as conn:
                return fn(conn)
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            last_err = e
            continue
    raise last_err


# ══════════════════════════════════════════════════════════════════════════
# AUTH — owner-only password gate (customer portal stays password-free)
# ══════════════════════════════════════════════════════════════════════════
# Deliberately dependency-free (stdlib hmac/hashlib only) rather than adding
# a JWT library for one signed field. OWNER_PASSWORD must be set explicitly
# (no baked-in default) since this project's source is public on GitHub —
# shipping a hardcoded fallback password would mean anyone reading the repo
# could log in to any deployment that forgot to override it.
OWNER_PASSWORD = os.getenv("OWNER_PASSWORD")
TOKEN_TTL = 12 * 3600  # owner stays logged in for 12h before needing to re-enter the password

def _derive_secret_key():
    env_secret = os.getenv("SECRET_KEY")
    if env_secret:
        return env_secret
    # Stable fallback across restarts / serverless cold starts without
    # requiring yet another mandatory env var: derived from OWNER_PASSWORD,
    # so a token issued before a cold start is still valid after one.
    # Setting a dedicated SECRET_KEY is still recommended — see README.
    basis = OWNER_PASSWORD or "brew-and-co-unconfigured"
    return hashlib.sha256((basis + "::brewco-static-salt-v1").encode()).hexdigest()

SECRET_KEY = _derive_secret_key()

def make_token(payload, max_age=TOKEN_TTL):
    body = dict(payload)
    body["_exp"] = int(time.time()) + max_age
    raw = json.dumps(body, separators=(",", ":")).encode()
    b64 = base64.urlsafe_b64encode(raw).rstrip(b"=")
    sig = hmac.new(SECRET_KEY.encode(), b64, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=")
    return (b64 + b"." + sig_b64).decode()

def verify_token(token):
    try:
        b64, sig_b64 = token.encode().split(b".")
        expected = hmac.new(SECRET_KEY.encode(), b64, hashlib.sha256).digest()
        expected_b64 = base64.urlsafe_b64encode(expected).rstrip(b"=")
        if not hmac.compare_digest(sig_b64, expected_b64):
            return None
        pad = b"=" * (-len(b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(b64 + pad))
        if payload.get("_exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None

def _bearer_token():
    auth = request.headers.get("Authorization", "")
    return auth[7:].strip() if auth.startswith("Bearer ") else None

def _current_owner_payload():
    token = _bearer_token()
    if not token:
        return None
    payload = verify_token(token)
    return payload if payload and payload.get("role") == "owner" else None

def owner_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not _current_owner_payload():
            return jsonify({"error": "unauthorized", "message": "Owner authentication required"}), 401
        return fn(*args, **kwargs)
    return wrapper

# very small in-memory throttle on login attempts (per-process; fine for a
# single small-cafe deployment, resets on cold start)
_login_attempts = {}

def _login_is_rate_limited(ip):
    now = time.time()
    count, window_start = _login_attempts.get(ip, (0, now))
    if now - window_start > 60:
        count, window_start = 0, now
        _login_attempts[ip] = (count, window_start)
    return count >= 8

def _login_record_failure(ip):
    count, window_start = _login_attempts.get(ip, (0, time.time()))
    _login_attempts[ip] = (count + 1, window_start)


# ══════════════════════════════════════════════════════════════════════════
# SCHEMA + SEED (Postgres)
# ══════════════════════════════════════════════════════════════════════════
# Creates tables on first run, migrates already-existing databases (adding
# the columns this update needs), and seeds demo menu/order data if the DB
# is empty. Safe on every cold start.

def init_db():
    conn = _raw_connect()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id   SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE,
            icon VARCHAR(10) NOT NULL DEFAULT '☕'
        );

        CREATE TABLE IF NOT EXISTS menu_items (
            id          SERIAL PRIMARY KEY,
            category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
            name        VARCHAR(200) NOT NULL,
            description TEXT,
            price       NUMERIC(10,2) NOT NULL CHECK (price >= 0),
            available   SMALLINT NOT NULL DEFAULT 1,
            image_key   VARCHAR(40) NOT NULL DEFAULT 'default',
            created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_menu_category ON menu_items(category_id);

        CREATE TABLE IF NOT EXISTS orders (
            id             SERIAL PRIMARY KEY,
            table_no       VARCHAR(20),
            customer       VARCHAR(150),
            status         VARCHAR(20) NOT NULL DEFAULT 'open'
                           CHECK (status IN ('open','billed','paid','cancelled')),
            subtotal       NUMERIC(10,2) NOT NULL DEFAULT 0.00,
            tax            NUMERIC(10,2) NOT NULL DEFAULT 0.00,
            discount       NUMERIC(10,2) NOT NULL DEFAULT 0.00,
            total          NUMERIC(10,2) NOT NULL DEFAULT 0.00,
            payment_method VARCHAR(20),
            placed_by      VARCHAR(10) NOT NULL DEFAULT 'customer',
            notes          TEXT,
            created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            billed_at      TIMESTAMP,
            paid_at        TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
        CREATE INDEX IF NOT EXISTS idx_orders_date ON orders((created_at::date));

        CREATE TABLE IF NOT EXISTS order_items (
            id         SERIAL PRIMARY KEY,
            order_id   INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            item_id    INTEGER NOT NULL REFERENCES menu_items(id) ON DELETE RESTRICT,
            quantity   INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
            unit_price NUMERIC(10,2) NOT NULL,
            line_total NUMERIC(10,2) NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_oi_order ON order_items(order_id);
    """)
    conn.commit()

    # migrations for databases that already existed before this update
    cur.execute("""
        ALTER TABLE menu_items ADD COLUMN IF NOT EXISTS image_key VARCHAR(40) NOT NULL DEFAULT 'default';
        ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_method VARCHAR(20);
        ALTER TABLE orders ADD COLUMN IF NOT EXISTS placed_by VARCHAR(10) NOT NULL DEFAULT 'customer';
    """)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM categories")
    if cur.fetchone()[0] == 0:
        _seed(cur)
        conn.commit()

    cur.close()
    conn.close()


def _seed(cur):
    cats = [
        ("Hot Beverages", "☕"),
        ("Cold Beverages", "🧋"),
        ("Snacks", "🥐"),
        ("Meals", "🍽️"),
        ("Desserts", "🍰"),
    ]
    cat_ids = []
    for name, icon in cats:
        cur.execute("INSERT INTO categories(name,icon) VALUES(%s,%s) RETURNING id", (name, icon))
        cat_ids.append(cur.fetchone()[0])

    # (category_index, name, description, price, image_key)
    items = [
        (0, "Espresso", "Rich single-shot espresso", 2.50, "espresso"),
        (0, "Cappuccino", "Espresso with steamed milk foam", 3.50, "cappuccino"),
        (0, "Flat White", "Double ristretto with velvety micro-foam", 4.00, "cappuccino"),
        (0, "Chai Latte", "Spiced tea with steamed milk", 3.75, "chai"),
        (0, "Masala Chai", "Bold Assam tea, whole spices, jaggery", 2.00, "chai"),
        (0, "Filter Coffee", "South Indian decoction coffee, frothed milk", 2.75, "filter-coffee"),
        (0, "Americano", "Espresso lengthened with hot water", 2.75, "espresso"),
        (0, "Hot Chocolate", "Belgian cocoa, steamed milk, marshmallow", 3.50, "hot-chocolate"),

        (1, "Cold Brew", "12-hour slow-extracted cold brew", 4.50, "cold-brew"),
        (1, "Iced Caramel Latte", "Espresso, milk, caramel over ice", 4.75, "iced-latte"),
        (1, "Mango Smoothie", "Fresh mango blended with yogurt", 4.25, "fruit-shake"),
        (1, "Sparkling Lemonade", "House-made with fresh zest", 3.25, "lemonade"),
        (1, "Cold Coffee", "Blended coffee, milk, ice, chocolate shavings", 3.75, "iced-latte"),
        (1, "Masala Lassi", "Spiced yogurt cooler, roasted cumin", 3.25, "lassi"),
        (1, "Fresh Lime Soda", "Sweet or salted, made to order", 2.25, "lemonade"),
        (1, "Chocolate Milkshake", "Belgian cocoa ice cream, malt, whipped cream", 4.25, "fruit-shake"),

        (2, "Butter Croissant", "Flaky, all-butter French croissant", 2.75, "croissant"),
        (2, "Avocado Toast", "Smashed avo on sourdough with sea salt", 6.50, "toast"),
        (2, "Club Sandwich", "Triple-decker with chicken & bacon", 7.00, "sandwich"),
        (2, "Cheese Scone", "Warm cheddar scone with butter", 2.25, "scone"),
        (2, "Samosa (2 pcs)", "Crisp pastry, spiced potato & pea filling", 2.50, "samosa"),
        (2, "Veg Puff", "Flaky puff pastry, curried vegetables", 2.25, "samosa"),
        (2, "French Fries", "Crisp-fried, tossed in peri-peri salt", 3.00, "fries"),
        (2, "Loaded Nachos", "Corn chips, cheese sauce, salsa, jalapenos", 4.50, "nachos"),
        (2, "Vada Pav", "Spiced potato fritter, soft bun, chutneys", 2.00, "bun-snack"),

        (3, "Eggs Benedict", "Poached eggs, ham, hollandaise on muffin", 9.50, "eggs-benedict"),
        (3, "Granola Bowl", "House granola, Greek yogurt, seasonal fruit", 7.00, "granola-bowl"),
        (3, "Pasta Primavera", "Penne with garden vegetables, olive oil", 10.50, "pasta"),
        (3, "Margherita Pizza", "Wood-fired, San Marzano tomato, fresh basil", 7.50, "pizza"),
        (3, "Veg Fried Rice", "Wok-tossed rice, garden vegetables, soy", 6.00, "asian-bowl"),
        (3, "Paneer Tikka Wrap", "Grilled paneer, mint chutney, onion, tortilla", 5.75, "wrap"),
        (3, "Chicken Burger", "Grilled patty, lettuce, cheese, house sauce", 6.50, "burger"),
        (3, "Masala Maggi", "Instant noodles, tomato masala, vegetables", 3.50, "asian-bowl"),

        (4, "Tiramisu", "Classic Italian layered dessert", 5.50, "tiramisu"),
        (4, "Chocolate Brownie", "Fudgy brownie, served warm with cream", 4.00, "brownie"),
        (4, "Cheesecake Slice", "New York-style, berry compote", 5.00, "cheesecake"),
        (4, "Gulab Jamun (2 pcs)", "Warm milk-solid dumplings, cardamom syrup", 3.00, "gulab-jamun"),
        (4, "Chocolate Lava Cake", "Molten centre, vanilla ice cream", 4.75, "lava-cake"),
        (4, "Vanilla Ice Cream", "Two scoops, choice of topping", 2.75, "ice-cream"),
        (4, "Red Velvet Cupcake", "Cream cheese frosting", 3.25, "cupcake"),
    ]
    item_rows = []
    for cat_idx, name, desc, price, image_key in items:
        cur.execute(
            "INSERT INTO menu_items(category_id,name,description,price,image_key) VALUES(%s,%s,%s,%s,%s) RETURNING id",
            (cat_ids[cat_idx], name, desc, price, image_key),
        )
        item_rows.append((cur.fetchone()[0], price))

    # 30 days of demo order history so Reports/History aren't empty on first run
    today = date.today()
    payment_choices = ["cash", "card", "upi"]
    for d in range(30, 0, -1):
        day = today - timedelta(days=d)
        for _ in range(random.randint(15, 35)):
            ts = datetime.combine(day, datetime.min.time()).replace(
                hour=random.randint(8, 20), minute=random.randint(0, 59)
            )
            table_no = f"T{random.randint(1, 10)}"
            payment_method = random.choice(payment_choices)
            placed_by = "owner" if random.random() < 0.12 else "customer"
            cur.execute(
                "INSERT INTO orders(table_no,status,created_at,billed_at,paid_at,subtotal,tax,total,payment_method,placed_by) "
                "VALUES(%s,'paid',%s,%s,%s,0,0,0,%s,%s) RETURNING id",
                (table_no, ts, ts, ts, payment_method, placed_by),
            )
            order_id = cur.fetchone()[0]
            chosen = random.sample(item_rows, min(random.randint(1, 5), len(item_rows)))
            subtotal = 0.0
            for item_id, price in chosen:
                qty = random.randint(1, 3)
                lt = round(price * qty, 2)
                subtotal += lt
                cur.execute(
                    "INSERT INTO order_items(order_id,item_id,quantity,unit_price,line_total) VALUES(%s,%s,%s,%s,%s)",
                    (order_id, item_id, qty, price, lt),
                )
            tax = round(subtotal * TAX_RATE, 2)
            total = round(subtotal + tax, 2)
            cur.execute(
                "UPDATE orders SET subtotal=%s, tax=%s, total=%s WHERE id=%s",
                (round(subtotal, 2), tax, total, order_id),
            )


try:
    init_db()
except Exception as e:
    print(f"[startup] init_db skipped: {e}")


@app.errorhandler(Exception)
def handle_uncaught_error(e):
    code = getattr(e, "code", 500)
    if not isinstance(code, int):
        code = 500
    return jsonify({"error": str(e)}), code


# ══════════════════════════════════════════════════════════════════════════
# OWNER AUTH
# ══════════════════════════════════════════════════════════════════════════
@app.post("/api/owner/login")
def owner_login():
    if not OWNER_PASSWORD:
        return jsonify({
            "error": "not_configured",
            "message": "Owner login isn't set up yet — set OWNER_PASSWORD in the server environment.",
        }), 500
    ip = request.remote_addr or "unknown"
    if _login_is_rate_limited(ip):
        return jsonify({"error": "too_many_attempts", "message": "Too many attempts. Wait a minute and try again."}), 429
    data = request.json or {}
    supplied = str(data.get("password", ""))
    if not hmac.compare_digest(supplied, OWNER_PASSWORD):
        _login_record_failure(ip)
        return jsonify({"error": "invalid_password", "message": "Incorrect password."}), 401
    _login_attempts.pop(ip, None)
    token = make_token({"role": "owner"})
    return jsonify({"token": token, "expires_in": TOKEN_TTL})


@app.get("/api/owner/verify")
@owner_required
def owner_verify():
    return jsonify({"ok": True})


# ══════════════════════════════════════════════════════════════════════════
# MENU  (browsing is public — both portals need it; edits are owner-only)
# ══════════════════════════════════════════════════════════════════════════
_menu_cache = {"data": None, "ts": 0.0}
MENU_CACHE_TTL = 30  # seconds — menus change rarely; skip the DB on repeat loads

def _menu_cache_get():
    if _menu_cache["data"] is not None and (time.time() - _menu_cache["ts"]) < MENU_CACHE_TTL:
        return _menu_cache["data"]
    return None

def _menu_cache_set(data):
    _menu_cache["data"] = data
    _menu_cache["ts"] = time.time()

def _menu_cache_clear():
    _menu_cache["data"] = None


@app.get("/api/menu")
def get_menu():
    cached = _menu_cache_get()
    if cached is not None:
        return jsonify(cached)

    # ONE query (categories LEFT JOIN items) instead of 1 + N — this used to
    # be 6 separate connections/queries for the default 5-category menu.
    rows = query(
        "SELECT c.id AS cat_id, c.name AS cat_name, c.icon AS cat_icon, "
        "mi.id AS item_id, mi.category_id, mi.name, mi.description, mi.price, "
        "mi.available, mi.image_key, mi.created_at "
        "FROM categories c LEFT JOIN menu_items mi ON mi.category_id = c.id "
        "ORDER BY c.id, mi.name",
        fetch=True,
    )
    by_cat, order = {}, []
    for r in rows:
        cid = r["cat_id"]
        if cid not in by_cat:
            by_cat[cid] = {"id": cid, "name": r["cat_name"], "icon": r["cat_icon"] or "", "items": []}
            order.append(cid)
        if r["item_id"] is not None:
            by_cat[cid]["items"].append({
                "id": r["item_id"], "category_id": r["category_id"], "name": r["name"],
                "description": r["description"], "price": r["price"], "available": r["available"],
                "image_key": r["image_key"] or "default", "created_at": r["created_at"],
            })
    result = [by_cat[cid] for cid in order]
    _menu_cache_set(result)
    return jsonify(result)


@app.post("/api/menu/items")
@owner_required
def add_menu_item():
    data = request.json
    if not {"category_id", "name", "price"}.issubset(data):
        return jsonify({"error": "Missing fields"}), 400
    item_id = query(
        "INSERT INTO menu_items(category_id,name,description,price,available,image_key) "
        "VALUES(%s,%s,%s,%s,%s,%s) RETURNING id",
        (data["category_id"], data["name"], data.get("description", ""), data["price"],
         int(bool(data.get("available", 1))), data.get("image_key", "default") or "default")
    )
    item = query("SELECT * FROM menu_items WHERE id=%s", (item_id,), fetch=True)
    _menu_cache_clear()
    return jsonify(item[0]), 201


@app.put("/api/menu/items/<int:item_id>")
@owner_required
def update_menu_item(item_id):
    data = request.json
    fields = {k: data[k] for k in ("name", "description", "price", "available", "image_key") if k in data}
    if not fields:
        return jsonify({"error": "Nothing to update"}), 400
    if "available" in fields:
        fields["available"] = int(bool(fields["available"]))
    set_clause = ", ".join(f"{k}=%s" for k in fields)
    query(f"UPDATE menu_items SET {set_clause} WHERE id=%s RETURNING id", (*fields.values(), item_id))
    item = query("SELECT * FROM menu_items WHERE id=%s", (item_id,), fetch=True)
    _menu_cache_clear()
    return jsonify(item[0])


@app.delete("/api/menu/items/<int:item_id>")
@owner_required
def delete_menu_item(item_id):
    try:
        query("DELETE FROM menu_items WHERE id=%s RETURNING id", (item_id,))
    except psycopg2.errors.ForeignKeyViolation:
        return jsonify({
            "error": "has_order_history",
            "message": "This item appears in past orders and can't be deleted. Mark it unavailable instead.",
        }), 409
    _menu_cache_clear()
    return jsonify({"deleted": item_id})


# ══════════════════════════════════════════════════════════════════════════
# ORDERS
# ══════════════════════════════════════════════════════════════════════════
def _calc_totals(items, discount=0.0):
    subtotal = sum(int(i["quantity"]) * float(i["unit_price"]) for i in items)
    tax = round(subtotal * TAX_RATE, 2)
    total = round(subtotal + tax - discount, 2)
    return round(subtotal, 2), tax, total


_ORDER_WITH_ITEMS_SQL = """
    SELECT o.*,
           COALESCE(json_agg(json_build_object(
               'id', oi.id, 'order_id', oi.order_id, 'item_id', oi.item_id,
               'quantity', oi.quantity, 'unit_price', oi.unit_price,
               'line_total', oi.line_total, 'name', mi.name, 'description', mi.description
           ) ORDER BY oi.id) FILTER (WHERE oi.id IS NOT NULL), '[]') AS items
    FROM orders o
    LEFT JOIN order_items oi ON oi.order_id = o.id
    LEFT JOIN menu_items mi ON mi.id = oi.item_id
    WHERE o.id = %s
    GROUP BY o.id
"""

def _fetch_order(order_id):
    rows = query(_ORDER_WITH_ITEMS_SQL, (order_id,), fetch=True)
    return rows[0] if rows else None

def _fetch_order_on_cursor(cur, order_id):
    cur.execute(_ORDER_WITH_ITEMS_SQL, (order_id,))
    row = cur.fetchone()
    return dict(row) if row else None


@app.post("/api/orders")
def create_order():
    data = request.json or {}
    items = data.get("items", [])
    if not items:
        return jsonify({"error": "Order must have at least one item"}), 400
    discount = float(data.get("discount", 0))
    payment_method = data.get("payment_method")
    if payment_method and payment_method not in VALID_PAYMENT_METHODS:
        return jsonify({"error": f"payment_method must be one of {sorted(VALID_PAYMENT_METHODS)}"}), 400

    subtotal, tax, total = _calc_totals(items, discount)
    now = datetime.now()
    status = "paid" if payment_method else "open"
    paid_at = now if payment_method else None
    # server-derived, not client-supplied — can't be spoofed by the request body
    placed_by = "owner" if _current_owner_payload() else "customer"

    def _do(conn):
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "INSERT INTO orders(table_no,customer,status,subtotal,tax,discount,total,created_at,notes,"
            "payment_method,paid_at,placed_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (data.get("table_no"), data.get("customer"), status, subtotal, tax, discount, total, now,
             data.get("notes"), payment_method, paid_at, placed_by)
        )
        order_id = cur.fetchone()["id"]
        rows = [
            (order_id, it["item_id"], int(it["quantity"]), float(it["unit_price"]),
             round(int(it["quantity"]) * float(it["unit_price"]), 2))
            for it in items
        ]
        execute_values(
            cur,
            "INSERT INTO order_items(order_id,item_id,quantity,unit_price,line_total) VALUES %s",
            rows,
        )
        return _fetch_order_on_cursor(cur, order_id)

    order = run(_do)
    return jsonify(order), 201


@app.get("/api/orders")
@owner_required
def list_orders():
    status = request.args.get("status")
    if status:
        rows = query("SELECT * FROM orders WHERE status=%s ORDER BY created_at DESC LIMIT 100", (status,), fetch=True)
    else:
        rows = query("SELECT * FROM orders ORDER BY created_at DESC LIMIT 100", fetch=True)
    return jsonify(rows)


@app.get("/api/orders/<int:order_id>")
def get_order(order_id):
    order = _fetch_order(order_id)
    if not order:
        return jsonify({"error": "Not found"}), 404
    return jsonify(order)


@app.delete("/api/orders/<int:order_id>")
@owner_required
def delete_order(order_id):
    existing = query("SELECT id FROM orders WHERE id=%s", (order_id,), fetch=True)
    if not existing:
        return jsonify({"error": "Not found"}), 404
    query("DELETE FROM orders WHERE id=%s RETURNING id", (order_id,))
    return jsonify({"deleted": order_id})


@app.patch("/api/orders/<int:order_id>/status")
@owner_required
def update_order_status(order_id):
    status = request.json.get("status")
    valid = {"open", "billed", "paid", "cancelled"}
    if status not in valid:
        return jsonify({"error": f"Status must be one of {valid}"}), 400
    now = datetime.now()
    billed_at = now if status == "billed" else None
    paid_at = now if status == "paid" else None
    query("UPDATE orders SET status=%s, billed_at=COALESCE(%s,billed_at), paid_at=COALESCE(%s,paid_at) WHERE id=%s RETURNING id",
          (status, billed_at, paid_at, order_id))
    return jsonify(_fetch_order(order_id))


@app.get("/api/orders/<int:order_id>/receipt")
def get_receipt(order_id):
    order = _fetch_order(order_id)
    if not order:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"receipt": {
        "order_id": order["id"], "table_no": order["table_no"],
        "customer": order["customer"], "items": order["items"],
        "subtotal": order["subtotal"], "tax": order["tax"],
        "tax_rate": f"{TAX_RATE*100:.0f}%", "discount": order["discount"],
        "total": order["total"], "status": order["status"],
        "payment_method": order.get("payment_method"),
        "created_at": str(order["created_at"]),
        "printed_at": datetime.now().isoformat(),
        "cafe_name": "Brew & Co.", "address": "12 Bean Street, Coffee Quarter",
        "thank_you": "Thank you for visiting Brew & Co.! See you soon",
    }})


# ══════════════════════════════════════════════════════════════════════════
# REPORTS  (owner-only)
# ══════════════════════════════════════════════════════════════════════════
@app.get("/api/reports/sales")
@owner_required
def sales_report():
    period = request.args.get("period", "today")
    if period == "today":
        since = date.today().isoformat()
    elif period == "week":
        since = (date.today() - timedelta(days=7)).isoformat()
    else:
        since = (date.today() - timedelta(days=30)).isoformat()
    rows = query(
        "SELECT COUNT(*) AS order_count, COALESCE(SUM(total),0) AS revenue, COALESCE(SUM(subtotal),0) AS subtotal, "
        "COALESCE(SUM(tax),0) AS tax_collected, COALESCE(AVG(total),0) AS avg_order FROM orders "
        "WHERE status='paid' AND DATE(created_at) >= %s",
        (since,), fetch=True
    )
    top_items = query(
        "SELECT mi.name, SUM(oi.quantity) AS qty, SUM(oi.line_total) AS revenue FROM order_items oi "
        "JOIN menu_items mi ON mi.id=oi.item_id JOIN orders o ON o.id=oi.order_id "
        "WHERE o.status='paid' AND DATE(o.created_at) >= %s GROUP BY mi.id, mi.name ORDER BY qty DESC LIMIT 5",
        (since,), fetch=True
    )
    daily = query(
        "SELECT DATE(created_at) AS day, COUNT(*) AS orders, COALESCE(SUM(total),0) AS revenue FROM orders "
        "WHERE status='paid' AND DATE(created_at) >= %s GROUP BY day ORDER BY day",
        (since,), fetch=True
    )
    return jsonify({"period": period, "since": since, "summary": rows[0], "top_items": top_items, "daily": daily})


@app.get("/api/reports/order-history")
@owner_required
def order_history():
    page = max(1, int(request.args.get("page", 1)))
    per_page = min(100, max(1, int(request.args.get("per_page", 20))))
    offset = (page - 1) * per_page
    sort_sql = "ASC" if request.args.get("sort") == "asc" else "DESC"
    date_filter = request.args.get("date")  # YYYY-MM-DD, optional

    if date_filter:
        try:
            datetime.strptime(date_filter, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "date must be in YYYY-MM-DD format"}), 400

    where = "o.status IN ('paid','billed')"
    params = []
    if date_filter:
        where += " AND DATE(o.created_at) = %s"
        params.append(date_filter)

    # window function folds the total-row-count into the same query instead
    # of a separate COUNT(*) round trip
    sql = f"""
        SELECT o.*, COUNT(oi.id) AS item_count, COUNT(*) OVER() AS total_count
        FROM orders o
        LEFT JOIN order_items oi ON oi.order_id = o.id
        WHERE {where}
        GROUP BY o.id
        ORDER BY o.created_at {sort_sql}
        LIMIT %s OFFSET %s
    """
    params += [per_page, offset]
    rows = query(sql, params, fetch=True)
    total = rows[0]["total_count"] if rows else 0
    for r in rows:
        r.pop("total_count", None)
    return jsonify({
        "page": page, "per_page": per_page, "total": total,
        "total_pages": (-(-total // per_page)) if total else 0,
        "orders": rows, "date": date_filter, "sort": sort_sql.lower(),
    })


@app.get("/api/health")
def health():
    return jsonify({"status": "running"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
