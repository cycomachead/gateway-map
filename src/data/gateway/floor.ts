import { pts, type XY } from '../helpers';
import type { Poi, PoiKind, Space, SpaceCategory } from '../types';

export type Wing = 'Northeast' | 'Southwest';

export type RoomExtra = {
  name?: string;
  label?: string;
  description?: string;
  tags?: string[];
};

/**
 * A room in floor coordinates: [wing, id, category, polygon, extras]. Numbered rooms get
 * their name from the category ("Meeting Room 3161") unless `name` is given.
 */
export type RoomSpec = [Wing | undefined, string, SpaceCategory, XY[], RoomExtra?];

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

export function makeSpace(floorId: string, wing: Wing | undefined, id: string, category: SpaceCategory, polygon: XY[], extra: RoomExtra = {}): Space {
  const number = /^[A-Z]?\d+[A-Z]?$/.test(id) ? id : undefined;
  return {
    id: `${floorId}-${id.toLowerCase().replace(/[\s’']+/g, '-')}`,
    name: extra.name ?? `${kindName[category] ?? 'Room'} ${id}`,
    label: extra.label ?? number ?? extra.name ?? id,
    floorId,
    category,
    wing,
    polygon: pts(polygon),
    description: extra.description,
    tags: [...(wing ? [wing.toLowerCase()] : []), ...(number ? [number] : []), ...(extra.tags ?? [])],
  };
}

export const spacesFrom = (floorId: string, rooms: RoomSpec[]): Space[] =>
  rooms.map(([wing, id, cat, poly, extra]) => makeSpace(floorId, wing, id, cat, poly, extra));

export const poisFrom = (floorId: string, pois: PoiSpec[]): Poi[] =>
  pois.map(([id, name, kind, [x, y], description]) => ({ id: `${floorId}-${id}`, name, floorId, kind, at: { x, y }, description }));
