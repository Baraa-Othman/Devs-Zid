# Merchant Automation Dashboard - Sandbox

A full-stack dashboard for reading live merchant data from the Zid e-commerce API.

## Project Structure

```text
frontend/          React + Vite application
backend/           FastAPI backend
README.md
```

## Getting Started

### Prerequisites

- Node.js 16+ for the frontend
- Python 3.8+ for the backend
- Zid store credentials

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The frontend will be available at `http://localhost:5173`.

### Backend Setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

The backend API will be available at `http://localhost:8000`.

### Zid API Setup

Set these values in `backend/.env`:

```bash
STORE_ID=your_store_id_here
ACCESS_TOKEN=your_store_access_token_here
```

Optional OAuth values:

```bash
ZID_CLIENT_ID=your_client_id_here
ZID_CLIENT_SECRET=your_client_secret_here
ZID_REDIRECT_URI=http://localhost:8000/auth/redirect
```

## API Endpoints

### GET /api/orders

Returns recent orders directly from Zid.

### GET /api/alerts

Returns low-stock alerts calculated from live Zid products.

### GET /api/zid/orders

Returns the raw Zid orders response.

### GET /api/zid/products

Returns the raw Zid products response.

### POST /api/products/ai-create

Generates an editable product draft from an image URL.

### POST /api/products/publish

Publishes the reviewed product draft to Zid.

## Features

- Live recent orders from Zid API
- Live low-stock alerts from Zid products
- AI product draft generation
- Product publishing to Zid
- CORS enabled for local frontend development
- RTL-ready UI components
