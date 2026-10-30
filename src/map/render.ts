import type { Building, Door, Floor, Poi, Point, Space, SpaceIcon, Street } from '../data/types';
import { POI_LABELS } from '../data/types';
import { nameLines } from '../data/occupants';
import { labelPoint, toPath } from './geometry';

const SVG_NS = 'http://www.w3.org/2000/svg';

function el<K extends keyof SVGElementTagNameMap>(
  tag: K,
  attrs: Record<string, string | number> = {},
): SVGElementTagNameMap[K] {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  return node;
}

const POI_GLYPH: Record<Poi['kind'], string> = {
  elevator: '⇕',
  stairs: '≡',
  restroom: 'WC',
  exit: '⇥',
  cafe: '☕',
  info: 'i',
  porch: '⌂',
  lactation: '♥',
  meditation: '❁',
  accessible: '♿',
};

/** Restroom pictograms (24 × 24 boxes): a standing man, a woman, and the two side by side. */
const ICON_PATHS: Record<SpaceIcon, string> = {
  man: 'M12 1a2.4 2.4 0 1 1 0 4.8A2.4 2.4 0 0 1 12 1zM8.6 7h6.8l1.8 7.4h-1.9l-1.2-4.9V23h-2.2v-7.8h-1V23H8.7V9.5l-1.2 4.9H5.6z',
  woman: 'M12 1a2.4 2.4 0 1 1 0 4.8A2.4 2.4 0 0 1 12 1zM9.2 7h5.6l2.1 7.4h-1.8l-.9-3.3 1.9 6.4h-2.3V23h-2v-5.5h-.6V23h-2v-5.5H6.9l1.9-6.4-.9 3.3H6.1z',
  'all-gender':
    'M7 2.2a1.9 1.9 0 1 1 0 3.8 1.9 1.9 0 0 1 0-3.8zM4.4 7h5.2l1.4 5.9H9.5l-.9-3.9V23H6.9v-6.2h-.8V23H4.4V9l-.9 3.9H2z' +
    'M17 2.2a1.9 1.9 0 1 1 0 3.8 1.9 1.9 0 0 1 0-3.8zM14.8 7h4.4l1.7 5.9h-1.5l-.7-2.6 1.5 5.1h-1.9V23h-1.6v-4.6h-.5V23h-1.6v-4.6h-1.9l1.5-5.1-.7 2.6h-1.5z',
  // a flight of steps climbing to the right
  stairs: 'M2 22V17h5v-5h5V7h5V2h5v20z',
};

const ICON_SIZE = 16;

function renderSpace(space: Space): SVGGElement {
  const g = el('g', {
    class: `space space--${space.category}${space.tags?.includes('suite') ? ' space--suite' : ''}`,
    'data-space-id': space.id,
    tabindex: 0,
    role: 'button',
    'aria-label': space.occupants?.length ? `${space.name}, ${space.occupants.join(', ')}` : space.name,
  });
  const d = [space.polygon, ...(space.holes ?? [])].map((p) => toPath(p)).join(' ');
  g.appendChild(el('path', { d, class: 'space__shape' }));

  const c = labelPoint(space.polygon);
  // A pictogram (the restroom signs, a stair) sits above the text, the two centred as one block.
  // A stair too small for both (a landing drawn on its own) keeps just its label.
  const box = extent(space.polygon);
  const fits = box.width >= 2 * ICON_SIZE && box.height >= 3 * ICON_SIZE;
  const icon = space.icon && (space.icon !== 'stairs' || fits) ? space.icon : undefined;
  const iconHeight = icon ? ICON_SIZE + 2 : 0;
  if (icon) {
    g.appendChild(
      el('path', {
        d: ICON_PATHS[icon],
        class: 'space__icon',
        transform: `translate(${c.x - ICON_SIZE / 2} ${c.y - iconHeight / 2 - ICON_SIZE / 2 - 2}) scale(${ICON_SIZE / 24})`,
      }),
    );
  }
  const label = el('text', {
    x: c.x,
    y: c.y + iconHeight / 2,
    class: 'space__label',
    'text-anchor': 'middle',
    'dominant-baseline': 'middle',
  });
  // The label's lines (a restroom's "Gender / Neutral" is wrapped, and then drawn small
  // throughout), then each occupant's name wrapped onto short lines, centred as one block.
  const [title, ...more] = (space.label ?? space.name).split('\n');
  const lines = [...more, ...(space.occupants ?? []).flatMap(nameLines)];
  if (!lines.length) {
    label.textContent = title;
  } else {
    const lineHeight = 10;
    const first = el('tspan', { x: c.x, dy: -(lines.length * lineHeight) / 2, ...(more.length ? { class: 'space__label-name' } : {}) });
    first.textContent = title;
    label.appendChild(first);
    lines.forEach((line, i) => {
      const t = el('tspan', { x: c.x, dy: i === 0 ? lineHeight + (more.length ? 0 : 2) : lineHeight, class: 'space__label-name' });
      t.textContent = line;
      label.appendChild(t);
    });
  }
  g.appendChild(label);
  return g;
}

function renderPoi(poi: Poi): SVGGElement {
  const g = el('g', {
    class: `poi poi--${poi.kind}`,
    transform: `translate(${poi.at.x} ${poi.at.y})`,
    'data-poi-id': poi.id,
  });
  const title = el('title');
  title.textContent = `${poi.name} (${POI_LABELS[poi.kind]})` + (poi.description ? `\n${poi.description}` : '');
  g.appendChild(title);
  g.appendChild(el('circle', { r: 12, class: 'poi__dot' }));
  const t = el('text', {
    class: 'poi__glyph',
    'text-anchor': 'middle',
    'dominant-baseline': 'central',
  });
  t.textContent = POI_GLYPH[poi.kind];
  g.appendChild(t);
  return g;
}

/** A street: the carriageway as a wide stroke, a dashed centre line and its name along it. */
function renderStreet(street: Street): SVGGElement {
  const g = el('g', { class: 'street', 'data-street-id': street.id, 'aria-hidden': 'true' });
  const d = toPath(street.path, false);
  const pathId = `street-${street.id}`;
  g.appendChild(el('path', { d, class: 'street__road', 'stroke-width': street.width }));
  g.appendChild(el('path', { d, id: pathId, class: 'street__centre' }));
  const text = el('text', { class: 'street__name', dy: '0.35em' });
  const along = el('textPath', { href: `#${pathId}`, startOffset: '40%', 'text-anchor': 'middle' });
  along.textContent = street.name;
  text.appendChild(along);
  g.appendChild(text);
  return g;
}

const fmt = (n: number) => String(Math.round(n * 10) / 10);

/** The axis-aligned extent of some points. */
function extent(points: Point[]): { x: number; y: number; width: number; height: number } {
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const x = Math.min(...xs);
  const y = Math.min(...ys);
  return { x, y, width: Math.max(...xs) - x, height: Math.max(...ys) - y };
}

const DOOR_R = 9;
const xy = (p: Point) => `${fmt(p.x)} ${fmt(p.y)}`;

/**
 * A door marker: a circle on the doorway holding the door's own swing in miniature, drawn the
 * way it stands on the plan, so the arc shows which way the door opens.
 */
function renderDoor(door: Door): SVGGElement {
  const m = { x: (door.a.x + door.b.x) / 2, y: (door.a.y + door.b.y) / 2 };
  const g = el('g', { class: 'door', transform: `translate(${xy(m)})` });
  const title = el('title');
  title.textContent = door.name ?? (door.leaves === 2 ? 'Double door' : 'Door');
  g.appendChild(title);
  g.appendChild(el('circle', { r: DOOR_R, class: 'door__dot' }));
  g.appendChild(el('path', { d: swingPath(door, DOOR_R * 1.4), class: 'door__glyph' }));
  return g;
}

/** The door's swing (leaf and arc per leaf), centred on the origin and scaled to fit `size`. */
function swingPath(door: Door, size: number): string {
  const m = { x: (door.a.x + door.b.x) / 2, y: (door.a.y + door.b.y) / 2 };
  const rel = (p: Point) => ({ x: p.x - m.x, y: p.y - m.y });
  const a = rel(door.a);
  const b = rel(door.b);
  const o = rel(door.open);
  let leaves: [Point, Point, Point][]; // hinge, open end, strike
  if (door.leaves === 2) {
    // Both leaves open to the side of `open`, each over half the doorway, and meet in the middle.
    const n = { x: o.x - a.x, y: o.y - a.y };
    const len = Math.hypot(n.x, n.y) || 1;
    const half = Math.hypot(b.x - a.x, b.y - a.y) / 2;
    const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    leaves = [
      [a, { x: a.x + (n.x / len) * half, y: a.y + (n.y / len) * half }, mid],
      [b, { x: b.x + (n.x / len) * half, y: b.y + (n.y / len) * half }, mid],
    ];
  } else {
    leaves = [[a, o, b]];
  }
  // Each swing fills the square spanned by its hinge, open end and strike: fit those squares.
  const box = extent(leaves.flatMap(([h, op, s]) => [h, op, s, { x: op.x + s.x - h.x, y: op.y + s.y - h.y }]));
  const scale = size / Math.max(box.width, box.height, 1);
  const T = (p: Point) => ({ x: (p.x - box.x - box.width / 2) * scale, y: (p.y - box.y - box.height / 2) * scale });
  return leaves
    .map(([h, op, s]) => {
      const H = T(h);
      const O = T(op);
      const S = T(s);
      const r = Math.hypot(O.x - H.x, O.y - H.y);
      const sweep = (O.x - H.x) * (S.y - H.y) - (O.y - H.y) * (S.x - H.x) > 0 ? 1 : 0;
      return `M${xy(H)} L${xy(O)} A${fmt(r)} ${fmt(r)} 0 0 ${sweep} ${xy(S)}`;
    })
    .join(' ');
}

/** Builds the SVG subtree for one floor. Caller decides where to mount it. */
export function renderFloor(building: Building, floor: Floor): SVGGElement {
  const root = el('g', { class: 'floor', 'data-floor-id': floor.id });
  for (const street of building.streets ?? []) root.appendChild(renderStreet(street));
  root.appendChild(el('path', { d: toPath(floor.outline), class: 'floor__outline' }));
  for (const island of floor.islands ?? []) root.appendChild(el('path', { d: toPath(island), class: 'floor__outline' }));

  // Furniture sits under the (translucent) spaces so it never hides a label or takes a click.
  if (floor.desks?.length) {
    const furniture = el('g', { class: 'furniture', 'aria-hidden': 'true' });
    for (const desk of floor.desks) furniture.appendChild(el('path', { d: toPath(desk), class: 'desk' }));
    root.appendChild(furniture);
  }

  const spaces = el('g', { class: 'spaces' });
  for (const s of building.spaces) if (s.floorId === floor.id) spaces.appendChild(renderSpace(s));
  root.appendChild(spaces);

  const pois = el('g', { class: 'pois' });
  for (const p of building.pois) if (p.floorId === floor.id) pois.appendChild(renderPoi(p));
  root.appendChild(pois);

  // Doors are data for directions; only the ones marked to be shown get a marker.
  const shown = floor.doors?.filter((d) => d.shown) ?? [];
  if (shown.length) {
    const doors = el('g', { class: 'doors' });
    for (const door of shown) doors.appendChild(renderDoor(door));
    root.appendChild(doors);
  }

  return root;
}

/**
 * Resolve a space id from an event inside a rendered space group.
 *
 * While the pointer is captured (see panzoom), browsers retarget pointer and click
 * events to the capturing <svg>, so for mouse events we also hit-test by position.
 */
export function spaceIdFromEvent(ev: Event): string | null {
  let target = ev.target as Element | null;
  if (target instanceof SVGSVGElement && ev instanceof MouseEvent && document.elementFromPoint) {
    target = document.elementFromPoint(ev.clientX, ev.clientY);
  }
  const g = target?.closest<SVGGElement>('[data-space-id]');
  return g?.dataset.spaceId ?? null;
}
