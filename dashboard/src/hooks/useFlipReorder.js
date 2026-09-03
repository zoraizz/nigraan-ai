import { useLayoutEffect, useRef } from 'react'

const EASE = 'cubic-bezier(0.22, 0.61, 0.36, 1)'

// Lightweight FLIP reorder for keyed lists — the one orchestrated motion
// moment in the app (Aid Priority ranked table). No animation library needed.
//
//   const register = useFlipReorder(rows.map((row) => row.key))  // call before
//   ... <div key={row.key} ref={register(row.key)}> ...          // any return
//
// When the key order changes, previously-rendered rows transition from their
// old on-screen position to the new one; rows appearing for the first time
// fade up with a short stagger. Honors prefers-reduced-motion (positions are
// still recorded, nothing moves).
export function useFlipReorder(keys, { duration = 420, enterStagger = 55 } = {}) {
  const nodes = useRef(new Map()) // key -> element
  const positions = useRef(new Map()) // key -> { top, left } at last layout

  const register = (key) => (element) => {
    if (element == null) nodes.current.delete(key)
    else nodes.current.set(key, element)
  }

  const orderKey = Array.isArray(keys) ? keys.join(' ') : String(keys)

  useLayoutEffect(() => {
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    let entering = 0

    nodes.current.forEach((element, key) => {
      const rect = element.getBoundingClientRect()
      const prev = positions.current.get(key)

      if (!reduced && prev) {
        // Moved row: invert (jump back to the old position), then play.
        const dx = prev.left - rect.left
        const dy = prev.top - rect.top
        if (dx !== 0 || dy !== 0) {
          element.style.transition = 'none'
          element.style.transform = `translate(${dx}px, ${dy}px)`
          void element.offsetHeight // commit the inverted position before animating
          element.style.transition = `transform ${duration}ms ${EASE}`
          element.style.transform = ''
        }
      } else if (!reduced) {
        // First appearance (initial load or a newly ranked district).
        element.animate(
          [
            { opacity: 0, transform: 'translateY(12px)' },
            { opacity: 1, transform: 'translateY(0)' },
          ],
          { duration: 300, delay: entering * enterStagger, easing: 'ease-out' },
        )
        entering += 1
      }

      positions.current.set(key, { top: rect.top, left: rect.left })
    })

    // Drop positions for rows that no longer exist.
    positions.current.forEach((_pos, key) => {
      if (!nodes.current.has(key)) positions.current.delete(key)
    })
  }, [orderKey, duration, enterStagger])

  return register
}
