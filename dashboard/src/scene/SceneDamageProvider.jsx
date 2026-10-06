import { createContext, useCallback, useContext, useMemo, useState } from 'react'

// Scene damage chosen on Damage Assessment and read by Aid Priority.
// Shape: { district, damage_breakdown: {none, partial, destroyed}, tile_count, truncated } | null
const SceneDamageContext = createContext(null)

export function SceneDamageProvider({ children }) {
  const [sceneDamage, setSceneDamage] = useState(null)
  const clearSceneDamage = useCallback(() => setSceneDamage(null), [])
  const value = useMemo(
    () => ({ sceneDamage, setSceneDamage, clearSceneDamage }),
    [sceneDamage, clearSceneDamage],
  )
  return (
    <SceneDamageContext.Provider value={value}>
      {children}
    </SceneDamageContext.Provider>
  )
}

export function useSceneDamage() {
  const value = useContext(SceneDamageContext)
  if (!value) {
    throw new Error('useSceneDamage must be used within SceneDamageProvider')
  }
  return value
}
