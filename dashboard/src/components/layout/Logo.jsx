import React from 'react'

/**
 * Modern Logo component for Nigraan AI.
 * Features an emerald-cyan satellite radar emblem + crisp typography.
 */
export default function Logo({ size = 'md', className = '' }) {
  const isSm = size === 'sm'
  const isLg = size === 'lg'

  const iconSize = isSm ? 'h-7 w-7' : isLg ? 'h-10 w-10' : 'h-8 w-8'
  const textSize = isSm ? 'text-sm' : isLg ? 'text-xl' : 'text-base'

  return (
    <div className={`inline-flex items-center gap-2.5 ${className}`}>
      {/* Emblem */}
      <div className={`relative flex ${iconSize} shrink-0 items-center justify-center`}>
        {/* Outer ambient glow */}
        <div className="absolute inset-0 rounded-lg bg-emerald-500/20 blur-sm" />
        
        {/* Vector Emblem */}
        <svg
          viewBox="0 0 36 36"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="relative h-full w-full drop-shadow-[0_0_8px_rgba(61,220,132,0.4)]"
        >
          {/* Hexagon Shield Frame */}
          <polygon
            points="18,2 32,9 32,27 18,34 4,27 4,9"
            fill="url(#logo-grad-bg)"
            stroke="url(#logo-grad-stroke)"
            strokeWidth="1.8"
            strokeLinejoin="round"
          />
          {/* Radar Sweep Arc */}
          <circle
            cx="18"
            cy="18"
            r="10"
            stroke="#3ddc84"
            strokeWidth="1"
            strokeDasharray="2 4"
            opacity="0.6"
          />
          {/* Stylized 'N' AI Core Node */}
          <path
            d="M12 24V12L24 24V12"
            stroke="#ffffff"
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {/* Active AI Radar Dot */}
          <circle cx="24" cy="12" r="2" fill="#3ddc84" />

          {/* Gradients */}
          <defs>
            <linearGradient id="logo-grad-bg" x1="4" y1="2" x2="32" y2="34" gradientUnits="userSpaceOnUse">
              <stop stopColor="#0a3a24" />
              <stop offset="1" stopColor="#041810" />
            </linearGradient>
            <linearGradient id="logo-grad-stroke" x1="4" y1="2" x2="32" y2="34" gradientUnits="userSpaceOnUse">
              <stop stopColor="#3ddc84" />
              <stop offset="0.5" stopColor="#2fa866" />
              <stop offset="1" stopColor="#2e9f90" />
            </linearGradient>
          </defs>
        </svg>
      </div>

      {/* Brand Name */}
      <div className="flex items-center leading-none">
        <span className={`font-heading font-extrabold tracking-tight text-white ${textSize}`}>
          NIGRAAN{' '}
        </span>
        <span className={`font-heading font-extrabold tracking-tight text-[#3ddc84] ${textSize}`}>
          AI
        </span>
      </div>
    </div>
  )
}
