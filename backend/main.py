from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import sqlite3

app = FastAPI()

# تفعيل CORS عشان الفرونت اند (React) يقدر يكلم الباك اند بدون مشاكل
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # في الهاكاثون نفتحها للكل للسرعة
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. إعداد قاعدة بيانات SQLite سريعة
def init_db():
    conn = sqlite3.connect("sandbox.db")
    cursor = conn.cursor()
    # جدول بسيط يحفظ الطلبات القادمة من زد
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            customer_name TEXT,
            total REAL,
            status TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# 2. Endpoint لاستقبال الـ Webhook من زد (Automate things)
@app.post("/api/webhook/order")
async def receive_order_webhook(request: Request):
    payload = await request.json()
    
    # استخراج البيانات الأساسية (تأكد من مطابقتها لـ JSON حق زد)
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
    conn.commit()
    conn.close()
    
    return {"status": "success", "message": f"Order {order_id} automated!"}

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
