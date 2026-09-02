import { useState } from 'react'

// Image picker placeholder — selection only, no upload yet.
// TODO: on submit, call classify (from useDamageClassification) which posts
// to the Damage Checker.
export default function ImageUploadBox() {
  const [fileName, setFileName] = useState(null)

  return (
    <div className="rounded border border-dashed border-slate-300 bg-white p-6 text-center">
      <input
        type="file"
        accept="image/*"
        onChange={(event) => setFileName(event.target.files?.[0]?.name || null)}
        className="mx-auto block text-sm text-slate-500 file:mr-3 file:rounded file:border-0 file:bg-slate-800 file:px-4 file:py-2 file:text-sm file:text-white hover:file:bg-slate-700"
      />
      <p className="mt-3 text-xs text-slate-400">
        {fileName
          ? `Selected: ${fileName}`
          : 'No image selected yet — upload logic lands with the hooks.'}
      </p>
    </div>
  )
}
