import { useContext } from 'react'
import { AuthContext } from './AuthProvider.jsx'

// Placeholder: everyone is authenticated with no user until real auth lands.
// Also carries the Ground Reports role:
//   { role: 'public' | 'officer', isOfficer, officerPin, notice,
//     enterOfficerMode(pin) -> Promise<{ ok, error? }>, exitOfficerMode(), clearNotice() }
// The context default means this also works outside a provider.
export function useAuth() {
  return useContext(AuthContext)
}
