import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  InputLabel,
  IconButton,
  LinearProgress,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material'
import AccountBalanceIcon from '@mui/icons-material/AccountBalance'
import BadgeIcon from '@mui/icons-material/Badge'
import LocalAtmIcon from '@mui/icons-material/LocalAtm'
import PointOfSaleIcon from '@mui/icons-material/PointOfSale'
import SyncIcon from '@mui/icons-material/Sync'
import EditIcon from '@mui/icons-material/Edit'
import PersonOffIcon from '@mui/icons-material/PersonOff'
import RestoreIcon from '@mui/icons-material/Restore'
import CalculateIcon from '@mui/icons-material/Calculate'
import SaveIcon from '@mui/icons-material/Save'
import { Bar, Doughnut } from 'react-chartjs-2'
import { ArcElement, BarElement, CategoryScale, Chart, Legend, LinearScale, Tooltip as ChartTooltip } from 'chart.js'
import { useAuth } from '../context/AuthContext.jsx'
import { API_BASE } from '../config'
import useBranches from '../hooks/useBranches.js'

Chart.register(ArcElement, BarElement, CategoryScale, LinearScale, ChartTooltip, Legend)

const API_SALARIES_SUMMARY = `${API_BASE}/salaries/summary/`
const API_SALARIES_MONTHLY = `${API_BASE}/salaries/monthly/`
const API_SALARIES_AGUINALDO = `${API_BASE}/salaries/aguinaldo/`
const API_ACCOUNT_DEDUCTIONS_CONFIRM = `${API_BASE}/salaries/account-deductions/confirm/`
const API_EMPLOYEES = `${API_BASE}/salaries/employees/`
const API_ACCOUNTS = `${API_BASE}/accounts/clients/`

const MONTHS = [
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

const SOURCE_COLORS = {
  bank_transfer: 'info',
  cash_expense: 'success',
  account_current: 'warning',
}

const CHART_COLORS = {
  bank_transfer: '#42a5f5',
  cash_expense: '#66bb6a',
  account_current: '#ffa726',
}

const CHART_LABELS = {
  bank_transfer: 'Transferencias',
  cash_expense: 'Efectivo',
  account_current: 'Cuenta corriente',
}

function EmptyState({ icon: Icon, title, description, action, testId }) {
  return (
    <Box
      role="status"
      data-testid={testId}
      sx={{
        minHeight: 220,
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        textAlign: 'center',
        border: '1px dashed',
        borderColor: 'divider',
        borderRadius: 1,
        bgcolor: 'action.hover',
        px: 3,
        py: 3,
      }}
    >
      <Box
        sx={{
          width: 46,
          height: 46,
          display: 'grid',
          placeItems: 'center',
          borderRadius: 1,
          bgcolor: 'action.selected',
          color: 'text.secondary',
          mb: 1.5,
        }}
      >
        <Icon />
      </Box>
      <Typography fontWeight={700}>{title}</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 380, mt: 0.5 }}>
        {description}
      </Typography>
      {action && <Box sx={{ mt: 2 }}>{action}</Box>}
    </Box>
  )
}

const DOCUMENT_TYPES = [
  { value: 'dni', label: 'DNI' },
  { value: 'cuil_cuit', label: 'CUIL/CUIT' },
]

const TERMINATION_REASONS = [
  { value: 'resignation', label: 'Renuncia' },
  { value: 'dismissal', label: 'Despido' },
  { value: 'other', label: 'Otro' },
]

const emptyEmployeeForm = () => ({
  name: '',
  branchId: '',
  documentType: '',
  documentNumber: '',
  aliases: '',
  accountClient: null,
  discountPercent: '0',
  hireDate: '',
  notes: '',
})

function buildRemunerationDraft(data) {
  return Object.fromEntries((data?.months || []).map((item) => [
    String(item.month),
    item.confirmed_amount ?? (item.detected_amount > 0 ? item.detected_amount : ''),
  ]))
}

function localIsoDate() {
  const now = new Date()
  const offset = now.getTimezoneOffset() * 60000
  return new Date(now.getTime() - offset).toISOString().slice(0, 10)
}

function formatDocument(employee) {
  if (!employee?.document_number) return 'Sin documento'
  if (employee.document_type === 'cuil_cuit' && employee.document_number.length === 11) {
    return `${employee.document_type_label}: ${employee.document_number.slice(0, 2)}-${employee.document_number.slice(2, 10)}-${employee.document_number.slice(10)}`
  }
  return `${employee.document_type_label}: ${employee.document_number}`
}

function formatCurrency(value) {
  return `$ ${Number(value || 0).toLocaleString('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

function formatDate(value) {
  if (!value) return 'Sin datos'
  const [year, month, day] = value.split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString('es-AR')
}

function chartCurrency(value) {
  return formatCurrency(value).replace('$ ', '$')
}

function SummaryCard({ icon, label, value, detail }) {
  return (
    <Card sx={{ height: '100%', border: '1px solid rgba(255,255,255,0.08)' }}>
      <CardContent>
        <Stack direction="row" spacing={1.5} alignItems="center">
          {icon}
          <Box>
            <Typography variant="body2" color="text.secondary">{label}</Typography>
            <Typography variant="h5" fontWeight={800}>{formatCurrency(value)}</Typography>
            {detail ? <Typography variant="caption" color="text.secondary">{detail}</Typography> : null}
          </Box>
        </Stack>
      </CardContent>
    </Card>
  )
}

export default function SalariesPage() {
  const { authFetch } = useAuth()
  const { branches, branchesLoading, branchesError } = useBranches(authFetch)
  const now = new Date()
  const [year, setYear] = useState(String(now.getFullYear()))
  const [month, setMonth] = useState(String(now.getMonth() + 1))
  const [branchId, setBranchId] = useState('')
  const [summary, setSummary] = useState(null)
  const [employees, setEmployees] = useState([])
  const [clients, setClients] = useState([])
  const [loading, setLoading] = useState(false)
  const [monthlyLoading, setMonthlyLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [deductionLoading, setDeductionLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [monthlySummary, setMonthlySummary] = useState(null)
  const [sacEmployeeId, setSacEmployeeId] = useState('')
  const [sacSemester, setSacSemester] = useState(now.getMonth() < 6 ? '1' : '2')
  const [sacData, setSacData] = useState(null)
  const [sacDraft, setSacDraft] = useState({})
  const [sacLoading, setSacLoading] = useState(false)
  const [sacSaving, setSacSaving] = useState(false)
  const [employeeView, setEmployeeView] = useState('composition')
  const [selectedEmployeeId, setSelectedEmployeeId] = useState('')
  const [movementSearch, setMovementSearch] = useState('')
  const [movementEmployee, setMovementEmployee] = useState('all')
  const [movementSource, setMovementSource] = useState('all')
  const [movementPage, setMovementPage] = useState(0)
  const [movementRowsPerPage, setMovementRowsPerPage] = useState(10)
  const [employeeForm, setEmployeeForm] = useState(emptyEmployeeForm)
  const [employeeStatusFilter, setEmployeeStatusFilter] = useState('active')
  const [editEmployee, setEditEmployee] = useState(null)
  const [editEmployeeForm, setEditEmployeeForm] = useState(emptyEmployeeForm)
  const [statusDialog, setStatusDialog] = useState({
    open: false,
    mode: 'deactivate',
    employee: null,
    reason: '',
    date: localIsoDate(),
  })
  const [deductionDialog, setDeductionDialog] = useState({ open: false, row: null })
  const accountSearchTimer = useRef(null)

  const defaultBranchId = useMemo(() => {
    const primary = branches.find((branch) => branch.slug === 'sucursal-primaria') || branches[0]
    return primary ? String(primary.id) : ''
  }, [branches])
  const selectedBranchName = branches.find((branch) => String(branch.id) === branchId)?.name || 'Todas las sucursales'
  const queryString = useMemo(() => {
    const params = new URLSearchParams({ year, month })
    if (branchId) params.set('branch_id', branchId)
    return params.toString()
  }, [branchId, month, year])

  const fetchSummary = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const resp = await authFetch(`${API_SALARIES_SUMMARY}?${queryString}`)
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo cargar sueldos')
      setSummary(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [authFetch, queryString])

  const fetchMonthlySummary = useCallback(async () => {
    setMonthlyLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({ year })
      if (branchId) params.set('branch_id', branchId)
      const resp = await authFetch(`${API_SALARIES_MONTHLY}?${params.toString()}`)
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo cargar la evolucion mensual')
      setMonthlySummary(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setMonthlyLoading(false)
    }
  }, [authFetch, branchId, year])

  const fetchAguinaldo = useCallback(async () => {
    if (!sacEmployeeId) {
      setSacData(null)
      setSacDraft({})
      return
    }
    setSacLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({ employee_id: sacEmployeeId, year, semester: sacSemester })
      const resp = await authFetch(`${API_SALARIES_AGUINALDO}?${params.toString()}`)
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo calcular el aguinaldo')
      setSacData(data)
      setSacDraft(buildRemunerationDraft(data))
    } catch (err) {
      setError(err.message)
      setSacData(null)
    } finally {
      setSacLoading(false)
    }
  }, [authFetch, sacEmployeeId, sacSemester, year])

  const fetchEmployees = useCallback(async () => {
    try {
      const [employeesResp, clientsResp] = await Promise.all([
        authFetch(API_EMPLOYEES),
        authFetch(`${API_ACCOUNTS}?limit=200&ordering=last_name`),
      ])
      const [employeesData, clientsData] = await Promise.all([
        employeesResp.json(),
        clientsResp.json(),
      ])
      if (!employeesResp.ok) throw new Error(employeesData.detail || 'No se pudieron cargar empleados')
      if (!clientsResp.ok) throw new Error(clientsData.detail || 'No se pudieron cargar clientes')
      setEmployees(employeesData || [])
      setClients(clientsData.results || [])
    } catch (err) {
      setError(err.message)
    }
  }, [authFetch])

  const searchAccountClients = useCallback((_event, value, reason) => {
    if (reason !== 'input') return
    if (accountSearchTimer.current) clearTimeout(accountSearchTimer.current)
    const search = value.trim()
    if (search.length < 2) return
    accountSearchTimer.current = setTimeout(async () => {
      try {
        const params = new URLSearchParams({ search, limit: '50', ordering: 'last_name' })
        const resp = await authFetch(`${API_ACCOUNTS}?${params.toString()}`)
        const data = await resp.json()
        if (!resp.ok) throw new Error(data.detail || 'No se pudieron buscar cuentas corrientes')
        setClients((current) => {
          const merged = new Map(current.map((client) => [client.id, client]))
          ;(data.results || []).forEach((client) => merged.set(client.id, client))
          return [...merged.values()]
        })
      } catch (err) {
        setError(err.message)
      }
    }, 300)
  }, [authFetch])

  useEffect(() => {
    fetchSummary()
  }, [fetchSummary])

  useEffect(() => {
    fetchEmployees()
  }, [fetchEmployees])

  useEffect(() => {
    if (!defaultBranchId) return
    setEmployeeForm((current) => (current.branchId ? current : { ...current, branchId: defaultBranchId }))
  }, [defaultBranchId])

  useEffect(() => {
    fetchAguinaldo()
  }, [fetchAguinaldo])

  useEffect(() => () => {
    if (accountSearchTimer.current) clearTimeout(accountSearchTimer.current)
  }, [])

  useEffect(() => {
    const loadedBranchId = String(monthlySummary?.branch_id || '')
    if (employeeView === 'monthly' && (monthlySummary?.year !== Number(year) || loadedBranchId !== branchId)) fetchMonthlySummary()
  }, [branchId, employeeView, fetchMonthlySummary, monthlySummary?.branch_id, monthlySummary?.year, year])

  const createEmployee = async () => {
    setActionLoading(true)
    setError('')
    setSuccess('')
    try {
      const aliases = employeeForm.aliases
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean)
      const resp = await authFetch(API_EMPLOYEES, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: employeeForm.name,
          branch_id: employeeForm.branchId,
          document_type: employeeForm.documentType,
          document_number: employeeForm.documentNumber,
          aliases,
          account_client_id: employeeForm.accountClient?.id || null,
          account_discount_percent: employeeForm.discountPercent,
          hire_date: employeeForm.hireDate || null,
          notes: employeeForm.notes,
        }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo crear el empleado')
      setSuccess(`Empleado creado: ${data.name}`)
      setEmployeeForm({ ...emptyEmployeeForm(), branchId: defaultBranchId })
      await Promise.all([
        fetchEmployees(),
        fetchSummary(),
        employeeView === 'monthly' ? fetchMonthlySummary() : Promise.resolve(),
      ])
    } catch (err) {
      setError(err.message)
    } finally {
      setActionLoading(false)
    }
  }

  const accountClientIsLinked = (client, currentEmployeeId = '') => (
    employees.some((employee) => employee.id !== currentEmployeeId && employee.account_client_id === client.id)
  )

  const openEditEmployee = (employee) => {
    const linkedClient = clients.find((client) => client.id === employee.account_client_id) || (
      employee.account_client_id
        ? { id: employee.account_client_id, full_name: employee.account_client_name, external_id: employee.account_client_id }
        : null
    )
    setEditEmployee(employee)
    setEditEmployeeForm({
      name: employee.name || '',
      branchId: String(employee.branch_id || ''),
      documentType: employee.document_type || '',
      documentNumber: employee.document_number || '',
      aliases: (employee.aliases || []).join(', '),
      accountClient: linkedClient,
      discountPercent: String(employee.account_discount_percent ?? 0),
      hireDate: employee.hire_date || '',
      notes: employee.notes || '',
    })
  }

  const saveEmployee = async () => {
    if (!editEmployee) return
    setActionLoading(true)
    setError('')
    setSuccess('')
    try {
      const aliases = editEmployeeForm.aliases
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean)
      const resp = await authFetch(`${API_EMPLOYEES}${editEmployee.id}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: editEmployeeForm.name,
          branch_id: editEmployeeForm.branchId,
          document_type: editEmployeeForm.documentType,
          document_number: editEmployeeForm.documentNumber,
          aliases,
          account_client_id: editEmployeeForm.accountClient?.id || null,
          account_discount_percent: editEmployeeForm.discountPercent,
          hire_date: editEmployeeForm.hireDate || null,
          notes: editEmployeeForm.notes,
        }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo actualizar el empleado')
      setEditEmployee(null)
      setSuccess(`Empleado actualizado: ${data.name}`)
      await Promise.all([
        fetchEmployees(),
        fetchSummary(),
        employeeView === 'monthly' ? fetchMonthlySummary() : Promise.resolve(),
        editEmployee.id === sacEmployeeId ? fetchAguinaldo() : Promise.resolve(),
      ])
    } catch (err) {
      setError(err.message)
    } finally {
      setActionLoading(false)
    }
  }

  const saveAguinaldoRemunerations = async () => {
    if (!sacEmployeeId || !sacData) return
    setSacSaving(true)
    setError('')
    setSuccess('')
    try {
      const params = new URLSearchParams({ employee_id: sacEmployeeId, year, semester: sacSemester })
      const remunerations = sacData.months.map((item) => ({
        month: item.month,
        amount: sacDraft[String(item.month)] === '' ? null : sacDraft[String(item.month)],
      }))
      const resp = await authFetch(`${API_SALARIES_AGUINALDO}?${params.toString()}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ remunerations }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudieron guardar las remuneraciones')
      setSacData(data)
      setSacDraft(buildRemunerationDraft(data))
      setSuccess(`Remuneraciones actualizadas: ${data.employee.name}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setSacSaving(false)
    }
  }

  const openStatusDialog = (employee, mode) => {
    setStatusDialog({
      open: true,
      mode,
      employee,
      reason: '',
      date: localIsoDate(),
    })
  }

  const confirmStatusChange = async () => {
    const { employee, mode, reason, date: terminationDate } = statusDialog
    if (!employee) return
    setActionLoading(true)
    setError('')
    setSuccess('')
    try {
      const body = mode === 'deactivate'
        ? { active: false, termination_reason: reason, termination_date: terminationDate }
        : { active: true }
      const resp = await authFetch(`${API_EMPLOYEES}${employee.id}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo cambiar el estado del empleado')
      setStatusDialog((prev) => ({ ...prev, open: false, employee: null }))
      setSuccess(mode === 'deactivate' ? `Empleado dado de baja: ${data.name}` : `Empleado reactivado: ${data.name}`)
      await Promise.all([
        fetchEmployees(),
        fetchSummary(),
        employeeView === 'monthly' ? fetchMonthlySummary() : Promise.resolve(),
      ])
    } catch (err) {
      setError(err.message)
    } finally {
      setActionLoading(false)
    }
  }

  const confirmAccountDeductions = async () => {
    const row = deductionDialog.row
    if (!row) return
    setDeductionLoading(true)
    setError('')
    setSuccess('')
    try {
      const resp = await authFetch(API_ACCOUNT_DEDUCTIONS_CONFIRM, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ employee_id: row.employee_id, year, month }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo confirmar el descuento')
      setDeductionDialog({ open: false, row: null })
      setSuccess(`Cuenta corriente confirmada para ${data.employee_name}: ${formatCurrency(data.net_amount)}`)
      await Promise.all([
        fetchSummary(),
        fetchEmployees(),
        employeeView === 'monthly' ? fetchMonthlySummary() : Promise.resolve(),
      ])
    } catch (err) {
      setError(err.message)
    } finally {
      setDeductionLoading(false)
    }
  }

  const totals = summary?.totals || {}
  const movements = summary?.movements || []
  const employeeRows = summary?.employees || []
  const accountDeductions = summary?.account_deductions || {}
  const accountDeductionRows = accountDeductions.employees || []
  const sources = summary?.sources || {}
  const latestBankDates = sources.latest_bank_dates || {}
  const monthlyMatchesSelection = monthlySummary?.year === Number(year) && String(monthlySummary?.branch_id || '') === branchId
  const annualEmployeeRows = monthlyMatchesSelection ? (monthlySummary.employees || []) : []
  const displayedEmployeeRows = employeeView === 'monthly' ? annualEmployeeRows : employeeRows
  const employeesInBranch = useMemo(() => employees.filter((employee) => (
    !branchId || String(employee.branch_id) === branchId
  )), [branchId, employees])
  const activeEmployees = useMemo(() => employeesInBranch.filter((employee) => employee.active), [employeesInBranch])
  const filteredEmployees = employeesInBranch.filter((employee) => (
    employeeStatusFilter === 'all' || (employeeStatusFilter === 'active' ? employee.active : !employee.active)
  ))

  useEffect(() => {
    if (!displayedEmployeeRows.length) {
      setSelectedEmployeeId('')
      return
    }
    if (!displayedEmployeeRows.some((row) => row.employee_id === selectedEmployeeId)) {
      setSelectedEmployeeId(displayedEmployeeRows[0].employee_id)
    }
  }, [displayedEmployeeRows, selectedEmployeeId])

  useEffect(() => {
    if (!activeEmployees.length) {
      setSacEmployeeId('')
      return
    }
    if (!activeEmployees.some((employee) => employee.id === sacEmployeeId)) {
      const selectedIsActive = activeEmployees.some((employee) => employee.id === selectedEmployeeId)
      setSacEmployeeId(selectedIsActive ? selectedEmployeeId : activeEmployees[0].id)
    }
  }, [activeEmployees, sacEmployeeId, selectedEmployeeId])

  useEffect(() => {
    setMovementPage(0)
  }, [movementSearch, movementEmployee, movementSource, movementRowsPerPage, movements])

  useEffect(() => {
    setMovementEmployee('all')
    setSelectedEmployeeId('')
  }, [branchId])

  const selectedEmployee = displayedEmployeeRows.find((row) => row.employee_id === selectedEmployeeId) || null
  const movementEmployeeOptions = useMemo(() => {
    const options = new Map()
    movements.forEach((movement) => options.set(movement.employee_id, movement.employee_name))
    return [...options.entries()].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name, 'es'))
  }, [movements])
  const filteredMovements = useMemo(() => {
    const search = movementSearch.trim().toLocaleLowerCase('es')
    return movements.filter((movement) => {
      if (movementEmployee !== 'all' && movement.employee_id !== movementEmployee) return false
      if (movementSource !== 'all' && movement.source !== movementSource) return false
      if (!search) return true
      return [movement.date, movement.employee_name, movement.source_label, movement.description]
        .filter(Boolean)
        .some((value) => String(value).toLocaleLowerCase('es').includes(search))
    })
  }, [movementEmployee, movementSearch, movementSource, movements])
  const paginatedMovements = useMemo(() => {
    const start = movementPage * movementRowsPerPage
    return filteredMovements.slice(start, start + movementRowsPerPage)
  }, [filteredMovements, movementPage, movementRowsPerPage])

  const compositionChartData = useMemo(() => ({
    labels: Object.keys(CHART_LABELS).map((source) => CHART_LABELS[source]),
    datasets: [{
      data: Object.keys(CHART_LABELS).map((source) => Number(selectedEmployee?.[source] || 0)),
      backgroundColor: Object.keys(CHART_LABELS).map((source) => CHART_COLORS[source]),
      borderWidth: 0,
      hoverOffset: 6,
    }],
  }), [selectedEmployee])
  const monthlyChartData = useMemo(() => ({
    labels: MONTHS.map((item) => item.label.slice(0, 3)),
    datasets: Object.keys(CHART_LABELS).map((source) => ({
      label: CHART_LABELS[source],
      data: MONTHS.map((_item, index) => Number(selectedEmployee?.months?.[index]?.[source] || 0)),
      backgroundColor: CHART_COLORS[source],
      borderRadius: 3,
    })),
  }), [selectedEmployee])
  const compositionChartOptions = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    cutout: '64%',
    plugins: {
      legend: { position: 'bottom', labels: { boxWidth: 12, usePointStyle: true } },
      tooltip: { callbacks: { label: (context) => `${context.label}: ${chartCurrency(context.raw)}` } },
    },
  }), [])
  const monthlyChartOptions = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: { stacked: true, grid: { display: false } },
      y: {
        stacked: true,
        beginAtZero: true,
        ticks: { callback: (value) => chartCurrency(value) },
      },
    },
    plugins: {
      legend: { position: 'bottom', labels: { boxWidth: 12, usePointStyle: true } },
      tooltip: { callbacks: { label: (context) => `${context.dataset.label}: ${chartCurrency(context.raw)}` } },
    },
  }), [])

  const refreshDashboard = () => Promise.all([
    fetchSummary(),
    employeeView === 'monthly' ? fetchMonthlySummary() : Promise.resolve(),
  ])

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h4" fontWeight={800}>Sueldos</Typography>
        <Typography color="text.secondary">
          Control mensual de transferencias, efectivo entregado y retiros por cuenta corriente.
        </Typography>
      </Box>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
        <FormControl sx={{ minWidth: 220 }} disabled={branchesLoading}>
          <InputLabel id="salary-branch-label">Sucursal</InputLabel>
          <Select
            id="salary-branch"
            labelId="salary-branch-label"
            label="Sucursal"
            value={branchId}
            onChange={(event) => setBranchId(event.target.value)}
          >
            <MenuItem value="">Todas las sucursales</MenuItem>
            {branches.map((branch) => (
              <MenuItem key={branch.id} value={String(branch.id)}>{branch.name}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl sx={{ minWidth: 150 }}>
          <InputLabel id="salary-year-label">Anio</InputLabel>
          <Select id="salary-year" labelId="salary-year-label" label="Anio" value={year} onChange={(event) => setYear(event.target.value)}>
            {[now.getFullYear() - 1, now.getFullYear(), now.getFullYear() + 1].map((item) => (
              <MenuItem key={item} value={String(item)}>{item}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl sx={{ minWidth: 180 }}>
          <InputLabel id="salary-month-label">Mes</InputLabel>
          <Select id="salary-month" labelId="salary-month-label" label="Mes" value={month} onChange={(event) => setMonth(event.target.value)}>
            {MONTHS.map((item) => (
              <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <Button variant="outlined" startIcon={<SyncIcon />} disabled={loading || monthlyLoading} onClick={refreshDashboard}>
          Sincronizar
        </Button>
      </Stack>

      {loading && <LinearProgress />}
      {branchesError && <Alert severity="error">{branchesError}</Alert>}
      {error && <Alert severity="error">{error}</Alert>}
      {success && <Alert severity="success">{success}</Alert>}

      {summary && sources.active_employees === 0 && (
        <Alert severity="warning">
          No hay empleados configurados. La aplicacion necesita al menos el nombre o alias de cada empleado para no confundir sueldos con otros egresos.
        </Alert>
      )}
      {summary && sources.bank_transactions === 0 && (
        <Alert severity="info">
          No hay movimientos bancarios importados en este periodo. Ultimos datos: Santander {formatDate(latestBankDates.santander)} y Bancor {formatDate(latestBankDates.bancon)}.
        </Alert>
      )}
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(4, minmax(0, 1fr))' }, gap: 2 }}>
        <SummaryCard icon={<BadgeIcon color="primary" />} label="Total empleados" value={totals.total} detail={`${employeeRows.length} empleados con movimientos`} />
        <SummaryCard icon={<AccountBalanceIcon color="info" />} label="Transferencias" value={totals.bank_transfer} detail="Egresos detectados en bancos" />
        <SummaryCard icon={<LocalAtmIcon color="success" />} label="Efectivo" value={totals.cash_expense} detail="Gastos en efectivo / sueldos" />
        <SummaryCard icon={<PointOfSaleIcon color="warning" />} label="Cuenta corriente" value={totals.account_current} detail="Retiros o vales vinculados" />
      </Box>

      <Card>
        <CardContent>
          <Stack direction="row" spacing={1.25} alignItems="center">
            <PointOfSaleIcon color="warning" />
            <Box>
              <Typography variant="h6" fontWeight={700}>Cuenta corriente para descontar</Typography>
              <Typography variant="caption" color="text.secondary">Consumos del mes con beneficio aplicado y neto a trasladar al sueldo</Typography>
            </Box>
          </Stack>
          <Divider sx={{ my: 2 }} />
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, minmax(0, 1fr))' }, gap: 2 }}>
            <Box>
              <Typography variant="caption" color="text.secondary">Consumo bruto</Typography>
              <Typography variant="h6" fontWeight={800}>{formatCurrency(accountDeductions.gross_amount)}</Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">Beneficio empleados</Typography>
              <Typography variant="h6" fontWeight={800}>{formatCurrency(accountDeductions.discount_amount)}</Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">Neto a descontar</Typography>
              <Typography variant="h6" fontWeight={800}>{formatCurrency(accountDeductions.net_amount)}</Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">Pendiente de confirmar</Typography>
              <Typography variant="h6" fontWeight={800}>{formatCurrency(accountDeductions.pending_net_amount)}</Typography>
            </Box>
          </Box>
          <TableContainer sx={{ mt: 2 }}>
            <Table size="small" sx={{ minWidth: 760 }}>
              <TableHead>
                <TableRow>
                  <TableCell>Empleado</TableCell>
                  <TableCell align="right">Bruto</TableCell>
                  <TableCell align="right">Beneficio</TableCell>
                  <TableCell align="right">Neto sueldo</TableCell>
                  <TableCell>Estado</TableCell>
                  <TableCell align="right">Accion</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {accountDeductionRows.map((row) => (
                  <TableRow key={row.employee_id} hover>
                    <TableCell>{row.employee_name}</TableCell>
                    <TableCell align="right">{formatCurrency(row.gross_amount)}</TableCell>
                    <TableCell align="right">{formatCurrency(row.discount_amount)}</TableCell>
                    <TableCell align="right"><strong>{formatCurrency(row.net_amount)}</strong></TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        color={row.pending_count ? 'warning' : 'success'}
                        label={row.pending_count ? `${row.pending_count} pendiente${row.pending_count === 1 ? '' : 's'}` : 'Confirmado'}
                      />
                    </TableCell>
                    <TableCell align="right">
                      {row.pending_count > 0 && (
                        <Button size="small" variant="outlined" onClick={() => setDeductionDialog({ open: true, row })}>
                          Confirmar
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {!accountDeductionRows.length && (
                  <TableRow>
                    <TableCell colSpan={6}>
                      <Typography color="text.secondary">No hay consumos de empleados en cuenta corriente para este mes.</Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Stack spacing={2}>
            <Box>
              <Typography variant="h6" fontWeight={700}>Alta de empleado</Typography>
              <Typography variant="body2" color="text.secondary">
                Los aliases ayudan a reconocer nombres en extractos, gastos y cuenta corriente. La sucursal define donde trabaja el empleado.
              </Typography>
            </Box>
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'minmax(180px, 0.8fr) minmax(140px, 0.5fr) minmax(180px, 0.7fr) minmax(220px, 1fr)' }, gap: 2 }}>
              <TextField
                label="Nombre"
                value={employeeForm.name}
                onChange={(event) => setEmployeeForm((prev) => ({ ...prev, name: event.target.value }))}
              />
              <TextField
                select
                required
                label="Sucursal"
                value={employeeForm.branchId}
                onChange={(event) => setEmployeeForm((prev) => ({ ...prev, branchId: event.target.value }))}
              >
                {branches.map((branch) => <MenuItem key={branch.id} value={String(branch.id)}>{branch.name}</MenuItem>)}
              </TextField>
              <TextField
                select
                label="Tipo de documento"
                value={employeeForm.documentType}
                onChange={(event) => setEmployeeForm((prev) => ({
                  ...prev,
                  documentType: event.target.value,
                  documentNumber: event.target.value ? prev.documentNumber : '',
                }))}
              >
                <MenuItem value="">Sin documento</MenuItem>
                {DOCUMENT_TYPES.map((item) => <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>)}
              </TextField>
              <TextField
                label={employeeForm.documentType === 'cuil_cuit' ? 'CUIL/CUIT' : 'DNI'}
                value={employeeForm.documentNumber}
                disabled={!employeeForm.documentType}
                onChange={(event) => setEmployeeForm((prev) => ({ ...prev, documentNumber: event.target.value }))}
                slotProps={{ htmlInput: { inputMode: 'numeric' } }}
              />
              <TextField
                type="date"
                label="Fecha de ingreso"
                value={employeeForm.hireDate}
                onChange={(event) => setEmployeeForm((prev) => ({ ...prev, hireDate: event.target.value }))}
                slotProps={{ inputLabel: { shrink: true } }}
              />
              <TextField
                label="Aliases separados por coma"
                value={employeeForm.aliases}
                onChange={(event) => setEmployeeForm((prev) => ({ ...prev, aliases: event.target.value }))}
              />
              <Autocomplete
                options={clients}
                value={employeeForm.accountClient}
                onChange={(_event, value) => setEmployeeForm((prev) => ({ ...prev, accountClient: value }))}
                onInputChange={searchAccountClients}
                getOptionLabel={(option) => option.full_name || option.external_id || ''}
                getOptionDisabled={(option) => accountClientIsLinked(option)}
                isOptionEqualToValue={(option, value) => option.id === value.id}
                renderInput={(params) => <TextField {...params} label="Cliente cuenta corriente" />}
              />
              <TextField
                type="number"
                label="Descuento cuenta corriente (%)"
                value={employeeForm.discountPercent}
                onChange={(event) => setEmployeeForm((prev) => ({ ...prev, discountPercent: event.target.value }))}
                slotProps={{ htmlInput: { min: 0, max: 100, step: '0.01' } }}
              />
              <TextField
                label="Notas"
                value={employeeForm.notes}
                onChange={(event) => setEmployeeForm((prev) => ({ ...prev, notes: event.target.value }))}
                sx={{ gridColumn: { md: 'span 2' } }}
              />
              <Button
                variant="contained"
                disabled={actionLoading || !employeeForm.branchId || employeeForm.name.trim().length < 2 || Boolean(employeeForm.documentType) !== Boolean(employeeForm.documentNumber.trim())}
                onClick={createEmployee}
                sx={{ minHeight: 44 }}
              >
                Crear
              </Button>
            </Box>
          </Stack>
        </CardContent>
      </Card>

      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(0, 1fr) minmax(0, 1.25fr)' }, gap: 2, alignItems: 'stretch' }}>
        <Card data-testid="employee-summary-card" sx={{ minWidth: 0, height: '100%' }}>
          <CardContent sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
            <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ xs: 'stretch', sm: 'center' }} spacing={1.5}>
              <Box>
                <Typography variant="h6" fontWeight={700}>Resumen por empleado</Typography>
                <Typography variant="caption" color="text.secondary">
                  {employeeView === 'monthly' ? `Acumulado y evolucion de ${year}` : `${MONTHS[Number(month) - 1]?.label} ${year}`} - {selectedBranchName}
                </Typography>
              </Box>
              <ToggleButtonGroup
                exclusive
                size="small"
                value={employeeView}
                onChange={(_event, value) => value && setEmployeeView(value)}
                aria-label="Vista del resumen por empleado"
              >
                <ToggleButton value="composition">Composicion</ToggleButton>
                <ToggleButton value="monthly">Mensual</ToggleButton>
              </ToggleButtonGroup>
            </Stack>
            {monthlyLoading && <LinearProgress sx={{ mt: 2 }} />}
            <Divider sx={{ my: 2 }} />
            {displayedEmployeeRows.length ? (
              <TableContainer sx={{ maxHeight: 300 }}>
                <Table stickyHeader size="small" sx={{ minWidth: 520 }}>
                  <TableHead>
                    <TableRow>
                      <TableCell>Empleado</TableCell>
                      <TableCell align="right">Banco</TableCell>
                      <TableCell align="right">Efectivo</TableCell>
                      <TableCell align="right">C. corriente</TableCell>
                      <TableCell align="right">Total</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {displayedEmployeeRows.map((row) => (
                      <TableRow
                        key={row.employee_id}
                        hover
                        selected={row.employee_id === selectedEmployeeId}
                        onClick={() => {
                          setSelectedEmployeeId(row.employee_id)
                          setSacEmployeeId(row.employee_id)
                        }}
                        sx={{ cursor: 'pointer' }}
                      >
                        <TableCell>
                          <Button
                            size="small"
                            color="inherit"
                            onClick={() => {
                              setSelectedEmployeeId(row.employee_id)
                              setSacEmployeeId(row.employee_id)
                            }}
                            sx={{ minWidth: 0, px: 0, fontWeight: row.employee_id === selectedEmployeeId ? 800 : 600 }}
                          >
                            {row.employee_name}
                          </Button>
                        </TableCell>
                        <TableCell align="right">{formatCurrency(row.bank_transfer)}</TableCell>
                        <TableCell align="right">{formatCurrency(row.cash_expense)}</TableCell>
                        <TableCell align="right">{formatCurrency(row.account_current)}</TableCell>
                        <TableCell align="right"><strong>{formatCurrency(row.total)}</strong></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            ) : !monthlyLoading && (
              <EmptyState
                icon={BadgeIcon}
                testId="employee-summary-empty"
                title={employeeView === 'monthly' ? `Sin actividad en ${year}` : `Sin actividad en ${MONTHS[Number(month) - 1]?.label.toLocaleLowerCase('es')}`}
                description={employeeView === 'monthly'
                  ? 'No se detectaron importes de empleados durante el anio seleccionado.'
                  : 'No se detectaron transferencias, efectivo ni cuenta corriente para este periodo.'}
              />
            )}

            {selectedEmployee && (
              <Box sx={{ mt: 2, pt: 2, borderTop: '1px solid rgba(255,255,255,0.12)' }}>
                <Stack direction="row" justifyContent="space-between" alignItems="baseline" spacing={2}>
                  <Typography fontWeight={800}>{selectedEmployee.employee_name}</Typography>
                  <Typography variant="h6" fontWeight={800}>{formatCurrency(selectedEmployee.total)}</Typography>
                </Stack>
                <Box sx={{ height: employeeView === 'monthly' ? 290 : 250, mt: 1 }}>
                  {employeeView === 'monthly' ? (
                    <Bar data={monthlyChartData} options={monthlyChartOptions} />
                  ) : (
                    <Doughnut data={compositionChartData} options={compositionChartOptions} />
                  )}
                </Box>
              </Box>
            )}
          </CardContent>
        </Card>

        <Card data-testid="movements-card" sx={{ minWidth: 0, height: '100%' }}>
          <CardContent sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
            <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', sm: 'baseline' }} spacing={0.5}>
              <Typography variant="h6" fontWeight={700}>Movimientos detectados</Typography>
              <Typography variant="caption" color="text.secondary">
                {filteredMovements.length} de {movements.length} movimientos
              </Typography>
            </Stack>
            {movements.length > 0 && <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'minmax(180px, 1fr) minmax(150px, 0.7fr) minmax(150px, 0.7fr)' }, gap: 1.5, mt: 2 }}>
              <TextField
                size="small"
                label="Buscar movimiento"
                value={movementSearch}
                onChange={(event) => setMovementSearch(event.target.value)}
              />
              <FormControl size="small">
                <InputLabel id="movement-employee-label">Empleado</InputLabel>
                <Select
                  id="movement-employee"
                  labelId="movement-employee-label"
                  label="Empleado"
                  value={movementEmployee}
                  onChange={(event) => setMovementEmployee(event.target.value)}
                >
                  <MenuItem value="all">Todos</MenuItem>
                  {movementEmployeeOptions.map((employee) => (
                    <MenuItem key={employee.id} value={employee.id}>{employee.name}</MenuItem>
                  ))}
                </Select>
              </FormControl>
              <FormControl size="small">
                <InputLabel id="movement-source-label">Origen</InputLabel>
                <Select
                  id="movement-source"
                  labelId="movement-source-label"
                  label="Origen"
                  value={movementSource}
                  onChange={(event) => setMovementSource(event.target.value)}
                >
                  <MenuItem value="all">Todos</MenuItem>
                  {Object.entries(CHART_LABELS).map(([source, label]) => (
                    <MenuItem key={source} value={source}>{label}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Box>}
            <Divider sx={{ my: 2 }} />
            {paginatedMovements.length ? (
              <TableContainer sx={{ maxHeight: 560 }}>
                <Table stickyHeader size="small" sx={{ minWidth: 820 }}>
                  <TableHead>
                    <TableRow>
                      <TableCell>Fecha</TableCell>
                      <TableCell>Empleado</TableCell>
                      <TableCell>Origen</TableCell>
                      <TableCell>Detalle</TableCell>
                      <TableCell align="right">Importe</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {paginatedMovements.map((movement) => (
                      <TableRow key={movement.id} hover>
                      <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDate(movement.date)}</TableCell>
                      <TableCell>{movement.employee_name}</TableCell>
                      <TableCell>
                        <Chip size="small" color={SOURCE_COLORS[movement.source] || 'default'} label={movement.source_label} />
                      </TableCell>
                      <TableCell sx={{ minWidth: 260, overflowWrap: 'anywhere' }}>
                        <Typography variant="body2">{movement.description}</Typography>
                        {movement.account_deduction && (
                          <Typography variant="caption" color="text.secondary">
                            Bruto {formatCurrency(movement.account_deduction.gross_amount)} · Beneficio {movement.account_deduction.discount_percent}% ({formatCurrency(movement.account_deduction.discount_amount)}) · {movement.account_deduction.status_label}
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>{formatCurrency(movement.amount)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            ) : (
              <EmptyState
                icon={PointOfSaleIcon}
                testId="movements-empty"
                title={movements.length ? 'Sin resultados' : `Sin movimientos en ${MONTHS[Number(month) - 1]?.label.toLocaleLowerCase('es')}`}
                description={movements.length
                  ? 'Los filtros actuales no coinciden con ningun movimiento detectado.'
                  : 'No se detectaron movimientos de empleados para este periodo.'}
                action={movements.length ? (
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() => {
                      setMovementSearch('')
                      setMovementEmployee('all')
                      setMovementSource('all')
                    }}
                  >
                    Limpiar filtros
                  </Button>
                ) : null}
              />
            )}
            {filteredMovements.length > 0 && <TablePagination
              component="div"
              count={filteredMovements.length}
              page={movementPage}
              onPageChange={(_event, page) => setMovementPage(page)}
              rowsPerPage={movementRowsPerPage}
              onRowsPerPageChange={(event) => setMovementRowsPerPage(Number(event.target.value))}
              rowsPerPageOptions={[10, 25, 50]}
              labelRowsPerPage="Filas"
              labelDisplayedRows={({ from, to, count }) => `${from}-${to} de ${count}`}
              sx={{
                '.MuiTablePagination-toolbar': { px: 0, flexWrap: 'wrap', justifyContent: 'flex-end' },
                '.MuiTablePagination-spacer': { display: { xs: 'none', sm: 'block' } },
              }}
            />}
          </CardContent>
        </Card>
      </Box>

      <Card>
        <CardContent>
          <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ xs: 'stretch', sm: 'center' }} spacing={1.5}>
            <Box>
              <Typography variant="h6" fontWeight={700}>Gestion de empleados</Typography>
              <Typography variant="caption" color="text.secondary">
                {employeesInBranch.filter((employee) => employee.active).length} activos y {employeesInBranch.filter((employee) => !employee.active).length} de baja - {selectedBranchName}
              </Typography>
            </Box>
            <ToggleButtonGroup
              exclusive
              size="small"
              value={employeeStatusFilter}
              onChange={(_event, value) => value && setEmployeeStatusFilter(value)}
              aria-label="Estado de empleados"
            >
              <ToggleButton value="active">Activos</ToggleButton>
              <ToggleButton value="inactive">Bajas</ToggleButton>
              <ToggleButton value="all">Todos</ToggleButton>
            </ToggleButtonGroup>
          </Stack>
          <Divider sx={{ my: 2 }} />
          <TableContainer>
            <Table size="small" sx={{ minWidth: 820 }}>
              <TableHead>
                <TableRow>
                  <TableCell>Empleado</TableCell>
                  <TableCell>Sucursal</TableCell>
                  <TableCell>Documento</TableCell>
                  <TableCell>Ingreso</TableCell>
                  <TableCell>Cuenta corriente</TableCell>
                  <TableCell align="right">Desc. CC</TableCell>
                  <TableCell>Estado</TableCell>
                  <TableCell>Fecha de baja</TableCell>
                  <TableCell align="right">Acciones</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filteredEmployees.map((employee) => (
                  <TableRow key={employee.id} hover>
                    <TableCell>
                      <Typography fontWeight={700}>{employee.name}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {(employee.aliases || []).filter((alias) => alias.toLocaleLowerCase('es') !== employee.name.toLocaleLowerCase('es')).join(', ') || 'Sin aliases adicionales'}
                      </Typography>
                    </TableCell>
                    <TableCell>{employee.branch_name || 'Sin sucursal'}</TableCell>
                    <TableCell>{formatDocument(employee)}</TableCell>
                    <TableCell>{employee.hire_date ? formatDate(employee.hire_date) : '-'}</TableCell>
                    <TableCell>{employee.account_client_name || 'Sin vincular'}</TableCell>
                    <TableCell align="right">{Number(employee.account_discount_percent || 0).toLocaleString('es-AR', { maximumFractionDigits: 2 })}%</TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        color={employee.active ? 'success' : 'default'}
                        label={employee.active ? 'Activo' : employee.termination_reason_label || 'Baja'}
                      />
                    </TableCell>
                    <TableCell>{employee.termination_date ? formatDate(employee.termination_date) : '-'}</TableCell>
                    <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>
                      <Tooltip title="Editar empleado">
                        <IconButton size="small" onClick={() => openEditEmployee(employee)} aria-label={`Editar ${employee.name}`}>
                          <EditIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      {employee.active ? (
                        <Tooltip title="Dar de baja">
                          <IconButton size="small" color="error" onClick={() => openStatusDialog(employee, 'deactivate')} aria-label={`Dar de baja a ${employee.name}`}>
                            <PersonOffIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      ) : (
                        <Tooltip title="Reactivar empleado">
                          <IconButton size="small" color="success" onClick={() => openStatusDialog(employee, 'reactivate')} aria-label={`Reactivar a ${employee.name}`}>
                            <RestoreIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {!filteredEmployees.length && (
                  <TableRow>
                      <TableCell colSpan={9}>
                      <Typography color="text.secondary">No hay empleados en este estado.</Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ xs: 'stretch', md: 'center' }} spacing={2}>
            <Stack direction="row" spacing={1.25} alignItems="center">
              <CalculateIcon color="primary" />
              <Box>
                <Typography variant="h6" fontWeight={700}>Aguinaldo estimado</Typography>
                <Typography variant="caption" color="text.secondary">Sueldo Anual Complementario</Typography>
              </Box>
            </Stack>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
              <FormControl size="small" sx={{ minWidth: 220 }}>
                <InputLabel id="sac-employee-label">Empleado</InputLabel>
                <Select
                  labelId="sac-employee-label"
                  label="Empleado"
                  value={activeEmployees.some((employee) => employee.id === sacEmployeeId) ? sacEmployeeId : ''}
                  onChange={(event) => setSacEmployeeId(event.target.value)}
                >
                  {activeEmployees.map((employee) => (
                    <MenuItem key={employee.id} value={employee.id}>{employee.name}</MenuItem>
                  ))}
                </Select>
              </FormControl>
              <ToggleButtonGroup
                exclusive
                size="small"
                value={sacSemester}
                onChange={(_event, value) => value && setSacSemester(value)}
                aria-label="Semestre del aguinaldo"
              >
                <ToggleButton value="1">Ene-Jun</ToggleButton>
                <ToggleButton value="2">Jul-Dic</ToggleButton>
              </ToggleButtonGroup>
            </Stack>
          </Stack>

          {sacLoading && <LinearProgress sx={{ mt: 2 }} />}
          {!activeEmployees.length && <Alert severity="warning" sx={{ mt: 2 }}>No hay empleados activos.</Alert>}
          {sacData && !sacLoading && (
            <>
              <Divider sx={{ my: 2 }} />
              <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, minmax(0, 1fr))' }, gap: 2 }}>
                <Box>
                  <Typography variant="caption" color="text.secondary">Importe estimado</Typography>
                  <Typography variant="h4" fontWeight={800}>{formatCurrency(sacData.sac_amount)}</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">Mejor remuneracion</Typography>
                  <Typography variant="h6" fontWeight={700}>{formatCurrency(sacData.best_remuneration)}</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">Mes base</Typography>
                  <Typography variant="h6" fontWeight={700}>{sacData.best_month_label}</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">Proporcionalidad</Typography>
                  <Typography variant="h6" fontWeight={700}>
                    {(Number(sacData.proportion || 0) * 100).toLocaleString('es-AR', { maximumFractionDigits: 1 })}%
                  </Typography>
                  <Typography variant="caption" color="text.secondary">{sacData.worked_days} de {sacData.semester_days} dias</Typography>
                </Box>
              </Box>

              <Stack spacing={1} sx={{ mt: 2 }}>
                {!sacData.employment_period_confirmed && (
                  <Alert severity="warning">Falta la fecha de ingreso. La proporcionalidad considera el semestre completo.</Alert>
                )}
                {!sacData.complete && (
                  <Alert severity="info">{sacData.confirmed_months} de {sacData.required_months} remuneraciones confirmadas. Los meses restantes usan importes detectados.</Alert>
                )}
              </Stack>

              <TableContainer sx={{ mt: 2 }}>
                <Table size="small" sx={{ minWidth: 720 }}>
                  <TableHead>
                    <TableRow>
                      <TableCell>Mes</TableCell>
                      <TableCell align="right">Detectado</TableCell>
                      <TableCell>Remuneracion computable</TableCell>
                      <TableCell align="right">Usado en calculo</TableCell>
                      <TableCell>Estado</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {sacData.months.map((item) => (
                      <TableRow key={item.month}>
                        <TableCell>{item.month_label}</TableCell>
                        <TableCell align="right">{formatCurrency(item.detected_amount)}</TableCell>
                        <TableCell sx={{ width: 240 }}>
                          <TextField
                            size="small"
                            type="number"
                            value={sacDraft[String(item.month)] ?? ''}
                            placeholder={String(item.detected_amount || 0)}
                            onChange={(event) => setSacDraft((prev) => ({ ...prev, [String(item.month)]: event.target.value }))}
                            slotProps={{ htmlInput: { min: 0, step: '0.01', 'aria-label': `Remuneracion computable ${item.month_label}` } }}
                            fullWidth
                          />
                        </TableCell>
                        <TableCell align="right">{formatCurrency(item.effective_amount)}</TableCell>
                        <TableCell>
                          <Chip
                            size="small"
                            color={item.confirmed ? 'success' : 'default'}
                            label={item.confirmed ? 'Confirmada' : 'Sugerida'}
                          />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
              <Stack direction="row" justifyContent="flex-end" sx={{ mt: 2 }}>
                <Button
                  variant="contained"
                  startIcon={<SaveIcon />}
                  onClick={saveAguinaldoRemunerations}
                  disabled={sacSaving || sacLoading}
                >
                  Guardar remuneraciones
                </Button>
              </Stack>
            </>
          )}
        </CardContent>
      </Card>

      <Dialog open={deductionDialog.open} onClose={() => !deductionLoading && setDeductionDialog({ open: false, row: null })} fullWidth maxWidth="xs">
        <DialogTitle>Confirmar descuento de cuenta corriente</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <Typography fontWeight={700}>{deductionDialog.row?.employee_name}</Typography>
            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1.5 }}>
              <Box>
                <Typography variant="caption" color="text.secondary">Consumo bruto</Typography>
                <Typography fontWeight={700}>{formatCurrency(deductionDialog.row?.pending_gross_amount)}</Typography>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary">Beneficio</Typography>
                <Typography fontWeight={700}>{formatCurrency(deductionDialog.row?.pending_discount_amount)}</Typography>
              </Box>
              <Box sx={{ gridColumn: '1 / -1' }}>
                <Typography variant="caption" color="text.secondary">Neto que se trasladara al sueldo</Typography>
                <Typography variant="h5" fontWeight={800}>{formatCurrency(deductionDialog.row?.pending_net_amount)}</Typography>
              </Box>
            </Box>
            <Alert severity="warning">Al confirmar, estos consumos quedaran cancelados en cuenta corriente y el calculo del mes no cambiara aunque luego se modifique el porcentaje.</Alert>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeductionDialog({ open: false, row: null })} disabled={deductionLoading}>Cancelar</Button>
          <Button variant="contained" onClick={confirmAccountDeductions} disabled={deductionLoading}>Confirmar descuento</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={Boolean(editEmployee)} onClose={() => !actionLoading && setEditEmployee(null)} fullWidth maxWidth="md">
        <DialogTitle>Editar empleado</DialogTitle>
        <DialogContent dividers>
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))' }, gap: 2, pt: 0.5 }}>
            <TextField
              label="Nombre"
              value={editEmployeeForm.name}
              onChange={(event) => setEditEmployeeForm((prev) => ({ ...prev, name: event.target.value }))}
            />
            <TextField
              select
              required
              label="Sucursal"
              value={editEmployeeForm.branchId}
              onChange={(event) => setEditEmployeeForm((prev) => ({ ...prev, branchId: event.target.value }))}
            >
              {branches.map((branch) => <MenuItem key={branch.id} value={String(branch.id)}>{branch.name}</MenuItem>)}
            </TextField>
            <TextField
              label="Aliases separados por coma"
              value={editEmployeeForm.aliases}
              onChange={(event) => setEditEmployeeForm((prev) => ({ ...prev, aliases: event.target.value }))}
            />
            <TextField
              select
              label="Tipo de documento"
              value={editEmployeeForm.documentType}
              onChange={(event) => setEditEmployeeForm((prev) => ({
                ...prev,
                documentType: event.target.value,
                documentNumber: event.target.value ? prev.documentNumber : '',
              }))}
            >
              <MenuItem value="">Sin documento</MenuItem>
              {DOCUMENT_TYPES.map((item) => <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>)}
            </TextField>
            <TextField
              label={editEmployeeForm.documentType === 'cuil_cuit' ? 'CUIL/CUIT' : 'DNI'}
              value={editEmployeeForm.documentNumber}
              disabled={!editEmployeeForm.documentType}
              onChange={(event) => setEditEmployeeForm((prev) => ({ ...prev, documentNumber: event.target.value }))}
              slotProps={{ htmlInput: { inputMode: 'numeric' } }}
            />
            <TextField
              type="date"
              label="Fecha de ingreso"
              value={editEmployeeForm.hireDate}
              onChange={(event) => setEditEmployeeForm((prev) => ({ ...prev, hireDate: event.target.value }))}
              slotProps={{ inputLabel: { shrink: true } }}
            />
            <Autocomplete
              options={clients}
              value={editEmployeeForm.accountClient}
              onChange={(_event, value) => setEditEmployeeForm((prev) => ({ ...prev, accountClient: value }))}
              onInputChange={searchAccountClients}
              getOptionLabel={(option) => option.full_name || option.external_id || ''}
              getOptionDisabled={(option) => accountClientIsLinked(option, editEmployee?.id)}
              isOptionEqualToValue={(option, value) => option.id === value.id}
              renderInput={(params) => <TextField {...params} label="Cliente cuenta corriente" />}
            />
            <TextField
              type="number"
              label="Descuento cuenta corriente (%)"
              value={editEmployeeForm.discountPercent}
              onChange={(event) => setEditEmployeeForm((prev) => ({ ...prev, discountPercent: event.target.value }))}
              slotProps={{ htmlInput: { min: 0, max: 100, step: '0.01' } }}
            />
            <TextField
              label="Notas"
              value={editEmployeeForm.notes}
              onChange={(event) => setEditEmployeeForm((prev) => ({ ...prev, notes: event.target.value }))}
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditEmployee(null)} disabled={actionLoading}>Cancelar</Button>
          <Button
            variant="contained"
            onClick={saveEmployee}
            disabled={actionLoading || !editEmployeeForm.branchId || editEmployeeForm.name.trim().length < 2 || Boolean(editEmployeeForm.documentType) !== Boolean(editEmployeeForm.documentNumber.trim())}
          >
            Guardar
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={statusDialog.open} onClose={() => !actionLoading && setStatusDialog((prev) => ({ ...prev, open: false }))} fullWidth maxWidth="xs">
        <DialogTitle>{statusDialog.mode === 'deactivate' ? 'Dar de baja al empleado' : 'Reactivar empleado'}</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <Typography fontWeight={700}>{statusDialog.employee?.name}</Typography>
            {statusDialog.mode === 'deactivate' ? (
              <>
                <TextField
                  select
                  label="Motivo"
                  value={statusDialog.reason}
                  onChange={(event) => setStatusDialog((prev) => ({ ...prev, reason: event.target.value }))}
                >
                  {TERMINATION_REASONS.map((item) => <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>)}
                </TextField>
                <TextField
                  type="date"
                  label="Fecha de baja"
                  value={statusDialog.date}
                  onChange={(event) => setStatusDialog((prev) => ({ ...prev, date: event.target.value }))}
                  slotProps={{ inputLabel: { shrink: true } }}
                />
              </>
            ) : (
              <Typography color="text.secondary">El empleado volvera a participar de las sincronizaciones automaticas.</Typography>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setStatusDialog((prev) => ({ ...prev, open: false }))} disabled={actionLoading}>Cancelar</Button>
          <Button
            variant="contained"
            color={statusDialog.mode === 'deactivate' ? 'error' : 'success'}
            onClick={confirmStatusChange}
            disabled={actionLoading || (statusDialog.mode === 'deactivate' && (!statusDialog.reason || !statusDialog.date))}
          >
            {statusDialog.mode === 'deactivate' ? 'Confirmar baja' : 'Reactivar'}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  )
}
