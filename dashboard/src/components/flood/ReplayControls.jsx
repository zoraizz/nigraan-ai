import { formatReplayStamp, formatShortDate } from './timeFormat.js'
import { REPLAY_STEP_MS } from '../../hooks/useFloodReplay.js'

export default function ReplayControls({ steps, index, playing, onScrub, onTogglePlay }) {
  const count = steps.length
  const current = steps[index]
  const stamp = formatReplayStamp(current?.as_of)
  const showTicks = count > 0 && count <= 8

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <button
        type="button"
        onClick={onTogglePlay}
        disabled={count === 0}
        aria-pressed={playing}
        className="inline-flex h-9 shrink-0 items-center justify-center rounded-lg bg-emerald-500 px-3 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-40"
      >
        {playing ? 'Pause' : 'Play'}
      </button>
      <div className="min-w-0 flex-1">
        <input
          type="range"
          min={0}
          max={Math.max(0, count - 1)}
          step={1}
          value={count === 0 ? 0 : index}
          disabled={count === 0}
          onChange={(event) => onScrub(Number(event.target.value))}
          aria-label="Replay step"
          aria-valuetext={stamp}
          className="flood-slider w-full"
        />
        {showTicks && (
          <div className="flex justify-between px-0.5 text-[10px] text-[#8aa898]">
            {steps.map((step) => (
              <span key={step.as_of}>{formatShortDate(step.as_of)}</span>
            ))}
          </div>
        )}
      </div>
      <div className="shrink-0 text-right">
        <p className="font-mono text-xs text-emerald-300">{stamp}</p>
        <p className="text-[10px] text-[#8aa898]">
          {count === 0 ? 'No steps' : `${index + 1} / ${count}`}
          {' · '}
          {(REPLAY_STEP_MS / 1000).toFixed(1)} s per step
        </p>
      </div>
    </div>
  )
}
