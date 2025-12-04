import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Box, Card, CardContent, Typography, FormControl, InputLabel, Select, MenuItem, TextField, FormControlLabel, Checkbox, Alert, LinearProgress, Chip, Stack, Divider, IconButton, Dialog, DialogTitle, DialogContent, Table, TableBody, TableCell, TableHead, TableRow, Button } from '@mui/material'
import { Bar, Doughnut } from 'react-chartjs-2'
import { Chart, ArcElement, BarElement, CategoryScale, LinearScale, Tooltip, Legend } from 'chart.js'
import { useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { API_BASE } from '../config'
import CloseIcon from '@mui/icons-material/Close'
import ChevronRightIcon from '@mui/icons-material/ChevronRight'
import DownloadIcon from '@mui/icons-material/Download'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import html2canvas from 'html2canvas'
import jsPDF from 'jspdf'

Chart.register(ArcElement, BarElement, CategoryScale, LinearScale, Tooltip, Legend)

const API = {
  stats: `${API_BASE}/stats/`,
  productTrend: `${API_BASE}/product-trend/`,
}

const SECTION_COLORS = {
  'CARNES': '#C0392B',
  'CERDO': '#D35400',
  'ACHURAS': '#9C640C',
  'ELABORADOS': '#27AE60',
  'VARIOS': '#1ABC9C',
  'CONGELADOS': '#2980B9',
  'VERDULERIA': '#1F618D',
  'POLLO': '#8E44AD',
  'ENSALADAS': '#AF7AC5',
  'PAN': '#E74C3C',
  'LACTEOS': '#E5B12C',
  'GASEOSAS': '#7DCEA0',
  'CARBON': '#117A65'
}

const FALLBACK_COLORS = ['#C0392B', '#D35400', '#F1C40F', '#27AE60', '#1ABC9C', '#2980B9', '#8E44AD', '#AF7AC5', '#E67E22', '#2ECC71']

const CARD_TITLE_SX = {
  fontWeight: 800,
  color: '#f9fbff',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  mb: 1,
}

const toLocalIso = (date) => {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

function getSectionColor(label, idx) {
  const key = (label || '').trim().toUpperCase()
  return SECTION_COLORS[key] || FALLBACK_COLORS[idx % FALLBACK_COLORS.length]
}

function number(n, digits = 2) {
  if (typeof n !== 'number') return n
  return n.toLocaleString('es-AR', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

function fmtDate(s) {
  if (!s) return ''
  const [y, m, d] = s.split('-')
  return `${d}/${m}/${y}`
}

function formatImporte(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) return value
  const digits = Math.max(1, Math.floor(Math.log10(Math.abs(value || 1))) + 1)
  const decimals = digits >= 7 ? 0 : 2
  return value.toLocaleString('es-AR', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

function hasQuantity(value) {
  return typeof value === 'number' && !Number.isNaN(value) && Math.abs(value) > 0.0005
}

function formatMeasures(peso, units, { withLabels = true } = {}) {
  const parts = []
  if (hasQuantity(peso)) parts.push(`${withLabels ? 'Peso: ' : ''}${number(peso, 2)} kg`)
  if (hasQuantity(units)) parts.push(`${withLabels ? 'Unidades: ' : ''}${number(units, 0)}`)
  if (!parts.length) return withLabels ? 'Sin datos' : ''
  return parts.join(withLabels ? ' · ' : ' / ')
}

function formatInteger(value) {
  const parsed = typeof value === 'number' && !Number.isNaN(value) ? value : 0
  return Math.round(parsed).toLocaleString('es-AR')
}

export default function StatsPage() {
  const [params] = useSearchParams()
  const paramsKey = params.toString()
  const { authFetch } = useAuth()
  const batchId = params.get('batch_id') || ''
  const rangeParam = params.get('range') || ''
  const startParam = params.get('fecha_desde') || ''
  const endParam = params.get('fecha_hasta') || ''
  const multiParam = params.get('multi') === '1' || (startParam && endParam && startParam !== endParam)
  const todayIso = useMemo(() => toLocalIso(new Date()), [])
  const currentYear = useMemo(() => new Date().getFullYear(), [])
  const [generalYear, setGeneralYear] = useState(currentYear)
  const startOfYearIso = useMemo(() => toLocalIso(new Date(generalYear, 0, 1)), [generalYear])
  const endOfYearIso = useMemo(() => toLocalIso(new Date(generalYear, 11, 31)), [generalYear])

  const [rangeMode, setRangeMode] = useState(() => {
    if (rangeParam === 'day') return 'day'
    if (rangeParam === 'month') return 'month'
    return 'year'
  }) // 'year' | 'day' | 'month'
  const [variosDias, setVariosDias] = useState(() => {
    if (rangeParam === 'day') return multiParam
    return true
  })
  const [month, setMonth] = useState(() => (rangeParam === 'month' && startParam ? startParam.slice(0, 7) : ''))
  const [fechaDesde, setFechaDesde] = useState(() => {
    if (rangeParam === 'day' && startParam) return startParam
    return startOfYearIso
  })
  const [fechaHasta, setFechaHasta] = useState(() => {
    if (rangeParam === 'day' && (endParam || startParam)) return endParam || startParam
    return endOfYearIso
  })
  const [fSeccion, setFSeccion] = useState('')
  const [selectedSection, setSelectedSection] = useState('')

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [selectedProduct, setSelectedProduct] = useState('')
  const [productTrend, setProductTrend] = useState(null)
  const [trendLoading, setTrendLoading] = useState(false)
  const [trendError, setTrendError] = useState('')
  const [trendOpen, setTrendOpen] = useState(false)
  const [exporting, setExporting] = useState(false)
  const exportRef = useRef(null)


  useEffect(() => {
    const urlRange = params.get('range')
    if (!urlRange) return
    const urlStart = params.get('fecha_desde') || ''
    const urlEndRaw = params.get('fecha_hasta') || ''
    const urlEnd = urlEndRaw || urlStart
    if (urlRange === 'day') {
      const urlMulti = params.get('multi') === '1' || (urlStart && urlEndRaw && urlStart !== urlEndRaw)
      setRangeMode('day')
      setVariosDias(urlMulti)
      if (urlStart) setFechaDesde(urlStart)
      if (urlEnd) setFechaHasta(urlEnd)
    } else if (urlRange === 'month') {
      setRangeMode('month')
      if (urlStart) {
        setMonth(urlStart.slice(0, 7))
        setFechaDesde(urlStart)
      }
      if (urlEnd) setFechaHasta(urlEnd)
    } else if (urlRange === 'year') {
      setRangeMode('year')
    }
  }, [paramsKey])

  useEffect(() => {
    if (rangeMode === 'year') {
      if (!variosDias) setVariosDias(true)
      if (month) setMonth('')
      if (fechaDesde !== startOfYearIso) setFechaDesde(startOfYearIso)
      if (fechaHasta !== endOfYearIso) setFechaHasta(endOfYearIso)
      return
    }

    if (rangeMode === 'month') {
      if (!month) {
        setMonth(todayIso.slice(0, 7))
        return
      }
      const [y, m] = month.split('-')
      if (y && m) {
        const lastDay = new Date(Number(y), Number(m), 0).getDate()
        const start = `${y}-${m}-01`
        const end = `${y}-${m}-${String(lastDay).padStart(2, '0')}`
        if (fechaDesde !== start) setFechaDesde(start)
        if (fechaHasta !== end) setFechaHasta(end)
      }
      return
    }

    if (rangeMode === 'day' && !variosDias) {
      if (fechaHasta !== fechaDesde) setFechaHasta(fechaDesde)
    }
  }, [rangeMode, month, variosDias, fechaDesde, fechaHasta, startOfYearIso, endOfYearIso, todayIso])

  const buildRangeParams = useCallback(() => {
    if (rangeMode === 'year') {
      return { start: startOfYearIso, end: endOfYearIso }
    }
    if (rangeMode === 'month' && month) {
      return { start: fechaDesde, end: fechaHasta }
    }
    if (!fechaDesde) return {}
    if (variosDias && fechaHasta) {
      return { start: fechaDesde, end: fechaHasta }
    }
    return { start: fechaDesde, end: fechaDesde }
  }, [rangeMode, month, fechaDesde, fechaHasta, variosDias, startOfYearIso, endOfYearIso])
  const fetchStats = useCallback(async () => {
    setLoading(true); setError('')
    const search = new URLSearchParams()
    const range = buildRangeParams()
    if (batchId) search.set('batch_id', batchId)
    if (rangeMode) search.set('range', rangeMode)
    if (rangeMode === 'day' && variosDias) search.set('multi', '1')
    if (rangeMode === 'month' && month) search.set('mes', month)
    if (range.start) search.set('fecha_desde', range.start)
    if (range.end) search.set('fecha_hasta', range.end)
    if (fSeccion) search.set('seccion', fSeccion)
    try {
      const resp = await authFetch(`${API.stats}?${search.toString()}`)
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'Error de servidor')
      setResult(data)
      setSelectedProduct('')
      setProductTrend(null)
      setTrendError('')
      setTrendOpen(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [batchId, buildRangeParams, fSeccion, authFetch])

  useEffect(() => {
    fetchStats()
  }, [fetchStats])

  const totals = result?.totals || { rows: 0, peso: 0, units: 0, imp: 0 }
  const rowsCount = totals?.rows ?? 0
  const hasData = Boolean(result) && rowsCount > 0
  const showEmpty = Boolean(result) && !loading && rowsCount === 0
  const sectionList = hasData ? (result?.by_seccion || []) : []
  const period = result?.period || null
  const datasetYear = generalYear

  const handleYearInputChange = useCallback((event) => {
    const value = parseInt(event.target.value, 10)
    if (!Number.isNaN(value)) {
      setGeneralYear(value)
    }
  }, [])

  const pieData = useMemo(() => {
    const list = sectionList
    return {
      labels: list.map(x => x.label || '(sin nombre)'),
      datasets: [{
        label: 'Importe por seccion',
        data: list.map(x => x.imp),
        backgroundColor: list.map((row, i) => getSectionColor(row.label, i)),
        borderWidth: 0
      }]
    }
  }, [sectionList])

  const handleSectionClick = useCallback((sectionLabel) => {
    if (!sectionLabel) return
    const normalized = sectionLabel.trim()
    setProductTrend(null)
    setSelectedProduct('')
    setSelectedSection((prev) => {
      if (prev === normalized) {
        setFSeccion('')
        return ''
      }
      setFSeccion(normalized)
      return normalized
    })
  }, [])

  const productPalette = ['#845EF7', '#FF6B6B', '#F9A826', '#6BCB77', '#4D96FF', '#FF6F91', '#FFC75F', '#70D6FF', '#A663CC', '#3DC1D3']


  const pieOptions = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (ctx) => `$ ${formatImporte(ctx.parsed ?? 0)}`,
          afterLabel: (ctx) => {
            const row = sectionList[ctx.dataIndex]
            if (!row) return ''
            const details = formatMeasures(row.peso, row.units)
            return details === 'Sin datos' ? '' : details
          }
        }
      }
    },
    onClick: (_event, elements, chart) => {
      if (!elements?.length) return
      const index = elements[0].index
      const label = chart.data.labels[index]
      handleSectionClick(label)
    }
  }), [handleSectionClick, sectionList])

  const barData = useMemo(() => {
    const list = hasData ? (result?.top_productos || []) : []
    return {
      labels: list.map(x => x.label || '(sin nombre)'),
      datasets: [{
        label: 'Importe',
        data: list.map(x => x.imp),
        backgroundColor: list.map((_, i) => productPalette[i % productPalette.length]),
        borderRadius: 12,
        borderSkipped: false,
        barThickness: 32,
      }]
    }
  }, [hasData, result])

  const totalImporte = result?.totals?.imp || 0
  const formattedTotal = formatImporte(totalImporte)
  const topProducts = hasData ? (result?.top_productos || []) : []
  const showUnitsCard = hasQuantity(totals.units)

  const handleProductClick = useCallback(async (productLabel) => {
    if (!productLabel) return
    setSelectedProduct(productLabel)
    setTrendLoading(true)
    setTrendError('')
    setTrendOpen(true)
    setProductTrend(null)
    const search = new URLSearchParams()
    const range = buildRangeParams()
    search.set('product', productLabel)
    if (batchId) search.set('batch_id', batchId)
    if (rangeMode) search.set('range', rangeMode)
    if (rangeMode === 'day' && variosDias) search.set('multi', '1')
    if (rangeMode === 'month' && month) search.set('mes', month)
    if (range.start) search.set('fecha_desde', range.start)
    if (range.end) search.set('fecha_hasta', range.end)
    if (fSeccion) search.set('seccion', fSeccion)
    try {
      const resp = await authFetch(`${API.productTrend}?${search.toString()}`)
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo obtener el detalle')
      setProductTrend(data.series)
    } catch (err) {
      setTrendError(err.message)
    } finally {
      setTrendLoading(false)
    }
  }, [batchId, fSeccion, buildRangeParams, authFetch])
  const closeTrend = useCallback(() => {
    setTrendOpen(false)
    setProductTrend(null)
    setSelectedProduct('')
    setTrendError('')
  }, [])

  const handleDownloadPdf = useCallback(async () => {
    if (!exportRef.current || !result || !hasData) return
    setExporting(true)
    try {
      const canvas = await html2canvas(exportRef.current, {
        scale: 2,
        backgroundColor: '#050505',
        useCORS: true,
      })
      const imageData = canvas.toDataURL('image/png')
      const pdf = new jsPDF('p', 'mm', 'a4')
      const pageWidth = pdf.internal.pageSize.getWidth()
      const pageHeight = pdf.internal.pageSize.getHeight()
      const imgWidth = pageWidth
      const imgHeight = canvas.height * imgWidth / canvas.width
      let heightLeft = imgHeight
      let position = 0
      pdf.addImage(imageData, 'PNG', 0, position, imgWidth, imgHeight)
      heightLeft -= pageHeight
      while (heightLeft > 0) {
        position = heightLeft - imgHeight
        pdf.addPage()
        pdf.addImage(imageData, 'PNG', 0, position, imgWidth, imgHeight)
        heightLeft -= pageHeight
      }
      const label = selectedSection ? selectedSection.replace(/\s+/g, '_') : `general_${datasetYear}`
      pdf.save(`estadisticas_${label}_${Date.now()}.pdf`)
    } catch (err) {
      console.error(err)
      window.alert('No se pudo generar el PDF. Reintentá nuevamente.')
    } finally {
      setExporting(false)
    }
  }, [currentYear, hasData, result, selectedSection])


  const barOptions = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (ctx) => `$ ${formatImporte(ctx.parsed.y ?? ctx.parsed.x)}`,
          afterLabel: (ctx) => {
            const related = topProducts[ctx.dataIndex]
            if (!related) return ''
            const details = formatMeasures(related.peso, related.units)
            return details === 'Sin datos' ? '' : details
          },
        }
      },
    },
    scales: {
      x: {
        ticks: { color: '#ccc', maxRotation: 45, minRotation: 0, autoSkip: false },
        grid: { display: false },
      },
      y: {
        ticks: { color: '#848484', callback: (value) => `$ ${formatImporte(value)}` },
        grid: { color: 'rgba(255,255,255,0.06)' }
      }
    },
    onClick: (_event, elements, chart) => {
      if (!elements?.length) return
      const index = elements[0].index
      const label = chart.data.labels[index]
      handleProductClick(label)
    }
  }), [handleProductClick, topProducts])

  const trendChartData = useMemo(() => {
    if (!productTrend) return null
    return {
      labels: productTrend.map(item => item.date ? fmtDate(item.date) : 'Sin fecha'),
      datasets: [{
        label: selectedProduct,
        data: productTrend.map(item => item.imp),
        backgroundColor: 'rgba(132, 94, 247, 0.8)',
        borderRadius: 14,
        barThickness: 32,
      }]
    }
  }, [productTrend, selectedProduct])

  const trendTotals = useMemo(() => {
    if (!productTrend) return { imp: 0, peso: 0, units: 0 }
    return productTrend.reduce((acc, item) => ({
      imp: acc.imp + (item?.imp || 0),
      peso: acc.peso + (item?.peso || 0),
      units: acc.units + (item?.units || 0),
    }), { imp: 0, peso: 0, units: 0 })
  }, [productTrend])

  const trendOptions = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (ctx) => `$ ${formatImporte(ctx.parsed.y ?? ctx.parsed.x)}`,
          afterLabel: (ctx) => {
            if (!productTrend) return ''
            const point = productTrend[ctx.dataIndex]
            if (!point) return ''
            const details = formatMeasures(point.peso, point.units)
            return details === 'Sin datos' ? '' : details
          }
        }
      }
    },
    scales: {
      x: { grid: { display: false }, ticks: { color: '#ccc' } },
      y: { ticks: { color: '#848484', callback: (value) => `$ ${formatImporte(value)}` } }
    }
  }), [productTrend])

  return (
    <Box sx={{ width: '100%', display: 'flex', justifyContent: 'center', overflowX: 'hidden', px: { xs: 1, md: 2 }, py: 4 }}>
      <Box sx={{ width: '100%', maxWidth: 1400, px: { xs: 1, md: 2, lg: 4 } }}>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 2, mb: 1 }}>
        <Typography variant="h4">Estadísticas</Typography>
        {result && (
          <Button
            variant="contained"
            color="secondary"
            startIcon={<DownloadIcon />}
            disabled={exporting || !hasData}
            onClick={handleDownloadPdf}
          >
            {exporting ? 'Generando...' : 'Guardar PDF'}
          </Button>
        )}
      </Box>
      <Card sx={{ width: '100%' }}>
        <CardContent>
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: 'repeat(auto-fit, minmax(220px, 1fr))' } }}>
            <Box>
              <FormControl fullWidth>
                <InputLabel id="range-mode">Modo de rango</InputLabel>
                <Select labelId="range-mode" label="Modo de rango" value={rangeMode} onChange={(e) => setRangeMode(e.target.value)}>
                  <MenuItem value="year">General (año {datasetYear})</MenuItem>
                  <MenuItem value="day">Por dia</MenuItem>
                  <MenuItem value="month">Por mes</MenuItem>
                </Select>
              </FormControl>
            </Box>

            {rangeMode === 'year' && (
              <Box>
                <TextField
                  type="number"
                  fullWidth
                  label="Año"
                  value={generalYear}
                  onChange={handleYearInputChange}
                  InputLabelProps={{ shrink: true }}
                />
              </Box>
            )}

            {rangeMode === 'year' && (
              <Stack direction="row" spacing={2} alignItems="center">
                <Chip color="primary" label={`General ${datasetYear}`} />
                <Typography variant="body2" color="text.secondary">
                  {fmtDate(startOfYearIso)} a {fmtDate(endOfYearIso)}
                  {period?.hasta ? ` · Última carga ${period.hasta}` : ''}
                </Typography>
              </Stack>
            )}

            {rangeMode === 'month' && (
              <Box>
                <TextField type="month" fullWidth label="Mes" InputLabelProps={{ shrink: true }} value={month || todayIso.slice(0, 7)} onChange={(e) => setMonth(e.target.value)} />
              </Box>
            )}

            {rangeMode === 'day' && (
              <>
                <Box>
                  <TextField type="date" fullWidth label="Desde" InputLabelProps={{ shrink: true }} value={fechaDesde} onChange={(e) => setFechaDesde(e.target.value)} />
                </Box>
                {variosDias && (
                  <Box>
                    <TextField type="date" fullWidth label="Hasta" InputLabelProps={{ shrink: true }} value={fechaHasta} onChange={(e) => setFechaHasta(e.target.value)} />
                  </Box>
                )}
                <Box>
                  <FormControlLabel control={<Checkbox checked={variosDias} onChange={(e) => setVariosDias(e.target.checked)} />} label="Varios dias" />
                </Box>
              </>
            )}

            {loading && <Box><LinearProgress /></Box>}
            {error && <Box><Alert severity="error">{error}</Alert></Box>}
          </Box>
        </CardContent>
      </Card>

      {result && (
        <Box ref={exportRef} sx={{ mt: 3, width: '100%', overflowX: 'hidden' }}>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} justifyContent="flex-start" sx={{ mb: 3 }}>
            {(result.period?.desde || result.period?.hasta) && (
              <Chip color="primary" label={`Periodo: ${fmtDate(result.period?.desde || '')}${result.period?.hasta ? ` a ${fmtDate(result.period?.hasta)}` : ''}`} sx={{ px: 2, py: 1, fontSize: 16 }} />
            )}
            {selectedSection && (
              <Chip color="secondary" label={`Seccion: ${selectedSection}`} onDelete={() => handleSectionClick(selectedSection)} sx={{ px: 2, py: 1, fontSize: 16 }} />

            )}
            <Chip label={`Registros: ${formatInteger(rowsCount)}`} sx={{ px: 2, py: 1, fontSize: 16 }} />
          </Stack>

          {showEmpty && (
            <Card sx={{ py: 6, px: 3, background: 'rgba(10,10,20,0.75)', border: '1px solid rgba(255,255,255,0.08)' }}>
              <CardContent sx={{ textAlign: 'center' }}>
                <InfoOutlinedIcon sx={{ fontSize: 64, color: 'rgba(255,255,255,0.45)', mb: 2 }} />
                <Typography variant="h6" sx={{ fontWeight: 700, mb: 1 }}>Sin datos para este periodo</Typography>
                <Typography variant="body1" color="text.secondary">
                  No encontramos registros para el rango seleccionado. Ajustá las fechas o carga nuevos CSV para este intervalo.
                </Typography>
              </CardContent>
            </Card>
          )}

          {hasData && (
            <>
          <Box sx={{
            display: 'grid',
            gap: 2,
            mb: 3,
            gridTemplateColumns: {
              xs: '1fr',
              sm: 'repeat(2, minmax(0, 1fr))',
              lg: showUnitsCard ? 'repeat(4, minmax(0, 1fr))' : 'repeat(3, minmax(0, 1fr))'
            }
          }}>
            <Card>
              <CardContent>
                <Typography variant="body2" color="text.secondary">Importe total</Typography>
                <Typography variant="h5" sx={{ fontWeight: 700 }}>$ {formattedTotal}</Typography>
              </CardContent>
            </Card>
            <Card>
              <CardContent>
                <Typography variant="body2" color="text.secondary">Peso acumulado</Typography>
                <Typography variant="h5" sx={{ fontWeight: 700 }}>{number(totals.peso || 0, 2)} kg</Typography>
              </CardContent>
            </Card>
            {showUnitsCard && (
              <Card>
                <CardContent>
                  <Typography variant="body2" color="text.secondary">Unidades totales</Typography>
                  <Typography variant="h5" sx={{ fontWeight: 700 }}>{number(totals.units || 0, 0)}</Typography>
                </CardContent>
              </Card>
            )}
            <Card>
              <CardContent>
                <Typography variant="body2" color="text.secondary">Registros procesados</Typography>
                <Typography variant="h5" sx={{ fontWeight: 700 }}>{formatInteger(totals.rows || 0)}</Typography>
              </CardContent>
            </Card>
          </Box>

          <Box sx={{ display: 'grid', gap: 3, gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' } }}>
            <Box sx={{ display: 'flex' }}>
              <Card sx={{ width: '100%', height: '100%', flexGrow: 1 }}>
                <CardContent>
                  <Typography variant="h6" sx={CARD_TITLE_SX}>Importe por seccion</Typography>
                  <Box sx={{ position: 'relative', width: '100%', height: { xs: 360, md: 460 } }}>
                    <Doughnut data={pieData} options={pieOptions} />
                    <Box sx={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', pointerEvents: 'none' }}>
                      <Box sx={{ textAlign: 'center' }}>
                        <Typography variant="subtitle1">Importe total</Typography>
                        <Typography variant="h5" sx={{ fontWeight: 800 }}>$ {formattedTotal}</Typography>
                      </Box>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Box>

            <Box sx={{ display: 'flex' }}>
              <Card sx={{ width: '100%', height: '100%', flexGrow: 1 }}>
                <CardContent>
                  <Typography variant="h6" sx={CARD_TITLE_SX}>Top Productos por Importe</Typography>
                  <Box sx={{ width: '100%', height: { xs: 360, md: 460 } }}>
                    <Bar data={barData} options={barOptions} />
                  </Box>
                </CardContent>
              </Card>
            </Box>
          </Box>

          {sectionList.length > 0 && (
            <Box sx={{ mt: 3 }}>
              <Card>
                <CardContent>
                  <Typography variant="h6" sx={CARD_TITLE_SX}>Secciones</Typography>
                  <Box sx={{ overflowX: 'auto' }}>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>Seccion</TableCell>
                          <TableCell align="right">Importe</TableCell>
                          <TableCell align="right">Peso (kg)</TableCell>
                          <TableCell align="right">Unidades</TableCell>
                          <TableCell align="right">Registros</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {sectionList.map((row, idx) => (
                          <TableRow
                            key={`${row.label || 'sin'}-${idx}`}
                            hover
                            selected={selectedSection === row.label}
                            onClick={() => handleSectionClick(row.label)}
                            sx={{ cursor: 'pointer' }}
                          >
                            <TableCell>{row.label || '(sin nombre)'}</TableCell>
                            <TableCell align="right">$ {formatImporte(row.imp || 0)}</TableCell>
                            <TableCell align="right">{hasQuantity(row.peso) ? number(row.peso, 2) : '-'}</TableCell>
                            <TableCell align="right">{hasQuantity(row.units) ? number(row.units, 0) : '-'}</TableCell>
                            <TableCell align="right">{formatInteger(row.count || 0)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </Box>
                </CardContent>
              </Card>
            </Box>
          )}

          {topProducts.length > 0 && (
            <Box sx={{ mt: 3 }}>
              <Card>
                <CardContent>
                  <Typography variant="h6" sx={CARD_TITLE_SX}>Top productos</Typography>
                  <Typography variant="body2" color="text.secondary">{selectedSection ? `Seccion ${selectedSection}` : `General (año ${datasetYear})`}</Typography>
                  <Divider sx={{ mb: 2, opacity: 0.2 }} />
                  <Stack spacing={1.5}>
                    {topProducts.map((prod, idx) => (
                      <Box
                        key={`${prod.label}-${idx}`}
                        onClick={() => handleProductClick(prod.label)}
                        sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', p: 1.5, borderRadius: 2, cursor: 'pointer', '&:hover': { backgroundColor: 'rgba(255,255,255,0.05)' } }}
                      >
                        <Stack direction="row" spacing={2} alignItems="center">
                          <Box sx={{ width: 40, height: 40, borderRadius: '50%', backgroundColor: productPalette[idx % productPalette.length], display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#0a0a0a', fontWeight: 700 }}>{prod.label?.slice(0, 2)?.toUpperCase() || '--'}</Box>
                          <Box>
                            <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>{prod.label || '(sin nombre)'}</Typography>
                            <Typography variant="body2" color="text.secondary">{formatMeasures(prod.peso, prod.units)}</Typography>
                          </Box>
                        </Stack>
                        <Stack direction="row" spacing={1} alignItems="center">
                          <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>$ {formatImporte(prod.imp)}</Typography>
                          <ChevronRightIcon fontSize="small" />
                        </Stack>
                      </Box>
                    ))}
                  </Stack>
                </CardContent>
              </Card>
            </Box>
          )}
            </>
          )}

          <Dialog open={trendOpen} onClose={closeTrend} fullWidth maxWidth="md">
            <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Typography component="div" variant="h6">Detalle diario: {selectedProduct || 'Producto'}</Typography>
              <IconButton size="small" onClick={closeTrend}>
                <CloseIcon fontSize="small" />
              </IconButton>
            </DialogTitle>
            <DialogContent>
              {trendLoading && <LinearProgress sx={{ mb: 2 }} />}
              {trendError && <Alert severity="error" sx={{ mb: 2 }}>{trendError}</Alert>}
              {!trendLoading && !trendError && productTrend && (
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mb: 2 }}>
                  <Chip label={`Importe total: $ ${formatImporte(trendTotals.imp)}`} />
                  {hasQuantity(trendTotals.peso) && <Chip label={`Peso: ${number(trendTotals.peso, 2)} kg`} />}
                  {hasQuantity(trendTotals.units) && <Chip label={`Unidades: ${number(trendTotals.units, 0)}`} />}
                </Stack>
              )}
              {!trendLoading && !trendError && trendChartData && (
                <Box sx={{ width: '100%', height: 360 }}>
                  <Bar data={trendChartData} options={trendOptions} />
                </Box>
              )}
            </DialogContent>
          </Dialog>        </Box>
      )}
      </Box>
    </Box>
  )
}




































