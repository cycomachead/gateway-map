import { affineFromPairs, offWall, rowOffWall, transform, type Affine, type Wall, type XY } from '../helpers';
import type { Point, Poi, PoiKind, Space, SpaceCategory } from '../types';

export type Wing = 'Northeast' | 'Southwest';

export type RoomExtra = {
  name?: string;
  label?: string;
  description?: string;
  tags?: string[];
};

/**
 * A room in floor coordinates: [wing, id, category, polygon, extras]. Numbered rooms get
 * their name from the category ("Meeting Room 3161"); anything else should pass `name`.
 */
export type RoomSpec = [Wing, string, SpaceCategory, XY[], RoomExtra?];

/** A point of interest: [id, name, kind, position, description]. */
export type PoiSpec = [string, string, PoiKind, XY, string?];

const kindName: Partial<Record<SpaceCategory, string>> = {
  meeting: 'Meeting Room',
  focus: 'Focus Room',
  lab: 'Lab',
  open: 'Open Workspace',
  classroom: 'Classroom',
  office: 'Room',
};

const pts = (xy: XY[]): Point[] => xy.map(([x, y]) => ({ x, y }));

export function makeSpace(floorId: string, wing: Wing | undefined, id: string, category: SpaceCategory, polygon: Point[], extra: RoomExtra = {}): Space {
  const number = /^\d+[A-Z]?$/.test(id) ? id : undefined;
  return {
    id: `${floorId}-${id.toLowerCase().replace(/[\s’']+/g, '-')}`,
    name: extra.name ?? `${kindName[category] ?? 'Room'} ${id}`,
    label: extra.label ?? number ?? extra.name ?? id,
    floorId,
    category,
    wing,
    polygon,
    description: extra.description,
    tags: [...(wing ? [wing.toLowerCase()] : []), ...(number ? [number] : []), ...(extra.tags ?? [])],
  };
}

export const spacesFrom = (floorId: string, rooms: RoomSpec[]): Space[] =>
  rooms.map(([wing, id, cat, poly, extra]) => makeSpace(floorId, wing, id, cat, pts(poly), extra));

export const poisFrom = (floorId: string, pois: PoiSpec[]): Poi[] =>
  pois.map(([id, name, kind, [x, y], description]) => ({ id: `${floorId}-${id}`, name, floorId, kind, at: { x, y }, description }));

/**
 * Builder for floors traced by hand in the Level 4 style: perimeter rooms are defined
 * relative to named walls, interior rooms are traced in a detail sign's pixel space and
 * mapped onto the floor with an affine transform fitted on the wing's corners.
 */
export function floorBuilder(floorId: string) {
  const spaces: Space[] = [];
  const place = (wing: Wing, id: string, polygon: Point[], spec: { cat: SpaceCategory } & RoomExtra) => {
    const { cat, ...extra } = spec;
    spaces.push(makeSpace(floorId, wing, id, cat, polygon, extra));
  };
  const traced = (wing: Wing, m: Affine, id: string, poly: Point[], spec: { cat: SpaceCategory } & RoomExtra) =>
    place(wing, id, transform(m, poly), spec);
  const perimeterRow = (
    wing: Wing,
    w: Wall,
    t0: number,
    t1: number,
    depth: number,
    ids: string[],
    opts: { cat?: SpaceCategory; weights?: number[]; overrides?: Record<string, SpaceCategory> } = {},
  ) => {
    for (const [id, poly] of rowOffWall(w, t0, t1, depth, ids, opts.weights)) {
      place(wing, id, poly, { cat: opts.overrides?.[id] ?? opts.cat ?? 'office' });
    }
  };
  return { spaces, place, traced, perimeterRow, offWall, affineFromPairs };
}
