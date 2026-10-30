/**
 * Hand corrections to the room occupants the directory and the space-assignment sheets give
 * (`occupants.ts`, `sheet_occupants.ts` are generated; this file is kept by hand). Keyed by
 * plan room number: `vacant` empties the room, `remove` drops the people named (matched the
 * way duplicates are, so a spelling off by a letter still matches).
 */
export const OCCUPANT_FIXES: Record<string, { vacant?: true; remove?: string[] }> = {
  '4115': { vacant: true },
  '4128': { remove: ['Ari Edmundson', 'Ramesh Sridharan'] },
};
