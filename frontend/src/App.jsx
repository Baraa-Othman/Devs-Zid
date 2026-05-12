import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  CssBaseline,
  Divider,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  ThemeProvider,
  Typography,
} from '@mui/material'
import { themeParcel } from '@zidsa/zidmui/theme/theme'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const tones = [
  { value: 'professional', label: 'Professional' },
  { value: 'friendly', label: 'Friendly' },
  { value: 'luxury', label: 'Luxury' },
  { value: 'playful', label: 'Playful' },
  { value: 'energetic', label: 'Energetic' },
]

const MAX_IMAGE_BYTES = 20 * 1024 * 1024
const IMAGE_ACCEPT = 'image/jpeg,image/png,image/webp,image/gif,image/jpg'

const draftPlaceholders = {
  trendy_name: 'Trendy product name',
  trendy_name_arabic: 'اسم منتج جذاب',
  description: 'A short marketing description will appear here.',
  description_arabic: 'سيظهر الوصف التسويقي العربي هنا.',
  marketing_audience: 'Primary audience placeholder',
  marketing_partners: ['Partner placeholder 1', 'Partner placeholder 2'],
  recommended_price: '0',
  marketing_plan: 'Marketing plan placeholder',
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(new Error('Could not read the selected image.'))
    reader.readAsDataURL(file)
  })
}

function normalizeDraft(payload) {
  const source = payload?.data || payload?.product || payload || {}
  const trendName = source.trendy_name || source.name_en || source.name || draftPlaceholders.trendy_name
  const trendNameArabic = source.trendy_name_arabic || source.name_ar || source.name || draftPlaceholders.trendy_name_arabic
  const description = source.description || source.description_en || draftPlaceholders.description
  const descriptionArabic = source.description_arabic || source.description_ar || draftPlaceholders.description_arabic
  const marketingPartners = Array.isArray(source.marketing_partners)
    ? source.marketing_partners
    : Array.isArray(source.partners)
      ? source.partners
      : Array.isArray(source.tags)
        ? source.tags
        : draftPlaceholders.marketing_partners
  const recommendedPrice = source.recommended_price || source.price || draftPlaceholders.recommended_price
  const marketingPlan = source.marketing_plan || source.bullets || draftPlaceholders.marketing_plan
  const marketingAudience = source.marketing_audience || source.audience || draftPlaceholders.marketing_audience

  return {
    trendy_name: trendName,
    trendy_name_arabic: trendNameArabic,
    description,
    description_arabic: descriptionArabic,
    marketing_audience: marketingAudience,
    marketing_partners: marketingPartners,
    recommended_price: recommendedPrice,
    marketing_plan: marketingPlan,
    name_ar: trendNameArabic,
    name_en: trendName,
    description_ar: descriptionArabic,
    description_en: description,
    seo_title_ar: source.seo_title_ar || trendNameArabic,
    seo_title_en: source.seo_title_en || trendName,
    price: recommendedPrice,
    tags: marketingPartners.join(', '),
    bullets: Array.isArray(marketingPlan) ? marketingPlan.join('\n') : String(marketingPlan || ''),
  }
}

async function fetchJson(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options)
  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json') ? await response.json() : null

  if (!response.ok) {
    throw new Error(payload?.detail || payload?.message || `Request failed: ${response.status}`)
  }

  return payload
}

function asArray(payload, key) {
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload?.[key])) return payload[key]
  if (Array.isArray(payload?.data)) return payload.data
  return []
}

function field(item, keys, fallback = '-') {
  for (const key of keys) {
    const value = item?.[key]
    if (value !== undefined && value !== null && value !== '') return value
  }
  return fallback
}

function Stat({ label, value, tone = 'default' }) {
  const colors = {
    default: ['#f8fafc', '#334155'],
    danger: ['#fff1f2', '#be123c'],
    good: ['#ecfdf3', '#027a48'],
    blue: ['#eff6ff', '#1d4ed8'],
  }
  const [bg, color] = colors[tone] || colors.default

  return (
    <Paper elevation={0} sx={{ p: 2, border: '1px solid #e5e7eb', borderRadius: 2, bgcolor: bg }}>
      <Typography sx={{ color, fontSize: 13, fontWeight: 700 }}>{label}</Typography>
      <Typography variant="h4" sx={{ mt: 0.5, color, fontWeight: 900, lineHeight: 1 }}>
        {value}
      </Typography>
    </Paper>
  )
}

function App() {
  const [orders, setOrders] = useState([])
  const [alerts, setAlerts] = useState([])
  const [storage, setStorage] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [loadError, setLoadError] = useState('')

  const [selectedImage, setSelectedImage] = useState(null)
  const [selectedImageName, setSelectedImageName] = useState('')
  const [selectedImagePreview, setSelectedImagePreview] = useState('')
  const [imageInputError, setImageInputError] = useState('')
  const [tone, setTone] = useState('professional')
  const [productDetails, setProductDetails] = useState('')
  const [generating, setGenerating] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [generatorError, setGeneratorError] = useState('')
  const [publishMessage, setPublishMessage] = useState('')
  const [generatedRaw, setGeneratedRaw] = useState(null)
  const [draftVisible, setDraftVisible] = useState(false)
  const [draft, setDraft] = useState({ ...draftPlaceholders })

  const totalSold = useMemo(
    () => alerts.reduce((sum, item) => sum + Number(field(item, ['sold_quantity'], 0)), 0),
    [alerts],
  )

  async function loadDashboard({ quiet = false } = {}) {
    setLoadError('')
    quiet ? setRefreshing(true) : setLoading(true)

    try {
      const [ordersResult, alertsResult, storageResult] = await Promise.allSettled([
        fetchJson('/api/orders'),
        fetchJson('/api/alerts'),
        fetchJson('/api/storage/status'),
      ])

      if (ordersResult.status === 'fulfilled') {
        setOrders(asArray(ordersResult.value, 'orders'))
      }
      if (alertsResult.status === 'fulfilled') {
        setAlerts(asArray(alertsResult.value, 'alerts'))
      }
      if (storageResult.status === 'fulfilled') {
        setStorage(storageResult.value?.data || storageResult.value)
      }

      if (ordersResult.status === 'rejected' && alertsResult.status === 'rejected') {
        setLoadError('Could not load dashboard data. Make sure the FastAPI backend is running on port 8000.')
      }
    } catch (error) {
      setLoadError(error.message || 'Could not load dashboard data.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    loadDashboard()
    const id = window.setInterval(() => loadDashboard({ quiet: true }), 15000)
    return () => window.clearInterval(id)
  }, [])

  async function handleImageSelect(event) {
    const file = event.target.files?.[0]
    setImageInputError('')
    setGeneratorError('')
    setPublishMessage('')
    setGeneratedRaw(null)
    setDraftVisible(false)

    if (!file) {
      setSelectedImage(null)
      setSelectedImageName('')
      setSelectedImagePreview('')
      return
    }

    if (!file.type.startsWith('image/')) {
      setImageInputError('Please choose a JPEG, PNG, WebP, or GIF image.')
      event.target.value = ''
      return
    }

    if (file.size > MAX_IMAGE_BYTES) {
      setImageInputError('Image size must be 20 MB or smaller.')
      event.target.value = ''
      return
    }

    try {
      const preview = await readFileAsDataUrl(file)
      setSelectedImage(file)
      setSelectedImageName(file.name)
      setSelectedImagePreview(preview)
    } catch (error) {
      setSelectedImage(null)
      setSelectedImageName('')
      setSelectedImagePreview('')
      setImageInputError(error.message || 'Could not read the selected image.')
      event.target.value = ''
    }
  }

  async function generateProduct() {
    setGeneratorError('')
    setPublishMessage('')
    setImageInputError('')
    setGeneratedRaw(null)
    setDraftVisible(true)
    setDraft({ ...draftPlaceholders })
    setGenerating(true)

    try {
      const image_url = selectedImagePreview || ''
      const payload = await fetchJson('/api/products/ai-create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_url, tone, product_details: productDetails.trim() || undefined }),
      })
      const normalized = normalizeDraft(payload)
      setGeneratedRaw(payload?.data || payload)
      setDraft(normalized)
    } catch (error) {
      setGeneratorError(error.message || 'Could not generate product draft.')
      setDraft({ ...draftPlaceholders })
    } finally {
      setGenerating(false)
      setDraftVisible(true)
    }
  }

  async function publishProduct() {
    setPublishing(true)
    setGeneratorError('')
    setPublishMessage('')

    try {
      await fetchJson('/api/products/publish', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...generatedRaw,
          ...draft,
          image_url: selectedImagePreview,
          tone,
          name: draft.trendy_name_arabic,
          name_ar: draft.trendy_name_arabic,
          name_en: draft.trendy_name,
          description: draft.description_arabic,
          description_ar: draft.description_arabic,
          description_en: draft.description,
          price: draft.recommended_price,
          suggested_price: draft.recommended_price,
          tags: draft.marketing_partners,
          bullets: Array.isArray(draft.marketing_plan)
            ? draft.marketing_plan
            : String(draft.marketing_plan || '')
                .split('\n')
                .map((item) => item.trim())
                .filter(Boolean),
        }),
      })
      setPublishMessage('Product published to Zid.')
    } catch (error) {
      setGeneratorError(error.message || 'Could not publish product.')
    } finally {
      setPublishing(false)
    }
  }

  function updateDraft(key, value) {
    setDraft((current) => ({ ...current, [key]: value }))
  }

  return (
    <ThemeProvider theme={themeParcel}>
      <CssBaseline />
      <Box sx={{ minHeight: '100vh', bgcolor: '#f6f7f9', color: '#182230' }}>
        <Container maxWidth="xl" sx={{ py: { xs: 2, md: 4 } }}>
          <Stack spacing={3}>
            <Paper elevation={0} sx={{ p: { xs: 2, md: 3 }, border: '1px solid #e5e7eb', borderRadius: 2 }}>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} justifyContent="space-between" alignItems={{ xs: 'stretch', md: 'center' }}>
                <Box>
                  <Typography variant="h4" component="h1" sx={{ fontWeight: 900, lineHeight: 1.15 }}>
                    Zid Merchant Automation
                  </Typography>
                  <Typography color="text.secondary" sx={{ mt: 1, maxWidth: 760 }}>
                    Smart stock alerts from order webhooks, plus AI product descriptions ready to review and publish.
                  </Typography>
                </Box>
                <Stack direction="row" spacing={1.25} flexWrap="wrap" useFlexGap>

                  <Button variant="contained" onClick={() => loadDashboard({ quiet: true })} disabled={refreshing}>
                    {refreshing ? 'Refreshing...' : 'Refresh'}
                  </Button>
                </Stack>
              </Stack>
            </Paper>

            {loadError && <Alert severity="error">{loadError}</Alert>}

            <Grid container spacing={2.5}>
              <Grid item xs={12} md={4}>
                <Stat label="Urgent low-stock items" value={alerts.length} tone={alerts.length ? 'danger' : 'good'} />
              </Grid>
              <Grid item xs={12} md={4}>
                <Stat label="Recent orders stored" value={orders.length} tone="blue" />
              </Grid>
              <Grid item xs={12} md={4}>
                <Stat label="Units sold in alert items" value={totalSold} />
              </Grid>
            </Grid>

            <Grid container spacing={3} alignItems="flex-start">
              <Grid item xs={12} lg={7}>
                <Paper elevation={0} sx={{ border: '1px solid #e5e7eb', borderRadius: 2, overflow: 'hidden' }}>
                  <Box sx={{ p: { xs: 2, md: 3 } }}>
                    <Typography variant="h5" sx={{ fontWeight: 900 }}>
                      Smart Stock Alert System
                    </Typography>
                    <Typography color="text.secondary" sx={{ mt: 0.75 }}>
                      Order webhooks are stored, item sales are counted, and products under the stock threshold are sorted by urgency.
                    </Typography>
                  </Box>
                  <Divider />

                  {loading ? (
                    <Stack sx={{ minHeight: 260 }} alignItems="center" justifyContent="center" spacing={2}>
                      <CircularProgress size={28} />
                      <Typography color="text.secondary">Loading alerts...</Typography>
                    </Stack>
                  ) : alerts.length === 0 ? (
                    <Box sx={{ p: 3 }}>
                      <Alert severity="success">No urgent stock alerts yet.</Alert>
                    </Box>
                  ) : (
                    <Box sx={{ overflowX: 'auto' }}>
                      <Box component="table" sx={{ width: '100%', minWidth: 760, borderCollapse: 'collapse' }}>
                        <Box component="thead" sx={{ bgcolor: '#f8fafc' }}>
                          <Box component="tr">
                            {['Product', 'SKU', 'Stock', 'Sold', 'Velocity', 'Source'].map((heading) => (
                              <Box component="th" key={heading} sx={{ p: 2, textAlign: 'left', fontSize: 13, color: '#475467' }}>
                                {heading}
                              </Box>
                            ))}
                          </Box>
                        </Box>
                        <Box component="tbody">
                          {alerts.map((alert, index) => (
                            <Box component="tr" key={field(alert, ['id', 'product_id', 'sku'], index)} sx={{ borderTop: '1px solid #eef0f3' }}>
                              <Box component="td" sx={{ p: 2 }}>
                                <Typography sx={{ fontWeight: 800, overflowWrap: 'anywhere' }}>
                                  {field(alert, ['product_name', 'name', 'title'])}
                                </Typography>
                                <Typography variant="caption" color="text.secondary">
                                  ID: {field(alert, ['product_id', 'id'])}
                                </Typography>
                              </Box>
                              <Box component="td" sx={{ p: 2, overflowWrap: 'anywhere' }}>{field(alert, ['sku'])}</Box>
                              <Box component="td" sx={{ p: 2 }}>
                                <Chip color="error" size="small" label={`${field(alert, ['current_stock', 'stock'], 0)} left`} sx={{ fontWeight: 800 }} />
                              </Box>
                              <Box component="td" sx={{ p: 2 }}>{field(alert, ['sold_quantity'], 0)}</Box>
                              <Box component="td" sx={{ p: 2 }}>{field(alert, ['sales_velocity'], 0)}/day</Box>
                              <Box component="td" sx={{ p: 2 }}>{field(alert, ['source'])}</Box>
                            </Box>
                          ))}
                        </Box>
                      </Box>
                    </Box>
                  )}
                </Paper>

                <Paper elevation={0} sx={{ mt: 3, p: { xs: 2, md: 3 }, border: '1px solid #e5e7eb', borderRadius: 2 }}>
                  <Typography variant="h6" sx={{ fontWeight: 900, mb: 2 }}>
                    Recent Orders
                  </Typography>
                  {orders.length === 0 ? (
                    <Typography color="text.secondary">No orders stored yet. Send a Zid order webhook to start filling this list.</Typography>
                  ) : (
                    <Stack spacing={1.25}>
                      {orders.slice(0, 5).map((order, index) => (
                        <Box key={field(order, ['order_id', 'id'], index)} sx={{ p: 1.5, bgcolor: '#f8fafc', borderRadius: 1.5, display: 'flex', justifyContent: 'space-between', gap: 2 }}>
                          <Box sx={{ minWidth: 0 }}>
                            <Typography sx={{ fontWeight: 800, overflowWrap: 'anywhere' }}>Order #{field(order, ['order_id', 'id'])}</Typography>
                            <Typography variant="body2" color="text.secondary">{field(order, ['customer_name'], 'Unknown customer')}</Typography>
                          </Box>
                          <Typography sx={{ fontWeight: 900, whiteSpace: 'nowrap' }}>{field(order, ['total'], 0)} SAR</Typography>
                        </Box>
                      ))}
                    </Stack>
                  )}
                </Paper>
              </Grid>

              <Grid item xs={12} lg={5}>
                <Paper elevation={0} sx={{ border: '1px solid #e5e7eb', borderRadius: 2, overflow: 'hidden' }}>
                  <Box sx={{ p: { xs: 2, md: 3 } }}>
                    <Typography variant="h5" sx={{ fontWeight: 900 }}>
                      AI Product Marketing & Description
                    </Typography>
                    <Typography color="text.secondary" sx={{ mt: 0.75, mb: 2 }}>
                      Upload a product photo, pick a tone, then generate a draft with marketing copy you can edit before publishing.
                    </Typography>

                    <Stack spacing={2}>
                      <Button variant="outlined" component="label" fullWidth sx={{ justifyContent: 'space-between' }}>
                        {selectedImageName ? 'Change product photo' : 'Upload product photo'}
                        <input type="file" accept={IMAGE_ACCEPT} hidden onChange={handleImageSelect} />
                      </Button>
                      <Typography variant="body2" color="text.secondary">
                        JPEG, PNG, WebP, or GIF up to 20 MB.
                      </Typography>
                      {selectedImagePreview && (
                        <Box sx={{ p: 1.25, border: '1px solid #e5e7eb', borderRadius: 2, bgcolor: '#f8fafc' }}>
                          <Box
                            component="img"
                            src={selectedImagePreview}
                            alt={selectedImageName || 'Selected product'}
                            sx={{ width: '100%', maxHeight: 240, objectFit: 'contain', borderRadius: 1.5, bgcolor: '#fff' }}
                          />
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                            {selectedImageName}
                          </Typography>
                        </Box>
                      )}
                      {imageInputError && <Alert severity="error">{imageInputError}</Alert>}
                      <TextField
                        id="product-details-input"
                        label="Product Details"
                        placeholder="Describe your product: materials, use-cases, target market, key features… The AI will use this to write better copy."
                        value={productDetails}
                        onChange={(e) => setProductDetails(e.target.value)}
                        fullWidth
                        multiline
                        minRows={3}
                        required
                        helperText="Required — this context helps the AI generate accurate marketing copy."
                      />
                      <FormControl fullWidth>
                        <InputLabel id="tone-label">Tone</InputLabel>
                        <Select labelId="tone-label" label="Tone" value={tone} onChange={(event) => setTone(event.target.value)}>
                          {tones.map((item) => (
                            <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                      <Button variant="contained" size="large" onClick={generateProduct} disabled={!selectedImage || !productDetails.trim() || generating}>
                        {generating ? 'Generating...' : 'Generate Draft'}
                      </Button>
                    </Stack>

                    {generatorError && <Alert severity="error" sx={{ mt: 2 }}>{generatorError}</Alert>}
                    {publishMessage && <Alert severity="success" sx={{ mt: 2 }}>{publishMessage}</Alert>}
                  </Box>

                  {(generating || draftVisible) && <Divider />}

                  {generating && (
                    <Stack sx={{ minHeight: 180 }} alignItems="center" justifyContent="center" spacing={2}>
                      <CircularProgress size={28} />
                      <Typography color="text.secondary">Analyzing and writing...</Typography>
                    </Stack>
                  )}

                  {draftVisible && !generating && (
                    <Box sx={{ p: { xs: 2, md: 3 }, bgcolor: '#fbfcfe' }}>
                      <Grid container spacing={2}>
                        <Grid item xs={12}>
                          <TextField label="Trendy_name" value={draft.trendy_name} onChange={(e) => updateDraft('trendy_name', e.target.value)} fullWidth />
                        </Grid>
                        <Grid item xs={12}>
                          <TextField label="Trendy_name_arabic" value={draft.trendy_name_arabic} onChange={(e) => updateDraft('trendy_name_arabic', e.target.value)} fullWidth />
                        </Grid>
                        <Grid item xs={12}>
                          <TextField label="Description" value={draft.description} onChange={(e) => updateDraft('description', e.target.value)} fullWidth multiline minRows={3} />
                        </Grid>
                        <Grid item xs={12}>
                          <TextField label="Description_arabic" value={draft.description_arabic} onChange={(e) => updateDraft('description_arabic', e.target.value)} fullWidth multiline minRows={3} />
                        </Grid>
                        <Grid item xs={12}>
                          <TextField label="Marketing_audience" value={draft.marketing_audience} onChange={(e) => updateDraft('marketing_audience', e.target.value)} fullWidth />
                        </Grid>
                        <Grid item xs={12}>
                          <TextField
                            label="Marketing_partners"
                            helperText="One partner per line"
                            value={Array.isArray(draft.marketing_partners) ? draft.marketing_partners.join('\n') : String(draft.marketing_partners || '')}
                            onChange={(e) => updateDraft('marketing_partners', e.target.value.split('\n').map((item) => item.trim()).filter(Boolean))}
                            fullWidth
                            multiline
                            minRows={3}
                          />
                        </Grid>
                        <Grid item xs={12} sm={4}>
                          <TextField label="Recommended_price" value={draft.recommended_price} onChange={(e) => updateDraft('recommended_price', e.target.value)} fullWidth />
                        </Grid>
                        <Grid item xs={12}>
                          <TextField label="Marketing_plan" value={Array.isArray(draft.marketing_plan) ? draft.marketing_plan.join('\n') : draft.marketing_plan} onChange={(e) => updateDraft('marketing_plan', e.target.value)} fullWidth multiline minRows={4} />
                        </Grid>
                      </Grid>
                      <Button sx={{ mt: 2 }} fullWidth variant="contained" color="success" onClick={publishProduct} disabled={publishing}>
                        {publishing ? 'Publishing...' : 'Publish Product to Zid'}
                      </Button>
                    </Box>
                  )}
                </Paper>
              </Grid>
            </Grid>
          </Stack>
        </Container>
      </Box>
    </ThemeProvider>
  )
}

export default App
