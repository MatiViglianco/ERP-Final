import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  InputAdornment,
  LinearProgress,
  Pagination,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
  useMediaQuery,
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import DeleteIcon from '@mui/icons-material/Delete'
import EditIcon from '@mui/icons-material/Edit'
import FilterAltIcon from '@mui/icons-material/FilterAlt'
import Inventory2OutlinedIcon from '@mui/icons-material/Inventory2Outlined'
import SearchIcon from '@mui/icons-material/Search'
import WhatsAppIcon from '@mui/icons-material/WhatsApp'
import InsightsIcon from '@mui/icons-material/Insights'
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline'
import { useAuth } from '../context/AuthContext.jsx'

const API_ACCOUNTS = 'http://localhost:8000/api/accounts/clients/'
const API_ACCOUNT_DETAIL = (id) => `http://localhost:8000/api/accounts/clients/${id}/`
const API_ACCOUNT_PAY = (id) => `http://localhost:8000/api/accounts/clients/${id}/pay/`
const API_ACCOUNT_TX_CREATE = (id) => `http://localhost:8000/api/accounts/clients/${id}/transactions/`
const API_ACCOUNT_TX_DELETE = (txId) => `http://localhost:8000/api/accounts/transactions/${txId}/`
const API_ACCOUNT_STATS = 'http://localhost:8000/api/accounts/clients/stats/'

const statusFilters = [
  { value: 'all', label: 'Todos' },
  { value: 'active', label: 'Activo' },
  { value: 'partial', label: 'Parcial' },
  { value: 'overdue', label: 'Vencido' },
  { value: 'paid', label: 'Pagado' },
]

const clientStatusColors = {
  active: 'warning',
  partial: 'info',
  overdue: 'error',
  paid: 'success',
}

const transactionStatusColors = {
  activo: 'warning',
  parcial: 'info',
  vencido: 'error',
  pagado: 'success',
}
const transactionStatusFilterMap = {
  active: 'activo',
  partial: 'parcial',
  overdue: 'vencido',
  paid: 'pagado',
}

const CLIENT_PAGE_SIZE = 10
const TX_PAGE_SIZE = 30
const TX_FETCH_LIMIT = 5000
const COUNTRY_CODE_PREFIX = '+54'
const STATS_MONTH_PAGE_SIZE = 12
const STATS_DAYS_PER_PAGE = 3
const SPANISH_MONTHS = [
  { value: '1', label: 'Enero' },
  { value: '2', label: 'Febrero' },
  { value: '3', label: 'Marzo' },
  { value: '4', label: 'Abril' },
  { value: '5', label: 'Mayo' },
  { value: '6', label: 'Junio' },
  { value: '7', label: 'Julio' },
  { value: '8', label: 'Agosto' },
  { value: '9', label: 'Septiembre' },
  { value: '10', label: 'Octubre' },
  { value: '11', label: 'Noviembre' },
  { value: '12', label: 'Diciembre' },
]
const todayISODate = () => new Date().toISOString().split('T')[0]

const toLocalDate = (dateStr) => {
  if (!dateStr) return null
  const parts = dateStr.split('-').map((p) => Number(p))
  if (parts.length !== 3 || parts.some(Number.isNaN)) {
    const parsed = new Date(dateStr)
    return Number.isNaN(parsed.getTime()) ? null : parsed
  }
  return new Date(parts[0], parts[1] - 1, parts[2])
}

const getRemainingValue = (tx) => {
  if (!tx) return 0
  if (typeof tx.remaining === 'number') return Math.max(0, tx.remaining)
  if (typeof tx.remaining_amount === 'number') return Math.max(0, tx.remaining_amount)
  const original = typeof tx.original === 'number' ? tx.original : 0
  const paid = typeof tx.paid === 'number' ? tx.paid : 0
  return Math.max(0, original - paid)
}

function formatCurrency(value) {
  return `$ ${Number(value || 0).toLocaleString('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

const formatPhoneDisplay = (phone) => {
  if (!phone) return ''
  let value = phone.replace(/\s+/g, '').trim()
  if (!value) return ''
  if (value.startsWith('+')) {
    return value.startsWith(COUNTRY_CODE_PREFIX) ? value : value
  }
  value = value.replace(/[^\d]/g, '')
  if (!value) return ''
  if (value.startsWith('54')) return `+${value}`
  return `${COUNTRY_CODE_PREFIX}${value}`
}

const normalizePhoneDigits = (phone) => {
  if (!phone) return ''
  const digits = phone.replace(/\D/g, '')
  if (!digits) return ''
  if (digits.startsWith('54')) return digits
  return `54${digits}`
}

function initials(name) {
  if (!name) return '?'
  const parts = name.split(/[\s,]+/).filter(Boolean)
  if (!parts.length) return '?'
  if (parts.length === 1) return parts[0][0]?.toUpperCase() || '?'
  return (parts[0][0] + parts[1][0]).toUpperCase()
}

export default function AccountsPage() {
  const { authFetch } = useAuth()
  const [clients, setClients] = useState([])
  const [clientCount, setClientCount] = useState(0)
  const [clientPage, setClientPage] = useState(0)
  const [clientsLoading, setClientsLoading] = useState(true)
  const [clientError, setClientError] = useState('')
  const [search, setSearch] = useState('')
  const [ordering, setOrdering] = useState('last_name')
  const [statusFilter, setStatusFilter] = useState('all')

  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const [txPage, setTxPage] = useState(0)

  const [selectedTransactions, setSelectedTransactions] = useState(new Set())
  const [actionLoading, setActionLoading] = useState(false)
  const [actionError, setActionError] = useState('')

  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [editForm, setEditForm] = useState({ first_name: '', last_name: '', phone: '' })
  const [newClientDialogOpen, setNewClientDialogOpen] = useState(false)
  const [newClientForm, setNewClientForm] = useState({ first_name: '', last_name: '', phone: '' })
  const [newClientError, setNewClientError] = useState('')
  const [newClientLoading, setNewClientLoading] = useState(false)
  const [statsDialogOpen, setStatsDialogOpen] = useState(false)
  const [statsLoading, setStatsLoading] = useState(false)
  const [statsError, setStatsError] = useState('')
  const [statsData, setStatsData] = useState([])
  const [statsYearTotals, setStatsYearTotals] = useState({ original: 0, remaining: 0 })
  const [statsTopClients, setStatsTopClients] = useState([])
  const [statsDaysPages, setStatsDaysPages] = useState({})
  const currentYear = new Date().getFullYear()
  const [statsFilters, setStatsFilters] = useState({ year: String(currentYear), month: '', day: '' })
  const statsTwoColumnLayout = useMediaQuery('(min-width:900px)')
  const isMobile = useMediaQuery('(max-width:900px)')
  const [confirmSelectedOpen, setConfirmSelectedOpen] = useState(false)
  const [confirmSelectedAmount, setConfirmSelectedAmount] = useState('')
  const [confirmSelectedError, setConfirmSelectedError] = useState('')
  const [newExpenseOpen, setNewExpenseOpen] = useState(false)
  const [newExpenseForm, setNewExpenseForm] = useState(() => ({ date: todayISODate(), amount: '', description: '' }))
  const [newExpenseError, setNewExpenseError] = useState('')
  const [newExpenseLoading, setNewExpenseLoading] = useState(false)
  const [whatsappLoadingId, setWhatsappLoadingId] = useState(null)

  const fetchClients = useCallback(async () => {
    setClientsLoading(true)
    setClientError('')
    try {
      const params = new URLSearchParams({
        limit: String(CLIENT_PAGE_SIZE),
        offset: String(clientPage * CLIENT_PAGE_SIZE),
        ordering,
      })
      if (search.trim()) params.set('search', search.trim())
      const resp = await authFetch(`${API_ACCOUNTS}?${params.toString()}`)
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo cargar la lista')
      setClients(data.results || [])
      setClientCount(data.count || 0)
      if (selectedId) {
        const exists = data.results?.some((client) => client.id === selectedId)
        if (!exists) setSelectedId(null)
      }
    } catch (err) {
      setClientError(err.message)
      setClients([])
    } finally {
      setClientsLoading(false)
    }
  }, [authFetch, clientPage, ordering, search, selectedId])

  useEffect(() => {
    fetchClients()
  }, [fetchClients])

  const fetchDetail = useCallback(async () => {
    if (!selectedId) {
      setDetail(null)
      return
    }
    setDetailLoading(true)
    setDetailError('')
    try {
      const params = new URLSearchParams({
        limit: String(TX_FETCH_LIMIT),
        offset: '0',
      })
      const resp = await authFetch(`${API_ACCOUNT_DETAIL(selectedId)}?${params.toString()}`)
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo obtener el detalle')
      setDetail(data)
      setSelectedTransactions(new Set())
    } catch (err) {
      setDetailError(err.message)
      setDetail(null)
    } finally {
      setDetailLoading(false)
    }
  }, [authFetch, selectedId])

  useEffect(() => {
    fetchDetail()
  }, [fetchDetail])

  useEffect(() => {
    setTxPage(0)
  }, [selectedId])

  useEffect(() => {
    setTxPage(0)
  }, [statusFilter])

  const selectedClient = detail?.client
  const transactions = detail?.transactions || []
  const totals = detail?.totals || { original: 0, paid: 0, remaining: 0 }
  const selectableTransactionIds = useMemo(
    () => transactions.filter((tx) => getRemainingValue(tx) > 0).map((tx) => tx.id),
    [transactions],
  )

  const txStatusSummary = useMemo(() => {
    const summary = { all: transactions.length, active: 0, partial: 0, overdue: 0, paid: 0 }
    transactions.forEach((tx) => {
      const statusKey = (tx.status || tx.status_label || '').toLowerCase()
      Object.entries(transactionStatusFilterMap).forEach(([filterKey, value]) => {
        if (statusKey === value) summary[filterKey] += 1
      })
    })
    return summary
  }, [transactions])

  const filteredTransactions = useMemo(() => {
    if (!statusFilter || statusFilter === 'all') return transactions
    const target = transactionStatusFilterMap[statusFilter]
    if (!target) return transactions
    return transactions.filter((tx) => {
      const statusKey = (tx.status || '').toLowerCase()
      const labelKey = (tx.status_label || '').toLowerCase()
      return statusKey === target || labelKey === target
    })
  }, [transactions, statusFilter])

  const clientTotalPages = Math.max(1, Math.ceil(clientCount / CLIENT_PAGE_SIZE))
  const txTotalPages = Math.max(1, Math.ceil(filteredTransactions.length / TX_PAGE_SIZE))
  const paginatedTransactions = useMemo(
    () => filteredTransactions.slice(txPage * TX_PAGE_SIZE, txPage * TX_PAGE_SIZE + TX_PAGE_SIZE),
    [filteredTransactions, txPage],
  )

  const handleSelectClient = (id) => {
    setSelectedId(id)
  }

  const handleOrdering = (_e, value) => {
    if (value) {
      setOrdering(value)
      setClientPage(0)
    }
  }

  const handleStatusChip = (value) => {
    setStatusFilter(value)
  }

  const handleSearchChange = (e) => {
    setSearch(e.target.value)
    setClientPage(0)
  }

  const handleToggleTransaction = (id, disabled) => {
    if (disabled) return
    setSelectedTransactions((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const handleToggleMonth = (group) => {
    if (!group?.selectableIds?.length) return
    const allSelected = group.selectableIds.every((id) => selectedTransactions.has(id))
    setSelectedTransactions((prev) => {
      const next = new Set(prev)
      if (allSelected) {
        group.selectableIds.forEach((id) => next.delete(id))
      } else {
        group.selectableIds.forEach((id) => next.add(id))
      }
      return next
    })
  }

  const openEditDialog = () => {
    if (!selectedClient) return
    setEditForm({
      first_name: selectedClient.first_name || '',
      last_name: selectedClient.last_name || '',
      phone: formatPhoneDisplay(selectedClient.phone || ''),
    })
    setEditDialogOpen(true)
  }

  const openNewClientDialog = () => {
    setNewClientForm({ first_name: '', last_name: '', phone: '' })
    setNewClientError('')
    setNewClientDialogOpen(true)
  }

  const closeNewClientDialog = () => {
    if (newClientLoading) return
    setNewClientDialogOpen(false)
  }

  const handleCreateClient = async () => {
    const first = newClientForm.first_name.trim()
    const last = newClientForm.last_name.trim()
    if (first.length < 2 || last.length < 2) {
      setNewClientError('Apellido y nombre deben tener al menos 2 caracteres.')
      return
    }
    setNewClientLoading(true)
    setNewClientError('')
    try {
      const payload = {
        first_name: first,
        last_name: last,
        phone: newClientForm.phone.trim() ? formatPhoneDisplay(newClientForm.phone) : '',
      }
      const resp = await authFetch(API_ACCOUNTS, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok) throw new Error(data.detail || 'No se pudo crear el cliente')
      setNewClientDialogOpen(false)
      setNewClientForm({ first_name: '', last_name: '', phone: '' })
      fetchClients()
      if (data.id) {
        setSelectedId(data.id)
      }
    } catch (err) {
      setNewClientError(err.message)
    } finally {
      setNewClientLoading(false)
    }
  }

  const submitEdit = async () => {
    if (!selectedId) return
    setActionError('')
    setActionLoading(true)
    try {
      const payload = {
        ...editForm,
        phone: formatPhoneDisplay(editForm.phone),
      }
      const resp = await authFetch(API_ACCOUNT_DETAIL(selectedId), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo actualizar el cliente')
      setEditDialogOpen(false)
      fetchClients()
      fetchDetail()
    } catch (err) {
      setActionError(err.message)
    } finally {
      setActionLoading(false)
    }
  }

  const deleteClient = async () => {
    if (!selectedId) return
    if (!window.confirm('¿Eliminar el cliente y todos sus registros?')) return
    setActionError('')
    setActionLoading(true)
    try {
      const resp = await authFetch(API_ACCOUNT_DETAIL(selectedId), { method: 'DELETE' })
      if (resp.status !== 204 && !resp.ok) {
        const data = await resp.json().catch(() => ({}))
        throw new Error(data.detail || 'No se pudo eliminar')
      }
      setSelectedId(null)
      setDetail(null)
      fetchClients()
    } catch (err) {
      setActionError(err.message)
    } finally {
      setActionLoading(false)
    }
  }

  const executePayment = async (payload) => {
    if (!selectedId) return
    setActionError('')
    setActionLoading(true)
    try {
      const resp = await authFetch(API_ACCOUNT_PAY(selectedId), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok) throw new Error(data.detail || 'No se pudo registrar el pago')
      setSelectedTransactions(new Set())
      fetchClients()
      fetchDetail()
    } catch (err) {
      setActionError(err.message)
    } finally {
      setActionLoading(false)
    }
  }

  const handlePaySelected = () => {
    if (!selectedTransactions.size) return
    setConfirmSelectedAmount('')
    setConfirmSelectedError('')
    setConfirmSelectedOpen(true)
  }

  const handlePayAll = () => {
    if (!selectableTransactionIds.length) return
    setSelectedTransactions(new Set(selectableTransactionIds))
    setConfirmSelectedAmount('')
    setConfirmSelectedError('')
    setConfirmSelectedOpen(true)
  }

  const selectedSummary = useMemo(() => {
    if (!transactions.length || !selectedTransactions.size) return null
    const selected = transactions.filter((tx) => selectedTransactions.has(tx.id))
    if (!selected.length) return null
    const total = selected.reduce((acc, tx) => acc + getRemainingValue(tx), 0)
    const dates = selected
      .map((tx) => (tx.date ? toLocalDate(tx.date) : null))
      .filter(Boolean)
      .sort((a, b) => a - b)
    return {
      count: selected.length,
      total,
      from: dates[0] || null,
      to: dates[dates.length - 1] || null,
    }
  }, [selectedTransactions, transactions])

        const buildWhatsappMessage = (client, pending) => {
    const name = client?.full_name || client?.first_name || 'cliente'
    if (!pending.length) {
      return `Hola ${name}! Actualmente no registramos deudas pendientes en tu cuenta.`
    }
    const lines = pending
      .map((tx) => {
        const dateObj = tx.date ? toLocalDate(tx.date) : null
        const date = dateObj ? dateObj.toLocaleDateString('es-AR') : 'Sin fecha'
        const desc = tx.description && tx.description.trim() ? tx.description : 'Gasto de'
        const remaining = formatCurrency(getRemainingValue(tx))
        return `• ${date} - ${desc}: ${remaining}`
      })
      .join('\n')
    const total = pending.reduce((acc, tx) => acc + getRemainingValue(tx), 0)
    const totalWithSurcharge = total * 1.1
    return `Hola ${name}! Te compartimos el detalle de tus movimientos pendientes:
${lines}
Total adeudado: ${formatCurrency(total)}.
Total con recargo 10% (si pagas despues del 10): ${formatCurrency(totalWithSurcharge)}.
Recorda que despues del dia 10 se aplica un recargo del 10%, asi que sumale ese extra al total si corresponde.
Avisanos cuando puedas cancelar o si necesitas ayuda.`
  }
const handleWhatsappMessage = async (client) => {
    if (!client?.phone) return
    const phoneDigits = normalizePhoneDigits(client.phone)
    if (!phoneDigits) {
      setActionError('El número de WhatsApp no es válido.')
      return
    }
    setActionError('')
    setWhatsappLoadingId(client.id)
    try {
      const params = new URLSearchParams({ limit: '500', offset: '0' })
      const resp = await authFetch(`${API_ACCOUNT_DETAIL(client.id)}?${params.toString()}`)
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo obtener el detalle para WhatsApp')
      const pending = (data.transactions || []).filter((tx) => getRemainingValue(tx) > 0)
      const message = buildWhatsappMessage(data.client || client, pending)
      const url = `https://wa.me/${phoneDigits}?text=${encodeURIComponent(message)}`
      window.open(url, '_blank', 'noopener,noreferrer')
    } catch (err) {
      setActionError(err.message)
    } finally {
      setWhatsappLoadingId(null)
    }
  }


  const transactionsByMonth = useMemo(() => {
    if (!paginatedTransactions.length) return []
    const groups = []
    let currentKey = null
    let currentGroup = null
    paginatedTransactions.forEach((tx) => {
      const dateObj = tx.date ? toLocalDate(tx.date) : null
      const key = dateObj ? `${dateObj.getFullYear()}-${String(dateObj.getMonth() + 1).padStart(2, '0')}` : 'sin-fecha'
      if (!currentGroup || currentKey !== key) {
        currentKey = key
        currentGroup = {
          key,
          label: dateObj
            ? dateObj.toLocaleDateString('es-AR', { month: 'long', year: 'numeric' })
            : 'Sin fecha',
          total: 0,
          transactions: [],
          selectableIds: [],
        }
        groups.push(currentGroup)
      }
      currentGroup.transactions.push(tx)
      const remaining = getRemainingValue(tx)
      currentGroup.total += remaining
      if (remaining > 0) {
        currentGroup.selectableIds.push(tx.id)
      }
    })
    return groups
  }, [paginatedTransactions])

  const confirmPaySelected = () => {
    const payload = { mode: 'selected', transaction_ids: Array.from(selectedTransactions) }
    if (confirmSelectedAmount.trim()) {
      const amountNumber = Number(confirmSelectedAmount)
      if (!amountNumber || amountNumber <= 0) {
        setConfirmSelectedError('El monto debe ser mayor a cero')
        return
      }
      payload.amount = amountNumber
    }
    setConfirmSelectedError('')
    setConfirmSelectedOpen(false)
    setConfirmSelectedAmount('')
    executePayment(payload)
  }

  const openNewExpenseDialog = () => {
    if (!selectedClient) return
    setNewExpenseForm({ date: todayISODate(), amount: '', description: '' })
    setNewExpenseError('')
    setNewExpenseOpen(true)
  }

  const closeNewExpenseDialog = () => {
    if (newExpenseLoading) return
    setNewExpenseOpen(false)
    setNewExpenseError('')
  }

  const handleCreateExpense = async () => {
    if (!selectedId) return
    if (!newExpenseForm.date) {
      setNewExpenseError('Debes indicar la fecha del movimiento.')
      return
    }
    const amountNumber = Number(newExpenseForm.amount)
    if (!amountNumber || amountNumber <= 0) {
      setNewExpenseError('El monto debe ser mayor a cero.')
      return
    }
    setNewExpenseLoading(true)
    setNewExpenseError('')
    try {
      const payload = {
        date: newExpenseForm.date,
        amount: amountNumber,
      }
      const cleanDescription = (newExpenseForm.description || '').trim()
      if (cleanDescription) payload.description = cleanDescription
      const resp = await authFetch(API_ACCOUNT_TX_CREATE(selectedId), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const raw = await resp.text()
      const data = raw ? (() => { try { return JSON.parse(raw) } catch { return {} } })() : {}
      if (!resp.ok) {
        const detail = data.detail || data.message || raw || `Error ${resp.status}`
        throw new Error(typeof detail === 'string' ? detail : 'No se pudo registrar el gasto')
      }
      setNewExpenseOpen(false)
      setNewExpenseForm({ date: todayISODate(), amount: '', description: '' })
      fetchClients()
      fetchDetail()
    } catch (err) {
      setNewExpenseError(err.message)
    } finally {
      setNewExpenseLoading(false)
    }
  }

  const handleDeleteTransaction = async (txId) => {
    if (!txId) return
    if (!window.confirm('¿Eliminar esta transacción?')) return
    setActionError('')
    setActionLoading(true)
    try {
      const resp = await authFetch(API_ACCOUNT_TX_DELETE(txId), { method: 'DELETE' })
      if (resp.status !== 204 && !resp.ok) {
        const data = await resp.json().catch(() => ({}))
        throw new Error(data.detail || 'No se pudo eliminar la transacción')
      }
      setSelectedTransactions((prev) => {
        const next = new Set(prev)
        next.delete(txId)
        return next
      })
      fetchClients()
      fetchDetail()
    } catch (err) {
      setActionError(err.message)
    } finally {
      setActionLoading(false)
    }
  }

  const disablePayments = actionLoading || !selectedClient
  const isMonthFiltered = Boolean(statsFilters.month)
  const isDayFiltered = isMonthFiltered && Boolean(statsFilters.day)

  const fetchStats = useCallback(async (filtersOverride = null) => {
    setStatsLoading(true)
    setStatsError('')
    try {
      const filters = filtersOverride || statsFilters
      const params = new URLSearchParams({
        page: '1',
        page_size: String(STATS_MONTH_PAGE_SIZE),
      })
      if (filters.year) params.set('year', filters.year)
      if (filters.month) params.set('month', filters.month)
      if (filters.day) params.set('day', filters.day)
      const resp = await authFetch(`${API_ACCOUNT_STATS}?${params.toString()}`)
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok) throw new Error(data?.detail || 'No se pudieron obtener las estadísticas')
      const results = Array.isArray(data.results) ? data.results : []
      setStatsData(results)
      setStatsYearTotals({
        original: Number(data.year_totals?.original || 0),
        remaining: Number(data.year_totals?.remaining || 0),
      })
      setStatsTopClients(Array.isArray(data.top_clients) ? data.top_clients : [])
      setStatsDaysPages({})
    } catch (err) {
      setStatsError(err.message)
      setStatsData([])
      setStatsYearTotals({ original: 0, remaining: 0 })
      setStatsTopClients([])
      setStatsDaysPages({})
    } finally {
      setStatsLoading(false)
    }
  }, [authFetch, statsFilters])

  const openStatsDialog = () => {
    setStatsDialogOpen(true)
    fetchStats()
  }

  const handleStatsFilterChange = (field, value) => {
    setStatsFilters((prev) => {
      const updated = { ...prev, [field]: value }
      fetchStats(updated)
      return updated
    })
  }

  const handleResetStatsFilters = () => {
    const resetFilters = { year: String(currentYear), month: '', day: '' }
    setStatsFilters(resetFilters)
    fetchStats(resetFilters)
  }

  const handleDayPageChange = (monthKey, value) => {
    setStatsDaysPages((prev) => ({ ...prev, [monthKey]: value }))
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3, py: 4 }}>
      <Stack
        direction={{ xs: 'column', md: 'row' }}
        spacing={2}
        sx={{ alignItems: 'stretch', minHeight: { md: 'calc(100vh - 120px)' } }}
      >
        <Card
          sx={{
            flexBasis: { xs: '100%', md: '35%' },
            flexShrink: 0,
            background: 'rgba(15,15,20,0.9)',
            borderRadius: 3,
            display: 'flex',
            flexDirection: 'column',
            height: { xs: 'auto', md: '100%' },
            minHeight: { md: 'calc(100vh - 120px)' },
          }}
        >
          <CardContent sx={{ display: 'flex', flexDirection: 'column', gap: 1.25, flexGrow: 1, minHeight: 0, height: '100%' }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Typography variant="h6">Clientes</Typography>
              <Stack direction="row" spacing={1}>
                <Button size="small" variant="contained" color="info" onClick={openStatsDialog} startIcon={<InsightsIcon />}>
                  Estadísticas
                </Button>
                <Button size="small" variant="contained" startIcon={<AddIcon />} onClick={openNewClientDialog}>
                  Nuevo cliente
                </Button>
              </Stack>
            </Stack>
            <TextField
              size="small"
              placeholder="Buscar cliente..."
              value={search}
              onChange={handleSearchChange}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon fontSize="small" />
                  </InputAdornment>
                )
              }}
            />
            <ToggleButtonGroup
              exclusive
              size="small"
              value={ordering}
              onChange={handleOrdering}
            >
              <ToggleButton value="last_name">Ordenar por apellido</ToggleButton>
              <ToggleButton value="debt">Ordenar por deuda</ToggleButton>
            </ToggleButtonGroup>
            {clientError && <Alert severity="error">{clientError}</Alert>}
            {clientsLoading && <LinearProgress />}
            <Stack spacing={0.75} sx={{ flexGrow: 1, minHeight: { xs: 0, md: 520 }, overflowY: 'auto', pr: 1 }}>
              {clients.map((client) => (
                <Box
                  key={client.id}
                  onClick={() => handleSelectClient(client.id)}
                  sx={{
                    borderRadius: 2,
                    border: client.id === selectedId ? '1px solid rgba(120,119,198,0.7)' : '1px solid rgba(255,255,255,0.05)',
                    backgroundColor: client.id === selectedId ? 'rgba(120,119,198,0.1)' : 'transparent',
                    p: 0.75,
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                    '&:hover': { borderColor: 'rgba(120,119,198,0.5)' },
                  }}
                >
                  <Stack direction="row" spacing={1.5} alignItems="center">
                    <Avatar sx={{ width: 38, height: 38, bgcolor: 'rgba(120,119,198,0.2)', color: '#fff', fontSize: '0.95rem' }}>
                      {initials(client.full_name)}
                    </Avatar>
                    <Box sx={{ flexGrow: 1 }}>
                      <Typography sx={{ fontWeight: 600, fontSize: '0.95rem' }}>{client.full_name}</Typography>
                      <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mt: 0.25 }}>
                        <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.2 }}>
                          Deuda: {formatCurrency(client.total_debt)}
                        </Typography>
                        <Chip
                          size="small"
                          label={client.status_label}
                          color={clientStatusColors[client.status] || 'default'}
                        />
                      </Stack>
                    </Box>
                    <Stack direction="row" spacing={0.75} alignItems="center">
                      {client.phone && (
                        <IconButton
                          size="small"
                          onClick={(e) => {
                            e.stopPropagation()
                            handleWhatsappMessage(client)
                          }}
                          disabled={whatsappLoadingId === client.id}
                          aria-label="Enviar WhatsApp"
                        >
                          <WhatsAppIcon fontSize="small" sx={{ color: '#25D366' }} />
                        </IconButton>
                      )}
                      <IconButton size="small" onClick={(e) => { e.stopPropagation(); openEditDialog() }}>
                        <EditIcon fontSize="small" />
                      </IconButton>
                      <IconButton size="small" onClick={(e) => { e.stopPropagation(); deleteClient() }}>
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Stack>
                  </Stack>
                </Box>
              ))}
              {!clients.length && !clientsLoading && (
                <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', py: 4 }}>
                  No se encontraron clientes.
                </Typography>
              )}
            </Stack>
            <Pagination
              count={clientTotalPages}
              page={clientPage + 1}
              onChange={(_e, value) => setClientPage(value - 1)}
              size="small"
              sx={{ alignSelf: 'center', mt: 'auto' }}
            />
          </CardContent>
        </Card>

        <Card
          sx={{
            flexGrow: 1,
            background: 'rgba(10,10,15,0.95)',
            borderRadius: 3,
            display: 'flex',
            flexDirection: 'column',
            minHeight: { md: 'calc(100vh - 120px)' },
          }}
        >
          <CardContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, flexGrow: 1, minHeight: 0 }}>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ md: 'center' }} justifyContent="space-between">
              <Box>
                <Typography variant="h5">{selectedClient?.full_name || 'Selecciona un cliente'}</Typography>
                <Typography variant="body2" color="text.secondary">
                {selectedClient ? `Registrado el ${selectedClient.created_at ? toLocalDate(selectedClient.created_at)?.toLocaleDateString('es-AR') : '-'}` : 'Sin cliente seleccionado'}
                </Typography>
                {selectedClient?.phone && (
                  <Typography variant="body2" color="text.secondary">
                    Teléfono: {formatPhoneDisplay(selectedClient.phone)}
                  </Typography>
                )}
                {selectedClient && (
                  <Chip
                    size="small"
                    label={selectedClient.status_label}
                    color={clientStatusColors[selectedClient.status] || 'default'}
                    sx={{ mt: 1 }}
                  />
                )}
              </Box>
              <Stack direction="row" spacing={1}>
                <Button
                  variant="contained"
                  color="success"
                  startIcon={<CheckCircleOutlineIcon />}
                  disabled={disablePayments || !selectableTransactionIds.length}
                  onClick={handlePayAll}
                >
                  Pagar todos los gastos
                </Button>
                <Button
                  variant="contained"
                  color="error"
                  startIcon={<AddIcon />}
                  disabled={!selectedClient || newExpenseLoading}
                  onClick={openNewExpenseDialog}
                >
                  Nuevo gasto
                </Button>
              </Stack>
            </Stack>

            <Divider />

            <Stack direction="row" spacing={1} flexWrap="wrap">
              {statusFilters.map((chip) => (
                <Chip
                  key={chip.value}
                  label={`${chip.label}${txStatusSummary?.[chip.value] !== undefined ? ` (${txStatusSummary[chip.value]})` : ''}`}
                  color={chip.value === statusFilter ? 'primary' : 'default'}
                  onClick={() => handleStatusChip(chip.value)}
                  icon={<FilterAltIcon fontSize="small" />}
                  variant={chip.value === statusFilter ? 'filled' : 'outlined'}
                />
              ))}
            </Stack>

            {actionError && <Alert severity="error">{actionError}</Alert>}
            {detailError && <Alert severity="error">{detailError}</Alert>}
            {detailLoading && <LinearProgress />}

            <Stack
              direction={{ xs: 'column', md: 'row' }}
              spacing={1}
              sx={{ display: { xs: 'flex', md: 'none' } }}
            >
              <Button variant="contained" color="success" disabled={disablePayments || !selectedTransactions.size} onClick={handlePaySelected}>
                Pagar seleccionados
              </Button>
            </Stack>

            {selectedClient && !detailLoading && (
              <>
                {filteredTransactions.length === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    No hay movimientos registrados para este cliente con ese filtro.
                  </Typography>
                ) : isMobile ? (
                  <Stack spacing={1.5} sx={{ mt: 1 }}>
                    {transactionsByMonth.map((group) => (
                      <Box
                        key={group.key}
                        sx={{
                          borderRadius: 2,
                          border: '1px solid rgba(255,255,255,0.08)',
                          backgroundColor: 'rgba(12,12,18,0.9)',
                          p: 1.5,
                        }}
                      >
                        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                          <Typography sx={{ fontWeight: 700, textTransform: 'capitalize' }}>{group.label}</Typography>
                          <Typography variant="body2" color="text.secondary">
                            Total pendiente: {formatCurrency(group.total)}
                          </Typography>
                        </Stack>
                        <Stack spacing={1}>
                          {group.transactions.map((tx) => {
                            const disabled = getRemainingValue(tx) <= 0 || disablePayments
                            return (
                              <Box
                                key={tx.id}
                                sx={{
                                  borderRadius: 1.5,
                                  border: '1px solid rgba(255,255,255,0.06)',
                                  p: 1.25,
                                  backgroundColor: 'rgba(255,255,255,0.02)',
                                }}
                              >
                                <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0.5 }}>
                                  <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                                    {tx.date ? toLocalDate(tx.date)?.toLocaleDateString('es-AR') : '-'}
                                  </Typography>
                                  <Checkbox
                                    size="small"
                                    checked={selectedTransactions.has(tx.id)}
                                    onChange={() => handleToggleTransaction(tx.id, getRemainingValue(tx) <= 0)}
                                    disabled={disabled}
                                    sx={{
                                      cursor: disabled ? 'not-allowed' : 'pointer',
                                      '&.Mui-disabled': { cursor: 'not-allowed', pointerEvents: 'auto' },
                                    }}
                                  />
                                </Stack>
                                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                                  <IconButton
                                    size="small"
                                    color="error"
                                    onClick={() => handleDeleteTransaction(tx.id)}
                                    disabled={actionLoading}
                                  >
                                    <DeleteIcon fontSize="small" />
                                  </IconButton>
                                  <Typography variant="body2" color="text.secondary">
                                    {tx.description && tx.description.trim() ? tx.description : 'Gasto de'}
                                  </Typography>
                                </Stack>
                                <Stack direction="row" justifyContent="space-between" alignItems="center">
                                  <Stack spacing={0.25}>
                                    <Typography variant="caption" color="text.secondary">Original</Typography>
                                    <Typography variant="subtitle2">{formatCurrency(tx.original)}</Typography>
                                  </Stack>
                                  <Stack spacing={0.25} alignItems="flex-end">
                                    <Typography variant="caption" color="text.secondary">Pagado</Typography>
                                    <Typography variant="subtitle2" sx={{ color: '#66ff99' }}>
                                      {formatCurrency(tx.paid)}
                                    </Typography>
                                  </Stack>
                                  <Stack spacing={0.25} alignItems="flex-end">
                                    <Typography variant="caption" color="text.secondary">Restante</Typography>
                                    <Typography variant="subtitle2" sx={{ color: '#ff6b6b' }}>
                                      {formatCurrency(getRemainingValue(tx))}
                                    </Typography>
                                  </Stack>
                                  <Chip
                                    size="small"
                                    label={tx.status_label || tx.status}
                                    color={transactionStatusColors[tx.status] || 'default'}
                                  />
                                </Stack>
                              </Box>
                            )
                          })}
                        </Stack>
                      </Box>
                    ))}
                  </Stack>
                ) : (
                  <Table size="small" sx={{ mt: 1 }}>
                    <TableHead>
                      <TableRow>
                        <TableCell padding="checkbox" />
                        <TableCell>Fecha</TableCell>
                        <TableCell>Descripción</TableCell>
                        <TableCell align="right">Original</TableCell>
                        <TableCell align="right">Pagado</TableCell>
                        <TableCell align="right">Restante</TableCell>
                        <TableCell>Estado</TableCell>
                        <TableCell padding="checkbox" align="right">Seleccionar</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {transactionsByMonth.map((group) => {
                        const monthSelected = group.selectableIds.length > 0 && group.selectableIds.every((id) => selectedTransactions.has(id))
                        const monthIndeterminate = group.selectableIds.some((id) => selectedTransactions.has(id)) && !monthSelected
                        return (
                          <React.Fragment key={group.key}>
                            <TableRow sx={{ backgroundColor: 'rgba(255,255,255,0.03)' }}>
                              <TableCell colSpan={7} sx={{ textTransform: 'capitalize', fontWeight: 600 }}>
                                {group.label} — Total pendiente: {formatCurrency(group.total)}
                              </TableCell>
                              <TableCell align="right">
                                <Checkbox
                                  checked={monthSelected}
                                  indeterminate={monthIndeterminate}
                                  disabled={disablePayments || !group.selectableIds.length}
                                  sx={{
                                    cursor: disablePayments || !group.selectableIds.length ? 'not-allowed' : 'pointer',
                                    '&.Mui-disabled': {
                                      cursor: 'not-allowed',
                                      pointerEvents: 'auto',
                                    },
                                  }}
                                  onChange={() => handleToggleMonth(group)}
                                />
                              </TableCell>
                            </TableRow>
                            {group.transactions.map((tx) => (
                              <TableRow key={tx.id}>
                                <TableCell padding="checkbox">
                                  <IconButton
                                    size="small"
                                    color="error"
                                    onClick={() => handleDeleteTransaction(tx.id)}
                                    disabled={actionLoading}
                                  >
                                    <DeleteIcon fontSize="small" />
                                  </IconButton>
                                </TableCell>
                                <TableCell>{tx.date ? toLocalDate(tx.date)?.toLocaleDateString('es-AR') : '-'}</TableCell>
                                <TableCell>
                                  {tx.description && tx.description.trim()
                                    ? tx.description
                                    : (
                                      <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.55)' }}>
                                        Gasto de
                                      </Typography>
                                    )}
                                </TableCell>
                                <TableCell align="right">{formatCurrency(tx.original)}</TableCell>
                                <TableCell align="right" sx={{ color: '#66ff99' }}>{formatCurrency(tx.paid)}</TableCell>
                                <TableCell align="right" sx={{ color: '#ff6b6b' }}>{formatCurrency(getRemainingValue(tx))}</TableCell>
                                <TableCell>
                                  <Chip
                                    size="small"
                                    label={tx.status_label || tx.status}
                                    color={transactionStatusColors[tx.status] || 'default'}
                                  />
                                </TableCell>
                                <TableCell padding="checkbox" align="right">
                                  <Checkbox
                                    checked={selectedTransactions.has(tx.id)}
                                    onChange={() => handleToggleTransaction(tx.id, getRemainingValue(tx) <= 0)}
                                    disabled={getRemainingValue(tx) <= 0 || disablePayments}
                                    sx={{
                                      cursor: getRemainingValue(tx) <= 0 || disablePayments ? 'not-allowed' : 'pointer',
                                      '&.Mui-disabled': {
                                        cursor: 'not-allowed',
                                        pointerEvents: 'auto',
                                      },
                                    }}
                                  />
                                </TableCell>
                              </TableRow>
                            ))}
                          </React.Fragment>
                        )
                      })}
                    </TableBody>
                  </Table>
                )}

                <Pagination
                  count={txTotalPages}
                  page={txPage + 1}
                  onChange={(_e, value) => setTxPage(value - 1)}
                  size="small"
                  sx={{ alignSelf: 'flex-end', mt: 1 }}
                />

                <Divider sx={{ my: 2 }} />
                <Stack direction="row" justifyContent="space-between" flexWrap="wrap">
                  <Typography variant="subtitle1">Total original: {formatCurrency(totals.original)}</Typography>
                  <Typography variant="subtitle1" color="success.main">Pagado: {formatCurrency(totals.paid)}</Typography>
                  <Typography variant="subtitle1" color="error.main">Restante: {formatCurrency(totals.remaining)}</Typography>
                </Stack>
              </>
            )}

            {!selectedClient && !detailLoading && (
              <Box
                sx={{
                  flexGrow: 1,
                  py: 4,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'flex-start',
                  textAlign: 'center',
                  color: 'text.secondary',
                  gap: 1.5,
                }}
              >
                <Inventory2OutlinedIcon sx={{ fontSize: 56, color: 'rgba(255,255,255,0.25)' }} />
                <Typography variant="h6" color="text.secondary">
                  Selecciona un cliente para ver sus movimientos.
                </Typography>
                <Typography variant="body2" color="text.disabled">
                  O agrega un nuevo cliente para comenzar.
                </Typography>
              </Box>
            )}
          </CardContent>
        </Card>
      </Stack>

      {selectedSummary && !!selectedTransactions.size && (
        <Box
          sx={{
            position: 'fixed',
            right: { xs: 16, md: 32 },
            bottom: { xs: 16, md: 32 },
            zIndex: 1300,
            display: 'flex',
            alignItems: 'center',
            gap: 2,
            px: 3,
            py: 2,
            borderRadius: 3,
            background: 'linear-gradient(135deg, rgba(26,26,36,0.9), rgba(10,10,20,0.75))',
            boxShadow: '0 20px 50px rgba(0,0,0,0.4)',
            border: '1px solid rgba(255,255,255,0.08)',
            backdropFilter: 'blur(6px)',
          }}
        >
          <Stack spacing={0.3}>
            <Typography variant="caption" color="text.secondary">
              Total seleccionado
            </Typography>
            <Typography variant="h6">{formatCurrency(selectedSummary.total)}</Typography>
          </Stack>
          <Button
            variant="contained"
            color="success"
            disabled={disablePayments || !selectedTransactions.size}
            onClick={handlePaySelected}
            sx={{ minWidth: 200 }}
          >
            Pagar seleccionados
          </Button>
        </Box>
      )}

      <Dialog
        open={statsDialogOpen}
        onClose={() => setStatsDialogOpen(false)}
        fullScreen
        sx={{
          '& .MuiPaper-root': {
            background: 'linear-gradient(135deg, rgba(16,16,24,0.98), rgba(24,24,36,0.95))',
            color: '#fff',
            border: '1px solid rgba(255,255,255,0.08)',
          },
        }}
      >
        <DialogTitle
          sx={{
            fontWeight: 700,
            fontSize: '1.4rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 2,
            px: { xs: 2, sm: 4 },
            pt: 2,
            pb: 1,
          }}
        >
          <Typography component="span" sx={{ flexGrow: 1, textAlign: 'center' }}>
            Reporte general de transacciones
          </Typography>
          <Button
            variant="contained"
            color="error"
            size="medium"
            onClick={() => setStatsDialogOpen(false)}
            sx={{
              minWidth: 150,
              borderRadius: 2,
              alignSelf: 'flex-start',
            }}
          >
            Cerrar
          </Button>
        </DialogTitle>
        <DialogContent
          dividers
          sx={{
            display: 'flex',
            flexDirection: 'column',
            gap: 2,
            height: '100%',
          }}
        >
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ md: 'flex-end' }}>
            <TextField
              label="Año"
              type="number"
              value={statsFilters.year}
              onChange={(e) => handleStatsFilterChange('year', e.target.value)}
              InputProps={{ inputProps: { min: 2000 } }}
              sx={{ maxWidth: 160 }}
            />
            <TextField
              label="Mes"
              select
              value={statsFilters.month}
              onChange={(e) => handleStatsFilterChange('month', e.target.value)}
              sx={{ maxWidth: 200 }}
              SelectProps={{ native: true }}
              InputLabelProps={{ shrink: true }}
            >
              <option value="">Todos los meses</option>
              {SPANISH_MONTHS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </TextField>
            {statsFilters.month && (
              <TextField
                label="Día"
                type="number"
                value={statsFilters.day}
                onChange={(e) => handleStatsFilterChange('day', e.target.value)}
                InputProps={{ inputProps: { min: 1, max: 31 } }}
                sx={{ maxWidth: 140 }}
              />
            )}
            <Button variant="text" color="inherit" onClick={handleResetStatsFilters} sx={{ alignSelf: { xs: 'flex-start', md: 'center' } }}>
              Restablecer
            </Button>
          </Stack>
          {statsLoading && <LinearProgress />}
          {statsError && <Alert severity="error">{statsError}</Alert>}
          {!statsLoading && !statsError && (
            <Stack spacing={2}>
              {!isMonthFiltered && (
                <Card sx={{ background: 'rgba(255,255,255,0.05)' }}>
                  <CardContent>
                    <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>Totales del año</Typography>
                    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                      <Box>
                        <Typography variant="body2" color="text.secondary">Original</Typography>
                        <Typography variant="h6">{formatCurrency(statsYearTotals.original)}</Typography>
                      </Box>
                      <Box>
                        <Typography variant="body2" color="text.secondary">Debe</Typography>
                        <Typography variant="h6" color="error.main">{formatCurrency(statsYearTotals.remaining)}</Typography>
                      </Box>
                    </Stack>
                  </CardContent>
                </Card>
              )}
              {!isDayFiltered && !!statsTopClients.length && (
                <Card sx={{ background: 'rgba(255,255,255,0.04)' }}>
                  <CardContent>
                    <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>Top 8 clientes por consumo</Typography>
                    <Stack spacing={1}>
                      {(() => {
                        const maxValue = statsTopClients.reduce((acc, item) => Math.max(acc, item.original || 0), 1)
                        return statsTopClients.map((item) => (
                          <Box key={item.client} sx={{ display: 'flex', flexDirection: 'column', gap: 0.3 }}>
                            <Stack direction="row" justifyContent="space-between">
                              <Typography variant="body2">{item.client}</Typography>
                              <Typography variant="body2" color="text.secondary">{formatCurrency(item.original)}</Typography>
                            </Stack>
                            <Box sx={{ width: '100%', height: 8, borderRadius: 999, background: 'rgba(255,255,255,0.08)' }}>
                              <Box
                                sx={{
                                  width: `${Math.min(100, (item.original / maxValue) * 100)}%`,
                                  height: '100%',
                                  borderRadius: 999,
                                  background: 'linear-gradient(90deg, #7c4dff, #00c9ff)',
                                }}
                              />
                            </Box>
                          </Box>
                        ))
                      })()}
                    </Stack>
                  </CardContent>
                </Card>
              )}
            </Stack>
          )}
          {!statsLoading && !statsError && !statsData.length && (
            <Typography variant="body2" color="text.secondary">
              No hay movimientos registrados en el período seleccionado.
            </Typography>
          )}
          {statsData.map((month, idx) => {
            const monthKey = month.month || month.key || `month-${idx}`
            const totalDayPages = Math.max(1, Math.ceil((month.days?.length || 0) / STATS_DAYS_PER_PAGE))
            const storedPage = statsDaysPages[monthKey] || 1
            const currentDayPage = Math.min(Math.max(storedPage, 1), totalDayPages)
            const startDayIdx = (currentDayPage - 1) * STATS_DAYS_PER_PAGE
            const visibleDays = (month.days || []).slice(startDayIdx, startDayIdx + STATS_DAYS_PER_PAGE)
            return (
            <Box key={monthKey} sx={{ borderRadius: 3, border: '1px solid rgba(255,255,255,0.08)', p: 2, background: 'rgba(255,255,255,0.02)' }}>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 700 }}>
                {month.month_label}
              </Typography>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2 }}>
                <Card sx={{ flex: 1, background: 'rgba(255,255,255,0.05)' }}>
                  <CardContent>
                    <Typography variant="body2" color="text.secondary">Total original del mes</Typography>
                    <Typography variant="h6">{formatCurrency(month.totals.original)}</Typography>
                  </CardContent>
                </Card>
                <Card sx={{ flex: 1, background: 'rgba(130,70,70,0.12)' }}>
                  <CardContent>
                    <Typography variant="body2" color="text.secondary">Debe del mes</Typography>
                    <Typography variant="h6" color="error.main">{formatCurrency(month.totals.remaining)}</Typography>
                  </CardContent>
                </Card>
              </Stack>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>Detalle por día</Typography>
              <Stack spacing={1.5}>
                {visibleDays.map((day) => (
                  <Box key={day.date} sx={{ background: 'rgba(255,255,255,0.03)', borderRadius: 2, p: 1.5, borderLeft: '4px solid rgba(255,255,255,0.2)' }}>
                    <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }}>
                      <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>{day.label}</Typography>
                      <Stack direction="row" spacing={2} sx={{ color: 'text.secondary', fontSize: '0.875rem' }}>
                        <span>Original: {formatCurrency(day.totals.original)}</span>
                        <span style={{ color: day.totals.remaining <= 0 ? '#7CFFB2' : '#ff6b6b' }}>
                          Debe: {formatCurrency(Math.max(day.totals.remaining, 0))}
                        </span>
                      </Stack>
                    </Stack>
                    <Stack spacing={1} sx={{ mt: 1, display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, columnGap: 1, rowGap: 1 }}>
                      {day.transactions.map((item, idx) => {
                        const columnsPerRow = statsTwoColumnLayout ? 2 : 1
                        const rowIndex = Math.floor(idx / columnsPerRow)
                        const nameColor = rowIndex % 2 === 0 ? '#ffffff' : '#5ab0ff'
                        return (
                          <Box key={`${day.date}-${idx}`} sx={{ background: 'rgba(10,10,10,0.3)', borderRadius: 2, p: 1.25 }}>
                            <Typography
                              sx={{
                                fontWeight: 600,
                                fontSize: '0.95rem',
                                color: nameColor,
                              }}
                            >
                              {item.client || 'Sin cliente'}
                            </Typography>
                            {item.description && (
                              <Typography variant="body2" color="text.secondary">{item.description}</Typography>
                            )}
                            <Stack direction="row" spacing={2} justifyContent="space-between" sx={{ mt: 0.5, fontSize: '0.9rem' }}>
                              <Typography component="span">Original: {formatCurrency(item.original)}</Typography>
                              <Typography component="span" sx={{ color: item.remaining <= 0 ? '#7CFFB2' : '#ff6b6b' }}>
                                Debe: {formatCurrency(Math.max(item.remaining, 0))}
                              </Typography>
                            </Stack>
                          </Box>
                        )
                      })}
                    </Stack>
                  </Box>
                ))}
              </Stack>
              {totalDayPages > 1 && (
                <Pagination
                  count={totalDayPages}
                  page={currentDayPage}
                  onChange={(_e, value) => handleDayPageChange(monthKey, value)}
                  size="small"
                  sx={{ alignSelf: 'flex-end', mt: 1 }}
                />
              )}
            </Box>
        )})}
        </DialogContent>
      </Dialog>

      <Dialog
        open={newClientDialogOpen}
        onClose={closeNewClientDialog}
        sx={{
          '& .MuiPaper-root': {
            background: 'linear-gradient(135deg, rgba(18,18,26,0.98), rgba(24,24,34,0.98))',
            borderRadius: 3,
            minWidth: { xs: '90vw', sm: 460 },
            color: '#fff',
            boxShadow: '0 25px 80px rgba(0,0,0,0.6)',
            border: '1px solid rgba(255,255,255,0.05)',
          },
        }}
      >
        <DialogTitle sx={{ fontWeight: 700, fontSize: '1.35rem' }}>
          Agregar nuevo cliente
        </DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
          {newClientError && <Alert severity="error">{newClientError}</Alert>}
          <TextField
            label="Apellido *"
            value={newClientForm.last_name}
            onChange={(e) => setNewClientForm((prev) => ({ ...prev, last_name: e.target.value }))}
            required
            fullWidth
          />
          <TextField
            label="Nombre *"
            value={newClientForm.first_name}
            onChange={(e) => setNewClientForm((prev) => ({ ...prev, first_name: e.target.value }))}
            required
            fullWidth
          />
          <TextField
            label="Teléfono (opcional)"
            value={newClientForm.phone}
            onChange={(e) => setNewClientForm((prev) => ({ ...prev, phone: e.target.value }))}
            placeholder="+54 3584000000"
            fullWidth
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button onClick={closeNewClientDialog} sx={{ color: '#b0b0b0' }} disabled={newClientLoading}>
            Cancelar
          </Button>
          <Button variant="contained" color="success" onClick={handleCreateClient} disabled={newClientLoading}>
            Guardar cliente
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={editDialogOpen}
        onClose={() => setEditDialogOpen(false)}
        sx={{
          '& .MuiPaper-root': {
            background: 'linear-gradient(135deg, rgba(18,18,26,0.98), rgba(24,24,34,0.98))',
            borderRadius: 3,
            minWidth: { xs: '90vw', sm: 420 },
            color: '#fff',
            boxShadow: '0 25px 80px rgba(0,0,0,0.6)',
            border: '1px solid rgba(255,255,255,0.05)',
          },
        }}
      >
        <DialogTitle sx={{ fontWeight: 700, fontSize: '1.35rem' }}>
          Editar cliente
          {selectedClient && (
            <Typography variant="subtitle2" color="text.secondary">
              {selectedClient.full_name}
            </Typography>
          )}
        </DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
          <Box>
            <Typography variant="caption" color="text.secondary">Nombre</Typography>
            <TextField
              fullWidth
              value={editForm.first_name}
              onChange={(e) => setEditForm((prev) => ({ ...prev, first_name: e.target.value }))}
              sx={{ mt: 0.5 }}
            />
            <Typography variant="caption" color="text.secondary">
              Original: {selectedClient?.first_name || 'â€”'}
            </Typography>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary">Apellido</Typography>
            <TextField
              fullWidth
              value={editForm.last_name}
              onChange={(e) => setEditForm((prev) => ({ ...prev, last_name: e.target.value }))}
              sx={{ mt: 0.5 }}
            />
            <Typography variant="caption" color="text.secondary">
              Original: {selectedClient?.last_name || 'â€”'}
            </Typography>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary">Teléfono (opcional)</Typography>
            <TextField
              fullWidth
              value={editForm.phone}
              onChange={(e) => setEditForm((prev) => ({ ...prev, phone: formatPhoneDisplay(e.target.value) }))}
              placeholder="+54 3584000000"
              sx={{ mt: 0.5 }}
            />
            <Typography variant="caption" color="text.secondary">
              Original: {selectedClient?.phone ? formatPhoneDisplay(selectedClient.phone) : 'â€”'}
            </Typography>
          </Box>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button onClick={() => setEditDialogOpen(false)} sx={{ color: '#b0b0b0' }}>
            Cancelar
          </Button>
          <Button onClick={submitEdit} disabled={actionLoading} variant="contained" color="error">
            Guardar cambios
          </Button>
        </DialogActions>
      </Dialog>


      <Dialog
        open={newExpenseOpen}
        onClose={closeNewExpenseDialog}
        sx={{
          '& .MuiPaper-root': {
            background: 'linear-gradient(135deg, rgba(18,18,26,0.98), rgba(24,24,34,0.98))',
            borderRadius: 3,
            minWidth: { xs: '90vw', sm: 460 },
            color: '#fff',
            boxShadow: '0 25px 80px rgba(0,0,0,0.6)',
            border: '1px solid rgba(255,255,255,0.05)',
          },
        }}
      >
        <DialogTitle sx={{ fontWeight: 700, fontSize: '1.35rem' }}>
          Registrar nuevo gasto/movimiento
        </DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
          {newExpenseError && <Alert severity="error">{newExpenseError}</Alert>}
          <TextField
            label="Fecha"
            type="date"
            value={newExpenseForm.date}
            onChange={(e) => setNewExpenseForm((prev) => ({ ...prev, date: e.target.value }))}
            InputLabelProps={{ shrink: true }}
            fullWidth
          />
          <TextField
            label="Monto"
            type="number"
            value={newExpenseForm.amount}
            onChange={(e) => setNewExpenseForm((prev) => ({ ...prev, amount: e.target.value }))}
            inputProps={{ min: 0, step: '0.01' }}
            fullWidth
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  $
                </InputAdornment>
              ),
            }}
          />
          <TextField
            label="Descripción (opcional)"
            value={newExpenseForm.description}
            onChange={(e) => setNewExpenseForm((prev) => ({ ...prev, description: e.target.value }))}
            fullWidth
            multiline
            minRows={2}
            placeholder="Ej: Compra de mercadería"
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button onClick={closeNewExpenseDialog} sx={{ color: '#b0b0b0' }} disabled={newExpenseLoading}>
            Cancelar
          </Button>
          <Button variant="contained" color="success" onClick={handleCreateExpense} disabled={newExpenseLoading}>
            Guardar gasto
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={confirmSelectedOpen}
        onClose={() => { setConfirmSelectedOpen(false); setConfirmSelectedAmount(''); setConfirmSelectedError('') }}
        sx={{
          '& .MuiPaper-root': {
            background: 'linear-gradient(135deg, rgba(17,17,25,0.98), rgba(22,22,34,0.98))',
            borderRadius: 3,
            minWidth: { xs: '90vw', sm: 420 },
            color: '#fff',
            boxShadow: '0 25px 80px rgba(0,0,0,0.6)',
            border: '1px solid rgba(255,255,255,0.05)',
          },
        }}
      >
        <DialogTitle sx={{ fontWeight: 700, fontSize: '1.35rem' }}>
          Confirmar pago de seleccionados
        </DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
          {selectedSummary ? (
            <>
              <Typography variant="body1">
                ¿Estás seguro de pagar las {selectedSummary.count} transacciones seleccionadas de{' '}
                {selectedClient?.full_name || 'este cliente'}?
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Total a pagar: {formatCurrency(selectedSummary.total)}
                {selectedSummary.from && selectedSummary.to && (
                  <>
                    <br />
                    Periodo: {selectedSummary.from.toLocaleDateString('es-AR')} - {selectedSummary.to.toLocaleDateString('es-AR')}
                  </>
                )}
              </Typography>
              <TextField
                label="Monto a pagar (opcional)"
                type="number"
                value={confirmSelectedAmount}
                onChange={(e) => setConfirmSelectedAmount(e.target.value)}
                inputProps={{ min: 0, step: '0.01' }}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      $
                    </InputAdornment>
                  ),
                }}
                helperText="Deja vacío para cancelar completamente los seleccionados."
                error={Boolean(confirmSelectedError)}
                fullWidth
              />
              {confirmSelectedError && (
                <Typography variant="caption" color="error">
                  {confirmSelectedError}
                </Typography>
              )}
            </>
          ) : (
            <Typography variant="body2" color="text.secondary">
              No hay movimientos seleccionados.
            </Typography>
          )}
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button onClick={() => { setConfirmSelectedOpen(false); setConfirmSelectedAmount(''); setConfirmSelectedError('') }} sx={{ color: '#b0b0b0' }}>
            No, cancelar
          </Button>
          <Button
            variant="contained"
            color="success"
            disabled={!selectedSummary}
            onClick={confirmPaySelected}
          >
            Sí, pagar seleccionados
          </Button>
        </DialogActions>
      </Dialog>

    </Box>
  )
}
