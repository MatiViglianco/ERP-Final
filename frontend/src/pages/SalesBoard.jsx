import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  LinearProgress,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
  Divider,
} from '@mui/material'
import useMediaQuery from '@mui/material/useMediaQuery'
import { useTheme } from '@mui/material/styles'
import { useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

const API_SALES_DAILY = 'http://localhost:8000/api/sales/daily/'
const API_SALES_MANUAL = 'http://localhost:8000/api/sales/manual/'
const YEAR_FILTER_STORAGE_KEY = 'viglianco_sales_year_filter'
const MONTH_FILTER_STORAGE_KEY = 'viglianco_sales_month_filter'

const columnConfig = [
  { key: 'date_label', label: 'Fecha', align: 'left', type: 'meta' },
  { key: 'ventas', label: 'Ventas', align: 'right', type: 'auto' },
  { key: 'anulado', label: 'Anulado', align: 'right', type: 'manual' },
  { key: 'fcInicial', label: 'FC Inicial', align: 'right', type: 'auto' },
  { key: 'pagos', label: 'Pagos', align: 'right', type: 'manual' },
  { key: 'debitos', label: 'Débitos', align: 'right', type: 'manual' },
  { key: 'gastos', label: 'Gastos', align: 'right', type: 'manual' },
  { key: 'vales', label: 'Vales', align: 'right', type: 'manual' },
  { key: 'fcFinal', label: 'FC Final', align: 'right', type: 'manual' },
  { key: 'total', label: 'Total', align: 'right', type: 'auto_total' },
]

const columnColors = {
  ventas: 'rgba(129, 199, 132, 0.35)',
  anulado: 'rgba(244, 143, 177, 0.35)',
  fcInicial: 'rgba(255, 241, 118, 0.35)',
  pagos: 'rgba(129, 212, 250, 0.35)',
  debitos: 'rgba(206, 147, 216, 0.35)',
  gastos: 'rgba(255, 138, 128, 0.35)',
  vales: 'rgba(255, 213, 79, 0.35)',
  fcFinal: 'rgba(255, 241, 118, 0.35)',
  total: 'rgba(165, 214, 167, 0.45)',
}

const formatCurrency = (value) => `$ ${Number(value || 0).toLocaleString('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`

const formatInputValue = (value) => {
  if (value === null || value === undefined) return ''
  const numberValue = Number(value)
  if (Number.isNaN(numberValue)) return ''
  return numberValue.toLocaleString('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

const sanitizeNumber = (value) => {
  if (value === '' || value === null || value === undefined) return 0
  const normalized = value.toString().replace(/\./g, '').replace(/,/g, '.').replace(/[^\d.-]/g, '')
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : 0
}

const getRowKey = (row) => row.date || row.date_label || row.batch_id

const buildFcInicialData = (rows, manualMap) => {
  if (!rows.length) return { map: {}, baseKey: null }
  const sorted = [...rows].sort((a, b) => {
    const dateA = a.date ? new Date(a.date).getTime() : 0
    const dateB = b.date ? new Date(b.date).getTime() : 0
    return dateA - dateB
  })
  const map = {}
  let previousFcFinal = 0
  let firstKey = null
  sorted.forEach((row, idx) => {
    const rowKey = getRowKey(row)
    const manualRow = manualMap[rowKey] || {}
    if (idx === 0) {
      const manualValue = manualRow.fcInicial !== undefined ? sanitizeNumber(manualRow.fcInicial) : sanitizeNumber(row.fcInicialManual)
      map[rowKey] = manualValue
      firstKey = rowKey
    } else {
      map[rowKey] = previousFcFinal
    }
    const manualFcFinal = manualRow.fcFinal !== undefined ? sanitizeNumber(manualRow.fcFinal) : sanitizeNumber(row.fcFinal)
    previousFcFinal = manualFcFinal
  })
  return { map, baseKey: firstKey }
}

const getStoredFilter = (key) => {
  if (typeof window === 'undefined') return ''
  return window.localStorage.getItem(key) || ''
}

export default function SalesBoard() {
  const { authFetch } = useAuth()
  const [searchParams] = useSearchParams()
  const batchId = searchParams.get('batch_id') || ''
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('md'))

  const initialYearFilter = getStoredFilter(YEAR_FILTER_STORAGE_KEY)
  const initialMonthFilter = getStoredFilter(MONTH_FILTER_STORAGE_KEY)

  const [sales, setSales] = useState([])
  const [manualData, setManualData] = useState({})
  const [meta, setMeta] = useState({ year: '', month_label: '', dataset: null })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [yearFilter, setYearFilter] = useState(initialYearFilter)
  const [monthFilter, setMonthFilter] = useState(initialMonthFilter)
  const [availableYears, setAvailableYears] = useState([])
  const [availableMonths, setAvailableMonths] = useState([])
  const [weekSummary, setWeekSummary] = useState([])
  const [stats, setStats] = useState(null)
  const filterLockRef = useRef({ year: Boolean(initialYearFilter), month: Boolean(initialMonthFilter) })

  useEffect(() => {
    if (typeof window !== 'undefined') {
      if (yearFilter) {
        window.localStorage.setItem(YEAR_FILTER_STORAGE_KEY, yearFilter)
      } else {
        window.localStorage.removeItem(YEAR_FILTER_STORAGE_KEY)
      }
    }
  }, [yearFilter])

  useEffect(() => {
    if (typeof window !== 'undefined') {
      if (monthFilter) {
        window.localStorage.setItem(MONTH_FILTER_STORAGE_KEY, monthFilter)
      } else {
        window.localStorage.removeItem(MONTH_FILTER_STORAGE_KEY)
      }
    }
  }, [monthFilter])

  const fetchSales = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams()
      if (batchId) params.set('batch_id', batchId)
      if (yearFilter) params.set('year', yearFilter)
      if (monthFilter) params.set('month', monthFilter)
      const query = params.toString()
      const resp = await authFetch(query ? `${API_SALES_DAILY}?${query}` : API_SALES_DAILY)
      const data = await resp.json()
      if (!resp.ok) throw new Error(data?.detail || 'No se pudieron cargar las ventas.')
      const nextSales = data?.results || []
      const manualMap = {}
      nextSales.forEach((row) => {
        const rowKey = getRowKey(row)
        manualMap[rowKey] = {
          anulado: formatInputValue(row.anulado),
          pagos: formatInputValue(row.pagos),
          debitos: formatInputValue(row.debitos),
          gastos: formatInputValue(row.gastos),
          vales: formatInputValue(row.vales),
          fcFinal: formatInputValue(row.fcFinal),
          fcInicial: formatInputValue(row.fcInicialManual),
        }
      })
      setManualData(manualMap)
      setSales(nextSales)
      const availableYearStrings = (data?.filters?.available_years || []).map((year) => (year != null ? year.toString() : ''))
      const availableMonthStrings = (data?.filters?.available_months || []).map((month) => (month != null ? month.toString() : ''))

      let normalizedYear = yearFilter || ''
      if (!filterLockRef.current.year) {
        normalizedYear = data?.filters?.year ? data.filters.year.toString() : normalizedYear
      }
      if (!normalizedYear && availableYearStrings.length) {
        normalizedYear = availableYearStrings[availableYearStrings.length - 1]
      }
      if (normalizedYear && !availableYearStrings.includes(normalizedYear)) {
        normalizedYear = availableYearStrings[availableYearStrings.length - 1] || ''
        filterLockRef.current.year = false
      }
      setYearFilter(normalizedYear)

      let normalizedMonth = monthFilter || ''
      if (!filterLockRef.current.month) {
        normalizedMonth = ''
      }
      if (normalizedMonth && !availableMonthStrings.includes(normalizedMonth)) {
        normalizedMonth = ''
        filterLockRef.current.month = false
      }
      setMonthFilter(normalizedMonth)

      setMeta({
        year: normalizedYear,
        month_label: data?.filters?.month_label || '',
        dataset: data?.dataset || null,
      })
      setAvailableYears(availableYearStrings)
      setAvailableMonths(availableMonthStrings)
      setWeekSummary(data?.week_summary || [])
      setStats(data?.stats || null)
    } catch (err) {
      setError(err.message)
      setSales([])
      setManualData({})
    } finally {
      setLoading(false)
    }
  }, [authFetch, batchId, yearFilter, monthFilter])

  useEffect(() => {
    fetchSales()
  }, [fetchSales])

  const { map: fcInicialByRow, baseKey: baseRowKey } = useMemo(
    () => buildFcInicialData(sales, manualData),
    [sales, manualData],
  )

  const computeRowTotal = useCallback((row, manualRow = {}, overrideFcInicial) => {
    const rowKey = getRowKey(row)
    const ventas = Number(row.ventas || 0)
    const fcInicial = overrideFcInicial ?? fcInicialByRow[rowKey] ?? 0
    const pagos = sanitizeNumber(manualRow.pagos ?? row.pagos)
    const fcFinal = sanitizeNumber(manualRow.fcFinal ?? row.fcFinal)
    const anulado = sanitizeNumber(manualRow.anulado ?? row.anulado)
    const debitos = sanitizeNumber(manualRow.debitos ?? row.debitos)
    const gastos = sanitizeNumber(manualRow.gastos ?? row.gastos)
    const vales = sanitizeNumber(manualRow.vales ?? row.vales)
    return ventas + fcInicial + pagos - fcFinal - anulado - debitos - gastos - vales
  }, [fcInicialByRow])

  const saveManualEntry = useCallback(async (row, rowValues) => {
    if (!row.batch_id || !row.date) return
    const rowKey = getRowKey(row)
    const overrideMap = { ...manualData, [rowKey]: rowValues }
    const { map: overrideFcMap, baseKey } = buildFcInicialData(sales, overrideMap)
    const fcInicialValue = overrideFcMap[rowKey] ?? 0
    const payload = {
      batch_id: row.batch_id,
      date: row.date,
      values: {
        anulado: sanitizeNumber(rowValues.anulado),
        pagos: sanitizeNumber(rowValues.pagos),
        debitos: sanitizeNumber(rowValues.debitos),
        gastos: sanitizeNumber(rowValues.gastos),
        vales: sanitizeNumber(rowValues.vales),
        fc_final: sanitizeNumber(rowValues.fcFinal),
        total: computeRowTotal(row, rowValues, fcInicialValue),
      },
    }
    if (rowKey === baseKey) {
      payload.values.fc_inicial = sanitizeNumber(rowValues.fcInicial)
    }
    try {
      await authFetch(API_SALES_MANUAL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
    } catch (err) {
      console.error('No se pudo guardar la fila', err)
    }
  }, [authFetch, manualData, sales, computeRowTotal])

  const handleManualChange = (row, field, value) => {
    const rowKey = getRowKey(row)
    const nextRow = { ...(manualData[rowKey] || {}), [field]: value }
    setManualData((prev) => ({ ...prev, [rowKey]: nextRow }))
    saveManualEntry(row, nextRow)
  }

  const handleYearChange = (event) => {
    filterLockRef.current.year = true
    setYearFilter(event.target.value)
  }

  const handleMonthChange = (event) => {
    filterLockRef.current.month = true
    setMonthFilter(event.target.value)
  }

  const renderManualInput = (row, columnKey, value, { fullWidth = false } = {}) => (
    <TextField
      size="small"
      variant="outlined"
      value={value}
      placeholder="$ 0"
      onChange={(e) => handleManualChange(row, columnKey, e.target.value)}
      fullWidth={fullWidth}
      InputProps={{
        sx: {
          fontWeight: 600,
          color: '#fff',
          '& input': { textAlign: 'right' },
        },
      }}
    />
  )

  const renderMobileField = (column, row, manualRow, rowKey) => {
    if (column.key === 'ventas') {
      return (
        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
          {formatCurrency(row.ventas)}
        </Typography>
      )
    }
    if (column.key === 'fcInicial') {
      if (rowKey === baseRowKey) {
        const baseValue = manualRow[column.key] ?? ''
        return renderManualInput(row, column.key, baseValue, { fullWidth: true })
      }
      return (
        <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
          {formatCurrency(fcInicialByRow[rowKey] || 0)}
        </Typography>
      )
    }
    if (column.key === 'total') {
      return (
        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
          {formatCurrency(computeRowTotal(row, manualRow))}
        </Typography>
      )
    }
    if (column.type === 'manual') {
      const value = manualRow[column.key] ?? ''
      return renderManualInput(row, column.key, value, { fullWidth: true })
    }
    if (column.type === 'auto') {
      return (
        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
          {formatCurrency(row[column.key])}
        </Typography>
      )
    }
    return (
      <Typography variant="body2" sx={{ fontWeight: 500 }}>
        {row[column.key]}
      </Typography>
    )
  }

  const tableRows = useMemo(() => {
    const sorted = [...sales]
    sorted.sort((a, b) => {
      const dateA = a.date ? new Date(a.date).getTime() : 0
      const dateB = b.date ? new Date(b.date).getTime() : 0
      return dateB - dateA
    })
    return sorted
  }, [sales])

  const yearSelectValue = availableYears.includes(yearFilter) ? yearFilter : ''
  const monthSelectValue = monthFilter && availableMonths.includes(monthFilter) ? monthFilter : ''

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <Typography variant="h4" sx={{ fontWeight: 700 }}>Ventas diarias</Typography>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        <TextField
          select
          label="Año"
          size="small"
          value={yearSelectValue}
          onChange={handleYearChange}
          sx={{ minWidth: 140 }}
        >
          {availableYears.map((year) => (
            <MenuItem key={year} value={year}>{year}</MenuItem>
          ))}
        </TextField>
        <TextField
          select
          label="Mes"
          size="small"
          value={monthSelectValue}
          onChange={handleMonthChange}
          sx={{ minWidth: 160 }}
        >
          <MenuItem value="">Todos los meses</MenuItem>
          {availableMonths.map((month) => (
            <MenuItem key={month} value={month}>{month}</MenuItem>
          ))}
        </TextField>
      </Stack>
      <Card sx={{ background: 'rgba(13,13,20,0.85)', borderRadius: 3, border: '1px solid rgba(255,255,255,0.08)' }}>
        <CardContent>
          <Stack direction="row" spacing={2} sx={{ mb: 2, flexWrap: 'wrap' }}>
            {meta.year ? <Chip label={`Año: ${meta.year}`} color="success" variant="outlined" /> : null}
            {meta.month_label ? <Chip label={`Mes: ${meta.month_label}`} color="info" variant="outlined" /> : null}
            {meta.dataset?.dataset_label ? (
              <Chip label={`Dataset: ${meta.dataset.dataset_label}`} variant="outlined" />
            ) : null}
            {meta.dataset?.source ? (
              <Chip label={`Fuente: ${meta.dataset.source}`} variant="outlined" color="secondary" />
            ) : null}
          </Stack>
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          {loading && <LinearProgress sx={{ mb: 2 }} />}
          {!loading && !tableRows.length && !error && (
            <Typography variant="body2" color="text.secondary">No hay ventas registradas para el periodo.</Typography>
          )}
          {tableRows.length ? (
            isMobile ? (
              <Stack spacing={2}>
                {tableRows.map((row) => {
                  const rowKey = getRowKey(row)
                  const manualRow = manualData[rowKey] || {}
                  return (
                    <Box
                      key={`${row.batch_id || row.date}-mobile`}
                      sx={{
                        p: 2,
                        borderRadius: 3,
                        border: '1px solid rgba(255,255,255,0.08)',
                        backgroundColor: 'rgba(8,8,12,0.9)',
                      }}
                    >
                      <Stack spacing={0.5}>
                        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{row.date_label}</Typography>
                        <Typography variant="caption" color="text.secondary">{row.dataset_label || row.date}</Typography>
                      </Stack>
                      <Divider sx={{ my: 1.5, borderColor: 'rgba(255,255,255,0.08)' }} />
                      <Box
                        sx={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
                          gap: 1.2,
                        }}
                      >
                        {columnConfig.filter((column) => column.key !== 'date_label').map((column) => (
                          <Box
                            key={`${rowKey}-${column.key}`}
                            sx={{
                              p: 1.2,
                              borderRadius: 2,
                              backgroundColor: columnColors[column.key] || 'rgba(255,255,255,0.04)',
                              display: 'flex',
                              flexDirection: 'column',
                              gap: 0.5,
                            }}
                          >
                            <Typography variant="caption" sx={{ textTransform: 'uppercase', color: 'rgba(255,255,255,0.85)', fontWeight: 600 }}>
                              {column.label}
                            </Typography>
                            {renderMobileField(column, row, manualRow, rowKey)}
                          </Box>
                        ))}
                      </Box>
                    </Box>
                  )
                })}
              </Stack>
            ) : (
              <Table size="small" sx={{ '& td, & th': { borderColor: 'rgba(255,255,255,0.08)' } }}>
                <TableHead>
                  <TableRow>
                    {columnConfig.map((column) => (
                      <TableCell key={column.key} align={column.align || 'right'} sx={{ fontWeight: 700, color: '#fff' }}>
                        {column.label}
                      </TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {tableRows.map((row) => {
                    const rowKey = getRowKey(row)
                    const manualRow = manualData[rowKey] || {}
                    return (
                      <TableRow key={`${row.batch_id || row.date}`}>
                        {columnConfig.map((column) => {
                          if (column.key === 'date_label') {
                            return (
                              <TableCell key={column.key} align={column.align || 'left'}>
                                <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>{row.date_label}</Typography>
                                {row.dataset_label ? (
                                  <Typography variant="caption" color="text.secondary">{row.dataset_label}</Typography>
                                ) : null}
                              </TableCell>
                            )
                          }
                          if (column.key === 'ventas') {
                            return (
                              <TableCell key={column.key} align={column.align || 'right'} sx={{ fontWeight: 600, backgroundColor: columnColors[column.key] }}>
                                {formatCurrency(row.ventas)}
                              </TableCell>
                            )
                          }
                          if (column.key === 'fcInicial') {
                            if (rowKey === baseRowKey) {
                              const baseValue = manualRow[column.key] ?? ''
                              return (
                                <TableCell key={column.key} align={column.align || 'right'} sx={{ backgroundColor: columnColors[column.key] }}>
                                  {renderManualInput(row, column.key, baseValue)}
                                </TableCell>
                              )
                            }
                            return (
                              <TableCell key={column.key} align={column.align || 'right'} sx={{ backgroundColor: columnColors[column.key], fontWeight: 600 }}>
                                {formatCurrency(fcInicialByRow[rowKey] || 0)}
                              </TableCell>
                            )
                          }
                          if (column.key === 'total') {
                            return (
                              <TableCell key={column.key} align={column.align || 'right'} sx={{ backgroundColor: columnColors[column.key], fontWeight: 700 }}>
                                {formatCurrency(computeRowTotal(row, manualRow))}
                              </TableCell>
                            )
                          }
                          const value = manualRow[column.key] ?? ''
                          return (
                            <TableCell key={column.key} align={column.align || 'right'} sx={{ backgroundColor: columnColors[column.key] }}>
                              {renderManualInput(row, column.key, value)}
                            </TableCell>
                          )
                        })}
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            )
          ) : null}
        </CardContent>
      </Card>
      {stats ? (
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
          <Card sx={{ flex: 1, background: 'rgba(9,12,18,0.9)' }}>
            <CardContent>
              <Typography variant="subtitle2" sx={{ color: 'rgba(255,255,255,0.7)' }}>Total periodo</Typography>
              <Typography variant="h5" sx={{ fontWeight: 700 }}>{formatCurrency(stats.total_sales)}</Typography>
            </CardContent>
          </Card>
          <Card sx={{ flex: 1, background: 'rgba(9,12,18,0.9)' }}>
            <CardContent>
              <Typography variant="subtitle2" sx={{ color: 'rgba(255,255,255,0.7)' }}>Promedio diario</Typography>
              <Typography variant="h5" sx={{ fontWeight: 700 }}>{formatCurrency(stats.average_daily)}</Typography>
            </CardContent>
          </Card>
          {stats.max_day ? (
            <Card sx={{ flex: 1, background: 'rgba(9,12,18,0.9)' }}>
              <CardContent>
                <Typography variant="subtitle2" sx={{ color: 'rgba(255,255,255,0.7)' }}>Mejor día</Typography>
                <Typography variant="body2">{stats.max_day.label}</Typography>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>{formatCurrency(stats.max_day.total)}</Typography>
              </CardContent>
            </Card>
          ) : null}
        </Stack>
      ) : null}
      {weekSummary.length ? (
        <Card sx={{ background: 'rgba(13,13,20,0.85)', borderRadius: 3, border: '1px solid rgba(255,255,255,0.08)' }}>
          <CardContent>
            <Typography variant="subtitle2" sx={{ mb: 2, color: 'rgba(255,255,255,0.7)' }}>Resumen semanal (lunes a lunes)</Typography>
            <Table size="small" sx={{ '& td, & th': { borderColor: 'rgba(255,255,255,0.08)' } }}>
              <TableHead>
                <TableRow>
                  <TableCell>Semana</TableCell>
                  <TableCell>Desde</TableCell>
                  <TableCell>Hasta</TableCell>
                  <TableCell align="right">Total</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {weekSummary.map((week) => (
                  <TableRow key={`${week.year}-${week.week}`}>
                    <TableCell>{`${week.week} / ${week.year}`}</TableCell>
                    <TableCell>{week.start}</TableCell>
                    <TableCell>{week.end}</TableCell>
                    <TableCell align="right">{formatCurrency(week.total)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : null}
    </Box>
  )
}
