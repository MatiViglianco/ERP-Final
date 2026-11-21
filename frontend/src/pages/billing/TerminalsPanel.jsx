import React from 'react'
import {
  Box,
  FormControl,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import { API_BASE } from '../../config'
import { formatDate } from './format'

const API_GETNET_TERMINAL = (id) => `${API_BASE}/billing/getnet/terminals/${id}/`

export default function TerminalsPanel({ terminals, branches, authFetch, onDone, notify, busy, setBusy }) {
  const updateBranch = async (terminalId, branchId) => {
    setBusy(true)
    try {
      const resp = await authFetch(API_GETNET_TERMINAL(terminalId), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ branch_id: branchId || null }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'No se pudo asignar la sucursal')
      notify('success', `Terminal ${data.code} asignada a ${data.branch?.name || 'sin sucursal'}`)
      await onDone()
    } catch (err) {
      notify('error', err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Stack spacing={2}>
      <Typography variant="body2" color="text.secondary">
        Cada codigo POS se vincula a una sucursal y conserva esa asignacion en futuras importaciones.
      </Typography>
      <Table size="small" aria-label="Terminales Getnet">
        <TableHead>
          <TableRow>
            <TableCell>Terminal</TableCell>
            <TableCell>Establecimiento</TableCell>
            <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>Ultima importacion</TableCell>
            <TableCell>Sucursal</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {terminals.map((terminal) => (
            <TableRow key={terminal.id}>
              <TableCell>{terminal.code}</TableCell>
              <TableCell>{terminal.establishment_name || terminal.establishment_number || '-'}</TableCell>
              <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>{formatDate(terminal.last_seen_at)}</TableCell>
              <TableCell sx={{ minWidth: 220 }}>
                <FormControl fullWidth size="small">
                  <Select
                    inputProps={{ 'aria-label': `Sucursal terminal ${terminal.code}` }}
                    value={terminal.branch?.id && branches.some((branch) => branch.id === terminal.branch.id)
                      ? String(terminal.branch.id)
                      : ''}
                    disabled={busy}
                    onChange={(event) => updateBranch(terminal.id, event.target.value)}
                  >
                    <MenuItem value="">Sin sucursal</MenuItem>
                    {branches.map((branch) => <MenuItem key={branch.id} value={String(branch.id)}>{branch.name}</MenuItem>)}
                  </Select>
                </FormControl>
              </TableCell>
            </TableRow>
          ))}
          {!terminals.length && (
            <TableRow>
              <TableCell colSpan={4}>
                <Box sx={{ py: 4, textAlign: 'center' }}>
                  <Typography color="text.secondary">Todavia no se importaron terminales Getnet.</Typography>
                </Box>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </Stack>
  )
}
