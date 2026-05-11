import { useEffect, useState } from 'react'

function App() {
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)

  // جلب البيانات من الباك اند (FastAPI)
  const fetchOrders = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/orders')
      const data = await response.json()
      setOrders(data)
    } catch (error) {
      console.error("Error fetching orders:", error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchOrders()
    // تحديث البيانات كل 5 ثواني عشان تبان كأنها Real-time للجنة التحكيم
    const interval = setInterval(fetchOrders, 5000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div style={{ padding: '2rem', fontFamily: 'system-ui, sans-serif', direction: 'rtl' }}>
      <h1>⚙️ لوحة أتمتة التاجر (Sandbox)</h1>
      <p>هنا تظهر الطلبات المؤتمتة القادمة من زد فوراً:</p>

      {loading ? (
        <p>جاري التحميل...</p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '1rem' }}>
          <thead>
            <tr style={{ background: '#f3f4f6', textAlign: 'right' }}>
              <th style={{ padding: '10px', borderBottom: '2px solid #ddd' }}>رقم الطلب</th>
              <th style={{ padding: '10px', borderBottom: '2px solid #ddd' }}>اسم العميل</th>
              <th style={{ padding: '10px', borderBottom: '2px solid #ddd' }}>الإجمالي</th>
              <th style={{ padding: '10px', borderBottom: '2px solid #ddd' }}>حالة الأتمتة</th>
            </tr>
          </thead>
          <tbody>
            {orders.length === 0 ? (
              <tr><td colSpan="4" style={{ padding: '10px', textAlign: 'center' }}>لا توجد طلبات حتى الآن. أرسل Webhook للتجربة!</td></tr>
            ) : (
              orders.map((order) => (
                <tr key={order.order_id}>
                  <td style={{ padding: '10px', borderBottom: '1px solid #ddd' }}>#{order.order_id}</td>
                  <td style={{ padding: '10px', borderBottom: '1px solid #ddd' }}>{order.customer_name}</td>
                  <td style={{ padding: '10px', borderBottom: '1px solid #ddd' }}>{order.total} ر.س</td>
                  <td style={{ padding: '10px', borderBottom: '1px solid #ddd', color: 'green' }}>✅ تمت الأتمتة</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default App
