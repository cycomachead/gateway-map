import type { Space, SpaceCategory } from './data/types';

export interface AppState {
  floorId: string;
  selectedSpaceId: string | null;
  hoveredSpaceId: string | null;
  query: string;
  /** Empty set = show everything. */
  categories: Set<SpaceCategory>;
}

/** Category filters never hide circulation: corridors and stairs stay as landmarks. */
export const isFilteredOut = (space: Space, categories: Set<SpaceCategory>) =>
  categories.size > 0 && space.category !== 'circulation' && !categories.has(space.category);

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
