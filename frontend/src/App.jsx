import { useEffect, useState } from 'react'
import { ThemeProvider, CssBaseline, Container, Box, Typography } from '@mui/material'
import { themeParcel } from '@zidsa/zidmui/theme/theme'
import { AppCard } from '@zidsa/zidmui/components/app-card'
import { AppButton } from '@zidsa/zidmui/components/app-button'

// Zid MUI uses standard HTML tables with 'zid-table' class for the platform look
import '@zidsa/zidmui/styles/components/table.css' 

function App() {
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)

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
    const interval = setInterval(fetchOrders, 5000)
    return () => clearInterval(interval)
  }, [])

  return (
    <ThemeProvider theme={themeParcel}>
      <CssBaseline />
      <Box sx={{ minHeight: '100vh', bgcolor: '#f4f6f8', py: 4, direction: 'rtl' }}>
        <Container maxWidth="lg">
          <Box sx={{ mb: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Box>
              <Typography variant="h4" fontWeight="700" color="primary" gutterBottom>
                ⚙️ لوحة أتمتة التاجر (Sandbox)
              </Typography>
              <Typography variant="body1" color="textSecondary">
                هنا تظهر الطلبات المؤتمتة القادمة من زد فوراً
              </Typography>
            </Box>
            <AppButton variant="contained" color="primary" onClick={fetchOrders}>
              تحديث البيانات
            </AppButton>
          </Box>

          <AppCard>
            {loading ? (
              <Box sx={{ p: 4, textAlign: 'center' }}>
                <Typography>جاري التحميل...</Typography>
              </Box>
            ) : (
              <Box sx={{ overflowX: 'auto' }}>
                <table className="zid-table">
                  <thead>
                    <tr>
                      <th>رقم الطلب</th>
                      <th>اسم العميل</th>
                      <th>الإجمالي</th>
                      <th>حالة الأتمتة</th>
                    </tr>
                  </thead>
                  <tbody>
                    {orders.length === 0 ? (
                      <tr>
                        <td colSpan="4" style={{ textAlign: 'center', padding: '2rem' }}>
                          لا توجد طلبات حتى الآن. أرسل Webhook للتجربة!
                        </td>
                      </tr>
                    ) : (
                      orders.map((order) => (
                        <tr key={order.order_id}>
                          <td>#{order.order_id}</td>
                          <td>{order.customer_name}</td>
                          <td>{order.total} ر.س</td>
                          <td>
                            <Box sx={{ color: 'success.main', display: 'flex', alignItems: 'center', gap: 1 }}>
                              ✅ تمت الأتمتة
                            </Box>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </Box>
            )}
          </AppCard>
        </Container>
      </Box>
    </ThemeProvider>
  )
}

export default App
