import type { Space } from './types';

/** The plan room number of a generated space id such as `4-4123` or `0-b1342`; undefined for named rooms. */
export function roomNumber(space: Space): string | undefined {
  const m = /^[^-]+-([a-z]?\d+[a-z]?)$/.exec(space.id);
  return m ? m[1].toUpperCase() : undefined;
}

/**
 * Attach occupants (keyed by plan room number) to the matching spaces. Returns the room
 * numbers that matched no space, so stale directory entries can be reported.
 */
export function assignOccupants(
  spaces: Space[],
  occupants: Record<string, string[]>,
): { spaces: Space[]; unmatched: string[] } {
  const seen = new Set<string>();
  const out = spaces.map((space) => {
    const number = roomNumber(space);
    const people = number ? occupants[number] : undefined;
    if (!number || !people?.length) return space;
    seen.add(number);
    return { ...space, occupants: [...people] };
  });
  const unmatched = Object.keys(occupants).filter((number) => occupants[number].length && !seen.has(number));
  return { spaces: out, unmatched };
}

/** "Michael I. Jordan" → ["Michael I.", "Jordan"], so a name can wrap onto two short map lines. */
export function nameLines(name: string): string[] {
  const at = name.trim().lastIndexOf(' ');
  return at > 0 ? [name.slice(0, at).trim(), name.slice(at + 1).trim()] : [name.trim()];
}
