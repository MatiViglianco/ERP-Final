import React, { useMemo, useState } from 'react'
import { Container, Box, Card, CardContent, Typography, TextField, FormControlLabel, Checkbox, LinearProgress, Alert, Button, FormControl, InputLabel, Select, MenuItem, Stack } from '@mui/material'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { API_BASE } from '../config'
import useBranches from '../hooks/useBranches.js'

const API_UPLOAD = `${API_BASE}/upload/`
const API_BANK_UPLOAD = `${API_BASE}/bank/upload/`
const API_ACCOUNT_UPLOAD = `${API_BASE}/accounts/upload/`
const API_GETNET_UPLOAD = `${API_BASE}/billing/getnet/import/`

export default function UploadPage() {
  const today = useMemo(() => new Date().toISOString().split('T')[0], [])
  const [file, setFile] = useState(null)
  const [fechaDesde, setFechaDesde] = useState(today)
  const [fechaHasta, setFechaHasta] = useState(today)
  const [variosDias, setVariosDias] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [bankFile, setBankFile] = useState(null)
  const [bankType, setBankType] = useState('santander')
  const [bankLoading, setBankLoading] = useState(false)
  const [bankError, setBankError] = useState('')

  const [getnetFile, setGetnetFile] = useState(null)
  const [getnetBranchId, setGetnetBranchId] = useState('')
  const [getnetLoading, setGetnetLoading] = useState(false)
  const [getnetError, setGetnetError] = useState('')
  const [getnetResult, setGetnetResult] = useState(null)

  const [accountFile, setAccountFile] = useState(null)
  const [accountLoading, setAccountLoading] = useState(false)
  const [accountError, setAccountError] = useState('')
  const [selectedBranchId, setSelectedBranchId] = useState('')

  const navigate = useNavigate()
  const { authFetch } = useAuth()
  const { branches, branchesError } = useBranches(authFetch)
  const datePickerIconStyles = useMemo(() => ({
    '& input::-webkit-calendar-picker-indicator': {
      filter: 'invert(1)',
      opacity: 1,
    },
  }), [])

  const buildFormData = (overwrite = false) => {
    if (!file) {
      setError('Selecciona un archivo CSV de la balanza.')
      return null
    }
    const form = new FormData()
    form.append('file', file)
    if (selectedBranchId) form.append('branch_id', selectedBranchId)

    if (!variosDias) {
      if (!fechaDesde) {
        setError('Selecciona la fecha del archivo (un solo dia).')
        return null
      }
      form.append('fecha', fechaDesde)
    } else {
      if (!fechaDesde || !fechaHasta) {
        setError('Completa las fechas Desde y Hasta para varios dias.')
        return null
      }
      form.append('fecha_desde', fechaDesde)
      form.append('fecha_hasta', fechaHasta)
    }

    if (overwrite) {
      form.append('overwrite', '1')
    }

    return form
  }

  const submitUpload = async ({ overwrite = false } = {}) => {
    setError('')
    const form = buildFormData(overwrite)
    if (!form) return

    setLoading(true)
    try {
      const resp = await authFetch(API_UPLOAD, { method: 'POST', body: form })
      let data = {}
      try {
        data = await resp.json()
      } catch (_) {}

      if (!resp.ok) {
        if (resp.status === 409 && data?.requires_overwrite && !overwrite) {
          const confirmed = window.confirm(data.detail || 'Ya existen datos para ese periodo. Sobrescribirlos?')
          if (confirmed) {
            await submitUpload({ overwrite: true })
          } else {
            setError('Carga cancelada por el usuario.')
          }
          return
        }
        throw new Error(data?.detail || 'Error de servidor')
      }

      const startDate = fechaDesde
      const endDate = variosDias ? fechaHasta : fechaDesde
      const params = new URLSearchParams()
      if (data.batch_id) params.set('batch_id', data.batch_id)
      if (selectedBranchId) params.set('branch_id', selectedBranchId)
      if (startDate) params.set('fecha_desde', startDate)
      if (endDate) params.set('fecha_hasta', endDate)
      params.set('range', 'day')
      if (variosDias && endDate && startDate && endDate !== startDate) {
        params.set('multi', '1')
      }
      navigate(`/balanza?${params.toString()}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const onUpload = (e) => {
    e.preventDefault()
    submitUpload()
  }

  const submitBankUpload = async ({ overwrite = false } = {}) => {
    setBankError('')
    if (!bankFile) {
      setBankError('Selecciona el archivo bancario')
      return
    }
    const form = new FormData()
    form.append('file', bankFile)
    form.append('bank', bankType)
    if (overwrite) form.append('overwrite', '1')

    setBankLoading(true)
    try {
      const resp = await authFetch(API_BANK_UPLOAD, { method: 'POST', body: form })
      let data = {}
      try { data = await resp.json() } catch (_) {}
      if (!resp.ok) {
        if (resp.status === 409 && data?.requires_overwrite && !overwrite) {
          const confirmed = window.confirm(data.detail || 'Ya existen movimientos para esas fechas. Sobrescribirlos?')
          if (confirmed) {
            await submitBankUpload({ overwrite: true })
          } else {
            setBankError('Carga cancelada por el usuario.')
          }
          return
        }
        throw new Error(data?.detail || 'Error al cargar los movimientos')
      }
      navigate(`/bancos?bank=${bankType}`)
    } catch (err) {
      setBankError(err.message)
    } finally {
      setBankLoading(false)
    }
  }

  const onBankUpload = (e) => {
    e.preventDefault()
    submitBankUpload()
  }

  const submitGetnetUpload = async (event) => {
    event.preventDefault()
    setGetnetError('')
    setGetnetResult(null)
    if (!getnetFile) {
      setGetnetError('Selecciona el CSV descargado desde Mis transacciones de Getnet')
      return
    }
    const form = new FormData()
    form.append('file', getnetFile)
    if (getnetBranchId) form.append('branch_id', getnetBranchId)

    setGetnetLoading(true)
    try {
      const resp = await authFetch(API_GETNET_UPLOAD, { method: 'POST', body: form })
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok) throw new Error(data?.detail || 'No se pudo importar el CSV de Getnet')
      setGetnetResult(data)
    } catch (err) {
      setGetnetError(err.message)
    } finally {
      setGetnetLoading(false)
    }
  }

  const submitAccountUpload = async () => {
    setAccountError('')
    if (!accountFile) {
      setAccountError('Selecciona el archivo JSON de cuentas corrientes')
      return
    }
    const form = new FormData()
    form.append('file', accountFile)
    if (selectedBranchId) form.append('branch_id', selectedBranchId)
    setAccountLoading(true)
    try {
      const resp = await authFetch(API_ACCOUNT_UPLOAD, { method: 'POST', body: form })
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok) {
        throw new Error(data?.detail || 'No se pudo procesar el archivo')
      }
      setAccountError('')
      navigate(selectedBranchId ? `/cuentas?branch_id=${selectedBranchId}` : '/cuentas')
    } catch (err) {
      setAccountError(err.message)
    } finally {
      setAccountLoading(false)
    }
  }

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Typography variant="h4" gutterBottom>Cargar datos</Typography>
      <Stack spacing={3}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>Ventas (balanza)</Typography>
            <Box component="form" onSubmit={onUpload} sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <FormControl fullWidth>
                <InputLabel id="branch-select">Sucursal</InputLabel>
                <Select labelId="branch-select" label="Sucursal" value={selectedBranchId} onChange={(e) => setSelectedBranchId(e.target.value)}>
                  <MenuItem value="">Sin sucursal</MenuItem>
                  {branches.map((branch) => (
                    <MenuItem key={branch.id} value={String(branch.id)}>{branch.name}</MenuItem>
                  ))}
                </Select>
              </FormControl>
              {branchesError && <Alert severity="warning">{branchesError}</Alert>}
              <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] || null)} />
              <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: variosDias ? '1fr 1fr' : '1fr' }, gap: 2 }}>
                <TextField type="date" fullWidth label="Desde" InputLabelProps={{ shrink: true }} value={fechaDesde} onChange={(e) => setFechaDesde(e.target.value)} sx={datePickerIconStyles} />
                {variosDias && (
                  <TextField type="date" fullWidth label="Hasta" InputLabelProps={{ shrink: true }} value={fechaHasta} onChange={(e) => setFechaHasta(e.target.value)} sx={datePickerIconStyles} />
                )}
              </Box>
              <FormControlLabel control={<Checkbox checked={variosDias} onChange={(e) => setVariosDias(e.target.checked)} />} label="Varios dias" />
              <Box>
                <Button type="submit" variant="contained" disabled={loading}>Subir ventas</Button>
              </Box>
              {loading && <LinearProgress />}
              {error && <Alert severity="error">{error}</Alert>}
            </Box>
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>Transacciones Getnet (CSV)</Typography>
            <Box component="form" onSubmit={submitGetnetUpload} sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <FormControl fullWidth>
                <InputLabel id="getnet-branch-select">Sucursal</InputLabel>
                <Select
                  labelId="getnet-branch-select"
                  label="Sucursal"
                  value={getnetBranchId}
                  onChange={(event) => setGetnetBranchId(event.target.value)}
                >
                  <MenuItem value="">Detectar sin asignar</MenuItem>
                  {branches.map((branch) => (
                    <MenuItem key={branch.id} value={String(branch.id)}>{branch.name}</MenuItem>
                  ))}
                </Select>
              </FormControl>
              <Typography variant="body2" color="text.secondary">
                Usa el archivo descargado desde Reportes, Mis transacciones. Las reimportaciones actualizan estados sin duplicar cobros.
              </Typography>
              <input
                data-testid="getnet-csv-input"
                type="file"
                accept=".csv,text/csv"
                onChange={(event) => setGetnetFile(event.target.files?.[0] || null)}
              />
              <Box>
                <Button type="submit" variant="contained" disabled={getnetLoading}>
                  {getnetLoading ? 'Procesando...' : 'Subir transacciones Getnet'}
                </Button>
              </Box>
              {getnetLoading && <LinearProgress />}
              {getnetError && <Alert severity="error">{getnetError}</Alert>}
              {getnetResult && (
                <Alert severity={getnetResult.unassigned_terminals?.length ? 'warning' : 'success'}>
                  Importacion Getnet completada: {getnetResult.created} nuevas, {getnetResult.updated} actualizadas.
                  {getnetResult.unassigned_terminals?.length
                    ? ` Terminales sin sucursal: ${getnetResult.unassigned_terminals.map((terminal) => terminal.code).join(', ')}.`
                    : ''}
                </Alert>
              )}
            </Box>
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>Movimientos bancarios</Typography>
            <Box component="form" onSubmit={onBankUpload} sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <FormControl fullWidth>
                <InputLabel id="bank-type">Banco</InputLabel>
                <Select labelId="bank-type" label="Banco" value={bankType} onChange={(e) => setBankType(e.target.value)}>
                  <MenuItem value="santander">Santander (CSV)</MenuItem>
                  <MenuItem value="bancon">Bancon (CSV/XLS)</MenuItem>
                </Select>
              </FormControl>
              <input type="file" accept=".csv,.xls,.xlsx" onChange={(e) => setBankFile(e.target.files?.[0] || null)} />
              <Box>
                <Button type="submit" variant="outlined" disabled={bankLoading}>Subir movimientos</Button>
              </Box>
              {bankLoading && <LinearProgress />}
              {bankError && <Alert severity="error">{bankError}</Alert>}
            </Box>
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>Cuentas corrientes (JSON)</Typography>
            <Stack spacing={2}>
              <FormControl fullWidth>
                <InputLabel id="account-branch-select">Sucursal</InputLabel>
                <Select labelId="account-branch-select" label="Sucursal" value={selectedBranchId} onChange={(e) => setSelectedBranchId(e.target.value)}>
                  <MenuItem value="">Sin sucursal</MenuItem>
                  {branches.map((branch) => (
                    <MenuItem key={branch.id} value={String(branch.id)}>{branch.name}</MenuItem>
                  ))}
                </Select>
              </FormControl>
              <Typography variant="body2" color="text.secondary">
                Sube el archivo JSON exportado de Carnicuenta (hasta 50.000 registros).
              </Typography>
              <input type="file" accept="application/json,.json" onChange={(e) => setAccountFile(e.target.files?.[0] || null)} />
              <Box>
                <Button variant="contained" color="secondary" disabled={accountLoading} onClick={submitAccountUpload}>
                  {accountLoading ? 'Procesando...' : 'Subir cuentas corrientes'}
                </Button>
              </Box>
              {accountLoading && <LinearProgress />}
              {accountError && <Alert severity="error">{accountError}</Alert>}
            </Stack>
          </CardContent>
        </Card>
      </Stack>
    </Container>
  )
}
