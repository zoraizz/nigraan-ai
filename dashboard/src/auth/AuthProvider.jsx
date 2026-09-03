import { createContext } from 'react'

// No-op passthrough for now. Real auth (e.g., NDMA/PDMA accounts) will be
// wired in here later — consumers already read this context via useAuth(),
// so swapping the implementation never touches pages or components.
export const AuthContext = createContext({ user: null, isAuthenticated: true })

export function AuthProvider({ children }) {
  return (
    <AuthContext.Provider value={{ user: null, isAuthenticated: true }}>
      {children}
    </AuthContext.Provider>
  )
}
