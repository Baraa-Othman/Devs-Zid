import { useEffect, useState } from 'react'
import { 
  Box, 
  Typography, 
  CssBaseline, 
  Container, 
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  CircularProgress,
  ThemeProvider 
} from '@mui/material'
import { themeParcel } from '@zidsa/zidmui/theme/theme'
import { AppCard } from '@zidsa/zidmui/components/app-card'
import { AppButton } from '@zidsa/zidmui/components/app-button'

// Zid MUI uses standard HTML tables with 'zid-table' class for the platform look
import '@zidsa/zidmui/styles/components/table.css' 

function App() {
  const [orders, setOrders] = useState([])
  const [alerts, setAlerts] = useState([])
  const [loading, setLoading] = useState(true)
  
  // AI Modal State
  const [isAiModalOpen, setIsAiModalOpen] = useState(false)
  const [aiImageUrl, setAiImageUrl] = useState('')
  const [aiTone, setAiTone] = useState('مرح')
  const [isGenerating, setIsGenerating] = useState(false)
  const [aiResult, setAiResult] = useState(null)

  const fetchData = async () => {
    try {
      const [ordersRes, alertsRes] = await Promise.all([
        fetch('http://localhost:8000/api/orders'),
        fetch('http://localhost:8000/api/alerts')
      ]);
      const ordersData = await ordersRes.json()
      const alertsData = await alertsRes.json()
      setOrders(ordersData)
      setAlerts(alertsData)
    } catch (error) {
      console.error("Error fetching data:", error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 5000)
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
            <Box sx={{ display: 'flex', gap: 2 }}>
              <AppButton variant="contained" color="primary" onClick={fetchData}>
                تحديث البيانات
              </AppButton>
              <AppButton variant="contained" color="secondary" onClick={() => setIsAiModalOpen(true)}>
                ✨ إضافة منتج بالذكاء الاصطناعي
              </AppButton>
            </Box>
          </Box>

          {/* AI PRODUCT MODAL */}
          <Dialog open={isAiModalOpen} onClose={() => setIsAiModalOpen(false)} maxWidth="sm" fullWidth>
            <DialogTitle>إضافة منتج جديد (AI)</DialogTitle>
            <DialogContent>
              <Typography variant="body2" sx={{ mb: 2 }}>
                ضع رابط صورة المنتج، وسيقوم الذكاء الاصطناعي بكتابة الوصف واقتراح السعر والـ SEO تلقائياً!
              </Typography>
              <TextField 
                fullWidth 
                label="رابط الصورة" 
                variant="outlined" 
                margin="normal"
                value={aiImageUrl}
                onChange={e => setAiImageUrl(e.target.value)}
              />
              <TextField 
                fullWidth 
                label="نبرة الوصف (مثال: مرح، رسمي، فاخر)" 
                variant="outlined" 
                margin="normal"
                value={aiTone}
                onChange={e => setAiTone(e.target.value)}
              />
              
              {isGenerating && (
                <Box sx={{ display: 'flex', justifyContent: 'center', mt: 3, gap: 2, alignItems: 'center' }}>
                  <CircularProgress size={24} />
                  <Typography>جاري التحليل والكتابة...</Typography>
                </Box>
              )}

              {aiResult && !isGenerating && (
                <Box sx={{ mt: 3, p: 2, bgcolor: '#f5f5f5', borderRadius: 1 }}>
                  <Typography variant="subtitle2" color="success.main" gutterBottom>تم توليد المنتج بنجاح!</Typography>
                  <Typography><strong>الاسم:</strong> {aiResult.name}</Typography>
                  <Typography><strong>السعر:</strong> {aiResult.price} ر.س</Typography>
                  <Typography><strong>الوصف:</strong> {aiResult.description}</Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                    الـ SEO: {aiResult.seo_title}
                  </Typography>
                </Box>
              )}
            </DialogContent>
            <DialogActions>
              <AppButton onClick={() => setIsAiModalOpen(false)}>إغلاق</AppButton>
              <AppButton 
                variant="contained" 
                color="primary"
                disabled={isGenerating || !aiImageUrl}
                onClick={async () => {
                  setIsGenerating(true)
                  setAiResult(null)
                  try {
                    const res = await fetch('http://localhost:8000/api/products/ai-create', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ image_url: aiImageUrl, tone: aiTone })
                    });
                    const data = await res.json();
                    if (data.status === 'success') {
                      setAiResult(data.data)
                    } else {
                      alert('خطأ في التوليد: ' + data.message)
                    }
                  } catch (e) {
                    console.error(e)
                  } finally {
                    setIsGenerating(false)
                  }
                }}
              >
                توليد واعتماد
              </AppButton>
            </DialogActions>
          </Dialog>

          {/* URGENT ALERTS SECTION */}
          {alerts.length > 0 && (
            <Box sx={{ mb: 4 }}>
              <Typography variant="h6" color="error" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                ⚠️ تنبيهات هامة! (نقص مخزون)
              </Typography>
              {alerts.map(alert => (
                <AppCard key={alert.id} sx={{ mb: 2, borderLeft: '4px solid #d32f2f' }}>
                  <Box sx={{ p: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Box>
                      <Typography variant="subtitle1" fontWeight="bold">
                        المنتج: {alert.product_name} (رقم: {alert.product_id})
                      </Typography>
                      <Typography variant="body2" color="error">
                        الكمية المتبقية: {alert.stock} فقط!
                      </Typography>
                    </Box>
                    <AppButton variant="outlined" color="error" size="small">
                      طلب كمية إضافية
                    </AppButton>
                  </Box>
                </AppCard>
              ))}
            </Box>
          )}

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
