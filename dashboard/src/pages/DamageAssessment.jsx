import PageContainer from '../components/layout/PageContainer.jsx'
import ImageUploadBox from '../components/ImageUploadBox.jsx'
import DamageResultCard from '../components/DamageResultCard.jsx'

// Image upload + classification result placeholder.
// TODO: wire useDamageClassification to call the Damage Checker on submit.
export default function DamageAssessment() {
  return (
    <PageContainer title="Damage Assessment">
      <p className="mb-6 text-sm text-slate-500">
        Placeholder — upload a post-disaster satellite image to classify its
        damage severity.
      </p>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <ImageUploadBox />
        <DamageResultCard result={null} />
      </div>
    </PageContainer>
  )
}
