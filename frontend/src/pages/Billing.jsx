import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Card,
  Chip,
  FormControl,
  IconButton,
  InputLabel,
  LinearProgress,
  MenuItem,
  Select,
  Snackbar,
  Stack,
  Tab,
  Tabs,
  Tooltip,
  Typography,
} from '@mui/material'
import RefreshIcon from '@mui/icons-material/Refresh'
import FactCheckIcon from '@mui/icons-material/FactCheck'
import { useAuth } from '../context/AuthContext.jsx'
import { API_BASE } from '../config'
import useBranches from '../hooks/useBranches.js'
import { MONTHS, arcaModeColor, arcaModeLabel, formatCurrency } from './billing/format'
import SummaryCards from './billing/SummaryCards.jsx'
import InvoicesPanel from './billing/InvoicesPanel.jsx'
import CouponsPanel from './billing/CouponsPanel.jsx'
import ManualInvoicesPanel from './billing/ManualInvoicesPanel.jsx'
import AccountInvoicePanel from './billing/AccountInvoicePanel.jsx'
import PaymentsPanel from './billing/PaymentsPanel.jsx'
import TerminalsPanel from './billing/TerminalsPanel.jsx'
import InvoiceDetailDrawer from './billing/InvoiceDetailDrawer.jsx'
import ArcaVerifyDialog from './billing/ArcaVerifyDialog.jsx'

const API_BILLING_SUMMARY = `${API_BASE}/billing/summary/`
const API_BILLING_INVOICES = `${API_BASE}/billing/invoices/`
const API_BILLING_PAYMENTS = `${API_BASE}/billing/payments/`
const API_GETNET_TERMINALS = `${API_BASE}/billing/getnet/terminals/`
const API_GETNET_INVOICEABLE = `${API_BASE}/billing/getnet/invoiceable/`
const API_ARCA_STATUS = `${API_BASE}/billing/arca/status/`

// Mientras la pagina esta abierta se vuelve a consultar ARCA para ver cuando vuelve.
const ARCA_STATUS_POLL_MS = 60000

const TABS = ['comprobantes', 'cupones', 'manuales', 'cuenta', 'cobros', 'terminales']
const TAB_STORAGE_KEY = 'billing.tab'

function readStoredTab() {
  try {
    const value = window.localStorage.getItem(TAB_STORAGE_KEY)
    return TABS.includes(value) ? value : 'comprobantes'
  } catch {
    return 'comprobantes'
  }
}

function storeTab(value) {
  try {
    window.localStorage.setItem(TAB_STORAGE_KEY, value)
  } catch {
    // Sin almacenamiento disponible: solo no se recuerda la pestana.
  }
}

async function fetchJson(authFetch, url, fallbackMessage) {
  const resp = await authFetch(url)
  const data = await resp.json()
  if (!resp.ok) throw new Error(data.detail || fallbackMessage)
  return data
}

function TabLabel({ label, count, color = 'primary', hint }) {
  return (
    <Stack direction="row" spacing={1} alignItems="center">
      <span>{label}</span>
      {count > 0 && (
        <Chip
          size="small"
          color={color}
          label={count > 999 ? '999+' : count}
          aria-label={hint ? `${count} ${hint}` : undefined}
          sx={{ height: 20, fontSize: 12, fontWeight: 700, '& .MuiChip-label': { px: 0.75 } }}
        />
      )}
    </Stack>
  )
}

export default function BillingPage() {
  const { authFetch } = useAuth()
  const { branches, branchesError } = useBranches(authFetch)
  const now = new Date()
  const [year, setYear] = useState(String(now.getFullYear()))
  const [month, setMonth] = useState(String(now.getMonth() + 1))
  const [terminalId, setTerminalId] = useState('')
  const [tab, setTab] = useState(readStoredTab)
  const [summary, setSummary] = useState(null)
  const [invoices, setInvoices] = useState([])
  const [payments, setPayments] = useState([])
  const [terminals, setTerminals] = useState([])
  const [candidates, setCandidates] = useState([])
  const [arcaStatus, setArcaStatus] = useState(null)
  const [branchId, setBranchId] = useState('')
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [toast, setToast] = useState(null)
  const [detailInvoiceId, setDetailInvoiceId] = useState(null)
  const [verifyOpen, setVerifyOpen] = useState(false)
  const pendingRetryRef = useRef(null)

  const queryString = useMemo(() => {
    const params = new URLSearchParams({ year, month })
    if (terminalId) params.set('terminal_id', terminalId)
    return params.toString()
  }, [year, month, terminalId])

  const periodLabel = `${year}-${String(month).padStart(2, '0')}`

  const notify = useCallback((severity, message) => {
    if (severity === 'error') {
      setError(message)
    } else {
      setError('')
      setToast({ severity, message })
    }
  }, [])

  const loadArcaStatus = useCallback(async () => {
    try {
      setArcaStatus(await fetchJson(authFetch, API_ARCA_STATUS, 'No se pudo consultar ARCA'))
    } catch (err) {
      setArcaStatus({ provider: 'wsfe', ready: false, error: err.message })
    }
  }, [authFetch])

  const loadAll = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [summaryData, invoicesData, paymentsData, candidatesData, terminalsData] = await Promise.all([
        fetchJson(authFetch, `${API_BILLING_SUMMARY}?${queryString}`, 'No se pudo cargar el resumen'),
        fetchJson(authFetch, `${API_BILLING_INVOICES}?${queryString}`, 'No se pudieron cargar los comprobantes'),
        fetchJson(authFetch, `${API_BILLING_PAYMENTS}?${queryString}`, 'No se pudieron cargar los cobros'),
        fetchJson(authFetch, `${API_GETNET_INVOICEABLE}?${queryString}`, 'No se pudieron cargar los cupones'),
        fetchJson(authFetch, API_GETNET_TERMINALS, 'No se pudieron cargar las terminales'),
      ])
      setSummary(summaryData)
      setInvoices(invoicesData || [])
      setPayments(paymentsData || [])
      setCandidates(candidatesData || [])
      setTerminals(terminalsData || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [authFetch, queryString])

  const refresh = useCallback(() => Promise.all([loadAll(), loadArcaStatus()]), [loadAll, loadArcaStatus])

  useEffect(() => {
    loadAll()
  }, [loadAll])

  useEffect(() => {
    loadArcaStatus()
    const timer = window.setInterval(loadArcaStatus, ARCA_STATUS_POLL_MS)
    return () => window.clearInterval(timer)
  }, [loadArcaStatus])

  // Cuando el reintento automatico emite facturas pendientes, se recargan los datos.
  const pendingRetryCount = arcaStatus?.pending_retry?.count
  useEffect(() => {
    if (pendingRetryCount === undefined) return
    const previous = pendingRetryRef.current
    pendingRetryRef.current = pendingRetryCount
    if (previous !== null && pendingRetryCount < previous) loadAll()
  }, [pendingRetryCount, loadAll])

  useEffect(() => {
    setBranchId((current) => {
      if (current && branches.some((branch) => String(branch.id) === current)) return current
      return branches.length === 1 ? String(branches[0].id) : ''
    })
  }, [branches])

  const changeTab = (_event, value) => {
    setTab(value)
    storeTab(value)
  }

  const failedInvoices = invoices.filter((invoice) => ['error', 'rejected'].includes(invoice.status)).length
  const panelProps = { authFetch, notify, busy, setBusy }

  return (
    <Stack spacing={3}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} justifyContent="space-between" alignItems={{ md: 'flex-end' }}>
        <Box>
          <Typography variant="h4" component="h1" fontWeight={800}>Facturacion</Typography>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 1 }} flexWrap="wrap" useFlexGap>
            <Chip size="small" color={arcaModeColor(arcaStatus)} label={arcaModeLabel(arcaStatus)} />
            {arcaStatus?.provider === 'wsfe' && arcaStatus?.ready && (
              <Typography variant="body2" color="text.secondary">
                Punto de venta {arcaStatus.point_of_sale} · ultimo comprobante B {arcaStatus.last_voucher_number}
              </Typography>
            )}
          </Stack>
        </Box>
        <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel id="billing-month">Mes</InputLabel>
            <Select labelId="billing-month" label="Mes" value={month} onChange={(event) => setMonth(event.target.value)}>
              {MONTHS.map((item) => <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>)}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 100 }}>
            <InputLabel id="billing-year">Anio</InputLabel>
            <Select labelId="billing-year" label="Anio" value={year} onChange={(event) => setYear(event.target.value)}>
              {[now.getFullYear() - 1, now.getFullYear(), now.getFullYear() + 1].map((item) => (
                <MenuItem key={item} value={String(item)}>{item}</MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 190 }}>
            <InputLabel id="billing-terminal">Terminal Getnet</InputLabel>
            <Select labelId="billing-terminal" label="Terminal Getnet" value={terminalId} onChange={(event) => setTerminalId(event.target.value)}>
              <MenuItem value="">Todas las terminales</MenuItem>
              {terminals.map((terminal) => (
                <MenuItem key={terminal.id} value={String(terminal.id)}>
                  {terminal.code} · {terminal.branch?.name || 'Sin sucursal'}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          {arcaStatus?.provider === 'wsfe' && (
            <Tooltip title="Verificar con ARCA los comprobantes del mes">
              <span>
                <IconButton onClick={() => setVerifyOpen(true)} aria-label="Verificar comprobantes del mes con ARCA">
                  <FactCheckIcon />
                </IconButton>
              </span>
            </Tooltip>
          )}
          <Tooltip title="Actualizar">
            <span>
              <IconButton onClick={refresh} disabled={loading} aria-label="Actualizar datos de facturacion">
                <RefreshIcon />
              </IconButton>
            </span>
          </Tooltip>
        </Stack>
      </Stack>

      {arcaStatus?.provider === 'wsfe' && !arcaStatus?.ready && (
        <Alert severity="error">
          No hay conexion con ARCA: {arcaStatus.error || 'revisa la configuracion'}. La emision esta pausada.
          {pendingRetryCount > 0 && arcaStatus.auto_retry_seconds > 0 && (
            <> {pendingRetryCount} factura(s) por {formatCurrency(arcaStatus.pending_retry.total)} quedaron en espera y
              se emiten solas cuando ARCA vuelva.</>
          )}
        </Alert>
      )}
      {arcaStatus?.provider === 'wsfe' && arcaStatus?.ready && pendingRetryCount > 0 && (
        <Alert severity="info">
          ARCA volvio: {pendingRetryCount} factura(s) por {formatCurrency(arcaStatus.pending_retry.total)} se estan
          reintentando automaticamente.
        </Alert>
      )}
      {error && <Alert severity="error" onClose={() => setError('')}>{error}</Alert>}
      {branchesError && <Alert severity="warning">{branchesError}</Alert>}

      <SummaryCards summary={summary} pendingCoupons={candidates} loading={loading && !summary} />

      <Card variant="outlined">
        <Box sx={{ borderBottom: 1, borderColor: 'divider', px: { xs: 1, md: 2 } }}>
          <Tabs
            value={tab}
            onChange={changeTab}
            variant="scrollable"
            scrollButtons="auto"
            aria-label="Secciones de facturacion"
            sx={{ '& .MuiTab-root': { textTransform: 'none', fontWeight: 600, fontSize: 15, minHeight: 56 } }}
          >
            <Tab value="comprobantes" label={<TabLabel label="Comprobantes" count={failedInvoices} color="error" hint="con error" />} />
            <Tab value="cupones" label={<TabLabel label="Cupones posnet" count={candidates.length} color="warning" hint="sin facturar" />} />
            <Tab value="manuales" label="Facturas manuales" />
            <Tab value="cuenta" label="Cuenta corriente" />
            <Tab value="cobros" label="Cobros" />
            <Tab value="terminales" label="Terminales" />
          </Tabs>
        </Box>
        {(loading || busy) && <LinearProgress />}
        <Box sx={{ p: { xs: 2, md: 3 } }}>
          {tab === 'comprobantes' && (
            <InvoicesPanel invoices={invoices} loading={loading} periodLabel={periodLabel} onOpenInvoice={setDetailInvoiceId} />
          )}
          {tab === 'cupones' && (
            <CouponsPanel candidates={candidates} arcaStatus={arcaStatus} onDone={refresh} {...panelProps} />
          )}
          {tab === 'manuales' && (
            <ManualInvoicesPanel
              arcaStatus={arcaStatus}
              branchId={branchId}
              monthInvoiced={summary?.invoices?.authorized_total}
              onDone={refresh}
              {...panelProps}
            />
          )}
          {tab === 'cuenta' && (
            <AccountInvoicePanel
              branches={branches}
              branchId={branchId}
              onBranchChange={setBranchId}
              totalDebt={summary?.account_current?.total_debt}
              onDone={refresh}
              {...panelProps}
            />
          )}
          {tab === 'cobros' && (
            <PaymentsPanel payments={payments} loading={loading} onDone={refresh} {...panelProps} />
          )}
          {tab === 'terminales' && (
            <TerminalsPanel terminals={terminals} branches={branches} onDone={refresh} {...panelProps} />
          )}
        </Box>
      </Card>

      <InvoiceDetailDrawer
        invoiceId={detailInvoiceId}
        onClose={() => setDetailInvoiceId(null)}
        authFetch={authFetch}
        arcaStatus={arcaStatus}
        onChanged={refresh}
        notify={notify}
      />

      <ArcaVerifyDialog
        open={verifyOpen}
        onClose={() => setVerifyOpen(false)}
        authFetch={authFetch}
        year={year}
        month={month}
        periodLabel={periodLabel}
      />

      <Snackbar
        open={Boolean(toast)}
        autoHideDuration={6000}
        onClose={() => setToast(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        {toast ? (
          <Alert severity={toast.severity} variant="filled" onClose={() => setToast(null)} sx={{ width: '100%' }}>
            {toast.message}
          </Alert>
        ) : <span />}
      </Snackbar>
    </Stack>
  )
}
