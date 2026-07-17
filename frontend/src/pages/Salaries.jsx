import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  FormControl,
  InputLabel,
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
  Typography,
} from '@mui/material'
import AccountBalanceIcon from '@mui/icons-material/AccountBalance'
import BadgeIcon from '@mui/icons-material/Badge'
import LocalAtmIcon from '@mui/icons-material/LocalAtm'
import PointOfSaleIcon from '@mui/icons-material/PointOfSale'
import SyncIcon from '@mui/icons-material/Sync'
import { Bar, Doughnut } from 'react-chartjs-2'
import { ArcElement, BarElement, CategoryScale, Chart, Legend, LinearScale, Tooltip } from 'chart.js'
import { useAuth } from '../context/AuthContext.jsx'
import { API_BASE } from '../config'

Chart.register(ArcElement, BarElement, CategoryScale, LinearScale, Tooltip, Legend)

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
  const [employeeForm, setEmployeeForm] = useState({
    name: '',
    aliases: '',
    accountClient: null,
  })

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

  useEffect(() => {
    fetchSummary()
  }, [fetchSummary])

  useEffect(() => {
    fetchEmployees()
  }, [fetchEmployees])

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
          aliases,
          account_client_id: employeeForm.accountClient?.id || null,
        }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo crear el empleado')
      setSuccess(`Empleado creado: ${data.name}`)
      setEmployeeForm({ name: '', aliases: '', accountClient: null })
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
              <Typography variant="h6" fontWeight={700}>Alta rapida de empleado</Typography>
              <Typography variant="body2" color="text.secondary">
                Los aliases ayudan a reconocer nombres en extractos, gastos y cuenta corriente.
              </Typography>
            </Box>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <TextField
                label="Nombre"
                value={employeeForm.name}
                onChange={(event) => setEmployeeForm((prev) => ({ ...prev, name: event.target.value }))}
                sx={{ minWidth: { md: 220 } }}
              />
              <TextField
                label="Aliases separados por coma"
                value={employeeForm.aliases}
                onChange={(event) => setEmployeeForm((prev) => ({ ...prev, aliases: event.target.value }))}
                sx={{ minWidth: { md: 280 } }}
              />
              <Autocomplete
                options={clients}
                value={employeeForm.accountClient}
                onChange={(_event, value) => setEmployeeForm((prev) => ({ ...prev, accountClient: value }))}
                getOptionLabel={(option) => option.full_name || option.external_id || ''}
                sx={{ minWidth: { md: 260 } }}
                renderInput={(params) => <TextField {...params} label="Cliente cuenta corriente" />}
              />
              <Button variant="contained" disabled={actionLoading || employeeForm.name.trim().length < 2} onClick={createEmployee}>
                Crear
              </Button>
            </Stack>
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
          <Typography variant="h6" fontWeight={700}>Empleados configurados</Typography>
          <Divider sx={{ my: 2 }} />
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {employees.map((employee) => (
              <Chip
                key={employee.id}
                label={`${employee.name}${employee.aliases?.length ? ` (${employee.aliases.join(', ')})` : ''}`}
                color={employee.active ? 'primary' : 'default'}
                variant="outlined"
              />
            ))}
            {!employees.length && <Typography color="text.secondary">No hay empleados cargados.</Typography>}
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  )
}
