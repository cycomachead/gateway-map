# Wayfinding: directions from one room to another

*Draft for discussion. Nothing here is built yet; the questions at the end need answers
before the data work starts.*

## What we want

A visitor picks two rooms (or is deep-linked to a pair) and gets a route they can follow:
drawn on the map, floor by floor, with a short list of steps ("Take the Northeast elevator to
Floor 4, turn left, 4123 is the third door on the right"). Routes must work across floors, and
the visitor can ask for one of two things:

- **Wheelchair accessible** (step-free): elevators and ramps only, no stairs, no doors without
  an opener where a heavy door would stop someone, no routes through fare gates they cannot
  open.
- **Minimize walking**: the shortest walk, with stairs allowed and a preference for the
  stair or elevator nearest both ends.

Both are the same search with different costs on the same graph, so the work is mostly in
the data.

## What the map knows today

- Every room is a polygon in one shared frame across all floors (`src/data/gateway/level*.ts`),
  so distances on different floors are directly comparable and the elevator shafts and stairs
  sit on the same points on every floor.
- Circulation is partly explicit: elevators, stairs and the atrium are `circulation` spaces;
  corridors are whatever is left inside the outline. The tracer leaves corridors blank on
  purpose (as the wayfinding signs do).
- Exterior doors are already entrance POIs (`kind: 'exit'`) on Level 1 and the Lower Level.
  Interior doors are known to the tracer: every room is flood-filled from its label through
  its door swing, and the swings are added back to the room polygons so doorways belong to
  rooms. The door positions are not exported yet, but they are one line away in
  `tools/trace_cad/`.
- Rooms carry tags and (soon) departments and occupants, so "from" and "to" can be picked by
  room number, name, person or department with the existing search.

## Proposed design

### 1. A walking graph per floor, generated, with hand-tagged features

Three ways to get a graph were considered:

1. **Hand-drawn corridor centrelines** per floor. Precise and readable, but six floors of
   polylines to draw and keep in step with the traced plans; every tracer re-run risks drift.
2. **A grid over the walkable area** (outline minus rooms, plus the open areas and the atrium
   on floors where it is a floor, not a void), with A* on the grid. Fully automatic and robust
   to re-tracing, but routes hug walls and corners unless smoothed, and the grid is big.
3. **Hybrid (recommended)**: generate a *visibility graph* over the walkable polygon per floor
   (vertices at the walkable area's reflex corners and at every door, edges where the straight
   line stays inside), weight edges by length, then simplify to a navigation mesh if it grows
   too large. Doors and vertical connectors are the only hand-curated nodes; everything else
   is derived. Routes come out as the natural "cut the corner" paths people walk.

The walkable polygon is computed at build time by `tools/trace_cad/` (it already has the
outline and every room) and exported per floor as `walkable: XY[][]` next to `outline` and
`desks`. Open-plan areas count as walkable; desks are obstacles. Rooms are reached through
their door nodes only.

### 2. Doors and connectors as data

New data, generated where possible, edited by hand in a small overlay file where not:

```ts
interface Door {
  id: string;            // '4-4123-door'
  floorId: string;
  spaceId: string;       // the room it opens into
  at: Point;             // on the room's edge, in the floor frame
  features?: DoorFeature[];
}
type DoorFeature = 'auto-opener' | 'card-access' | 'wide' | 'heavy' | 'fire-door' | 'after-hours-locked';

interface Connector {
  id: string;            // 'ne-elevator', 'sw-stair', 'lobby-ramp'
  kind: 'elevator' | 'stairs' | 'ramp' | 'escalator';
  name: string;
  stops: { floorId: string; at: Point }[];   // one entry per floor it serves
  accessible: boolean;   // false for stairs
  features?: ConnectorFeature[];             // 'freight', 'key-operated', 'slow'
}
```

Door positions come from the tracer's door-swing fit (one door per room today, more where
the plan draws more). Connectors are the existing elevator and stair spaces, grouped by name
across floors (`ne-elevator-*` on every floor is one connector with five or six stops).
Features are hand-entered in `src/data/gateway/features.ts`, keyed by door or connector id,
because the plans do not record them.

Locations other than doors can carry the same vocabulary as **tags on spaces**: `'step-free'`,
`'automatic-door'`, `'card-access'`, `'accessible-restroom'`, `'lactation'`, `'quiet'`. The
search and filters already index tags, so "accessible restroom" works the day the tags exist,
before any routing ships.

### 3. The search

One graph with a layer per floor; connector stops are nodes linked to the walkable graph of
their floor, and a connector links its own stops to each other. A* with straight-line distance
as the heuristic (the shared frame makes it admissible across floors with a vertical term).

Costs by mode:

| Edge                         | Minimize walking | Wheelchair accessible |
| ---------------------------- | ---------------- | --------------------- |
| Walking, per metre           | 1                | 1                     |
| Stairs, per floor            | 15 m equivalent  | forbidden             |
| Elevator, per ride           | 30 m (waiting)   | 30 m                  |
| Elevator, per floor          | 3 m              | 3 m                   |
| Door, plain                  | 0                | 0                     |
| Door, `heavy` and no opener  | 0                | 20 m (or forbidden; see questions) |
| Door, `card-access`          | forbidden unless the visitor says they have access | same |
| Fare gates                   | as card-access   | as card-access        |
| Ramp                         | length × 1.2     | length × 1.2          |

The numbers are placeholders to tune by walking a few routes.

### 4. The interface

- A **Directions** button in the room details panel ("Directions to here" / "from here"), and
  a from/to pair of search boxes that reuse the existing search (rooms, people, departments).
- Two toggles: *Wheelchair accessible* and *I have card access*. "Minimize walking" is the
  default when accessible is off.
- The route is drawn as a path on the current floor, with the connector it leaves by
  highlighted; a floor-by-floor **step list** in the panel also works as the screen-reader
  version ("Floor 1: walk 40 m to the Northeast elevator. Floor 4: turn left, 25 m to 4123").
  Clicking a step switches floors and pans.
- URL: `?from=1-1171&to=4-4123&mode=accessible` so routes can be shared and linked from
  room pages or calendar invites.
- Keyboard: the step list is a list of buttons; Escape leaves directions mode.

### 5. Milestones

1. Export doors and the walkable polygon per floor from the tracer; draw them in a debug
   overlay (`?debug=walk`) to check them.
2. Build the per-floor graph and same-floor routes; step list, URL state, tests with a few
   known pairs ("1171 to 1110" must not cross a wall).
3. Add connectors; cross-floor routes; accessible mode.
4. Collect door and connector features (the survey below); card-access mode; tune costs.
5. Turn-by-turn phrasing (left/right relative to walking direction, door counts).

## What other information is needed

Things the plans do not say, best collected by walking the building with a checklist:

- **Doors**: which have automatic openers (and the button's side), which are card-access and
  when (after-hours schedules), which are heavy fire doors, widths narrower than 32 in.
- **Vertical travel**: which elevators serve which floors (does the Southwest bank reach the
  Lower Level and the roof terrace?), freight or key-operated cars, any ramps or short
  flights inside (a few steps into a lecture hall or down to the cafe seating would break a
  "step-free" promise), the stairs that are exit-only.
- **Entrances**: which exterior doors are step-free and automatic, which are the accessible
  entrances the campus access map lists, the grade difference between Hearst Avenue and the
  campus side (which level each entrance lands on), and which doors are open to the public
  versus card-only.
- **Fare gates**: what opens them (Cal 1 card, visitor pass, intercom), hours, and whether
  there is an accessible gate (wider lane) beside the turnstiles.
- **Counters and distances**: a couple of measured corridor lengths to calibrate frame units
  to metres (the plans are to scale, so one measurement per sheet is enough).
- **Destinations people actually ask for**: the front desk's most common questions, to seed
  tests and the step phrasing.
- **Accessible amenities** to tag: accessible restrooms, lactation and meditation rooms,
  adjustable-height desks in open areas, hearing loops in lecture halls.

## Open questions

1. Is "wheelchair accessible" a hard filter (never a heavy door) or a cost (prefer, then warn)?
   Hard filter is simpler to explain; a cost gives a route where none would otherwise exist.
2. Should routes assume the visitor can pass the fare gates? Default to "no" and show both?
3. Do we want turn-by-turn text, or is the drawn path plus "take elevator X to floor Y" enough
   for a first version?
4. Who maintains the features file? If the facilities office will, it should be a spreadsheet
   or form rather than TypeScript, imported like the directory and the department sheets.
5. Outdoor legs: do we route between entrances around the outside of the building (Hearst to
   campus side), or stop at the nearest entrance?
