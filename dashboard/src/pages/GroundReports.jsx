import { useState } from 'react'
import PageContainer from '../components/layout/PageContainer.jsx'
import GroundUploadForm from '../components/ground/GroundUploadForm.jsx'
import GroundReportCard from '../components/ground/GroundReportCard.jsx'
import ReviewActions from '../components/ground/ReviewActions.jsx'
import UrgentBanner from '../components/ground/UrgentBanner.jsx'
import DistrictGroundSummary from '../components/ground/DistrictGroundSummary.jsx'
import { DISTRICTS } from '../config/districts.js'
import { useGroundReports } from '../hooks/useGroundReports.js'

export default function GroundReports() {
  const [district, setDistrict] = useState('')
  const { reports, summary, loading, error, refetch } = useGroundReports({ district })
  // Use the service's open-urgent definition; counts never feed a score here.
  const urgentCount = Object.values(summary?.districts ?? {}).reduce((sum, row) => sum + (row.urgent_open ?? 0), 0)
  return <PageContainer title="Ground Reports" lead="Ground-level disaster photos, structured observations, and officer review for local response.">
    <div className="space-y-5">
      <GroundUploadForm refetch={refetch} />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <label className="text-xs text-muted">Filter reports and district summary<select className="field mt-1" value={district} onChange={(event) => setDistrict(event.target.value)}><option value="">All districts</option>{DISTRICTS.map(({ name }) => <option key={name}>{name}</option>)}</select></label>
        <button type="button" className="btn" onClick={refetch} disabled={loading}>Refresh reports</button>
      </div>
      {loading ? <div className="panel p-6 text-center" role="status"><div className="spinner mx-auto mb-3" /><p className="text-sm text-muted">Loading ground reports…</p></div> : error ? <div className="alert-error p-4 text-sm" role="alert"><p className="font-semibold">{error.status === 0 ? 'Damage Checker is not reachable' : 'Ground reports request failed'}</p><p className="mt-1">{error.message}</p><button type="button" className="btn mt-3" onClick={refetch}>Try again</button></div> : <>
        <UrgentBanner count={urgentCount} />
        <section aria-labelledby="ground-queue-title" className="space-y-4">
          <div><h2 id="ground-queue-title" className="font-heading text-lg font-semibold text-text">Review queue</h2><p className="mt-1 text-sm text-muted">{reports.filter((report) => report.status === 'unverified').length} awaiting review · Similar photos are folded into one report.</p></div>
          {reports.length ? reports.map((report) => <GroundReportCard key={report.id} report={report}><ReviewActions report={report} refetch={refetch} /></GroundReportCard>) : <p className="panel p-5 text-sm text-muted">No reports{district ? ` for ${district}` : ''} yet. Submit a photo to get started.</p>}
        </section>
        <DistrictGroundSummary summary={summary} />
      </>}
    </div>
  </PageContainer>
}
