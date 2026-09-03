import { ellipse } from './helpers';
import { poisFrom, spacesFrom } from './gateway/floor';
import * as l1 from './gateway/level1';
import * as l2 from './gateway/level2';
import * as l3 from './gateway/level3';
import { level4 } from './gateway/level4';
import { FRAME, outline1, outline1sw, outline2, outline34 } from './gateway/outline';
import type { Building, Floor, Point, Space } from './types';

/**
 * Gateway building (UC Berkeley College of Computing, Data Science, and Society).
 *
 * Every floor is drawn in one shared coordinate frame so the exterior walls line up
 * exactly when switching floors; the outline vertices live in `gateway/outline.ts`.
 *
 *  - Levels 1–3 are generated from perspective-corrected photos of the wayfinding signs
 *    (`floorplans/`, `tools/trace_signs/`): rooms are segmented from the detail signs,
 *    warped onto the shared outline and snapped to its walls.
 *  - Level 4 was traced by hand (`gateway/level4.ts`).
 */

const floor = (id: string, level: number, outline: Point[], islands?: Point[][]): Floor => ({
  id,
  label: id,
  level,
  width: FRAME.width,
  height: FRAME.height,
  outline,
  ...(islands ? { islands } : {}),
});

const floors: Floor[] = [
  floor('1', 1, outline1, [outline1sw]),
  floor('2', 2, outline2),
  floor('3', 3, outline34),
  floor('4', 4, outline34),
];

const atriumStair = (floorId: string, a: { cx: number; cy: number; rx: number; ry: number }): Space => ({
  id: `${floorId}-atrium-stair`,
  name: 'Atrium Stair',
  label: 'Atrium Stair',
  floorId,
  category: 'circulation',
  polygon: ellipse(a.cx, a.cy, a.rx, a.ry),
  description: 'The open stair through the central atrium connecting all levels.',
  tags: ['stairs', 'atrium'],
});

const generated = [
  ['1', l1],
  ['2', l2],
  ['3', l3],
] as const;

const spaces: Space[] = [
  ...generated.flatMap(([id, l]) => [...spacesFrom(id, l.rooms), atriumStair(id, l.atrium)]),
  ...level4.spaces,
];

const pois = [...generated.flatMap(([id, l]) => poisFrom(id, l.pois)), ...level4.pois];

export const building: Building = {
  name: 'Gateway',
  floors,
  spaces,
  pois,
};
