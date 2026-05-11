from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
import sqlite3
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Zid Automation API")

# ─── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Zid OAuth2.0 Config ──────────────────────────────────────────────────────
ZID_CLIENT_ID     = os.getenv("ZID_CLIENT_ID")
ZID_CLIENT_SECRET = os.getenv("ZID_CLIENT_SECRET")
ZID_REDIRECT_URI  = os.getenv("ZID_REDIRECT_URI")
ZID_CALLBACK_URI  = os.getenv("ZID_CALLBACK_URI")
ACCESS_TOKEN      = os.getenv("ACCESS_TOKEN")   # pre-issued manager token
ZID_STORE_ID      = os.getenv("ZID_STORE_ID")

ZID_AUTH_URL      = "https://oauth.zid.sa/oauth/authorize"
ZID_TOKEN_URL     = "https://oauth.zid.sa/oauth/token"
ZID_API_BASE      = "https://api.zid.sa/v1"

# In-memory token store (replace with DB for production)
token_store: dict = {
    "access_token": ACCESS_TOKEN,
    "refresh_token": None,
    "authorization": None,   # Zid's "Authorization" field from token response
}

# ─── Database ─────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect("sandbox.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id      TEXT PRIMARY KEY,
            customer_name TEXT,
            total         REAL,
            status        TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()


# ─── Helper: build Zid API headers ────────────────────────────────────────────
def zid_headers() -> dict:
    """
    Zid requires TWO auth headers on every API call:
      - X-MANAGER-TOKEN : the access_token (manager token)
      - Authorization   : Bearer <Authorization field from OAuth response>
    When using a pre-issued ACCESS_TOKEN (sandbox), we use it for both.
    """
    manager_token  = token_store.get("access_token") or ACCESS_TOKEN
    auth_bearer    = token_store.get("authorization") or ACCESS_TOKEN
    return {
        "X-MANAGER-TOKEN": manager_token,
        "Authorization": f"Bearer {auth_bearer}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ─── Health Check ─────────────────────────────────────────────────────────────
@app.get("/")
def read_root():
    return {
        "status": "online",
        "oauth_configured": bool(ZID_CLIENT_ID),
        "token_available": bool(token_store.get("access_token")),
        "message": "Zid Automation API is running",
    }


# ─── OAuth2.0 Step 1: Redirect merchant to Zid login ─────────────────────────
@app.get("/auth/login")
def oauth_login():
    """
    Redirect the merchant browser to Zid's OAuth authorization page.
    Zid will ask the merchant to approve access, then redirect back to
    ZID_REDIRECT_URI with ?code=...
    """
    auth_url = (
        f"{ZID_AUTH_URL}"
        f"?client_id={ZID_CLIENT_ID}"
        f"&redirect_uri={ZID_REDIRECT_URI}"
        f"&response_type=code"
    )
    return RedirectResponse(url=auth_url)


# ─── OAuth2.0 Step 2: Handle redirect & exchange code for token ───────────────
@app.get("/auth/redirect")
async def oauth_redirect(code: str = None, error: str = None):
    """
    Zid redirects here after merchant approves.
    Exchange the one-time `code` for access_token + refresh_token.
    """
    if error or not code:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error or 'no code returned'}")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            ZID_TOKEN_URL,
            data={
                "grant_type":    "authorization_code",
                "client_id":     ZID_CLIENT_ID,
                "client_secret": ZID_CLIENT_SECRET,
                "redirect_uri":  ZID_REDIRECT_URI,
                "code":          code,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Token exchange failed: {response.text}"
        )

    data = response.json()

    # Zid returns both `access_token` and an `Authorization` field
    token_store["access_token"]  = data.get("access_token")
    token_store["refresh_token"] = data.get("refresh_token")
    token_store["authorization"] = data.get("Authorization")  # ← Zid-specific

    return JSONResponse({
        "status": "authenticated",
        "access_token": token_store["access_token"],
        "message": "OAuth2.0 flow completed successfully",
    })


# ─── OAuth2.0 Step 3 (optional): Handle callback URI ─────────────────────────
@app.get("/auth/callback")
async def oauth_callback(code: str = None, error: str = None):
    """Alias callback endpoint — delegates to redirect handler."""
    return await oauth_redirect(code=code, error=error)


# ─── OAuth2.0 Token Refresh ───────────────────────────────────────────────────
@app.post("/auth/refresh")
async def refresh_token():
    """Use the stored refresh_token to get a new access_token."""
    rt = token_store.get("refresh_token")
    if not rt:
        raise HTTPException(status_code=400, detail="No refresh token stored. Re-authenticate.")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            ZID_TOKEN_URL,
            data={
                "grant_type":    "refresh_token",
                "client_id":     ZID_CLIENT_ID,
                "client_secret": ZID_CLIENT_SECRET,
                "refresh_token": rt,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Refresh failed: {response.text}")

    data = response.json()
    token_store["access_token"]  = data.get("access_token")
    token_store["refresh_token"] = data.get("refresh_token", rt)
    token_store["authorization"] = data.get("Authorization")

    return {"status": "token refreshed", "access_token": token_store["access_token"]}


# ─── Auth Status ──────────────────────────────────────────────────────────────
@app.get("/auth/status")
def auth_status():
    return {
        "authenticated": bool(token_store.get("access_token")),
        "has_refresh_token": bool(token_store.get("refresh_token")),
    }


# ─── Webhook: receive order events from Zid ───────────────────────────────────
@app.post("/api/webhook/order")
async def receive_order_webhook(request: Request):
    payload = await request.json()

    order_id      = payload.get("data", {}).get("id", "Unknown")
    customer_name = payload.get("data", {}).get("customer", {}).get("name", "Unknown")
    total         = payload.get("data", {}).get("totals", {}).get("total", 0.0)

    conn = sqlite3.connect("sandbox.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO orders (order_id, customer_name, total, status) VALUES (?, ?, ?, ?)",
        (order_id, customer_name, total, "New"),
    )
    conn.commit()
    conn.close()

    return {"status": "success", "message": f"Order {order_id} received."}


# ─── Orders: list stored orders ───────────────────────────────────────────────
@app.get("/api/orders")
def get_orders():
    conn = sqlite3.connect("sandbox.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders")
    rows = cursor.fetchall()
    conn.close()
    return [{"order_id": r[0], "customer_name": r[1], "total": r[2], "status": r[3]} for r in rows]


# ─── Proxy: fetch live orders from Zid API ────────────────────────────────────
@app.get("/api/zid/orders")
async def get_zid_orders():
    """Fetch orders directly from the Zid API using authenticated headers."""
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
        raise HTTPException(status_code=429, detail="Zid API: Rate limit hit (60 req/min). Try again shortly.")
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    return response.json()

# To run: .\venv\Scripts\python -m uvicorn main:app --reload
