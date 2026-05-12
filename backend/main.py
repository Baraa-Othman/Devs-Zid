from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sqlite3
import uuid

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except ImportError:
    firebase_admin = None
    credentials = None
    firestore = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
load_dotenv()

app = FastAPI(title="Zid Automation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ZID_CLIENT_ID = os.getenv("ZID_CLIENT_ID")
ZID_CLIENT_SECRET = os.getenv("ZID_CLIENT_SECRET")
ZID_REDIRECT_URI = os.getenv("ZID_REDIRECT_URI")
ZID_CALLBACK_URI = os.getenv("ZID_CALLBACK_URI")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN") or os.getenv("ZID_ACCESS_TOKEN")
AUTHORIZATION_TOKEN = os.getenv("ZID_AUTHORIZATION") or os.getenv("AUTHORIZATION")
ZID_STORE_ID = os.getenv("ZID_STORE_ID") or os.getenv("STORE_ID")

ZID_AUTH_URL = "https://oauth.zid.sa/oauth/authorize"
ZID_TOKEN_URL = "https://oauth.zid.sa/oauth/token"
ZID_API_BASE = "https://api.zid.sa/v1"

LOW_STOCK_THRESHOLD = int(os.getenv("LOW_STOCK_THRESHOLD", "5"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

token_store = {
    "access_token": ACCESS_TOKEN,
    "refresh_token": None,
    "authorization": AUTHORIZATION_TOKEN,
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def to_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def first_value(*values, default=None):
    for value in values:
        if value is not None and value != "":
            return value
    return default


def nested(data, *keys):
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def resolve_local_path(raw_path):
    if not raw_path:
        return None

    path = Path(raw_path)
    if path.is_absolute() and path.exists():
        return str(path)

    cwd_path = Path.cwd() / path
    if cwd_path.exists():
        return str(cwd_path)

    backend_path = BASE_DIR / path
    if backend_path.exists():
        return str(backend_path)

    return str(backend_path)


class SQLiteStore:
    mode = "sqlite"

    def __init__(self):
        self.db_path = BASE_DIR / "sandbox.db"
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    customer_name TEXT,
                    total REAL,
                    status TEXT,
                    payload TEXT,
                    items TEXT,
                    created_at TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    product_id TEXT,
                    product_name TEXT,
                    sku TEXT,
                    current_stock REAL,
                    threshold REAL,
                    sold_quantity REAL,
                    sales_velocity REAL,
                    severity_score REAL,
                    source TEXT,
                    updated_at TEXT,
                    payload TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS product_drafts (
                    id TEXT PRIMARY KEY,
                    payload TEXT,
                    created_at TEXT
                )
                """
            )
            conn.commit()

    def status(self):
        return {
            "mode": self.mode,
            "connected": True,
            "path": str(self.db_path),
        }

    def save_order(self, order):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO orders
                (order_id, customer_name, total, status, payload, items, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order["order_id"],
                    order.get("customer_name", "Unknown"),
                    to_float(order.get("total")),
                    order.get("status", "New"),
                    json.dumps(order.get("payload", {})),
                    json.dumps(order.get("items", [])),
                    order.get("created_at", now_iso()),
                ),
            )
            conn.commit()

    def list_orders(self, limit=100):
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT order_id, customer_name, total, status, payload, items, created_at
                FROM orders
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        orders = []
        for row in rows:
            orders.append(
                {
                    "order_id": row[0],
                    "customer_name": row[1],
                    "total": row[2],
                    "status": row[3],
                    "payload": json.loads(row[4] or "{}"),
                    "items": json.loads(row[5] or "[]"),
                    "created_at": row[6],
                }
            )
        return orders

    def save_alert(self, alert):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO alerts
                (id, product_id, product_name, sku, current_stock, threshold,
                 sold_quantity, sales_velocity, severity_score, source, updated_at, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert["id"],
                    alert.get("product_id"),
                    alert.get("product_name"),
                    alert.get("sku"),
                    to_float(alert.get("current_stock")),
                    to_float(alert.get("threshold")),
                    to_float(alert.get("sold_quantity")),
                    to_float(alert.get("sales_velocity")),
                    to_float(alert.get("severity_score")),
                    alert.get("source"),
                    alert.get("updated_at", now_iso()),
                    json.dumps(alert),
                ),
            )
            conn.commit()

    def delete_alert(self, alert_id):
        with self._connect() as conn:
            conn.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
            conn.commit()

    def list_alerts(self):
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload FROM alerts
                ORDER BY severity_score DESC, current_stock ASC
                """
            ).fetchall()

        return [json.loads(row[0] or "{}") for row in rows]

    def save_draft(self, draft):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO product_drafts (id, payload, created_at)
                VALUES (?, ?, ?)
                """,
                (draft["draft_id"], json.dumps(draft), draft.get("created_at", now_iso())),
            )
            conn.commit()


class FirestoreStore:
    mode = "firestore"

    def __init__(self):
        if firebase_admin is None:
            raise RuntimeError("firebase-admin is not installed")

        if not firebase_admin._apps:
            service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
            service_account_file = (
                os.getenv("FIREBASE_SERVICE_ACCOUNT_FILE")
                or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            )
            project_id = os.getenv("FIREBASE_PROJECT_ID")
            options = {"projectId": project_id} if project_id else None

            if service_account_json:
                cred = credentials.Certificate(json.loads(service_account_json))
                firebase_admin.initialize_app(cred, options=options)
            elif service_account_file:
                cred = credentials.Certificate(resolve_local_path(service_account_file))
                firebase_admin.initialize_app(cred, options=options)
            else:
                firebase_admin.initialize_app(options=options)

        self.client = firestore.client()
        self.store_id = ZID_STORE_ID or "local"

    def _collection(self, name):
        return (
            self.client.collection("stores")
            .document(str(self.store_id))
            .collection(name)
        )

    def status(self):
        return {
            "mode": self.mode,
            "connected": True,
            "store_id": self.store_id,
            "project_id": os.getenv("FIREBASE_PROJECT_ID"),
        }

    def save_order(self, order):
        self._collection("orders").document(str(order["order_id"])).set(order)

    def list_orders(self, limit=100):
        docs = self._collection("orders").stream()
        orders = [doc.to_dict() or {} for doc in docs]
        orders.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return orders[:limit]

    def save_alert(self, alert):
        self._collection("alerts").document(str(alert["id"])).set(alert)

    def delete_alert(self, alert_id):
        self._collection("alerts").document(str(alert_id)).delete()

    def list_alerts(self):
        docs = self._collection("alerts").stream()
        alerts = [doc.to_dict() or {} for doc in docs]
        alerts.sort(
            key=lambda item: (
                to_float(item.get("severity_score")),
                -to_float(item.get("current_stock")),
            ),
            reverse=True,
        )
        return alerts

    def save_draft(self, draft):
        self._collection("product_drafts").document(str(draft["draft_id"])).set(draft)


def build_store():
    try:
        return FirestoreStore(), None
    except Exception as exc:
        return SQLiteStore(), str(exc)


storage, storage_warning = build_store()


def zid_headers():
    manager_token = token_store.get("access_token") or ACCESS_TOKEN
    authorization = token_store.get("authorization") or AUTHORIZATION_TOKEN

    if authorization and not str(authorization).lower().startswith("bearer "):
        authorization = f"Bearer {authorization}"
    elif not authorization and manager_token:
        authorization = f"Bearer {manager_token}"

    headers = {
        "Accept": "application/json",
        "Accept-Language": "ar",
        "Content-Type": "application/json",
        "Role": "Manager",
    }

    if manager_token:
        headers["X-Manager-Token"] = manager_token
        headers["X-MANAGER-TOKEN"] = manager_token
        headers["Access-Token"] = manager_token
    if authorization:
        headers["Authorization"] = authorization
    if ZID_STORE_ID:
        headers["Store-Id"] = str(ZID_STORE_ID)

    return headers


def zid_ready():
    return bool((token_store.get("access_token") or ACCESS_TOKEN) and ZID_STORE_ID)


def get_order_data(payload):
    return (
        payload.get("data")
        or payload.get("order")
        or payload.get("payload")
        or payload
    )


def extract_order_items(order_data):
    candidates = [
        order_data.get("products"),
        order_data.get("items"),
        order_data.get("line_items"),
        order_data.get("order_products"),
        nested(order_data, "order", "products"),
        nested(order_data, "data", "products"),
    ]

    raw_items = next((items for items in candidates if isinstance(items, list)), [])
    normalized = []

    for item in raw_items:
        if not isinstance(item, dict):
            continue

        product = item.get("product") if isinstance(item.get("product"), dict) else {}
        product_id = first_value(
            item.get("product_id"),
            product.get("id"),
            item.get("id"),
        )
        quantity = to_int(first_value(item.get("quantity"), item.get("qty")), 1)
        name = first_value(
            item.get("product_name"),
            item.get("name"),
            product.get("name"),
            nested(item, "name", "ar"),
            default="Unknown product",
        )
        sku = first_value(item.get("sku"), product.get("sku"), item.get("SKU"))

        stock_value = first_value(
            item.get("available_quantity"),
            item.get("current_stock"),
            item.get("stock"),
            product.get("quantity"),
            product.get("available_quantity"),
        )

        normalized.append(
            {
                "product_id": str(product_id) if product_id is not None else None,
                "product_name": str(name),
                "sku": str(sku) if sku else None,
                "quantity": quantity,
                "current_stock": None if stock_value is None else to_float(stock_value),
                "raw": item,
            }
        )

    return normalized


def extract_stock_from_product(product):
    if not isinstance(product, dict):
        return None

    data = product.get("data") if isinstance(product.get("data"), dict) else product
    if data.get("is_infinite") is True:
        return None

    quantity = first_value(
        data.get("quantity"),
        data.get("available_quantity"),
        data.get("stock"),
    )
    if quantity is not None:
        return to_float(quantity)

    stocks = data.get("stocks")
    if isinstance(stocks, list):
        finite_quantities = [
            to_float(stock.get("available_quantity"))
            for stock in stocks
            if isinstance(stock, dict) and not stock.get("is_infinite")
        ]
        if finite_quantities:
            return sum(finite_quantities)

    return None


async def fetch_zid_product(product_id):
    if not product_id or not zid_ready():
        return None

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{ZID_API_BASE}/products/{product_id}/",
            headers=zid_headers(),
            timeout=15,
        )

    if response.status_code >= 400:
        return None

    return response.json()


def order_summary(payload):
    data = get_order_data(payload)
    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    totals = data.get("totals") if isinstance(data.get("totals"), dict) else {}

    return {
        "order_id": str(first_value(data.get("id"), data.get("order_id"), uuid.uuid4())),
        "customer_name": first_value(
            customer.get("name"),
            data.get("customer_name"),
            nested(data, "customer", "full_name"),
            default="Unknown",
        ),
        "total": to_float(first_value(totals.get("total"), data.get("total"), data.get("grand_total"))),
        "status": first_value(data.get("status"), data.get("order_status"), default="New"),
        "items": extract_order_items(data),
        "payload": payload,
        "created_at": now_iso(),
    }


def sales_velocity_for(product_id, sku):
    sold_quantity = 0
    matching_dates = []

    for order in storage.list_orders(limit=1000):
        for item in order.get("items", []):
            same_product = product_id and item.get("product_id") == product_id
            same_sku = sku and item.get("sku") == sku
            if same_product or same_sku:
                sold_quantity += to_int(item.get("quantity"), 0)
                matching_dates.append(order.get("created_at"))

    if not matching_dates:
        return sold_quantity, float(sold_quantity)

    parsed_dates = []
    for raw_date in matching_dates:
        try:
            parsed_dates.append(datetime.fromisoformat(str(raw_date).replace("Z", "+00:00")))
        except ValueError:
            pass

    if len(parsed_dates) < 2:
        return sold_quantity, float(sold_quantity)

    days = max((max(parsed_dates) - min(parsed_dates)).days, 1)
    return sold_quantity, round(sold_quantity / days, 2)


async def update_low_stock_alerts(order):
    alerts_changed = []

    for item in order.get("items", []):
        product_id = item.get("product_id")
        sku = item.get("sku")
        stock = item.get("current_stock")
        source = "webhook"

        if stock is None and product_id:
            product = await fetch_zid_product(product_id)
            stock = extract_stock_from_product(product)
            source = "zid_product_api" if stock is not None else "webhook"

        alert_id = product_id or sku
        if not alert_id:
            continue

        if stock is None:
            continue

        sold_quantity, velocity = sales_velocity_for(product_id, sku)

        if stock <= LOW_STOCK_THRESHOLD:
            severity_score = ((LOW_STOCK_THRESHOLD - stock) + 1) * 10 + velocity
            alert = {
                "id": str(alert_id),
                "product_id": product_id,
                "product_name": item.get("product_name") or "Unknown product",
                "sku": sku,
                "current_stock": stock,
                "threshold": LOW_STOCK_THRESHOLD,
                "sold_quantity": sold_quantity,
                "sales_velocity": velocity,
                "severity_score": round(severity_score, 2),
                "source": source,
                "updated_at": now_iso(),
            }
            storage.save_alert(alert)
            alerts_changed.append(alert)
        else:
            storage.delete_alert(str(alert_id))

    return alerts_changed


def mock_product_draft(image_url, tone):
    tone_label = {
        "playful": "Playful",
        "friendly": "Friendly",
        "luxury": "Luxury",
        "professional": "Professional",
        "energetic": "Energetic",
    }.get(str(tone).lower(), "Professional")

    draft_id = str(uuid.uuid4())
    name_en = f"{tone_label} AI Product"
    name_ar = "منتج ذكي جاهز للبيع"
    bullets = [
        "Clear product positioning for online shoppers",
        "Bilingual copy ready for Zid product pages",
        "Short selling points for faster review",
    ]

    return {
        "draft_id": draft_id,
        "mode": "mock",
        "image_url": image_url,
        "tone": tone,
        "name": name_ar,
        "name_ar": name_ar,
        "name_en": name_en,
        "description_ar": "وصف عربي مبدئي للمنتج يمكنك تعديله قبل النشر في متجرك.",
        "description_en": "A clean product description draft you can review, edit, and publish to your Zid store.",
        "bullets": bullets,
        "tags": ["zid", "ai-generated", str(tone).lower()],
        "price": 99,
        "seo_title": name_ar,
        "seo_title_ar": name_ar,
        "seo_title_en": name_en,
        "created_at": now_iso(),
    }


async def generate_ai_product_draft(image_url, tone):
    if not GEMINI_API_KEY or genai is None:
        return mock_product_draft(image_url, tone)

    prompt = f"""
Create a Zid ecommerce product draft from this product image URL:
{image_url}

Tone: {tone}

Return JSON only with these keys:
name_ar, name_en, description_ar, description_en, bullets, tags, price,
seo_title_ar, seo_title_en.
Bullets and tags must be arrays. Arabic and English output are both required.
"""

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = await model.generate_content_async(prompt)
        text = response.text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text.replace("json\n", "", 1).replace("JSON\n", "", 1)

        parsed = json.loads(text)
        draft = mock_product_draft(image_url, tone)
        draft.update(parsed)
        draft["mode"] = "gemini"
        return draft
    except Exception:
        return mock_product_draft(image_url, tone)


def product_payload_for_zid(draft):
    name = first_value(
        draft.get("name_ar"),
        draft.get("name"),
        draft.get("name_en"),
        default="AI generated product",
    )
    description = first_value(
        draft.get("description_ar"),
        draft.get("description"),
        draft.get("description_en"),
        default="Generated product description",
    )
    price = to_float(first_value(draft.get("price"), draft.get("suggested_price")), 99)

    return {
        "name": name,
        "description": description,
        "price": price,
        "sku": draft.get("sku") or f"AI-{uuid.uuid4().hex[:8].upper()}",
        "requires_shipping": True,
        "is_draft": False,
        "is_infinite": False,
        "is_taxable": True,
    }


@app.get("/")
def read_root():
    return {
        "status": "online",
        "oauth_configured": bool(ZID_CLIENT_ID),
        "token_available": bool(token_store.get("access_token")),
        "storage": storage.status(),
        "storage_warning": storage_warning,
        "message": "Zid Automation API is running",
    }


@app.get("/api/storage/status")
def storage_status():
    return {
        "status": "success",
        "data": storage.status(),
        "warning": storage_warning,
    }


@app.get("/auth/login")
def oauth_login():
    if not ZID_CLIENT_ID or not ZID_REDIRECT_URI:
        raise HTTPException(status_code=400, detail="Missing ZID_CLIENT_ID or ZID_REDIRECT_URI")

    auth_url = (
        f"{ZID_AUTH_URL}"
        f"?client_id={ZID_CLIENT_ID}"
        f"&redirect_uri={ZID_REDIRECT_URI}"
        f"&response_type=code"
    )
    return RedirectResponse(url=auth_url)


@app.get("/auth/redirect")
async def oauth_redirect(code: str = None, error: str = None):
    if error or not code:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error or 'no code returned'}")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            ZID_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": ZID_CLIENT_ID,
                "client_secret": ZID_CLIENT_SECRET,
                "redirect_uri": ZID_REDIRECT_URI,
                "code": code,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Token exchange failed: {response.text}")

    data = response.json()
    token_store["access_token"] = data.get("access_token")
    token_store["refresh_token"] = data.get("refresh_token")
    token_store["authorization"] = data.get("Authorization") or data.get("authorization")

    return JSONResponse(
        {
            "status": "authenticated",
            "access_token": token_store["access_token"],
            "message": "OAuth flow completed successfully",
        }
    )


@app.get("/auth/callback")
async def oauth_callback(code: str = None, error: str = None):
    return await oauth_redirect(code=code, error=error)


@app.post("/auth/refresh")
async def refresh_token():
    rt = token_store.get("refresh_token")
    if not rt:
        raise HTTPException(status_code=400, detail="No refresh token stored. Re-authenticate.")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            ZID_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": ZID_CLIENT_ID,
                "client_secret": ZID_CLIENT_SECRET,
                "refresh_token": rt,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Refresh failed: {response.text}")

    data = response.json()
    token_store["access_token"] = data.get("access_token")
    token_store["refresh_token"] = data.get("refresh_token", rt)
    token_store["authorization"] = data.get("Authorization") or data.get("authorization")

    return {"status": "token refreshed", "access_token": token_store["access_token"]}


@app.get("/auth/status")
def auth_status():
    return {
        "authenticated": bool(token_store.get("access_token")),
        "has_refresh_token": bool(token_store.get("refresh_token")),
        "store_id_available": bool(ZID_STORE_ID),
    }


@app.post("/api/webhook/order")
async def receive_order_webhook(request: Request):
    payload = await request.json()
    order = order_summary(payload)
    storage.save_order(order)
    alerts_changed = await update_low_stock_alerts(order)

    return {
        "status": "success",
        "message": f"Order {order['order_id']} received.",
        "order": {
            "order_id": order["order_id"],
            "customer_name": order["customer_name"],
            "total": order["total"],
            "items_count": len(order["items"]),
        },
        "alerts_changed": alerts_changed,
    }


@app.get("/api/orders")
def get_orders():
    orders = storage.list_orders(limit=100)
    return [
        {
            "order_id": order.get("order_id"),
            "customer_name": order.get("customer_name", "Unknown"),
            "total": order.get("total", 0.0),
            "status": order.get("status", "New"),
            "items_count": len(order.get("items", [])),
            "created_at": order.get("created_at"),
        }
        for order in orders
    ]


@app.get("/api/alerts")
def get_alerts():
    return {
        "status": "success",
        "alerts": storage.list_alerts(),
        "threshold": LOW_STOCK_THRESHOLD,
    }


@app.post("/api/alerts/recalculate")
async def recalculate_alerts():
    changed = []
    for order in storage.list_orders(limit=1000):
        changed.extend(await update_low_stock_alerts(order))

    return {
        "status": "success",
        "alerts_changed": changed,
        "alerts": storage.list_alerts(),
    }


@app.get("/api/zid/orders")
async def get_zid_orders():
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{ZID_API_BASE}/managers/store/orders/",
            headers=zid_headers(),
            params={"store_id": ZID_STORE_ID},
            timeout=15,
        )

    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Zid API: Unauthorized. Re-authenticate via /auth/login")
    if response.status_code == 429:
        raise HTTPException(status_code=429, detail="Zid API: Rate limit hit. Try again shortly.")
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    return response.json()


@app.get("/api/zid/products")
async def get_zid_products():
    if not zid_ready():
        raise HTTPException(status_code=400, detail="Missing Zid token or store id")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{ZID_API_BASE}/products/",
            headers=zid_headers(),
            timeout=15,
        )

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    return response.json()


@app.post("/api/products/ai-create")
async def ai_create_product(request: Request):
    body = await request.json()
    image_url = body.get("image_url")
    tone = body.get("tone", "professional")

    if not image_url:
        raise HTTPException(status_code=400, detail="image_url is required")

    draft = await generate_ai_product_draft(image_url, tone)
    storage.save_draft(draft)

    return {
        "status": "success",
        "message": "Product draft generated",
        "data": draft,
    }


@app.post("/api/products/publish")
async def publish_product(request: Request):
    draft = await request.json()

    if not zid_ready():
        raise HTTPException(
            status_code=400,
            detail="Missing Zid ACCESS_TOKEN/ZID_ACCESS_TOKEN or ZID_STORE_ID/STORE_ID",
        )

    payload = product_payload_for_zid(draft)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{ZID_API_BASE}/products/",
            headers=zid_headers(),
            json=payload,
            timeout=20,
        )

    if response.status_code not in (200, 201):
        raise HTTPException(status_code=response.status_code, detail=response.text)

    return {
        "status": "success",
        "message": "Product published to Zid",
        "zid_payload": payload,
        "zid_response": response.json(),
    }


# To run: .\venv\Scripts\python -m uvicorn main:app --reload
