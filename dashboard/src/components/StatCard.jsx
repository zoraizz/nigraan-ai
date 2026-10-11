import React from 'react'

export default function StatCard({
  value,
  label,
  accentColor = 'emerald', // emerald, rose, cyan, amber
  subtext,
}) {
  const accentStyles = {
    emerald: 'text-emerald-400 drop-shadow-[0_0_8px_rgba(52,211,153,0.3)]',
    rose: 'text-rose-400 drop-shadow-[0_0_8px_rgba(251,113,133,0.3)]',
    cyan: 'text-cyan-400 drop-shadow-[0_0_8px_rgba(34,211,238,0.3)]',
    amber: 'text-amber-400 drop-shadow-[0_0_8px_rgba(251,191,36,0.3)]',
    blue: 'text-blue-400 drop-shadow-[0_0_8px_rgba(96,165,250,0.3)]',
  }

  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-[#1b4a33]/80 bg-[#0a2418]/80 p-3 text-center transition-all hover:bg-[#0e2d18] hover:border-[#1b4a33]/80">
      <div className={`font-heading text-2xl font-extrabold tracking-tight ${accentStyles[accentColor] || accentStyles.emerald}`}>
        {value}
      </div>
      <div className="mt-0.5 text-xs font-semibold text-slate-300">{label}</div>
      {subtext && <div className="text-[10px] text-[#6f8f7e] mt-0.5">{subtext}</div>}
    </div>
  )
}
