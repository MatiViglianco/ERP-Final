import React, { useMemo, useState } from 'react'
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControl,
  IconButton,
  InputLabel,
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
  Tooltip,
  Typography,
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import CallSplitIcon from '@mui/icons-material/CallSplit'
import ReceiptLongIcon from '@mui/icons-material/ReceiptLong'
import { API_BASE } from '../../config'
import {
  VAT_RATES,
  failureMessage,
  formatCurrency,
  formatMoney,
  isRealVoucher,
  parseAmount,
  splitAmount,
} from './format'

const API_MANUAL_INVOICES = `${API_BASE}/billing/manual-invoices/`
const EMPTY_ROW = { amount: '', description: '' }
const MAX_ROWS = 100

export default function ManualInvoicesPanel({ arcaStatus, authFetch, branchId, monthInvoiced, onDone, notify, busy, setBusy }) {
  const [rows, setRows] = useState([{ ...EMPTY_ROW }])
  const [vatRate, setVatRate] = useState('10.5')
  const [splitTotal, setSplitTotal] = useState('')
  const [splitCount, setSplitCount] = useState('10')
  const [splitError, setSplitError] = useState('')
  const [confirmOpen, setConfirmOpen] = useState(false)

  const amounts = useMemo(() => rows.map((row) => parseAmount(row.amount)), [rows])
  const filledCount = rows.filter((row) => String(row.amount || '').trim() !== '').length
  const invalid = rows.some((row, index) => String(row.amount || '').trim() !== '' && !(amounts[index] > 0))
  const total = amounts.reduce((acc, value) => acc + (value > 0 ? value : 0), 0)
  const rate = Number(vatRate)
  const net = total / (1 + rate / 100)
  const arcaBlocked = arcaStatus?.provider === 'wsfe' && !arcaStatus?.ready

  const updateRow = (index, field, value) => {
    setRows((prev) => prev.map((row, rowIndex) => (rowIndex === index ? { ...row, [field]: value } : row)))
  }

  const removeRow = (index) => {
    setRows((prev) => (prev.length === 1 ? [{ ...EMPTY_ROW }] : prev.filter((_, rowIndex) => rowIndex !== index)))
  }

  const applySplit = () => {
    const amount = parseAmount(splitTotal)
    const count = Number.parseInt(splitCount, 10)
    if (!(amount > 0)) {
      setSplitError('Carga un total mayor a cero')
      return
    }
    if (!(count >= 1 && count <= MAX_ROWS)) {
      setSplitError(`La cantidad debe estar entre 1 y ${MAX_ROWS}`)
      return
    }
    setSplitError('')
    setRows(splitAmount(amount, count).map((value) => ({ amount: value.toFixed(2).replace('.', ','), description: '' })))
  }

  const issue = async () => {
    setConfirmOpen(false)
    const items = rows
      .map((row, index) => ({ amount: amounts[index], description: row.description }))
      .filter((item) => item.amount > 0)
    if (!items.length) return
    setBusy(true)
    try {
      const resp = await authFetch(API_MANUAL_INVOICES, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items, vat_rate: vatRate, branch_id: branchId || null }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudieron emitir las facturas manuales')
      const failed = (data.results || []).filter((item) => !item.ok)
      if (failed.length) {
        notify('error', failureMessage(
          `${data.authorized ? `${data.authorized} autorizada(s). ` : ''}`
            + `${failed.length} factura(s) no se pudieron emitir y quedaron cargadas para reintentar:`,
          failed.map((item) => `Fila ${item.row} (${formatMoney(item.amount)}): ${item.detail}`),
        ))
      } else if (data.authorized) {
        notify('success', `${data.authorized} factura(s) manual(es) autorizada(s) por ${formatMoney(data.authorized_total)}`)
      }
      setRows(failed.length
        ? failed.map((item) => ({ amount: String(item.amount), description: items[item.row - 1]?.description || '' }))
        : [{ ...EMPTY_ROW }])
      await onDone()
    } catch (err) {
      notify('error', err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Stack spacing={3}>
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'minmax(0, 2fr) minmax(0, 1fr)' }, gap: 3 }}>
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            Para ventas que no pasaron por el posnet (efectivo, transferencia). Cada importe genera una Factura B a consumidor final con el IVA incluido.
          </Typography>

          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="subtitle2" fontWeight={700} gutterBottom>Repartir un total</Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'flex-start' }}>
              <TextField
                label="Total"
                value={splitTotal}
                onChange={(event) => setSplitTotal(event.target.value)}
                placeholder="1.000.000"
                size="small"
                error={Boolean(splitError)}
                helperText={splitError || ' '}
              />
              <TextField
                label="En cuantas facturas"
                type="number"
                value={splitCount}
                onChange={(event) => setSplitCount(event.target.value)}
                inputProps={{ min: 1, max: MAX_ROWS }}
                size="small"
                helperText=" "
                sx={{ width: { sm: 170 } }}
              />
              <Button variant="outlined" startIcon={<CallSplitIcon />} onClick={applySplit} disabled={busy}>
                Repartir
              </Button>
            </Stack>
          </Paper>

          <Table size="small" aria-label="Importes a facturar">
            <TableHead>
              <TableRow>
                <TableCell sx={{ width: 40 }}>#</TableCell>
                <TableCell sx={{ width: 200 }}>Importe</TableCell>
                <TableCell>Detalle (opcional)</TableCell>
                <TableCell sx={{ width: 48 }} />
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row, index) => {
                const rowInvalid = String(row.amount || '').trim() !== '' && !(amounts[index] > 0)
                return (
                  <TableRow key={index}>
                    <TableCell>{index + 1}</TableCell>
                    <TableCell>
                      <TextField
                        size="small"
                        fullWidth
                        value={row.amount}
                        error={rowInvalid}
                        helperText={rowInvalid ? 'Importe invalido' : ''}
                        onChange={(event) => updateRow(index, 'amount', event.target.value)}
                        inputProps={{ 'aria-label': `Importe factura manual ${index + 1}`, inputMode: 'decimal' }}
                      />
                    </TableCell>
                    <TableCell>
                      <TextField
                        size="small"
                        fullWidth
                        placeholder="Venta mostrador"
                        value={row.description}
                        onChange={(event) => updateRow(index, 'description', event.target.value)}
                        inputProps={{ maxLength: 255, 'aria-label': `Detalle factura manual ${index + 1}` }}
                      />
                    </TableCell>
                    <TableCell>
                      <Tooltip title="Quitar fila">
                        <span>
                          <IconButton size="small" onClick={() => removeRow(index)} disabled={busy} aria-label={`Quitar fila ${index + 1}`}>
                            <DeleteOutlineIcon fontSize="small" />
                          </IconButton>
                        </span>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
          <Box>
            <Button
              startIcon={<AddIcon />}
              onClick={() => setRows((prev) => [...prev, { ...EMPTY_ROW }])}
              disabled={busy || rows.length >= MAX_ROWS}
            >
              Agregar importe
            </Button>
          </Box>
        </Stack>

        <Paper variant="outlined" sx={{ p: 2, alignSelf: 'start', position: { md: 'sticky' }, top: { md: 16 } }}>
          <Stack spacing={1.5}>
            <Typography variant="subtitle2" fontWeight={700}>Resumen</Typography>
            <Stack direction="row" justifyContent="space-between">
              <Typography variant="body2" color="text.secondary">Facturas</Typography>
              <Typography variant="body2">{filledCount}</Typography>
            </Stack>
            <Stack direction="row" justifyContent="space-between">
              <Typography variant="body2" color="text.secondary">Neto gravado</Typography>
              <Typography variant="body2">{formatMoney(net)}</Typography>
            </Stack>
            <Stack direction="row" justifyContent="space-between">
              <Typography variant="body2" color="text.secondary">IVA</Typography>
              <Typography variant="body2">{formatMoney(total - net)}</Typography>
            </Stack>
            <Stack direction="row" justifyContent="space-between" alignItems="baseline">
              <Typography variant="body2" color="text.secondary">Total</Typography>
              <Typography variant="h6" fontWeight={700}>{formatMoney(total)}</Typography>
            </Stack>
            <FormControl size="small" fullWidth>
              <InputLabel id="manual-vat-rate">Alicuota</InputLabel>
              <Select labelId="manual-vat-rate" label="Alicuota" value={vatRate} onChange={(event) => setVatRate(event.target.value)}>
                {VAT_RATES.map((item) => <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>)}
              </Select>
            </FormControl>
            <Button
              variant="contained"
              size="large"
              startIcon={<ReceiptLongIcon />}
              disabled={busy || invalid || total <= 0 || arcaBlocked}
              onClick={() => setConfirmOpen(true)}
            >
              Emitir {filledCount} factura(s)
            </Button>
            <Typography variant="caption" color="text.secondary">
              Facturado en el mes: {formatCurrency(monthInvoiced)}
            </Typography>
          </Stack>
        </Paper>
      </Box>

      <Dialog open={confirmOpen} onClose={() => setConfirmOpen(false)}>
        <DialogTitle>Confirmar facturas manuales</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Se van a emitir {filledCount} Factura(s) B a consumidor final por un total de {formatMoney(total)} con{' '}
            {vatRate.replace('.', ',')}% de IVA incluido.
            {isRealVoucher(arcaStatus)
              ? ' Son comprobantes reales: una vez autorizados solo se anulan con nota de credito.'
              : ' Ambiente de prueba: los comprobantes no tienen validez fiscal.'}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmOpen(false)}>Cancelar</Button>
          <Button variant="contained" onClick={issue}>Emitir</Button>
        </DialogActions>
      </Dialog>
    </Stack>
  )
}
