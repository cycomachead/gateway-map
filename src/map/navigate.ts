import type { Point } from '../data/types';
import type { BBox } from './geometry';

export type Direction = 'up' | 'down' | 'left' | 'right';

export const DIRECTION_LABELS: Record<Direction, string> = { up: 'up', down: 'down', left: 'left', right: 'right' };

const UNIT: Record<Direction, Point> = {
  up: { x: 0, y: -1 },
  down: { x: 0, y: 1 },
  left: { x: -1, y: 0 },
  right: { x: 1, y: 0 },
};

export interface Candidate<T> {
  item: T;
  box: BBox;
  centre: Point;
}

/** Signed distance of `p` from `from` along `dir` (positive = ahead) and its sideways offset. */
function project(from: Point, p: Point, dir: Direction) {
  const u = UNIT[dir];
  const dx = p.x - from.x;
  const dy = p.y - from.y;
  return { forward: dx * u.x + dy * u.y, lateral: dx * u.y - dy * u.x };
}

/** Distance from a coordinate to a closed interval; 0 inside it. */
const gapTo = (v: number, lo: number, hi: number) => (v < lo ? lo - v : v > hi ? v - hi : 0);

/**
 * The room a keyboard user would expect to land on when pressing an arrow key from `from`
 * (normally the centre of the room they are on). A candidate counts when its centre lies
 * ahead; the winner is the one with the smallest gap between the boxes along the arrow,
 * breaking ties in favour of rooms that sit in line with the starting point, so walking up
 * a corridor of offices stays in the same column. Returns null when nothing lies that way.
 */
export function nearestInDirection<T>(from: Point, current: BBox | null, candidates: Candidate<T>[], dir: Direction): T | null {
  const vertical = dir === 'up' || dir === 'down';
  let best: T | null = null;
  let bestScore = Infinity;
  for (const c of candidates) {
    const { forward, lateral } = project(from, c.centre, dir);
    if (forward <= 0) continue;
    const gap = current
      ? vertical
        ? dir === 'up'
          ? current.y - (c.box.y + c.box.height)
          : c.box.y - (current.y + current.height)
        : dir === 'left'
          ? current.x - (c.box.x + c.box.width)
          : c.box.x - (current.x + current.width)
      : forward;
    // Sideways distance from the starting point to the candidate's extent across the arrow.
    const sideways = vertical ? gapTo(from.x, c.box.x, c.box.x + c.box.width) : gapTo(from.y, c.box.y, c.box.y + c.box.height);
    const score = Math.max(gap, 0) + 2 * sideways + 0.05 * Math.abs(lateral);
    if (score < bestScore) {
      bestScore = score;
      best = c.item;
    }
  }
  return best;
}

/** The candidate whose centre is closest to `from`, ignoring direction. */
export function nearestTo<T>(from: Point, candidates: Candidate<T>[]): T | null {
  let best: T | null = null;
  let bestDist = Infinity;
  for (const c of candidates) {
    const d = Math.hypot(c.centre.x - from.x, c.centre.y - from.y);
    if (d < bestDist) {
      bestDist = d;
      best = c.item;
    }
  }
  return best;
}
