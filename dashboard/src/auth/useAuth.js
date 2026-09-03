import { useContext } from 'react'
import { AuthContext } from './AuthProvider.jsx'

// Placeholder — everyone is authenticated with no user until real auth lands.
// The context default means this also works outside a provider.
export function useAuth() {
  return useContext(AuthContext)
}
