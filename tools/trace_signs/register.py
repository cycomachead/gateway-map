import cv2, numpy as np, json, sys
from seg import wing_footprint
from outline_fit import arc_pts
O=json.load(open('outline.json'))
def outline_pts(O, names=None, step=3):
    verts=O; pts=[]
    for k,v in enumerate(verts):
        w=verts[(k+1)%len(verts)]
        if names and v['name'] not in names: continue
        seg=arc_pts([v['x'],v['y']],[w['x'],w['y']],v['bulge'],n=200)
        L=np.linalg.norm(np.diff(seg,axis=0),axis=1).sum(); n=max(2,int(L/step))
        seg=arc_pts([v['x'],v['y']],[w['x'],w['y']],v['bulge'],n=n); pts.append(seg)
    return np.vstack(pts)
NE_WALLS=['notchE','neNW','neN','tip','tipSW','sBend','sPeak','sEnd']   # edges starting at these vertices
SW_WALLS=['swNW','swNE','notchS','notchB','eMid','swSE','bumpE','bumpW','swSW','swW','notchE2','n2a','notchB2','n2b','notchW2']
def similarity_fit(src,dst):
    # least squares similarity (scale+rot+trans)
    ms=src.mean(0); md=dst.mean(0); s=src-ms; d=dst-md
    a=(s[:,0]*d[:,0]+s[:,1]*d[:,1]).sum(); b=(s[:,0]*d[:,1]-s[:,1]*d[:,0]).sum(); n=(s**2).sum()
    A=a/n; B=b/n
    M=np.array([[A,B],[-B,A]]); t=md-ms@M
    return np.vstack([M,t])  # 3x2, apply: [x y 1]@M
def affine_fit(src,dst):
    A=np.hstack([src,np.ones((len(src),1))]); M,_,_,_=np.linalg.lstsq(A,dst,rcond=None); return M
def apply(M,p): return np.hstack([p,np.ones((len(p),1))])@M
def icp(src, target, M0, iters=40, trim=0.6, model='affine'):
    from scipy.spatial import cKDTree
    tree=cKDTree(target); M=M0
    for it in range(iters):
        p=apply(M,src); d,j=tree.query(p)
        thr=np.percentile(d,trim*100)
        sel=d<=thr
        M=(affine_fit if model=='affine' else similarity_fit)(src[sel],target[j[sel]])
    p=apply(M,src); d,j=tree.query(p)
    return M, d
if __name__=='__main__':
    from scipy.spatial import cKDTree
    n,wing,floor=sys.argv[1],sys.argv[2],sys.argv[3]
    img=cv2.imread(f'rect/{n}.png')[950:1850]
    fp,c=wing_footprint(img)
    O_=O['O2'] if floor=='2' else O['O34']
    names=NE_WALLS if wing=='NE' else SW_WALLS
    target=outline_pts(O_,names)
    src=c.astype(float)[::2]
    # init: bbox mapping
    sb=np.array([src.min(0),src.max(0)]); tb=np.array([target.min(0),target.max(0)])
    sc=(tb[1]-tb[0])/(sb[1]-sb[0]); M0=np.array([[sc[0],0],[0,sc[1]],tb[0]-sb[0]*sc]); 
    M,d=icp(src,target,M0,model='similarity',trim=0.5)
    M,d=icp(src,target,M,model='affine',trim=0.6)
    print(n,'median dist %.1f, 60pct %.1f, 80pct %.1f'%(np.median(d),np.percentile(d,60),np.percentile(d,80)))
    print('M',np.round(M,4).tolist())
    json.dump({'M':M.tolist(),'y0':950},open(f'rect/{n}_reg.json','w'))
    # overlay: draw frame outline onto the sign crop
    A=np.vstack([M.T,[0,0,1]]); Ainv=np.linalg.inv(A)
    full=outline_pts(O_,None,step=2); sp=(np.hstack([full,np.ones((len(full),1))])@Ainv.T)[:,:2]
    dbg=img.copy(); 
    for p in sp.astype(int): cv2.circle(dbg,tuple(p),1,(0,0,255),-1)
    x,y,w,h=cv2.boundingRect(c); cv2.imwrite(f'rect/{n}_reg.png',dbg[max(0,y-20):y+h+20,max(0,x-20):x+w+20])
