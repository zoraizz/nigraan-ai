// Shared page wrapper — consistent padding and optional title.
export default function PageContainer({ title, children }) {
  return (
    <div className="p-6">
      {title ? (
        <h2 className="mb-4 text-xl font-semibold text-slate-800">{title}</h2>
      ) : null}
      {children}
    </div>
  )
}
