import React, { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Container,
  Divider,
  IconButton,
  InputAdornment,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import VisibilityIcon from '@mui/icons-material/Visibility'
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff'
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline'

const featureList = [
  'Control financiero unificado',
  'Historial de ventas actualizado',
  'Protocolos de seguridad activos',
]

export default function LoginPage() {
  const { login, user, bootstrapping } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()
  const location = useLocation()
  const redirectPath = location.state?.from?.pathname || '/ventas'

  useEffect(() => {
    if (!bootstrapping && user) {
      navigate(redirectPath, { replace: true })
    }
  }, [bootstrapping, user, navigate, redirectPath])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(username.trim(), password)
      navigate(redirectPath, { replace: true })
    } catch (err) {
      setError(err.message || 'No se pudo iniciar sesión')
    } finally {
      setLoading(false)
    }
  }

  if (bootstrapping) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <CircularProgress />
      </Box>
    )
  }

  const logoUrl = new URL('favicon.svg', document.baseURI).href

  return (
    <Container maxWidth="md" sx={{ py: 10 }}>
      <Stack spacing={2} alignItems="center" textAlign="center" sx={{ mb: 4 }}>
        <Box
          component="img"
          src={logoUrl}
          alt="Viglianco ERP"
          sx={{
            width: 96,
            height: 96,
            filter: 'drop-shadow(0 20px 40px rgba(0,0,0,0.35))',
          }}
        />
        <Typography variant="h4" fontWeight={700}>Bienvenido a Viglianco:ERP</Typography>
        <Typography variant="body1" color="text.secondary">
          Gestioná la operación y finanzas internas con una experiencia renovada y segura.
        </Typography>
      </Stack>
      <Card
        sx={{
          overflow: 'hidden',
          backgroundColor: 'rgba(15,15,25,0.85)',
          border: '1px solid rgba(255,255,255,0.05)',
          boxShadow: '0 40px 80px rgba(0,0,0,0.35)',
        }}
      >
        <Stack direction={{ xs: 'column', md: 'row' }}>
          <Box
            sx={{
              flex: 1,
              p: { xs: 3, md: 4 },
              background: 'linear-gradient(165deg, rgba(120,140,255,0.45), rgba(15,18,40,0.9))',
              display: 'flex',
              flexDirection: 'column',
              gap: 2,
              justifyContent: 'center',
              color: 'rgba(255,255,255,0.95)',
            }}
          >
            <Typography variant="subtitle2" sx={{ letterSpacing: 2, textTransform: 'uppercase' }}>
              Operación segura
            </Typography>
            <Typography variant="h5" fontWeight={600}>Tus datos operativos en un solo lugar</Typography>
            <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.85)' }}>
              Autentificate para continuar con la administración y el seguimiento de la balanza,
              bancos y cuentas corrientes.
            </Typography>
            <Stack spacing={1.2}>
              {featureList.map((text) => (
                <Stack key={text} direction="row" spacing={1} alignItems="center">
                  <CheckCircleOutlineIcon fontSize="small" sx={{ color: '#9ad0ff' }} />
                  <Typography variant="body2">{text}</Typography>
                </Stack>
              ))}
            </Stack>
          </Box>
          <Divider
            orientation="vertical"
            flexItem
            sx={{ borderColor: 'rgba(255,255,255,0.04)', display: { xs: 'none', md: 'block' } }}
          />
          <CardContent sx={{ flex: 1 }}>
            <Stack spacing={2.5} component="form" onSubmit={handleSubmit} sx={{ maxWidth: 420, mx: 'auto', py: 1 }}>
              <Typography variant="h5" fontWeight={600}>Ingresar</Typography>
              <Typography variant="body2" color="text.secondary">
                Ingresá con tu usuario interno. La sesión se mantiene activa y sólo se cerrará si salís manualmente
                o si pasan 24 horas sin actividad.
              </Typography>
              {error && <Alert severity="error">{error}</Alert>}
              <TextField
                label="Usuario"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
                fullWidth
              />
              <TextField
                label="Contraseña"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                fullWidth
                sx={{
                  '& input::-ms-reveal': { display: 'none' },
                  '& input::-ms-clear': { display: 'none' },
                }}
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton
                        aria-label="Mostrar contraseña"
                        onClick={() => setShowPassword((prev) => !prev)}
                        edge="end"
                      >
                        {showPassword ? <VisibilityOffIcon /> : <VisibilityIcon />}
                      </IconButton>
                    </InputAdornment>
                  ),
                }}
              />
              <Button type="submit" variant="contained" size="large" disabled={loading} sx={{ py: 1.3 }}>
                {loading ? 'Ingresando...' : 'Ingresar'}
              </Button>
            </Stack>
          </CardContent>
        </Stack>
      </Card>
    </Container>
  )
}
