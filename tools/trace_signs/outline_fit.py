import json, numpy as np, cv2
fp=json.load(open('rect/footprints.json'))
P4={'swNW':[40,352],'swNE':[415,243],'neNW':[683,168],'neN':[1325,22],'tip':[1990,718],'tipSW':[1582,777],'swSE':[1180,850],'swSW':[260,975]}
IDX={'IMG_9060':{'swNW':13,'swNE':12,'neNW':6,'neN':2,'tip':0,'tipSW':28,'swSE':21,'swSW':15},
     'IMG_9058':{'swNW':10,'swNE':9,'neNW':3,'neN':2,'tip':0,'tipSW':23,'swSE':16,'swSW':12},
     'IMG_9066':{'swNW':13,'swNE':12,'neNW':6,'neN':2,'tip':0,'tipSW':28,'swSE':21,'swSW':15}}
def fit_affine(src,dst):
    A=np.hstack([src,np.ones((len(src),1))]); M,_,_,_=np.linalg.lstsq(A,dst,rcond=None); return M  # 3x2
def apply(M,p): p=np.atleast_2d(p); return np.hstack([p,np.ones((len(p),1))])@M
def crop_pts(n,key): return np.array(fp[n][key],float)-[0,1180]
def frame_transform(n):
    ap=crop_pts(n,'approx'); ix=IDX[n]
    src=np.array([ap[ix[k]] for k in P4]); dst=np.array(list(P4.values()),float)
    return fit_affine(src,dst)
def contour_frame(n,M=None):
    M=M if M is not None else frame_transform(n)
    return apply(M,crop_pts(n,'contour'))
def nearest(c,p):
    d=np.linalg.norm(c-np.array(p),axis=1); return int(np.argmin(d))
def arc_pts(a,b,bulge,n=40):
    a=np.array(a,float);b=np.array(b,float)
    if abs(bulge)<1e-9:
        t=np.linspace(0,1,n)[:,None]; return a+(b-a)*t
    d=b-a; chord=np.linalg.norm(d); theta=4*np.arctan(abs(bulge)); r=chord/(2*np.sin(theta/2)); sag=abs(bulge)*chord/2
    sign=1 if bulge>0 else -1; nrm=np.array([-d[1],d[0]])/chord*sign
    m=(a+b)/2; c=m-nrm*(r-sag)
    a0=np.arctan2(a[1]-c[1],a[0]-c[0]); am=np.arctan2(m[1]+nrm[1]*sag-c[1],m[0]+nrm[0]*sag-c[0])
    dd=am-a0
    while dd<=-np.pi: dd+=2*np.pi
    while dd>np.pi: dd-=2*np.pi
    sweep=np.sign(dd)*theta
    t=np.linspace(0,1,n); ang=a0+sweep*t
    return np.stack([c[0]+r*np.cos(ang),c[1]+r*np.sin(ang)],1)
def seg_dev(pts,poly):
    # max distance from pts to polyline poly
    best=np.full(len(pts),1e9)
    for i in range(len(poly)-1):
        a=poly[i];b=poly[i+1];d=b-a;L=d@d
        t=np.clip(((pts-a)@d)/max(L,1e-9),0,1); proj=a+t[:,None]*d
        best=np.minimum(best,np.linalg.norm(pts-proj,axis=1))
    return best.max()
def fit_bulge(a,b,pts):
    # choose bulge minimizing max deviation from contour pts between a and b
    if len(pts)<3: return 0.0
    best=(1e9,0.0)
    for bb in np.linspace(-1.2,1.2,481):
        dv=seg_dev(pts,arc_pts(a,b,bb))
        if dv<best[0]: best=(dv,bb)
    return best[1]
def build(contour, spec):
    """spec: list of (name, approx_xy, kind) kind in 'line'|'arc'|'arc2'; picks nearest contour point.
    returns list of dict(name,x,y,bulge) and deviations"""
    idxs=[nearest(contour,p) for _,p,_ in spec]
    n=len(contour); out=[]
    for k,(name,_,kind) in enumerate(spec):
        i=idxs[k]; j=idxs[(k+1)%len(spec)]
        a=contour[i]; b=contour[j]
        # contour points from i to j (contour direction may be either; pick shorter arc of indices)
        if i<=j: seg=contour[i:j+1]
        else: seg=np.vstack([contour[i:],contour[:j+1]])
        if len(seg)>n/2:  # wrong way round
            if i<=j: seg=np.vstack([contour[j:],contour[:i+1]])[::-1]
            else: seg=contour[j:i+1][::-1]
        bulge=fit_bulge(a,b,seg) if kind=='arc' else 0.0
        dev=seg_dev(seg,arc_pts(a,b,bulge))
        out.append({'name':name,'x':float(a[0]),'y':float(a[1]),'bulge':float(bulge),'dev':float(dev),'n':len(seg)})
    return out
def draw(img, M, verts, color=(0,0,255)):
    # verts in frame coords; draw onto sign crop via inverse of M
    A=np.vstack([M.T,[0,0,1]]); Ainv=np.linalg.inv(A)
    poly=[]
    for k,v in enumerate(verts):
        w=verts[(k+1)%len(verts)]
        poly.append(arc_pts([v['x'],v['y']],[w['x'],w['y']],v['bulge']))
    pts=np.vstack(poly); sp=(np.hstack([pts,np.ones((len(pts),1))])@Ainv.T)[:,:2]
    cv2.polylines(img,[sp.astype(np.int32)],True,color,2)
    for v in verts:
        s=(np.array([v['x'],v['y'],1])@Ainv.T)[:2].astype(int)
        cv2.circle(img,tuple(s),4,(0,255,0),-1); cv2.putText(img,v['name'],(s[0]+4,s[1]-3),cv2.FONT_HERSHEY_SIMPLEX,0.4,(0,140,0),1)
    return img
