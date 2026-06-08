import { useEffect, useReducer, useRef } from "react"

const prefersReducedMotion =
  typeof window !== "undefined"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false

export function useCountUp(target: number, duration = 600): number {
  const [value, dispatch] = useReducer((_: number, v: number) => v, target)
  const rafRef = useRef<number | null>(null)
  const prevTargetRef = useRef<number>(target)

  useEffect(() => {
    if (prefersReducedMotion) {
      dispatch(target)
      return
    }

    const from = prevTargetRef.current === target ? 0 : prevTargetRef.current
    prevTargetRef.current = target
    const start = performance.now()

    function tick(now: number) {
      const elapsed = now - start
      const progress = Math.min(elapsed / duration, 1)
      // ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3)
      dispatch(Math.round(from + (target - from) * eased))
      if (progress < 1) {
        rafRef.current = requestAnimationFrame(tick)
      }
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    }
  }, [target, duration])

  return value
}
