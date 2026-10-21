// Asia/Karachi wall times from the flood API: YYYY-MM-DDTHH:MM, no offset.
// Parsed as calendar fields so a UTC browser does not shift the clock.

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

const WALL = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/

export function parseWallTime(iso) {
  const match = WALL.exec(String(iso || ''))
  if (!match) return null
  const [, year, month, day, hour, minute] = match
  return Date.UTC(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute))
}

function parts(iso) {
  const match = WALL.exec(String(iso || ''))
  if (!match) return null
  const ms = parseWallTime(iso)
  return {
    year: match[1],
    monthIndex: Number(match[2]) - 1,
    day: Number(match[3]),
    hour: match[4],
    minute: match[5],
    weekday: WEEKDAYS[new Date(ms).getUTCDay()],
  }
}

// "Fri 2 Sep 04:00"
export function formatWall(iso) {
  const wall = parts(iso)
  if (!wall) return '—'
  return `${wall.weekday} ${wall.day} ${MONTHS[wall.monthIndex]} ${wall.hour}:${wall.minute}`
}

// "Mon 29 Aug 2022 06:00"
export function formatReplayStamp(iso) {
  const wall = parts(iso)
  if (!wall) return '—'
  return `${wall.weekday} ${wall.day} ${MONTHS[wall.monthIndex]} ${wall.year} ${wall.hour}:${wall.minute}`
}

// "Fri 24 Oct" from a YYYY-MM-DD date or a wall time
export function formatDay(iso) {
  const value = String(iso || '')
  const wall = parts(value.length === 10 ? `${value}T06:00` : value)
  if (!wall) return '—'
  return `${wall.weekday} ${wall.day} ${MONTHS[wall.monthIndex]}`
}

// "29 Aug"
export function formatShortDate(iso) {
  const wall = parts(iso)
  if (!wall) return '—'
  return `${wall.day} ${MONTHS[wall.monthIndex]}`
}

export function hoursBetween(earlier, later) {
  const start = parseWallTime(earlier)
  const end = parseWallTime(later)
  if (start == null || end == null) return null
  return Math.round((end - start) / 3600000)
}

// Half-width of the arrival window, in hours. The larger side is used when
// the window is not symmetric, matching a single "+/- N h" label.
export function uncertaintyHours(low, mid, high) {
  const back = hoursBetween(low, mid)
  const forward = hoursBetween(mid, high)
  if (back == null || forward == null) return null
  return Math.max(Math.abs(back), Math.abs(forward))
}

// "Peak at Guddu: ~Fri 2 Sep 04:00 (+/- 12 h)"
// Arrived rows name the observed time and drop the estimate mark.
export function formatPeakLine(eta) {
  const place = eta?.barrage || 'barrage'
  if (eta?.status === 'arrived') {
    const when = eta.observed_time ? formatWall(eta.observed_time) : 'time not recorded'
    return `Peak at ${place}: arrived ${when}`
  }
  const when = formatWall(eta?.eta)
  const band = uncertaintyHours(eta?.eta_low, eta?.eta, eta?.eta_high)
  const bandText = band == null ? '' : ` (+/- ${band} h)`
  return `Peak at ${place}: ~${when}${bandText}`
}

export function formatPeople(value) {
  const count = Number(value)
  if (!Number.isFinite(count)) return '—'
  return count.toLocaleString('en-US')
}

export function formatCusecs(value) {
  const flow = Number(value)
  if (!Number.isFinite(flow)) return '—'
  return `${flow.toLocaleString('en-US')} cusecs`
}

export function formatSignedHours(value) {
  const hours = Number(value)
  if (!Number.isFinite(hours)) return '—'
  const sign = hours > 0 ? '+' : ''
  return `${sign}${hours} h`
}
