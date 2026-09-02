import type { BBox } from './geometry';

export interface PanZoom {
  fit(box: BBox): void;
  zoomBy(factor: number): void;
  destroy(): void;
}

const MIN_SCALE = 0.5; // relative to the last fitted box
const MAX_SCALE = 8;

/**
 * Pan/zoom by mutating the SVG viewBox. Wheel zooms around the cursor, drag pans,
 * pinch is handled through pointer events. Kept dependency-free on purpose.
 */
export function attachPanZoom(svg: SVGSVGElement): PanZoom {
  let view: BBox = { x: 0, y: 0, width: 1000, height: 600 };
  let home: BBox = view;
  const pointers = new Map<number, { x: number; y: number }>();
  let lastPinchDist = 0;
  let dragging = false;
  let moved = false;

  const apply = () => {
    svg.setAttribute('viewBox', `${view.x} ${view.y} ${view.width} ${view.height}`);
  };

  /** Convert a client-space point into viewBox units. */
  const toView = (clientX: number, clientY: number) => {
    const r = svg.getBoundingClientRect();
    const scale = Math.max(view.width / r.width, view.height / r.height);
    // viewBox is centred within the element when aspect ratios differ (xMidYMid meet)
    const offsetX = (r.width - view.width / scale) / 2;
    const offsetY = (r.height - view.height / scale) / 2;
    return {
      x: view.x + (clientX - r.left - offsetX) * scale,
      y: view.y + (clientY - r.top - offsetY) * scale,
      scale,
    };
  };

  const clampScale = (nextWidth: number) => {
    const min = home.width / MAX_SCALE;
    const max = home.width / MIN_SCALE;
    return Math.min(max, Math.max(min, nextWidth));
  };

  const zoomAt = (factor: number, clientX: number, clientY: number) => {
    const before = toView(clientX, clientY);
    const width = clampScale(view.width / factor);
    const f = width / view.width;
    view = {
      x: before.x - (before.x - view.x) * f,
      y: before.y - (before.y - view.y) * f,
      width,
      height: view.height * f,
    };
    apply();
  };

  const onWheel = (ev: WheelEvent) => {
    ev.preventDefault();
    const factor = Math.exp(-ev.deltaY * 0.0015);
    zoomAt(factor, ev.clientX, ev.clientY);
  };

  const onPointerDown = (ev: PointerEvent) => {
    pointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    svg.setPointerCapture(ev.pointerId);
    dragging = pointers.size === 1;
    moved = false;
    if (pointers.size === 2) lastPinchDist = pinchDistance();
  };

  const pinchDistance = () => {
    const [a, b] = [...pointers.values()];
    return Math.hypot(a.x - b.x, a.y - b.y);
  };

  const onPointerMove = (ev: PointerEvent) => {
    const prev = pointers.get(ev.pointerId);
    if (!prev) return;
    pointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });

    if (pointers.size === 2) {
      const dist = pinchDistance();
      if (lastPinchDist > 0) {
        const [a, b] = [...pointers.values()];
        zoomAt(dist / lastPinchDist, (a.x + b.x) / 2, (a.y + b.y) / 2);
      }
      lastPinchDist = dist;
      return;
    }

    if (!dragging) return;
    const { scale } = toView(ev.clientX, ev.clientY);
    const dx = (ev.clientX - prev.x) * scale;
    const dy = (ev.clientY - prev.y) * scale;
    if (Math.abs(ev.clientX - prev.x) + Math.abs(ev.clientY - prev.y) > 2) moved = true;
    view = { ...view, x: view.x - dx, y: view.y - dy };
    svg.classList.toggle('is-dragging', moved);
    apply();
  };

  const onPointerUp = (ev: PointerEvent) => {
    pointers.delete(ev.pointerId);
    if (pointers.size < 2) lastPinchDist = 0;
    if (pointers.size === 0) {
      dragging = false;
      svg.classList.remove('is-dragging');
    }
  };

  // Suppress the click that follows a drag so it doesn't select a room.
  const onClickCapture = (ev: MouseEvent) => {
    if (moved) {
      ev.stopPropagation();
      ev.preventDefault();
      moved = false;
    }
  };

  svg.addEventListener('wheel', onWheel, { passive: false });
  svg.addEventListener('pointerdown', onPointerDown);
  svg.addEventListener('pointermove', onPointerMove);
  svg.addEventListener('pointerup', onPointerUp);
  svg.addEventListener('pointercancel', onPointerUp);
  svg.addEventListener('click', onClickCapture, true);

  return {
    fit(box) {
      home = box;
      view = { ...box };
      apply();
    },
    zoomBy(factor) {
      const r = svg.getBoundingClientRect();
      zoomAt(factor, r.left + r.width / 2, r.top + r.height / 2);
    },
    destroy() {
      svg.removeEventListener('wheel', onWheel);
      svg.removeEventListener('pointerdown', onPointerDown);
      svg.removeEventListener('pointermove', onPointerMove);
      svg.removeEventListener('pointerup', onPointerUp);
      svg.removeEventListener('pointercancel', onPointerUp);
      svg.removeEventListener('click', onClickCapture, true);
    },
  };
}
