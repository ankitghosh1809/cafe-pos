from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
from datetime import datetime, date, timedelta
import random

app = Flask(__name__)
CORS(app)

DB_PATH = os.path.join(os.path.dirname(__file__), "cafe.db")


# ── helpers ────────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.executescript("""
        PRAGMA journal_mode=WAL;

        CREATE TABLE IF NOT EXISTS categories (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT    NOT NULL UNIQUE,
            icon      TEXT    DEFAULT '☕'
        );

        CREATE TABLE IF NOT EXISTS menu_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL REFERENCES categories(id),
            name        TEXT    NOT NULL,
            description TEXT,
            price       REAL    NOT NULL CHECK(price >= 0),
            available   INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS orders (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            table_no     TEXT,
            customer     TEXT,
            status       TEXT NOT NULL DEFAULT 'open'
                              CHECK(status IN ('open','billed','paid','cancelled')),
            subtotal     REAL NOT NULL DEFAULT 0,
            tax          REAL NOT NULL DEFAULT 0,
            discount     REAL NOT NULL DEFAULT 0,
            total        REAL NOT NULL DEFAULT 0,
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            billed_at    TEXT,
            paid_at      TEXT,
            notes        TEXT
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id    INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            item_id     INTEGER NOT NULL REFERENCES menu_items(id),
            quantity    INTEGER NOT NULL DEFAULT 1 CHECK(quantity > 0),
            unit_price  REAL    NOT NULL,
            line_total  REAL    NOT NULL
        );
    """)
    conn.commit()

    # seed only when empty
    if cur.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
        _seed(cur)
        conn.commit()

    conn.close()


def _seed(cur):
    cats = [
        ("Hot Beverages", "☕"),
        ("Cold Beverages", "🧋"),
        ("Snacks", "🥐"),
        ("Meals", "🍽️"),
        ("Desserts", "🍰"),
    ]
    for name, icon in cats:
        cur.execute("INSERT INTO categories(name,icon) VALUES(?,?)", (name, icon))

    items = [
        (1, "Espresso",           "Rich single-shot espresso",                 2.50),
        (1, "Cappuccino",         "Espresso with steamed milk foam",            3.50),
        (1, "Flat White",         "Double ristretto with velvety micro-foam",  4.00),
        (1, "Chai Latte",         "Spiced tea with steamed milk",               3.75),
        (2, "Cold Brew",          "12-hour slow-extracted cold brew",           4.50),
        (2, "Iced Caramel Latte", "Espresso, milk, caramel over ice",          4.75),
        (2, "Mango Smoothie",     "Fresh mango blended with yogurt",           4.25),
        (2, "Sparkling Lemonade", "House-made with fresh zest",                3.25),
        (3, "Butter Croissant",   "Flaky, all-butter French croissant",        2.75),
        (3, "Avocado Toast",      "Smashed avo on sourdough with sea salt",    6.50),
        (3, "Club Sandwich",      "Triple-decker with chicken & bacon",        7.00),
        (3, "Cheese Scone",       "Warm cheddar scone with butter",            2.25),
        (4, "Eggs Benedict",      "Poached eggs, ham, hollandaise on muffin",  9.50),
        (4, "Granola Bowl",       "House granola, Greek yogurt, seasonal fruit",7.00),
        (4, "Pasta Primavera",    "Penne with garden vegetables, olive oil",   10.50),
        (5, "Tiramisu",           "Classic Italian layered dessert",            5.50),
        (5, "Chocolate Brownie",  "Fudgy brownie, served warm with cream",     4.00),
        (5, "Cheesecake Slice",   "New York-style, berry compote",              5.00),
    ]
    for cat_id, name, desc, price in items:
        cur.execute(
            "INSERT INTO menu_items(category_id,name,description,price) VALUES(?,?,?,?)",
            (cat_id, name, desc, price),
        )

    # generate 30 days of realistic historical orders
    conn = cur.connection
    today = date.today()
    for d in range(30, 0, -1):
        day = today - timedelta(days=d)
        n_orders = random.randint(15, 35)
        for _ in range(n_orders):
            hour = random.randint(8, 20)
            minute = random.randint(0, 59)
            ts = datetime.combine(day, datetime.min.time()).replace(
                hour=hour, minute=minute
            )
            table = f"T{random.randint(1, 12)}"
            cur.execute(
                """INSERT INTO orders(table_no,status,created_at,billed_at,paid_at)
                   VALUES(?,?,?,?,?)""",
                (table, "paid", ts.isoformat(),
                 ts.isoformat(), ts.isoformat()),
            )
            order_id = cur.lastrowid

            n_items = random.randint(1, 5)
            all_items = conn.execute("SELECT id,price FROM menu_items").fetchall()
            chosen = random.sample(all_items, min(n_items, len(all_items)))
            subtotal = 0.0
            for row in chosen:
                qty = random.randint(1, 3)
                lt = round(row["price"] * qty, 2)
                subtotal += lt
                cur.execute(
                    """INSERT INTO order_items(order_id,item_id,quantity,unit_price,line_total)
                       VALUES(?,?,?,?,?)""",
                    (order_id, row["id"], qty, row["price"], lt),
                )
            tax = round(subtotal * 0.05, 2)
            total = round(subtotal + tax, 2)
            cur.execute(
                "UPDATE orders SET subtotal=?,tax=?,total=? WHERE id=?",
                (round(subtotal, 2), tax, total, order_id),
            )


# ── menu endpoints ──────────────────────────────────────────────────────────────

@app.get("/api/menu")
def get_menu():
    db = get_db()
    cats = db.execute("SELECT * FROM categories ORDER BY id").fetchall()
    result = []
    for cat in cats:
        items = db.execute(
            "SELECT * FROM menu_items WHERE category_id=? ORDER BY name",
            (cat["id"],),
        ).fetchall()
        result.append({
            "id":    cat["id"],
            "name":  cat["name"],
            "icon":  cat["icon"],
            "items": [dict(i) for i in items],
        })
    db.close()
    return jsonify(result)


@app.post("/api/menu/items")
def add_menu_item():
    data = request.json
    required = {"category_id", "name", "price"}
    if not required.issubset(data):
        return jsonify({"error": "Missing fields"}), 400
    db = get_db()
    cur = db.execute(
        "INSERT INTO menu_items(category_id,name,description,price,available) VALUES(?,?,?,?,?)",
        (data["category_id"], data["name"], data.get("description", ""),
         data["price"], data.get("available", 1)),
    )
    db.commit()
    item = db.execute("SELECT * FROM menu_items WHERE id=?", (cur.lastrowid,)).fetchone()
    db.close()
    return jsonify(dict(item)), 201


@app.put("/api/menu/items/<int:item_id>")
def update_menu_item(item_id):
    data = request.json
    db = get_db()
    fields = {k: data[k] for k in ("name", "description", "price", "available") if k in data}
    if not fields:
        return jsonify({"error": "Nothing to update"}), 400
    set_clause = ", ".join(f"{k}=?" for k in fields)
    db.execute(
        f"UPDATE menu_items SET {set_clause} WHERE id=?",
        (*fields.values(), item_id),
    )
    db.commit()
    item = db.execute("SELECT * FROM menu_items WHERE id=?", (item_id,)).fetchone()
    db.close()
    return jsonify(dict(item))


@app.delete("/api/menu/items/<int:item_id>")
def delete_menu_item(item_id):
    db = get_db()
    db.execute("DELETE FROM menu_items WHERE id=?", (item_id,))
    db.commit()
    db.close()
    return jsonify({"deleted": item_id})


# ── order endpoints ─────────────────────────────────────────────────────────────

TAX_RATE = 0.05


def _calc_totals(items, discount=0.0):
    subtotal = sum(i["quantity"] * i["unit_price"] for i in items)
    tax      = round(subtotal * TAX_RATE, 2)
    total    = round(subtotal + tax - discount, 2)
    return round(subtotal, 2), tax, total


@app.post("/api/orders")
def create_order():
    data  = request.json or {}
    items = data.get("items", [])
    if not items:
        return jsonify({"error": "Order must have at least one item"}), 400

    db  = get_db()
    now = datetime.now().isoformat()

    discount          = float(data.get("discount", 0))
    subtotal, tax, total = _calc_totals(items, discount)

    cur = db.execute(
        """INSERT INTO orders(table_no,customer,status,subtotal,tax,discount,total,created_at,notes)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (data.get("table_no"), data.get("customer"), "open",
         subtotal, tax, discount, total, now, data.get("notes")),
    )
    order_id = cur.lastrowid

    for it in items:
        lt = round(it["quantity"] * it["unit_price"], 2)
        db.execute(
            "INSERT INTO order_items(order_id,item_id,quantity,unit_price,line_total) VALUES(?,?,?,?,?)",
            (order_id, it["item_id"], it["quantity"], it["unit_price"], lt),
        )

    db.commit()
    order = _fetch_order(db, order_id)
    db.close()
    return jsonify(order), 201


@app.get("/api/orders")
def list_orders():
    status = request.args.get("status")
    db     = get_db()
    q      = "SELECT * FROM orders"
    params: list = []
    if status:
        q     += " WHERE status=?"
        params = [status]
    q     += " ORDER BY created_at DESC LIMIT 100"
    rows   = db.execute(q, params).fetchall()
    result = [dict(r) for r in rows]
    db.close()
    return jsonify(result)


@app.get("/api/orders/<int:order_id>")
def get_order(order_id):
    db    = get_db()
    order = _fetch_order(db, order_id)
    db.close()
    if not order:
        return jsonify({"error": "Not found"}), 404
    return jsonify(order)


def _fetch_order(db, order_id):
    order = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        return None
    items = db.execute(
        """SELECT oi.*, mi.name, mi.description
           FROM order_items oi
           JOIN menu_items mi ON mi.id = oi.item_id
           WHERE oi.order_id=?""",
        (order_id,),
    ).fetchall()
    result = dict(order)
    result["items"] = [dict(i) for i in items]
    return result


@app.patch("/api/orders/<int:order_id>/status")
def update_order_status(order_id):
    status = request.json.get("status")
    valid  = {"open", "billed", "paid", "cancelled"}
    if status not in valid:
        return jsonify({"error": f"Status must be one of {valid}"}), 400

    db  = get_db()
    now = datetime.now().isoformat()

    billed_at = now if status == "billed" else None
    paid_at   = now if status == "paid"   else None

    db.execute(
        "UPDATE orders SET status=?, billed_at=COALESCE(?,billed_at), paid_at=COALESCE(?,paid_at) WHERE id=?",
        (status, billed_at, paid_at, order_id),
    )
    db.commit()
    order = _fetch_order(db, order_id)
    db.close()
    return jsonify(order)


# ── receipt endpoint ────────────────────────────────────────────────────────────

@app.get("/api/orders/<int:order_id>/receipt")
def get_receipt(order_id):
    db    = get_db()
    order = _fetch_order(db, order_id)
    db.close()
    if not order:
        return jsonify({"error": "Not found"}), 404

    lines = []
    for it in order["items"]:
        lines.append({
            "name":       it["name"],
            "quantity":   it["quantity"],
            "unit_price": it["unit_price"],
            "line_total": it["line_total"],
        })

    return jsonify({
        "receipt": {
            "order_id":    order["id"],
            "table_no":    order["table_no"],
            "customer":    order["customer"],
            "items":       lines,
            "subtotal":    order["subtotal"],
            "tax":         order["tax"],
            "tax_rate":    f"{TAX_RATE*100:.0f}%",
            "discount":    order["discount"],
            "total":       order["total"],
            "status":      order["status"],
            "created_at":  order["created_at"],
            "printed_at":  datetime.now().isoformat(),
            "cafe_name":   "Brew & Co.",
            "address":     "12 Bean Street, Coffee Quarter",
            "thank_you":   "Thank you for visiting Brew & Co.! See you soon ☕",
        }
    })


# ── reporting endpoints ─────────────────────────────────────────────────────────

@app.get("/api/reports/sales")
def sales_report():
    period = request.args.get("period", "today")  # today | week | month
    db     = get_db()

    if period == "today":
        since = date.today().isoformat()
    elif period == "week":
        since = (date.today() - timedelta(days=7)).isoformat()
    else:
        since = (date.today() - timedelta(days=30)).isoformat()

    row = db.execute(
        """SELECT
               COUNT(*)       AS order_count,
               COALESCE(SUM(total),0)    AS revenue,
               COALESCE(SUM(subtotal),0) AS subtotal,
               COALESCE(SUM(tax),0)      AS tax_collected,
               COALESCE(AVG(total),0)    AS avg_order
           FROM orders
           WHERE status='paid' AND date(created_at) >= ?""",
        (since,),
    ).fetchone()

    top_items = db.execute(
        """SELECT mi.name, SUM(oi.quantity) AS qty, SUM(oi.line_total) AS revenue
           FROM order_items oi
           JOIN menu_items mi ON mi.id = oi.item_id
           JOIN orders o ON o.id = oi.order_id
           WHERE o.status='paid' AND date(o.created_at) >= ?
           GROUP BY mi.id
           ORDER BY qty DESC LIMIT 5""",
        (since,),
    ).fetchall()

    daily = db.execute(
        """SELECT date(created_at) AS day,
                  COUNT(*)         AS orders,
                  COALESCE(SUM(total),0) AS revenue
           FROM orders
           WHERE status='paid' AND date(created_at) >= ?
           GROUP BY day
           ORDER BY day""",
        (since,),
    ).fetchall()

    db.close()
    return jsonify({
        "period":     period,
        "since":      since,
        "summary":    dict(row),
        "top_items":  [dict(i) for i in top_items],
        "daily":      [dict(d) for d in daily],
    })


@app.get("/api/reports/order-history")
def order_history():
    page     = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    offset   = (page - 1) * per_page

    db    = get_db()
    total = db.execute(
        "SELECT COUNT(*) FROM orders WHERE status IN ('paid','billed')"
    ).fetchone()[0]
    rows  = db.execute(
        """SELECT o.*, COUNT(oi.id) AS item_count
           FROM orders o
           LEFT JOIN order_items oi ON oi.order_id=o.id
           WHERE o.status IN ('paid','billed')
           GROUP BY o.id
           ORDER BY o.created_at DESC
           LIMIT ? OFFSET ?""",
        (per_page, offset),
    ).fetchall()
    db.close()

    return jsonify({
        "page":        page,
        "per_page":    per_page,
        "total":       total,
        "total_pages": -(-total // per_page),
        "orders":      [dict(r) for r in rows],
    })


# ── entry point ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
