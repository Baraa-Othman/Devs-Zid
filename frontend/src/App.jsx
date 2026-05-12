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
  Snackbar,
  Stack,
  TextField,
  ThemeProvider,
  ToggleButton,
  ToggleButtonGroup,
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
  stock: '',
  marketing_plan: 'Marketing plan placeholder',
}

const emptyDraft = {
  trendy_name: '',
  trendy_name_arabic: '',
  description: '',
  description_arabic: '',
  marketing_audience: '',
  marketing_partners: [],
  recommended_price: '',
  stock: '',
  marketing_plan: '',
}

const draftFieldKeys = [
  'trendy_name',
  'trendy_name_arabic',
  'description',
  'description_arabic',
  'marketing_audience',
  'marketing_partners',
  'recommended_price',
  'stock',
  'marketing_plan',
]

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(new Error('Could not read the selected image.'))
    reader.readAsDataURL(file)
  })
}

function fieldValue(value) {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value.value ?? value.text ?? value.content ?? value.copy ?? ''
  }
  return value
}

function firstDraftValue(source, keys, fallback) {
  for (const key of keys) {
    const value = fieldValue(source?.[key])
    if (value !== undefined && value !== null && value !== '') return value
  }
  return fallback
}

function priceValue(value, fallback = '') {
  const raw = fieldValue(value)
  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    return priceValue(raw.amount ?? raw.price ?? raw.value ?? raw.text, fallback)
  }
  if (raw === undefined || raw === null || raw === '') return fallback
  const match = String(raw).match(/\d+(?:[.,]\d+)?/)
  return match ? match[0].replace(',', '.') : String(raw)
}

function extractFieldExplanations(payload) {
  const source = payload?.data || payload?.product || payload || {}
  const explanations = {}
  const containers = [
    source.explanations,
    source.field_explanations,
    source.fieldExplanations,
    source.field_notes,
    source.fieldNotes,
  ]

  containers.forEach((container) => {
    if (!container || typeof container !== 'object' || Array.isArray(container)) return
    draftFieldKeys.forEach((key) => {
      const value = fieldValue(container[key])
      if (value) explanations[key] = String(value)
    })
  })

  draftFieldKeys.forEach((key) => {
    const field = source[key]
    const embedded = field && typeof field === 'object' && !Array.isArray(field)
      ? field.explanation || field.reason || field.helper || field.note
      : ''
    const sibling = source[`${key}_explanation`] || source[`${key}_reason`] || source[`${key}_helper`]
    const value = fieldValue(embedded || sibling)
    if (value) explanations[key] = String(value)
  })

  return explanations
}

function normalizeDraft(payload) {
  const source = payload?.data || payload?.product || payload || {}
  const trendName = firstDraftValue(source, ['trendy_name', 'name_en', 'name'], draftPlaceholders.trendy_name)
  const trendNameArabic = firstDraftValue(source, ['trendy_name_arabic', 'name_ar', 'name'], draftPlaceholders.trendy_name_arabic)
  const description = firstDraftValue(source, ['description', 'description_en'], draftPlaceholders.description)
  const descriptionArabic = firstDraftValue(source, ['description_arabic', 'description_ar'], draftPlaceholders.description_arabic)
  const sourcePartners = fieldValue(source.marketing_partners)
  const sourcePartnerFallback = fieldValue(source.partners)
  const sourceTags = fieldValue(source.tags)
  const marketingPartners = Array.isArray(sourcePartners)
    ? sourcePartners
    : Array.isArray(sourcePartnerFallback)
      ? sourcePartnerFallback
      : Array.isArray(sourceTags)
        ? sourceTags
        : draftPlaceholders.marketing_partners
  const recommendedPrice = priceValue(
    firstDraftValue(source, ['recommended_price', 'price', 'suggested_price'], draftPlaceholders.recommended_price),
    draftPlaceholders.recommended_price,
  )
  const marketingPlan = firstDraftValue(source, ['marketing_plan', 'bullets'], draftPlaceholders.marketing_plan)
  const marketingAudience = firstDraftValue(source, ['marketing_audience', 'audience'], draftPlaceholders.marketing_audience)

  return {
    trendy_name: trendName,
    trendy_name_arabic: trendNameArabic,
    description,
    description_arabic: descriptionArabic,
    marketing_audience: marketingAudience,
    marketing_partners: marketingPartners,
    recommended_price: recommendedPrice,
    stock: '',
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

function FieldWithReason({ reason, children }) {
  return (
    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems="stretch">
      <Box sx={{ flex: 1 }}>{children}</Box>
      <Box sx={{ width: { xs: '100%', sm: 180 }, p: 1.25, border: '1px solid #e5e7eb', borderRadius: 1.5, bgcolor: '#f8fafc' }}>
        <Typography variant="caption" sx={{ color: '#475467', fontWeight: 700 }}>
          Why
        </Typography>
        <Typography variant="body2" sx={{ color: '#344054', mt: 0.5 }}>
          {reason || 'Add this manually or generate with AI to see the reason.'}
        </Typography>
      </Box>
    </Stack>
  )
}

function MaybeFieldWithReason({ showReason, reason, children }) {
  if (!showReason) return children
  return <FieldWithReason reason={reason}>{children}</FieldWithReason>
}

function App() {
  const [orders, setOrders] = useState([])
  const [alerts, setAlerts] = useState([])
  const [dataSource, setDataSource] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [loadError, setLoadError] = useState('')

  const [selectedImage, setSelectedImage] = useState(null)
  const [selectedImageName, setSelectedImageName] = useState('')
  const [selectedImagePreview, setSelectedImagePreview] = useState('')
  const [imageInputError, setImageInputError] = useState('')
  const [creatorMode, setCreatorMode] = useState('ai')
  const [tone, setTone] = useState('professional')
  const [productDetails, setProductDetails] = useState('')
  const [generating, setGenerating] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [generatorError, setGeneratorError] = useState('')
  const [publishMessage, setPublishMessage] = useState('')
  const [stockMessage, setStockMessage] = useState('')
  const [stockAdditions, setStockAdditions] = useState({})
  const [updatingStockId, setUpdatingStockId] = useState('')
  const [generatedRaw, setGeneratedRaw] = useState(null)
  const [fieldExplanations, setFieldExplanations] = useState({})
  const [draftVisible, setDraftVisible] = useState(false)
  const [draft, setDraft] = useState({ ...emptyDraft })

  const totalSold = useMemo(
    () => alerts.reduce((sum, item) => sum + Number(field(item, ['sold_quantity'], 0)), 0),
    [alerts],
  )

  async function loadDashboard({ quiet = false } = {}) {
    setLoadError('')
    quiet ? setRefreshing(true) : setLoading(true)

    try {
      const [ordersResult, alertsResult, sourceResult] = await Promise.allSettled([
        fetchJson('/api/orders'),
        fetchJson('/api/alerts'),
        fetchJson('/api/source/status'),
      ])

      if (ordersResult.status === 'fulfilled') {
        setOrders(asArray(ordersResult.value, 'orders'))
      }
      if (alertsResult.status === 'fulfilled') {
        setAlerts(asArray(alertsResult.value, 'alerts'))
      }
      if (sourceResult.status === 'fulfilled') {
        setDataSource(sourceResult.value?.data || sourceResult.value)
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
    setFieldExplanations({})
    setStockMessage('')
    setDraftVisible(creatorMode === 'manual')

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
    setFieldExplanations({})
    setStockMessage('')
    setDraftVisible(true)
    setDraft({ ...draftPlaceholders, stock: '' })
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
      setFieldExplanations(extractFieldExplanations(payload))
      setDraft(normalized)
    } catch (error) {
      setGeneratorError(error.message || 'Could not generate product draft.')
      setDraft({ ...draftPlaceholders, stock: '' })
      setFieldExplanations({})
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
          ...(creatorMode === 'ai' && generatedRaw ? generatedRaw : {}),
          ...draft,
          creator_mode: creatorMode,
          image_url: selectedImagePreview || undefined,
          tone,
          name: draft.trendy_name_arabic || draft.trendy_name,
          name_ar: draft.trendy_name_arabic || draft.trendy_name,
          name_en: draft.trendy_name,
          description: draft.description_arabic || draft.description,
          description_ar: draft.description_arabic || draft.description,
          description_en: draft.description,
          price: draft.recommended_price,
          stock: draft.stock,
          quantity: draft.stock,
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
      setSelectedImage(null)
      setSelectedImageName('')
      setSelectedImagePreview('')
      setProductDetails('')
      setGeneratedRaw(null)
      setFieldExplanations({})
      setDraft({ ...emptyDraft })
      setCreatorMode('ai')
      setDraftVisible(false)
    } catch (error) {
      setGeneratorError(error.message || 'Could not publish product.')
    } finally {
      setPublishing(false)
    }
  }

  function updateDraft(key, value) {
    setDraft((current) => ({ ...current, [key]: value }))
  }

  function handleCreatorModeChange(_event, value) {
    if (!value) return
    setCreatorMode(value)
    setGeneratorError('')
    setPublishMessage('')
    setGeneratedRaw(null)
    setFieldExplanations({})
    setDraft({ ...emptyDraft })
    setDraftVisible(value === 'manual')
  }

  const isAiMode = creatorMode === 'ai'
  const showDraftEditor = creatorMode === 'manual' || draftVisible
  const hasName = Boolean((draft.trendy_name || draft.trendy_name_arabic || '').trim())
  const hasPrice = Boolean(String(draft.recommended_price || '').trim())
  const hasStock = Boolean(String(draft.stock || '').trim())
  const canPublish = Boolean(
    hasName
      && hasPrice
      && hasStock
      && (creatorMode === 'manual' || draft.description)
      && !publishing,
  )

  function draftHelperText(_key, fallback = '') {
    return fallback
  }

  function draftReason(key) {
    return fieldExplanations[key] || ''
  }

  function updateStockAddition(alert, value) {
    const alertId = field(alert, ['id', 'product_id', 'sku'])
    setStockAdditions((current) => ({ ...current, [alertId]: value }))
  }

  async function addStockFromAlert(alert) {
    const alertId = field(alert, ['id', 'product_id', 'sku'])
    const productId = field(alert, ['product_id', 'id'], '')
    const amount = Number(stockAdditions[alertId])

    if (!productId || !Number.isFinite(amount) || amount <= 0) {
      setStockMessage('Enter a stock amount greater than 0.')
      return
    }

    setUpdatingStockId(alertId)
    setStockMessage('')

    try {
      const payload = await fetchJson(`/api/products/${encodeURIComponent(productId)}/stock/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ amount }),
      })
      setAlerts((current) => current.filter((item) => field(item, ['id', 'product_id', 'sku']) !== alertId))
      setStockAdditions((current) => {
        const next = { ...current }
        delete next[alertId]
        return next
      })
      setStockMessage(payload?.message || 'Stock updated and alert removed.')
    } catch (error) {
      setStockMessage(error.message || 'Could not update stock.')
    } finally {
      setUpdatingStockId('')
    }
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
                    Live stock alerts and recent orders from Zid, plus AI product descriptions ready to review and publish.
                  </Typography>
                </Box>
                <Stack direction="row" spacing={1.25} flexWrap="wrap" useFlexGap>
                  <Chip label={dataSource?.source === 'zid_api' ? 'Source: Zid API' : 'Source: checking'} color={dataSource?.connected ? 'success' : 'default'} />
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
                <Stat label="Recent orders from Zid" value={orders.length} tone="blue" />
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
                      Products are pulled from Zid, low-stock items are detected live, and recent orders are used when available for sales context.
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
                            {['Product', 'SKU', 'Stock', 'Sold', 'Add to stock'].map((heading) => (
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
                              <Box component="td" sx={{ p: 2, minWidth: 220 }}>
                                <Stack direction="row" spacing={1} alignItems="center">
                                  <TextField
                                    label="Qty"
                                    type="number"
                                    size="small"
                                    value={stockAdditions[field(alert, ['id', 'product_id', 'sku'])] || ''}
                                    onChange={(e) => updateStockAddition(alert, e.target.value)}
                                    inputProps={{ min: 1, step: 1 }}
                                    sx={{ width: 92 }}
                                  />
                                  <Button
                                    variant="contained"
                                    size="small"
                                    onClick={() => addStockFromAlert(alert)}
                                    disabled={updatingStockId === field(alert, ['id', 'product_id', 'sku'])}
                                  >
                                    {updatingStockId === field(alert, ['id', 'product_id', 'sku']) ? 'Adding...' : 'Add'}
                                  </Button>
                                </Stack>
                              </Box>
                            </Box>
                          ))}
                        </Box>
                      </Box>
                    </Box>
                  )}
                </Paper>

                <Paper elevation={0} sx={{ mt: 3, p: { xs: 2, md: 3 }, border: '1px solid #e5e7eb', borderRadius: 2 }}>
                  <Typography variant="h6" sx={{ fontWeight: 900, mb: 2 }}>
                    Recent Orders from Zid
                  </Typography>
                  {orders.length === 0 ? (
                    <Typography color="text.secondary">No recent orders returned from Zid yet.</Typography>
                  ) : (
                    <Stack spacing={1.25}>
                      {orders.slice(0, 5).map((order, index) => (
                        <Box key={field(order, ['order_id', 'id'], index)} sx={{ p: 1.5, bgcolor: '#f8fafc', borderRadius: 1.5, display: 'flex', justifyContent: 'space-between', gap: 2 }}>
                          <Box sx={{ minWidth: 0 }}>
                            <Typography sx={{ fontWeight: 800, overflowWrap: 'anywhere' }}>Order #{field(order, ['order_id', 'id'])}</Typography>
                            <Typography variant="body2" color="text.secondary">{field(order, ['customer_name'], 'Unknown customer')}</Typography>
                            <Chip size="small" label={field(order, ['status_name', 'status'], 'New')} sx={{ mt: 0.75, fontWeight: 700 }} />
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
                      Product Creator
                    </Typography>
                    <Typography color="text.secondary" sx={{ mt: 0.75, mb: 2 }}>
                      Create product copy with AI or enter it manually before publishing to Zid.
                    </Typography>

                    <Stack spacing={2}>
                      <ToggleButtonGroup
                        value={creatorMode}
                        exclusive
                        onChange={handleCreatorModeChange}
                        fullWidth
                        size="small"
                        color="primary"
                      >
                        <ToggleButton value="ai">Create with AI</ToggleButton>
                        <ToggleButton value="manual">Manual</ToggleButton>
                      </ToggleButtonGroup>
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
                      {isAiMode && (
                        <>
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
                        </>
                      )}
                    </Stack>

                    {generatorError && <Alert severity="error" sx={{ mt: 2 }}>{generatorError}</Alert>}
                    {publishMessage && <Alert severity="success" sx={{ mt: 2 }}>{publishMessage}</Alert>}
                  </Box>

                  {(generating || showDraftEditor) && <Divider />}

                  {generating && (
                    <Stack sx={{ minHeight: 180 }} alignItems="center" justifyContent="center" spacing={2}>
                      <CircularProgress size={28} />
                      <Typography color="text.secondary">Analyzing and writing...</Typography>
                    </Stack>
                  )}

                  {showDraftEditor && !generating && (
                    <Box sx={{ p: { xs: 2, md: 3 }, bgcolor: '#fbfcfe' }}>
                      <Grid container spacing={2}>
                        <Grid item xs={12}>
                          <MaybeFieldWithReason showReason={isAiMode} reason={draftReason('trendy_name')}>
                            <TextField label="Name" value={draft.trendy_name} onChange={(e) => updateDraft('trendy_name', e.target.value)} helperText={draftHelperText('trendy_name')} required fullWidth />
                          </MaybeFieldWithReason>
                        </Grid>
                        <Grid item xs={12}>
                          <MaybeFieldWithReason showReason={isAiMode} reason={draftReason('trendy_name_arabic')}>
                            <TextField label="Trendy_name_arabic" value={draft.trendy_name_arabic} onChange={(e) => updateDraft('trendy_name_arabic', e.target.value)} helperText={draftHelperText('trendy_name_arabic')} fullWidth />
                          </MaybeFieldWithReason>
                        </Grid>
                        <Grid item xs={12}>
                          <MaybeFieldWithReason showReason={isAiMode} reason={draftReason('recommended_price')}>
                            <TextField
                              label="Price"
                              type="number"
                              value={draft.recommended_price}
                              onChange={(e) => updateDraft('recommended_price', e.target.value)}
                              helperText={isAiMode ? 'AI suggested price. You can edit it.' : draftHelperText('recommended_price')}
                              required
                              fullWidth
                              inputProps={{ min: 0, step: 0.01 }}
                            />
                          </MaybeFieldWithReason>
                        </Grid>
                        <Grid item xs={12}>
                          <TextField
                            label="Stock"
                            type="number"
                            value={draft.stock}
                            onChange={(e) => updateDraft('stock', e.target.value)}
                            required
                            fullWidth
                            inputProps={{ min: 0, step: 1 }}
                          />
                        </Grid>
                        <Grid item xs={12}>
                          <MaybeFieldWithReason showReason={isAiMode} reason={draftReason('description')}>
                            <TextField label="Description" value={draft.description} onChange={(e) => updateDraft('description', e.target.value)} helperText={draftHelperText('description')} required={isAiMode} fullWidth multiline minRows={3} />
                          </MaybeFieldWithReason>
                        </Grid>
                        <Grid item xs={12}>
                          <MaybeFieldWithReason showReason={isAiMode} reason={draftReason('description_arabic')}>
                            <TextField label="Description_arabic" value={draft.description_arabic} onChange={(e) => updateDraft('description_arabic', e.target.value)} helperText={draftHelperText('description_arabic')} fullWidth multiline minRows={3} />
                          </MaybeFieldWithReason>
                        </Grid>
                        <Grid item xs={12}>
                          <MaybeFieldWithReason showReason={isAiMode} reason={draftReason('marketing_audience')}>
                            <TextField label="Marketing_audience" value={draft.marketing_audience} onChange={(e) => updateDraft('marketing_audience', e.target.value)} helperText={draftHelperText('marketing_audience')} fullWidth />
                          </MaybeFieldWithReason>
                        </Grid>
                        <Grid item xs={12}>
                          <MaybeFieldWithReason showReason={isAiMode} reason={draftReason('marketing_partners')}>
                            <TextField
                              label="Marketing_partners"
                              helperText={draftHelperText('marketing_partners', 'One partner per line')}
                              value={Array.isArray(draft.marketing_partners) ? draft.marketing_partners.join('\n') : String(draft.marketing_partners || '')}
                              onChange={(e) => updateDraft('marketing_partners', e.target.value.split('\n').map((item) => item.trim()).filter(Boolean))}
                              fullWidth
                              multiline
                              minRows={3}
                            />
                          </MaybeFieldWithReason>
                        </Grid>
                        <Grid item xs={12}>
                          <MaybeFieldWithReason showReason={isAiMode} reason={draftReason('marketing_plan')}>
                            <TextField label="Marketing_plan" value={Array.isArray(draft.marketing_plan) ? draft.marketing_plan.join('\n') : draft.marketing_plan} onChange={(e) => updateDraft('marketing_plan', e.target.value)} helperText={draftHelperText('marketing_plan')} fullWidth multiline minRows={4} />
                          </MaybeFieldWithReason>
                        </Grid>
                      </Grid>
                      <Button sx={{ mt: 2 }} fullWidth variant="contained" color="success" onClick={publishProduct} disabled={!canPublish}>
                        {publishing ? 'Publishing...' : 'Publish Product to Zid'}
                      </Button>
                    </Box>
                  )}
                </Paper>
              </Grid>
            </Grid>
          </Stack>
        </Container>
        <Snackbar
          open={Boolean(stockMessage)}
          autoHideDuration={3500}
          onClose={() => setStockMessage('')}
          message={stockMessage}
        />
      </Box>
    </ThemeProvider>
  )
}

export default App
