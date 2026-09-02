import type { SpaceCategory } from './data/types';

export interface AppState {
  floorId: string;
  selectedSpaceId: string | null;
  hoveredSpaceId: string | null;
  query: string;
  /** Empty set = show everything. */
  categories: Set<SpaceCategory>;
}

type Listener = (state: AppState, prev: AppState) => void;

/** Minimal observable store; enough for a handful of panels sharing state. */
export function createStore(initial: AppState) {
  let state = initial;
  const listeners = new Set<Listener>();

  return {
    get: () => state,
    set(patch: Partial<AppState>) {
      const prev = state;
      state = { ...state, ...patch };
      for (const l of listeners) l(state, prev);
    },
    subscribe(l: Listener) {
      listeners.add(l);
      l(state, state);
      return () => listeners.delete(l);
    },
  };
}

export type Store = ReturnType<typeof createStore>;
