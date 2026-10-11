import React from 'react'

/**
 * Modern Logo component for Nigraan AI.
 * Displays official uploaded logo image + crisp typography.
 */
export default function Logo({ size = 'md', className = '', showText = true }) {
  const isSm = size === 'sm'
  const isLg = size === 'lg'

  const iconSize = isSm ? 'h-8 w-8' : isLg ? 'h-11 w-11' : 'h-9 w-9'
  const textSize = isSm ? 'text-sm' : isLg ? 'text-xl' : 'text-base'

  return (
    <div className={`inline-flex items-center gap-2.5 ${className}`}>
      {/* Emblem Container with soft shadow/glow */}
      <div className={`relative flex ${iconSize} shrink-0 items-center justify-center rounded-lg bg-[#0a3a24] p-0.5 shadow-md shadow-emerald-950/40 border border-emerald-600/30 overflow-hidden`}>
        <img
          src="/logo.png"
          alt="Nigraan AI Logo"
          className="h-full w-full object-contain rounded-md"
        />
      </div>

      {/* Brand Name */}
      {showText && (
        <div className="flex items-center leading-none">
          <span className={`font-heading font-extrabold tracking-tight text-white ${textSize}`}>
            NIGRAAN{' '}
          </span>
          <span className={`font-heading font-extrabold tracking-tight text-[#3ddc84] ${textSize}`}>
            AI
          </span>
        </div>
      )}
    </div>
  )
}

