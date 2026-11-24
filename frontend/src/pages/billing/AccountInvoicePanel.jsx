import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Autocomplete,
  Box,
  Button,
  Checkbox,
  Chip,
  FormControl,
  InputLabel,
  LinearProgress,
  MenuItem,
  Paper,
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
import { API_BASE } from '../../config'
import { formatCurrency, formatDate, formatVoucher, statusColor } from './format'

const API_ACCOUNTS = `${API_BASE}/accounts/clients/`
const API_ACCOUNT_PREVIEW = (id) => `${API_BASE}/billing/accounts/${id}/preview/`
const API_ACCOUNT_INVOICE = (id) => `${API_BASE}/billing/accounts/${id}/invoices/`

export default function AccountInvoicePanel({
  authFetch, branches, branchId, onBranchChange, totalDebt, onDone, notify, busy, setBusy,
}) {
  const [clients, setClients] = useState([])
  const [client, setClient] = useState(null)
  const [preview, setPreview] = useState(null)
  const [selectedTx, setSelectedTx] = useState(new Set())
  const [loading, setLoading] = useState(false)
  const [lastInvoice, setLastInvoice] = useState(null)
  const needsBranch = branches.length > 1 && !branchId

  const loadClients = useCallback(async () => {
    if (needsBranch) {
      setClients([])
      return
    }
    setLoading(true)
    try {
      const params = new URLSearchParams({ limit: '100', ordering: 'debt' })
      if (branchId) params.set('branch_id', branchId)
      const resp = await authFetch(`${API_ACCOUNTS}?${params.toString()}`)
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudieron cargar clientes')
      setClients(data.results || [])
    } catch (err) {
      notify('error', err.message)
    } finally {
      setLoading(false)
    }
  }, [authFetch, branchId, needsBranch, notify])

  const loadPreview = useCallback(async (selectedClient) => {
    setPreview(null)
    setSelectedTx(new Set())
    if (!selectedClient || needsBranch) return
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (branchId) params.set('branch_id', branchId)
      const query = params.toString()
      const resp = await authFetch(`${API_ACCOUNT_PREVIEW(selectedClient.id)}${query ? `?${query}` : ''}`)
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo cargar la deuda')
      setPreview(data)
      setSelectedTx(new Set((data.transactions || []).map((tx) => tx.id)))
    } catch (err) {
      notify('error', err.message)
    } finally {
      setLoading(false)
    }
  }, [authFetch, branchId, needsBranch, notify])

  useEffect(() => {
    loadClients()
  }, [loadClients])

  useEffect(() => {
    loadPreview(client)
  }, [client, loadPreview])

  const selectedTotal = useMemo(() => (preview?.transactions || [])
    .filter((tx) => selectedTx.has(tx.id))
    .reduce((acc, tx) => acc + Number(tx.remaining || 0), 0), [preview, selectedTx])

  const toggleTx = (txId) => setSelectedTx((prev) => {
    const next = new Set(prev)
    if (next.has(txId)) next.delete(txId)
    else next.add(txId)
    return next
  })

  const changeBranch = (value) => {
    onBranchChange(value)
    setClient(null)
    setPreview(null)
    setSelectedTx(new Set())
  }

  const createInvoice = async () => {
    if (!client || selectedTx.size === 0 || (branches.length > 0 && !branchId)) return
    setBusy(true)
    try {
      const resp = await authFetch(API_ACCOUNT_INVOICE(client.id), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transaction_ids: Array.from(selectedTx), authorize: true, branch_id: branchId || null }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo crear la factura')
      setLastInvoice(data)
      notify('success', `Factura creada por ${formatCurrency(data.total_amount)}. Estado: ${data.status_label}`)
      await Promise.all([onDone(), loadPreview(client)])
    } catch (err) {
      notify('error', err.message)
    } finally {
      setBusy(false)
    }
  }

  const allSelected = preview?.transactions?.length > 0 && selectedTx.size === preview.transactions.length

  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} justifyContent="space-between" alignItems={{ md: 'center' }}>
        <Typography variant="body2" color="text.secondary">
          Elegi un cliente, revisa sus movimientos pendientes y genera la factura.
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Deuda total de clientes: <strong>{formatCurrency(totalDebt)}</strong>
        </Typography>
      </Stack>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
        <FormControl sx={{ minWidth: 240 }}>
          <InputLabel id="invoice-branch-select">Sucursal a facturar</InputLabel>
          <Select
            labelId="invoice-branch-select"
            label="Sucursal a facturar"
            value={branchId}
            onChange={(event) => changeBranch(event.target.value)}
          >
            <MenuItem value="" disabled>Seleccionar sucursal</MenuItem>
            {branches.map((branch) => <MenuItem key={branch.id} value={String(branch.id)}>{branch.name}</MenuItem>)}
          </Select>
        </FormControl>
        <Autocomplete
          sx={{ flexGrow: 1 }}
          loading={loading}
          disabled={needsBranch}
          options={clients}
          value={client}
          onChange={(_event, value) => setClient(value)}
          getOptionLabel={(option) => `${option.full_name || option.name || option.external_id} - ${formatCurrency(branchId ? option.branch_total_debt : option.total_debt)}`}
          renderInput={(params) => <TextField {...params} label="Cliente" />}
        />
      </Stack>
      {loading && <LinearProgress />}

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
              disabled={busy || selectedTx.size === 0 || (branches.length > 0 && !branchId)}
              onClick={createInvoice}
            >
              Facturar {formatCurrency(selectedTotal)}
            </Button>
          </Stack>
          <Table size="small" aria-label="Movimientos pendientes de facturar">
            <TableHead>
              <TableRow>
                <TableCell padding="checkbox">
                  <Checkbox
                    inputProps={{ 'aria-label': 'Seleccionar todos los movimientos' }}
                    checked={Boolean(allSelected)}
                    indeterminate={selectedTx.size > 0 && !allSelected}
                    onChange={() => setSelectedTx(allSelected ? new Set() : new Set(preview.transactions.map((tx) => tx.id)))}
                    disabled={!preview.transactions?.length}
                  />
                </TableCell>
                <TableCell>Fecha</TableCell>
                <TableCell>Detalle</TableCell>
                <TableCell align="right">Pendiente</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(preview.transactions || []).map((tx) => (
                <TableRow key={tx.id} hover selected={selectedTx.has(tx.id)} onClick={() => toggleTx(tx.id)} sx={{ cursor: 'pointer' }}>
                  <TableCell padding="checkbox">
                    <Checkbox
                      checked={selectedTx.has(tx.id)}
                      onClick={(event) => event.stopPropagation()}
                      onChange={() => toggleTx(tx.id)}
                      inputProps={{ 'aria-label': `Seleccionar movimiento ${tx.description || tx.id}` }}
                    />
                  </TableCell>
                  <TableCell>{formatDate(tx.date)}</TableCell>
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

      {lastInvoice && (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="subtitle2" fontWeight={700} gutterBottom>Ultimo comprobante emitido</Typography>
          <Table size="small" aria-label="Ultimo comprobante emitido">
            <TableBody>
              <TableRow>
                <TableCell>{formatVoucher(lastInvoice)}</TableCell>
                <TableCell>{lastInvoice.client_name || '-'}</TableCell>
                <TableCell>{lastInvoice.branch?.name || '-'}</TableCell>
                <TableCell><Chip size="small" color={statusColor(lastInvoice.status)} label={lastInvoice.status_label} /></TableCell>
                <TableCell align="right">{formatCurrency(lastInvoice.total_amount)}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Paper>
      )}
    </Stack>
  )
}
