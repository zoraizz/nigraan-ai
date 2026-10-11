import React from 'react'
import { Link } from 'react-router-dom'

export default function HeroCard({
  title,
  value,
  subtitle,
  badgeText,
  badgeColor = 'red', // red, orange, yellow, emerald, blue, cyan
  icon: Icon,
  iconBg = 'bg-rose-500/10 text-rose-400 border-rose-500/20',
  actionLink,
  actionText,
}) {
  const badgeStyles = {
    red: 'bg-rose-500/15 text-rose-400 border-rose-500/30',
    orange: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    yellow: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
    emerald: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    blue: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
    cyan: 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30',
  }

  return (
    <div className="group relative flex flex-col justify-between rounded-xl border border-[#1b4a33]/80 bg-[#0a2418]/90 p-4 transition-all hover:border-[#1b4a33]/80 hover:shadow-lg hover:shadow-black/40">
      {/* Top Header Row */}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
          {Icon && (
            <div
              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border ${iconBg}`}
            >
              <Icon className="h-5 w-5" />
            </div>
          )}
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            {title}
          </span>
        </div>

        {badgeText && (
          <span
            className={`inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[10px] font-medium tracking-wide ${
              badgeStyles[badgeColor] || badgeStyles.emerald
            }`}
          >
            {badgeText}
          </span>
        )}
      </div>

      {/* Primary Metric / Value */}
      <div className="my-1">
        <div className="font-heading text-2xl font-extrabold tracking-tight text-white group-hover:text-emerald-400 transition-colors">
          {value}
        </div>
        {subtitle && <p className="mt-1 text-xs text-slate-400 leading-snug">{subtitle}</p>}
      </div>

      {/* Action Footer link if provided */}
      {actionLink && (
        <div className="mt-3 pt-2.5 border-t border-[#1b4a33]/60 flex items-center justify-between">
          <Link
            to={actionLink}
            className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-400 hover:text-emerald-300 transition-colors"
          >
            <span>{actionText || 'View Details'}</span>
            <svg
              className="h-3.5 w-3.5"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fillRule="evenodd"
                d="M7.21 14.77a.75.75 0 01.02-1.06L11.16 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
                clipRule="evenodd"
              />
            </svg>
          </Link>
        </div>
      )}
    </div>
  )
}
