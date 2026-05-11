# Merchant Automation Dashboard - Sandbox

A full-stack application for automating merchant orders from Zid e-commerce platform.

## 📁 Project Structure

```
├── frontend/          # React + Vite application
│   ├── src/
│   │   ├── App.jsx    # Main component
│   │   └── main.jsx   # Entry point
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── backend/           # FastAPI backend
│   ├── main.py        # FastAPI application
│   └── requirements.txt
└── README.md
```

## 🚀 Getting Started

### Prerequisites
- Node.js 16+ (for frontend)
- Python 3.8+ (for backend)

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The frontend will be available at `http://localhost:5173`

### Backend Setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate  # On Windows
pip install -r requirements.txt
uvicorn main:app --reload
```

The backend API will be available at `http://localhost:8000`

## 📌 API Endpoints

### POST /api/webhook/order
Receives order webhooks from Zid platform
- Payload structure: Must include order data with id, customer name, and total

### GET /api/orders
Returns all orders stored in the database
- Response: Array of order objects

## 🛠️ Features

- ✅ Real-time order automation dashboard
- ✅ WebSocket-ready polling (5-second intervals)
- ✅ SQLite database for order storage
- ✅ CORS enabled for cross-origin requests
- ✅ RTL (Right-to-Left) support for Arabic text
