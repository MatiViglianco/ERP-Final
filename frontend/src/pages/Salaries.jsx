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
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import AccountBalanceIcon from '@mui/icons-material/AccountBalance'
import BadgeIcon from '@mui/icons-material/Badge'
import LocalAtmIcon from '@mui/icons-material/LocalAtm'
import LinkIcon from '@mui/icons-material/Link'
import PersonAddIcon from '@mui/icons-material/PersonAdd'
import PointOfSaleIcon from '@mui/icons-material/PointOfSale'
import SyncIcon from '@mui/icons-material/Sync'
import { useAuth } from '../context/AuthContext.jsx'
import { API_BASE } from '../config'

const API_SALARIES_SUMMARY = `${API_BASE}/salaries/summary/`
const API_EMPLOYEES = `${API_BASE}/salaries/employees/`
const API_ASSIGN_MOVEMENT = `${API_BASE}/salaries/movements/assign/`
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

function formatCurrency(value) {
  return `$ ${Number(value || 0).toLocaleString('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

function formatDate(value) {
  if (!value) return 'Sin datos'
  const [year, month, day] = value.split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString('es-AR')
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
  const [actionLoading, setActionLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [candidateEmployees, setCandidateEmployees] = useState({})
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
      await Promise.all([fetchEmployees(), fetchSummary()])
    } catch (err) {
      setError(err.message)
    } finally {
      setActionLoading(false)
    }
  }

  const prepareEmployee = (candidate) => {
    const accountClient = clients.find((client) => client.id === candidate.account_client_id) || null
    setEmployeeForm({
      name: candidate.suggested_name || '',
      aliases: candidate.suggested_alias || '',
      accountClient,
    })
    setSuccess('Datos preparados. Revisa el nombre y presiona Crear.')
    document.getElementById('employee-setup')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  const assignCandidate = async (candidate) => {
    const employeeId = candidateEmployees[`${candidate.source}:${candidate.source_id}`]
    if (!employeeId) return
    setActionLoading(true)
    setError('')
    setSuccess('')
    try {
      const resp = await authFetch(API_ASSIGN_MOVEMENT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          employee_id: employeeId,
          source: candidate.source,
          source_id: candidate.source_id,
          alias: candidate.suggested_alias || '',
        }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo asignar el movimiento')
      setSuccess(`Movimiento asignado a ${data.employee_name}`)
      setCandidateEmployees((prev) => {
        const next = { ...prev }
        delete next[`${candidate.source}:${candidate.source_id}`]
        return next
      })
      await Promise.all([fetchEmployees(), fetchSummary()])
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
  const unmatched = summary?.unmatched || { count: 0, counts: {}, items: [] }
  const latestBankDates = sources.latest_bank_dates || {}

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
        <Button variant="outlined" startIcon={<SyncIcon />} disabled={loading} onClick={fetchSummary}>
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
      {summary && unmatched.count > 0 && (
        <Alert severity="warning">
          Hay {unmatched.count} movimientos pendientes de identificar. Asigna solamente los que correspondan a empleados.
        </Alert>
      )}

      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(4, minmax(0, 1fr))' }, gap: 2 }}>
        <SummaryCard icon={<BadgeIcon color="primary" />} label="Total empleados" value={totals.total} detail={`${employeeRows.length} empleados con movimientos`} />
        <SummaryCard icon={<AccountBalanceIcon color="info" />} label="Transferencias" value={totals.bank_transfer} detail="Egresos detectados en bancos" />
        <SummaryCard icon={<LocalAtmIcon color="success" />} label="Efectivo" value={totals.cash_expense} detail="Gastos en efectivo / sueldos" />
        <SummaryCard icon={<PointOfSaleIcon color="warning" />} label="Cuenta corriente" value={totals.account_current} detail="Retiros o vales vinculados" />
      </Box>

      {unmatched.count > 0 && (
        <Card>
          <CardContent>
            <Typography variant="h6" fontWeight={700}>Pendientes de identificar</Typography>
            <Typography variant="body2" color="text.secondary">
              Transferencias, gastos en Sueldos y consumos de cuenta corriente que todavia no tienen empleado asociado.
            </Typography>
            <Divider sx={{ my: 2 }} />
            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small" sx={{ minWidth: 860 }}>
                <TableHead>
                  <TableRow>
                    <TableCell>Fecha</TableCell>
                    <TableCell>Origen</TableCell>
                    <TableCell>Detalle</TableCell>
                    <TableCell align="right">Importe</TableCell>
                    <TableCell>Empleado</TableCell>
                    <TableCell align="right">Accion</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(unmatched.items || []).map((candidate) => {
                    const candidateKey = `${candidate.source}:${candidate.source_id}`
                    return (
                      <TableRow key={candidateKey}>
                        <TableCell>{formatDate(candidate.date)}</TableCell>
                        <TableCell>
                          <Chip size="small" color={SOURCE_COLORS[candidate.source] || 'default'} label={candidate.source_label} />
                        </TableCell>
                        <TableCell>{candidate.description}</TableCell>
                        <TableCell align="right">{formatCurrency(candidate.amount)}</TableCell>
                        <TableCell sx={{ minWidth: 210 }}>
                          {employees.length ? (
                            <FormControl fullWidth size="small">
                              <InputLabel>Empleado</InputLabel>
                              <Select
                                label="Empleado"
                                value={candidateEmployees[candidateKey] || ''}
                                onChange={(event) => setCandidateEmployees((prev) => ({ ...prev, [candidateKey]: event.target.value }))}
                              >
                                {employees.filter((employee) => employee.active).map((employee) => (
                                  <MenuItem key={employee.id} value={employee.id}>{employee.name}</MenuItem>
                                ))}
                              </Select>
                            </FormControl>
                          ) : (
                            <Typography variant="body2" color="text.secondary">Primero crea el empleado</Typography>
                          )}
                        </TableCell>
                        <TableCell align="right">
                          {employees.length ? (
                            <Button
                              size="small"
                              variant="outlined"
                              startIcon={<LinkIcon />}
                              disabled={actionLoading || !candidateEmployees[candidateKey]}
                              onClick={() => assignCandidate(candidate)}
                            >
                              Asignar
                            </Button>
                          ) : (
                            <Button size="small" variant="outlined" startIcon={<PersonAddIcon />} onClick={() => prepareEmployee(candidate)}>
                              Preparar alta
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </Box>
            {unmatched.truncated && (
              <Typography variant="caption" color="text.secondary">Se muestran los primeros 100 pendientes.</Typography>
            )}
          </CardContent>
        </Card>
      )}

      <Card id="employee-setup">
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

      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(0, 5fr) minmax(0, 7fr)' }, gap: 2 }}>
        <Card>
          <CardContent>
            <Typography variant="h6" fontWeight={700}>Resumen por empleado</Typography>
            <Divider sx={{ my: 2 }} />
            <Table size="small">
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
                {employeeRows.map((row) => (
                  <TableRow key={row.employee_id}>
                    <TableCell>{row.employee_name}</TableCell>
                    <TableCell align="right">{formatCurrency(row.bank_transfer)}</TableCell>
                    <TableCell align="right">{formatCurrency(row.cash_expense)}</TableCell>
                    <TableCell align="right">{formatCurrency(row.account_current)}</TableCell>
                    <TableCell align="right"><strong>{formatCurrency(row.total)}</strong></TableCell>
                  </TableRow>
                ))}
                {!employeeRows.length && (
                  <TableRow>
                    <TableCell colSpan={5}>
                      <Typography color="text.secondary">Sin movimientos detectados en el periodo.</Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <Typography variant="h6" fontWeight={700}>Movimientos detectados</Typography>
            <Divider sx={{ my: 2 }} />
            <Table size="small">
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
                {movements.map((movement) => (
                  <TableRow key={movement.id}>
                    <TableCell>{movement.date}</TableCell>
                    <TableCell>{movement.employee_name}</TableCell>
                    <TableCell>
                      <Chip size="small" color={SOURCE_COLORS[movement.source] || 'default'} label={movement.source_label} />
                    </TableCell>
                    <TableCell>{movement.description}</TableCell>
                    <TableCell align="right">{formatCurrency(movement.amount)}</TableCell>
                  </TableRow>
                ))}
                {!movements.length && (
                  <TableRow>
                    <TableCell colSpan={5}>
                      <Typography color="text.secondary">No hay movimientos para mostrar.</Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
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
