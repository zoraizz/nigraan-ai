import React from 'react'

/**
 * NigraanLogo — matches the official wordmark:
 *   Icon: green crescent arc + white dot (eye/sentinel mark)
 *   Text: "NIGRAAN AI" — wide-tracked, bold, all-caps white
 */
export default function Logo({ size = 'md', className = '', showText = true }) {
  // Scale: sm = sidebar collapsed, md = sidebar open, lg = hero
  const iconH = size === 'sm' ? 28 : size === 'lg' ? 44 : 34
  const textCls =
    size === 'sm'
      ? 'text-[13px] tracking-[0.18em]'
      : size === 'lg'
      ? 'text-[22px] tracking-[0.2em]'
      : 'text-[15px] tracking-[0.18em]'

  return (
    <div className={`inline-flex items-center gap-2.5 select-none ${className}`}>
      {/* ── Icon Mark ── */}
      <svg
        width={iconH}
        height={iconH}
        viewBox="0 0 40 40"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
        style={{ flexShrink: 0 }}
      >
        {/* Green crescent / bowl arc */}
        <path
          d="M6 26 C6 14 34 14 34 26"
          stroke="#3ddc84"
          strokeWidth="4"
          strokeLinecap="round"
          fill="none"
        />
        {/* White sentinel dot sitting on the arc apex */}
        <circle cx="20" cy="15" r="5.5" fill="white" />
      </svg>

      {/* ── Wordmark ── */}
      {showText && (
        <span
          className={`font-bold uppercase leading-none text-white ${textCls}`}
          style={{ fontFamily: "'Public Sans', system-ui, sans-serif", letterSpacing: '0.18em' }}
        >
          NIGRAAN AI
        </span>
      )}
    </div>
  )
}
