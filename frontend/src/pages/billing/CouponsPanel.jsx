import React, { useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControl,
  InputAdornment,
  InputLabel,
  MenuItem,
  Paper,
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
import SearchIcon from '@mui/icons-material/Search'
import ReceiptLongIcon from '@mui/icons-material/ReceiptLong'
import { API_BASE } from '../../config'
import {
  VAT_RATES,
  formatDate,
  formatMoney,
  isRealVoucher,
  normalizeText,
  statusColor,
  useClientPagination,
} from './format'

const API_GETNET_INVOICES = `${API_BASE}/billing/getnet/invoices/`

export default function CouponsPanel({ candidates, arcaStatus, authFetch, onDone, notify, busy, setBusy }) {
  const [search, setSearch] = useState('')
  const [day, setDay] = useState('')
  const [selected, setSelected] = useState(new Set())
  const [vatRate, setVatRate] = useState('10.5')
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [failures, setFailures] = useState([])

  const days = useMemo(() => [...new Set(candidates.map((item) => item.date))].sort(), [candidates])

  const filtered = useMemo(() => {
    const term = normalizeText(search.trim())
    return candidates.filter((item) => {
      if (day && item.date !== day) return false
      if (!term) return true
      return normalizeText([
        item.coupon_number, item.external_id, item.brand, item.card_last_four,
        item.terminal?.code, item.amount, formatMoney(item.amount),
      ].join(' ')).includes(term)
    })
  }, [candidates, search, day])

  const { pageItems, paginationProps } = useClientPagination(filtered, `${search}|${day}`)

  const selectedItems = useMemo(
    () => candidates.filter((item) => selected.has(item.id)),
    [candidates, selected],
  )
  const selectedTotal = selectedItems.reduce((acc, item) => acc + Number(item.amount || 0), 0)
  const filteredTotal = filtered.reduce((acc, item) => acc + Number(item.amount || 0), 0)
  const pageAllSelected = pageItems.length > 0 && pageItems.every((item) => selected.has(item.id))
  const pageSomeSelected = pageItems.some((item) => selected.has(item.id))
  const arcaBlocked = arcaStatus?.provider === 'wsfe' && !arcaStatus?.ready

  const toggle = (id) => setSelected((prev) => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })

  const togglePage = () => setSelected((prev) => {
    const next = new Set(prev)
    pageItems.forEach((item) => (pageAllSelected ? next.delete(item.id) : next.add(item.id)))
    return next
  })

  const selectAllFiltered = () => setSelected(new Set(filtered.map((item) => item.id)))

  const issue = async () => {
    setConfirmOpen(false)
    setBusy(true)
    setFailures([])
    try {
      const resp = await authFetch(API_GETNET_INVOICES, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ payment_ids: Array.from(selected), vat_rate: vatRate }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudieron facturar los cupones')
      const failed = (data.results || []).filter((item) => !item.ok)
      setFailures(failed)
      setSelected(new Set(failed.map((item) => item.payment_id)))
      if (data.authorized) notify('success', `${data.authorized} factura(s) autorizada(s)`)
      if (failed.length) notify('error', `${failed.length} cupon(es) no se pudieron facturar. Quedaron seleccionados para reintentar.`)
      await onDone()
    } catch (err) {
      notify('error', err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ md: 'center' }}>
        <TextField
          size="small"
          placeholder="Buscar por cupon, tarjeta o importe"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          sx={{ flexGrow: 1, maxWidth: { md: 360 } }}
          inputProps={{ 'aria-label': 'Buscar cupones' }}
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
        />
        <FormControl size="small" sx={{ minWidth: 170 }}>
          <InputLabel id="coupon-day-filter">Dia</InputLabel>
          <Select labelId="coupon-day-filter" label="Dia" value={day} onChange={(event) => setDay(event.target.value)}>
            <MenuItem value="">Todos los dias</MenuItem>
            {days.map((item) => <MenuItem key={item} value={item}>{formatDate(item)}</MenuItem>)}
          </Select>
        </FormControl>
        <Typography variant="body2" color="text.secondary">
          {filtered.length} cupon(es) · {formatMoney(filteredTotal)}
        </Typography>
        <Box sx={{ flexGrow: 1 }} />
        {filtered.length > 0 && selected.size < filtered.length && (
          <Button size="small" onClick={selectAllFiltered}>Seleccionar los {filtered.length}</Button>
        )}
        {selected.size > 0 && (
          <Button size="small" onClick={() => setSelected(new Set())}>Limpiar seleccion</Button>
        )}
      </Stack>

      {failures.length > 0 && (
        <Alert severity="warning" onClose={() => setFailures([])}>
          {failures.map((item) => <div key={item.payment_id}>{item.detail}</div>)}
        </Alert>
      )}

      <TableContainer>
        <Table size="small" aria-label="Cupones posnet sin facturar">
          <TableHead>
            <TableRow>
              <TableCell padding="checkbox">
                <Checkbox
                  inputProps={{ 'aria-label': 'Seleccionar cupones de esta pagina' }}
                  checked={pageAllSelected}
                  indeterminate={pageSomeSelected && !pageAllSelected}
                  onChange={togglePage}
                  disabled={!pageItems.length}
                />
              </TableCell>
              <TableCell>Fecha</TableCell>
              <TableCell>Cupon</TableCell>
              <TableCell>Tarjeta</TableCell>
              <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>Terminal</TableCell>
              <TableCell>Estado</TableCell>
              <TableCell align="right">Importe</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {pageItems.map((item) => (
              <TableRow
                key={item.id}
                hover
                selected={selected.has(item.id)}
                onClick={() => toggle(item.id)}
                sx={{ cursor: 'pointer' }}
              >
                <TableCell padding="checkbox">
                  <Checkbox
                    inputProps={{ 'aria-label': `Seleccionar cupon ${item.coupon_number || item.external_id}` }}
                    checked={selected.has(item.id)}
                    onClick={(event) => event.stopPropagation()}
                    onChange={() => toggle(item.id)}
                  />
                </TableCell>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDate(item.date)}</TableCell>
                <TableCell>{item.coupon_number || item.external_id}</TableCell>
                <TableCell sx={{ textTransform: 'capitalize' }}>
                  {[item.brand, item.card_last_four && `**** ${item.card_last_four}`].filter(Boolean).join(' ') || '-'}
                </TableCell>
                <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>{item.terminal?.code || '-'}</TableCell>
                <TableCell>
                  {item.invoice_status ? (
                    <Stack spacing={0.5} alignItems="flex-start">
                      <Chip size="small" color={statusColor(item.invoice_status)} label="Reintentar" />
                      {item.invoice_error && <Typography variant="caption" color="error">{item.invoice_error}</Typography>}
                    </Stack>
                  ) : (
                    <Typography variant="caption" color="text.secondary">Sin facturar</Typography>
                  )}
                </TableCell>
                <TableCell align="right" sx={{ whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>
                  {formatMoney(item.amount)}
                </TableCell>
              </TableRow>
            ))}
            {!pageItems.length && (
              <TableRow>
                <TableCell colSpan={7}>
                  <Box sx={{ py: 4, textAlign: 'center' }}>
                    <Typography color="text.secondary">
                      {candidates.length
                        ? 'Ningun cupon coincide con los filtros.'
                        : 'No hay cupones pendientes de facturar en el periodo. Importa el CSV de Getnet desde Cargar.'}
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      <TablePagination {...paginationProps} />

      <Paper
        elevation={6}
        sx={{
          position: 'sticky',
          bottom: 16,
          p: 2,
          display: selected.size ? 'block' : 'none',
          zIndex: 2,
        }}
      >
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }}>
          <Box sx={{ flexGrow: 1 }}>
            <Typography fontWeight={700}>{selected.size} cupon(es) seleccionado(s)</Typography>
            <Typography variant="body2" color="text.secondary">Total {formatMoney(selectedTotal)} · una Factura B por cupon</Typography>
          </Box>
          <FormControl size="small" sx={{ minWidth: 150 }}>
            <InputLabel id="coupon-vat-rate">Alicuota</InputLabel>
            <Select labelId="coupon-vat-rate" label="Alicuota" value={vatRate} onChange={(event) => setVatRate(event.target.value)}>
              {VAT_RATES.map((item) => <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>)}
            </Select>
          </FormControl>
          <Button
            variant="contained"
            startIcon={<ReceiptLongIcon />}
            disabled={busy || arcaBlocked}
            onClick={() => setConfirmOpen(true)}
          >
            Facturar {selected.size}
          </Button>
        </Stack>
      </Paper>

      <Dialog open={confirmOpen} onClose={() => setConfirmOpen(false)}>
        <DialogTitle>Confirmar facturacion</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Se van a emitir {selected.size} Factura(s) B a consumidor final por {formatMoney(selectedTotal)} con{' '}
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
