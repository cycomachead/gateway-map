import { pts, type XY } from './helpers';
import { poisFrom, spacesFrom, type PoiSpec, type RoomSpec } from './gateway/floor';
import { FRAME } from './gateway/frame';
import * as l0 from './gateway/level0';
import * as l1 from './gateway/level1';
import * as l2 from './gateway/level2';
import * as l3 from './gateway/level3';
import * as l4 from './gateway/level4';
import * as l5 from './gateway/level5';
import type { Building, Floor, Space } from './types';

/**
 * Gateway building (UC Berkeley College of Computing, Data Science, and Society).
 *
 * Every level is generated from the CAD plan-view PDFs by `tools/trace_cad/` (rooms are
 * flood-filled from the plan's room labels, outlines are the exterior walls) and drawn in one
 * shared coordinate frame, so walls and cores line up exactly when switching floors.
 */
/** What a generated `level*.ts` module exports (`desks` arrived later, so older modules may lack it). */
type LevelModule = { outline: XY[]; islands: XY[][]; rooms: RoomSpec[]; pois: PoiSpec[]; desks?: XY[][] };

const levels: ReadonlyArray<readonly [id: string, label: string, level: number, data: LevelModule]> = [
  ['0', 'LL', 0, l0],
  ['1', '1', 1, l1],
  ['2', '2', 2, l2],
  ['3', '3', 3, l3],
  ['4', '4', 4, l4],
  ['5', '5', 5, l5],
];

/** The floor shown on load: the street-level entrance floor. */
export const DEFAULT_FLOOR_ID = '1';

const floors: Floor[] = levels.map(([id, label, level, l]) => ({
  id,
  label,
  level,
  width: FRAME.width,
  height: FRAME.height,
  outline: pts(l.outline),
  ...(l.islands.length ? { islands: l.islands.map(pts) } : {}),
  ...(l.desks?.length ? { desks: l.desks.map(pts) } : {}),
}));

const spaces: Space[] = levels.flatMap(([id, , , l]) => spacesFrom(id, l.rooms));
const pois = levels.flatMap(([id, , , l]) => poisFrom(id, l.pois));

export const building: Building = {
  name: 'Gateway',
  floors,
  spaces,
  pois,
};
