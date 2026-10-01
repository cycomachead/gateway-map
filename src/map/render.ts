import type { Building, Floor, Poi, Space, Street } from '../data/types';
import { POI_LABELS } from '../data/types';
import { centroid, toPath } from './geometry';

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
};

function renderSpace(space: Space): SVGGElement {
  const g = el('g', {
    class: `space space--${space.category}`,
    'data-space-id': space.id,
    tabindex: 0,
    role: 'button',
    'aria-label': space.name,
  });
  const d = [space.polygon, ...(space.holes ?? [])].map((p) => toPath(p)).join(' ');
  g.appendChild(el('path', { d, class: 'space__shape' }));

  const c = centroid(space.polygon);
  const label = el('text', {
    x: c.x,
    y: c.y,
    class: 'space__label',
    'text-anchor': 'middle',
    'dominant-baseline': 'middle',
  });
  label.textContent = space.label ?? space.name;
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
