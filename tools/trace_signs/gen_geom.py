"""Geometry helpers for turning segmented room polygons into clean map polygons."""
import numpy as np, cv2
def hull(pts):
    pts=np.asarray(pts,np.float32).reshape(-1,1,2); h=cv2.convexHull(pts).reshape(-1,2); return h.astype(float)
def simplify(poly,eps=2.5):
    p=np.asarray(poly,np.float32).reshape(-1,1,2); return cv2.approxPolyDP(p,eps,True).reshape(-1,2).astype(float)
def clip_halfplane(poly,p0,nrm):
    """Keep the part of poly with (x-p0)·nrm >= 0 (Sutherland-Hodgman)."""
    poly=np.asarray(poly,float); out=[]; n=len(poly)
    for i in range(n):
        a=poly[i]; b=poly[(i+1)%n]; da=(a-p0)@nrm; db=(b-p0)@nrm
        if da>=0: out.append(a)
        if (da>=0)!=(db>=0):
            t=da/(da-db); out.append(a+(b-a)*t)
    return np.array(out)
def split_along(poly,direction,fracs):
    """Split poly into len(fracs)+1 pieces by lines perpendicular to `direction` placed at
    fractions of the polygon's extent along that direction."""
    poly=np.asarray(poly,float); d=np.asarray(direction,float); d=d/np.linalg.norm(d); nrm=np.array([-d[1],d[0]])
    t=poly@d; t0,t1=t.min(),t.max(); cuts=[t0+(t1-t0)*f for f in fracs]
    pieces=[]; lo=None
    for cut in cuts+[None]:
        piece=poly
        if lo is not None: piece=clip_halfplane(piece,d*lo,d)
        if cut is not None: piece=clip_halfplane(piece,d*cut,-d)
        pieces.append(piece); lo=cut
    return pieces
def signed_area(p): x,y=p[:,0],p[:,1]; return 0.5*np.sum(x*np.roll(y,-1)-np.roll(x,-1)*y)
def polygon_area(p): return abs(signed_area(np.asarray(p,float)))
def clockwise(p):
    p=np.asarray(p,float); return p if signed_area(p)>0 else p[::-1]  # y-down screen: positive = clockwise visually
class Snapper:
    """Snap polygon vertices onto outline walls / corners so perimeter rooms coincide with the outline."""
    def __init__(self, walls, corners, tol=9.0, corner_tol=12.0):
        # walls: dict name -> (a, b) ; corners: dict name -> xy (incl. arc junctions)
        self.walls={k:(np.array(a,float),np.array(b,float)) for k,(a,b) in walls.items()}
        self.corners={k:np.array(v,float) for k,v in corners.items()}; self.tol=tol; self.ctol=corner_tol
    def snap_point(self,p):
        p=np.asarray(p,float)
        best=None
        for k,v in self.corners.items():
            d=np.linalg.norm(p-v)
            if d<self.ctol and (best is None or d<best[0]): best=(d,v,'corner:'+k)
        if best: return best[1],best[2]
        for k,(a,b) in self.walls.items():
            ab=b-a; L=np.linalg.norm(ab); u=ab/L; t=(p-a)@u
            if t<-2 or t>L+2: continue
            q=a+u*t; d=np.linalg.norm(p-q)
            if d<self.tol and (best is None or d<best[0]): best=(d,q,'wall:'+k)
        if best: return best[1],best[2]
        return p,None
    def snap(self,poly):
        out=[];tags=[]
        for p in poly:
            q,tag=self.snap_point(p); out.append(q); tags.append(tag)
        return np.array(out),tags
def weld(polys, tol=5.0):
    """Merge vertices across polygons that lie within tol of each other (shared corners)."""
    allp=np.vstack(polys); n=len(allp); parent=list(range(n))
    def find(i):
        while parent[i]!=i: parent[i]=parent[parent[i]]; i=parent[i]
        return i
    from scipy.spatial import cKDTree
    tree=cKDTree(allp)
    for i,j in tree.query_pairs(tol):
        a,b=find(i),find(j)
        if a!=b: parent[a]=b
    groups={}
    for i in range(n): groups.setdefault(find(i),[]).append(i)
    merged=allp.copy()
    for g in groups.values():
        m=allp[g].mean(0); merged[g]=m
    out=[]; k=0
    for p in polys:
        out.append(merged[k:k+len(p)]); k+=len(p)
    return out
def dedupe(poly, tol=1.0):
    poly=np.asarray(poly,float); out=[poly[0]]
    for p in poly[1:]:
        if np.linalg.norm(p-out[-1])>tol: out.append(p)
    if len(out)>1 and np.linalg.norm(out[0]-out[-1])<=tol: out.pop()
    return np.array(out)

def clean(poly, eps=3.5, hull_ratio=0.85):
    """Simplify a traced polygon; replace it with its convex hull when it is (nearly) convex,
    which removes the jagged edges left by pixel segmentation of rectangular rooms."""
    p=simplify(clockwise(np.asarray(poly,float)),eps)
    h=hull(p)
    if polygon_area(p)>=hull_ratio*polygon_area(h): p=simplify(h,eps)
    return clockwise(p)
