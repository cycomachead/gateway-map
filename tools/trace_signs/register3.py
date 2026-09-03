import cv2, numpy as np, json, sys
from scipy.interpolate import RBFInterpolator
from seg import wing_footprint
from register import outline_pts, affine_fit, apply, O
import register2 as R
V=R.V
def signed_area(p): x,y=p[:,0],p[:,1]; return 0.5*np.sum(x*np.roll(y,-1)-np.roll(x,-1)*y)
def resample(path, n):
    seg=np.linalg.norm(np.diff(path,axis=0),axis=1); cum=np.r_[0,np.cumsum(seg)]; L=cum[-1]
    t=np.linspace(0,L,n); return np.stack([np.interp(t,cum,path[:,0]),np.interp(t,cum,path[:,1])],1)
def frame_path(O_, A, B):
    names=[v['name'] for v in O_]; i=names.index(A); j=names.index(B)
    idx=[]; k=i
    while True:
        idx.append(k); k=(k+1)%len(O_)
        if k==j: break
    pts=[outline_pts(O_,[names[m]],step=2) for m in idx]
    return np.vstack(pts)
def contour_sub(c, i, j):
    return c[i:j+1] if i<=j else np.vstack([c[i:],c[:j+1]])
def line_end(pts, line, near, tol=3.0, radius=150):
    m,d=line[0],line[1]; nrm=np.array([-d[1],d[0]]); rel=pts-m; t=rel@d; s=rel@nrm
    tn=(np.array(near)-m)@d; sel=(np.abs(s)<tol)&(np.abs(t-tn)<radius)
    if sel.sum()==0: return np.array(near,float)
    tt=t[sel]; te=tt[np.argmin(np.abs(tt-tn))] if False else (tt.max() if tn>np.median(t[np.abs(s)<tol]) else tt.min())
    return m+d*te
SEQ={'NE':['notchE','neNW','neN','tip','tipSW','sBend','sPeak','sEnd'],
     'SW3':['swNW','swNE','notchS','notchB',None,'sEnd','eMid','swSE','bumpE','bumpW','swSW','swW'],
     'SW2':['swNW','swNE','notchS','notchB',None,'sEnd','eMid','swSE','notchE2','n2a','notchB2','n2b','notchW2','swSW','swW']}
LINE_ENDS={'notchE':'neWest','sBend':'neInner','notchS':'swEast','sEnd':'sSide','bumpE':'swSouth','bumpW':'swSouthW','notchE2':'swSouth','notchW2':'swSouthW'}
class Warp:
    def __init__(self,M,src,dst,smoothing=1.0):
        self.M=M; a=apply(M,src); self.tps=RBFInterpolator(a,dst-a,kernel='thin_plate_spline',smoothing=smoothing)
    def __call__(self,pts):
        pts=np.asarray(pts,float).reshape(-1,2); a=apply(self.M,pts); return a+self.tps(a)
def build(n, dbg=True):
    reg=json.load(open(f'rect/{n}_reg2.json')); M=np.array(reg['M']); wing=reg['wing']; floor=reg['floor']
    O_=O['O2'] if floor=='2' else O['O34']
    img=cv2.imread(f'rect/{n}.png')[950:1850]; fp,c=wing_footprint(img); c=c.astype(float)
    fr=outline_pts(O_,None,step=2)
    if np.sign(signed_area(c))!=np.sign(signed_area(fr)): c=c[::-1]
    Mi=R.inv(M)
    # fitted lines (round 2, tol 12) seeded by M
    lines={}
    for name,a,b in R.WALLS[wing]:
        pa=apply(Mi,V[a][None])[0]; pb=apply(Mi,V[b][None])[0]; lines[name]=R.fit_line(c,pa,pb,tol=12) or R.fit_line(c,pa,pb,tol=30)
    seq=SEQ[wing if wing=='NE' else 'SW'+floor]
    det={}
    for k,v in reg['corners'].items(): det[k]=np.array(v)
    for name in seq:
        if name is None or name in det: continue
        near=apply(Mi,V[name][None])[0]
        if name in LINE_ENDS and lines.get(LINE_ENDS[name]): det[name]=line_end(c,lines[LINE_ENDS[name]],near)
        else: det[name]=c[np.argmin(np.linalg.norm(c-near,axis=1))]
    idx={name:int(np.argmin(np.linalg.norm(c-det[name],axis=1))) for name in seq if name}
    src=[];dst=[]
    for k in range(len(seq)):
        A=seq[k]; B=seq[(k+1)%len(seq)]
        if A is None or B is None: continue
        sub=contour_sub(c,idx[A],idx[B]); fpth=frame_path(O_,A,B)
        if len(sub)<4: continue
        n_=max(3,int(np.linalg.norm(np.diff(fpth,axis=0),axis=1).sum()/15))
        s=resample(sub,n_); d=resample(fpth,n_)
        # exact corners at ends
        src.append(s); dst.append(d)
    src=np.vstack(src); dst=np.vstack(dst)
    W=Warp(M,src,dst)
    res=np.linalg.norm(W(src)-dst,axis=1)
    print(n,'ctrl',len(src),'resid mean %.1f max %.1f'%(res.mean(),res.max()))
    if dbg:
        rooms=json.load(open(f'rect/{n}_rooms.json'))['room']
        im=np.full((1100,2050,3),255,np.uint8); cv2.polylines(im,[fr.astype(np.int32)],True,(0,0,0),2)
        wc=W(c); cv2.polylines(im,[wc.astype(np.int32)],True,(0,160,0),1)
        for k,cp in enumerate(rooms):
            p=W(np.array(cp['poly'],float)); cv2.polylines(im,[p.astype(np.int32)],True,(0,0,255),1)
            cx,cy=p.mean(0).astype(int); cv2.putText(im,str(k),(cx-6,cy+4),cv2.FONT_HERSHEY_SIMPLEX,0.35,(120,0,0),1)
        cv2.imwrite(f'rect/{n}_frame.png',im)
        im2=img.copy()
        for name,p in det.items(): cv2.circle(im2,tuple(p.astype(int)),5,(0,255,0),2); cv2.putText(im2,name,(int(p[0])+5,int(p[1])-5),cv2.FONT_HERSHEY_SIMPLEX,0.4,(0,120,0),1)
        x,y,w,h=cv2.boundingRect(c.astype(np.int32)); cv2.imwrite(f'rect/{n}_det.png',im2[max(0,y-20):y+h+20,max(0,x-20):x+w+20])
    return W,O_,c
if __name__=='__main__':
    for n in sys.argv[1:]: build(n)
