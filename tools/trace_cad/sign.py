"""Shapes from a wayfinding sign photo (the simplified floor map on the elevator-lobby signs).

The sign draws the big shapes cleanly: the building outline, the S-curve walls between the
wings, the white piazza band around the atrium and the atrium oval. This registers the sign's
map onto the CAD frame (a homography fitted to the building outline by iterative closest
point) and returns the piazza band and the oval as polygons in sheet coordinates. The CAD
then fills in the rooms.
"""
import cv2
import numpy as np
from scipy.spatial import cKDTree


def segment(path):
    """Masks of the map on the sign: (crop offset, dark line work, white floor)."""
    im = cv2.imread(path)
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    # the map is the band of the sign with line work below the text block: dark rows
    dark_all = (gray < 110).astype(np.uint8)
    prof = dark_all.sum(1)
    h = im.shape[0]
    rows = np.nonzero(prof[h // 2:] > 5)[0] + h // 2
    y0, y1 = int(rows.min()) - 10, int(rows.max()) + 10
    band = slice(max(0, y0), min(h, y1))
    g, s, v = gray[band], hsv[band, :, 1], hsv[band, :, 2]
    dark = (g < 110).astype(np.uint8)
    coloured = (s > 90) & (v > 60)
    white = ((g > 175) & (s < 60)).astype(np.uint8)
    filled = (dark | coloured).astype(np.uint8)
    return band.start, dark, white, filled


def sign_outline(filled):
    """Outer contour of the map (the building outline), from the line work and the wings."""
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    m = cv2.morphologyEx(filled * 255, cv2.MORPH_CLOSE, k)
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cs, key=cv2.contourArea).reshape(-1, 2).astype(float)
    # the entrance pointer lines stick out of the outline: an opening removes them
    solid = np.zeros_like(m)
    cv2.fillPoly(solid, [c.astype(np.int32)], 255)
    solid = cv2.morphologyEx(solid, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25)))
    cs, _ = cv2.findContours(solid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    return max(cs, key=cv2.contourArea).reshape(-1, 2).astype(float)


def _densify(poly, step=2.0):
    P = np.asarray(poly, float)
    out = []
    for a, b in zip(P, np.roll(P, -1, axis=0)):
        n = max(1, int(np.linalg.norm(b - a) / step))
        out.append(a + (b - a) * np.linspace(0, 1, n, endpoint=False)[:, None])
    return np.vstack(out)


def apply(H, pts):
    P = np.hstack([np.asarray(pts, float), np.ones((len(pts), 1))]) @ H.T
    return P[:, :2] / P[:, 2:3]


def register(sign_pts, cad_outline, iterations=40):
    """Homography from sign pixels to sheet points, fitted by ICP on the building outline."""
    C = _densify(cad_outline)
    tree = cKDTree(C)
    S = np.asarray(sign_pts, float)
    # initial similarity: match the bounding boxes
    s = (C.max(0) - C.min(0)) / (S.max(0) - S.min(0))
    scale = float(s.mean())
    H = np.array([[scale, 0, 0], [0, scale, 0], [0, 0, 1.0]])
    t = C.min(0) - S.min(0) * scale
    H[:2, 2] = t
    for it in range(iterations):
        T = apply(H, S)
        d, idx = tree.query(T)
        keep = d < np.percentile(d, 90)  # drop the worst matches (pointer lines, glare)
        Hn, _ = cv2.findHomography(S[keep].astype(np.float32), C[idx[keep]].astype(np.float32), cv2.RANSAC, 12.0)
        if Hn is None:
            break
        H = Hn
    T = apply(H, S)
    d, _ = tree.query(T)
    return H, float(np.median(d)), float(np.percentile(d, 90))


def central_white(white, dark, oval_hint):
    """The white component of the map holding the atrium (the piazza band) and its hole (the
    oval), as contours in map pixels."""
    n, cc = cv2.connectedComponents(white, connectivity=4)
    k = cc[int(oval_hint[1]), int(oval_hint[0])]
    if not k:
        return None, None
    m = (cc == k).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    cs, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    outer = max(cs, key=cv2.contourArea)
    holes = [c for c, hh in zip(cs, hier[0]) if hh[3] >= 0 and cv2.contourArea(c) > 300]
    oval = max(holes, key=cv2.contourArea) if holes else None
    return outer.reshape(-1, 2).astype(float), (oval.reshape(-1, 2).astype(float) if oval is not None else None)


def oval(dark, hint, r_min=38, r_max=85):
    """Ellipse fitted to the dark ring of the atrium oval around the hint (the oval's line is
    broken by the label inside it, so it is not a closed contour). Returns cv2 ellipse
    ((cx, cy), (w, h), angle) in map pixels and the fit residual."""
    ys, xs = np.nonzero(dark)
    r = np.hypot(xs - hint[0], ys - hint[1])
    sel = (r > r_min) & (r < r_max)
    pts = np.column_stack([xs[sel], ys[sel]]).astype(np.float32)
    if len(pts) < 20:
        return None, None
    e = cv2.fitEllipse(pts)
    # residual: distance of the points from the ellipse, via the normalised radius
    (cx, cy), (w, h), ang = e
    t = np.radians(ang)
    dx, dy = pts[:, 0] - cx, pts[:, 1] - cy
    u = dx * np.cos(t) + dy * np.sin(t)
    v = -dx * np.sin(t) + dy * np.cos(t)
    rho = np.hypot(u / (w / 2), v / (h / 2))
    res = np.abs(rho - 1) * min(w, h) / 2
    return e, float(np.median(res))


def ellipse_poly(e, n=48):
    (cx, cy), (w, h), ang = e
    t = np.radians(ang)
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    u, v = w / 2 * np.cos(a), h / 2 * np.sin(a)
    return np.column_stack([cx + u * np.cos(t) - v * np.sin(t), cy + u * np.sin(t) + v * np.cos(t)])


def smooth_closed(pts, step=2.0, sigma=6.0, eps=1.5):
    """Resample a closed contour, low-pass it along its length (wrapping) and simplify."""
    from scipy.ndimage import gaussian_filter1d
    P = _densify(pts, step)
    sm = gaussian_filter1d(P, sigma, axis=0, mode='wrap')
    return cv2.approxPolyDP(sm.astype(np.float32), eps, True).reshape(-1, 2).astype(float)


def shapes(path, cad_outline, hint_frac):
    """(piazza band polygon, oval polygon, registration residuals) in sheet coordinates."""
    y0, dark, white, filled = segment(path)
    S = sign_outline(filled)
    H, med, p90 = register(S, cad_outline)
    bh, bw = white.shape
    hint = (bw * hint_frac[0], bh * hint_frac[1])
    outer, _ = central_white(white, dark, hint)
    e, res = oval(dark, hint)
    band = smooth_closed(apply(H, outer)) if outer is not None else None
    oval_poly = smooth_closed(apply(H, ellipse_poly(e)), sigma=2.0, eps=0.8) if e is not None else None
    return band, oval_poly, {'median': med, 'p90': p90, 'oval_residual': res}
