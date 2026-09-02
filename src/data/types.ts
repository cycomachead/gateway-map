/**
 * Shared coordinate: floor-plan units (arbitrary, consistent per building).
 *
 * A vertex may carry a `bulge`, which turns the edge from this vertex to the next one
 * into a circular arc (same convention as DXF polylines). bulge = tan(θ/4) where θ is
 * the arc's included angle: 0 = straight, 1 = semicircle, ±0.41 ≈ 90°. Positive values
 * bow the arc to the right of the direction of travel (on screen, y down); negative to
 * the left. Two vertices with bulge 1 each make a full circle.
 */
export interface Point {
  x: number;
  y: number;
  bulge?: number;
}

export type SpaceCategory =
  | 'classroom'
  | 'lab'
  | 'office'
  | 'meeting'
  | 'focus'
  | 'open'
  | 'study'
  | 'amenity'
  | 'service'
  | 'circulation';

export const SPACE_CATEGORIES: SpaceCategory[] = [
  'classroom',
  'lab',
  'office',
  'meeting',
  'focus',
  'open',
  'study',
  'amenity',
  'service',
  'circulation',
];

export const CATEGORY_LABELS: Record<SpaceCategory, string> = {
  classroom: 'Classrooms',
  lab: 'Labs',
  office: 'Offices',
  meeting: 'Meeting rooms',
  focus: 'Focus rooms',
  open: 'Open workspace',
  study: 'Study spaces',
  amenity: 'Amenities',
  service: 'Services',
  circulation: 'Circulation',
};

export interface Space {
  id: string;
  name: string;
  /** Short text drawn on the map (defaults to `name`); e.g. just the room number. */
  label?: string;
  floorId: string;
  category: SpaceCategory;
  /** Closed outline; last point is implicitly joined to the first. Edges may be arcs via `bulge`. */
  polygon: Point[];
  /** Building zone, e.g. "Northeast" / "Southwest" on the Gateway wayfinding signs. */
  wing?: string;
  tags?: string[];
  description?: string;
  capacity?: number;
}

export type PoiKind =
  | 'elevator'
  | 'stairs'
  | 'restroom'
  | 'exit'
  | 'cafe'
  | 'info'
  | 'porch'
  | 'lactation'
  | 'meditation';

export const POI_LABELS: Record<PoiKind, string> = {
  elevator: 'Elevator',
  stairs: 'Stairs',
  restroom: 'Restroom',
  exit: 'Entrance / exit',
  cafe: 'Social kitchen',
  info: 'Information',
  porch: 'Front porch',
  lactation: 'Lactation room',
  meditation: 'Meditation room',
};

export interface Poi {
  id: string;
  name: string;
  floorId: string;
  kind: PoiKind;
  at: Point;
  description?: string;
}

export interface Floor {
  id: string;
  label: string;
  /** Sort key; 0 = ground. */
  level: number;
  width: number;
  height: number;
  outline: Point[];
}

export interface Building {
  name: string;
  floors: Floor[];
  spaces: Space[];
  pois: Poi[];
}
