import cv2, numpy as np, json, sys
from seg import wing_footprint
from register import outline_pts, affine_fit, apply, O
V={k:np.array(v) for k,v in O['V'].items()}
def fit_line(pts, a, b, tol=14, margin=0.1):
    a=np.array(a,float); b=np.array(b,float); d=b-a; L=np.linalg.norm(d); d/=L; nrm=np.array([-d[1],d[0]])
    rel=pts-a; t=rel@d; s=rel@nrm
    sel=(t>L*margin)&(t<L*(1-margin))&(np.abs(s)<tol); q=pts[sel]
    if len(q)<10: return None
    for it in range(4):
        m=q.mean(0); u,sv,vt=np.linalg.svd(q-m); dv=vt[0]; nn=np.array([-dv[1],dv[0]]); r=np.abs((q-m)@nn)
        q=q[r<max(1.5,np.percentile(r,70))]
    m=q.mean(0); u,sv,vt=np.linalg.svd(q-m); return (m,vt[0],len(q))
def isect(l1,l2):
    (p1,d1),(p2,d2)=(l1[0],l1[1]),(l2[0],l2[1]); A=np.array([d1,-d2]).T; t=np.linalg.solve(A,p2-p1); return p1+d1*t[0]
def inv(M): A=np.vstack([M.T,[0,0,1]]); Ai=np.linalg.inv(A); return Ai[:2].T  # 3x2 inverse
WALLS={'L1NE':[('westUp','L1w','L1nw'),('neNorth','L1nw','neN'),('neDiagonal','neN','tip'),('neTip','tip','tipSW'),('neInner','tipSW','sBend')],'NE':[('neWest','notchE','neNW'),('neNorth','neNW','neN'),('neDiagonal','neN','tip'),('neTip','tip','tipSW'),('neInner','tipSW','sBend')],
       'SW':[('swNorth','swNW','swNE'),('swEast','swNE','notchS'),('swEastLower','eMid','swSE'),('swSouth','swSE','bumpE'),('swSouthW','bumpW','swSW'),('swWestS','swSW','swW'),('swWestN','swW','swNW'),('sSide','sEnd','eMid')]}
CORNERS={'L1NE':[('L1nw','westUp','neNorth'),('neN','neNorth','neDiagonal'),('tip','neDiagonal','neTip'),('tipSW','neTip','neInner')],'NE':[('neNW','neWest','neNorth'),('neN','neNorth','neDiagonal'),('tip','neDiagonal','neTip'),('tipSW','neTip','neInner')],
         'SW':[('swNW','swWestN','swNorth'),('swNE','swNorth','swEast'),('swSE','swEastLower','swSouth'),('swSW','swSouthW','swWestS'),('swW','swWestS','swWestN'),('eMid','sSide','swEastLower')]}
def register(n):
    reg=json.load(open(f'rect/{n}_reg.json')); wing=reg['wing']; M0=np.array(reg['M'])
    img=cv2.imread(f'rect/{n}.png')[950:1850]; fp,c=wing_footprint(img); src=c.astype(float)
    Mi=inv(M0)
    lines={}
    for name,a,b in WALLS[wing]:
        pa=apply(Mi,V[a][None])[0]; pb=apply(Mi,V[b][None])[0]
        l=fit_line(src,pa,pb,tol=12); lines[name]=l
        print('  ',name,'n=%d'%l[2] if l else 'FAILED')
    S=[];D=[];names=[]
    for cn,l1,l2 in CORNERS[wing]:
        if lines.get(l1) and lines.get(l2):
            S.append(isect(lines[l1],lines[l2])); D.append(V[cn]); names.append(cn)
    S=np.array(S);D=np.array(D); M=affine_fit(S,D)
    res=np.linalg.norm(apply(M,S)-D,axis=1)
    print(n,'corners',names,'resid',np.round(res,1))
    json.dump({'M':M.tolist(),'y0':950,'wing':wing,'floor':reg['floor'],'corners':{k:s.tolist() for k,s in zip(names,S)}},open(f'rect/{n}_reg2.json','w'))
    O_={'1':O['O1'],'2':O['O2']}.get(reg['floor'],O['O34'])
    full=outline_pts(O_,None,step=2); sp=apply(inv(M),full)
    dbg=img.copy()
    for p in sp.astype(int): cv2.circle(dbg,tuple(p),1,(0,0,255),-1)
    for s in S: cv2.circle(dbg,tuple(s.astype(int)),6,(0,255,0),2)
    x,y,w,h=cv2.boundingRect(c); cv2.imwrite(f'rect/{n}_reg2.png',dbg[max(0,y-20):y+h+20,max(0,x-20):x+w+20])
    return M
if __name__=='__main__':
    for n in sys.argv[1:]: register(n)
