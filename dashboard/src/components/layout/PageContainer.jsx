// Shared page wrapper — consistent padding, page title, and lead sentence.
export default function PageContainer({ title, lead, children }) {
  return (
    <div className="mx-auto w-full max-w-[1400px] px-4 py-6 lg:px-8 lg:py-8">
      {title ? (
        <div className="mb-6">
          <h2 className="font-heading text-2xl font-bold tracking-tight text-text">{title}</h2>
          {lead ? (
            <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-muted">{lead}</p>
          ) : null}
        </div>
      ) : null}
      {children}
    </div>
  )
}
