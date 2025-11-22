import React, { useState, useEffect } from 'react'
import { AppBar, Toolbar, Typography, Box, CssBaseline, Button, Stack, CircularProgress, IconButton, Fade, Backdrop, Container, Fab, Zoom } from '@mui/material'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import { Routes, Route, Link, useLocation, useNavigate, Navigate } from 'react-router-dom'
import UploadPage from './pages/Upload.jsx'
import StatsPage from './pages/Stats.jsx'
import BankStatsPage from './pages/BankStats.jsx'
import AccountsPage from './pages/Accounts.jsx'
import LoginPage from './pages/Login.jsx'
import SalesBoard from './pages/SalesBoard.jsx'
import ExpensesBoard from './pages/ExpensesBoard.jsx'
import { AuthProvider, useAuth } from './context/AuthContext.jsx'
import MenuIcon from '@mui/icons-material/Menu'
import CloseIcon from '@mui/icons-material/Close'
import KeyboardArrowUpIcon from '@mui/icons-material/KeyboardArrowUp'

const darkTheme = createTheme({ palette: { mode: 'dark' } })

function Background() {
  return (
    <Box sx={{ position: 'fixed', inset: 0, zIndex: -2, backgroundColor: '#0a0a0a', backgroundImage: 'radial-gradient(ellipse 80% 80% at 50% -20%, rgba(120,119,198,0.3), rgba(255,255,255,0))' }} />
  )
}

function Nav() {
  const location = useLocation()
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  if (!user) return null
  const isActive = (path) => location.pathname === path

  const navButtons = [
    { to: '/', label: 'Cargar' },
    { to: '/balanza', label: 'Balanza' },
    { to: '/ventas', label: 'Ventas' },
    { to: '/gastos', label: 'Gastos' },
    { to: '/bancos', label: 'Bancos' },
    { to: '/cuentas', label: 'Cuenta corriente' },
  ]

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
    setMobileMenuOpen(false)
  }

  const renderButton = ({ to, label }) => (
    <Button
      key={to}
      component={Link}
      to={to}
      variant={isActive(to) ? 'contained' : 'outlined'}
      color={isActive(to) ? 'primary' : 'inherit'}
      sx={{ borderRadius: { xs: 2, md: 999 }, textTransform: 'none', px: 2 }}
      onClick={() => setMobileMenuOpen(false)}
    >
      {label}
    </Button>
  )

  return (
    <>
      <AppBar position="static" color="transparent" elevation={0} sx={{ backdropFilter: 'blur(6px)', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
        <Toolbar>
          <Typography variant="h6" sx={{ flexGrow: 1, fontWeight: 700 }}>Viglianco ERP</Typography>
          <Stack direction="row" spacing={1} sx={{ display: { xs: 'none', md: 'flex' } }}>
            {navButtons.map(renderButton)}
            <Button onClick={handleLogout} variant="text" color="inherit" sx={{ textTransform: 'none' }}>
              Cerrar sesión
            </Button>
          </Stack>
          <IconButton
            color="inherit"
            onClick={() => setMobileMenuOpen((prev) => !prev)}
            sx={{ display: { xs: 'inline-flex', md: 'none' } }}
            aria-label="Abrir menú"
          >
            {mobileMenuOpen ? <CloseIcon /> : <MenuIcon />}
          </IconButton>
        </Toolbar>
      </AppBar>
      <Backdrop
        open={mobileMenuOpen}
        onClick={() => setMobileMenuOpen(false)}
        sx={{ display: { xs: 'flex', md: 'none' }, zIndex: 1200, backgroundColor: 'rgba(0,0,0,0.4)' }}
      />
      <Fade in={mobileMenuOpen} unmountOnExit>
        <Box
          sx={{
            position: 'fixed',
            top: 70,
            left: 16,
            right: 16,
            display: { xs: 'flex', md: 'none' },
            flexDirection: 'column',
            gap: 1,
            p: 2,
            borderRadius: 3,
            zIndex: 1300,
            background: 'linear-gradient(135deg, rgba(20,20,30,0.95), rgba(35,35,55,0.9))',
            border: '1px solid rgba(255,255,255,0.08)',
            boxShadow: '0 25px 70px rgba(0,0,0,0.45)',
            backdropFilter: 'blur(10px)',
            transformOrigin: 'top right',
          }}
        >
          {navButtons.map(renderButton)}
          <Button onClick={handleLogout} variant="contained" color="error" sx={{ textTransform: 'none' }}>
            Cerrar sesión
          </Button>
        </Box>
      </Fade>
    </>
  )
}

function Footer() {
  return (
    <Box component="footer" sx={{ borderTop: '1px solid rgba(255,255,255,0.08)', px: 2, py: 4, backgroundColor: 'rgba(2,2,8,0.85)', mt: 'auto' }}>
      <Container maxWidth="lg">
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={4} justifyContent="space-between">
          <Stack spacing={1}>
            <Typography variant="h6" fontWeight={700}>Viglianco:ERP</Typography>
            <Typography variant="body2" color="text.secondary">
              Plataforma interna para control operativo, ventas, gastos y cuentas corrientes.
            </Typography>
            <Typography variant="caption" color="text.secondary">© {new Date().getFullYear()} Viglianco. Todos los derechos reservados.</Typography>
          </Stack>
          <Stack spacing={1} direction={{ xs: 'column', sm: 'row' }} flexWrap="wrap" rowGap={1} columnGap={3} sx={{ display: { xs: 'none', sm: 'flex' } }}>
            {[
              { to: '/', label: 'Cargar' },
              { to: '/balanza', label: 'Balanza' },
              { to: '/ventas', label: 'Ventas' },
              { to: '/gastos', label: 'Gastos' },
              { to: '/bancos', label: 'Bancos' },
              { to: '/cuentas', label: 'Cuenta corriente' },
            ].map((item) => (
              <Button key={item.to} component={Link} to={item.to} color="inherit" sx={{ textTransform: 'none', px: 0 }}>
                {item.label}
              </Button>
            ))}
          </Stack>
          <Stack spacing={0.5}>
            <Typography variant="subtitle2" color="text.secondary">Contacto interno</Typography>
            <Typography variant="body2">matiasviglisnco@gmail.com</Typography>
            <Typography variant="body2">+54 3584 438810</Typography>
          </Stack>
        </Stack>
      </Container>
    </Box>
  )
}

function ScrollTopButton() {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const handleScroll = () => {
      setVisible(window.scrollY > 250)
    }
    handleScroll()
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  const goTop = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <Zoom in={visible}>
      <Fab
        color="primary"
        size="medium"
        onClick={goTop}
        aria-label="Volver arriba"
        sx={{
          position: 'fixed',
          bottom: { xs: 24, md: 32 },
          right: { xs: 20, md: 32 },
          boxShadow: '0 15px 30px rgba(0,0,0,0.35)',
          zIndex: 1300,
        }}
      >
        <KeyboardArrowUpIcon />
      </Fab>
    </Zoom>
  )
}
function ProtectedRoute({ children }) {
  const { user, bootstrapping } = useAuth()
  const location = useLocation()

  if (bootstrapping) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
        <CircularProgress />
      </Box>
    )
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return children
}

function AppRoutes() {
  return (
    <>
      <Nav />
      <Box component="main" sx={{ width: '100%', px: { xs: 2, md: 4 }, py: 2, minHeight: 'calc(100vh - 64px)' }}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/"
            element={(
              <ProtectedRoute>
                <UploadPage />
              </ProtectedRoute>
            )}
          />
          <Route
            path="/balanza"
            element={(
              <ProtectedRoute>
                <StatsPage />
              </ProtectedRoute>
            )}
          />
          <Route
            path="/stats"
            element={(
              <ProtectedRoute>
                <StatsPage />
              </ProtectedRoute>
            )}
          />
          <Route
            path="/ventas"
            element={(
              <ProtectedRoute>
                <SalesBoard />
              </ProtectedRoute>
            )}
          />
          <Route
            path="/gastos"
            element={(
              <ProtectedRoute>
                <ExpensesBoard />
              </ProtectedRoute>
            )}
          />
          <Route
            path="/bancos"
            element={(
              <ProtectedRoute>
                <BankStatsPage />
              </ProtectedRoute>
            )}
          />
          <Route
            path="/cuentas"
            element={(
              <ProtectedRoute>
                <AccountsPage />
              </ProtectedRoute>
            )}
          />
        </Routes>
      </Box>
      <Footer />
      <ScrollTopButton />
    </>
  )
}

export default function App() {
  return (
    <ThemeProvider theme={darkTheme}>
      <CssBaseline />
      <Background />
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </ThemeProvider>
  )
}





