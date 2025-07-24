from flask import Flask, request, render_template, redirect, url_for
import sqlite3
from datetime import datetime
import os
from werkzeug.utils import secure_filename
import pdfplumber
import re

app = Flask(__name__)

# Database setup
def init_db():
    if not os.path.exists('egg_data.db'):
        conn = sqlite3.connect('egg_data.db')
        c = conn.cursor()
        c.execute('''CREATE TABLE egg_counts 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     date TEXT NOT NULL,
                     egg_count INTEGER NOT NULL,
                     notes TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS feed_purchases (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL,
                        sku TEXT,
                        product_name TEXT,
                        quantity INTEGER,
                        price REAL
                    )''')
        c.execute('''CREATE TABLE IF NOT EXISTS purchase_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        order_date TEXT NOT NULL,
                        sku TEXT,
                        name TEXT,
                        quantity INTEGER,
                        price REAL,
                        subtotal REAL,
                        tax_exempt TEXT,
                        href TEXT,
                        product_thumbnail TEXT
                    )''')
        conn.commit()
        conn.close()

# Initialize database on startup
init_db()

@app.route('/')
def index():
    conn = sqlite3.connect('egg_data.db')
    c = conn.cursor()
    c.execute('SELECT * FROM egg_counts ORDER BY date DESC')
    records = c.fetchall()
    conn.close()
    return render_template('index.html', records=records)

@app.route('/add', methods=['GET', 'POST'])
def add_count():
    if request.method == 'POST':
        egg_count = request.form['egg_count']
        notes = request.form['notes']
        date = datetime.now().strftime('%Y-%m-%d')
        
        conn = sqlite3.connect('egg_data.db')
        c = conn.cursor()
        c.execute('INSERT INTO egg_counts (date, egg_count, notes) VALUES (?, ?, ?)',
                 (date, egg_count, notes))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
    
    return render_template('add.html')

ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def parse_to_iso_date(date_str):
    """Convert various date formats to YYYY-MM-DD. Returns today's date if parsing fails."""
    if not date_str:
        return datetime.now().strftime('%Y-%m-%d')
    # Try common formats
    for fmt in [
        '%B %d, %Y',    # March 6, 2024
        '%b %d, %Y',    # Mar 6, 2024
        '%m/%d/%Y',     # 03/06/2024
        '%Y-%m-%d',     # 2024-03-06
        '%d %B %Y',     # 6 March 2024
        '%d %b %Y',     # 6 Mar 2024
        '%B %d %Y',     # March 6 2024
        '%b %d %Y',     # Mar 6 2024
        '%m-%d-%Y',     # 03-06-2024
        '%Y/%m/%d',     # 2024/03/06
    ]:
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime('%Y-%m-%d')
        except Exception:
            continue
    # Try to extract numbers
    match = re.search(r'(\d{1,2})[\s/-](\d{1,2})[\s/-](\d{2,4})', date_str)
    if match:
        m, d, y = match.groups()
        if len(y) == 2:
            y = '20' + y
        try:
            return datetime(int(y), int(m), int(d)).strftime('%Y-%m-%d')
        except Exception:
            pass
    return datetime.now().strftime('%Y-%m-%d')

@app.route('/upload_feed', methods=['GET', 'POST'])
def upload_feed():
    upload_folder = 'purchases'  # Use purchases folder for HTML files
    os.makedirs(upload_folder, exist_ok=True)
    available_files = [f for f in os.listdir(upload_folder) if f.lower().endswith('.html')]
    uploaded_count = None
    if request.method == 'POST':
        # Batch import all HTML files in purchases/
        import importlib.util
        import sys
        spec = importlib.util.spec_from_file_location("extract_items_to_mysql", "extract_items_to_mysql.py")
        ext_mod = importlib.util.module_from_spec(spec)
        sys.modules["extract_items_to_mysql"] = ext_mod
        spec.loader.exec_module(ext_mod)
        ext_mod.import_all_html_purchases()
        # Count imported items (optional: could be returned from import_all_html_purchases)
        db_path = 'egg_data.db'
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM purchase_items')
        uploaded_count = c.fetchone()[0]
        conn.close()
        return render_template('upload_feed.html', available_files=available_files, uploaded_count=uploaded_count)
    return render_template('upload_feed.html', available_files=available_files, uploaded_count=uploaded_count)

@app.route('/feed_purchases')
def feed_purchases():
    sort_by = request.args.get('sort_by', 'order_date')
    order = request.args.get('order', 'desc')
    valid_columns = {'order_date', 'sku', 'name', 'price'}
    if sort_by not in valid_columns:
        sort_by = 'order_date'
    if order not in {'asc', 'desc'}:
        order = 'desc'
    conn = sqlite3.connect('egg_data.db')
    c = conn.cursor()
    query = f'SELECT id, order_date, sku, name, quantity, price, subtotal, tax_exempt, href, product_thumbnail FROM purchase_items ORDER BY '
    if sort_by == 'order_date':
        query += 'date(order_date) ' + order.upper()
    else:
        query += f'{sort_by} {order.upper()}'
    c.execute(query)
    records = c.fetchall()
    conn.close()
    # Prepare records for display: add href to name and include thumbnail
    display_records = []
    for rec in records:
        (id, order_date, sku, name, quantity, price, subtotal, tax_exempt, href, product_thumbnail) = rec
        name_with_link = f'<a href="{href}" target="_blank">{name}</a>' if href and name else name or ''
        thumbnail_img = f'<img src="{product_thumbnail}" alt="thumb" style="height:40px;">' if product_thumbnail else ''
        display_records.append({
            'id': id,
            'order_date': order_date,
            'sku': sku,
            'name': name_with_link,
            'quantity': quantity,
            'price': price,
            'subtotal': subtotal,
            'tax_exempt': tax_exempt,
            'thumbnail': thumbnail_img
        })
    # Count available purchase files
    purchase_folder = 'purchases'
    available_purchase_count = len([f for f in os.listdir(purchase_folder) if f.lower().endswith('.html')])
    return render_template('feed_purchases.html', records=display_records, sort_by=sort_by, order=order, available_purchase_count=available_purchase_count)

@app.route('/feed_purchases/delete/<int:purchase_id>', methods=['POST'])
def delete_feed_purchase(purchase_id):
    conn = sqlite3.connect('egg_data.db')
    c = conn.cursor()
    c.execute('DELETE FROM purchase_items WHERE id = ?', (purchase_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('feed_purchases'))

@app.route('/feed_purchases/delete_multiple', methods=['POST'])
def delete_multiple_feed_purchases():
    ids = request.form.getlist('delete_ids')
    if ids:
        conn = sqlite3.connect('egg_data.db')
        c = conn.cursor()
        c.executemany('DELETE FROM purchase_items WHERE id = ?', [(i,) for i in ids])
        conn.commit()
        conn.close()
    return redirect(url_for('feed_purchases'))

@app.route('/feed_purchases/edit/<int:purchase_id>', methods=['GET', 'POST'])
def edit_feed_purchase(purchase_id):
    conn = sqlite3.connect('egg_data.db')
    c = conn.cursor()
    if request.method == 'POST':
        order_date = request.form['order_date']
        sku = request.form['sku']
        name = request.form['name']
        quantity = request.form['quantity']
        price = request.form['price']
        subtotal = request.form['subtotal']
        href = request.form['href']
        product_thumbnail = request.form['product_thumbnail']
        tax_exempt = int(request.form.get('tax_exempt', 0))
        c.execute('''UPDATE purchase_items SET order_date=?, sku=?, name=?, quantity=?, price=?, subtotal=?, href=?, product_thumbnail=?, tax_exempt=? WHERE id=?''',
                  (order_date, sku, name, quantity, price, subtotal, href, product_thumbnail, tax_exempt, purchase_id))
        conn.commit()
        conn.close()
        return redirect(url_for('feed_purchases'))
    else:
        c.execute('SELECT * FROM purchase_items WHERE id = ?', (purchase_id,))
        record = c.fetchone()
        conn.close()
        return render_template('edit_feed_purchase.html', record=record)

@app.route('/upload_all_feeds', methods=['POST'])
def upload_all_feeds():
    # Import and run HTML batch import
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location("extract_items_to_mysql", "extract_items_to_mysql.py")
    ext_mod = importlib.util.module_from_spec(spec)
    sys.modules["extract_items_to_mysql"] = ext_mod
    spec.loader.exec_module(ext_mod)
    ext_mod.import_all_html_purchases()
    # Count imported items
    db_path = 'egg_data.db'
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM purchase_items')
    uploaded_count = c.fetchone()[0]
    conn.close()
    # Get available files (after import, should be empty)
    upload_folder = 'purchases'
    available_files = [f for f in os.listdir(upload_folder) if f.lower().endswith('.html')]
    return render_template('upload_feed.html', available_files=available_files, uploaded_count=uploaded_count)

@app.route('/dashboard')
def dashboard():
    conn = sqlite3.connect('egg_data.db')
    c = conn.cursor()
    # Total eggs and total cost
    c.execute('SELECT SUM(egg_count) FROM egg_counts')
    total_eggs = c.fetchone()[0] or 0
    c.execute('SELECT SUM(price) FROM feed_purchases')
    total_cost = c.fetchone()[0] or 0.0
    # Eggs and cost per week (last 7 days)
    c.execute('SELECT SUM(egg_count) FROM egg_counts WHERE date >= date("now", "-7 days")')
    eggs_week = c.fetchone()[0] or 0
    c.execute('SELECT SUM(price) FROM feed_purchases WHERE date >= date("now", "-7 days")')
    cost_week = c.fetchone()[0] or 0.0
    cost_per_egg_week = (cost_week / eggs_week) if eggs_week else 0.0
    # Eggs and cost per month (last 30 days)
    c.execute('SELECT SUM(egg_count) FROM egg_counts WHERE date >= date("now", "-30 days")')
    eggs_month = c.fetchone()[0] or 0
    c.execute('SELECT SUM(price) FROM feed_purchases WHERE date >= date("now", "-30 days")')
    cost_month = c.fetchone()[0] or 0.0
    cost_per_egg_month = (cost_month / eggs_month) if eggs_month else 0.0
    # Cost per chicken (user input, default 1)
    num_chickens = 1
    try:
        with open('num_chickens.txt') as f:
            num_chickens = int(f.read().strip())
    except Exception:
        pass
    cost_per_chicken = (total_cost / num_chickens) if num_chickens else 0.0
    conn.close()
    return render_template('dashboard.html',
        total_eggs=total_eggs,
        total_cost=total_cost,
        cost_per_egg_week=cost_per_egg_week,
        cost_per_egg_month=cost_per_egg_month,
        cost_per_chicken=cost_per_chicken,
        num_chickens=num_chickens,
        eggs_week=eggs_week,
        cost_week=cost_week,
        eggs_month=eggs_month,
        cost_month=cost_month
    )

@app.route('/set_chickens', methods=['GET', 'POST'])
def set_chickens():
    num_chickens = 1
    try:
        with open('num_chickens.txt') as f:
            num_chickens = int(f.read().strip())
    except Exception:
        pass
    if request.method == 'POST':
        num_chickens = int(request.form['num_chickens'])
        with open('num_chickens.txt', 'w') as f:
            f.write(str(num_chickens))
        return redirect(url_for('dashboard'))
    return render_template('set_chickens.html', num_chickens=num_chickens)

if __name__ == '__main__':
    app.run(debug=True)