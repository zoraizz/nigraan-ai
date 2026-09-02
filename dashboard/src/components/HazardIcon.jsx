import { HAZARD_LABELS } from '../config/districts.js'

// Small chip for one of the five hazard types (matches Risk Flag's
// HAZARD_TYPES). Real icons can replace the text later.
export default function HazardIcon({ hazard }) {
  const label = HAZARD_LABELS[hazard] || hazard
  return (
    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs font-medium text-slate-600">
      {label}
    </span>
  )
}
