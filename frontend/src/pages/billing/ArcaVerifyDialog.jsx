import React, { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import { API_BASE } from '../../config'
import { formatDate, formatMoney } from './format'

const API_ARCA_VERIFY = `${API_BASE}/billing/arca/verify/`

const RESULT_LABELS = {
  mismatch: { label: 'Diferencia', color: 'warning' },
  missing: { label: 'No esta en ARCA', color: 'error' },
  simulated: { label: 'Simulado', color: 'default' },
}

function TotalRow({ label, erp, arca }) {
  const same = Math.abs(Number(erp || 0) - Number(arca || 0)) < 0.005
  return (
    <TableRow>
      <TableCell>{label}</TableCell>
      <TableCell align="right">{formatMoney(erp)}</TableCell>
      <TableCell align="right" sx={{ color: same ? 'success.main' : 'error.main', fontWeight: 700 }}>
        {formatMoney(arca)}
      </TableCell>
    </TableRow>
  )
}

export default function ArcaVerifyDialog({ open, onClose, authFetch, year, month, periodLabel }) {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    setReport(null)
    setError('')
  }, [open, year, month])

  const run = async () => {
    setLoading(true)
    setError('')
    setReport(null)
    try {
      const params = new URLSearchParams({ year, month })
      const resp = await authFetch(`${API_ARCA_VERIFY}?${params.toString()}`)
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo verificar con ARCA')
      setReport(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const totals = report?.totals
  const extra = report?.not_in_erp?.vouchers || []

  return (
    <Dialog open={open} onClose={loading ? undefined : onClose} fullWidth maxWidth="md">
      <DialogTitle>Verificar {periodLabel} con ARCA</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          {!report && !loading && !error && (
            <Typography variant="body2" color="text.secondary">
              Consulta en ARCA, uno por uno, los comprobantes que el ERP tiene autorizados en el periodo y compara
              CAE, importe y fecha. Tambien revisa si ARCA tiene numeros que el ERP no registro.
              Puede tardar uno o dos minutos.
            </Typography>
          )}
          {loading && (
            <Box>
              <Typography variant="body2" sx={{ mb: 1 }}>Consultando ARCA...</Typography>
              <LinearProgress />
            </Box>
          )}
          {error && <Alert severity="error">{error}</Alert>}
          {report && (
            <>
              <Alert severity={report.checked === 0 ? 'info' : report.all_ok ? 'success' : 'warning'}>
                {report.checked === 0
                  ? 'No hay comprobantes autorizados en este periodo.'
                  : report.all_ok
                  ? `Los ${report.checked} comprobantes del periodo estan registrados en ARCA y coinciden.`
                  : `Se verificaron ${report.checked} comprobantes: ${report.counts.ok} coinciden, `
                    + `${report.counts.mismatch} con diferencias, ${report.counts.missing} no estan en ARCA`
                    + `${report.counts.simulated ? `, ${report.counts.simulated} simulados` : ''}`
                    + `${extra.length ? ` y ARCA tiene ${extra.length} que el ERP no registra` : ''}.`}
              </Alert>

              <Table size="small" aria-label="Totales ERP contra ARCA">
                <TableHead>
                  <TableRow>
                    <TableCell />
                    <TableCell align="right">ERP</TableCell>
                    <TableCell align="right">ARCA</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TotalRow label="Facturado vigente (sin anuladas)" erp={totals.erp_active_invoices} arca={totals.arca_active_invoices} />
                  <TotalRow label="Facturas emitidas (incluye anuladas)" erp={totals.erp_invoices} arca={totals.arca_invoices} />
                  <TotalRow label="Notas de credito" erp={totals.erp_credit_notes} arca={totals.arca_credit_notes} />
                </TableBody>
              </Table>

              {report.problems.length > 0 && (
                <Box>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>Comprobantes a revisar</Typography>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Comprobante</TableCell>
                        <TableCell>Fecha</TableCell>
                        <TableCell align="right">Importe ERP</TableCell>
                        <TableCell>Resultado</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {report.problems.map((entry) => (
                        <TableRow key={entry.invoice_id}>
                          <TableCell>{entry.voucher}</TableCell>
                          <TableCell>{formatDate(entry.issue_date)}</TableCell>
                          <TableCell align="right">{formatMoney(entry.total)}</TableCell>
                          <TableCell>
                            <Stack spacing={0.5} alignItems="flex-start">
                              <Chip size="small" color={RESULT_LABELS[entry.result]?.color} label={RESULT_LABELS[entry.result]?.label || entry.result} />
                              <Typography variant="caption" color="text.secondary">{entry.problems.join(' · ')}</Typography>
                            </Stack>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Box>
              )}

              {extra.length > 0 && (
                <Box>
                  <Typography variant="subtitle2">En ARCA pero no en el ERP</Typography>
                  <Typography variant="caption" color="text.secondary" component="p" sx={{ mb: 1 }}>
                    Pueden venir de otro sistema que usa el mismo punto de venta, o de una factura que quedo en error
                    despues de que ARCA la autorizo.
                  </Typography>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Comprobante</TableCell>
                        <TableCell>Fecha</TableCell>
                        <TableCell align="right">Importe</TableCell>
                        <TableCell>CAE</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {extra.map((voucher) => (
                        <TableRow key={voucher.voucher}>
                          <TableCell>{voucher.voucher}</TableCell>
                          <TableCell>{formatDate(voucher.issue_date)}</TableCell>
                          <TableCell align="right">{formatMoney(voucher.total)}</TableCell>
                          <TableCell>{voucher.cae}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Box>
              )}
              {report.not_in_erp?.truncated && (
                <Alert severity="info">Hay demasiados numeros salteados: se revisaron los primeros {report.not_in_erp.lookups}.</Alert>
              )}
            </>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={loading}>Cerrar</Button>
        <Button variant="contained" onClick={run} disabled={loading}>
          {report || error ? 'Verificar de nuevo' : 'Verificar'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
