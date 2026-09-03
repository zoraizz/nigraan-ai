// Image picker + classify trigger for the Damage Assessment page.
// Stateless: the page owns the file and calls the hook.
export default function ImageUploadBox({
  previewUrl,
  fileName,
  onFileSelect,
  onClassify,
  loading = false,
  disabled = false,
}) {
  return (
    <div className="rounded border border-dashed border-slate-300 bg-white p-6 text-center">
      {previewUrl ? (
        <img
          src={previewUrl}
          alt="Selected tile preview"
          className="mx-auto mb-4 max-h-64 rounded border border-slate-200 object-contain"
        />
      ) : (
        <p className="mb-4 text-sm text-slate-400">
          No image selected yet — choose a post-disaster satellite tile.
        </p>
      )}

      <input
        type="file"
        accept="image/*"
        onChange={onFileSelect}
        className="mx-auto block text-sm text-slate-500 file:mr-3 file:rounded file:border-0 file:bg-slate-800 file:px-4 file:py-2 file:text-sm file:text-white hover:file:bg-slate-700"
      />

      <button
        type="button"
        onClick={onClassify}
        disabled={disabled || loading}
        className="mt-4 rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
      >
        {loading ? 'Classifying…' : 'Classify damage'}
      </button>

      {fileName ? (
        <p className="mt-3 text-xs text-slate-400">Selected: {fileName}</p>
      ) : null}
    </div>
  )
}
