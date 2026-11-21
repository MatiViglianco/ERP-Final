import React from 'react'
import { Box, Card, CardContent, LinearProgress, Skeleton, Stack, Tooltip, Typography } from '@mui/material'
import ReceiptLongIcon from '@mui/icons-material/ReceiptLong'
import PaymentsIcon from '@mui/icons-material/Payments'
import PendingActionsIcon from '@mui/icons-material/PendingActions'
import AccountBalanceIcon from '@mui/icons-material/AccountBalance'
import { formatCurrency } from './format'

function KpiCard({ icon, label, value, detail, loading, children }) {
  return (
    <Card variant="outlined" sx={{ height: '100%' }}>
      <CardContent>
        <Stack direction="row" spacing={1.5} alignItems="flex-start">
          <Box sx={{ mt: 0.5 }} aria-hidden>{icon}</Box>
          <Box sx={{ minWidth: 0, flexGrow: 1 }}>
            <Typography variant="body2" color="text.secondary">{label}</Typography>
            {loading ? (
              <Skeleton variant="text" width="70%" height={40} />
            ) : (
              <Typography variant="h5" fontWeight={700} noWrap>{value}</Typography>
            )}
            {detail ? <Typography variant="caption" color="text.secondary">{detail}</Typography> : null}
            {children}
          </Box>
        </Stack>
      </CardContent>
    </Card>
  )
}

export default function SummaryCards({ summary, pendingCoupons, loading }) {
  const invoiced = Number(summary?.invoices?.authorized_total || 0)
  const collections = summary?.collections || {}
  const posnet = Number(collections.getnet || 0)
  const banks = Number(collections.santander || 0) + Number(collections.bancon || 0)
  const pendingTotal = pendingCoupons.reduce((acc, item) => acc + Number(item.amount || 0), 0)
  const coverage = posnet > 0 ? Math.round((invoiced / posnet) * 100) : null
  const authorizedCount = summary?.invoices?.authorized_count || 0
  const cancelledCount = summary?.invoices?.cancelled_count || 0

  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))', lg: 'repeat(4, minmax(0, 1fr))' }, gap: 2 }}>
      <KpiCard
        icon={<ReceiptLongIcon color="primary" />}
        label="Facturado en ARCA"
        value={formatCurrency(invoiced)}
        loading={loading}
        detail={`${authorizedCount} comprobante(s) autorizado(s)${cancelledCount ? ` · ${cancelledCount} anulado(s)` : ''}`}
      />
      <KpiCard
        icon={<PaymentsIcon color="success" />}
        label="Cobrado por posnet"
        value={formatCurrency(posnet)}
        loading={loading}
      >
        {coverage !== null && !loading && (
          <Tooltip title="Facturado en ARCA sobre lo cobrado por posnet en el periodo">
            <Box sx={{ mt: 1 }}>
              <Stack direction="row" justifyContent="space-between">
                <Typography variant="caption" color="text.secondary">Cobertura facturada</Typography>
                <Typography variant="caption" fontWeight={700}>{coverage}%</Typography>
              </Stack>
              <LinearProgress
                variant="determinate"
                value={Math.min(coverage, 100)}
                color={coverage >= 100 ? 'success' : 'primary'}
                aria-label={`Cobertura facturada ${coverage}%`}
                sx={{ height: 6, borderRadius: 3, mt: 0.5 }}
              />
            </Box>
          </Tooltip>
        )}
      </KpiCard>
      <KpiCard
        icon={<PendingActionsIcon color={pendingCoupons.length ? 'warning' : 'disabled'} />}
        label="Cupones sin facturar"
        value={formatCurrency(pendingTotal)}
        loading={loading}
        detail={pendingCoupons.length ? `${pendingCoupons.length} cupon(es) pendiente(s)` : 'Todo facturado'}
      />
      <KpiCard
        icon={<AccountBalanceIcon color="info" />}
        label="Acreditado en bancos"
        value={formatCurrency(banks)}
        loading={loading}
        detail={`Santander ${formatCurrency(collections.santander)} · Bancor ${formatCurrency(collections.bancon)}`}
      />
    </Box>
  )
}
