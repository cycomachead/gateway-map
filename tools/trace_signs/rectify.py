import cv2, numpy as np, json, sys, os
SRC='/workspace/.prompt/initial'
OUT='rect'
S=1.024  # displayed->original scale

# approximate corners in displayed coords (TL, TR, BR, BL)
approx = {
 'IMG_9058': [(300,150),(1178,150),(1176,1840),(325,1840)],
 'IMG_9059': [(105,130),(1360,130),(1330,1835),(110,1835)],
 'IMG_9060': [(285,90),(1250,90),(1235,1915),(325,1912)],
 'IMG_9061': [(225,170),(1355,170),(1345,1760),(270,1770)],
 'IMG_9062': [(190,75),(1370,75),(1345,1720),(230,1725)],
 'IMG_9063': [(150,90),(1875,120),(1760,1340),(245,1430)],
 'IMG_9064': [(170,160),(1340,160),(1290,1785),(200,1790)],
 'IMG_9066': [(300,145),(1190,145),(1170,1820),(330,1825)],
 'IMG_9067': [(265,80),(1185,80),(1170,1815),(310,1815)],
 'IMG_9068': [(185,120),(1310,120),(1250,1700),(215,1700)],
}

def refine_edge(gray, p, q, search=30, step=8):
    """Fit a line to strongest gradient across the segment p->q within +-search px."""
    p=np.array(p,float); q=np.array(q,float)
    d=q-p; L=np.linalg.norm(d); d/=L; n=np.array([-d[1],d[0]])
    pts=[]
    gx=cv2.Sobel(gray,cv2.CV_32F,1,0,ksize=3); gy=cv2.Sobel(gray,cv2.CV_32F,0,1,ksize=3)
    for t in np.arange(L*0.08, L*0.92, step):
        base=p+d*t
        best=None;bv=0
        for s in range(-search,search+1):
            x,y=base+n*s
            xi,yi=int(round(x)),int(round(y))
            if 0<=xi<gray.shape[1] and 0<=yi<gray.shape[0]:
                v=abs(gx[yi,xi]*n[0]+gy[yi,xi]*n[1])
                if v>bv: bv=v;best=(x,y)
        if best is not None and bv>40: pts.append(best)
    pts=np.array(pts)
    # robust line fit: iterate, drop outliers
    for it in range(5):
        m=pts.mean(0); u,s,vt=np.linalg.svd(pts-m); dirv=vt[0]
        nn=np.array([-dirv[1],dirv[0]]); res=np.abs((pts-m)@nn)
        keep=res<max(2.0, np.percentile(res,60))
        if keep.sum()<10: break
        pts=pts[keep]
    m=pts.mean(0); u,s,vt=np.linalg.svd(pts-m)
    return m, vt[0]

def intersect(l1,l2):
    (p1,d1),(p2,d2)=l1,l2
    A=np.array([d1,-d2]).T; t=np.linalg.solve(A,p2-p1); return p1+d1*t[0]

def aspect_from_quad(quad, f, cx, cy):
    # Zhang's method for rectangle aspect ratio
    def h(p): return np.array([p[0]-cx,p[1]-cy,f],float)
    m1,m2,m3,m4=[h(p) for p in [quad[0],quad[1],quad[3],quad[2]]]  # TL,TR,BL,BR
    k2=np.dot(np.cross(m1,m4),m3)/np.dot(np.cross(m2,m4),m3)
    k3=np.dot(np.cross(m1,m4),m2)/np.dot(np.cross(m3,m4),m2)
    n2=k2*m2-m1; n3=k3*m3-m1
    return np.sqrt(np.dot(n2,n2)/np.dot(n3,n3))  # width/height

results={}
for name,corners in approx.items():
    img=cv2.imread(f'{SRC}/{name}.jpeg'); gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    gray=cv2.GaussianBlur(gray,(3,3),0)
    c=[(x*S,y*S) for x,y in corners]
    lines=[refine_edge(gray,c[i],c[(i+1)%4]) for i in range(4)]
    quad=[intersect(lines[3],lines[0]),intersect(lines[0],lines[1]),intersect(lines[1],lines[2]),intersect(lines[2],lines[3])]
    quad=np.array(quad,np.float32)
    H_,W_=gray.shape
    f=1.0*max(W_,H_)  # ~ iPhone main camera in px for 2048 long side
    ar=aspect_from_quad(quad,f,W_/2,H_/2)
    results[name]={'quad':quad.tolist(),'aspect':float(ar)}
    print(name, np.round(quad).tolist(), 'aspect %.3f'%ar)
    dbg=img.copy(); cv2.polylines(dbg,[quad.astype(int)],True,(0,0,255),3)
    for q in quad: cv2.circle(dbg,tuple(q.astype(int)),12,(0,255,0),3)
    cv2.imwrite(f'{OUT}/{name}_dbg.jpg', cv2.resize(dbg,None,fx=0.5,fy=0.5))
json.dump(results,open(f'{OUT}/corners.json','w'),indent=1)
