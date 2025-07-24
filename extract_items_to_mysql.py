import re
from bs4 import BeautifulSoup
import sqlite3
import os

def clean_price(price_text):
    """Remove currency symbols and parentheses for negative prices."""
    return float(re.sub(r'[^\d.-]', '', price_text))

def extract_items_from_order_details(html):
    """Extract all product info from all .mr-6 <ul> using <li> children, grouping every 6 <li> as a product, and add order_date."""
    soup = BeautifulSoup(html, 'html.parser')
    # Extract order_date from the first .order-detail > li > span
    order_date = None
    order_detail = soup.select_one('.order-detail')
    if order_detail:
        li = order_detail.find('li')
        if li:
            span = li.find('span')
            if span:
                order_date = span.get_text(strip=True)
    uls = soup.select('.mr-6')
    if not uls:
        print('No .mr-6 ul found!')
        return []
    items = []
    group_size = 6
    for ul in uls:
        li_elements = ul.find_all('li', recursive=False)
        for i in range(0, len(li_elements), group_size):
            group = li_elements[i:i+group_size]
            if len(group) < group_size:
                continue  # skip incomplete product blocks
            try:
                # Do NOT overwrite order_date here; use the one from the header
                sku = group[0].find_all(recursive=False)[1].get_text(strip=True)
                name = group[1].find('a').get_text(strip=True) if group[2].find('a') else None
                href = group[1].find('a')['href'] if group[2].find('a') else None
                # Product thumbnail
                img_tag = group[2].find('a').find('img') if group[2].find('a') else None
                product_thumbnail = img_tag['src'] if img_tag else None
                quantity = group[3].find_all(recursive=False)[1].get_text(strip=True)
                price = group[4].find_all(recursive=False)[1].get_text(strip=True)
                subtotal = group[5].find_all(recursive=False)[1].get_text(strip=True)
                # Clean up numeric fields
                def parse_float(val):
                    val = val.replace('$','').replace('(','-').replace(')','').replace(',','').strip()
                    return float(val) if val and re.search(r'\d', val) else None
                quantity = int(quantity) if quantity and re.search(r'\d', quantity) else None
                price = parse_float(price)
                subtotal = parse_float(subtotal)
                # Tax Exempt
                tax_exempt = any('tax exemption' in li.get_text(strip=True).lower() for li in group)
                items.append({
                    'sku': sku,
                    'name': name,
                    'quantity': quantity,
                    'price': price,
                    'subtotal': subtotal,
                    'tax_exempt': tax_exempt,
                    'href': href,
                    'product_thumbnail': product_thumbnail,
                    'order_date': order_date
                })
            except Exception as e:
                print(f'Error parsing product block at index {i}: {e}')
                continue
    return items

def create_database_and_table():
    """Create SQLite table, dropping and recreating if schema is out of date (for dev use)."""
    db_path = 'egg_data.db'
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    # Check if 'order_date' column exists
    c.execute("PRAGMA table_info(purchase_items)")
    columns = [row[1] for row in c.fetchall()]
    if 'order_date' not in columns or 'product_thumbnail' not in columns:
        c.execute('DROP TABLE IF EXISTS purchase_items')
    c.execute('''CREATE TABLE IF NOT EXISTS purchase_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sku TEXT,
        name TEXT,
        quantity INTEGER,
        price REAL,
        subtotal REAL,
        tax_exempt BOOLEAN,
        href TEXT,
        product_thumbnail TEXT,
        order_date TEXT
    )''')
    conn.commit()
    conn.close()

def insert_items_to_db(items):
    """Insert extracted items into SQLite database."""
    db_path = 'egg_data.db'
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    insert_query = '''INSERT INTO purchase_items (sku, name, quantity, price, subtotal, tax_exempt, href, product_thumbnail, order_date)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'''
    for item in items:
        c.execute(insert_query, (
            item.get('sku'),
            item.get('name'),
            item.get('quantity'),
            item.get('price'),
            item.get('subtotal'),
            int(item.get('tax_exempt', False)),
            item.get('href'),
            item.get('product_thumbnail'),
            item.get('order_date')
        ))
    conn.commit()
    conn.close()
    print(f"Successfully inserted {len(items)} items into the SQLite database.")

def import_all_html_purchases():
    purchases_folder = 'purchases'
    processed_folder = 'processed'
    os.makedirs(processed_folder, exist_ok=True)
    html_files = [f for f in os.listdir(purchases_folder) if f.lower().endswith('.html')]
    all_items = []
    for filename in html_files:
        filepath = os.path.join(purchases_folder, filename)
        with open(filepath, encoding='utf-8') as f:
            html = f.read()
        items = extract_items_from_order_details(html)
        all_items.extend(items)
        # Move processed file
        os.rename(filepath, os.path.join(processed_folder, filename))
    create_database_and_table()
    insert_items_to_db(all_items)
    print(f"Imported {len(all_items)} items from {len(html_files)} HTML files.")

def main():
    html_path = os.path.join('purchases', 'J17.html')  # Change filename as needed
    with open(html_path, encoding='utf-8') as f:
        html = f.read()
    items = extract_items_from_order_details(html)
    create_database_and_table()
    insert_items_to_db(items)
    for item in items:
        print(item)

if __name__ == "__main__":
    import_all_html_purchases()