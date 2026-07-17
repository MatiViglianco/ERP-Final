import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
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
import ReceiptLongIcon from '@mui/icons-material/ReceiptLong'
import PaymentsIcon from '@mui/icons-material/Payments'
import AccountBalanceIcon from '@mui/icons-material/AccountBalance'
import SyncAltIcon from '@mui/icons-material/SyncAlt'
import { useAuth } from '../context/AuthContext.jsx'
import { API_BASE } from '../config'
import useBranches from '../hooks/useBranches.js'

const API_BILLING_SUMMARY = `${API_BASE}/billing/summary/`
const API_BILLING_INVOICES = `${API_BASE}/billing/invoices/`
const API_BILLING_PAYMENTS = `${API_BASE}/billing/payments/`
const API_GETNET_TERMINALS = `${API_BASE}/billing/getnet/terminals/`
const API_GETNET_TERMINAL = (id) => `${API_GETNET_TERMINALS}${id}/`
const API_ACCOUNTS = `${API_BASE}/accounts/clients/`
const API_ACCOUNT_PREVIEW = (id) => `${API_BASE}/billing/accounts/${id}/preview/`
const API_ACCOUNT_INVOICE = (id) => `${API_BASE}/billing/accounts/${id}/invoices/`

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

const PAYMENT_SOURCES = [
  { value: 'getnet', label: 'Getnet' },
  { value: 'santander', label: 'Santander' },
  { value: 'bancon', label: 'Bancor' },
  { value: 'transfer', label: 'Transferencia' },
  { value: 'cash', label: 'Efectivo' },
  { value: 'manual', label: 'Manual' },
]

function formatCurrency(value) {
  return `$ ${Number(value || 0).toLocaleString('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

function currentIsoDate() {
  return new Date().toISOString().split('T')[0]
}

function statusColor(status) {
  if (status === 'authorized' || status === 'approved' || status === 'reconciled') return 'success'
  if (status === 'draft' || status === 'pending') return 'warning'
  if (status === 'needs_review') return 'info'
  return 'error'
}

function SummaryCard({ icon, label, value, detail }) {
  return (
    <Card sx={{ height: '100%', border: '1px solid rgba(255,255,255,0.08)' }}>
      <CardContent>
        <Stack direction="row" spacing={1.5} alignItems="center">
          {icon}
          <Box>
            <Typography variant="body2" color="text.secondary">{label}</Typography>
            <Typography variant="h5" fontWeight={700}>{formatCurrency(value)}</Typography>
            {detail ? <Typography variant="caption" color="text.secondary">{detail}</Typography> : null}
          </Box>
        </Stack>
      </CardContent>
    </Card>
  )
}

export default function BillingPage() {
  const { authFetch } = useAuth()
  const { branches, branchesError } = useBranches(authFetch)
  const now = new Date()
  const [year, setYear] = useState(String(now.getFullYear()))
  const [month, setMonth] = useState(String(now.getMonth() + 1))
  const [summary, setSummary] = useState(null)
  const [invoices, setInvoices] = useState([])
  const [payments, setPayments] = useState([])
  const [terminals, setTerminals] = useState([])
  const [selectedTerminalId, setSelectedTerminalId] = useState('')
  const [invoiceBranchId, setInvoiceBranchId] = useState('')
  const [clients, setClients] = useState([])
  const [selectedClient, setSelectedClient] = useState(null)
  const [preview, setPreview] = useState(null)
  const [selectedTx, setSelectedTx] = useState(new Set())
  const [loading, setLoading] = useState(false)
  const [clientLoading, setClientLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [paymentForm, setPaymentForm] = useState({
    source: 'getnet',
    amount: '',
    date: currentIsoDate(),
    external_id: '',
  })

  const queryString = useMemo(() => {
    const params = new URLSearchParams({ year, month })
    if (selectedTerminalId) params.set('terminal_id', selectedTerminalId)
    return params.toString()
  }, [year, month, selectedTerminalId])

  const selectedTotal = useMemo(() => {
    const txs = preview?.transactions || []
    return txs
      .filter((tx) => selectedTx.has(tx.id))
      .reduce((acc, tx) => acc + Number(tx.remaining || 0), 0)
  }, [preview, selectedTx])

  const totalCollected = useMemo(() => {
    const collections = summary?.collections || {}
    return Object.values(collections).reduce((acc, value) => acc + Number(value || 0), 0)
  }, [summary])

  const loadBilling = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [summaryResp, invoicesResp, paymentsResp] = await Promise.all([
        authFetch(`${API_BILLING_SUMMARY}?${queryString}`),
        authFetch(`${API_BILLING_INVOICES}?${queryString}`),
        authFetch(`${API_BILLING_PAYMENTS}?${queryString}`),
      ])
      const [summaryData, invoicesData, paymentsData] = await Promise.all([
        summaryResp.json(),
        invoicesResp.json(),
        paymentsResp.json(),
      ])
      if (!summaryResp.ok) throw new Error(summaryData.detail || 'No se pudo cargar el resumen')
      if (!invoicesResp.ok) throw new Error(invoicesData.detail || 'No se pudieron cargar las facturas')
      if (!paymentsResp.ok) throw new Error(paymentsData.detail || 'No se pudieron cargar los pagos')
      setSummary(summaryData)
      setInvoices(invoicesData || [])
      setPayments(paymentsData || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [authFetch, queryString])

  const loadClients = useCallback(async () => {
    if (branches.length > 1 && !invoiceBranchId) {
      setClients([])
      setClientLoading(false)
      return
    }
    setClientLoading(true)
    try {
      const params = new URLSearchParams({ limit: '100', ordering: 'debt' })
      if (invoiceBranchId) params.set('branch_id', invoiceBranchId)
      const resp = await authFetch(`${API_ACCOUNTS}?${params.toString()}`)
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudieron cargar clientes')
      setClients(data.results || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setClientLoading(false)
    }
  }, [authFetch, branches.length, invoiceBranchId])

  const loadTerminals = useCallback(async () => {
    try {
      const resp = await authFetch(API_GETNET_TERMINALS)
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudieron cargar las terminales Getnet')
      setTerminals(data || [])
    } catch (err) {
      setError(err.message)
    }
  }, [authFetch])

  const loadPreview = useCallback(async (client) => {
    setPreview(null)
    setSelectedTx(new Set())
    if (!client || (branches.length > 1 && !invoiceBranchId)) return
    setClientLoading(true)
    try {
      const params = new URLSearchParams()
      if (invoiceBranchId) params.set('branch_id', invoiceBranchId)
      const query = params.toString()
      const resp = await authFetch(`${API_ACCOUNT_PREVIEW(client.id)}${query ? `?${query}` : ''}`)
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo cargar la deuda')
      setPreview(data)
      setSelectedTx(new Set((data.transactions || []).map((tx) => tx.id)))
    } catch (err) {
      setError(err.message)
    } finally {
      setClientLoading(false)
    }
  }, [authFetch, branches.length, invoiceBranchId])

  useEffect(() => {
    setInvoiceBranchId((current) => {
      if (current && branches.some((branch) => String(branch.id) === current)) return current
      return branches.length === 1 ? String(branches[0].id) : ''
    })
  }, [branches])

  useEffect(() => {
    loadBilling()
  }, [loadBilling])

  useEffect(() => {
    loadClients()
  }, [loadClients])

  useEffect(() => {
    loadTerminals()
  }, [loadTerminals])

  useEffect(() => {
    loadPreview(selectedClient)
  }, [selectedClient, loadPreview])

  const changeInvoiceBranch = (branchId) => {
    setInvoiceBranchId(branchId)
    setSelectedClient(null)
    setPreview(null)
    setSelectedTx(new Set())
  }

  const toggleTx = (txId) => {
    setSelectedTx((prev) => {
      const next = new Set(prev)
      if (next.has(txId)) next.delete(txId)
      else next.add(txId)
      return next
    })
  }

  const updateTerminalBranch = async (terminalId, branchId) => {
    setActionLoading(true)
    setError('')
    setSuccess('')
    try {
      const resp = await authFetch(API_GETNET_TERMINAL(terminalId), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ branch_id: branchId || null }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo asignar la sucursal')
      setSuccess(`Terminal ${data.code} asignada a ${data.branch?.name || 'sin sucursal'}`)
      await Promise.all([loadTerminals(), loadBilling()])
    } catch (err) {
      setError(err.message)
    } finally {
      setActionLoading(false)
    }
  }

  const createInvoice = async () => {
    if (!selectedClient || selectedTx.size === 0 || (branches.length > 0 && !invoiceBranchId)) return
    setActionLoading(true)
    setError('')
    setSuccess('')
    try {
      const resp = await authFetch(API_ACCOUNT_INVOICE(selectedClient.id), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          transaction_ids: Array.from(selectedTx),
          authorize: true,
          branch_id: invoiceBranchId || null,
        }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo crear la factura')
      setSuccess(`Factura creada por ${formatCurrency(data.total_amount)}. Estado: ${data.status_label}`)
      await Promise.all([loadBilling(), loadPreview(selectedClient)])
    } catch (err) {
      setError(err.message)
    } finally {
      setActionLoading(false)
    }
  }

  const createPayment = async () => {
    setActionLoading(true)
    setError('')
    setSuccess('')
    try {
      const resp = await authFetch(API_BILLING_PAYMENTS, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(paymentForm),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo registrar el cobro')
      setSuccess(`Cobro registrado: ${formatCurrency(data.amount)} (${data.source_label})`)
      setPaymentForm((prev) => ({ ...prev, amount: '', external_id: '' }))
      await loadBilling()
    } catch (err) {
      setError(err.message)
    } finally {
      setActionLoading(false)
    }
  }

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h4" fontWeight={800}>Facturacion</Typography>
        <Typography color="text.secondary">
          Control de facturas ARCA, cobros Getnet, bancos y cuenta corriente.
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
        <FormControl sx={{ minWidth: 230 }}>
          <InputLabel>Terminal Getnet</InputLabel>
          <Select
            label="Terminal Getnet"
            value={selectedTerminalId}
            onChange={(event) => setSelectedTerminalId(event.target.value)}
          >
            <MenuItem value="">Todas las terminales</MenuItem>
            {terminals.map((terminal) => (
              <MenuItem key={terminal.id} value={String(terminal.id)}>
                {terminal.code} · {terminal.branch?.name || 'Sin sucursal'}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <Button variant="outlined" startIcon={<SyncAltIcon />} onClick={loadBilling} disabled={loading}>
          Actualizar
        </Button>
      </Stack>

      {loading && <LinearProgress />}
      {error && <Alert severity="error">{error}</Alert>}
      {branchesError && <Alert severity="warning">{branchesError}</Alert>}
      {success && <Alert severity="success">{success}</Alert>}

      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(4, minmax(0, 1fr))' }, gap: 2 }}>
        <Box>
          <SummaryCard
            icon={<ReceiptLongIcon color="primary" />}
            label="Facturado ARCA"
            value={summary?.invoices?.authorized_total}
            detail={`${summary?.invoices?.authorized_count || 0} comprobantes autorizados`}
          />
        </Box>
        <Box>
          <SummaryCard
            icon={<PaymentsIcon color="success" />}
            label="Cobrado total"
            value={totalCollected}
            detail={selectedTerminalId
              ? `Getnet ${formatCurrency(summary?.collections?.getnet || 0)} · Pendiente ${formatCurrency(summary?.getnet?.pending_total || 0)}`
              : `Getnet ${formatCurrency(summary?.collections?.getnet || 0)} · Acreditado en banco ${formatCurrency(summary?.getnet?.bank_settled_total || 0)}`}
          />
        </Box>
        <Box>
          <SummaryCard
            icon={<AccountBalanceIcon color="info" />}
            label="Bancos"
            value={(summary?.collections?.santander || 0) + (summary?.collections?.bancon || 0)}
            detail={`Santander ${formatCurrency(summary?.collections?.santander || 0)} / Bancor ${formatCurrency(summary?.collections?.bancon || 0)}`}
          />
        </Box>
        <Box>
          <SummaryCard
            icon={<ReceiptLongIcon color="warning" />}
            label="Deuda cuenta corriente"
            value={summary?.account_current?.total_debt}
            detail="Saldo pendiente de clientes"
          />
        </Box>
      </Box>

      <Card>
        <CardContent>
          <Stack spacing={2}>
            <Box>
              <Typography variant="h6" fontWeight={700}>Terminales Getnet</Typography>
              <Typography variant="body2" color="text.secondary">
                Cada codigo POS se vincula a una sucursal y conserva esa asignacion en futuras importaciones.
              </Typography>
            </Box>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Terminal</TableCell>
                  <TableCell>Establecimiento</TableCell>
                  <TableCell>Sucursal</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {terminals.map((terminal) => (
                  <TableRow key={terminal.id}>
                    <TableCell>{terminal.code}</TableCell>
                    <TableCell>{terminal.establishment_name || terminal.establishment_number || '-'}</TableCell>
                    <TableCell sx={{ minWidth: 220 }}>
                      <FormControl fullWidth size="small">
                        <Select
                          aria-label={`Sucursal terminal ${terminal.code}`}
                          value={terminal.branch?.id && branches.some((branch) => branch.id === terminal.branch.id)
                            ? String(terminal.branch.id)
                            : ''}
                          disabled={actionLoading}
                          onChange={(event) => updateTerminalBranch(terminal.id, event.target.value)}
                        >
                          <MenuItem value="">Sin sucursal</MenuItem>
                          {branches.map((branch) => (
                            <MenuItem key={branch.id} value={String(branch.id)}>{branch.name}</MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    </TableCell>
                  </TableRow>
                ))}
                {!terminals.length && (
                  <TableRow>
                    <TableCell colSpan={3}>
                      <Typography color="text.secondary">Todavia no se importaron terminales Getnet.</Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Stack spacing={2}>
            <Box>
              <Typography variant="h6" fontWeight={700}>Facturar cuenta corriente</Typography>
              <Typography variant="body2" color="text.secondary">
                Selecciona un cliente, revisa sus movimientos pendientes y genera la factura.
              </Typography>
            </Box>
            <FormControl fullWidth>
              <InputLabel id="invoice-branch-select">Sucursal a facturar</InputLabel>
              <Select
                labelId="invoice-branch-select"
                label="Sucursal a facturar"
                value={invoiceBranchId}
                onChange={(event) => changeInvoiceBranch(event.target.value)}
              >
                <MenuItem value="" disabled>Seleccionar sucursal</MenuItem>
                {branches.map((branch) => (
                  <MenuItem key={branch.id} value={String(branch.id)}>{branch.name}</MenuItem>
                ))}
              </Select>
            </FormControl>
            <Autocomplete
              loading={clientLoading}
              disabled={branches.length > 1 && !invoiceBranchId}
              options={clients}
              value={selectedClient}
              onChange={(_event, value) => setSelectedClient(value)}
              getOptionLabel={(option) => `${option.full_name || option.name || option.external_id} - ${formatCurrency(invoiceBranchId ? option.branch_total_debt : option.total_debt)}`}
              renderInput={(params) => <TextField {...params} label="Cliente" />}
            />
            {clientLoading && <LinearProgress />}
            {preview && (
              <Stack spacing={2}>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ md: 'center' }} justifyContent="space-between">
                  <Box>
                    <Typography fontWeight={700}>{preview.client.name}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {preview.branch?.name ? `${preview.branch.name} - ` : ''}Pendiente para facturar: {formatCurrency(preview.total_pending_to_invoice)}
                    </Typography>
                  </Box>
                  <Button
                    variant="contained"
                    startIcon={<ReceiptLongIcon />}
                    disabled={actionLoading || selectedTx.size === 0 || (branches.length > 0 && !invoiceBranchId)}
                    onClick={createInvoice}
                  >
                    Facturar {formatCurrency(selectedTotal)}
                  </Button>
                </Stack>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell padding="checkbox" />
                      <TableCell>Fecha</TableCell>
                      <TableCell>Detalle</TableCell>
                      <TableCell align="right">Pendiente</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(preview.transactions || []).map((tx) => (
                      <TableRow key={tx.id} hover>
                        <TableCell padding="checkbox">
                          <Checkbox checked={selectedTx.has(tx.id)} onChange={() => toggleTx(tx.id)} />
                        </TableCell>
                        <TableCell>{tx.date || '-'}</TableCell>
                        <TableCell>{tx.description || tx.id}</TableCell>
                        <TableCell align="right">{formatCurrency(tx.remaining)}</TableCell>
                      </TableRow>
                    ))}
                    {(!preview.transactions || preview.transactions.length === 0) && (
                      <TableRow>
                        <TableCell colSpan={4}>
                          <Typography color="text.secondary">No hay movimientos pendientes para facturar.</Typography>
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </Stack>
            )}
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="h6" fontWeight={700}>Registrar cobro</Typography>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <FormControl sx={{ minWidth: 170 }}>
                <InputLabel>Medio</InputLabel>
                <Select
                  label="Medio"
                  value={paymentForm.source}
                  onChange={(event) => setPaymentForm((prev) => ({ ...prev, source: event.target.value }))}
                >
                  {PAYMENT_SOURCES.map((item) => (
                    <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>
                  ))}
                </Select>
              </FormControl>
              <TextField
                label="Importe"
                value={paymentForm.amount}
                onChange={(event) => setPaymentForm((prev) => ({ ...prev, amount: event.target.value }))}
              />
              <TextField
                label="Fecha"
                type="date"
                value={paymentForm.date}
                onChange={(event) => setPaymentForm((prev) => ({ ...prev, date: event.target.value }))}
                InputLabelProps={{ shrink: true }}
              />
              <TextField
                label="Referencia"
                value={paymentForm.external_id}
                onChange={(event) => setPaymentForm((prev) => ({ ...prev, external_id: event.target.value }))}
              />
              <Button variant="outlined" onClick={createPayment} disabled={actionLoading || !paymentForm.amount}>
                Registrar
              </Button>
            </Stack>
          </Stack>
        </CardContent>
      </Card>

      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'minmax(0, 7fr) minmax(0, 5fr)' }, gap: 2 }}>
        <Box>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={700}>Facturas del mes</Typography>
              <Divider sx={{ my: 2 }} />
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Fecha</TableCell>
                    <TableCell>Cliente</TableCell>
                    <TableCell>Sucursal</TableCell>
                    <TableCell>Estado</TableCell>
                    <TableCell align="right">Total</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {invoices.map((invoice) => (
                    <TableRow key={invoice.id}>
                      <TableCell>{invoice.issue_date}</TableCell>
                      <TableCell>{invoice.client_name || '-'}</TableCell>
                      <TableCell>{invoice.branch?.name || '-'}</TableCell>
                      <TableCell>
                        <Chip size="small" color={statusColor(invoice.status)} label={invoice.status_label} />
                      </TableCell>
                      <TableCell align="right">{formatCurrency(invoice.total_amount)}</TableCell>
                    </TableRow>
                  ))}
                  {!invoices.length && (
                    <TableRow>
                      <TableCell colSpan={5}>
                        <Typography color="text.secondary">Sin facturas en el periodo.</Typography>
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </Box>
        <Box>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={700}>Cobros registrados</Typography>
              <Divider sx={{ my: 2 }} />
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Fecha</TableCell>
                    <TableCell>Medio</TableCell>
                    <TableCell>Terminal</TableCell>
                    <TableCell>Estado</TableCell>
                    <TableCell align="right">Importe</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {payments.map((payment) => (
                    <TableRow key={payment.id}>
                      <TableCell>{payment.date}</TableCell>
                      <TableCell>{payment.source_label}</TableCell>
                      <TableCell>{payment.terminal?.code || '-'}</TableCell>
                      <TableCell>
                        <Stack spacing={0.5} alignItems="flex-start">
                          <Chip size="small" color={statusColor(payment.status)} label={payment.status_label} />
                          {payment.provider_status && (
                            <Typography variant="caption" color="text.secondary">Getnet: {payment.provider_status}</Typography>
                          )}
                        </Stack>
                      </TableCell>
                      <TableCell align="right">{formatCurrency(payment.amount)}</TableCell>
                    </TableRow>
                  ))}
                  {!payments.length && (
                    <TableRow>
                      <TableCell colSpan={5}>
                        <Typography color="text.secondary">Sin cobros registrados en el periodo.</Typography>
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </Box>
      </Box>
    </Stack>
  )
}
