import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  IconButton,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Chip,
  Divider,
  LinearProgress,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Snackbar,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TablePagination,
  TextField,
  Typography,
} from '@mui/material'
import useMediaQuery from '@mui/material/useMediaQuery'
import { useTheme } from '@mui/material/styles'
import { Bar, Doughnut } from 'react-chartjs-2'
import { Chart, ArcElement, BarElement, CategoryScale, LinearScale, Tooltip, Legend } from 'chart.js'
import { useAuth } from '../context/AuthContext.jsx'
import { API_BASE } from '../config'
import EditIcon from '@mui/icons-material/Edit'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import InsightsIcon from '@mui/icons-material/Insights'

const donutCenterPlugin = {
  id: 'expensesDonutCenter',
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
      ctx.fillText(pluginOptions.title, centerX, centerY - 32)
    }
    ctx.font = pluginOptions?.valueFont || '700 28px "Inter", "Roboto", sans-serif'
    ctx.fillText(value, centerX, centerY - (pluginOptions?.subtitle ? 4 : 0))
    if (pluginOptions?.subtitle) {
      ctx.font = pluginOptions?.subtitleFont || '600 14px "Inter", "Roboto", sans-serif'
      ctx.fillText(pluginOptions.subtitle, centerX, centerY + 18)
    }
    if (pluginOptions?.detail) {
      ctx.font = pluginOptions?.detailFont || '500 13px "Inter", "Roboto", sans-serif'
      ctx.fillText(pluginOptions.detail, centerX, centerY + 36)
    }
    ctx.restore()
  },
}

Chart.register(ArcElement, BarElement, CategoryScale, LinearScale, Tooltip, Legend, donutCenterPlugin)

const paymentMethods = ['EFECTIVO', 'TRANSFERENCIA', 'CHEQUE']
const API_BANK_STATS = `${API_BASE}/bank/stats/`
const API_EXPENSES = `${API_BASE}/expenses/`
const API_EXPENSE_CATEGORIES = `${API_BASE}/expenses/categories/`
const API_EXPENSE_ASSIGNMENTS = `${API_BASE}/expenses/assignments/`
const API_EXPENSE_IMPORT = `${API_BASE}/expenses/import/`
const BANK_SOURCES = ['santander', 'bancon']
const MANUAL_EXPENSES_STORAGE_KEY = 'viglianco_manual_expenses'
const BANK_ASSIGNMENTS_STORAGE_KEY = 'viglianco_bank_assignments'
const CATEGORIES_STORAGE_KEY = 'viglianco_expense_categories'
const UNCLASSIFIED_CATEGORY = 'SIN CLASIFICAR'
const NO_DATE_MONTH_KEY = 'sin-fecha'

const METHOD_ICONS = {
  'EFECTIVO': (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="28"
      height="28"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ color: '#4caf50' }}
    >
      <path d="M7 15h-3a1 1 0 0 1 -1 -1v-8a1 1 0 0 1 1 -1h12a1 1 0 0 1 1 1v3" />
      <path d="M7 9m0 1a1 1 0 0 1 1 -1h12a1 1 0 0 1 1 1v8a1 1 0 0 1 -1 1h-12a1 1 0 0 1 -1 -1z" />
      <path d="M12 14a2 2 0 1 0 4 0a2 2 0 0 0 -4 0" />
    </svg>
  ),
  'TRANSFERENCIA': (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="28"
      height="28"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ color: '#fdd835' }}
    >
      <path stroke="none" d="M0 0h24v24H0z" fill="none" />
      <path d="M9 12a3 3 0 1 0 6 0a3 3 0 0 0 -6 0" />
      <path d="M12 18h-7a2 2 0 0 1 -2 -2v-8a2 2 0 0 1 2 -2h14a2 2 0 0 1 2 2v4.5" />
      <path d="M18 12h.01" />
      <path d="M6 12h.01" />
      <path d="M16 19h6" />
      <path d="M19 16l3 3l-3 3" />
    </svg>
  ),
  'CHEQUE': (
    <svg
      width="28"
      height="28"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="2" y="7" width="20" height="10" rx="2" ry="2" />
      <path d="M6 12h8" />
      <path d="M6 9h4" />
      <path d="M18 14l2 2" />
      <path d="M20 12l-4 4" />
    </svg>
  ),
}

const initialCategoryMap = {
  'SUELDOS': ['DIEGO', 'ROCIO', 'VALERIA', 'ZAIRA', 'DAMIAN', 'MATIAS', 'NATALIA', 'ALBERTINA'],
  'GASTOS FIJOS': ['LUZ', 'AFIP', 'ALQUILER', 'SEGURO', 'RENTAS', 'INTERNET', 'CONTADOR', 'AGUA', 'CONSUMO'],
  'GASTOS GENERALES': ['INVERSION', 'MANTENIMIENTO', 'BANCOS', 'HACIENDA'],
  'ALIMENTOS': ['CONGELADOS', 'PANADERIA', 'VERDULERIA', 'PASTAS', 'MERCADERIA', 'ENSALADAS'],
  'VARIOS': ['DESCARTABLES', 'CARBON Y LENA', 'DESCUENTOS', 'LIMPIEZA'],
  'CARNES': ['ANIMALES', 'AVES', 'CERDO', 'ACHURAS', 'FRIGORIFICO', 'ELABORADOS'],
  'BEBIDAS': ['GASEOSAS', 'CERVEZAS', 'VINOS'],
}

const CATEGORY_COLORS = {
  'SUELDOS': '#6FCFEB',
  'GASTOS FIJOS': '#FF8A80',
  'GASTOS GENERALES': '#FDD835',
  'ALIMENTOS': '#8BC34A',
  'VARIOS': '#CE93D8',
  'CARNES': '#FF7043',
  'BEBIDAS': '#64B5F6',
  [UNCLASSIFIED_CATEGORY]: '#9E9E9E',
}

const FALLBACK_CHART_COLORS = ['#29b6f6', '#ff8a65', '#4dd0e1', '#ba68c8', '#ffd54f', '#4db6ac', '#f06292', '#9575cd', '#aed581', '#90caf9']
const STATS_CARD_TITLE_SX = {
  fontWeight: 800,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  color: '#fff',
  mb: 2,
}

const adjustColor = (hex, amount = 0.25) => {
  const sanitized = (hex || '#999999').replace('#', '')
  const safe = sanitized.length === 6 ? sanitized : '999999'
  const num = parseInt(safe, 16)
  const mix = (channel) => {
    const value = (num >> channel) & 0xff
    return Math.min(255, Math.round(value + (255 - value) * amount))
  }
  const [r, g, b] = [16, 8, 0].map((shift) => mix(shift).toString(16).padStart(2, '0'))
  return `#${r}${g}${b}`
}

const formatCurrency = (value) => {
  const num = Number(value || 0)
  return `$ ${num.toLocaleString('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

const formatLocalIsoDate = (date = new Date()) => {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const parseDateValue = (value) => {
  if (!value) return null
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value
  const isoMatch = typeof value === 'string' ? value.match(/^(\d{4})-(\d{2})-(\d{2})$/) : null
  if (isoMatch) {
    const [, yearStr, monthStr, dayStr] = isoMatch
    const year = Number(yearStr)
    const month = Number(monthStr)
    const day = Number(dayStr)
    return Number.isNaN(year + month + day) ? null : new Date(year, month - 1, day)
  }
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

const formatDateDisplay = (value) => {
  const date = parseDateValue(value)
  return date ? date.toLocaleDateString('es-AR') : ''
}

const formatDayLabel = (value) => {
  const date = parseDateValue(value)
  return date ? date.toLocaleDateString('es-AR', { weekday: 'long' }).toUpperCase() : ''
}

const formatMonthYear = (value) => {
  if (!value) return ''
  const date = value instanceof Date ? value : parseDateValue(value)
  if (!date) return ''
  const formatted = date.toLocaleDateString('es-AR', { month: 'long', year: 'numeric' })
  return formatted.charAt(0).toUpperCase() + formatted.slice(1)
}

const formatMonthNumeric = (year, month) => {
  if (!year || !month) return ''
  const date = new Date(Number(year), Number(month) - 1)
  return date.toLocaleDateString('es-AR', { month: 'long', year: 'numeric' })
}

const getMonthKeyFromDate = (value) => {
  const date = parseDateValue(value)
  if (!date) return ''
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}

const isMonthKey = (value) => /^\d{4}-\d{2}$/.test(value || '')

const formatMonthKeyLabel = (monthKey) => {
  if (!monthKey) return ''
  if (monthKey === NO_DATE_MONTH_KEY) return 'Sin fecha'
  if (!isMonthKey(monthKey)) return monthKey
  const [year, month] = monthKey.split('-')
  return formatMonthNumeric(year, month)
}

const renderDeleteIcon = (backgroundColor = '#ff8a80') => (
  <Box
    component="span"
    sx={{
      width: 18,
      height: 18,
      borderRadius: '50%',
      backgroundColor,
      color: '#fff',
      fontSize: '0.75rem',
      fontWeight: 700,
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      mr: 1,
    }}
  >
    ×
  </Box>
)

const renderAssignmentChipOrSelect = ({
  expense,
  type,
  categories,
  assignedCategories,
  handleBankCategoryChange,
  handleManualCategoryChange,
}) => {
  const isBankExpense = expense.source === 'bank'
  const manualCategory = expense.category || ''
  const manualSubcategory = expense.subcategory || ''
  const assignment = assignedCategories[expense.id] || { category: manualCategory, subcategory: manualSubcategory }
  const categoryValue = isBankExpense ? assignment.category : manualCategory
  const subcategoryValue = isBankExpense ? assignment.subcategory : manualSubcategory
  const subcategoryOptions = categoryValue ? (categories[categoryValue] || []) : []
  const categoryColor = CATEGORY_COLORS[categoryValue] || '#ccc'
  const subColor = adjustColor(categoryColor, 0.45)
  const showCategorySelect = !categoryValue
  const showSubcategorySelect = !subcategoryValue

  const onCategoryChange = (value) => (
    isBankExpense
      ? handleBankCategoryChange(expense.id, 'category', value)
      : handleManualCategoryChange(expense.id, 'category', value)
  )

  const onSubcategoryChange = (value) => (
    isBankExpense
      ? handleBankCategoryChange(expense.id, 'subcategory', value)
      : handleManualCategoryChange(expense.id, 'subcategory', value)
  )

  if (type === 'category') {
    if (showCategorySelect) {
      return (
        <FormControl size="small" fullWidth>
          <Select
            value={categoryValue}
            onChange={(e) => onCategoryChange(e.target.value)}
            displayEmpty
            renderValue={(selected) => selected || 'Sin categoría'}
            sx={{ minWidth: 140 }}
          >
            <MenuItem value="">
              <em>Sin categoría</em>
            </MenuItem>
            {Object.keys(categories).map((cat) => (
              <MenuItem key={cat} value={cat}>{cat}</MenuItem>
            ))}
          </Select>
        </FormControl>
      )
    }
    return (
      <Chip
        size="small"
        label={categoryValue}
        onDelete={() => onCategoryChange('')}
        deleteIcon={renderDeleteIcon('#ff6b6b')}
        sx={{
          backgroundColor: categoryColor,
          color: '#0d0d0d',
          fontWeight: 600,
          '& .MuiChip-deleteIcon': { m: 0 },
        }}
      />
    )
  }

  if (showSubcategorySelect) {
    return (
      <FormControl size="small" fullWidth disabled={!categoryValue}>
        <Select
          value={subcategoryValue}
          onChange={(e) => onSubcategoryChange(e.target.value)}
          displayEmpty
          renderValue={(selected) => selected || 'Sin subcategoría'}
          sx={{ minWidth: 140 }}
        >
          <MenuItem value="">
            <em>Sin subcategoría</em>
          </MenuItem>
          {subcategoryOptions.map((sub) => (
            <MenuItem key={sub} value={sub}>{sub}</MenuItem>
          ))}
        </Select>
      </FormControl>
    )
  }

  if (subcategoryValue) {
    return (
      <Chip
        size="small"
        label={subcategoryValue}
        onDelete={() => onSubcategoryChange('')}
        deleteIcon={renderDeleteIcon('#ff6b6b')}
        sx={{
          backgroundColor: subColor,
          color: '#0d0d0d',
          fontWeight: 600,
          '& .MuiChip-deleteIcon': { m: 0 },
        }}
      />
    )
  }

  return null
}

const getMethodIcon = (method) => (
  <Box
    component="span"
    aria-label={method || 'Metodo'}
    sx={{
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 36,
      height: 36,
      borderRadius: '50%',
      border: '1px solid rgba(255,255,255,0.25)',
      color: '#fff',
      backgroundColor: 'rgba(255,255,255,0.05)',
    }}
  >
    {METHOD_ICONS[method] || (
      <Typography variant="caption" sx={{ fontWeight: 600 }}>
        {method || '-'}
      </Typography>
    )}
  </Box>
)

const useBankExpenses = (authFetch) => {
  const [bankExpenses, setBankExpenses] = useState([])
  const [bankLoading, setBankLoading] = useState(false)
  const [bankError, setBankError] = useState('')

  useEffect(() => {
    let active = true
    const fetchBankExpenses = async () => {
      setBankLoading(true)
      setBankError('')
      try {
        const results = await Promise.allSettled(
          BANK_SOURCES.map(async (bankSource) => {
            const response = await authFetch(`${API_BANK_STATS}?bank=${bankSource}`)
            let data = {}
            try {
              data = await response.json()
            } catch (_) {
              data = {}
            }
            if (!response.ok) {
              throw new Error(data?.detail || `No se pudieron obtener los egresos de ${bankSource}.`)
            }
            return { bankSource, data }
          }),
        )
        const grouped = {}
        const errors = []
        results.forEach((result, index) => {
          const bankSource = BANK_SOURCES[index]
          if (result.status !== 'fulfilled') {
            errors.push(result.reason?.message || `No se pudieron obtener los egresos de ${bankSource}.`)
            return
          }
          const data = result.value.data
          const conceptEntries = data?.concept_entries?.egresos || {}
          Object.entries(conceptEntries).forEach(([conceptName, rows]) => {
            rows.forEach((row) => {
              const amount = Math.abs(Number(row.amount) || 0)
              if (!amount) return
              const conceptLabel = (conceptName || '').trim() || 'Movimiento bancario'
              const descriptionLabel = (row.description || '').trim()
              const groupingLabel = bankSource === 'bancon' && descriptionLabel ? descriptionLabel : conceptLabel
              const dateObj = row.date ? parseDateValue(row.date) : null
              const year = dateObj ? dateObj.getFullYear() : null
              const month = dateObj ? String(dateObj.getMonth() + 1).padStart(2, '0') : null
              const monthKey = year && month ? `${year}-${month}` : NO_DATE_MONTH_KEY
              const key = `${bankSource}-${monthKey}-${groupingLabel}`
              if (!grouped[key]) {
                const sortTimestamp = dateObj ? new Date(dateObj.getFullYear(), dateObj.getMonth(), 1).getTime() : 0
                const monthLabel = monthKey === NO_DATE_MONTH_KEY ? 'Sin fecha' : formatMonthNumeric(year, Number(month))
                grouped[key] = {
                  id: `bank-${key}`,
                  date: monthKey === NO_DATE_MONTH_KEY ? null : `${monthKey}-01`,
                  day: dateObj ? 'MENSUAL' : 'BANCO',
                  displayDate: monthLabel,
                  monthKey,
                  amount: 0,
                  method: 'TRANSFERENCIA',
                  category: '',
                  subcategory: '',
                  description: `${groupingLabel} (${bankSource.toUpperCase()})`,
                  source: 'bank',
                  sortTimestamp,
                }
              }
              grouped[key].amount += amount
            })
          })
        })
        if (errors.length && active) {
          setBankError(errors.join(' '))
        }
        const aggregated = Object.values(grouped).sort((a, b) => (b.sortTimestamp || 0) - (a.sortTimestamp || 0))
        if (active) setBankExpenses(aggregated)
      } catch (err) {
        if (active) setBankError(err.message)
      } finally {
        if (active) setBankLoading(false)
      }
    }
    fetchBankExpenses()
    return () => { active = false }
  }, [authFetch])

  return { bankExpenses, bankLoading, bankError }
}

export default function ExpensesBoard() {
  const { authFetch } = useAuth()
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('md'))
  const ROWS_PER_PAGE = 50
  const todayIso = useMemo(() => formatLocalIsoDate(), [])
  const todayDayLabel = useMemo(() => formatDayLabel(todayIso), [todayIso])
  const [expenses, setExpenses] = useState([])
  const [manualLoading, setManualLoading] = useState(false)
  const [manualError, setManualError] = useState('')
  const { bankExpenses, bankLoading, bankError } = useBankExpenses(authFetch)
  const [assignedCategories, setAssignedCategories] = useState({})
  const [categories, setCategories] = useState(initialCategoryMap)
  const [page, setPage] = useState(0)
  const [newEntry, setNewEntry] = useState({
    date: todayIso,
    day: todayDayLabel,
    amount: '',
    method: paymentMethods[0],
    category: '',
    subcategory: '',
  })
  const [entryError, setEntryError] = useState('')
  const [subcategoryCategory, setSubcategoryCategory] = useState('')
  const [newSubcategory, setNewSubcategory] = useState('')
  const [subCategoryError, setSubCategoryError] = useState('')
  const [toast, setToast] = useState({ open: false, message: '', severity: 'success' })
  const [editDescriptionDialog, setEditDescriptionDialog] = useState({ open: false, expenseId: '', value: '' })
  const [filterCategory, setFilterCategory] = useState('')
  const [filterSubcategory, setFilterSubcategory] = useState('')
  const [filterMonth, setFilterMonth] = useState('')
  const [amountOrder, setAmountOrder] = useState('')
  const [statsOpen, setStatsOpen] = useState(false)
  const currentYear = useMemo(() => new Date().getFullYear().toString(), [])
  const [statsYearFilter, setStatsYearFilter] = useState(currentYear)
  const [statsMonthFilter, setStatsMonthFilter] = useState('')
  const [statsSelectedCategory, setStatsSelectedCategory] = useState('')
  const categoryChartRef = useRef(null)

  useEffect(() => {
    setFilterSubcategory('')
  }, [filterCategory])

  useEffect(() => {
    setStatsMonthFilter('')
  }, [statsYearFilter])

  useEffect(() => {
    let active = true
    const readStoredJson = (key, fallback) => {
      if (typeof window === 'undefined') return fallback
      try {
        const raw = window.localStorage.getItem(key)
        if (!raw) return fallback
        const parsed = JSON.parse(raw)
        return parsed ?? fallback
      } catch (_) {
        return fallback
      }
    }

    const migrateLegacyData = async () => {
      const legacyExpenses = readStoredJson(MANUAL_EXPENSES_STORAGE_KEY, [])
      const legacyCategories = readStoredJson(CATEGORIES_STORAGE_KEY, {})
      const legacyAssignments = readStoredJson(BANK_ASSIGNMENTS_STORAGE_KEY, {})
      const hasLegacy =
        (Array.isArray(legacyExpenses) && legacyExpenses.length) ||
        (legacyCategories && Object.keys(legacyCategories).length) ||
        (legacyAssignments && Object.keys(legacyAssignments).length)

      if (!hasLegacy) return

      const payload = {
        expenses: Array.isArray(legacyExpenses)
          ? legacyExpenses.map((expense) => ({
            external_id: expense.id,
            date: expense.date,
            amount: Number(expense.amount || 0),
            method: expense.method,
            category: expense.category,
            subcategory: expense.subcategory,
            description: expense.description,
          }))
          : [],
        categories: legacyCategories && typeof legacyCategories === 'object' ? legacyCategories : {},
        assignments: legacyAssignments && typeof legacyAssignments === 'object' ? legacyAssignments : {},
      }

      const response = await authFetch(API_EXPENSE_IMPORT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data?.detail || 'No se pudieron migrar los gastos guardados.')
      }

      if (typeof window !== 'undefined') {
        window.localStorage.removeItem(MANUAL_EXPENSES_STORAGE_KEY)
        window.localStorage.removeItem(CATEGORIES_STORAGE_KEY)
        window.localStorage.removeItem(BANK_ASSIGNMENTS_STORAGE_KEY)
      }
    }

    const loadExpensesData = async () => {
      setManualLoading(true)
      setManualError('')
      try {
        await migrateLegacyData()

        const [expensesResponse, categoriesResponse, assignmentsResponse] = await Promise.all([
          authFetch(API_EXPENSES),
          authFetch(API_EXPENSE_CATEGORIES),
          authFetch(API_EXPENSE_ASSIGNMENTS),
        ])

        const expensesData = await expensesResponse.json().catch(() => ([]))
        const categoriesData = await categoriesResponse.json().catch(() => ({}))
        const assignmentsData = await assignmentsResponse.json().catch(() => ({}))

        if (!expensesResponse.ok) {
          throw new Error(expensesData?.detail || 'No se pudieron cargar los gastos.')
        }
        if (!categoriesResponse.ok) {
          throw new Error(categoriesData?.detail || 'No se pudieron cargar las categorias.')
        }
        if (!assignmentsResponse.ok) {
          throw new Error(assignmentsData?.detail || 'No se pudieron cargar las asignaciones.')
        }

        let nextCategories = categoriesData?.categories || {}
        if (!Object.keys(nextCategories).length) {
          const seedResponse = await authFetch(API_EXPENSE_IMPORT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ categories: initialCategoryMap }),
          })
          if (seedResponse.ok) {
            nextCategories = initialCategoryMap
          }
        }

        if (!active) return
        setExpenses(Array.isArray(expensesData) ? expensesData : [])
        setCategories(nextCategories)
        setAssignedCategories(assignmentsData?.assignments || {})
      } catch (err) {
        if (active) {
          setManualError(err.message || 'Error al cargar los gastos.')
        }
      } finally {
        if (active) {
          setManualLoading(false)
        }
      }
    }

    loadExpensesData()
    return () => { active = false }
  }, [authFetch])

  useEffect(() => {
    setPage(0)
  }, [filterCategory, filterSubcategory, filterMonth, amountOrder])

  const availableSubcategories = useMemo(
    () => (newEntry.category ? categories[newEntry.category] || [] : []),
    [newEntry.category, categories],
  )

  const combinedExpenses = useMemo(() => {
    const combined = [...bankExpenses, ...expenses]
    const getSortValue = (expense) => {
      if (typeof expense.sortTimestamp === 'number') return expense.sortTimestamp
      if (expense.date) {
        const date = parseDateValue(expense.date)
        if (date) return date.getTime()
      }
      return 0
    }
    return combined.sort((a, b) => getSortValue(b) - getSortValue(a))
  }, [bankExpenses, expenses])

  const normalizedExpenses = useMemo(() => combinedExpenses.map((expense) => {
    const isBank = expense.source === 'bank'
    const assigned = assignedCategories[expense.id] || {}
    const effectiveCategory = isBank ? assigned.category || UNCLASSIFIED_CATEGORY : expense.category || ''
    const effectiveSubcategory = isBank ? assigned.subcategory || '' : expense.subcategory || ''
    const monthKey = expense.monthKey || getMonthKeyFromDate(expense.date) || (expense.date ? '' : NO_DATE_MONTH_KEY)
    return { ...expense, effectiveCategory, effectiveSubcategory, monthKey }
  }), [combinedExpenses, assignedCategories])

  const statsExpenses = useMemo(
    () => normalizedExpenses.filter((expense) => {
      if (statsMonthFilter) return expense.monthKey === statsMonthFilter
      if (statsYearFilter) {
        if (!expense.monthKey) return false
        if (expense.monthKey === NO_DATE_MONTH_KEY) return false
        if (!expense.monthKey.startsWith(`${statsYearFilter}-`)) return false
      }
      return true
    }),
    [normalizedExpenses, statsYearFilter, statsMonthFilter],
  )

  const statsOverview = useMemo(() => {
    const total = statsExpenses.reduce((acc, exp) => acc + Number(exp.amount || 0), 0)
    const manual = statsExpenses.filter((exp) => exp.source === 'manual').reduce((acc, exp) => acc + Number(exp.amount || 0), 0)
    const bank = statsExpenses.filter((exp) => exp.source === 'bank').reduce((acc, exp) => acc + Number(exp.amount || 0), 0)
    return {
      total,
      manual,
      bank,
      count: statsExpenses.length,
    }
  }, [statsExpenses])


  const availableFilterMonths = useMemo(() => {
    const set = new Set()
    normalizedExpenses.forEach((expense) => {
      if (expense.monthKey) set.add(expense.monthKey)
    })
    return Array.from(set).sort((a, b) => {
      if (a === NO_DATE_MONTH_KEY) return 1
      if (b === NO_DATE_MONTH_KEY) return -1
      return a.localeCompare(b)
    })
  }, [normalizedExpenses])

  const statsYearOptions = useMemo(() => {
    const set = new Set()
    availableFilterMonths.forEach((monthKey) => {
      if (!isMonthKey(monthKey)) return
      const [year] = monthKey.split('-')
      if (year) set.add(year)
    })
    const values = Array.from(set)
    if (!values.length) return [currentYear]
    return values.sort((a, b) => b.localeCompare(a))
  }, [availableFilterMonths, currentYear])

  useEffect(() => {
    if (!statsYearOptions.length) return
    if (!statsYearOptions.includes(statsYearFilter)) {
      setStatsYearFilter(statsYearOptions[0])
    }
  }, [statsYearOptions, statsYearFilter])

  const statsMonthOptions = useMemo(() => {
    const months = [...availableFilterMonths].filter((monthKey) => {
      if (monthKey === NO_DATE_MONTH_KEY) return true
      if (!statsYearFilter) return true
      return monthKey.startsWith(`${statsYearFilter}-`)
    })
    return months.sort((a, b) => {
      if (a === NO_DATE_MONTH_KEY) return 1
      if (b === NO_DATE_MONTH_KEY) return -1
      return b.localeCompare(a)
    })
  }, [availableFilterMonths, statsYearFilter])

  const categorySummary = useMemo(() => {
    const summary = statsExpenses.reduce((acc, expense) => {
      const categoryKey = expense.effectiveCategory || (expense.source === 'bank' ? UNCLASSIFIED_CATEGORY : '')
      if (!categoryKey) return acc
      acc[categoryKey] = (acc[categoryKey] || 0) + Number(expense.amount || 0)
      return acc
    }, {})
    return Object.entries(summary).sort((a, b) => b[1] - a[1])
  }, [statsExpenses])

  const categoryTotalsMap = useMemo(() => Object.fromEntries(categorySummary), [categorySummary])

  const monthlySummary = useMemo(() => {
    const summary = statsExpenses.reduce((acc, expense) => {
      if (!expense.monthKey) return acc
      acc[expense.monthKey] = (acc[expense.monthKey] || 0) + Number(expense.amount || 0)
      return acc
    }, {})
    return Object.entries(summary).sort(([aKey], [bKey]) => {
      if (aKey === NO_DATE_MONTH_KEY) return 1
      if (bKey === NO_DATE_MONTH_KEY) return -1
      return bKey.localeCompare(aKey)
    })
  }, [statsExpenses])

  const subcategorySummary = useMemo(() => {
    const summary = {}
    statsExpenses.forEach((expense) => {
      const category = expense.effectiveCategory || ''
      const subcategory = expense.effectiveSubcategory || ''
      if (!category || !subcategory) return
      const key = `${category}__${subcategory}`
      if (!summary[key]) summary[key] = { category, subcategory, amount: 0 }
      summary[key].amount += Number(expense.amount || 0)
    })
    return Object.values(summary).sort((a, b) => b.amount - a.amount)
  }, [statsExpenses])

  const filteredSubcategories = useMemo(
    () => (statsSelectedCategory ? subcategorySummary.filter((item) => item.category === statsSelectedCategory) : subcategorySummary),
    [statsSelectedCategory, subcategorySummary],
  )

  const topSubcategorySummary = useMemo(() => filteredSubcategories.slice(0, 10), [filteredSubcategories])

  const selectedCategorySubcategories = useMemo(
    () => (statsSelectedCategory ? subcategorySummary.filter((item) => item.category === statsSelectedCategory) : []),
    [statsSelectedCategory, subcategorySummary],
  )

  const baseCategoryChartData = useMemo(() => {
    if (!categorySummary.length) return { labels: [], datasets: [] }
    const labels = categorySummary.map(([name]) => name)
    const data = categorySummary.map(([, amount]) => Number(amount || 0))
    const colors = categorySummary.map(([name], idx) => CATEGORY_COLORS[name] || FALLBACK_CHART_COLORS[idx % FALLBACK_CHART_COLORS.length])
    return {
      labels,
      datasets: [
        {
          data,
          backgroundColor: colors,
          borderColor: '#0b111d',
          borderWidth: 2,
        },
      ],
    }
  }, [categorySummary])

  const subcategoryDonutData = useMemo(() => {
    if (!statsSelectedCategory || !selectedCategorySubcategories.length) return null
    const labels = selectedCategorySubcategories.map((item) => item.subcategory)
    const data = selectedCategorySubcategories.map((item) => Number(item.amount || 0))
    const baseColor = CATEGORY_COLORS[statsSelectedCategory] || '#29b6f6'
    const colors = selectedCategorySubcategories.map((_, idx) => adjustColor(baseColor, 0.2 + idx * 0.1))
    return {
      labels,
      datasets: [
        {
          data,
          backgroundColor: colors,
          borderColor: '#0b111d',
          borderWidth: 2,
        },
      ],
    }
  }, [statsSelectedCategory, selectedCategorySubcategories])

  const categoryChartData = useMemo(() => {
    if (statsSelectedCategory && subcategoryDonutData) return subcategoryDonutData
    return baseCategoryChartData
  }, [statsSelectedCategory, subcategoryDonutData, baseCategoryChartData])

  const donutValue = statsSelectedCategory && statsSelectedCategory in categoryTotalsMap
    ? formatCurrency(categoryTotalsMap[statsSelectedCategory])
    : formatCurrency(statsOverview.total)
  const donutSubtitle = statsSelectedCategory ? `Subcategorias de ${statsSelectedCategory}` : 'Todas las categorias'
  const donutDetail = statsSelectedCategory
    ? `${selectedCategorySubcategories.length} subcategorias`
    : `${categorySummary.length} categorias`

  const categoryChartOptions = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    cutout: '65%',
    animation: {
      duration: 600,
      easing: 'easeOutQuart',
    },
    plugins: {
      legend: {
        position: 'bottom',
        labels: { color: '#fff' },
      },
      tooltip: {
        callbacks: {
          label: (context) => `${context.label || ''}: ${formatCurrency(context.raw ?? 0)}`,
        },
      },
      expensesDonutCenter: {
        title: 'Importe total',
        value: donutValue,
        subtitle: donutSubtitle,
        detail: donutDetail,
      },
    },
  }), [donutValue, donutSubtitle, donutDetail])

  const subcategoryChartData = useMemo(() => {
    if (!topSubcategorySummary.length) return { labels: [], datasets: [] }
    const labels = topSubcategorySummary.map((item) => item.subcategory)
    const data = topSubcategorySummary.map((item) => Number(item.amount || 0))
    const colors = topSubcategorySummary.map((item, idx) => adjustColor(CATEGORY_COLORS[item.category] || FALLBACK_CHART_COLORS[idx % FALLBACK_CHART_COLORS.length], 0.35))
    return {
      labels,
      datasets: [
        {
          label: 'Monto',
          data,
          backgroundColor: colors,
          borderRadius: 12,
          borderSkipped: false,
          barThickness: 28,
        },
      ],
    }
  }, [topSubcategorySummary])

  const subcategoryChartOptions = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (context) => formatCurrency(context.raw ?? 0),
        },
      },
    },
    elements: {
      bar: {
        borderRadius: 12,
        borderSkipped: false,
      },
    },
    scales: {
      x: {
        ticks: {
          color: 'rgba(255,255,255,0.85)',
          autoSkip: false,
          maxRotation: 40,
          minRotation: 30,
        },
        grid: { display: false },
      },
      y: {
        ticks: {
          color: 'rgba(255,255,255,0.8)',
          callback: (value) => formatCurrency(value),
        },
        grid: { color: 'rgba(255,255,255,0.08)' },
      },
    },
  }), [])

  const filteredExpenses = useMemo(() => {
    let result = normalizedExpenses.filter((expense) => {
      if (filterCategory && expense.effectiveCategory !== filterCategory) return false
      if (filterSubcategory && expense.effectiveSubcategory !== filterSubcategory) return false
      if (filterMonth && expense.monthKey !== filterMonth) return false
      return true
    })
    if (amountOrder === 'asc') {
      result = [...result].sort((a, b) => a.amount - b.amount)
    } else if (amountOrder === 'desc') {
      result = [...result].sort((a, b) => b.amount - a.amount)
    }
    return result
  }, [normalizedExpenses, filterCategory, filterSubcategory, filterMonth, amountOrder])

  const totals = useMemo(() => filteredExpenses.reduce((acc, expense) => acc + Number(expense.amount || 0), 0), [filteredExpenses])

  useEffect(() => {
    const maxPage = Math.max(0, Math.ceil(filteredExpenses.length / ROWS_PER_PAGE) - 1)
    if (page > maxPage) setPage(maxPage)
  }, [filteredExpenses.length, page, ROWS_PER_PAGE])

  const paginatedExpenses = useMemo(
    () => filteredExpenses.slice(page * ROWS_PER_PAGE, page * ROWS_PER_PAGE + ROWS_PER_PAGE),
    [filteredExpenses, page, ROWS_PER_PAGE],
  )

  const filterCategoryOptions = useMemo(() => {
    const base = Object.keys(categories)
    const hasUnclassified = normalizedExpenses.some((expense) => expense.effectiveCategory === UNCLASSIFIED_CATEGORY)
    if (!hasUnclassified || base.includes(UNCLASSIFIED_CATEGORY)) return base
    return [...base, UNCLASSIFIED_CATEGORY]
  }, [categories, normalizedExpenses])

  const filterSubcategoryOptions = useMemo(
    () => (filterCategory && filterCategory !== UNCLASSIFIED_CATEGORY ? categories[filterCategory] || [] : []),
    [filterCategory, categories],
  )

  useEffect(() => {
    if (statsSelectedCategory && !categorySummary.find(([name]) => name === statsSelectedCategory)) {
      setStatsSelectedCategory('')
    }
  }, [statsSelectedCategory, categorySummary])

  const handleCategoryChartClick = useCallback((event) => {
    const chart = categoryChartRef.current
    if (!chart) return
    const elements = chart.getElementsAtEventForMode(event.nativeEvent, 'nearest', { intersect: true }, false)
    if (!elements.length) return
    if (statsSelectedCategory && subcategoryDonutData) return
    const { index } = elements[0]
    const labels = baseCategoryChartData.labels || []
    const clickedLabel = labels[index]
    if (!clickedLabel) return
    setStatsSelectedCategory(clickedLabel)
  }, [baseCategoryChartData.labels, statsSelectedCategory, subcategoryDonutData])
  useEffect(() => {
    if (!bankExpenses.length) return
    setAssignedCategories((prev) => {
      const next = {}
      bankExpenses.forEach((expense) => {
        next[expense.id] = prev[expense.id] || { category: '', subcategory: '' }
      })
      return next
    })
  }, [bankExpenses])

  const handleEntryChange = (field, value) => {
    setEntryError('')
    setNewEntry((prev) => {
      const next = { ...prev, [field]: value }
      if (field === 'date' && value) {
        const date = parseDateValue(value)
        next.day = date ? date.toLocaleDateString('es-AR', { weekday: 'long' }).toUpperCase() : ''
      }
      if (field === 'category') {
        const list = categories[value] || []
        next.subcategory = list[0] || ''
      }
      return next
    })
  }

  const handleAddExpense = async () => {
    if (!newEntry.date || !newEntry.amount || !newEntry.category || !newEntry.subcategory) {
      setEntryError('Completa fecha, monto, categoria y subcategoria.')
      return
    }
    const payload = {
      date: newEntry.date,
      day: newEntry.day,
      amount: Number(newEntry.amount),
      method: newEntry.method,
      category: newEntry.category,
      subcategory: newEntry.subcategory,
      description: 'Sin descripcion',
      source: 'manual',
    }
    try {
      const response = await authFetch(API_EXPENSES, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data?.detail || 'No se pudo registrar el gasto.')
      }
      setExpenses((prev) => [data, ...prev])
      setNewEntry((prev) => ({
        ...prev,
        amount: '',
      }))
      setToast({ open: true, message: 'Gasto registrado', severity: 'success' })
    } catch (err) {
      setToast({ open: true, message: err.message || 'No se pudo registrar el gasto.', severity: 'error' })
    }
  }

  const handleAddSubcategory = async () => {
    if (!subcategoryCategory) {
      setSubCategoryError('Selecciona la categoria.')
      return
    }
    const name = newSubcategory.trim().toUpperCase()
    if (!name) {
      setSubCategoryError('Ingresa el nombre de la subcategoria.')
      return
    }
    try {
      const response = await authFetch(API_EXPENSE_CATEGORIES, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category: subcategoryCategory, subcategory: name }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data?.detail || 'No se pudo crear la subcategoria.')
      }
      setCategories((prev) => {
        const current = prev[subcategoryCategory] || []
        if (current.includes(name)) {
          return prev
        }
        return { ...prev, [subcategoryCategory]: [...current, name] }
      })
      setSubCategoryError('')
      setNewSubcategory('')
      setToast({ open: true, message: `Subcategoria ${name} creada`, severity: 'success' })
    } catch (err) {
      setSubCategoryError(err.message || 'No se pudo crear la subcategoria.')
    }
  }

  const handleDeleteSubcategory = async (category, name) => {
    try {
      const response = await authFetch(API_EXPENSE_CATEGORIES, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category, subcategory: name }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data?.detail || 'No se pudo eliminar la subcategoria.')
      }
      setCategories((prev) => {
        const updated = (prev[category] || []).filter((item) => item !== name)
        return { ...prev, [category]: updated }
      })
      setExpenses((prev) => prev.map((exp) => (
        exp.category === category && exp.subcategory === name ? { ...exp, subcategory: '' } : exp
      )))
      setAssignedCategories((prev) => {
        let changed = false
        const next = Object.entries(prev).reduce((acc, [expenseId, assignment]) => {
          if (assignment?.category === category && assignment?.subcategory === name) {
            changed = true
            acc[expenseId] = { ...assignment, subcategory: '' }
            return acc
          }
          acc[expenseId] = assignment
          return acc
        }, {})
        return changed ? next : prev
      })
      setToast({ open: true, message: `Subcategoria ${name} eliminada`, severity: 'info' })
    } catch (err) {
      setToast({ open: true, message: err.message || 'No se pudo eliminar la subcategoria.', severity: 'error' })
    }
  }

  const handleCloseToast = (_event, reason) => {
    if (reason === 'clickaway') return
    setToast((prev) => ({ ...prev, open: false }))
  }

  const handleBankCategoryChange = async (expenseId, field, value) => {
    const current = assignedCategories[expenseId] || { category: '', subcategory: '' }
    const updated = { ...current, [field]: value }
    if (field === 'category') {
      const list = categories[value] || []
      updated.subcategory = list[0] || ''
    }
    setAssignedCategories((prev) => ({ ...prev, [expenseId]: updated }))
    try {
      const response = await authFetch(API_EXPENSE_ASSIGNMENTS, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          assignments: [
            { external_id: expenseId, category: updated.category, subcategory: updated.subcategory },
          ],
        }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data?.detail || 'No se pudo guardar la asignacion.')
      }
    } catch (err) {
      setAssignedCategories((prev) => ({ ...prev, [expenseId]: current }))
      setToast({ open: true, message: err.message || 'No se pudo guardar la asignacion.', severity: 'error' })
    }
  }

  const handleManualCategoryChange = async (expenseId, field, value) => {
    let previousExpense = null
    let nextPayload = {}
    setExpenses((prev) => prev.map((expense) => {
      if (expense.id !== expenseId) return expense
      previousExpense = expense
      if (field === 'category') {
        const list = categories[value] || []
        const nextSubcategory = value ? list[0] || '' : ''
        nextPayload = { category: value, subcategory: nextSubcategory }
        return { ...expense, category: value, subcategory: nextSubcategory }
      }
      if (field === 'subcategory') {
        nextPayload = { subcategory: value }
        return { ...expense, subcategory: value }
      }
      return expense
    }))
    if (!expenseId || !Object.keys(nextPayload).length) return
    try {
      const response = await authFetch(`${API_EXPENSES}${expenseId}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(nextPayload),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data?.detail || 'No se pudo actualizar la categoria.')
      }
    } catch (err) {
      if (previousExpense) {
        setExpenses((prev) => prev.map((expense) => (
          expense.id === expenseId ? previousExpense : expense
        )))
      }
      setToast({ open: true, message: err.message || 'No se pudo actualizar la categoria.', severity: 'error' })
    }
  }

  const handleEditDescription = (expense) => {
    setEditDescriptionDialog({ open: true, expenseId: expense.id, value: expense.description || 'Sin descripcion' })
  }

  const handleCloseDescriptionDialog = () => {
    setEditDescriptionDialog({ open: false, expenseId: '', value: '' })
  }

  const handleSaveDescription = async () => {
    const { expenseId, value } = editDescriptionDialog
    if (!expenseId) return
    const nextDescription = value || 'Sin descripcion'
    const previous = expenses.find((expense) => expense.id === expenseId)
    setExpenses((prev) => prev.map((expense) => (
      expense.id === expenseId ? { ...expense, description: nextDescription } : expense
    )))
    try {
      const response = await authFetch(`${API_EXPENSES}${expenseId}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: nextDescription }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data?.detail || 'No se pudo actualizar la descripcion.')
      }
      handleCloseDescriptionDialog()
      setToast({ open: true, message: 'Descripcion actualizada', severity: 'success' })
    } catch (err) {
      if (previous) {
        setExpenses((prev) => prev.map((expense) => (
          expense.id === expenseId ? previous : expense
        )))
      }
      setToast({ open: true, message: err.message || 'No se pudo actualizar la descripcion.', severity: 'error' })
    }
  }

  const handleDeleteExpense = async (expense) => {
    if (expense.source !== 'manual') return
    try {
      const response = await authFetch(`${API_EXPENSES}${expense.id}/`, { method: 'DELETE' })
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data?.detail || 'No se pudo eliminar el gasto.')
      }
      setExpenses((prev) => prev.filter((item) => item.id !== expense.id))
      setToast({ open: true, message: 'Gasto eliminado', severity: 'info' })
    } catch (err) {
      setToast({ open: true, message: err.message || 'No se pudo eliminar el gasto.', severity: 'error' })
    }
  }

  const dateFieldSx = useMemo(() => ({
    '& input::-webkit-calendar-picker-indicator': {
      filter: 'invert(1)',
      opacity: 0.9,
      cursor: 'pointer',
    },
    '& input::-moz-calendar-picker-indicator': {
      filter: 'invert(1)',
      opacity: 0.9,
      cursor: 'pointer',
    },
  }), [])

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4" sx={{ fontWeight: 700 }}>Gastos y categorias</Typography>
        <Button
          variant="contained"
          startIcon={<InsightsIcon />}
          onClick={() => setStatsOpen(true)}
          sx={{
            backgroundColor: '#29b6f6',
            color: '#021019',
            fontWeight: 700,
            px: 3,
            borderRadius: 2,
            '&:hover': { backgroundColor: '#1aa8e8' },
          }}
        >
          ESTADISTICAS
        </Button>
      </Stack>

      <Card sx={{ borderRadius: 3, border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(12,12,18,0.9)' }}>
        <CardContent>
          <Typography variant="h6" sx={{ mb: 2 }}>Nuevo gasto</Typography>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
            <TextField
              type="date"
              label="Fecha"
              InputLabelProps={{ shrink: true }}
              value={newEntry.date}
              onChange={(e) => handleEntryChange('date', e.target.value)}
              fullWidth
              sx={dateFieldSx}
            />
            <TextField
              label="Monto"
              type="number"
              value={newEntry.amount}
              onChange={(e) => handleEntryChange('amount', e.target.value)}
              fullWidth
            />
            <FormControl fullWidth>
              <InputLabel>Metodo</InputLabel>
              <Select
                label="Metodo"
                value={newEntry.method}
                onChange={(e) => handleEntryChange('method', e.target.value)}
              >
                {paymentMethods.map((method) => (
                  <MenuItem key={method} value={method}>{method}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mt: 2 }}>
            <FormControl fullWidth>
              <InputLabel>Categoria</InputLabel>
              <Select
                label="Categoria"
                value={newEntry.category}
                onChange={(e) => handleEntryChange('category', e.target.value)}
              >
                {Object.keys(categories).map((cat) => (
                  <MenuItem key={cat} value={cat}>{cat}</MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl fullWidth disabled={!availableSubcategories.length}>
              <InputLabel>Subcategoria</InputLabel>
              <Select
                label="Subcategoria"
                value={newEntry.subcategory}
                onChange={(e) => handleEntryChange('subcategory', e.target.value)}
              >
                {availableSubcategories.map((sub) => (
                  <MenuItem key={sub} value={sub}>{sub}</MenuItem>
                ))}
              </Select>
            </FormControl>
            <Button variant="contained" color="success" onClick={handleAddExpense} sx={{ alignSelf: 'stretch' }}>
              Crear
            </Button>
          </Stack>
          {entryError && <Alert severity="error" sx={{ mt: 2 }}>{entryError}</Alert>}
        </CardContent>
      </Card>

      <Card sx={{ borderRadius: 3, border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(7,7,12,0.95)' }}>
        <CardContent>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
            <Typography variant="h6">Historial de gastos</Typography>
            <Chip label={`Total: ${formatCurrency(totals)}`} color="success" variant="outlined" />
          </Stack>
          {manualError && <Alert severity="error" sx={{ mb: 2 }}>{manualError}</Alert>}
          {manualLoading && <LinearProgress sx={{ mb: 2 }} />}
          {bankError && <Alert severity="error" sx={{ mb: 2 }}>{bankError}</Alert>}
          {bankLoading && <LinearProgress sx={{ mb: 2 }} />}
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }}>
            <FormControl fullWidth size="small">
              <InputLabel>Filtrar categoria</InputLabel>
              <Select
                label="Filtrar categoria"
                value={filterCategory}
                onChange={(e) => setFilterCategory(e.target.value)}
              >
                <MenuItem value="">
                  <em>Todas</em>
                </MenuItem>
                {filterCategoryOptions.map((cat) => (
                  <MenuItem key={cat} value={cat}>{cat}</MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl fullWidth size="small" disabled={!filterCategory || filterCategory === UNCLASSIFIED_CATEGORY}>
              <InputLabel>Filtrar subcategoria</InputLabel>
              <Select
                label="Filtrar subcategoria"
                value={filterSubcategory}
                onChange={(e) => setFilterSubcategory(e.target.value)}
              >
                <MenuItem value="">
                  <em>Todas</em>
                </MenuItem>
                {filterSubcategoryOptions.map((sub) => (
                  <MenuItem key={sub} value={sub}>{sub}</MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl fullWidth size="small">
              <InputLabel>Mes</InputLabel>
              <Select
                label="Mes"
                value={filterMonth}
                onChange={(e) => setFilterMonth(e.target.value)}
              >
                <MenuItem value="">
                  <em>Todos</em>
                </MenuItem>
                {availableFilterMonths.map((monthKey) => (
                  <MenuItem key={monthKey} value={monthKey}>
                    {formatMonthKeyLabel(monthKey)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl fullWidth size="small">
              <InputLabel>Orden monto</InputLabel>
              <Select
                label="Orden monto"
                value={amountOrder}
                onChange={(e) => setAmountOrder(e.target.value)}
              >
                <MenuItem value="">
                  <em>Sin ordenar</em>
                </MenuItem>
                <MenuItem value="asc">Ascendente</MenuItem>
                <MenuItem value="desc">Descendente</MenuItem>
              </Select>
            </FormControl>
          </Stack>
          {isMobile ? (
            <Stack spacing={2}>
              {paginatedExpenses.map((expense, idx) => {
                const key = expense.id || `${expense.date}-${idx + page * ROWS_PER_PAGE}`
                const displayDate = expense.displayDate || formatDateDisplay(expense.date)
                const displayDay = expense.day || formatDayLabel(expense.date)
                const descriptionLabel = expense.description || 'Sin descripcion'
                return (
                  <Box
                    key={`mobile-${key}`}
                    sx={{
                      p: 2,
                      borderRadius: 3,
                      border: '1px solid rgba(255,255,255,0.08)',
                      backgroundColor: 'rgba(8,8,12,0.9)',
                    }}
                  >
                    <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                      <Box>
                        <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>{displayDate}</Typography>
                        <Typography variant="caption" color="text.secondary">{displayDay}</Typography>
                      </Box>
                      <Stack spacing={1} alignItems="flex-end">
                        <Typography variant="h6" sx={{ fontWeight: 700 }}>{formatCurrency(expense.amount)}</Typography>
                        {expense.source === 'manual' ? (
                          <IconButton size="small" color="error" onClick={() => handleDeleteExpense(expense)}>
                            <DeleteOutlineIcon fontSize="inherit" />
                          </IconButton>
                        ) : null}
                      </Stack>
                    </Stack>
                    <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 1 }}>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>{descriptionLabel}</Typography>
                      {!expense.source || expense.source === 'manual' ? (
                        <IconButton size="small" onClick={() => handleEditDescription(expense)}>
                          <EditIcon fontSize="inherit" />
                        </IconButton>
                      ) : null}
                    </Stack>
                    <Divider sx={{ my: 1.5, borderColor: 'rgba(255,255,255,0.08)' }} />
                    <Stack spacing={1.2}>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: 0.5 }}>Metodo</Typography>
                        {getMethodIcon(expense.method)}
                      </Stack>
                      <Box>
                        <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase' }}>Categoria</Typography>
                        {renderAssignmentChipOrSelect({
                          expense,
                          type: 'category',
                          categories,
                          assignedCategories,
                          handleBankCategoryChange,
                          handleManualCategoryChange,
                        })}
                      </Box>
                      <Box>
                        <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase' }}>Subcategoria</Typography>
                        {renderAssignmentChipOrSelect({
                          expense,
                          type: 'subcategory',
                          categories,
                          assignedCategories,
                          handleBankCategoryChange,
                          handleManualCategoryChange,
                        })}
                      </Box>
                    </Stack>
                  </Box>
                )
              })}
            </Stack>
          ) : null}
          {!isMobile && (
          <Table size="small" sx={{ '& td, & th': { borderColor: 'rgba(255,255,255,0.08)' } }}>
            <TableHead>
              <TableRow>
                <TableCell align="center" width={40} sx={{ px: 0.5 }}> </TableCell>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>Fecha</TableCell>
                <TableCell>Dia</TableCell>
                <TableCell>Descripcion</TableCell>
                <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>Monto</TableCell>
                <TableCell>Metodo</TableCell>
                <TableCell>Categoria</TableCell>
                <TableCell>Subcategoria</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {paginatedExpenses.map((expense, idx) => {
                const key = expense.id || `${expense.date}-${idx + page * ROWS_PER_PAGE}`
                const displayDate = expense.displayDate || formatDateDisplay(expense.date)
                const displayDay = expense.day || formatDayLabel(expense.date)
                const descriptionLabel = expense.description || 'Sin descripcion'
                const isBankExpense = expense.source === 'bank'
                const manualCategory = expense.category || ''
                const manualSubcategory = expense.subcategory || ''
                const assignment = assignedCategories[expense.id] || { category: manualCategory, subcategory: manualSubcategory }
                const categoryValue = isBankExpense ? assignment.category : manualCategory
                const subcategoryValue = isBankExpense ? assignment.subcategory : manualSubcategory
                const subcategoryOptions = categoryValue ? (categories[categoryValue] || []) : []
                const categoryColor = CATEGORY_COLORS[categoryValue] || '#ccc'
                const subColor = adjustColor(categoryColor, 0.45)
                const showCategorySelect = !categoryValue
                const showSubcategorySelect = !subcategoryValue
                return (
                  <TableRow key={key}>
                    <TableCell align="center" sx={{ px: 0.5 }}>
                      {expense.source === 'manual' ? (
                        <IconButton size="small" color="error" onClick={() => handleDeleteExpense(expense)}>
                          <DeleteOutlineIcon fontSize="inherit" />
                        </IconButton>
                      ) : null}
                    </TableCell>
                    <TableCell>{displayDate}</TableCell>
                    <TableCell>{displayDay}</TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {descriptionLabel}
                        </Typography>
                        {!expense.source || expense.source === 'manual' ? (
                          <IconButton size="small" onClick={() => handleEditDescription(expense)}>
                            <EditIcon fontSize="inherit" />
                          </IconButton>
                        ) : null}
                      </Stack>
                    </TableCell>
                    <TableCell align="right">{formatCurrency(expense.amount)}</TableCell>
                    <TableCell>{getMethodIcon(expense.method)}</TableCell>
                    <TableCell>
                      {renderAssignmentChipOrSelect({
                        expense,
                        type: 'category',
                        categories,
                        assignedCategories,
                        handleBankCategoryChange,
                        handleManualCategoryChange,
                      })}
                    </TableCell>
                    <TableCell>
                      {renderAssignmentChipOrSelect({
                        expense,
                        type: 'subcategory',
                        categories,
                        assignedCategories,
                        handleBankCategoryChange,
                        handleManualCategoryChange,
                      })}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
          )}
          <TablePagination
            component="div"
            count={filteredExpenses.length}
            page={page}
            onPageChange={(_event, newPage) => setPage(newPage)}
            rowsPerPage={ROWS_PER_PAGE}
            rowsPerPageOptions={[ROWS_PER_PAGE]}
            labelRowsPerPage="Filas por pagina"
            labelDisplayedRows={({ from, to, count }) => `${from}-${to} de ${count}`}
          />
        </CardContent>
      </Card>

      <Card sx={{ borderRadius: 3, border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(12,12,18,0.9)' }}>
        <CardContent>
          <Typography variant="h6" sx={{ mb: 2 }}>Gestionar subcategorias</Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <FormControl fullWidth>
              <InputLabel>Categoria</InputLabel>
              <Select
                label="Categoria"
                value={subcategoryCategory}
                onChange={(e) => { setSubCategoryError(''); setSubcategoryCategory(e.target.value) }}
              >
                {Object.keys(categories).map((cat) => (
                  <MenuItem key={cat} value={cat}>{cat}</MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField
              label="Subcategoria"
              value={newSubcategory}
              onChange={(e) => { setSubCategoryError(''); setNewSubcategory(e.target.value) }}
              fullWidth
            />
            <Button variant="outlined" onClick={handleAddSubcategory}>Crear</Button>
          </Stack>
          {subCategoryError && <Alert severity="error" sx={{ mt: 2 }}>{subCategoryError}</Alert>}
        </CardContent>
      </Card>

      <Card sx={{ borderRadius: 3, border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(7,7,12,0.95)' }}>
        <CardContent>
          <Typography variant="h6" sx={{ mb: 1 }}>Categorias y subcategorias</Typography>
          <Divider sx={{ mb: 2 }} />
          <Stack spacing={2}>
            {Object.entries(categories).map(([category, subs]) => {
              const categoryColor = CATEGORY_COLORS[category] || '#666'
              const subColor = adjustColor(categoryColor, 0.35)
              return (
                <Box key={category} sx={{ pb: 1 }}>
                  <Typography variant="subtitle2" sx={{ color: '#bbb', textTransform: 'uppercase' }}>
                      <Chip
                        size="small"
                        label={category}
                        sx={{ backgroundColor: categoryColor, color: '#111', fontWeight: 700, mr: 1 }}
                      />
                  </Typography>
                  <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mt: 1, pl: 1 }}>
                    {subs.length ? subs.map((sub) => (
                      <Chip
                        key={sub}
                        label={sub}
                        size="small"
                        onDelete={() => handleDeleteSubcategory(category, sub)}
                        deleteIcon={renderDeleteIcon('#ff6b6b')}
                        sx={{
                          backgroundColor: subColor,
                          color: '#111',
                          fontWeight: 600,
                          mr: 0.5,
                          mb: 0.5,
                          '& .MuiChip-deleteIcon': { m: 0 },
                        }}
                      />
                    )) : (
                      <Typography variant="body2" color="text.secondary" sx={{ py: 0.5 }}>
                        Sin subcategorias registradas.
                      </Typography>
                    )}
                  </Stack>
                </Box>
              )
            })}
          </Stack>
        </CardContent>
      </Card>

      <Snackbar
        open={toast.open}
        autoHideDuration={3000}
        onClose={handleCloseToast}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert onClose={handleCloseToast} severity={toast.severity} variant="filled" sx={{ width: '100%' }}>
          {toast.message}
        </Alert>
      </Snackbar>

      <Dialog
        open={editDescriptionDialog.open}
        onClose={handleCloseDescriptionDialog}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Editar descripcion</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Descripcion"
            fullWidth
            value={editDescriptionDialog.value}
            onChange={(e) => setEditDescriptionDialog((prev) => ({ ...prev, value: e.target.value }))}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDescriptionDialog}>Cancelar</Button>
          <Button variant="contained" onClick={handleSaveDescription}>Guardar</Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={statsOpen}
        onClose={() => setStatsOpen(false)}
        fullScreen
        PaperProps={{
          sx: {
            bgcolor: '#05070f',
            color: '#fff',
            borderRadius: 0,
            border: 'none',
            width: '100vw',
            height: '100vh',
          },
        }}
        BackdropProps={{
          sx: { backgroundColor: 'rgba(0,0,0,0.92)' },
        }}
      >
        <DialogTitle sx={{ borderBottom: '1px solid rgba(255,255,255,0.08)', background: 'linear-gradient(90deg, rgba(7,13,25,0.95), rgba(9,12,18,0.85))' }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between">
            <Typography variant="h6" sx={{ fontWeight: 700 }}>Estadisticas de gastos</Typography>
            <Button color="error" variant="contained" onClick={() => setStatsOpen(false)}>Cerrar</Button>
          </Stack>
        </DialogTitle>
        <DialogContent dividers sx={{ background: 'radial-gradient(circle at top, rgba(21,27,45,0.85), rgba(6,8,14,0.95))', p: 3 }}>
          <Stack spacing={3}>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} justifyContent="flex-end">
              <FormControl size="small" sx={{ minWidth: 160 }}>
                <InputLabel sx={{ color: '#fff', '&.Mui-focused': { color: '#fff' } }}>Año</InputLabel>
                <Select
                  label="Año"
                  value={statsYearFilter}
                  onChange={(e) => setStatsYearFilter(e.target.value)}
                  sx={{
                    color: '#fff',
                    '& .MuiSvgIcon-root': { color: '#fff' },
                    '& .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.3)' },
                    '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: '#fff' },
                    '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: '#fff' },
                  }}
                >
                  {statsYearOptions.map((year) => (
                    <MenuItem key={year} value={year}>{year}</MenuItem>
                  ))}
                </Select>
              </FormControl>
              <FormControl size="small" sx={{ minWidth: 220 }}>
                <InputLabel sx={{ color: '#fff', '&.Mui-focused': { color: '#fff' } }}>Mes</InputLabel>
                <Select
                  label="Mes"
                  value={statsMonthFilter}
                  onChange={(e) => setStatsMonthFilter(e.target.value)}
                  sx={{
                    color: '#fff',
                    '& .MuiSvgIcon-root': { color: '#fff' },
                    '& .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.3)' },
                    '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: '#fff' },
                    '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: '#fff' },
                  }}
                >
                  <MenuItem value="">
                    <em>Todos los meses</em>
                  </MenuItem>
                  {statsMonthOptions.map((monthKey) => {
                    return (
                      <MenuItem key={monthKey} value={monthKey}>
                        {formatMonthKeyLabel(monthKey)}
                      </MenuItem>
                    )
                  })}
                </Select>
              </FormControl>
            </Stack>

            <Card sx={{ background: 'rgba(10,15,29,0.95)', borderRadius: 3, border: '1px solid rgba(255,255,255,0.08)' }}>
              <CardContent>
                <Typography variant="subtitle2" sx={STATS_CARD_TITLE_SX}>Totales generales</Typography>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
                  <Box sx={{ flex: 1 }}>
                    <Typography variant="body2" color="text.secondary">Total general</Typography>
                    <Typography variant="h4" sx={{ fontWeight: 700 }}>{formatCurrency(statsOverview.total)}</Typography>
                    <Typography variant="caption" color="text.secondary">{statsOverview.count} movimientos</Typography>
                  </Box>
                  <Box sx={{ flex: 1 }}>
                    <Typography variant="body2" color="text.secondary">Manual</Typography>
                    <Typography variant="h5" sx={{ fontWeight: 600 }}>{formatCurrency(statsOverview.manual)}</Typography>
                  </Box>
                  <Box sx={{ flex: 1 }}>
                    <Typography variant="body2" color="text.secondary">Banco</Typography>
                    <Typography variant="h5" sx={{ fontWeight: 600 }}>{formatCurrency(statsOverview.bank)}</Typography>
                  </Box>
                </Stack>
              </CardContent>
            </Card>

            <Stack direction={{ xs: 'column', lg: 'row' }} spacing={3}>
              <Card sx={{ flex: 1, background: 'rgba(13,16,28,0.92)', borderRadius: 3, border: '1px solid rgba(255,255,255,0.05)' }}>
                <CardContent>
                  <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
                    <Typography variant="subtitle2" sx={STATS_CARD_TITLE_SX}>Distribucion por categoria</Typography>
                    {statsSelectedCategory && (
                      <Chip
                        label={`Filtrado: ${statsSelectedCategory}`}
                        size="small"
                        onDelete={() => setStatsSelectedCategory('')}
                        deleteIcon={renderDeleteIcon('#ff6b6b')}
                        sx={{
                          backgroundColor: adjustColor(CATEGORY_COLORS[statsSelectedCategory] || '#fff', 0.4),
                          color: '#111',
                          fontWeight: 600,
                        }}
                      />
                    )}
                  </Stack>
                  {categorySummary.length ? (
                    <Box sx={{ height: 360 }}>
                      <Doughnut
                        ref={categoryChartRef}
                        data={categoryChartData}
                        options={categoryChartOptions}
                        onClick={handleCategoryChartClick}
                      />
                    </Box>
                  ) : (
                    <Typography variant="body2" color="text.secondary">Sin datos disponibles.</Typography>
                  )}
                </CardContent>
              </Card>
              <Card sx={{ flex: 1.2, background: 'rgba(13,16,28,0.92)', borderRadius: 3, border: '1px solid rgba(255,255,255,0.05)' }}>
                <CardContent>
                  <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                    <Typography variant="subtitle2" sx={STATS_CARD_TITLE_SX}>Top subcategorias</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {statsSelectedCategory ? `Solo ${statsSelectedCategory}` : 'Todas las categorias'}
                    </Typography>
                  </Stack>
                  {topSubcategorySummary.length ? (
                    <Box sx={{ height: 360 }}>
                      <Bar data={subcategoryChartData} options={subcategoryChartOptions} />
                    </Box>
                  ) : (
                    <Typography variant="body2" color="text.secondary">Sin datos disponibles.</Typography>
                  )}
                </CardContent>
              </Card>
            </Stack>

            <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
              <Card sx={{ flex: 1, background: 'rgba(13,16,28,0.92)', borderRadius: 3, border: '1px solid rgba(255,255,255,0.05)' }}>
                <CardContent>
                  <Typography variant="subtitle2" sx={STATS_CARD_TITLE_SX}>Categorias</Typography>
                  {categorySummary.length ? (
                    <Table size="small" sx={{ '& th, & td': { borderColor: 'rgba(255,255,255,0.08)' } }}>
                      <TableHead>
                        <TableRow>
                          <TableCell>Categoria</TableCell>
                          <TableCell align="right">Monto</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {categorySummary.map(([name, amount]) => (
                          <TableRow key={name}>
                            <TableCell>{name}</TableCell>
                            <TableCell align="right">{formatCurrency(amount)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  ) : (
                    <Typography variant="body2" color="text.secondary">Sin datos disponibles.</Typography>
                  )}
                </CardContent>
              </Card>
              <Card sx={{ flex: 1, background: 'rgba(13,16,28,0.92)', borderRadius: 3, border: '1px solid rgba(255,255,255,0.05)' }}>
                <CardContent>
                  <Typography variant="subtitle2" sx={STATS_CARD_TITLE_SX}>Gasto mensual</Typography>
                  {monthlySummary.length ? (
                    <Table size="small" sx={{ '& th, & td': { borderColor: 'rgba(255,255,255,0.08)' } }}>
                      <TableHead>
                        <TableRow>
                          <TableCell>Mes</TableCell>
                          <TableCell align="right">Monto</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {monthlySummary.map(([monthKey, amount]) => {
                          const label = formatMonthKeyLabel(monthKey) || 'Sin fecha'
                          return (
                            <TableRow key={monthKey || `month-${label}`}>
                              <TableCell>{label}</TableCell>
                              <TableCell align="right">{formatCurrency(amount)}</TableCell>
                            </TableRow>
                          )
                        })}
                      </TableBody>
                    </Table>
                  ) : (
                    <Typography variant="body2" color="text.secondary">Sin datos disponibles.</Typography>
                  )}
                </CardContent>
              </Card>
            </Stack>
          </Stack>
        </DialogContent>
      </Dialog>
    </Box>
  )
}
