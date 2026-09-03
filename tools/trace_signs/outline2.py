import json, numpy as np, cv2
from outline_fit import *
fp=json.load(open('rect/footprints.json'))
# re-derive per-sign frame transforms using approx vertices (indices per new approx lists)
IDX={'IMG_9060':{'swNW':10,'swNE':9,'neNW':3,'neN':2,'tipSW':22,'swSE':16,'swSW':12},
     'IMG_9058':{'swNW':10,'swNE':9,'neNW':3,'neN':2,'tipSW':22,'swSE':16,'swSW':12},
     'IMG_9066':{'swNW':10,'swNE':9,'neNW':3,'neN':2,'tipSW':24,'swSE':18,'swSW':12}}
P4={'swNW':[40,352],'swNE':[415,243],'neNW':[683,168],'neN':[1325,22],'tipSW':[1582,777],'swSE':[1180,850],'swSW':[260,975]}
def frame_T(n):
    ap=crop_pts(n,'approx'); ix=IDX[n]
    src=np.array([ap[ix[k]] for k in P4]); dst=np.array([P4[k] for k in P4],float)
    return fit_affine(src,dst)
T={n:frame_T(n) for n in IDX}
C={n:contour_frame(n,T[n]) for n in IDX}
merged=np.vstack([C['IMG_9058'],C['IMG_9060'],C['IMG_9066']])
def fit_line(pts, a, b, tol=14, margin=0.08):
    a=np.array(a,float); b=np.array(b,float); d=b-a; L=np.linalg.norm(d); d/=L; nrm=np.array([-d[1],d[0]])
    rel=pts-a; t=rel@d; s=rel@nrm
    sel=(t>L*margin)&(t<L*(1-margin))&(np.abs(s)<tol)
    q=pts[sel]
    for it in range(4):
        m=q.mean(0); u,sv,vt=np.linalg.svd(q-m); dv=vt[0]; nn=np.array([-dv[1],dv[0]]); r=np.abs((q-m)@nn)
        q=q[r<max(1.5,np.percentile(r,70))]
    m=q.mean(0); u,sv,vt=np.linalg.svd(q-m); dv=vt[0]; nn=np.array([-dv[1],dv[0]])
    return m,dv,float(np.abs((pts[sel]-m)@nn).mean()),int(sel.sum())
def isect(l1,l2):
    (p1,d1),(p2,d2)=(l1[0],l1[1]),(l2[0],l2[1]); A=np.array([d1,-d2]).T; t=np.linalg.solve(A,p2-p1); return p1+d1*t[0]
def proj(l,p): m,d=l[0],l[1]; return m+d*((np.array(p)-m)@d)
# approximate corners (frame) from earlier
A={'swNW':(39,352),'swNE':(425,240),'notchS':(508,473),'notchE':(657,398),'neNW':(668,166),'neN':(1330,28),'tip':(1992,703),'tipSW':(1574,787),
   'sBend':(1364,562),'eMid':(1142,711),'swSE':(1187,859),'bumpE':(739,914),'bumpW':(504,942),'swSW':(260,971),'swW':(172,720)}
walls={'swNorth':('swNW','swNE'),'swEast':('swNE','notchS'),'neWest':('notchE','neNW'),'neNorth':('neNW','neN'),'neDiagonal':('neN','tip'),
       'neTip':('tip','tipSW'),'neInner':('tipSW','sBend'),'swEastLower':('eMid','swSE'),'swSouth':('swSE','bumpE'),'swSouthW':('bumpW','swSW'),
       'swWestS':('swSW','swW'),'swWestN':('swW','swNW')}
lines={}
for w,(a,b) in walls.items():
    lines[w]=fit_line(merged,A[a],A[b]); print(w,'mean resid %.2f n=%d'%(lines[w][2],lines[w][3]))
V={}
V['swNW']=isect(lines['swWestN'],lines['swNorth']); V['swNE']=isect(lines['swNorth'],lines['swEast'])
V['neNW']=isect(lines['neWest'],lines['neNorth']); V['neN']=isect(lines['neNorth'],lines['neDiagonal'])
V['tip']=isect(lines['neDiagonal'],lines['neTip']); V['tipSW']=isect(lines['neTip'],lines['neInner'])
V['swSE']=isect(lines['swEastLower'],lines['swSouth']); V['swSW']=isect(lines['swSouthW'],lines['swWestS'])
V['swW']=isect(lines['swWestS'],lines['swWestN'])
# check: is south wall one line? compare swSouth and swSouthW directions
print('south dirs',lines['swSouth'][1],lines['swSouthW'][1], 'swSouthW offset from swSouth line:',(lines['swSouthW'][0]-lines['swSouth'][0])@np.array([-lines['swSouth'][1][1],lines['swSouth'][1][0]]))
print('west dirs',lines['swWestS'][1],lines['swWestN'][1])
for k,v in V.items(): print(k,np.round(v,1))
json.dump({k:v.tolist() for k,v in V.items()},open('corners_v2.json','w'))
np.save('merged_contour.npy',merged)
json.dump({n:T[n].tolist() for n in T},open('frameT.json','w'))
