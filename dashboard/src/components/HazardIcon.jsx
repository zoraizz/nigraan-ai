import { HAZARD_LABELS } from '../config/districts.js'

// Hazard glyphs — 14px inline SVGs, stroke/fill inherit currentColor so the
// hz-* chip class (hazard token color) drives the hue.

function FloodGlyph() {
  return (
    <svg
      viewBox="0 0 14 14"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      aria-hidden="true"
      className="h-3.5 w-3.5 shrink-0"
    >
      <path d="M1.5 4.8c1.2-1.3 2.4-1.3 3.6 0s2.4 1.3 3.6 0 2.4-1.3 3.6 0" />
      <path d="M1.5 9.2c1.2-1.3 2.4-1.3 3.6 0s2.4 1.3 3.6 0 2.4-1.3 3.6 0" />
    </svg>
  )
}

function DroughtGlyph() {
  return (
    <svg
      viewBox="0 0 14 14"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.3"
      strokeLinecap="round"
      aria-hidden="true"
      className="h-3.5 w-3.5 shrink-0"
    >
      <circle cx="7" cy="7" r="2.4" fill="currentColor" stroke="none" />
      <path d="M7 .8v1.8M7 11.4v1.8M.8 7h1.8M11.4 7h1.8M2.6 2.6l1.3 1.3M10.1 10.1l1.3 1.3M11.4 2.6l-1.3 1.3M3.9 10.1l-1.3 1.3" />
    </svg>
  )
}

function LandslideGlyph() {
  return (
    <svg
      viewBox="0 0 14 14"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      aria-hidden="true"
      className="h-3.5 w-3.5 shrink-0"
    >
      <path d="M1.2 12.8 12.8 1.2" />
      <circle cx="5" cy="9.6" r="1.1" fill="currentColor" stroke="none" />
      <circle cx="7.6" cy="8.2" r="0.9" fill="currentColor" stroke="none" />
      <circle cx="9.8" cy="6.6" r="0.7" fill="currentColor" stroke="none" />
    </svg>
  )
}

function AvalancheGlyph() {
  return (
    <svg
      viewBox="0 0 14 14"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.3"
      strokeLinecap="round"
      aria-hidden="true"
      className="h-3.5 w-3.5 shrink-0"
    >
      <path d="M7 1.2v11.6M2 4.1l10 5.8M12 4.1 2 9.9" />
    </svg>
  )
}

function GlofGlyph() {
  return (
    <svg
      viewBox="0 0 14 14"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.3"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="h-3.5 w-3.5 shrink-0"
    >
      <path d="M1.2 8.6 4.6 3.4l2 2.9 1.7-2.3 3.5 4.6z" />
      <path d="M1.5 11.6c1.1-1 2.2-1 3.3 0s2.2 1 3.3 0 2.2-1 3.3 0" />
    </svg>
  )
}

const GLYPHS = {
  flood: FloodGlyph,
  drought: DroughtGlyph,
  landslide: LandslideGlyph,
  avalanche: AvalancheGlyph,
  glof: GlofGlyph,
}

// Chip for one of the five hazard types (Risk Flag's HAZARD_TYPES), tinted
// from the hazard token via the hz-* class. Same glyph set on every page.
export default function HazardIcon({ hazard }) {
  const label = HAZARD_LABELS[hazard] || hazard
  const Glyph = GLYPHS[hazard]
  return (
    <span className={`hazard-chip hz-${hazard}`}>
      {Glyph ? <Glyph /> : null}
      {label}
    </span>
  )
}
