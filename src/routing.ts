import { building, DEFAULT_FLOOR_ID } from './data/building';
import type { AppState, Store } from './state';

type Route = Pick<AppState, 'floorId' | 'selectedSpaceId'>;

const base = import.meta.env.BASE_URL;
const floorPath = (floorId: string) => `${base}floor-${floorId}`;

/** Only accept rooms belonging to the floor in the path. */
export function readRoute(): Route {
  const url = new URL(window.location.href);
  const path = url.pathname.replace(/\/$/, '');
  const floor = building.floors.find((f) => floorPath(f.id) === path);
  const floorId = floor?.id ?? DEFAULT_FLOOR_ID;
  const roomId = url.searchParams.get('room');
  const room = building.spaces.find((s) => s.id === roomId && s.floorId === floorId);
  return { floorId, selectedSpaceId: room?.id ?? null };
}

/** Keep shareable URLs and browser history in sync with every selection control. */
export function mountRouting(store: Store) {
  function writeRoute(route: Route, replace = false) {
    const url = new URL(window.location.href);
    url.pathname = floorPath(route.floorId);
    if (route.selectedSpaceId) url.searchParams.set('room', route.selectedSpaceId);
    else url.searchParams.delete('room');
    if (url.href !== window.location.href) {
      if (replace) window.history.replaceState(null, '', url);
      else window.history.pushState(null, '', url);
    }
  }

  // Normalize the root, trailing slashes, and invalid selections without adding history.
  writeRoute(store.get(), true);
  store.subscribe((state, prev) => {
    if (state.floorId !== prev.floorId || state.selectedSpaceId !== prev.selectedSpaceId) {
      writeRoute(state);
    }
  });
  window.addEventListener('popstate', () => {
    const route = readRoute();
    writeRoute(route, true);
    // The URL already matches, so the subscription won't add a history entry.
    store.set({ ...route, hoveredSpaceId: null });
  });
}
