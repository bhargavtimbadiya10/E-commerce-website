import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash
import os
from werkzeug.utils import secure_filename

DB_PATH = os.path.join(os.path.dirname(__file__), "ecommerce.db")

UPLOAD_FOLDER = "static/images"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
app = Flask(__name__)
app.secret_key = "secret123"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def setup_db():
    con = get_db()
    cur = con.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS products(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        price REAL,
        image TEXT,
        description TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS cart(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        product_id INTEGER,
        qty INTEGER DEFAULT 1
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        total REAL,
        address TEXT,
        payment_method TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS order_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER,
        product_id INTEGER,
        qty INTEGER,
        price REAL
    )""")
    con.commit()
    con.close()

def seed_products():
    con = get_db()
    cur = con.cursor()
    count = cur.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if count == 0:
        products = [
            ("PUMA BLKtop Preppy", 6299.0, "1.jpg", "Trendy sneakers with retro design and durable build."),
            ("PUMA X-RAY Speed", 6000.0, "2.jpg", "Lightweight shoes designed for speed and comfort."),
            ("PUMA Slipstream", 10999.0, "3.jpg", "Classic basketball-inspired shoes with modern cushioning."),
            ("PUMA BMW M Motorsport", 9000.0, "4.jpg", "High performance sneakers with BMW motorsport DNA."),
        ]
        cur.executemany("INSERT INTO products(name, price, image, description) VALUES (?,?,?,?)", products)
        con.commit()
    con.close()

setup_db()
seed_products()

def require_login():
    if 'user_id' not in session:
        flash("Please login first.")
        return redirect(url_for('login'))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username")
        p = request.form.get("password")
        con = get_db(); cur = con.cursor()
        row = cur.execute("SELECT * FROM users WHERE username=? AND password=?", (u, p)).fetchone()
        con.close()
        if row:
            session['user_id'] = row['id']
            session['username'] = row['username']
            return redirect(url_for("products"))
        else:
            flash("Invalid credentials")
    return render_template("login.html")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        u = request.form.get("username")
        p = request.form.get("password")
        con = get_db(); cur = con.cursor()
        try:
            cur.execute("INSERT INTO users(username, password) VALUES(?,?)", (u,p))
            con.commit()
            flash("Registered! Please login.")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username already exists.")
        finally:
            con.close()
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
def home():
    return redirect(url_for("products"))

@app.route("/products")
def products():
    con = get_db()
    items = con.execute("SELECT id,name,price,image,description FROM products").fetchall()
    con.close()
    return render_template("products.html", items=items)

@app.route("/add_to_cart/<int:product_id>")
def add_to_cart(product_id):
    if 'user_id' not in session:
        return redirect(url_for("login"))
    con = get_db(); cur = con.cursor()
    cur.execute("INSERT INTO cart(user_id, product_id, qty) VALUES(?,?,1)", (session['user_id'], product_id))
    con.commit(); con.close()
    flash("Item added to cart.")
    return redirect(url_for("products"))

@app.route("/cart")
def cart():
    if 'user_id' not in session:
        return redirect(url_for("login"))
    con = get_db(); cur = con.cursor()
    items = cur.execute("""
        SELECT c.id as cart_id, p.image, p.name, p.price, c.qty
        FROM cart c JOIN products p ON p.id = c.product_id
        WHERE c.user_id=?
    """, (session['user_id'],)).fetchall()
    total = sum(row['price'] * row['qty'] for row in items)
    con.close()
    return render_template("cart.html", items=items, total=total)

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    if 'user_id' not in session:
        return redirect(url_for("login"))
    con = get_db(); cur = con.cursor()
    cart_items = cur.execute("""
        SELECT c.id as cart_id, p.id as product_id, p.name, p.price, p.image, c.qty
        FROM cart c JOIN products p ON p.id = c.product_id
        WHERE c.user_id=?
    """, (session['user_id'],)).fetchall()
    if not cart_items:
        con.close()
        flash("Cart is empty.")
        return redirect(url_for("products"))
    total = sum(row['price']*row['qty'] for row in cart_items)
    if request.method == "POST":
        address = request.form.get("address")
        city = request.form.get("city")
        pincode = request.form.get("pincode")
        payment = request.form.get("payment_method")
        full_address = f"{address}, {city} - {pincode}"
        
        cur.execute("INSERT INTO orders(user_id,total,address,payment_method) VALUES (?,?,?,?)",
                    (session['user_id'], total, full_address, payment))
        order_id = cur.lastrowid
        
        for row in cart_items:
            cur.execute("INSERT INTO order_items(order_id,product_id,qty,price) VALUES (?,?,?,?)",
                        (order_id, row['product_id'], row['qty'], row['price']))
        
        cur.execute("DELETE FROM cart WHERE user_id=?", (session['user_id'],))
        con.commit(); con.close()
        return redirect(url_for("order_success", order_id=order_id))
    con.close()
    return render_template("checkout.html", items=cart_items, total=total)

@app.route("/order_success/<int:order_id>")
def order_success(order_id):
    if 'user_id' not in session:
        return redirect(url_for("login"))
    con = get_db(); cur = con.cursor()
    order = cur.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    con.close()
    return render_template("order_success.html", order=order)


@app.route("/admin/add_product", methods=["GET", "POST"])
def add_product():
    
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT username FROM users WHERE id=?", (session["user_id"],))
    username = cur.fetchone()[0]
    conn.close()

    if username != "admin":
        flash("🚫 Only admin can add products!")
        return redirect(url_for("products"))

    
    if request.method == "POST":
        name = request.form["name"]
        price = request.form["price"]
        file = request.files["image"]
        description = request.form["description"]

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(filepath)  

            conn = get_db()
            cur = conn.cursor()
            cur.execute("INSERT INTO products (name, price, image, description) VALUES (?, ?, ?, ?)",
                        (name, price, filename, description))
            conn.commit()
            conn.close()

            flash("✅ Product added successfully!")
            return redirect(url_for("products"))
        else:
            flash("❌ Invalid file format. Allowed: jpg, jpeg, png, gif")

    return render_template("admin_add.html")

if __name__ == "__main__":
    app.run(debug=True)
