import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, ApiError } from '../lib/api'
import type { RegisterPayload, RegisterResult, User } from '../lib/types'

interface AuthState {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<User>
  register: (data: RegisterPayload) => Promise<RegisterResult>
  logout: () => Promise<void>
  refresh: () => Promise<User | null>
  setUser: (u: User | null) => void
}

const Ctx = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const u = await api.me()
      setUser(u)
      return u
    } catch (e) {
      if (!(e instanceof ApiError) || e.status !== 401) console.error(e)
      setUser(null)
      return null
    }
  }, [])

  useEffect(() => {
    refresh().finally(() => setLoading(false))
  }, [refresh])

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      refresh,
      setUser,
      login: async (email, password) => {
        const u = await api.login(email, password)
        setUser(u)
        return u
      },
      register: async (data) => {
        const result = await api.register(data)
        if (result.user) setUser(result.user)
        return result
      },
      logout: async () => {
        await api.logout()
        setUser(null)
      },
    }),
    [user, loading, refresh],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAuth must be used inside <AuthProvider>')
  return v
}

/** Where a signed-in user should land, based on server-computed state. */
export function homeFor(u: User): string {
  if (u.role === 'reviewer') return '/reviewer'
  if (u.role === 'doctor') return '/doctor'
  if (!u.consent_accepted) return '/consent'
  if (u.checkin.prompt) return '/check-in'
  return '/'
}
