/**
 * Shared GSAP motion presets for the dashboard.
 *
 * Rules: animate transform/opacity only; every effect runs inside
 * `gsap.matchMedia()` under `(prefers-reduced-motion: no-preference)`, so
 * reduced-motion users (and environments without matchMedia, e.g. jsdom in
 * tests) get the final state immediately.
 */
import { useLayoutEffect, useRef, type RefObject } from 'react';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';

gsap.registerPlugin(useGSAP);

export const MOTION_OK = '(prefers-reduced-motion: no-preference)';
export const EASE = 'power2.out';
export const DURATION = { fast: 0.25, base: 0.35, count: 0.6, pulse: 0.9 } as const;

/** True when the browser allows motion. False in jsdom (no matchMedia) or with reduced motion. */
export function motionAllowed(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  return window.matchMedia(MOTION_OK).matches;
}

/**
 * Runs `fn` only when motion is allowed, via gsap.matchMedia so the animation is
 * reverted if the user flips the OS preference. Returns a cleanup for useGSAP.
 */
export function withMotion(fn: () => void): (() => void) | undefined {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined;
  const mm = gsap.matchMedia();
  mm.add(MOTION_OK, fn);
  return () => mm.revert();
}

/** Card entrance: fade + rise, staggered. */
export const enterFrom: gsap.TweenVars = { opacity: 0, y: 8, duration: DURATION.base, ease: EASE, stagger: 0.06 };

/**
 * Staggered entrance for every `selector` match inside `scope` on mount (and
 * whenever one of `deps` changes, e.g. the page/view key). Never let two of these
 * target the same element: a second `from` would capture the hidden state as its end.
 */
export function useStaggerIn(scope: RefObject<HTMLElement | null>, deps: unknown[] = [], selector = '[data-animate]') {
  useGSAP(
    () => withMotion(() => {
      const targets = scope.current?.querySelectorAll(selector);
      if (targets && targets.length) gsap.from(targets, { ...enterFrom, clearProps: 'opacity,transform' });
    }),
    { scope, dependencies: deps, revertOnUpdate: true },
  );
}

/** Page switch: quick fade/rise of the whole view. */
export function usePageFade(scope: RefObject<HTMLElement | null>, key: string) {
  useGSAP(
    () => withMotion(() => {
      if (scope.current) gsap.from(scope.current, { opacity: 0, y: 8, duration: DURATION.fast, ease: EASE, clearProps: 'opacity,transform' });
    }),
    { scope, dependencies: [key], revertOnUpdate: true },
  );
}

/** New live-table row: slide down + fade in. No overshoot on data tables. */
export function animateRowIn(el: Element) {
  if (!motionAllowed()) return;
  gsap.from(el, { opacity: 0, y: -6, duration: 0.3, ease: EASE, clearProps: 'opacity,transform' });
}

/**
 * One-shot attention pulse for a new blocked alert: the element scales to 1.02 and
 * back, while its `[data-pulse-ring]` child (a red ring) fades out.
 */
export function pulseOnce(el: Element) {
  if (!motionAllowed()) return;
  const tl = gsap.timeline();
  tl.fromTo(el, { scale: 1 }, { scale: 1.015, duration: 0.18, ease: 'power1.out', yoyo: true, repeat: 1, clearProps: 'transform' });
  const ring = el.querySelector('[data-pulse-ring]');
  if (ring) tl.fromTo(ring, { opacity: 1, scale: 1 }, { opacity: 0, scale: 1.03, duration: DURATION.pulse, ease: EASE }, 0);
}

/**
 * Count-up: tweens the text of the element (its single text node) from the
 * previously shown value to `value`, formatting each frame with `format`.
 *
 * React renders the final formatted value as the element's only child, so the
 * DOM always ends (and, without motion, starts) at the right text; we only
 * rewrite that same text node's nodeValue during the tween, which React's
 * text-content fast path keeps in sync.
 */
export function useCountUp<T extends HTMLElement>(value: number, format: (n: number) => string) {
  const ref = useRef<T>(null);
  const shown = useRef<number | null>(null);
  const fmt = useRef(format);
  fmt.current = format;

  useLayoutEffect(() => {
    const el = ref.current;
    const from = shown.current;
    shown.current = value;
    if (!el || from == null || from === value || !Number.isFinite(value) || !motionAllowed()) return;
    const node = el.firstChild;
    if (!node || node.nodeType !== Node.TEXT_NODE) return;
    const proxy = { v: from };
    const tween = gsap.to(proxy, {
      v: value,
      duration: DURATION.count,
      ease: EASE,
      onUpdate: () => {
        shown.current = proxy.v;
        node.nodeValue = fmt.current(proxy.v);
      },
      onComplete: () => {
        shown.current = value;
        node.nodeValue = fmt.current(value);
      },
    });
    // React has already written the next final value before this cleanup runs;
    // just stop the tween so it cannot overwrite it.
    return () => { tween.kill(); };
  }, [value]);

  return ref;
}
