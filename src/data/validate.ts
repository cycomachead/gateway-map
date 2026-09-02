import type { Building, Point } from './types';

/** Two points with arcs can close a shape (a circle); otherwise we need three. */
const isClosedShape = (pts: Point[]) => pts.length >= 3 || (pts.length === 2 && pts.some((p) => p.bulge));

/** Returns a list of human-readable problems; empty means the data is valid. */
export function validateBuilding(b: Building): string[] {
  const problems: string[] = [];
  const floorIds = new Set<string>();
  for (const f of b.floors) {
    if (floorIds.has(f.id)) problems.push(`Duplicate floor id "${f.id}"`);
    floorIds.add(f.id);
    if (!isClosedShape(f.outline)) problems.push(`Floor "${f.id}" outline needs 3+ points (or 2 with arcs)`);
  }

  const spaceIds = new Set<string>();
  for (const s of b.spaces) {
    if (spaceIds.has(s.id)) problems.push(`Duplicate space id "${s.id}"`);
    spaceIds.add(s.id);
    if (!floorIds.has(s.floorId)) problems.push(`Space "${s.id}" references unknown floor "${s.floorId}"`);
    if (!isClosedShape(s.polygon)) problems.push(`Space "${s.id}" polygon needs 3+ points (or 2 with arcs)`);
  }

  const poiIds = new Set<string>();
  for (const p of b.pois) {
    if (poiIds.has(p.id)) problems.push(`Duplicate POI id "${p.id}"`);
    poiIds.add(p.id);
    if (!floorIds.has(p.floorId)) problems.push(`POI "${p.id}" references unknown floor "${p.floorId}"`);
  }
  return problems;
}
