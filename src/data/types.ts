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
  | 'copy'
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
  'copy',
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
  copy: 'Copy rooms',
  circulation: 'Circulation',
};

/** Pictograms drawn above a room's label (the restroom signs, a stair, a copy room's printer). */
export type SpaceIcon = 'man' | 'woman' | 'all-gender' | 'stairs' | 'printer';

export interface Space {
  id: string;
  name: string;
  /**
   * Short text drawn on the map (defaults to `name`); e.g. just the room number. Lines after
   * a newline are drawn smaller under the first one.
   */
  label?: string;
  /** A pictogram drawn above the label. */
  icon?: SpaceIcon;
  /** The room's name, drawn small under the label; set for rooms large enough to carry it. */
  caption?: string;
  /** A direction drawn along the space (the way a stair goes), tail to head; the label sits at the head. */
  arrow?: Point[];
  floorId: string;
  category: SpaceCategory;
  /** Closed outline; last point is implicitly joined to the first. Edges may be arcs via `bulge`. */
  polygon: Point[];
  /** Cut-outs inside the outline (e.g. a huddle room standing in an open workspace). */
  holes?: Point[][];
  /** Building zone, e.g. "Northeast" / "Southwest" on the Gateway wayfinding signs. */
  wing?: string;
  tags?: string[];
  description?: string;
  capacity?: number;
  /** People whose office this is (e.g. the faculty member assigned to a faculty office). */
  occupants?: string[];
  /** The department the room is assigned to on the space-assignment plans (e.g. "EECS"). */
  department?: string;
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
  | 'meditation'
  | 'accessible';

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
  accessible: 'Accessible route',
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
  /** Additional separate footprints on this floor (e.g. a detached ground-floor block). */
  islands?: Point[][];
  /** Desk footprints in the open workspaces, drawn for orientation only (not interactive). */
  desks?: Point[][];
  /** The doors the plans show between corridors and open areas (see `Door`). */
  doors?: Door[];
}

/**
 * A door: the doorway along its wall from `a` to `b` (hinge to strike, or hinge to hinge for a
 * pair of leaves) and `open`, where the leaf hinged at `a` stands when open. Every door between
 * corridors and open areas is here for directions; only a door marked `shown` gets a marker.
 */
export interface Door {
  a: Point;
  b: Point;
  open: Point;
  leaves: 1 | 2;
  shown?: boolean;
  name?: string;
}

/** A street next to the building, drawn on every floor for orientation (not interactive). */
export interface Street {
  id: string;
  name: string;
  /** Centre line, in floor coordinates (edges may be arcs via `bulge`). */
  path: Point[];
  /** Carriageway width, in floor units. */
  width: number;
}

export interface Building {
  name: string;
  floors: Floor[];
  spaces: Space[];
  pois: Poi[];
  streets?: Street[];
}
