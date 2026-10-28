import type { Space } from './types';

/**
 * Attach departments (keyed by space id, see `gateway/departments.ts`) to the matching spaces,
 * and tag the reservable meeting rooms. Returns the ids that matched no space, so a stale
 * import can be reported.
 */
export function assignDepartments(
  spaces: Space[],
  departments: Record<string, string>,
  reservable: string[],
): { spaces: Space[]; unmatched: string[] } {
  const ids = new Set(spaces.map((s) => s.id));
  const bookable = new Set(reservable);
  const out = spaces.map((space) => {
    const department = departments[space.id];
    const tags = bookable.has(space.id) ? [...(space.tags ?? []), 'reservable'] : space.tags;
    if (!department && tags === space.tags) return space;
    return { ...space, ...(department ? { department } : {}), ...(tags ? { tags } : {}) };
  });
  const unmatched = [...Object.keys(departments), ...reservable].filter((id) => !ids.has(id));
  return { spaces: out, unmatched };
}
