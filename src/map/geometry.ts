import type { Point, Street } from '../data/types';

export interface BBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface Arc {
  cx: number;
  cy: number;
  r: number;
  /** Start angle (radians, screen coords) */
  a0: number;
  /** Signed sweep in radians; positive = clockwise on screen (SVG positive-angle direction). */
  sweep: number;
}

/** Circle through a and b with the given bulge (see Point docs); null for straight edges. */
function arcBetween(a: Point, b: Point, bulge: number): Arc | null {
  if (!bulge) return null;
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const chord = Math.hypot(dx, dy);
  if (chord < 1e-9) return null;
  const theta = 4 * Math.atan(Math.abs(bulge)); // included angle
  const r = chord / (2 * Math.sin(theta / 2));
  const sagitta = (Math.abs(bulge) * chord) / 2;
  // Unit normal pointing to the right of travel on a y-down screen, flipped for negative bulge.
  const sign = bulge > 0 ? 1 : -1;
  const nx = (-dy / chord) * sign;
  const ny = (dx / chord) * sign;
  const mx = (a.x + b.x) / 2;
  const my = (a.y + b.y) / 2;
  const cx = mx - nx * (r - sagitta);
  const cy = my - ny * (r - sagitta);
  const a0 = Math.atan2(a.y - cy, a.x - cx);
  const aMid = Math.atan2(my + ny * sagitta - cy, mx + nx * sagitta - cx);
  // Rotate from a0 through aMid; pick the direction whose short rotation hits the arc midpoint.
  let d = aMid - a0;
  while (d <= -Math.PI) d += 2 * Math.PI;
  while (d > Math.PI) d -= 2 * Math.PI;
  const sweep = Math.sign(d) * theta;
  return { cx, cy, r, a0, sweep };
}

/**
 * Approximates the outline (including arcs) with straight segments. Used for bbox,
 * centroid, and anything else that wants plain polygon math.
 */
export function flatten(points: Point[], maxSegmentAngle = Math.PI / 12): Point[] {
  const out: Point[] = [];
  for (let i = 0; i < points.length; i++) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    out.push({ x: a.x, y: a.y });
    const arc = arcBetween(a, b, a.bulge ?? 0);
    if (!arc) continue;
    const steps = Math.max(1, Math.ceil(Math.abs(arc.sweep) / maxSegmentAngle));
    for (let s = 1; s < steps; s++) {
      const ang = arc.a0 + (arc.sweep * s) / steps;
      out.push({ x: arc.cx + arc.r * Math.cos(ang), y: arc.cy + arc.r * Math.sin(ang) });
    }
  }
  return out;
}

/** SVG path data for an outline, using true arcs for bulged edges; `closed: false` for a line (a street). */
export function toPath(points: Point[], closed = true): string {
  if (points.length === 0) return '';
  const parts: string[] = [`M${fmt(points[0].x)} ${fmt(points[0].y)}`];
  const edges = closed ? points.length : points.length - 1;
  for (let i = 0; i < edges; i++) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    const bulge = a.bulge ?? 0;
    if (!bulge) {
      if (i < points.length - 1) parts.push(`L${fmt(b.x)} ${fmt(b.y)}`);
      continue;
    }
    const arc = arcBetween(a, b, bulge)!;
    const large = Math.abs(bulge) > 1 ? 1 : 0;
    const sweepFlag = arc.sweep > 0 ? 1 : 0;
    // Full circles need two arcs; a single A from a point to itself renders nothing.
    if (Math.hypot(b.x - a.x, b.y - a.y) < 1e-9) continue;
    parts.push(`A${fmt(arc.r)} ${fmt(arc.r)} 0 ${large} ${sweepFlag} ${fmt(b.x)} ${fmt(b.y)}`);
  }
  if (closed) parts.push('Z');
  return parts.join(' ');
}

const fmt = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(2));

export function bbox(points: Point[]): BBox {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const p of flatten(points)) {
    if (p.x < minX) minX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.x > maxX) maxX = p.x;
    if (p.y > maxY) maxY = p.y;
  }
  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
}

/** Area-weighted centroid of the (flattened) outline; falls back to bbox centre if degenerate. */
export function centroid(points: Point[]): Point {
  const poly = flatten(points);
  let area = 0;
  let cx = 0;
  let cy = 0;
  for (let i = 0; i < poly.length; i++) {
    const a = poly[i];
    const b = poly[(i + 1) % poly.length];
    const cross = a.x * b.y - b.x * a.y;
    area += cross;
    cx += (a.x + b.x) * cross;
    cy += (a.y + b.y) * cross;
  }
  if (Math.abs(area) < 1e-9) {
    const box = bbox(points);
    return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  }
  area *= 0.5;
  return { x: cx / (6 * area), y: cy / (6 * area) };
}

export function pad(box: BBox, amount: number): BBox {
  return {
    x: box.x - amount,
    y: box.y - amount,
    width: box.width + amount * 2,
    height: box.height + amount * 2,
  };
}

/** Smallest box holding all the given boxes. */
export function unionBox(first: BBox, ...rest: BBox[]): BBox {
  let { x: x0, y: y0 } = first;
  let x1 = first.x + first.width;
  let y1 = first.y + first.height;
  for (const b of rest) {
    x0 = Math.min(x0, b.x);
    y0 = Math.min(y0, b.y);
    x1 = Math.max(x1, b.x + b.width);
    y1 = Math.max(y1, b.y + b.height);
  }
  return { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
}

/** The box of the stretch of a street that runs past `within` (its x range), carriageway included. */
export function streetBox(street: Street, within: BBox): BBox {
  const line = flatten(street.path, Math.PI / 180);
  const near = line.filter((p) => p.x >= within.x && p.x <= within.x + within.width);
  if (!near.length) return within;
  return pad(bbox(near), street.width / 2);
}
