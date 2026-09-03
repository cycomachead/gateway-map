import json, numpy as np, cv2
from outline_fit import arc_pts, seg_dev, fit_bulge, crop_pts, nearest
exec(open('outline2.py').read().split("V={}")[0])  # reuse lines, T, C, merged, lines, A, walls
def isect(l1,l2):
    (p1,d1),(p2,d2)=(l1[0],l1[1]),(l2[0],l2[1]); A_=np.array([d1,-d2]).T; t=np.linalg.solve(A_,p2-p1); return p1+d1*t[0]
def line_end(pts, line, near, tol=2.5, radius=120):
    """contour point on `line` (within tol) closest to `near` region: returns the point on line
    that is the extreme along the line in the direction away from the line's interior points."""
    m,d=line[0],line[1]; nrm=np.array([-d[1],d[0]])
    rel=pts-m; t=rel@d; s=rel@nrm
    tn=(np.array(near)-m)@d
    sel=(np.abs(s)<tol)&(np.abs(t-tn)<radius)
    tt=t[sel]
    # the junction is the extreme t on the side of `near` relative to the wall centre (t=0 at mean)
    te=tt.max() if tn>0 else tt.min()
    return m+d*te
# extra line: sSide (sEnd->eMid)
lines['sSide']=fit_line(merged,(1132,596),(1142,711),tol=10)
print('sSide resid',lines['sSide'][2],lines['sSide'][3])
V={}
V['swNW']=isect(lines['swWestN'],lines['swNorth']); V['swNE']=isect(lines['swNorth'],lines['swEast'])
V['neNW']=isect(lines['neWest'],lines['neNorth']); V['neN']=isect(lines['neNorth'],lines['neDiagonal'])
V['tip']=isect(lines['neDiagonal'],lines['neTip']); V['tipSW']=isect(lines['neTip'],lines['neInner'])
V['swSE']=isect(lines['swEastLower'],lines['swSouth']); V['swSW']=isect(lines['swSouthW'],lines['swWestS'])
V['swW']=isect(lines['swWestS'],lines['swWestN']); V['eMid']=isect(lines['sSide'],lines['swEastLower'])
# junctions, averaged over L3 signs (9058, 9060) and L2 (9066) where shared
def avg_end(line, near, signs=('IMG_9058','IMG_9060','IMG_9066')):
    return np.mean([line_end(C[n],line,near) for n in signs],axis=0)
V['notchS']=avg_end(lines['swEast'],(508,473)); V['notchE']=avg_end(lines['neWest'],(657,398))
V['sBend']=avg_end(lines['neInner'],(1364,562)); V['sEnd']=avg_end(lines['sSide'],(1132,596))
V['bumpE']=avg_end(lines['swSouth'],(739,914),signs=('IMG_9058','IMG_9060')); V['bumpW']=avg_end(lines['swSouthW'],(504,942),signs=('IMG_9058','IMG_9060'))
# L2 deep notch junctions
V2={'notchE2':avg_end(lines['swSouth'],(760,905),signs=('IMG_9066',)),'notchW2':avg_end(lines['swSouthW'],(560,930),signs=('IMG_9066',))}
# curve extreme points: notchB (bottom of U: farthest from chord notchS-notchE), sPeak (farthest from chord sBend-sEnd)
def seg_between(contour,a,b):
    i=nearest(contour,a); j=nearest(contour,b); n=len(contour)
    seg=contour[i:j+1] if i<=j else np.vstack([contour[i:],contour[:j+1]])
    if len(seg)>n/2: seg=(np.vstack([contour[j:],contour[:i+1]]) if i<=j else contour[j:i+1])[::-1]
    return seg
def farthest(pts,a,b,side_pt=None):
    pts=seg_between(pts,a,b)
    d=b-a; L=np.linalg.norm(d); d/=L; nrm=np.array([-d[1],d[0]]); rel=pts-a; s=rel@nrm
    i=np.argmax(np.abs(s)); return pts[i]
c60=C['IMG_9060']; c66=C['IMG_9066']
V['notchB']=np.mean([farthest(C[n],V['notchS'],V['notchE']) for n in C],axis=0)
V['sPeak']=np.mean([farthest(C[n],V['sBend'],V['sEnd']) for n in C],axis=0)
V2['notchB2']=farthest(c66,V2['notchE2'],V2['notchW2'])
for k,v in {**V,**V2}.items(): print(k,np.round(v,1))
order=['swNW','swNE','notchS','notchB','notchE','neNW','neN','tip','tipSW','sBend','sPeak','sEnd','eMid','swSE','bumpE','bumpW','swSW','swW']
kinds={'notchS':'arc','notchB':'arc','sBend':'arc','sPeak':'arc','bumpE':'arc'}
def build_outline(order,kinds,V,contours):
    out=[]
    for k,name in enumerate(order):
        nxt=order[(k+1)%len(order)]; a=V[name]; b=V[nxt]
        bulge=0.0
        if kinds.get(name)=='arc':
            segs=[seg_between(c,a,b) for c in contours]
            bulge=float(np.mean([fit_bulge(a,b,s) for s in segs]))
        devs=[seg_dev(seg_between(c,a,b),arc_pts(a,b,bulge)) for c in contours]
        out.append({'name':name,'x':round(float(a[0]),1),'y':round(float(a[1]),1),'bulge':round(bulge,3),'dev':[round(float(d),1) for d in devs]})
    return out
O34=build_outline(order,kinds,V,[C['IMG_9058'],C['IMG_9060']])
for o in O34: print(o)
order2=['swNW','swNE','notchS','notchB','notchE','neNW','neN','tip','tipSW','sBend','sPeak','sEnd','eMid','swSE','notchE2','notchB2','notchW2','swSW','swW']
kinds2={**kinds,'notchE2':'arc','notchB2':'arc'}; kinds2.pop('bumpE')
O2=build_outline(order2,kinds2,{**V,**V2},[C['IMG_9066']])
print('--- L2'); 
for o in O2: print(o)
json.dump({'O34':O34,'O2':O2,'V':{k:v.tolist() for k,v in {**V,**V2}.items()}},open('outline.json','w'),indent=1)
from outline_fit import draw
for n,O in [('IMG_9058',O34),('IMG_9060',O34),('IMG_9066',O2)]:
    img=cv2.imread(f'rect/{n}_map.png'); draw(img,T[n],O); cv2.imwrite(f'rect/overlay_{n[-4:]}.png',img)

# ---- L2 deep notch: split the contour between notchE2 and notchW2 into 4 arc pieces
seg=seg_between(c66,V2['notchE2'],V2['notchW2'])
cum=np.r_[0,np.cumsum(np.linalg.norm(np.diff(seg,axis=0),axis=1))]
def at(frac): return seg[np.searchsorted(cum,cum[-1]*frac)]
V2['n2a']=at(0.28); V2['notchB2']=at(0.5); V2['n2b']=at(0.72)
order2=['swNW','swNE','notchS','notchB','notchE','neNW','neN','tip','tipSW','sBend','sPeak','sEnd','eMid','swSE','notchE2','n2a','notchB2','n2b','notchW2','swSW','swW']
kinds2={**kinds,'notchE2':'arc','n2a':'arc','notchB2':'arc','n2b':'arc'}; kinds2.pop('bumpE')
O2=build_outline(order2,kinds2,{**V,**V2},[C['IMG_9066']])
print('--- L2 notch'); 
for o in O2[13:19]: print(o)
json.dump({'O34':O34,'O2':O2,'V':{k:v.tolist() for k,v in {**V,**V2}.items()}},open('outline.json','w'),indent=1)
img=cv2.imread('rect/IMG_9066_map.png'); draw(img,T['IMG_9066'],O2); cv2.imwrite('rect/overlay_9066.png',img[380:580,200:700])
