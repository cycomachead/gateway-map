import './style.css';
import { building, DEFAULT_FLOOR_ID } from './data/building';
import type { Floor } from './data/types';
import { validateBuilding } from './data/validate';
import { bbox, pad } from './map/geometry';
import { attachPanZoom } from './map/panzoom';
import { renderFloor, spaceIdFromEvent } from './map/render';
import { createStore } from './state';
import { mountFilters } from './ui/filters';
import { mountFloorSwitcher } from './ui/floors';
import { mountPanel } from './ui/panel';
import { mountSearchBox } from './ui/search';

const problems = validateBuilding(building);
if (problems.length) console.error('Building data problems:\n' + problems.join('\n'));

const $ = <T extends HTMLElement>(sel: string) => document.querySelector<T>(sel)!;

const svg = $<HTMLElement>('#map') as unknown as SVGSVGElement;

const store = createStore({
  floorId: building.floors.some((f) => f.id === DEFAULT_FLOOR_ID) ? DEFAULT_FLOOR_ID : building.floors[0].id,
  selectedSpaceId: null,
  hoveredSpaceId: null,
  query: '',
  categories: new Set(),
});

const floorLabel = (id: string) => building.floors.find((f) => f.id === id)?.label ?? id;
const panzoom = attachPanZoom(svg);

// ---- Map ------------------------------------------------------------------
let mountedFloorId: string | null = null;

function mountFloor(floorId: string) {
  const floor = building.floors.find((f) => f.id === floorId);
  if (!floor) return;
  svg.replaceChildren(renderFloor(building, floor));
  fitFloor(floor);
  mountedFloorId = floorId;
}

function fitFloor(floor: Floor) {
  // Fit the whole footprint, including detached blocks (e.g. Level 1's Southwest block).
  panzoom.fit(pad(bbox([floor.outline, ...(floor.islands ?? [])].flat()), 24));
}

function syncSpaceClasses(selectedId: string | null, categories: Set<string>) {
  svg.querySelectorAll<SVGGElement>('[data-space-id]').forEach((g) => {
    const id = g.dataset.spaceId!;
    const space = building.spaces.find((s) => s.id === id)!;
    g.classList.toggle('is-selected', id === selectedId);
    const dimmed =
      categories.size > 0 && space.category !== 'circulation' && !categories.has(space.category);
    g.classList.toggle('is-dimmed', dimmed);
  });
}

svg.addEventListener('click', (e) => {
  const id = spaceIdFromEvent(e);
  if (id) store.set({ selectedSpaceId: id });
});
svg.addEventListener('keydown', (e) => {
  if (e.key !== 'Enter' && e.key !== ' ') return;
  const id = spaceIdFromEvent(e);
  if (id) {
    store.set({ selectedSpaceId: id });
    e.preventDefault();
  }
});
svg.addEventListener('pointerover', (e) => {
  const id = spaceIdFromEvent(e);
  if (id !== store.get().hoveredSpaceId) store.set({ hoveredSpaceId: id });
});
svg.addEventListener('pointerleave', () => store.set({ hoveredSpaceId: null }));

// ---- Tooltip --------------------------------------------------------------
const tooltip = $('#tooltip');
svg.addEventListener('pointermove', (e) => {
  const id = store.get().hoveredSpaceId;
  if (!id) return;
  tooltip.style.transform = `translate(${e.clientX + 14}px, ${e.clientY + 14}px)`;
});

// ---- Controls -------------------------------------------------------------
mountFloorSwitcher($('#floors'), building.floors, store);
mountFilters($('#filters'), store);
mountPanel($('#panel'), building, store);
mountSearchBox($('#search'), {
  spaces: building.spaces.filter((s) => s.category !== 'circulation'),
  floorLabel,
  onPick: (space) => store.set({ floorId: space.floorId, selectedSpaceId: space.id }),
});
$('#zoom-in').addEventListener('click', () => panzoom.zoomBy(1.4));
$('#zoom-out').addEventListener('click', () => panzoom.zoomBy(1 / 1.4));
$('#zoom-fit').addEventListener('click', () => {
  if (store.get().selectedSpaceId) store.set({ selectedSpaceId: null });
  else fitFloor(building.floors.find((f) => f.id === store.get().floorId)!);
});

// ---- Wire state → view ----------------------------------------------------
store.subscribe((s, prev) => {
  if (s.floorId !== mountedFloorId) mountFloor(s.floorId);

  syncSpaceClasses(s.selectedSpaceId, s.categories);

  if (s.selectedSpaceId && s.selectedSpaceId !== prev.selectedSpaceId) {
    const space = building.spaces.find((sp) => sp.id === s.selectedSpaceId);
    if (space) panzoom.fit(pad(bbox(space.polygon), 120));
  } else if (!s.selectedSpaceId && prev.selectedSpaceId) {
    fitFloor(building.floors.find((f) => f.id === s.floorId)!);
  }

  const hovered = s.hoveredSpaceId ? building.spaces.find((sp) => sp.id === s.hoveredSpaceId) : null;
  tooltip.hidden = !hovered;
  if (hovered) tooltip.textContent = hovered.name;
});
