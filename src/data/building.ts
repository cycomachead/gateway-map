import { pts, type XY } from './helpers';
import { FLOOR_DEFINITIONS } from './floors';
import { poisFrom, spacesFrom, type PoiSpec, type RoomSpec, doorsFrom } from './gateway/floor';
import type { DoorSpec } from './gateway/floor';
import { FRAME } from './gateway/frame';
import * as l0 from './gateway/level0';
import * as l1 from './gateway/level1';
import * as l2 from './gateway/level2';
import * as l3 from './gateway/level3';
import * as l4 from './gateway/level4';
import * as l5 from './gateway/level5';
import { DEPARTMENTS, RESERVABLE } from './gateway/departments';
import { OCCUPANTS } from './gateway/occupants';
import { SHEET_OCCUPANTS } from './gateway/sheet_occupants';
import { OCCUPANT_FIXES } from './gateway/occupant_fixes';
import { hearst } from './gateway/streets';
import { assignDepartments } from './departments';
import { assignOccupants, fixOccupants, mergeOccupants } from './occupants';
import type { Building, Floor, Space } from './types';

/**
 * Gateway building (UC Berkeley College of Computing, Data Science, and Society).
 *
 * Every level is generated from the CAD plan-view PDFs by `tools/trace_cad/` (rooms are
 * flood-filled from the plan's room labels, outlines are the exterior walls) and drawn in one
 * shared coordinate frame, so walls and cores line up exactly when switching floors. Who sits
 * where comes from `gateway/occupants.ts` (the EECS directory) and `gateway/sheet_occupants.ts`
 * (the names written on the colour-shaded space-assignment plans), and which department a
 * room belongs to from `gateway/departments.ts` (the plans' shading).
 */
/** What a generated `level*.ts` module exports (`desks` and `doors` arrived later, so older modules may lack them). */
type LevelModule = { outline: XY[]; islands: XY[][]; rooms: RoomSpec[]; pois: PoiSpec[]; desks?: XY[][]; doors?: DoorSpec[] };

const levelData = { '0': l0, '1': l1, '2': l2, '3': l3, '4': l4, '5': l5 };
const levels: ReadonlyArray<readonly [id: string, label: string, level: number, data: LevelModule]> =
  FLOOR_DEFINITIONS.map(([id, label, level]) => [id, label, level, levelData[id]]);

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
  ...(l.doors?.length ? { doors: doorsFrom(l.doors) } : {}),
}));

const occupied = assignOccupants(
  levels.flatMap(([id, , , l]): Space[] => spacesFrom(id, l.rooms)),
  fixOccupants(mergeOccupants(OCCUPANTS, SHEET_OCCUPANTS), OCCUPANT_FIXES),
);
const assigned = assignDepartments(occupied.spaces, DEPARTMENTS, RESERVABLE);
const spaces = assigned.spaces;

/** Directory rooms (see `gateway/occupants.ts`) that match no space on any floor. */
export const unplacedOccupantRooms: string[] = occupied.unmatched;
/** Space ids in `gateway/departments.ts` that match no space on any floor. */
export const unplacedDepartmentRooms: string[] = assigned.unmatched;
const pois = levels.flatMap(([id, , , l]) => poisFrom(id, l.pois));

export const building: Building = {
  name: 'Gateway',
  floors,
  spaces,
  pois,
  streets: [{ id: 'hearst', name: 'Hearst Avenue', path: pts(hearst.path), width: hearst.width }],
};
