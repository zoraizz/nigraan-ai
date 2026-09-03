import { Routes, Route } from 'react-router-dom'
import Sidebar from './components/layout/Sidebar.jsx'
import Header from './components/layout/Header.jsx'
import ProtectedRoute from './auth/ProtectedRoute.jsx'
import Overview from './pages/Overview.jsx'
import RiskMap from './pages/RiskMap.jsx'
import DamageAssessment from './pages/DamageAssessment.jsx'
import AidPriority from './pages/AidPriority.jsx'

// Router + layout shell: sidebar nav between the 4 pages.
// Page content is placeholder for now — see src/pages/.
export default function App() {
  return (
    <div className="flex min-h-screen bg-slate-100">
      <Sidebar />
      <div className="flex min-h-screen flex-1 flex-col">
        <Header />
        <main className="flex-1">
          <Routes>
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <Overview />
                </ProtectedRoute>
              }
            />
            <Route
              path="/risk-map"
              element={
                <ProtectedRoute>
                  <RiskMap />
                </ProtectedRoute>
              }
            />
            <Route
              path="/damage-assessment"
              element={
                <ProtectedRoute>
                  <DamageAssessment />
                </ProtectedRoute>
              }
            />
            <Route
              path="/aid-priority"
              element={
                <ProtectedRoute>
                  <AidPriority />
                </ProtectedRoute>
              }
            />
          </Routes>
        </main>
      </div>
    </div>
  )
}
