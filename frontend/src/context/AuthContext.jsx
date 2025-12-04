import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { API_BASE } from '../config'
const ACCESS_STORAGE_KEY = 'kretz_access_token'
const USER_STORAGE_KEY = 'kretz_user'
const INACTIVITY_LIMIT_MS = null // sin cierre automático por inactividad
const REFRESH_FLAG_KEY = 'kretz_has_refresh'

const AuthContext = createContext(null)

const buildAuthHeader = (token, headers = {}) => {
  const next = new Headers(headers)
  if (token) {
    next.set('Authorization', `Bearer ${token}`)
  }
  return next
}

const getStorage = () => (typeof window !== 'undefined' ? window.localStorage : null)

const readStoredToken = () => {
  const storage = getStorage()
  if (!storage) return null
  return storage.getItem(ACCESS_STORAGE_KEY)
}

const readStoredUser = () => {
  const storage = getStorage()
  if (!storage) return null
  const raw = storage.getItem(USER_STORAGE_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch (_) {
    return null
  }
}

const persistToken = (token) => {
  const storage = getStorage()
  if (!storage) return
  if (token) storage.setItem(ACCESS_STORAGE_KEY, token)
  else storage.removeItem(ACCESS_STORAGE_KEY)
}

const persistUser = (data) => {
  const storage = getStorage()
  if (!storage) return
  if (data) storage.setItem(USER_STORAGE_KEY, JSON.stringify(data))
  else storage.removeItem(USER_STORAGE_KEY)
}

const readRefreshFlag = () => {
  const storage = getStorage()
  if (!storage) return false
  return storage.getItem(REFRESH_FLAG_KEY) === '1'
}

const persistRefreshFlag = (value) => {
  const storage = getStorage()
  if (!storage) return
  if (value) storage.setItem(REFRESH_FLAG_KEY, '1')
  else storage.removeItem(REFRESH_FLAG_KEY)
}

export function AuthProvider({ children }) {
  const [accessToken, setAccessTokenState] = useState(() => readStoredToken())
  const [user, setUserState] = useState(() => readStoredUser())
  const [bootstrapping, setBootstrapping] = useState(true)
  const [hasRefreshFlag, setHasRefreshFlag] = useState(() => readRefreshFlag())
  const inactivityTimer = useRef(null)
  const manualLogoutRef = useRef(false)

  const setAccessToken = useCallback((token) => {
    setAccessTokenState(token)
    persistToken(token)
  }, [])

  const setUser = useCallback((data) => {
    setUserState(data)
    persistUser(data)
  }, [])

  const setRefreshFlag = useCallback((value) => {
    setHasRefreshFlag(value)
    persistRefreshFlag(value)
  }, [])

  const logout = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/auth/logout/`, {
        method: 'POST',
        credentials: 'include',
      })
    } catch (err) {
      console.error(err)
    } finally {
      manualLogoutRef.current = true
      setAccessToken(null)
      setRefreshFlag(false)
      setUser(null)
      if (inactivityTimer.current) {
        clearTimeout(inactivityTimer.current)
        inactivityTimer.current = null
      }
    }
  }, [setAccessToken, setUser, setRefreshFlag])

  const resetInactivityTimeout = useCallback((_tokenOverride) => {
    // Deshabilitado el auto-logout por inactividad
    if (inactivityTimer.current) {
      clearTimeout(inactivityTimer.current)
      inactivityTimer.current = null
    }
    return
  }, [])

  const fetchProfile = useCallback(async (token) => {
    if (!token) return null
    const resp = await fetch(`${API_BASE}/auth/me/`, {
      headers: buildAuthHeader(token),
      credentials: 'include',
    })
    if (!resp.ok) {
      return null
    }
    return resp.json()
  }, [])

  const refreshAccess = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/auth/refresh/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({}),
      })
      if (!resp.ok) {
        return false
      }
      const data = await resp.json()
      const token = data.access
      if (!token) {
        return false
      }
      setAccessToken(token)
      setRefreshFlag(true)
      resetInactivityTimeout(token)
      if (data.user) {
        setUser(data.user)
      } else {
        const profile = await fetchProfile(token)
        if (profile) {
          setUser(profile)
        }
      }
      return true
    } catch (err) {
      console.error(err)
      return false
    }
  }, [fetchProfile, resetInactivityTimeout, setRefreshFlag])

  useEffect(() => {
    let mounted = true
    ;(async () => {
      if (accessToken) {
        const profile = await fetchProfile(accessToken)
        if (!mounted) return
        if (profile) {
          setUser(profile)
          setBootstrapping(false)
          return
        }
        // Token inválido, limpiar y continuar con flujo normal
        setAccessToken(null)
        setUser(null)
        setRefreshFlag(false)
        if (mounted) {
          setBootstrapping(false)
        }
        return
      }
      if (manualLogoutRef.current) {
        manualLogoutRef.current = false
        if (mounted) {
          setBootstrapping(false)
        }
        return
      }
      if (!hasRefreshFlag) {
        if (mounted) {
          setBootstrapping(false)
        }
        return
      }
      const ok = await refreshAccess()
      if (!mounted) return
      if (!ok) {
        setAccessToken(null)
        setUser(null)
        setRefreshFlag(false)
      }
      setBootstrapping(false)
    })()
    return () => {
      mounted = false
    }
  }, [accessToken, fetchProfile, refreshAccess, setAccessToken, setUser, hasRefreshFlag])

  const login = useCallback(async (username, password) => {
    const resp = await fetch(`${API_BASE}/auth/login/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ username, password }),
    })
    const data = await resp.json().catch(() => ({}))
    if (!resp.ok) {
      throw new Error(data.detail || 'Credenciales inválidas')
    }
    if (!data.access) {
      throw new Error('Respuesta inválida del servidor')
    }
    setAccessToken(data.access)
    setRefreshFlag(true)
    setUser(data.user || null)
    resetInactivityTimeout(data.access)
    return data
  }, [resetInactivityTimeout, setAccessToken, setUser, setRefreshFlag])

  const authFetch = useCallback(async (url, options = {}, retry = true) => {
    const headers = buildAuthHeader(accessToken, options.headers)
    const response = await fetch(url, { ...options, headers, credentials: 'include' })
    resetInactivityTimeout()
    if (response.status === 401 && retry) {
      if (!hasRefreshFlag) {
        await logout()
        return response
      }
      const refreshed = await refreshAccess()
      if (!refreshed) {
        await logout()
        return response
      }
      return authFetch(url, options, false)
    }
    return response
  }, [accessToken, refreshAccess, logout, hasRefreshFlag, resetInactivityTimeout])

  const value = useMemo(() => ({
    user,
    accessToken,
    bootstrapping,
    login,
    logout,
    authFetch,
  }), [user, accessToken, bootstrapping, login, logout, authFetch])

  useEffect(() => {
    if (!accessToken) {
      if (inactivityTimer.current) {
        clearTimeout(inactivityTimer.current)
        inactivityTimer.current = null
      }
      return
    }
    const handler = () => resetInactivityTimeout()
    resetInactivityTimeout(accessToken)
    const events = ['mousemove', 'keydown', 'click', 'touchstart']
    events.forEach((evt) => window.addEventListener(evt, handler))
    return () => {
      events.forEach((evt) => window.removeEventListener(evt, handler))
      if (inactivityTimer.current) {
        clearTimeout(inactivityTimer.current)
        inactivityTimer.current = null
      }
    }
  }, [accessToken, resetInactivityTimeout])

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth debe usarse dentro de AuthProvider')
  }
  return ctx
}
