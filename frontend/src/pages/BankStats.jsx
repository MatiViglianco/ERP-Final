
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Box, Card, CardContent, Typography, FormControl, InputLabel, Select, MenuItem, TextField, Stack, Alert, LinearProgress, Dialog, DialogTitle, DialogContent, IconButton, Divider, Table, TableHead, TableRow, TableCell, TableBody, Avatar } from '@mui/material'
import { Chart, CategoryScale, LinearScale, BarElement, PointElement, LineElement, ArcElement, Tooltip, Legend, Filler } from 'chart.js'
import { Bar, Line, Doughnut } from 'react-chartjs-2'
import CloseIcon from '@mui/icons-material/Close'
import { useAuth } from '../context/AuthContext.jsx'
import { API_BASE } from '../config'
const donutCenterPlugin = {
  id: 'donutCenter',
  afterDraw(chart, _args, pluginOptions) {
    const value = pluginOptions?.value
    if (!value) return
    const { ctx, chartArea: { left, right, top, bottom } } = chart
    const centerX = (left + right) / 2
    const centerY = (top + bottom) / 2
    ctx.save()
    ctx.fillStyle = pluginOptions?.color || '#fff'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    if (pluginOptions?.title) {
      ctx.font = pluginOptions?.titleFont || '600 14px "Inter", "Roboto", sans-serif'
      ctx.fillText(pluginOptions.title, centerX, centerY - 14)
      ctx.font = pluginOptions?.valueFont || '700 24px "Inter", "Roboto", sans-serif'
      ctx.fillText(value, centerX, centerY + 12)
    } else {
      ctx.font = pluginOptions?.valueFont || '700 24px "Inter", "Roboto", sans-serif'
      ctx.fillText(value, centerX, centerY)
    }
    ctx.restore()
  }
}
Chart.register(CategoryScale, LinearScale, BarElement, PointElement, LineElement, ArcElement, Tooltip, Legend, Filler, donutCenterPlugin)

const API_BANK_STATS = `${API_BASE}/bank/stats/`
const INCOME_COLORS = ['#50fa7b', '#38d9a9', '#4dabf7', '#ffd43b', '#845ef7', '#ff922b']
const EXPENSE_COLORS = ['#ff6b6b', '#ff8787', '#ff9f43', '#ffa8a8', '#f783ac', '#ff4d6d']

function toIso(date) {
  return date.toISOString().split('T')[0]
}

function setMonthStart(value) {
  if (!value) return ''
  const [year, month] = value.split('-')
  return `${year}-${month}-01`
}

function setMonthEnd(value) {
  if (!value) return ''
  const [year, month] = value.split('-')
  const lastDay = new Date(Number(year), Number(month), 0).getDate()
  return `${year}-${month}-${String(lastDay).padStart(2, '0')}`
}

function formatCurrency(value) {
  return (Number(value) || 0).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function truncateLabel(label, max = 28) {
  if (!label) return ''
  return label.length > max ? `${label.slice(0, max - 3)}...` : label
}

function formatDateLabel(dateStr) {
  if (!dateStr) return '-'
  const [year, month, day] = dateStr.split('-')
  return `${day}/${month}/${year}`
}

function formatDateHeading(dateStr) {
  if (!dateStr) return 'Sin fecha'
  const date = new Date(dateStr)
  return date.toLocaleDateString('es-AR', { day: 'numeric', month: 'long', year: 'numeric' })
}

export default function BankStatsPage() {
  const today = useMemo(() => new Date(), [])
  const currentYear = useMemo(() => today.getFullYear(), [today])
  const todayIso = useMemo(() => toIso(today), [today])

  const [bank, setBank] = useState('santander')
  const [monthPreset, setMonthPreset] = useState('year')
  const [availableYears, setAvailableYears] = useState([])
  const [selectedYear, setSelectedYear] = useState(currentYear.toString())
  const [fechaDesde, setFechaDesde] = useState(() => toIso(new Date(currentYear, 0, 1)))
  const [fechaHasta, setFechaHasta] = useState(todayIso)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [stats, setStats] = useState(null)
  const monthFieldSx = useMemo(() => ({
    '& label': {
      color: '#fff'
    },
    '& .MuiOutlinedInput-root': {
      color: '#fff',
      '& fieldset': {
        borderColor: 'rgba(255,255,255,0.25)'
      },
      '&:hover fieldset': {
        borderColor: '#fff'
      },
      '&.Mui-focused fieldset': {
        borderColor: '#fff'
      }
    },
    '& .MuiInputBase-input': {
      color: '#fff',
      caretColor: '#fff'
    },
    '& input::-webkit-calendar-picker-indicator': {
      filter: 'invert(1)',
      opacity: 0.9,
      cursor: 'pointer'
    },
    '& input::-moz-focus-inner': {
      border: 0
    },
    '& input::-moz-calendar-picker-indicator': {
      filter: 'invert(1)',
      opacity: 0.9,
      cursor: 'pointer'
    }
  }), [])
  const monthLabelProps = useMemo(() => ({
    shrink: true,
    sx: { color: '#fff', '&.Mui-focused': { color: '#fff' } }
  }), [])
  const outlinedSelectSx = useMemo(() => ({
    color: '#fff',
    '& .MuiOutlinedInput-notchedOutline': {
      borderColor: 'rgba(255,255,255,0.25)'
    },
    '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
      borderColor: '#fff'
    },
    '&:hover .MuiOutlinedInput-notchedOutline': {
      borderColor: '#fff'
    },
    '& .MuiSvgIcon-root': {
      color: '#fff'
    }
  }), [])
  const yearOptions = useMemo(() => (
    availableYears.length ? availableYears : [currentYear.toString()]
  ), [availableYears, currentYear])
  const normalizedYear = useMemo(() => (
    yearOptions.includes(selectedYear) ? selectedYear : yearOptions[yearOptions.length - 1]
  ), [yearOptions, selectedYear])
  const selectedYearNumber = useMemo(() => {
    const parsed = Number(normalizedYear)
    return Number.isFinite(parsed) ? parsed : currentYear
  }, [normalizedYear, currentYear])
  const startOfSelectedYearIso = useMemo(
    () => toIso(new Date(selectedYearNumber, 0, 1)),
    [selectedYearNumber],
  )
  const endOfSelectedYearIso = useMemo(() => {
    if (selectedYearNumber === currentYear) return todayIso
    return toIso(new Date(selectedYearNumber, 11, 31))
  }, [selectedYearNumber, currentYear, todayIso])
  const isCustomRange = monthPreset === 'custom'
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailConcept, setDetailConcept] = useState('')
  const [detailMode, setDetailMode] = useState('ingresos')
  const [detailItems, setDetailItems] = useState([])
  const { authFetch } = useAuth()
  const monthOptions = useMemo(() => {
    const months = []
    for (let monthIndex = 0; monthIndex < 12; monthIndex += 1) {
      const date = new Date(selectedYearNumber, monthIndex, 1)
      const value = `${selectedYearNumber}-${String(monthIndex + 1).padStart(2, '0')}`
      const rawLabel = date.toLocaleDateString('es-AR', { month: 'long' })
      months.push({
        value,
        label: rawLabel.charAt(0).toUpperCase() + rawLabel.slice(1)
      })
    }
    return months
  }, [selectedYearNumber])
  const detailGroups = useMemo(() => {
    if (!detailItems.length) return []
    const groups = new Map()
    detailItems.forEach((item) => {
      const key = item.date || 'sin-fecha'
      if (!groups.has(key)) {
        groups.set(key, {
          key,
          label: formatDateHeading(item.date),
          items: [],
        })
      }
      groups.get(key).items.push(item)
    })
    return Array.from(groups.values())
  }, [detailItems])

  useEffect(() => {
    if (normalizedYear !== selectedYear) {
      setSelectedYear(normalizedYear)
    }
  }, [normalizedYear, selectedYear])

  useEffect(() => {
    if (monthPreset === 'custom' || monthPreset === 'year') return
    const match = monthPreset.match(/^\d{4}-(\d{2})$/)
    if (!match) return
    const nextPreset = `${selectedYearNumber}-${match[1]}`
    if (nextPreset !== monthPreset) {
      setMonthPreset(nextPreset)
    }
  }, [monthPreset, selectedYearNumber])

  const fetchStats = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams()
      if (bank) params.set('bank', bank)
      if (fechaDesde) params.set('fecha_desde', fechaDesde)
      if (fechaHasta) params.set('fecha_hasta', fechaHasta)
      const resp = await authFetch(`${API_BANK_STATS}?${params.toString()}`)
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudieron obtener los datos')
      setStats(data)
      const availableYearStrings = (data?.filters?.available_years || [])
        .map((year) => (year != null ? year.toString() : ''))
        .filter(Boolean)
      setAvailableYears(availableYearStrings)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [bank, fechaDesde, fechaHasta, authFetch])

  useEffect(() => {
    fetchStats()
  }, [fetchStats])

  useEffect(() => {
    if (monthPreset === 'year') {
      setFechaDesde((prev) => (prev === startOfSelectedYearIso ? prev : startOfSelectedYearIso))
      setFechaHasta((prev) => (prev === endOfSelectedYearIso ? prev : endOfSelectedYearIso))
      return
    }
    if (monthPreset !== 'custom') {
      const start = setMonthStart(monthPreset)
      const end = setMonthEnd(monthPreset)
      setFechaDesde((prev) => (prev === start ? prev : start))
      setFechaHasta((prev) => (prev === end ? prev : end))
    }
  }, [monthPreset, startOfSelectedYearIso, endOfSelectedYearIso])

  const buildBarData = (dataset, label, color) => {
    if (!dataset?.length) return null
    return {
      labels: dataset.map((item) => item.label),
      datasets: [{
        label,
        data: dataset.map((item) => item.total),
        backgroundColor: color,
        borderRadius: 8,
      }]
    }
  }

  const conceptEntries = stats?.concept_entries || {}

  const combinedConcepts = useMemo(() => {
    if (!stats) return []
    const incomes = (stats.ingresos_por_concepto || []).map((item, idx) => ({ ...item, type: 'Ingreso', color: INCOME_COLORS[idx % INCOME_COLORS.length] }))
    const expenses = (stats.egresos_por_concepto || []).map((item, idx) => ({ ...item, type: 'Egreso', color: EXPENSE_COLORS[idx % EXPENSE_COLORS.length] }))
    return [...incomes, ...expenses].sort((a, b) => (b.total || 0) - (a.total || 0))
  }, [stats])

  const topIngresos = useMemo(() => (stats?.ingresos_por_concepto || []).slice(0, 6).map((item, idx) => ({ ...item, color: INCOME_COLORS[idx % INCOME_COLORS.length] })), [stats])
  const topEgresos = useMemo(() => (stats?.egresos_por_concepto || []).slice(0, 6).map((item, idx) => ({ ...item, color: EXPENSE_COLORS[idx % EXPENSE_COLORS.length] })), [stats])

  const donutIngresos = useMemo(() => {
    if (!topIngresos.length) return null
    return {
      labels: topIngresos.map((slice) => truncateLabel(slice.label)),
      datasets: [{
        data: topIngresos.map((slice) => slice.total),
        backgroundColor: topIngresos.map((slice) => slice.color),
        borderWidth: 0,
      }]
    }
  }, [topIngresos])

  const donutEgresos = useMemo(() => {
    if (!topEgresos.length) return null
    return {
      labels: topEgresos.map((slice) => truncateLabel(slice.label)),
      datasets: [{
        data: topEgresos.map((slice) => slice.total),
        backgroundColor: topEgresos.map((slice) => slice.color),
        borderWidth: 0,
      }]
    }
  }, [topEgresos])

  const tableData = useMemo(() => combinedConcepts.slice(0, 20), [combinedConcepts])

  const openDetail = useCallback((mode, concept) => {
    if (!conceptEntries[mode]?.[concept]) return
    setDetailMode(mode)
    setDetailConcept(concept)
    setDetailItems(conceptEntries[mode][concept])
    setDetailOpen(true)
  }, [conceptEntries])

  const closeDetail = () => {
    setDetailOpen(false)
    setDetailItems([])
    setDetailConcept('')
  }

  const donutOptions = useCallback((mode) => {
    const total = mode === 'ingresos' ? (stats?.totals.ingresos || 0) : (stats?.totals.egresos || 0)
    const formatted = `$ ${total.toLocaleString('es-AR', { maximumFractionDigits: 0 })}`
    return {
      animation: { animateRotate: false },
      plugins: {
        legend: { position: 'bottom', labels: { color: '#ccc', boxWidth: 12 } },
        donutCenter: {
          title: 'Total',
          value: formatted,
        },
      },
      maintainAspectRatio: false,
      cutout: '65%',
      onClick: (_evt, elements) => {
        if (!elements?.length) return
        const index = elements[0].index
        const concept = mode === 'ingresos' ? topIngresos[index]?.label : topEgresos[index]?.label
        if (concept) openDetail(mode, concept)
      }
    }
  }, [openDetail, stats, topEgresos, topIngresos])

  const serieDiaria = useMemo(() => {
    if (!stats?.serie_diaria?.length) return null
    return {
      labels: stats.serie_diaria.map((item) => item.date),
      datasets: [
        {
          label: 'Ingresos',
          data: stats.serie_diaria.map((item) => item.ingresos),
          borderColor: '#66ff99',
          backgroundColor: 'rgba(102,255,153,0.2)',
          tension: 0.3,
          fill: true,
        },
        {
          label: 'Egresos',
          data: stats.serie_diaria.map((item) => item.egresos),
          borderColor: '#ff6384',
          backgroundColor: 'rgba(255,99,132,0.2)',
          tension: 0.3,
          fill: true,
        }
      ]
    }
  }, [stats])

  const renderConceptStack = (items, mode) => {
    if (!items?.length) {
      return <Typography variant="body2" color="text.secondary">Sin datos</Typography>
    }
    const maxValue = Math.max(...items.map((item) => item.total || 0), 1)
    return (
      <Stack spacing={1.5} sx={{ mt: 2 }}>
        {items.map((item, idx) => {
          const width = `${Math.max((item.total / maxValue) * 100, 4)}%`
          const color = item.color || (mode === 'ingresos' ? 'rgba(99,255,132,0.9)' : 'rgba(255,99,132,0.9)')
          return (
            <Box
              key={`${item.label}-${idx}`}
              onClick={() => openDetail(mode, item.label)}
              sx={{ p: 1.5, borderRadius: 1.5, backgroundColor: 'rgba(255,255,255,0.03)', cursor: conceptEntries[mode]?.[item.label]?.length ? 'pointer' : 'default' }}
            >
              <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2, mb: 1 }}>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>{item.label}</Typography>
                <Typography variant="body2">$ {formatCurrency(item.total)}</Typography>
              </Box>
              <Box sx={{ width: '100%', height: 6, backgroundColor: 'rgba(255,255,255,0.08)', borderRadius: 999 }}>
                <Box sx={{ width, height: '100%', borderRadius: 999, backgroundColor: color }} />
              </Box>
            </Box>
          )
        })}
      </Stack>
    )
  }

  return (
    <Box sx={{ width: '100%', display: 'flex', justifyContent: 'center', px: { xs: 1, md: 2 }, py: 4 }}>
      <Box sx={{ width: '100%', maxWidth: 1200 }}>
        <Typography variant="h4" gutterBottom>Bancos</Typography>

        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Stack spacing={2}>
              <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2}>
                <FormControl fullWidth>
                  <InputLabel id="bank-select" sx={{ color: '#fff', '&.Mui-focused': { color: '#fff' } }}>Banco</InputLabel>
                  <Select
                    labelId="bank-select"
                    label="Banco"
                    value={bank}
                    onChange={(e) => setBank(e.target.value)}
                    sx={outlinedSelectSx}
                  >
                    <MenuItem value="santander">Santander</MenuItem>
                    <MenuItem value="bancon">Bancon</MenuItem>
                  </Select>
                </FormControl>
                <FormControl fullWidth>
                  <InputLabel id="year-select" sx={{ color: '#fff', '&.Mui-focused': { color: '#fff' } }}>A\u00f1o</InputLabel>
                  <Select
                    labelId="year-select"
                    label="A\u00f1o"
                    value={normalizedYear}
                    onChange={(e) => setSelectedYear(e.target.value)}
                    sx={outlinedSelectSx}
                  >
                    {yearOptions.map((year) => (
                      <MenuItem key={year} value={year}>{year}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <FormControl fullWidth>
                  <InputLabel id="period-select" sx={{ color: '#fff', '&.Mui-focused': { color: '#fff' } }}>Periodo</InputLabel>
                  <Select
                    labelId="period-select"
                    label="Periodo"
                    value={monthPreset}
                    onChange={(e) => setMonthPreset(e.target.value)}
                    sx={outlinedSelectSx}
                  >
                    <MenuItem value="year">{`General del a\u00f1o ${normalizedYear}`}</MenuItem>
                    {monthOptions.map((month) => (
                      <MenuItem key={month.value} value={month.value}>{month.label}</MenuItem>
                    ))}
                    <MenuItem value="custom">Rango personalizado</MenuItem>
                  </Select>
                </FormControl>
              </Stack>
              {isCustomRange && (
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                  <TextField
                    type="date"
                    label="Fecha desde"
                    InputLabelProps={monthLabelProps}
                    value={fechaDesde || ''}
                    onChange={(e) => {
                      const v = e.target.value
                      if (!v) return
                      setFechaDesde(v)
                    }}
                    fullWidth
                    sx={monthFieldSx}
                  />
                  <TextField
                    type="date"
                    label="Fecha hasta"
                    InputLabelProps={monthLabelProps}
                    value={fechaHasta || ''}
                    onChange={(e) => {
                      const v = e.target.value
                      if (!v) return
                      setFechaHasta(v)
                    }}
                    fullWidth
                    sx={monthFieldSx}
                  />
                </Stack>
              )}
            </Stack>
            {loading && <LinearProgress sx={{ mt: 2 }} />}
            {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
          </CardContent>
        </Card>

        {stats && (
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(4, minmax(0, 1fr))' }, gap: 2, mb: 3 }}>
            <Card><CardContent><Typography variant="body2">Ingresos</Typography><Typography variant="h5">$ {formatCurrency(stats.totals.ingresos)}</Typography></CardContent></Card>
            <Card><CardContent><Typography variant="body2">Egresos</Typography><Typography variant="h5">$ {formatCurrency(stats.totals.egresos)}</Typography></CardContent></Card>
            <Card><CardContent><Typography variant="body2">Neto</Typography><Typography variant="h5">$ {formatCurrency(stats.totals.neto)}</Typography></CardContent></Card>
            <Card><CardContent><Typography variant="body2">Movimientos</Typography><Typography variant="h5">{stats.totals.movimientos}</Typography></CardContent></Card>
          </Box>
        )}

        {stats && (
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' }, gap: 3, mb: 3 }}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>Ingresos por concepto</Typography>
                <Box sx={{ position: 'relative', height: { xs: 280, md: 360 } }}>
                  {donutIngresos ? (
                    <Doughnut data={donutIngresos} options={donutOptions('ingresos')} />
                  ) : (
                    <Typography variant="body2" color="text.secondary">Sin ingresos</Typography>
                  )}
                </Box>
              </CardContent>
            </Card>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>Egresos por concepto</Typography>
                <Box sx={{ position: 'relative', height: { xs: 280, md: 360 } }}>
                  {donutEgresos ? (
                    <Doughnut data={donutEgresos} options={donutOptions('egresos')} />
                  ) : (
                    <Typography variant="body2" color="text.secondary">Sin egresos</Typography>
                  )}
                </Box>
              </CardContent>
            </Card>
          </Box>
        )}

        {serieDiaria && (
          <Card sx={{ mb: 3 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom>Evolucion diaria</Typography>
              <Box sx={{ width: '100%', height: 320 }}>
                <Line data={serieDiaria} options={{ responsive: true, maintainAspectRatio: false }} />
              </Box>
            </CardContent>
          </Card>
        )}

        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>Conceptos destacados</Typography>
            {tableData.length === 0 ? (
              <Typography variant="body2" color="text.secondary">Sin registros.</Typography>
            ) : (
              <Box sx={{ overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Concepto</TableCell>
                      <TableCell>Tipo</TableCell>
                      <TableCell align="right">Movimientos</TableCell>
                      <TableCell align="right">Total</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {tableData.map((row, idx) => (
                      <TableRow
                        key={`${row.label}-${idx}`}
                        hover
                        sx={{ cursor: conceptEntries[row.type === 'Ingreso' ? 'ingresos' : 'egresos']?.[row.label]?.length ? 'pointer' : 'default' }}
                        onClick={() => openDetail(row.type === 'Ingreso' ? 'ingresos' : 'egresos', row.label)}
                      >
                        <TableCell>{row.label}</TableCell>
                        <TableCell>{row.type}</TableCell>
                        <TableCell align="right">{row.count}</TableCell>
                        <TableCell align="right">$ {formatCurrency(row.total)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
            )}
          </CardContent>
        </Card>

        <Dialog open={detailOpen} onClose={closeDetail} fullWidth maxWidth="sm">
          <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Typography component="div" variant="h6">Detalle {detailMode === 'ingresos' ? 'de ingresos' : 'de egresos'}</Typography>
            <IconButton onClick={closeDetail} size="small">
              <CloseIcon fontSize="small" />
            </IconButton>
          </DialogTitle>
          <DialogContent dividers>
            <Typography variant="subtitle1" sx={{ mb: 1 }}>{detailConcept}</Typography>
            <Divider sx={{ mb: 2 }} />
            {detailGroups.length === 0 ? (
              <Typography variant="body2" color="text.secondary">Sin movimientos registrados.</Typography>
            ) : (
              <Stack spacing={2}>
                {detailGroups.map((group) => (
                  <Box key={group.key}>
                    <Typography variant="overline" color="text.secondary">{group.label}</Typography>
                    <Stack spacing={1.2}>
                      {group.items.map((item, idx) => (
                        <Box key={`${group.key}-${idx}`} sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', p: 1.5, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)' }}>
                          <Stack direction="row" spacing={2} alignItems="center">
                            <Avatar sx={{ bgcolor: detailMode === 'ingresos' ? 'rgba(80,250,123,0.15)' : 'rgba(255,107,107,0.15)', color: detailMode === 'ingresos' ? '#50fa7b' : '#ff6b6b', width: 40, height: 40, fontWeight: 700 }}>
                              {item.description?.slice(0, 2)?.toUpperCase() || '--'}
                            </Avatar>
                            <Box>
                              <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>{item.description || '(sin descripción)'}</Typography>
                              <Typography variant="caption" color="text.secondary">{formatDateLabel(item.date)}</Typography>
                            </Box>
                          </Stack>
                          <Typography variant="subtitle1" sx={{ fontWeight: 700, color: detailMode === 'ingresos' ? '#50fa7b' : '#ff6b6b' }}>
                            $ {formatCurrency(item.amount)}
                          </Typography>
                        </Box>
                      ))}
                    </Stack>
                  </Box>
                ))}
              </Stack>
            )}
          </DialogContent>
        </Dialog>
      </Box>
    </Box>
  )
}
