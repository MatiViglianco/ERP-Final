import React, { useMemo, useState } from 'react'
import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputAdornment,
  InputLabel,
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
  Typography,
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import SearchIcon from '@mui/icons-material/Search'
import { API_BASE } from '../../config'
import {
  PAYMENT_SOURCES,
  currentIsoDate,
  formatCurrency,
  formatDate,
  formatMoney,
  normalizeText,
  parseAmount,
  statusColor,
  useClientPagination,
} from './format'

const API_BILLING_PAYMENTS = `${API_BASE}/billing/payments/`
const EMPTY_FORM = { source: 'cash', amount: '', date: currentIsoDate(), external_id: '' }

export default function PaymentsPanel({ payments, loading, authFetch, onDone, notify, busy, setBusy }) {
  const [search, setSearch] = useState('')
  const [source, setSource] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)

  const filtered = useMemo(() => {
    const term = normalizeText(search.trim())
    return payments.filter((payment) => {
      if (source && payment.source !== source) return false
      if (!term) return true
      return normalizeText([
        payment.external_id, payment.terminal?.code, payment.provider_status,
        payment.amount, formatMoney(payment.amount), payment.source_label,
      ].join(' ')).includes(term)
    })
  }, [payments, search, source])

  const totalsBySource = useMemo(() => {
    const totals = {}
    payments.forEach((payment) => {
      if (!['approved', 'reconciled'].includes(payment.status)) return
      totals[payment.source_label] = (totals[payment.source_label] || 0) + Number(payment.amount || 0)
    })
    return Object.entries(totals).sort((a, b) => b[1] - a[1])
  }, [payments])

  const { pageItems, paginationProps } = useClientPagination(filtered, `${search}|${source}`)
  const formAmount = parseAmount(form.amount)

  const submit = async () => {
    setBusy(true)
    try {
      const resp = await authFetch(API_BILLING_PAYMENTS, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, amount: formAmount }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo registrar el cobro')
      notify('success', `Cobro registrado: ${formatMoney(data.amount)} (${data.source_label})`)
      setForm(EMPTY_FORM)
      setFormOpen(false)
      await onDone()
    } catch (err) {
      notify('error', err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        {totalsBySource.map(([label, total]) => (
          <Chip key={label} variant="outlined" label={`${label}: ${formatCurrency(total)}`} />
        ))}
      </Stack>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ md: 'center' }}>
        <TextField
          size="small"
          placeholder="Buscar por referencia, terminal o importe"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          sx={{ flexGrow: 1, maxWidth: { md: 380 } }}
          inputProps={{ 'aria-label': 'Buscar cobros' }}
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
        />
        <FormControl size="small" sx={{ minWidth: 170 }}>
          <InputLabel id="payment-source-filter">Medio</InputLabel>
          <Select labelId="payment-source-filter" label="Medio" value={source} onChange={(event) => setSource(event.target.value)}>
            <MenuItem value="">Todos</MenuItem>
            {PAYMENT_SOURCES.map((item) => <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>)}
          </Select>
        </FormControl>
        <Box sx={{ flexGrow: 1 }} />
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setFormOpen(true)}>
          Registrar cobro
        </Button>
      </Stack>

      <TableContainer>
        <Table size="small" aria-label="Cobros del periodo">
          <TableHead>
            <TableRow>
              <TableCell>Fecha</TableCell>
              <TableCell>Medio</TableCell>
              <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>Terminal</TableCell>
              <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>Referencia</TableCell>
              <TableCell>Estado</TableCell>
              <TableCell align="right">Importe</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {pageItems.map((payment) => (
              <TableRow key={payment.id} hover>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDate(payment.date)}</TableCell>
                <TableCell>{payment.source_label}</TableCell>
                <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>{payment.terminal?.code || '-'}</TableCell>
                <TableCell sx={{ display: { xs: 'none', md: 'table-cell' }, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {payment.external_id || '-'}
                </TableCell>
                <TableCell>
                  <Stack spacing={0.5} alignItems="flex-start">
                    <Chip size="small" color={statusColor(payment.status)} label={payment.status_label} />
                    {payment.invoice_id && <Typography variant="caption" color="text.secondary">Facturado</Typography>}
                  </Stack>
                </TableCell>
                <TableCell align="right" sx={{ whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>{formatMoney(payment.amount)}</TableCell>
              </TableRow>
            ))}
            {!pageItems.length && (
              <TableRow>
                <TableCell colSpan={6}>
                  <Box sx={{ py: 4, textAlign: 'center' }}>
                    <Typography color="text.secondary">
                      {loading ? 'Cargando cobros...' : 'Sin cobros en el periodo con estos filtros.'}
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      <TablePagination {...paginationProps} />

      <Dialog open={formOpen} onClose={() => setFormOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Registrar cobro</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <FormControl fullWidth>
              <InputLabel id="payment-form-source">Medio</InputLabel>
              <Select
                labelId="payment-form-source"
                label="Medio"
                value={form.source}
                onChange={(event) => setForm((prev) => ({ ...prev, source: event.target.value }))}
              >
                {PAYMENT_SOURCES.map((item) => <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>)}
              </Select>
            </FormControl>
            <TextField
              label="Importe"
              value={form.amount}
              onChange={(event) => setForm((prev) => ({ ...prev, amount: event.target.value }))}
              error={form.amount !== '' && !(formAmount > 0)}
              helperText={form.amount !== '' && !(formAmount > 0) ? 'Importe invalido' : ' '}
              inputProps={{ inputMode: 'decimal' }}
              autoFocus
            />
            <TextField
              label="Fecha"
              type="date"
              value={form.date}
              onChange={(event) => setForm((prev) => ({ ...prev, date: event.target.value }))}
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label="Referencia (opcional)"
              value={form.external_id}
              onChange={(event) => setForm((prev) => ({ ...prev, external_id: event.target.value }))}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFormOpen(false)}>Cancelar</Button>
          <Button variant="contained" onClick={submit} disabled={busy || !(formAmount > 0)}>Registrar</Button>
        </DialogActions>
      </Dialog>
    </Stack>
  )
}
