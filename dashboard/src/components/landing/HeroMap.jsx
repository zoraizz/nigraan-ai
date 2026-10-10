import { useEffect, useState } from 'react'

// Simplified outline of Pakistan (illustrative, not survey-accurate).
const OUTLINE =
  'M192 8L236 5L262 19L289 46L262 73L245 86L241 127L254 140L245 162L233 186L192 243L171 248L166 289L184 343L135 365L119 335L108 319L61 324L19 324L19 289L47 270L33 240L12 200L35 211L61 205L101 200L100 167L131 148L154 143L166 108L183 86L185 46Z'

const LEVELS = {
  critical: { label: 'Critical', color: 'var(--color-danger)', cls: 'lp-tone-critical' },
  high: { label: 'High', color: 'var(--color-risk-high)', cls: 'lp-tone-high' },
  medium: { label: 'Medium', color: 'var(--color-risk-medium)', cls: 'lp-tone-medium' },
  low: { label: 'Low', color: 'var(--color-risk-low)', cls: 'lp-tone-low' },
}

// Illustrative sample markers only. These are NOT live assessments; the live
// ones are on the Risk Map and Aid Priority pages of the console.
const SAMPLE_MARKERS = [
  {
    name: 'Islamabad',
    x: 219,
    y: 94,
    level: 'high',
    rainfall: 'Heavy',
    damage: 'Under review',
    aid: 'High',
  },
  {
    name: 'Lahore',
    x: 242,
    y: 153,
    level: 'medium',
    rainfall: 'Moderate',
    damage: 'None reported',
    aid: 'Medium',
  },
  {
    name: 'Karachi',
    x: 114,
    y: 332,
    level: 'low',
    rainfall: 'Low',
    damage: 'None reported',
    aid: 'Low',
  },
  {
    name: 'Peshawar',
    x: 192,
    y: 86,
    level: 'high',
    rainfall: 'Heavy',
    damage: 'Under review',
    aid: 'High',
  },
  {
    name: 'Quetta',
    x: 114,
    y: 189,
    level: 'low',
    rainfall: 'Low',
    damage: 'None reported',
    aid: 'Low',
  },
  {
    name: 'Sukkur',
    x: 147,
    y: 257,
    level: 'critical',
    rainfall: 'Very heavy',
    damage: 'Severe (sample)',
    aid: 'Critical',
  },
  {
    name: 'Skardu',
    x: 264,
    y: 51,
    level: 'medium',
    rainfall: 'Moderate',
    damage: 'Unknown',
    aid: 'Medium',
  },
]

export default function HeroMap() {
  const [active, setActive] = useState(null)

  const marker = active == null ? null : SAMPLE_MARKERS[active]

  return (
    <div className="lp-map">
      <div className="lp-stage">
        <svg
          viewBox="0 0 310 370"
          role="img"
          aria-label="Illustrative map of Pakistan with sample risk markers"
        >
          <path d={OUTLINE} />
          {SAMPLE_MARKERS.map((m) => (
            <circle
              key={`pulse-${m.name}`}
              className="lp-pulse"
              cx={m.x}
              cy={m.y}
              r="5"
              fill={LEVELS[m.level].color}
              aria-hidden="true"
            />
          ))}
          {SAMPLE_MARKERS.map((m, i) => (
            <circle
              key={m.name}
              className="lp-dot"
              cx={m.x}
              cy={m.y}
              r="5"
              fill={LEVELS[m.level].color}
              tabIndex={0}
              role="button"
              aria-label={`${m.name}: ${LEVELS[m.level].label} risk (sample data)`}
              onMouseEnter={() => setActive(i)}
              onFocus={() => setActive(i)}
              onClick={() => setActive(i)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  setActive(i)
                }
              }}
            />
          ))}
        </svg>

        <div className="lp-radar" aria-hidden="true" />

        <div className="lp-tip" aria-live="polite">
          {marker ? (
            <>
              <b>{marker.name}</b>
              <span className={`lp-tag lp-tag-sm ${LEVELS[marker.level].cls} is-on`}>
                <i />
                {LEVELS[marker.level].label} risk
              </span>
              <br />
              Rainfall: {marker.rainfall}
              <br />
              Damage: {marker.damage}
              <br />
              Aid priority: {marker.aid}
            </>
          ) : (
            <>
              <b>Hover a marker</b>
              Sample data
            </>
          )}
        </div>
      </div>
      <p className="lp-map-note">Illustrative sample data only</p>
    </div>
  )
}
