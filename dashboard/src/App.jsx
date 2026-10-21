import { useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/layout/Sidebar.jsx'
import Header from './components/layout/Header.jsx'
import ProtectedRoute from './auth/ProtectedRoute.jsx'
import Landing from './pages/Landing.jsx'
import Overview from './pages/Overview.jsx'
import RiskMap from './pages/RiskMap.jsx'
import DamageAssessment from './pages/DamageAssessment.jsx'
import AidPriority from './pages/AidPriority.jsx'
import FloodTracker from './pages/FloodTracker.jsx'
import { SceneDamageProvider } from './scene/SceneDamageProvider.jsx'

// Console shell: persistent sidebar rail + header around the 4 console pages.
function ConsoleShell() {
  const [isCollapsed, setIsCollapsed] = useState(false)

  const toggleSidebar = () => setIsCollapsed((prev) => !prev)

  return (
    <div className="flex min-h-screen bg-[#030b06] text-slate-100">
      <Sidebar isCollapsed={isCollapsed} toggleSidebar={toggleSidebar} />
      <div className="flex min-h-screen min-w-0 flex-1 flex-col transition-all duration-300">
        <Header isCollapsed={isCollapsed} toggleSidebar={toggleSidebar} />
        <main className="flex-1 overflow-x-hidden p-4 lg:p-6">
          <Routes>
            <Route
              path="/overview"
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
            {/* flood: River Flood Tracker */}
            <Route
              path="/flood-tracker"
              element={
                <ProtectedRoute>
                  <FloodTracker />
                </ProtectedRoute>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

// Top level: the public landing page at "/" (no sidebar), everything else
// inside the console shell.
export default function App() {
  return (
    <SceneDamageProvider>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/*" element={<ConsoleShell />} />
      </Routes>
    </SceneDamageProvider>
  )
}

