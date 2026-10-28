import './style.css';
import { building, unplacedDepartmentRooms, unplacedOccupantRooms } from './data/building';
import type { Floor, Space, SpaceCategory } from './data/types';
import { validateBuilding } from './data/validate';
import { bbox, centroid, pad, streetBox, unionBox } from './map/geometry';
import { nearestInDirection, nearestTo, type Direction } from './map/navigate';
import { attachPanZoom } from './map/panzoom';
import { renderFloor, spaceIdFromEvent } from './map/render';
import { createStore, isFilteredOut } from './state';
import { mountRouting, readRoute } from './routing';
import { announce } from './ui/announce';
import { openDialog, setupDialog } from './ui/dialog';
import { mountFilters } from './ui/filters';
import { mountFloorSwitcher } from './ui/floors';
import { mountPanel } from './ui/panel';
import { spaceTitle } from './ui/names';
import { mountSearchBox } from './ui/search';
import { mountShortcuts, mountShortcutsDialog } from './ui/shortcuts';

const problems = [
  ...validateBuilding(building),
  ...unplacedOccupantRooms.map((n) => `Occupants listed for room "${n}", which is not on any floor`),
  ...unplacedDepartmentRooms.map((id) => `Department listed for space "${id}", which is not on any floor`),
];
if (problems.length) console.error('Building data problems:\n' + problems.join('\n'));

const $ = <T extends HTMLElement>(sel: string) => document.querySelector<T>(sel)!;

const svg = $<HTMLElement>('#map') as unknown as SVGSVGElement;

const store = createStore({
  ...readRoute(),
  hoveredSpaceId: null,
  query: '',
  categories: new Set(),
  allFloors: false,
});
mountRouting(store);

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
  // Fit the whole footprint, including detached blocks (e.g. Level 1's Southwest block),
  // and the stretch of street in front of it (its name is drawn there).
  const footprint = bbox([floor.outline, ...(floor.islands ?? [])].flat());
  panzoom.fit(pad(unionBox(footprint, ...building.streets?.map((s) => streetBox(s, footprint)) ?? []), 24));
}

function syncSpaceClasses(selectedId: string | null, categories: Set<SpaceCategory>) {
  svg.querySelectorAll<SVGGElement>('[data-space-id]').forEach((g) => {
    const id = g.dataset.spaceId!;
    const space = building.spaces.find((s) => s.id === id)!;
    g.classList.toggle('is-selected', id === selectedId);
    g.classList.toggle('is-dimmed', isFilteredOut(space, categories));
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
const floorSwitcher = mountFloorSwitcher($('#floors'), building.floors, store);
mountFilters($('#filters'), store);
mountPanel($('#panel'), building, store);
mountSearchBox($('#search'), {
  spaces: building.spaces.filter((s) => s.category !== 'circulation'),
  floorLabel,
  onPick: (space) => store.set({ floorId: space.floorId, selectedSpaceId: space.id }),
});

const zoomBy = (factor: number) => {
  panzoom.zoomBy(factor);
  announce(`Zoom ${Math.round(panzoom.zoom() * 100)}%`);
};
$('#zoom-in').addEventListener('click', () => zoomBy(1.4));
$('#zoom-out').addEventListener('click', () => zoomBy(1 / 1.4));
$('#zoom-fit').addEventListener('click', () => {
  if (store.get().selectedSpaceId) store.set({ selectedSpaceId: null });
  else fitFloor(building.floors.find((f) => f.id === store.get().floorId)!);
});

// ---- Dialogs and keyboard shortcuts ----------------------------------------
const aboutDialog = $<HTMLDialogElement>('#about');
const shortcutsDialog = $<HTMLDialogElement>('#shortcuts');
setupDialog(aboutDialog);
setupDialog(shortcutsDialog);
const help = mountShortcutsDialog(shortcutsDialog);
$('#about-btn').addEventListener('click', () => openDialog(aboutDialog));
$('#shortcuts-btn').addEventListener('click', help.toggle);
$('#about-shortcuts').addEventListener('click', () => {
  aboutDialog.close();
  help.toggle();
});

const spaceElement = (id: string) => svg.querySelector<SVGGElement>(`[data-space-id="${CSS.escape(id)}"]`);

/** Focus a room on the map, panning just enough to show it; the room's label is read out. */
function focusSpace(space: Space) {
  const g = spaceElement(space.id);
  if (!g) return;
  panzoom.panToInclude(bbox(space.polygon));
  g.focus({ preventScroll: true });
}

/** The room keyboard navigation starts from: the focused room, else the selected one. */
function currentSpace(): Space | null {
  const focused = document.activeElement?.closest<SVGGElement>('[data-space-id]');
  const id = focused && svg.contains(focused) ? focused.dataset.spaceId! : store.get().selectedSpaceId;
  const space = id ? building.spaces.find((sp) => sp.id === id) : null;
  return space && space.floorId === store.get().floorId ? space : null;
}

function moveFocus(dir: Direction) {
  const { floorId, categories } = store.get();
  const current = currentSpace();
  // Rooms only: corridors and the atrium are landmarks to walk across, not stops.
  const candidates = building.spaces
    .filter((sp) => sp.floorId === floorId && sp !== current && sp.category !== 'circulation' && !isFilteredOut(sp, categories))
    .map((sp) => ({ item: sp, box: bbox(sp.polygon), centre: centroid(sp.polygon) }));
  let next: Space | null;
  if (current) {
    next = nearestInDirection(centroid(current.polygon), bbox(current.polygon), candidates, dir);
  } else {
    // Nothing to start from: pick up at the middle of what is on screen.
    const v = panzoom.view();
    next = nearestTo({ x: v.x + v.width / 2, y: v.y + v.height / 2 }, candidates);
  }
  if (!next) {
    announce(current ? `No rooms further ${dir} from ${current.name}` : 'No rooms on this floor match the filters');
    return;
  }
  focusSpace(next);
}

mountShortcuts({
  focusSearch() {
    const input = $<HTMLInputElement>('#search .search__input');
    input.focus();
    input.select();
  },
  zoomIn: () => zoomBy(1.4),
  zoomOut: () => zoomBy(1 / 1.4),
  goToFloor(floorId) {
    if (!building.floors.some((f) => f.id === floorId)) return;
    const s = store.get();
    if (s.floorId !== floorId || s.selectedSpaceId) store.set({ floorId, selectedSpaceId: null, hoveredSpaceId: null });
    // The pressed floor button announces the new floor; the panel reads its summary.
    floorSwitcher.focus(floorId);
  },
  moveFocus,
  clearSelection() {
    const id = store.get().selectedSpaceId;
    if (!id) return false;
    store.set({ selectedSpaceId: null });
    // "Back to floor" leaves the details panel, so hand focus to the room on the map.
    const space = building.spaces.find((sp) => sp.id === id);
    if (space) focusSpace(space);
    return true;
  },
  toggleHelp: help.toggle,
});

// ---- Wire state → view ----------------------------------------------------
store.subscribe((s, prev) => {
  const floorChanged = s.floorId !== mountedFloorId;
  if (floorChanged) mountFloor(s.floorId);

  syncSpaceClasses(s.selectedSpaceId, s.categories);

  if (s.selectedSpaceId && (floorChanged || s.selectedSpaceId !== prev.selectedSpaceId)) {
    const space = building.spaces.find((sp) => sp.id === s.selectedSpaceId);
    if (space) panzoom.fit(pad(bbox(space.polygon), 120));
  } else if (!s.selectedSpaceId && prev.selectedSpaceId) {
    fitFloor(building.floors.find((f) => f.id === s.floorId)!);
  }

  const hovered = s.hoveredSpaceId ? building.spaces.find((sp) => sp.id === s.hoveredSpaceId) : null;
  tooltip.hidden = !hovered;
  if (hovered) tooltip.textContent = spaceTitle(hovered);
});
