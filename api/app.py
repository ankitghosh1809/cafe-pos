import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import psycopg2.extras
import os
from dotenv import load_dotenv
from datetime import datetime, date, timedelta
import random

load_dotenv()
app = Flask(__name__)
CORS(app)
TAX_RATE = 0.05

def get_db():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Add it in Vercel → Settings → Environment Variables."
        )
    return psycopg2.connect(db_url)

def query(sql, params=None, fetch=False):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, params or ())
    if fetch:
        result = [dict(r) for r in cur.fetchall()]
    else:
        conn.commit()
        row = cur.fetchone()
        result = list(row.values())[0] if row else cur.rowcount
    cur.close()
    conn.close()
    return result

# ── schema + seed (Postgres) ─────────────────────────────────────────────────
# Creates tables on first run and seeds demo menu/order data if the DB is
# empty. Safe on every cold start: CREATE TABLE IF NOT EXISTS is a no-op once
# the schema exists, and seeding only runs when categories is empty.

def init_db():
    conn = get_db()
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
            created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_menu_category ON menu_items(category_id);

        CREATE TABLE IF NOT EXISTS orders (
            id         SERIAL PRIMARY KEY,
            table_no   VARCHAR(20),
            customer   VARCHAR(150),
            status     VARCHAR(20) NOT NULL DEFAULT 'open'
                       CHECK (status IN ('open','billed','paid','cancelled')),
            subtotal   NUMERIC(10,2) NOT NULL DEFAULT 0.00,
            tax        NUMERIC(10,2) NOT NULL DEFAULT 0.00,
            discount   NUMERIC(10,2) NOT NULL DEFAULT 0.00,
            total      NUMERIC(10,2) NOT NULL DEFAULT 0.00,
            notes      TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            billed_at  TIMESTAMP,
            paid_at    TIMESTAMP
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

    items = [
        (0, "Espresso", "Rich single-shot espresso", 2.50),
        (0, "Cappuccino", "Espresso with steamed milk foam", 3.50),
        (0, "Flat White", "Double ristretto with velvety micro-foam", 4.00),
        (0, "Chai Latte", "Spiced tea with steamed milk", 3.75),
        (1, "Cold Brew", "12-hour slow-extracted cold brew", 4.50),
        (1, "Iced Caramel Latte", "Espresso, milk, caramel over ice", 4.75),
        (1, "Mango Smoothie", "Fresh mango blended with yogurt", 4.25),
        (1, "Sparkling Lemonade", "House-made with fresh zest", 3.25),
        (2, "Butter Croissant", "Flaky, all-butter French croissant", 2.75),
        (2, "Avocado Toast", "Smashed avo on sourdough with sea salt", 6.50),
        (2, "Club Sandwich", "Triple-decker with chicken & bacon", 7.00),
        (2, "Cheese Scone", "Warm cheddar scone with butter", 2.25),
        (3, "Eggs Benedict", "Poached eggs, ham, hollandaise on muffin", 9.50),
        (3, "Granola Bowl", "House granola, Greek yogurt, seasonal fruit", 7.00),
        (3, "Pasta Primavera", "Penne with garden vegetables, olive oil", 10.50),
        (4, "Tiramisu", "Classic Italian layered dessert", 5.50),
        (4, "Chocolate Brownie", "Fudgy brownie, served warm with cream", 4.00),
        (4, "Cheesecake Slice", "New York-style, berry compote", 5.00),
    ]
    item_rows = []
    for cat_idx, name, desc, price in items:
        cur.execute(
            "INSERT INTO menu_items(category_id,name,description,price) VALUES(%s,%s,%s,%s) RETURNING id",
            (cat_ids[cat_idx], name, desc, price),
        )
        item_rows.append((cur.fetchone()[0], price))

    # 30 days of demo order history so Reports/History aren't empty on first run
    today = date.today()
    for d in range(30, 0, -1):
        day = today - timedelta(days=d)
        for _ in range(random.randint(15, 35)):
            ts = datetime.combine(day, datetime.min.time()).replace(
                hour=random.randint(8, 20), minute=random.randint(0, 59)
            )
            table_no = f"T{random.randint(1, 12)}"
            cur.execute(
                "INSERT INTO orders(table_no,status,created_at,billed_at,paid_at,subtotal,tax,total) "
                "VALUES(%s,'paid',%s,%s,%s,0,0,0) RETURNING id",
                (table_no, ts, ts, ts),
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


@app.get("/api/menu")
def get_menu():
    cats = query("SELECT * FROM categories ORDER BY id", fetch=True)
    result = []
    for cat in cats:
        items = query("SELECT * FROM menu_items WHERE category_id=%s ORDER BY name", (cat["id"],), fetch=True)
        result.append({"id": cat["id"], "name": cat["name"], "icon": cat.get("icon",""), "items": items})
    return jsonify(result)

@app.post("/api/menu/items")
def add_menu_item():
    data = request.json
    if not {"category_id","name","price"}.issubset(data):
        return jsonify({"error": "Missing fields"}), 400
    item_id = query(
        "INSERT INTO menu_items(category_id,name,description,price,available) VALUES(%s,%s,%s,%s,%s) RETURNING id",
        (data["category_id"],data["name"],data.get("description",""),data["price"],data.get("available",1))
    )
    item = query("SELECT * FROM menu_items WHERE id=%s", (item_id,), fetch=True)
    return jsonify(item[0]), 201

@app.put("/api/menu/items/<int:item_id>")
def update_menu_item(item_id):
    data = request.json
    fields = {k: data[k] for k in ("name","description","price","available") if k in data}
    if not fields:
        return jsonify({"error": "Nothing to update"}), 400
    set_clause = ", ".join(f"{k}=%s" for k in fields)
    query(f"UPDATE menu_items SET {set_clause} WHERE id=%s", (*fields.values(), item_id))
    item = query("SELECT * FROM menu_items WHERE id=%s", (item_id,), fetch=True)
    return jsonify(item[0])

@app.delete("/api/menu/items/<int:item_id>")
def delete_menu_item(item_id):
    query("DELETE FROM menu_items WHERE id=%s", (item_id,))
    return jsonify({"deleted": item_id})

def _calc_totals(items, discount=0.0):
    subtotal = sum(i["quantity"] * i["unit_price"] for i in items)
    tax = round(subtotal * TAX_RATE, 2)
    total = round(subtotal + tax - discount, 2)
    return round(subtotal, 2), tax, total

@app.post("/api/orders")
def create_order():
    data = request.json or {}
    items = data.get("items", [])
    if not items:
        return jsonify({"error": "Order must have at least one item"}), 400
    discount = float(data.get("discount", 0))
    subtotal, tax, total = _calc_totals(items, discount)
    now = datetime.now()
    order_id = query(
        "INSERT INTO orders(table_no,customer,status,subtotal,tax,discount,total,created_at,notes) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (data.get("table_no"),data.get("customer"),"open",subtotal,tax,discount,total,now,data.get("notes"))
    )
    for it in items:
        lt = round(it["quantity"] * it["unit_price"], 2)
        query(
            "INSERT INTO order_items(order_id,item_id,quantity,unit_price,line_total) VALUES(%s,%s,%s,%s,%s) RETURNING id",
            (order_id,it["item_id"],it["quantity"],it["unit_price"],lt)
        )
    return jsonify(_fetch_order(order_id)), 201

@app.get("/api/orders")
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

def _fetch_order(order_id):
    orders = query("SELECT * FROM orders WHERE id=%s", (order_id,), fetch=True)
    if not orders:
        return None
    order = orders[0]
    items = query(
        "SELECT oi.*, mi.name, mi.description FROM order_items oi JOIN menu_items mi ON mi.id=oi.item_id WHERE oi.order_id=%s",
        (order_id,), fetch=True
    )
    order["items"] = items
    return order

@app.patch("/api/orders/<int:order_id>/status")
def update_order_status(order_id):
    status = request.json.get("status")
    valid = {"open","billed","paid","cancelled"}
    if status not in valid:
        return jsonify({"error": f"Status must be one of {valid}"}), 400
    now = datetime.now()
    billed_at = now if status == "billed" else None
    paid_at = now if status == "paid" else None
    query("UPDATE orders SET status=%s, billed_at=COALESCE(%s,billed_at), paid_at=COALESCE(%s,paid_at) WHERE id=%s",
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
        "created_at": str(order["created_at"]),
        "printed_at": datetime.now().isoformat(),
        "cafe_name": "Brew & Co.", "address": "12 Bean Street, Coffee Quarter",
        "thank_you": "Thank you for visiting Brew & Co.! See you soon",
    }})

@app.get("/api/reports/sales")
def sales_report():
    period = request.args.get("period", "today")
    if period == "today":
        since = date.today().isoformat()
    elif period == "week":
        since = (date.today() - timedelta(days=7)).isoformat()
    else:
        since = (date.today() - timedelta(days=30)).isoformat()
    rows = query(
        "SELECT COUNT(*) AS order_count, COALESCE(SUM(total),0) AS revenue, COALESCE(SUM(subtotal),0) AS subtotal, COALESCE(SUM(tax),0) AS tax_collected, COALESCE(AVG(total),0) AS avg_order FROM orders WHERE status='paid' AND DATE(created_at) >= %s",
        (since,), fetch=True
    )
    top_items = query(
        "SELECT mi.name, SUM(oi.quantity) AS qty, SUM(oi.line_total) AS revenue FROM order_items oi JOIN menu_items mi ON mi.id=oi.item_id JOIN orders o ON o.id=oi.order_id WHERE o.status='paid' AND DATE(o.created_at) >= %s GROUP BY mi.id, mi.name ORDER BY qty DESC LIMIT 5",
        (since,), fetch=True
    )
    daily = query(
        "SELECT DATE(created_at) AS day, COUNT(*) AS orders, COALESCE(SUM(total),0) AS revenue FROM orders WHERE status='paid' AND DATE(created_at) >= %s GROUP BY day ORDER BY day",
        (since,), fetch=True
    )
    return jsonify({"period": period, "since": since, "summary": rows[0], "top_items": top_items, "daily": daily})

@app.get("/api/reports/order-history")
def order_history():
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    offset = (page - 1) * per_page
    total_rows = query("SELECT COUNT(*) AS cnt FROM orders WHERE status IN ('paid','billed')", fetch=True)
    total = total_rows[0]["cnt"]
    rows = query(
        "SELECT o.*, COUNT(oi.id) AS item_count FROM orders o LEFT JOIN order_items oi ON oi.order_id=o.id WHERE o.status IN ('paid','billed') GROUP BY o.id ORDER BY o.created_at DESC LIMIT %s OFFSET %s",
        (per_page, offset), fetch=True
    )
    return jsonify({"page": page, "per_page": per_page, "total": total, "total_pages": -(-total // per_page), "orders": rows})

@app.get("/api/health")
def health():
    return jsonify({"status": "running"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
