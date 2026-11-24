import React, { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Divider,
  Drawer,
  IconButton,
  LinearProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import { API_BASE } from '../../config'
import {
  RETRYABLE_STATUSES,
  formatDate,
  formatMoney,
  formatVoucher,
  invoiceClientLabel,
  isCreditNote,
  isRealVoucher,
  statusColor,
} from './format'

const API_INVOICE = (id) => `${API_BASE}/billing/invoices/${id}/`
const API_INVOICE_AUTHORIZE = (id) => `${API_BASE}/billing/invoices/${id}/authorize/`
const API_INVOICE_CREDIT_NOTE = (id) => `${API_BASE}/billing/invoices/${id}/credit-note/`

function DetailRow({ label, children }) {
  return (
    <Stack direction="row" justifyContent="space-between" spacing={2} sx={{ py: 0.75 }}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Box sx={{ textAlign: 'right', minWidth: 0 }}>{children}</Box>
    </Stack>
  )
}

export default function InvoiceDetailDrawer({ invoiceId, onClose, authFetch, arcaStatus, onChanged, notify }) {
  const [invoice, setInvoice] = useState(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [cancelOpen, setCancelOpen] = useState(false)
  const [reason, setReason] = useState('')

  useEffect(() => {
    if (!invoiceId) {
      setInvoice(null)
      return
    }
    let active = true
    setLoading(true)
    setLoadError('')
    authFetch(API_INVOICE(invoiceId))
      .then(async (resp) => {
        const data = await resp.json()
        if (!resp.ok) throw new Error(data.detail || 'No se pudo cargar el comprobante')
        if (active) setInvoice(data)
      })
      .catch((err) => active && setLoadError(err.message))
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [authFetch, invoiceId])

  const runAction = async (url, body, successMessage) => {
    setBusy(true)
    try {
      const resp = await authFetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'ARCA no autorizo la operacion')
      notify('success', successMessage(data))
      await onChanged()
      onClose()
    } catch (err) {
      notify('error', err.message)
      await onChanged()
    } finally {
      setBusy(false)
    }
  }

  const cancelInvoice = () => {
    setCancelOpen(false)
    runAction(
      API_INVOICE_CREDIT_NOTE(invoice.id),
      { reason },
      (data) => `${formatVoucher(invoice)} anulada con ${formatVoucher(data)} (CAE ${data.cae})`,
    )
  }

  const retryInvoice = () => runAction(
    API_INVOICE_AUTHORIZE(invoice.id),
    null,
    (data) => `${formatVoucher(data)} autorizada (CAE ${data.cae})`,
  )

  const copyCae = () => {
    if (invoice?.cae && navigator.clipboard) navigator.clipboard.writeText(invoice.cae)
  }

  const canCancel = invoice && invoice.status === 'authorized' && !isCreditNote(invoice) && invoice.voucher_number
  const canRetry = invoice && RETRYABLE_STATUSES.has(invoice.status)
  const realVoucher = isRealVoucher(arcaStatus)

  return (
    <>
      <Drawer
        anchor="right"
        open={Boolean(invoiceId)}
        onClose={onClose}
        PaperProps={{ sx: { width: { xs: '100%', sm: 460 } } }}
      >
        <Stack sx={{ p: 3, height: '100%' }} spacing={2}>
          <Stack direction="row" alignItems="center" justifyContent="space-between">
            <Box>
              <Typography variant="overline" color="text.secondary">Comprobante</Typography>
              <Typography variant="h6" fontWeight={700}>{invoice ? formatVoucher(invoice) : 'Cargando...'}</Typography>
            </Box>
            <IconButton onClick={onClose} aria-label="Cerrar detalle">
              <CloseIcon />
            </IconButton>
          </Stack>
          {(loading || busy) && <LinearProgress />}
          {loadError && <Alert severity="error">{loadError}</Alert>}

          {invoice && (
            <>
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                <Chip color={statusColor(invoice.status)} label={invoice.status_label} />
                <Chip variant="outlined" label={invoice.source_label} />
                {isCreditNote(invoice) && <Chip variant="outlined" color="warning" label="Nota de credito" />}
              </Stack>

              {invoice.error_message && invoice.status !== 'authorized' && (
                <Alert severity="error">{invoice.error_message}</Alert>
              )}
              {invoice.cancelled_by_voucher && (
                <Alert severity="info">Anulada por {invoice.cancelled_by_voucher}{invoice.reason ? `. Motivo: ${invoice.reason}` : ''}</Alert>
              )}
              {invoice.cancels_voucher && (
                <Alert severity="info">Anula {invoice.cancels_voucher}{invoice.reason ? `. Motivo: ${invoice.reason}` : ''}</Alert>
              )}

              <Box>
                <DetailRow label="Fecha">
                  <Typography variant="body2">{formatDate(invoice.issue_date)}</Typography>
                </DetailRow>
                <DetailRow label="Receptor">
                  <Typography variant="body2">{invoiceClientLabel(invoice)}</Typography>
                </DetailRow>
                <DetailRow label="Sucursal">
                  <Typography variant="body2">{invoice.branch?.name || '-'}</Typography>
                </DetailRow>
                <DetailRow label="CAE">
                  {invoice.cae ? (
                    <Stack direction="row" spacing={0.5} alignItems="center" justifyContent="flex-end">
                      <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>{invoice.cae}</Typography>
                      <IconButton size="small" onClick={copyCae} aria-label="Copiar CAE">
                        <ContentCopyIcon fontSize="inherit" />
                      </IconButton>
                    </Stack>
                  ) : <Typography variant="body2">-</Typography>}
                </DetailRow>
                <DetailRow label="Vencimiento CAE">
                  <Typography variant="body2">{formatDate(invoice.cae_due_date)}</Typography>
                </DetailRow>
              </Box>

              <Divider />

              <Box>
                <DetailRow label="Neto gravado">
                  <Typography variant="body2">{formatMoney(invoice.net_amount)}</Typography>
                </DetailRow>
                <DetailRow label="IVA">
                  <Typography variant="body2">{formatMoney(invoice.vat_amount)}</Typography>
                </DetailRow>
                <DetailRow label="Total">
                  <Typography variant="h6" fontWeight={700}>{formatMoney(invoice.total_amount)}</Typography>
                </DetailRow>
              </Box>

              {invoice.lines?.length > 0 && (
                <Table size="small" aria-label="Detalle del comprobante">
                  <TableHead>
                    <TableRow>
                      <TableCell>Detalle</TableCell>
                      <TableCell align="right">Importe</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {invoice.lines.map((line) => (
                      <TableRow key={line.id}>
                        <TableCell>{line.description}</TableCell>
                        <TableCell align="right">{formatMoney(line.total)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}

              <Box sx={{ flexGrow: 1 }} />

              <Stack direction="row" spacing={1} justifyContent="flex-end">
                {canRetry && (
                  <Button variant="contained" onClick={retryInvoice} disabled={busy}>
                    Reintentar autorizacion
                  </Button>
                )}
                {canCancel && (
                  <Button
                    variant="outlined"
                    color="error"
                    onClick={() => {
                      setReason('')
                      setCancelOpen(true)
                    }}
                    disabled={busy}
                  >
                    Anular con nota de credito
                  </Button>
                )}
              </Stack>
            </>
          )}
        </Stack>
      </Drawer>

      <Dialog open={cancelOpen} onClose={() => setCancelOpen(false)}>
        <DialogTitle>Anular {invoice ? formatVoucher(invoice) : 'comprobante'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2}>
            <DialogContentText>
              Se va a emitir una nota de credito por {formatMoney(invoice?.total_amount)} que anula este comprobante.
              {realVoucher
                ? ' Es un comprobante real ante ARCA y no se puede deshacer.'
                : ' Ambiente de prueba: el comprobante no tiene validez fiscal.'}
              {invoice?.source === 'getnet' ? ' El cupon vuelve a quedar disponible para facturar.' : ''}
            </DialogContentText>
            <TextField
              label="Motivo (opcional)"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              inputProps={{ maxLength: 255 }}
              fullWidth
              autoFocus
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCancelOpen(false)}>Volver</Button>
          <Button variant="contained" color="error" onClick={cancelInvoice}>Emitir nota de credito</Button>
        </DialogActions>
      </Dialog>
    </>
  )
}
