import { useEffect, useState } from 'react'
import { API_BASE } from '../config'

const API_BRANCHES = `${API_BASE}/branches/`

export default function useBranches(authFetch) {
  const [branches, setBranches] = useState([])
  const [branchesLoading, setBranchesLoading] = useState(false)
  const [branchesError, setBranchesError] = useState('')

  useEffect(() => {
    let active = true
    const loadBranches = async () => {
      setBranchesLoading(true)
      setBranchesError('')
      try {
        const resp = await authFetch(API_BRANCHES)
        const data = await resp.json().catch(() => [])
        if (!resp.ok) throw new Error(data?.detail || 'No se pudieron cargar las sucursales.')
        if (active) setBranches(Array.isArray(data) ? data : [])
      } catch (err) {
        if (active) setBranchesError(err.message || 'No se pudieron cargar las sucursales.')
      } finally {
        if (active) setBranchesLoading(false)
      }
    }
    loadBranches()
    return () => { active = false }
  }, [authFetch])

  return { branches, branchesLoading, branchesError }
}
