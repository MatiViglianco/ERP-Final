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
import { Bar, Doughnut } from 'react-chartjs-2'
import { ArcElement, BarElement, CategoryScale, Chart, Legend, LinearScale, Tooltip as ChartTooltip } from 'chart.js'
import { useAuth } from '../context/AuthContext.jsx'
import { API_BASE } from '../config'

Chart.register(ArcElement, BarElement, CategoryScale, LinearScale, ChartTooltip, Legend)

const API_SALARIES_SUMMARY = `${API_BASE}/salaries/summary/`
const API_SALARIES_MONTHLY = `${API_BASE}/salaries/monthly/`
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
  documentType: '',
  documentNumber: '',
  aliases: '',
  accountClient: null,
  notes: '',
})

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
  const now = new Date()
  const [year, setYear] = useState(String(now.getFullYear()))
  const [month, setMonth] = useState(String(now.getMonth() + 1))
  const [summary, setSummary] = useState(null)
  const [employees, setEmployees] = useState([])
  const [clients, setClients] = useState([])
  const [loading, setLoading] = useState(false)
  const [monthlyLoading, setMonthlyLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [monthlySummary, setMonthlySummary] = useState(null)
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
  const accountSearchTimer = useRef(null)

  const queryString = useMemo(() => new URLSearchParams({ year, month }).toString(), [year, month])

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
      const resp = await authFetch(`${API_SALARIES_MONTHLY}?${params.toString()}`)
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo cargar la evolucion mensual')
      setMonthlySummary(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setMonthlyLoading(false)
    }
  }, [authFetch, year])

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

  useEffect(() => () => {
    if (accountSearchTimer.current) clearTimeout(accountSearchTimer.current)
  }, [])

  useEffect(() => {
    if (employeeView === 'monthly' && monthlySummary?.year !== Number(year)) fetchMonthlySummary()
  }, [employeeView, fetchMonthlySummary, monthlySummary?.year, year])

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
          document_type: employeeForm.documentType,
          document_number: employeeForm.documentNumber,
          aliases,
          account_client_id: employeeForm.accountClient?.id || null,
          notes: employeeForm.notes,
        }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo crear el empleado')
      setSuccess(`Empleado creado: ${data.name}`)
      setEmployeeForm(emptyEmployeeForm())
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
      documentType: employee.document_type || '',
      documentNumber: employee.document_number || '',
      aliases: (employee.aliases || []).join(', '),
      accountClient: linkedClient,
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
          document_type: editEmployeeForm.documentType,
          document_number: editEmployeeForm.documentNumber,
          aliases,
          account_client_id: editEmployeeForm.accountClient?.id || null,
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
      ])
    } catch (err) {
      setError(err.message)
    } finally {
      setActionLoading(false)
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

  const totals = summary?.totals || {}
  const movements = summary?.movements || []
  const employeeRows = summary?.employees || []
  const sources = summary?.sources || {}
  const latestBankDates = sources.latest_bank_dates || {}
  const annualEmployeeRows = monthlySummary?.year === Number(year) ? (monthlySummary.employees || []) : []
  const displayedEmployeeRows = employeeView === 'monthly' ? annualEmployeeRows : employeeRows
  const filteredEmployees = employees.filter((employee) => (
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
    setMovementPage(0)
  }, [movementSearch, movementEmployee, movementSource, movementRowsPerPage, movements])

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
        <FormControl sx={{ minWidth: 150 }}>
          <InputLabel>Anio</InputLabel>
          <Select label="Anio" value={year} onChange={(event) => setYear(event.target.value)}>
            {[now.getFullYear() - 1, now.getFullYear(), now.getFullYear() + 1].map((item) => (
              <MenuItem key={item} value={String(item)}>{item}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl sx={{ minWidth: 180 }}>
          <InputLabel>Mes</InputLabel>
          <Select label="Mes" value={month} onChange={(event) => setMonth(event.target.value)}>
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
          <Stack spacing={2}>
            <Box>
              <Typography variant="h6" fontWeight={700}>Alta de empleado</Typography>
              <Typography variant="body2" color="text.secondary">
                Los aliases ayudan a reconocer nombres en extractos, gastos y cuenta corriente.
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
                label="Notas"
                value={employeeForm.notes}
                onChange={(event) => setEmployeeForm((prev) => ({ ...prev, notes: event.target.value }))}
                sx={{ gridColumn: { md: 'span 2' } }}
              />
              <Button
                variant="contained"
                disabled={actionLoading || employeeForm.name.trim().length < 2 || Boolean(employeeForm.documentType) !== Boolean(employeeForm.documentNumber.trim())}
                onClick={createEmployee}
                sx={{ minHeight: 44 }}
              >
                Crear
              </Button>
            </Box>
          </Stack>
        </CardContent>
      </Card>

      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(0, 1fr) minmax(0, 1.25fr)' }, gap: 2, alignItems: 'start' }}>
        <Card>
          <CardContent>
            <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ xs: 'stretch', sm: 'center' }} spacing={1.5}>
              <Box>
                <Typography variant="h6" fontWeight={700}>Resumen por empleado</Typography>
                <Typography variant="caption" color="text.secondary">
                  {employeeView === 'monthly' ? `Acumulado y evolucion de ${year}` : `${MONTHS[Number(month) - 1]?.label} ${year}`}
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
                      onClick={() => setSelectedEmployeeId(row.employee_id)}
                      sx={{ cursor: 'pointer' }}
                    >
                      <TableCell>
                        <Button
                          size="small"
                          color="inherit"
                          onClick={() => setSelectedEmployeeId(row.employee_id)}
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
                  {!displayedEmployeeRows.length && !monthlyLoading && (
                    <TableRow>
                      <TableCell colSpan={5}>
                        <Typography color="text.secondary">
                          {employeeView === 'monthly' ? 'Sin movimientos detectados en el anio.' : 'Sin movimientos detectados en el periodo.'}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>

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

        <Card>
          <CardContent>
            <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', sm: 'baseline' }} spacing={0.5}>
              <Typography variant="h6" fontWeight={700}>Movimientos detectados</Typography>
              <Typography variant="caption" color="text.secondary">
                {filteredMovements.length} de {movements.length} movimientos
              </Typography>
            </Stack>
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'minmax(180px, 1fr) minmax(150px, 0.7fr) minmax(150px, 0.7fr)' }, gap: 1.5, mt: 2 }}>
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
            </Box>
            <Divider sx={{ my: 2 }} />
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
                      <TableCell sx={{ minWidth: 260, overflowWrap: 'anywhere' }}>{movement.description}</TableCell>
                      <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>{formatCurrency(movement.amount)}</TableCell>
                    </TableRow>
                  ))}
                  {!paginatedMovements.length && (
                    <TableRow>
                      <TableCell colSpan={5}>
                        <Typography color="text.secondary">
                          {movements.length ? 'Ningun movimiento coincide con los filtros.' : 'No hay movimientos para mostrar.'}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>
            <TablePagination
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
            />
          </CardContent>
        </Card>
      </Box>

      <Card>
        <CardContent>
          <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ xs: 'stretch', sm: 'center' }} spacing={1.5}>
            <Box>
              <Typography variant="h6" fontWeight={700}>Gestion de empleados</Typography>
              <Typography variant="caption" color="text.secondary">
                {employees.filter((employee) => employee.active).length} activos y {employees.filter((employee) => !employee.active).length} de baja
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
                  <TableCell>Documento</TableCell>
                  <TableCell>Cuenta corriente</TableCell>
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
                    <TableCell>{formatDocument(employee)}</TableCell>
                    <TableCell>{employee.account_client_name || 'Sin vincular'}</TableCell>
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
                    <TableCell colSpan={6}>
                      <Typography color="text.secondary">No hay empleados en este estado.</Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>

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
            disabled={actionLoading || editEmployeeForm.name.trim().length < 2 || Boolean(editEmployeeForm.documentType) !== Boolean(editEmployeeForm.documentNumber.trim())}
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
