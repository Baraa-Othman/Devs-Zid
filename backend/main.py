from datetime import datetime, timezone
from pathlib import Path
import base64
import binascii
import json
import os
import uuid

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

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
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN") or os.getenv("ZID_ACCESS_TOKEN")
AUTHORIZATION_TOKEN = os.getenv("ZID_AUTHORIZATION") or os.getenv("AUTHORIZATION")
ZID_STORE_ID = os.getenv("ZID_STORE_ID") or os.getenv("STORE_ID")

ZID_AUTH_URL = "https://oauth.zid.sa/oauth/authorize"
ZID_TOKEN_URL = "https://oauth.zid.sa/oauth/token"
ZID_API_BASE = "https://api.zid.sa/v1"

LOW_STOCK_THRESHOLD = int(os.getenv("LOW_STOCK_THRESHOLD", "5"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")

AI_PRODUCT_FIELDS = [
    "trendy_name",
    "trendy_name_arabic",
    "description",
    "description_arabic",
    "marketing_audience",
    "marketing_partners",
    "recommended_price",
    "marketing_plan",
]

AI_EXPLANATION_FALLBACKS = {
    "trendy_name": "Chosen to make the product feel searchable and current.",
    "trendy_name_arabic": "Chosen to sound natural for Arabic-speaking shoppers.",
    "description": "Written to connect product details with a clear shopper benefit.",
    "description_arabic": "Written to keep the Arabic product story clear and persuasive.",
    "marketing_audience": "Selected from the product details and likely buyer intent.",
    "marketing_partners": "Suggested from channels that can realistically promote this item.",
    "recommended_price": "Estimated from perceived value, positioning, and merchant context.",
    "marketing_plan": "Built around simple launch actions a merchant can execute quickly.",
}

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


# Local persistence is intentionally disabled for now. The dashboard reads
# orders, products, and alerts directly from Zid so Zid stays the source of truth.


def zid_headers(content_type="application/json"):
    manager_token = token_store.get("access_token") or ACCESS_TOKEN
    authorization = token_store.get("authorization") or AUTHORIZATION_TOKEN

    if authorization and not str(authorization).lower().startswith("bearer "):
        authorization = f"Bearer {authorization}"
    elif not authorization and manager_token:
        authorization = f"Bearer {manager_token}"

    headers = {
        "Accept": "application/json",
        "Accept-Language": "ar",
        "Role": "Manager",
    }
    if content_type:
        headers["Content-Type"] = content_type

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


def zid_status():
    return {
        "source": "zid_api",
        "connected": zid_ready(),
        "store_id_available": bool(ZID_STORE_ID),
        "token_available": bool(token_store.get("access_token") or ACCESS_TOKEN),
        "api_base": ZID_API_BASE,
    }


async def zid_request(path, params=None, method="GET", json_body=None):
    if not zid_ready():
        raise HTTPException(
            status_code=400,
            detail="Missing Zid ACCESS_TOKEN/ZID_ACCESS_TOKEN and ZID_STORE_ID/STORE_ID",
        )

    url = f"{ZID_API_BASE}{path}"
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method,
            url,
            headers=zid_headers(),
            params=params,
            json=json_body,
            timeout=20,
        )

    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Zid API: Unauthorized. Re-authenticate via /auth/login")
    if response.status_code == 429:
        raise HTTPException(status_code=429, detail="Zid API: Rate limit hit. Try again shortly.")
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    if response.status_code == 204 or not response.content:
        return {}

    return response.json()


async def zid_multipart_request(path, form_body=None, method="POST"):
    if not zid_ready():
        raise HTTPException(
            status_code=400,
            detail="Missing Zid ACCESS_TOKEN/ZID_ACCESS_TOKEN and ZID_STORE_ID/STORE_ID",
        )

    files = {
        key: (None, str(value))
        for key, value in (form_body or {}).items()
        if value is not None
    }

    async with httpx.AsyncClient() as client:
        response = await client.request(
            method,
            f"{ZID_API_BASE}{path}",
            headers=zid_headers(content_type=None),
            files=files,
            timeout=20,
        )

    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Zid API: Unauthorized. Re-authenticate via /auth/login")
    if response.status_code == 429:
        raise HTTPException(status_code=429, detail="Zid API: Rate limit hit. Try again shortly.")
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    if response.status_code == 204 or not response.content:
        return {}

    return response.json()


def payload_list(payload, *keys):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    search_keys = keys or ("data", "payload", "results", "orders", "products")
    for key in search_keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            found = payload_list(value, *search_keys)
            if found:
                return found

    return []


def localized_text(value, default="-"):
    if isinstance(value, dict):
        return first_value(value.get("ar"), value.get("en"), *value.values(), default=default)
    return first_value(value, default=default)


def localized_pair(value, default=""):
    if isinstance(value, dict):
        ar = first_value(value.get("ar"), value.get("en"), *value.values(), default=default)
        en = first_value(value.get("en"), value.get("ar"), *value.values(), default=default)
        return {"ar": ar, "en": en}

    text = first_value(value, default=default)
    return {"ar": text, "en": text}


def get_order_data(payload):
    if not isinstance(payload, dict):
        return {}

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


def order_summary(payload):
    data = get_order_data(payload)
    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    totals = data.get("totals") if isinstance(data.get("totals"), dict) else {}
    status = data.get("status") if isinstance(data.get("status"), str) else None
    order_status = data.get("order_status")
    order_status_code = None
    order_status_name = None
    if isinstance(order_status, dict):
        order_status_code = order_status.get("code")
        order_status_name = order_status.get("name")
        order_status = first_value(order_status_name, order_status_code)

    display_status = data.get("display_status") if isinstance(data.get("display_status"), dict) else {}

    return {
        "order_id": str(first_value(data.get("id"), data.get("order_id"), uuid.uuid4())),
        "customer_name": first_value(
            customer.get("name"),
            data.get("customer_name"),
            nested(data, "customer", "full_name"),
            default="Unknown",
        ),
        "total": to_float(
            first_value(
                totals.get("total"),
                data.get("order_total"),
                data.get("total"),
                data.get("grand_total"),
            )
        ),
        "status": first_value(status, order_status, default="New"),
        "status_code": first_value(order_status_code, display_status.get("code"), status),
        "status_name": first_value(order_status_name, display_status.get("name"), status, default="New"),
        "display_status": {
            "code": display_status.get("code"),
            "name": display_status.get("name"),
            "color": display_status.get("color"),
        },
        "payment_status": data.get("payment_status"),
        "items": extract_order_items(data),
        "payload": payload,
        "created_at": first_value(
            data.get("created_at"),
            data.get("created_date"),
            data.get("date_created"),
            data.get("updated_at"),
            default=now_iso(),
        ),
    }


def normalize_product(product):
    if not isinstance(product, dict):
        return {}

    data = product.get("data") if isinstance(product.get("data"), dict) else product
    product_id = first_value(data.get("id"), data.get("uuid"), data.get("product_id"))
    names = localized_pair(first_value(data.get("name"), data.get("title"), default="Unknown product"))
    descriptions = localized_pair(first_value(data.get("description"), data.get("short_description"), default=""))
    name = localized_text(first_value(data.get("name"), data.get("title"), default="Unknown product"))
    stock = extract_stock_from_product(data)

    return {
        "id": str(product_id) if product_id is not None else None,
        "product_id": str(product_id) if product_id is not None else None,
        "product_name": name,
        "name": name,
        "name_ar": names.get("ar"),
        "name_en": names.get("en"),
        "description": descriptions.get("en"),
        "description_arabic": descriptions.get("ar"),
        "description_ar": descriptions.get("ar"),
        "description_en": descriptions.get("en"),
        "sku": first_value(data.get("sku"), data.get("SKU")),
        "price": to_float(first_value(data.get("price"), data.get("sale_price"))),
        "current_stock": stock,
        "is_infinite": bool(data.get("is_infinite")),
        "is_published": data.get("is_published"),
        "raw": product,
    }


def normalize_coupon(coupon):
    if not isinstance(coupon, dict):
        return {}

    coupon_id = first_value(coupon.get("coupon_id"), coupon.get("id"))
    return {
        "id": str(coupon_id) if coupon_id is not None else None,
        "coupon_id": str(coupon_id) if coupon_id is not None else None,
        "name": first_value(coupon.get("name"), default="Coupon"),
        "code": first_value(coupon.get("code"), default=""),
        "discount_type": first_value(coupon.get("discount_type"), default="p"),
        "discount": to_float(coupon.get("discount")),
        "total": to_float(coupon.get("total")),
        "uses_total": to_int(coupon.get("uses_total")),
        "uses_customer": to_int(coupon.get("uses_customer")),
        "date_start": coupon.get("date_start"),
        "date_end": coupon.get("date_end"),
        "coupon_status": bool(coupon.get("coupon_status") or coupon.get("enabled")),
        "enabled": bool(coupon.get("enabled") or coupon.get("coupon_status")),
        "free_shipping": bool(coupon.get("free_shipping")),
        "free_cod": bool(coupon.get("free_cod")),
        "apply_to": first_value(coupon.get("apply_to"), default="all"),
        "status_code": coupon.get("status_code"),
        "raw": coupon,
    }


async def fetch_zid_orders(limit=100, payload_type="default"):
    payload = await zid_request(
        "/managers/store/orders/",
        params={
            "store_id": ZID_STORE_ID,
            "per_page": limit,
            "payload_type": payload_type,
            "sort_by": "desc",
        },
    )
    raw_orders = payload_list(payload, "orders", "data", "payload", "results")
    return [order_summary(order) for order in raw_orders[:limit]]


async def fetch_zid_products(limit=100):
    payload = await zid_request(
        "/products/",
        params={"page_size": limit, "extended": "true"},
    )
    raw_products = payload_list(payload, "results", "products", "data", "payload")
    return [product for product in (normalize_product(item) for item in raw_products[:limit]) if product]


async def fetch_zid_coupons(limit=100):
    coupons = []
    page = 1
    page_size = min(limit, 100)

    while len(coupons) < limit:
        payload = await zid_request(
            "/managers/store/coupons",
            params={"page": page, "page_size": page_size},
        )
        raw_coupons = payload_list(payload, "coupons", "data", "payload", "results")
        coupons.extend(
            coupon
            for coupon in (normalize_coupon(item) for item in raw_coupons)
            if coupon
        )

        pagination = payload.get("pagination") if isinstance(payload, dict) else {}
        next_page = pagination.get("next_page") if isinstance(pagination, dict) else None
        if not raw_coupons or not next_page or next_page == page:
            break
        page = to_int(next_page, page + 1)

    return coupons[:limit]


def sales_velocity_for(orders, product_id, sku):
    sold_quantity = 0
    matching_dates = []

    for order in orders:
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


async def build_low_stock_alerts():
    products = await fetch_zid_products(limit=100)
    try:
        orders = await fetch_zid_orders(limit=100, payload_type="default")
    except HTTPException:
        orders = []

    alerts = []
    for product in products:
        stock = product.get("current_stock")
        if stock is None or product.get("is_infinite") or stock > LOW_STOCK_THRESHOLD:
            continue

        product_id = product.get("product_id")
        sku = product.get("sku")
        sold_quantity, velocity = sales_velocity_for(orders, product_id, sku)
        severity_score = ((LOW_STOCK_THRESHOLD - stock) + 1) * 10 + velocity

        alerts.append(
            {
                "id": str(product_id or sku),
                "product_id": product_id,
                "product_name": product.get("product_name") or "Unknown product",
                "sku": sku,
                "current_stock": stock,
                "threshold": LOW_STOCK_THRESHOLD,
                "sold_quantity": sold_quantity,
                "sales_velocity": velocity,
                "severity_score": round(severity_score, 2),
                "source": "zid_products_api",
                "updated_at": now_iso(),
            }
        )

    alerts.sort(
        key=lambda item: (
            to_float(item.get("severity_score")),
            -to_float(item.get("current_stock")),
        ),
        reverse=True,
    )
    return alerts


def legacy_mock_product_draft(image_url, tone, product_details=""):
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
    details = product_details or "Generated from the uploaded product image."

    return {
        "draft_id": draft_id,
        "mode": "mock",
        "image_url": image_url,
        "tone": tone,
        "product_details": product_details,
        "trendy_name": name_en,
        "trendy_name_arabic": name_ar,
        "name": name_ar,
        "name_ar": name_ar,
        "name_en": name_en,
        "description": f"A clean product description draft based on: {details}",
        "description_ar": "وصف عربي مبدئي للمنتج يمكنك تعديله قبل النشر في متجرك.",
        "description_en": f"A clean product description draft based on: {details}",
        "marketing_audience": "Online shoppers looking for practical, well-presented products.",
        "marketing_partners": ["Zid store", "Social media creators", "Local retail partners"],
        "recommended_price": 99,
        "marketing_plan": "Launch with a clear product page, short social clips, and a limited-time opening offer.",
        "bullets": bullets,
        "tags": ["zid", "ai-generated", str(tone).lower()],
        "price": 99,
        "seo_title": name_ar,
        "seo_title_ar": name_ar,
        "seo_title_en": name_en,
        "created_at": now_iso(),
    }


def normalize_ai_draft(raw, image_url="", tone="professional", product_details="", mode="gemini"):
    source = raw if isinstance(raw, dict) else {}
    normalized = {
        "draft_id": str(source.get("draft_id") or uuid.uuid4()),
        "mode": mode,
        "image_url": image_url,
        "tone": tone,
        "product_details": product_details,
        "created_at": source.get("created_at") or now_iso(),
    }

    fallback = mock_product_draft(image_url, tone, product_details)
    for key in AI_PRODUCT_FIELDS:
        value = source.get(key, fallback.get(key))
        if key == "marketing_partners":
            if isinstance(value, str):
                value = [item.strip() for item in value.split(",") if item.strip()]
            if not isinstance(value, list):
                value = fallback[key]
        normalized[key] = value

    explanations = source.get("explanations")
    if not isinstance(explanations, dict):
        explanations = source.get("field_explanations")
    if not isinstance(explanations, dict):
        explanations = {}

    normalized["explanations"] = {
        key: first_value(
            explanations.get(key),
            source.get(f"{key}_explanation"),
            AI_EXPLANATION_FALLBACKS[key],
        )
        for key in AI_PRODUCT_FIELDS
    }
    return normalized


def mock_product_draft(image_url, tone, product_details=""):
    tone_label = {
        "playful": "Playful",
        "friendly": "Friendly",
        "luxury": "Luxury",
        "professional": "Professional",
        "energetic": "Energetic",
    }.get(str(tone).lower(), "Professional")
    details = product_details or "the uploaded product image"
    draft = {
        "trendy_name": f"{tone_label} AI Product",
        "trendy_name_arabic": "AI product ready for sale",
        "description": f"A clear product description based on {details}.",
        "description_arabic": f"Arabic product description based on {details}.",
        "marketing_audience": "Online shoppers looking for practical, well-presented products.",
        "marketing_partners": ["Zid store", "Social media creators", "Local retail partners"],
        "recommended_price": 99,
        "marketing_plan": "Launch with a clear product page, short social clips, and a limited-time opening offer.",
    }
    draft["explanations"] = {key: AI_EXPLANATION_FALLBACKS[key] for key in AI_PRODUCT_FIELDS}
    draft.update(
        {
            "draft_id": str(uuid.uuid4()),
            "mode": "mock",
            "image_url": image_url,
            "tone": tone,
            "product_details": product_details,
            "created_at": now_iso(),
        }
    )
    return draft


async def generate_ai_product_draft(image_url, tone, product_details=""):
    if not GEMINI_API_KEY or genai is None:
        return mock_product_draft(image_url, tone, product_details)

    prompt = f"""
Create a Zid ecommerce product draft from this product image input:
{image_url}

Tone: {tone}
Product details from the merchant:
{product_details or "No extra details provided."}

Return JSON only with these keys:
trendy_name, trendy_name_arabic, description, description_arabic,
marketing_audience, marketing_partners, recommended_price, marketing_plan,
explanations.
marketing_partners must be an array of strings.
explanations must be an object with one short reason for each field:
trendy_name, trendy_name_arabic, description, description_arabic,
marketing_audience, marketing_partners, recommended_price, marketing_plan.
Arabic and English output are both required. Do not include extra keys.
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
        return normalize_ai_draft(parsed, image_url, tone, product_details, mode="gemini")
    except Exception:
        return mock_product_draft(image_url, tone, product_details)


def product_id_from_response(product_response):
    if not isinstance(product_response, dict):
        return None
    product = product_response.get("product") if isinstance(product_response.get("product"), dict) else product_response
    return first_value(product.get("id"), product.get("uuid"), product.get("product_id"))


def data_url_to_upload(image_url):
    if not image_url or not str(image_url).startswith("data:image/"):
        return None

    header, _, encoded = str(image_url).partition(",")
    if not encoded:
        return None

    mime_type = header.split(";", 1)[0].replace("data:", "") or "image/jpeg"
    extension = {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/gif": "gif",
    }.get(mime_type, "jpg")

    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return None

    return f"product-image.{extension}", content, mime_type


async def upload_product_image(product_id, image_url, alt_text):
    upload = data_url_to_upload(image_url)
    if not product_id or upload is None:
        return None

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{ZID_API_BASE}/products/{product_id}/images/",
            headers=zid_headers(content_type=None),
            files={"image": upload},
            data={"alt_text": alt_text or "Product image"},
            timeout=30,
        )

    if response.status_code >= 400:
        return {
            "uploaded": False,
            "status_code": response.status_code,
            "detail": response.text,
        }

    return {
        "uploaded": True,
        "data": response.json(),
    }


def product_payload_for_zid(draft):
    name_ar = first_value(
        draft.get("trendy_name_arabic"),
        draft.get("name_ar"),
        draft.get("name"),
        draft.get("trendy_name"),
        default="AI generated product",
    )
    name_en = first_value(
        draft.get("trendy_name"),
        draft.get("name_en"),
        draft.get("name"),
        draft.get("trendy_name_arabic"),
        default=name_ar,
    )
    description_ar = first_value(
        draft.get("description_arabic"),
        draft.get("description_ar"),
        draft.get("description"),
        default="Generated product description",
    )
    description_en = first_value(
        draft.get("description"),
        draft.get("description_en"),
        draft.get("description_arabic"),
        default=description_ar,
    )
    price = to_float(first_value(draft.get("recommended_price"), draft.get("price"), draft.get("suggested_price")), 99)
    is_infinite = bool(draft.get("is_infinite", False))

    payload = {
        "name": {
            "ar": str(name_ar),
            "en": str(name_en),
        },
        "description": {
            "ar": str(description_ar),
            "en": str(description_en),
        },
        "price": price,
        "sku": draft.get("sku") or f"AI-{uuid.uuid4().hex[:8].upper()}",
        "requires_shipping": True,
        "is_draft": False,
        "is_infinite": is_infinite,
        "is_taxable": True,
    }

    sale_price = first_value(draft.get("sale_price"), draft.get("discount_price"))
    if sale_price not in (None, ""):
        payload["sale_price"] = to_float(sale_price)

    quantity = first_value(draft.get("quantity"), draft.get("stock"), draft.get("available_quantity"))
    if not is_infinite and quantity not in (None, ""):
        payload["quantity"] = to_int(quantity, 0)

    return payload


def validate_publish_draft(draft):
    name = first_value(draft.get("trendy_name"), draft.get("name_en"), draft.get("name"))
    arabic_name = first_value(draft.get("trendy_name_arabic"), draft.get("name_ar"))
    price = first_value(draft.get("recommended_price"), draft.get("price"), draft.get("suggested_price"))
    stock = first_value(draft.get("stock"), draft.get("quantity"), draft.get("available_quantity"))

    if not str(name or "").strip():
        raise HTTPException(status_code=400, detail="Product name is required")
    if not str(arabic_name or "").strip():
        raise HTTPException(status_code=400, detail="Arabic product name is required")
    if price in (None, ""):
        raise HTTPException(status_code=400, detail="Product price is required")
    if to_float(price, None) is None or to_float(price) < 0:
        raise HTTPException(status_code=400, detail="Product price must be 0 or greater")
    if stock in (None, ""):
        raise HTTPException(status_code=400, detail="Product stock is required")
    if to_int(stock, None) is None or to_int(stock) < 0:
        raise HTTPException(status_code=400, detail="Product stock must be 0 or greater")


async def update_zid_product_stock(product_id, new_stock):
    update_payload = {
        "quantity": to_int(new_stock, 0),
        "is_infinite": False,
    }
    last_error = None

    for method in ("PATCH", "PUT"):
        try:
            return await zid_request(
                f"/products/{product_id}/",
                method=method,
                json_body=update_payload,
            )
        except HTTPException as exc:
            if exc.status_code in (401, 429):
                raise
            last_error = exc

    raise last_error or HTTPException(status_code=502, detail="Could not update product stock in Zid")


def product_update_payload_for_zid(body):
    name_en = first_value(body.get("name_en"), body.get("name"), body.get("product_name"))
    name_ar = first_value(body.get("name_ar"), body.get("name_arabic"), body.get("trendy_name_arabic"), name_en)
    description_en = first_value(body.get("description"), body.get("description_en"))
    description_ar = first_value(body.get("description_arabic"), body.get("description_ar"), description_en)
    price = first_value(body.get("price"), body.get("recommended_price"))
    stock = first_value(body.get("stock"), body.get("quantity"), body.get("current_stock"))

    payload = {}

    if name_en not in (None, "") or name_ar not in (None, ""):
        if not str(first_value(name_en, name_ar, default="")).strip():
            raise HTTPException(status_code=400, detail="Product name is required")
        payload["name"] = {
            "ar": str(first_value(name_ar, name_en, default="")).strip(),
            "en": str(first_value(name_en, name_ar, default="")).strip(),
        }

    if description_en is not None or description_ar is not None:
        payload["description"] = {
            "ar": str(first_value(description_ar, description_en, default="")),
            "en": str(first_value(description_en, description_ar, default="")),
        }

    if price not in (None, ""):
        parsed_price = to_float(price, None)
        if parsed_price is None or parsed_price < 0:
            raise HTTPException(status_code=400, detail="Product price must be 0 or greater")
        payload["price"] = parsed_price

    if stock not in (None, ""):
        parsed_stock = to_int(stock, None)
        if parsed_stock is None or parsed_stock < 0:
            raise HTTPException(status_code=400, detail="Product stock must be 0 or greater")
        payload["quantity"] = parsed_stock
        payload["is_infinite"] = False

    if not payload:
        raise HTTPException(status_code=400, detail="No product changes provided")

    return payload


def coupon_payload_for_zid(body):
    name = first_value(body.get("name"), body.get("coupon_name"))
    code = first_value(body.get("code"), body.get("coupon_code"))
    discount_type = first_value(body.get("discount_type"), default="p")
    discount = first_value(body.get("discount"), body.get("amount"))
    total = first_value(body.get("total"), body.get("minimum_total"), default=0)
    date_start = first_value(body.get("date_start"), body.get("start_date"))
    date_end = first_value(body.get("date_end"), body.get("end_date"))

    if not str(name or "").strip():
        raise HTTPException(status_code=400, detail="Coupon name is required")
    if not str(code or "").strip():
        raise HTTPException(status_code=400, detail="Coupon code is required")
    if discount_type not in ("p", "f", "free_shipping"):
        raise HTTPException(status_code=400, detail="Discount type must be p, f, or free_shipping")
    if discount_type != "free_shipping" and (to_float(discount, None) is None or to_float(discount) <= 0):
        raise HTTPException(status_code=400, detail="Discount must be greater than 0")

    status = body.get("status")
    if status is None:
        status = body.get("enabled", True)

    payload = {
        "name": str(name).strip(),
        "code": str(code).strip(),
        "discount_type": discount_type,
        "discount": 0 if discount_type == "free_shipping" else to_float(discount),
        "free_shipping": "1" if bool(body.get("free_shipping")) or discount_type == "free_shipping" else "0",
        "free_cod": "1" if bool(body.get("free_cod")) else "0",
        "total": to_float(total, 0),
        "date_start": str(date_start or ""),
        "date_end": str(date_end or ""),
        "uses_total": to_int(first_value(body.get("uses_total"), default=0)),
        "uses_customer": to_int(first_value(body.get("uses_customer"), default=0)),
        "status": "1" if bool(status) else "0",
        "apply_to": first_value(body.get("apply_to"), default="all"),
        "applying_method": first_value(body.get("applying_method"), default="CODE"),
        "max_total": first_value(body.get("max_total"), body.get("maximum_total"), default=""),
        "max_weight": first_value(body.get("max_weight"), default=""),
        "maximum_discount_value": first_value(body.get("maximum_discount_value"), default=""),
        "is_mazeed_active": first_value(body.get("is_mazeed_active"), default=""),
        "is_pos_active": "1" if bool(body.get("is_pos_active")) else "",
        "is_shown_in_pos": "1" if bool(body.get("is_shown_in_pos")) else "",
        "is_mobile_app_active": "1" if bool(body.get("is_mobile_app_active")) else "",
        "conditions": first_value(body.get("conditions"), default=""),
        "conditions_criteria": first_value(body.get("conditions_criteria"), default="all"),
    }

    return payload


@app.get("/")
def read_root():
    return {
        "status": "online",
        "oauth_configured": bool(ZID_CLIENT_ID),
        "token_available": bool(token_store.get("access_token")),
        "data_source": zid_status(),
        "message": "Zid Automation API is running",
    }


@app.get("/api/source/status")
def source_status():
    return {
        "status": "success",
        "data": zid_status(),
        "warning": None,
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

    return {
        "status": "success",
        "message": f"Order {order['order_id']} received. Dashboard data is read from Zid API.",
        "order": {
            "order_id": order["order_id"],
            "customer_name": order["customer_name"],
            "total": order["total"],
            "status": order["status"],
            "status_code": order.get("status_code"),
            "items_count": len(order["items"]),
        },
        "alerts_changed": [],
    }


@app.get("/api/orders")
async def get_orders():
    orders = await fetch_zid_orders(limit=100, payload_type="simple")
    return [
        {
            "order_id": order.get("order_id"),
            "customer_name": order.get("customer_name", "Unknown"),
            "total": order.get("total", 0.0),
            "status": order.get("status", "New"),
            "status_code": order.get("status_code"),
            "status_name": order.get("status_name", order.get("status", "New")),
            "display_status": order.get("display_status", {}),
            "payment_status": order.get("payment_status"),
            "items_count": len(order.get("items", [])),
            "created_at": order.get("created_at"),
        }
        for order in orders
    ]


@app.get("/api/alerts")
async def get_alerts():
    alerts = await build_low_stock_alerts()
    return {
        "status": "success",
        "alerts": alerts,
        "threshold": LOW_STOCK_THRESHOLD,
    }


@app.get("/api/products")
async def get_products():
    products = await fetch_zid_products(limit=100)
    return {
        "status": "success",
        "products": products,
    }


@app.get("/api/coupons")
async def get_coupons():
    coupons = await fetch_zid_coupons(limit=100)
    return {
        "status": "success",
        "coupons": coupons,
    }


@app.post("/api/alerts/recalculate")
async def recalculate_alerts():
    alerts = await build_low_stock_alerts()

    return {
        "status": "success",
        "alerts_changed": alerts,
        "alerts": alerts,
    }


@app.get("/api/zid/orders")
async def get_zid_orders():
    return await zid_request(
        "/managers/store/orders/",
        params={"store_id": ZID_STORE_ID, "payload_type": "default"},
    )


@app.get("/api/zid/products")
async def get_zid_products():
    return await zid_request("/products/", params={"extended": "true"})


@app.get("/api/zid/coupons")
async def get_zid_coupons():
    return await zid_request("/managers/store/coupons")


@app.post("/api/products/ai-create")
async def ai_create_product(request: Request):
    body = await request.json()
    image_url = body.get("image_url")
    tone = body.get("tone", "professional")
    product_details = body.get("product_details") or ""

    if not image_url:
        raise HTTPException(status_code=400, detail="image_url is required")

    draft = await generate_ai_product_draft(image_url, tone, product_details)

    return {
        "status": "success",
        "message": "Product draft generated",
        "data": draft,
    }


@app.post("/api/products/publish")
async def publish_product(request: Request):
    draft = await request.json()
    validate_publish_draft(draft)

    if not zid_ready():
        raise HTTPException(
            status_code=400,
            detail="Missing Zid ACCESS_TOKEN/ZID_ACCESS_TOKEN or ZID_STORE_ID/STORE_ID",
        )

    payload = product_payload_for_zid(draft)
    product_response = await zid_request(
        "/products/",
        method="POST",
        json_body=payload,
    )
    product_id = product_id_from_response(product_response)
    image_result = await upload_product_image(
        product_id,
        draft.get("image_url"),
        first_value(draft.get("trendy_name"), draft.get("name_en"), draft.get("name")),
    )

    verified_product = None
    if product_id:
        try:
            verified_product = await zid_request(f"/products/{product_id}/")
        except HTTPException:
            verified_product = None

    return {
        "status": "success",
        "message": "Product published to Zid",
        "zid_payload": payload,
        "zid_response": product_response,
        "product_id": product_id,
        "image_upload": image_result,
        "store_product": verified_product,
    }


@app.post("/api/products/{product_id}/stock/add")
async def add_product_stock(product_id: str, request: Request):
    body = await request.json()
    amount = to_int(body.get("amount"), 0)

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Stock amount must be greater than 0")
    if not zid_ready():
        raise HTTPException(
            status_code=400,
            detail="Missing Zid ACCESS_TOKEN/ZID_ACCESS_TOKEN or ZID_STORE_ID/STORE_ID",
        )

    product_response = await zid_request(f"/products/{product_id}/")
    current_stock = extract_stock_from_product(product_response)
    if current_stock is None:
        current_stock = 0

    new_stock = to_int(current_stock, 0) + amount
    update_response = await update_zid_product_stock(product_id, new_stock)

    return {
        "status": "success",
        "message": f"Stock increased by {amount}.",
        "product_id": product_id,
        "previous_stock": current_stock,
        "added_stock": amount,
        "new_stock": new_stock,
        "zid_response": update_response,
    }


@app.delete("/api/products/{product_id}")
async def delete_product(product_id: str):
    if not zid_ready():
        raise HTTPException(
            status_code=400,
            detail="Missing Zid ACCESS_TOKEN/ZID_ACCESS_TOKEN or ZID_STORE_ID/STORE_ID",
        )

    await zid_request(
        f"/products/{product_id}/",
        method="DELETE",
    )

    return {
        "status": "success",
        "message": "Product deleted from Zid",
        "product_id": product_id,
    }


@app.patch("/api/products/{product_id}")
async def update_product(product_id: str, request: Request):
    if not zid_ready():
        raise HTTPException(
            status_code=400,
            detail="Missing Zid ACCESS_TOKEN/ZID_ACCESS_TOKEN or ZID_STORE_ID/STORE_ID",
        )

    body = await request.json()
    payload = product_update_payload_for_zid(body)
    update_response = await zid_request(
        f"/products/{product_id}/",
        method="PATCH",
        json_body=payload,
    )

    try:
        verified_product = await zid_request(f"/products/{product_id}/")
    except HTTPException:
        verified_product = update_response

    return {
        "status": "success",
        "message": "Product updated in Zid",
        "product_id": product_id,
        "zid_payload": payload,
        "zid_response": update_response,
        "product": normalize_product(verified_product),
    }


@app.post("/api/coupons")
async def create_coupon(request: Request):
    body = await request.json()
    payload = coupon_payload_for_zid(body)
    response = await zid_multipart_request(
        "/managers/store/coupons/add",
        form_body=payload,
    )

    return {
        "status": "success",
        "message": "Coupon created in Zid",
        "zid_payload": payload,
        "zid_response": response,
        "coupon": normalize_coupon(response.get("coupon") if isinstance(response, dict) else {}),
    }


@app.patch("/api/coupons/{coupon_id}")
async def update_coupon(coupon_id: str, request: Request):
    body = await request.json()
    payload = coupon_payload_for_zid(body)
    response = await zid_multipart_request(
        f"/managers/store/coupons/{coupon_id}/update",
        form_body=payload,
    )

    return {
        "status": "success",
        "message": "Coupon updated in Zid",
        "coupon_id": coupon_id,
        "zid_payload": payload,
        "zid_response": response,
        "coupon": normalize_coupon(response.get("coupon") if isinstance(response, dict) else {}),
    }


@app.delete("/api/coupons/{coupon_id}")
async def delete_coupon(coupon_id: str):
    response = await zid_request(
        f"/managers/store/coupons/{coupon_id}",
        method="DELETE",
    )

    return {
        "status": "success",
        "message": "Coupon deleted from Zid",
        "coupon_id": coupon_id,
        "zid_response": response,
    }


@app.post("/api/products/create")
async def create_product(request: Request):
    return await publish_product(request)


# To run: .\venv\Scripts\python -m uvicorn main:app --reload
