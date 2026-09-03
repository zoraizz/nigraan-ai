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
    <div className="panel border-dashed p-6 text-center">
      {previewUrl ? (
        <img
          src={previewUrl}
          alt="Selected tile preview"
          className="mx-auto mb-4 max-h-64 rounded-panel border border-line object-contain"
        />
      ) : (
        <p className="mb-4 text-sm text-muted">
          No image selected yet. Choose a post-disaster satellite tile.
        </p>
      )}

      <input
        type="file"
        accept="image/*"
        onChange={onFileSelect}
        className="mx-auto block w-full max-w-xs text-sm text-muted file:mr-3 file:cursor-pointer file:rounded-chip file:border file:border-line-strong file:bg-transparent file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-text hover:file:bg-surface-hover"
      />

      <button
        type="button"
        onClick={onClassify}
        disabled={disabled || loading}
        className="btn btn-primary mt-4"
      >
        {loading ? 'Classifying…' : 'Classify damage'}
      </button>

      {fileName ? (
        <p className="data mt-3 truncate text-xs text-muted">{fileName}</p>
      ) : null}
    </div>
  )
}
