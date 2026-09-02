import type { Point } from './types';

/** [x, y] pairs are terser to type when tracing from an image. */
export type XY = [number, number];

export const pts = (xy: XY[]): Point[] => xy.map(([x, y]) => ({ x, y }));

/** Convex quad from four corners in drawing order. */
export const quad = (a: XY, b: XY, c: XY, d: XY): Point[] => pts([a, b, c, d]);

/**
 * Splits the wall segment `from`→`to` into `ids.length` equal bays and extrudes each by
 * `depth` (a vector pointing into the building). Returns [id, polygon] pairs so callers
 * can attach metadata. Handy for the rows of offices along Gateway's outer walls.
 */
export function strip(from: XY, to: XY, depth: XY, ids: string[]): Array<[string, Point[]]> {
  const n = ids.length;
  const dx = (to[0] - from[0]) / n;
  const dy = (to[1] - from[1]) / n;
  return ids.map((id, i) => {
    const a: XY = [from[0] + dx * i, from[1] + dy * i];
    const b: XY = [from[0] + dx * (i + 1), from[1] + dy * (i + 1)];
    return [id, quad(a, b, [b[0] + depth[0], b[1] + depth[1]], [a[0] + depth[0], a[1] + depth[1]])];
  });
}

export function ellipse(cx: number, cy: number, rx: number, ry: number, n = 28): Point[] {
  return Array.from({ length: n }, (_, i) => {
    const t = (i / n) * Math.PI * 2;
    return { x: cx + rx * Math.cos(t), y: cy + ry * Math.sin(t) };
  });
}

/** 2×3 affine matrix: x' = a·x + b·y + c ; y' = d·x + e·y + f */
export type Affine = [number, number, number, number, number, number];

/**
 * Least-squares affine fit from ≥3 point pairs (source → target). Used to place rooms
 * traced in one sign's pixel space onto the floor traced from another sign.
 */
export function affineFromPairs(pairs: Array<[XY, XY]>): Affine {
  // Normal equations for x' and y' separately: [x y 1] · [a b c]ᵀ = x'
  const ata = [
    [0, 0, 0],
    [0, 0, 0],
    [0, 0, 0],
  ];
  const atx = [0, 0, 0];
  const aty = [0, 0, 0];
  for (const [[x, y], [tx, ty]] of pairs) {
    const row = [x, y, 1];
    for (let i = 0; i < 3; i++) {
      for (let j = 0; j < 3; j++) ata[i][j] += row[i] * row[j];
      atx[i] += row[i] * tx;
      aty[i] += row[i] * ty;
    }
  }
  const [a, b, c] = solve3(ata, atx);
  const [d, e, f] = solve3(ata, aty);
  return [a, b, c, d, e, f];
}

function solve3(m: number[][], v: number[]): number[] {
  // Gaussian elimination with partial pivoting on a 3×3 system.
  const a = m.map((r, i) => [...r, v[i]]);
  for (let col = 0; col < 3; col++) {
    let piv = col;
    for (let r = col + 1; r < 3; r++) if (Math.abs(a[r][col]) > Math.abs(a[piv][col])) piv = r;
    [a[col], a[piv]] = [a[piv], a[col]];
    for (let r = 0; r < 3; r++) {
      if (r === col) continue;
      const k = a[r][col] / a[col][col];
      for (let cc = col; cc < 4; cc++) a[r][cc] -= k * a[col][cc];
    }
  }
  return [a[0][3] / a[0][0], a[1][3] / a[1][1], a[2][3] / a[2][2]];
}

export const applyAffine = (m: Affine, p: Point): Point => ({
  x: m[0] * p.x + m[1] * p.y + m[2],
  y: m[3] * p.x + m[4] * p.y + m[5],
  ...(p.bulge !== undefined ? { bulge: p.bulge } : {}),
});

export const transform = (m: Affine, poly: Point[]): Point[] => poly.map((p) => applyAffine(m, p));
export const transformXY = (m: Affine, [x, y]: XY): Point => applyAffine(m, { x, y });

// ---------------------------------------------------------------------------
// Walls: rooms on the building perimeter are defined *relative to the outline* so
// their outer edge is exactly the outline segment, never a separately traced line.
// ---------------------------------------------------------------------------

/** Straight outline segment from `a` to `b`, travelling clockwise on screen (y down). */
export interface Wall {
  a: Point;
  b: Point;
}

export const wall = (a: XY, b: XY): Wall => ({ a: { x: a[0], y: a[1] }, b: { x: b[0], y: b[1] } });

/** Point at parameter t ∈ [0, 1] along the wall. */
export const along = (w: Wall, t: number): Point => ({
  x: w.a.x + (w.b.x - w.a.x) * t,
  y: w.a.y + (w.b.y - w.a.y) * t,
});

export const wallLength = (w: Wall) => Math.hypot(w.b.x - w.a.x, w.b.y - w.a.y);

/** Unit normal pointing into the building (to the right of travel for a clockwise outline). */
export function inward(w: Wall): Point {
  const dx = w.b.x - w.a.x;
  const dy = w.b.y - w.a.y;
  const len = Math.hypot(dx, dy) || 1;
  return { x: -dy / len, y: dx / len };
}

/** Room whose outer edge is wall[t0..t1], extruded `depth` units into the building. */
export function offWall(w: Wall, t0: number, t1: number, depth: number): Point[] {
  const n = inward(w);
  const p0 = along(w, t0);
  const p1 = along(w, t1);
  return [p0, p1, { x: p1.x + n.x * depth, y: p1.y + n.y * depth }, { x: p0.x + n.x * depth, y: p0.y + n.y * depth }];
}

/**
 * Consecutive rooms along wall[t0..t1]. `weights` gives relative widths (default equal);
 * neighbours share their dividing edge exactly.
 */
export function rowOffWall(
  w: Wall,
  t0: number,
  t1: number,
  depth: number,
  ids: string[],
  weights?: number[],
): Array<[string, Point[]]> {
  const ws = weights ?? ids.map(() => 1);
  const total = ws.reduce((s, x) => s + x, 0);
  let t = t0;
  return ids.map((id, i) => {
    const tn = t + ((t1 - t0) * ws[i]) / total;
    const poly = offWall(w, t, tn, depth);
    t = tn;
    return [id, poly];
  });
}

/**
 * Room wrapping an outline corner where `w1` ends and `w2` begins: it owns w1[t1..1]
 * and w2[0..t2]. The fourth vertex closes a parallelogram.
 */
export function cornerRoom(w1: Wall, t1: number, w2: Wall, t2: number): Point[] {
  const p = along(w1, t1);
  const c = w1.b;
  const q = along(w2, t2);
  return [p, c, q, { x: p.x + (q.x - c.x), y: p.y + (q.y - c.y) }];
}
