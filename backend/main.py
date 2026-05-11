from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import os
import google.generativeai as genai
from dotenv import load_dotenv
# Zid SDK is optional for local dev — import gracefully
load_dotenv()
try:
    from zid import ZidClient
except Exception:
    ZidClient = None

# Initialize Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

app = FastAPI()

# Database setup
def init_db():
    conn = sqlite3.connect('sandbox.db')
    c = conn.cursor()
    # Existing table
    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            customer_name TEXT,
            total REAL,
            status TEXT
        )
    ''')
    # New tables for AI features
    c.execute('''
        CREATE TABLE IF NOT EXISTS stock_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT,
            product_name TEXT,
            stock_quantity INTEGER,
            is_resolved BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS return_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE,
            status TEXT,
            history TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.get("/")
def read_root():
    return {
        "status": "online",
        "zid_client_initialized": client is not None,
        "message": "Zid Automation Dashboard API is running"
    }

# Initialize Zid Client (Optional for dev)
partner_token = os.getenv("PARTNER_TOKEN")
if partner_token and ZidClient is not None:
    try:
        client = ZidClient(
            authorization=partner_token,
            store_id=os.getenv("STORE_ID"),
            store_token=os.getenv("ACCESS_TOKEN")
        )
    except Exception:
        client = None
        print("WARNING: Failed to initialize ZidClient — continuing without it.")
elif partner_token and ZidClient is None:
    client = None
    print("WARNING: Zid SDK not installed. ZidClient unavailable.")
else:
    client = None
    print("WARNING: PARTNER_TOKEN not found in .env. ZidClient not initialized.")

# تفعيل CORS عشان الفرونت اند (React) يقدر يكلم الباك اند بدون مشاكل
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # في الهاكاثون نفتحها للكل للسرعة
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database setup was moved to the top.

# 2. Endpoint لاستقبال الـ Webhook من زد (Automate things)
@app.post("/api/webhook/order")
async def receive_order_webhook(request: Request):
    payload = await request.json()
    
    # استخراج البيانات الأساسية
    order_id = payload.get("data", {}).get("id", "Unknown")
    customer_name = payload.get("data", {}).get("customer", {}).get("name", "Unknown")
    total = payload.get("data", {}).get("totals", {}).get("total", 0.0)
    
    # حفظ في SQLite
    conn = sqlite3.connect("sandbox.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO orders (order_id, customer_name, total, status) VALUES (?, ?, ?, ?)",
        (order_id, customer_name, total, "New")
    )
    
    # Feature 1: Stock checking simulation
    try:
        # We would normally loop through order products and check stock via SDK
        # Example: stock = client.products.get_product_stock_by_id(item["product_id"])
        product_id = "PROD-1"
        product_name = "ميدالية مفاتيح - Test Product"
        stock_left = 3 # Simulated low stock < 5
        
        if stock_left < 5:
            cursor.execute(
                'INSERT INTO stock_alerts (product_id, product_name, stock_quantity) VALUES (?, ?, ?)',
                (product_id, product_name, stock_left)
            )
            print(f"URGENT ALERT: {product_name} stock is low ({stock_left}).")
    except Exception as e:
        print(f"Error checking stock: {e}")
            
    conn.commit()
    conn.close()
    
    return {"status": "success", "message": f"Order {order_id} automated!"}

@app.get("/api/alerts")
def get_alerts():
    conn = sqlite3.connect('sandbox.db')
    c = conn.cursor()
    c.execute('SELECT id, product_id, product_name, stock_quantity, created_at FROM stock_alerts WHERE is_resolved = 0 ORDER BY created_at DESC')
    alerts = [{"id": row[0], "product_id": row[1], "product_name": row[2], "stock": row[3], "date": row[4]} for row in c.fetchall()]
    conn.close()
    return alerts


@app.post("/api/products/ai-create")
async def create_product_with_ai(request: Request):
    """
    Receives an image and a 'tone'. Uses Gemini to generate product details,
    then pushes the product to Zid via the SDK.
    """
    payload = await request.json()
    image_url = payload.get("image_url", "")
    tone = payload.get("tone", "احترافي")
    
    prompt = f"""
    أنت خبير في التجارة الإلكترونية ومختص بكتابة وصف للمنتجات.
    قم بإنشاء تفاصيل لمنتج جديد بناءً على المعلومات التالية:
    - الرابط أو وصف الصورة: {image_url}
    - النبرة المطلوبة: {tone}
    
    الرجاء تقديم الرد بصيغة JSON تحتوي على:
    "name": اسم المنتج باللغة العربية
    "description": وصف المنتج باللغة العربية
    "price": السعر المقترح كرقم صحيح (مثلاً 50)
    "seo_title": عنوان SEO
    "seo_description": وصف SEO
    """
    
    import json
    
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        # Parse the JSON from the markdown block returned by Gemini
        text = response.text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
            
        ai_data = json.loads(text.strip())
        
        # Now we would push this to Zid!
        # For PoC, we will simulate the push if client is None
        if client:
            # Example SDK call: client.products.create_a_new_product(name=ai_data["name"], ...)
            pass
            
        return {"status": "success", "data": ai_data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 3. Endpoint للفرونت اند عشان يعرض الطلبات في لوحة التحكم
@app.get("/api/orders")
def get_orders():
    conn = sqlite3.connect("sandbox.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders")
    rows = cursor.fetchall()
    conn.close()
    
    # تحويل البيانات لمصفوفة عشان الرياكت
    orders = [{"order_id": r[0], "customer_name": r[1], "total": r[2], "status": r[3]} for r in rows]
    return orders

# لتشغيل السيرفر: uvicorn main:app --reload
