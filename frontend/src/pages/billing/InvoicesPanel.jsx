import React, { useMemo, useState } from 'react'
import {
  Box,
  Button,
  Chip,
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
import SearchIcon from '@mui/icons-material/Search'
import FileDownloadIcon from '@mui/icons-material/FileDownload'
import ChevronRightIcon from '@mui/icons-material/ChevronRight'
import {
  INVOICE_SOURCES,
  INVOICE_STATUSES,
  csvNumber,
  downloadCsv,
  formatDate,
  formatMoney,
  formatVoucher,
  invoiceClientLabel,
  isCreditNote,
  normalizeText,
  statusColor,
  useClientPagination,
} from './format'

export default function InvoicesPanel({ invoices, loading, periodLabel, onOpenInvoice }) {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [source, setSource] = useState('')

  const filtered = useMemo(() => {
    const term = normalizeText(search.trim())
    return invoices.filter((invoice) => {
      if (status && invoice.status !== status) return false
      if (source && invoice.source !== source) return false
      if (!term) return true
      const haystack = normalizeText([
        formatVoucher(invoice),
        invoice.cae,
        invoiceClientLabel(invoice),
        invoice.branch?.name,
        invoice.total_amount,
        formatMoney(invoice.total_amount),
      ].join(' '))
      return haystack.includes(term)
    })
  }, [invoices, search, status, source])

  // Mismo criterio que el resumen: las facturas anuladas ya salen del total,
  // asi que su nota de credito no se descuenta otra vez.
  const filteredTotal = useMemo(() => filtered.reduce((acc, invoice) => (
    invoice.status === 'authorized' && !isCreditNote(invoice)
      ? acc + Number(invoice.total_amount || 0)
      : acc
  ), 0), [filtered])

  const { pageItems, paginationProps } = useClientPagination(filtered, `${search}|${status}|${source}`)

  const exportCsv = () => {
    downloadCsv(
      `comprobantes-${periodLabel}.csv`,
      ['Fecha', 'Comprobante', 'Punto de venta', 'Numero', 'CAE', 'Vto CAE', 'Receptor', 'Origen', 'Estado', 'Neto', 'IVA', 'Total'],
      filtered.map((invoice) => [
        formatDate(invoice.issue_date),
        formatVoucher(invoice),
        invoice.point_of_sale,
        invoice.voucher_number || '',
        invoice.cae || '',
        formatDate(invoice.cae_due_date),
        invoiceClientLabel(invoice),
        invoice.source_label,
        invoice.status_label,
        csvNumber((isCreditNote(invoice) ? -1 : 1) * invoice.net_amount),
        csvNumber((isCreditNote(invoice) ? -1 : 1) * invoice.vat_amount),
        csvNumber((isCreditNote(invoice) ? -1 : 1) * invoice.total_amount),
      ]),
    )
  }

  const hasFilters = Boolean(search || status || source)

  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ md: 'center' }}>
        <TextField
          size="small"
          placeholder="Buscar por numero, CAE, receptor o importe"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          sx={{ flexGrow: 1, maxWidth: { md: 420 } }}
          inputProps={{ 'aria-label': 'Buscar comprobantes' }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment>
            ),
          }}
        />
        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel id="invoice-status-filter">Estado</InputLabel>
          <Select labelId="invoice-status-filter" label="Estado" value={status} onChange={(event) => setStatus(event.target.value)}>
            <MenuItem value="">Todos</MenuItem>
            {INVOICE_STATUSES.map((item) => <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>)}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 170 }}>
          <InputLabel id="invoice-source-filter">Origen</InputLabel>
          <Select labelId="invoice-source-filter" label="Origen" value={source} onChange={(event) => setSource(event.target.value)}>
            <MenuItem value="">Todos</MenuItem>
            {INVOICE_SOURCES.map((item) => <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>)}
          </Select>
        </FormControl>
        {hasFilters && (
          <Button
            size="small"
            onClick={() => {
              setSearch('')
              setStatus('')
              setSource('')
            }}
          >
            Limpiar filtros
          </Button>
        )}
        <Box sx={{ flexGrow: 1 }} />
        <Button variant="outlined" startIcon={<FileDownloadIcon />} onClick={exportCsv} disabled={!filtered.length}>
          Exportar CSV
        </Button>
      </Stack>

      <Typography variant="body2" color="text.secondary">
        {filtered.length} comprobante(s){hasFilters ? ' con los filtros aplicados' : ''} · Facturado vigente (sin anuladas):{' '}
        <strong>{formatMoney(filteredTotal)}</strong>
      </Typography>

      <TableContainer>
        <Table size="small" aria-label="Comprobantes del periodo">
          <TableHead>
            <TableRow>
              <TableCell>Fecha</TableCell>
              <TableCell>Comprobante</TableCell>
              <TableCell sx={{ display: { xs: 'none', sm: 'table-cell' } }}>Receptor</TableCell>
              <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>Origen</TableCell>
              <TableCell>Estado</TableCell>
              <TableCell align="right">Total</TableCell>
              <TableCell padding="checkbox" />
            </TableRow>
          </TableHead>
          <TableBody>
            {pageItems.map((invoice) => (
              <TableRow
                key={invoice.id}
                hover
                tabIndex={0}
                onClick={() => onOpenInvoice(invoice.id)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    onOpenInvoice(invoice.id)
                  }
                }}
                sx={{ cursor: 'pointer' }}
                aria-label={`Ver ${formatVoucher(invoice)}`}
              >
                <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDate(invoice.issue_date)}</TableCell>
                <TableCell>
                  <Typography variant="body2" fontWeight={600} sx={{ whiteSpace: 'nowrap' }}>{formatVoucher(invoice)}</Typography>
                  {invoice.cae && (
                    <Typography variant="caption" color="text.secondary">CAE {invoice.cae}</Typography>
                  )}
                </TableCell>
                <TableCell sx={{ display: { xs: 'none', sm: 'table-cell' } }}>{invoiceClientLabel(invoice)}</TableCell>
                <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>{invoice.source_label}</TableCell>
                <TableCell>
                  <Stack spacing={0.5} alignItems="flex-start">
                    <Chip size="small" color={statusColor(invoice.status)} label={invoice.status_label} />
                    {invoice.cancelled_by_voucher && (
                      <Typography variant="caption" color="text.secondary">Por {invoice.cancelled_by_voucher}</Typography>
                    )}
                    {invoice.cancels_voucher && (
                      <Typography variant="caption" color="text.secondary">Anula {invoice.cancels_voucher}</Typography>
                    )}
                  </Stack>
                </TableCell>
                <TableCell align="right" sx={{ whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>
                  {isCreditNote(invoice) ? `- ${formatMoney(invoice.total_amount)}` : formatMoney(invoice.total_amount)}
                </TableCell>
                <TableCell padding="checkbox">
                  <ChevronRightIcon fontSize="small" color="action" />
                </TableCell>
              </TableRow>
            ))}
            {!pageItems.length && (
              <TableRow>
                <TableCell colSpan={7}>
                  <Box sx={{ py: 4, textAlign: 'center' }}>
                    <Typography color="text.secondary">
                      {loading ? 'Cargando comprobantes...' : hasFilters ? 'Ningun comprobante coincide con los filtros.' : 'Sin comprobantes en el periodo.'}
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      <TablePagination {...paginationProps} />
    </Stack>
  )
}
