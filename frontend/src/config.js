const API_BASE =
  import.meta.env.VITE_API_BASE_URL ||
  (window.location.hostname === 'localhost'
    ? 'http://localhost:8000/api'
    : 'https://api.mativiglianco.online/api')

export { API_BASE }
