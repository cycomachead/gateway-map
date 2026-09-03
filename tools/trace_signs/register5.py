import cv2, numpy as np, json, sys
from seg import wing_footprint
from register import outline_pts, apply, O
import register2 as R
from register3 import signed_area, resample, contour_sub, Warp
V=R.V
class Frame:
    """Dense closed outline with named arc-length positions."""
    def __init__(self,O_):
        self.names=[v['name'] for v in O_]; pts=[]; self.pos={}; L=0
        for k,v in enumerate(O_):
            seg=outline_pts(O_,[v['name']],step=1); self.pos[v['name']]=L
            L+=np.linalg.norm(np.diff(seg,axis=0),axis=1).sum(); pts.append(seg[:-1])
        self.pts=np.vstack(pts); d=np.linalg.norm(np.diff(np.vstack([self.pts,self.pts[:1]]),axis=0),axis=1)
        self.cum=np.r_[0,np.cumsum(d)]; self.L=self.cum[-1]
    def at(self,s):
        s=np.mod(s,self.L); return np.array([np.interp(s,self.cum,np.r_[self.pts[:,0],self.pts[0,0]]),np.interp(s,self.cum,np.r_[self.pts[:,1],self.pts[0,1]])])
    def path(self,s0,s1,n):
        if s1<s0: s1+=self.L
        return np.array([self.at(s) for s in np.linspace(s0,s1,n)])
def arc(c,i,j):
    sub=contour_sub(c,i,j); return np.linalg.norm(np.diff(sub,axis=0),axis=1).sum()
def walk(c,i0,line,direction,tol=3.5,minrun=10):
    m,d=line[0],line[1]; nrm=np.array([-d[1],d[0]]); n=len(c); last=i0
    for k in range(1,n//2):
        i=(i0+direction*k)%n
        if abs((c[i]-m)@nrm)>tol and k>minrun: break
        last=i
    return last
def extreme(c,i0,direction_vec,window,drop=8.0):
    """first local maximum of the projection on direction_vec walking from i0"""
    n=len(c); d=np.array(direction_vec); best=-1e9; bi=i0
    for k in range(1,window):
        i=(i0+k)%n; p=c[i]@d
        if p>best: best=p; bi=i
        elif p<best-drop: break
    return bi
# anchor rules per wing. kinds: corner | walk(line, from, dir, tol) | extreme(from, dirline, window) | frac(a,b,f)
SEQ={'L1NE':['L1wEnd','L1nw','neN','tip','tipSW','sBend','sPeak',None],'NE':['notchE','neNW','neN','tip','tipSW','sBend','sPeak',None],
     'SW3':['swNW','swNE','notchS','notchB',None,'eTop','swSE','bumpE','bumpW','swSW','swW'],
     'SW2':['swNW','swNE','notchS','notchB',None,'eTop','swSE','notchE2','n2a','notchB2','n2b','notchW2','swSW','swW']}
MANUAL={'IMG_9068':{'L1wEnd':(49,502)}}
RULES={'L1wEnd':('walk','westUp','L1nw',-1,6.0),'notchE':('walk','neWest','neNW',-1,9.0),'sBend':('walk','neInner','tipSW',+1,3.5),'sPeak':('len','sBend'),
       'notchS':('walk','swEast','swNE',+1,3.5),'notchB':('len','notchS'),'eTop':('walk','swEastLower','swSE',-1,5.0),
       'bumpE':('walk','swSouth','swSE',+1,3.5),'bumpW':('walk','swSouthW','swSW',-1,3.5),
       'notchE2':('walk','swSouth','swSE',+1,3.5),'notchW2':('walk','swSouthW','swSW',-1,3.5),
       'notchB2':('extremeN','notchE2','swSouth'),'n2a':('frac','notchE2','notchW2',0.28),'n2b':('frac','notchE2','notchW2',0.72)}
def build(n,dbg=True,smoothing=1.0):
    reg=json.load(open(f'rect/{n}_reg2.json')); M=np.array(reg['M']); wing=reg['wing']; floor=reg['floor']
    O_={'1':O['O1'],'2':O['O2']}.get(floor,O['O34']); F=Frame(O_)
    img=cv2.imread(f'rect/{n}.png')[950:1850]; fp,c=wing_footprint(img); c=c.astype(float)
    if np.sign(signed_area(c))!=np.sign(signed_area(F.pts)): c=c[::-1]
    Mi=R.inv(M); scale=np.sqrt(abs(np.linalg.det(M[:2]))); lines={}
    for name,a,b in R.WALLS[wing]:
        pa=apply(Mi,V[a][None])[0]; pb=apply(Mi,V[b][None])[0]; lines[name]=R.fit_line(c,pa,pb,tol=12) or R.fit_line(c,pa,pb,tol=30)
    seq=SEQ[wing if wing in ('NE','L1NE') else 'SW'+floor]
    idx={}; fpos={}
    for k,v in reg['corners'].items(): idx[k]=int(np.argmin(np.linalg.norm(c-np.array(v),axis=1))); fpos[k]=F.pos[k]
    for k,v in MANUAL.get(n,{}).items():
        idx[k]=int(np.argmin(np.linalg.norm(c-np.array(v),axis=1)))
        if k=='L1wEnd': fpos[k]=max(F.pos['L1w'],F.pos['L1nw']-arc(c,idx[k],idx['L1nw'])*scale)
    def nearest_affine(name):
        near=apply(Mi,V[name][None])[0]; return int(np.argmin(np.linalg.norm(c-near,axis=1)))
    order=[nm for nm in seq if nm and RULES.get(nm,('x',))[0]!='frac']+[nm for nm in seq if nm and RULES.get(nm,('x',))[0]=='frac']
    for name in order:
        if name is None or name in idx: continue
        rule=RULES.get(name)
        if rule is None: idx[name]=nearest_affine(name); fpos[name]=F.pos[name]; continue
        if rule[0]=='walk':
            _,lname,fromc,direction,tol=rule
            if lines.get(lname) is None or fromc not in idx:
                if name in V: idx[name]=nearest_affine(name); fpos[name]=F.pos[name]
                continue
            idx[name]=walk(c,idx[fromc],lines[lname],direction,tol=tol,minrun=(60 if name=='notchE' else 10))
            L=arc(c,idx[fromc],idx[name]) if direction>0 else arc(c,idx[name],idx[fromc])
            # frame position: from the corner, scaled length, clamped at the named frame vertex (or sEnd for eTop)
            if name=='eTop': lim=F.pos['sEnd']; fpos[name]=max(lim,F.pos[fromc]-L*scale)
            elif name=='L1wEnd': fpos[name]=max(F.pos['L1w'],F.pos[fromc]-L*scale)
            else:
                target=F.pos[name]; start=F.pos[fromc]
                if direction>0: fpos[name]=min(target if target>start else target+F.L, start+L*scale)
                else: fpos[name]=max(target, start-L*scale)
        elif rule[0] in ('extreme','extremeN'):
            _,fromc,lname=rule
            if lines.get(lname) is not None: d=lines[lname][1]
            else:
                wa,wb=[(a,b) for nm,a,b in R.WALLS[wing] if nm==lname][0]; pa=apply(Mi,V[wa][None])[0]; pb=apply(Mi,V[wb][None])[0]; d=(pb-pa)/np.linalg.norm(pb-pa)
            if rule[0]=='extremeN': d=np.array([-d[1],d[0]]); d=d if (c.mean(0)-c[idx[fromc]])@d>0 else -d  # inward: toward centroid
            # direction of travel for 'extreme': from the previous corner toward fromc
            if rule[0]=='extreme':
                prev=c[idx[fromc]]-c[idx[fromc]-40]; d=d if prev@d>0 else -d
            win=int(min(len(c)//3, 2.5*(F.pos[name]-F.pos[fromc])/scale+50))
            idx[name]=extreme(c,idx[fromc],d,max(win,50)); fpos[name]=F.pos[name]; print('   ',name,'detail pt',np.round(c[idx[name]]),'from',fromc,np.round(c[idx[fromc]]),'dir',np.round(d,2),'win',win)
        elif rule[0]=='len':
            _,fromc=rule; n_=len(c); target=(F.pos[name]-F.pos[fromc])/scale; acc=0; i=idx[fromc]
            while acc<target: j=(i+1)%n_; acc+=np.linalg.norm(c[j]-c[i]); i=j
            idx[name]=i; fpos[name]=F.pos[name]; print('   ',name,'len pt',np.round(c[i]))
        elif rule[0]=='join':
            _,fromc,ca,cb=rule; pa=apply(Mi,V[ca][None])[0]; pb=apply(Mi,V[cb][None])[0]
            ln=R.fit_line(c,pa,pb,tol=30,margin=0.05)
            n_=len(c); found=None
            if ln is not None:
                m,d=ln[0],ln[1]; nrm=np.array([-d[1],d[0]])
                for k in range(30,n_//2):
                    i=(idx[fromc]+k)%n_
                    if abs((c[i]-m)@nrm)<3.5: found=i; break
            if found is None:  # fallback: scaled arc length
                target=(F.pos[name]-F.pos[fromc])/scale; acc=0; i=idx[fromc]
                while acc<target: j=(i+1)%n_; acc+=np.linalg.norm(c[j]-c[i]); i=j
                found=i
            idx[name]=found; fpos[name]=F.pos[name]; print('   ',name,'join pt',np.round(c[found]),'line n',ln[2] if ln else None)
        elif rule[0]=='nearestA':
            _,fromc=rule; near=apply(Mi,V[name][None])[0]; win=int(min(len(c)//3,3*(F.pos[name]-F.pos[fromc])/scale+80)); n_=len(c)
            ids=[(idx[fromc]+k)%n_ for k in range(1,win)]; dd=np.linalg.norm(c[ids]-near,axis=1); idx[name]=ids[int(np.argmin(dd))]; fpos[name]=F.pos[name]
            print('   ',name,'nearest-affine detail pt',np.round(c[idx[name]]),'dist %.1f'%dd.min())
        elif rule[0]=='frac':
            _,a,b,f=rule; sub=contour_sub(c,idx[a],idx[b]); cum=np.r_[0,np.cumsum(np.linalg.norm(np.diff(sub,axis=0),axis=1))]
            k=int(np.searchsorted(cum,cum[-1]*f)); idx[name]=(idx[a]+k)%len(c); fpos[name]=F.pos[name]
    src=[];dst=[]
    for k in range(len(seq)):
        A=seq[k]; B=seq[(k+1)%len(seq)]
        if A is None or B is None or A not in idx or B not in idx: continue
        sub=contour_sub(c,idx[A],idx[B]); 
        if len(sub)<4: continue
        n_=max(3,int(arc(c,idx[A],idx[B])*scale/15))
        src.append(resample(sub,n_)); dst.append(F.path(fpos[A],fpos[B],n_))
    src=np.vstack(src); dst=np.vstack(dst); W=Warp(M,src,dst,smoothing=smoothing)
    res=np.linalg.norm(W(src)-dst,axis=1); print(n,'ctrl',len(src),'resid mean %.1f max %.1f'%(res.mean(),res.max()))
    if dbg:
        rooms=json.load(open(f'rect/{n}_rooms.json'))
        im=np.full((1100,2050,3),255,np.uint8); fr=outline_pts(O_,None,step=2); cv2.polylines(im,[fr.astype(np.int32)],True,(0,0,0),2)
        cv2.polylines(im,[W(c).astype(np.int32)],True,(0,160,0),1)
        for key,col in [('room',(0,0,255)),('white',(200,0,200)),('corr',(0,120,0))]:
            for k,cp in enumerate(rooms[key]):
                p=W(np.array(cp['poly'],float)); cv2.polylines(im,[p.astype(np.int32)],True,col,1)
                cx,cy=p.mean(0).astype(int); cv2.putText(im,(str(k) if key=='room' else key[0]+str(k)),(cx-6,cy+4),cv2.FONT_HERSHEY_SIMPLEX,0.35,(120,0,0),1)
        cv2.imwrite(f'rect/{n}_frame.png',im)
        im2=img.copy()
        for name,i in idx.items():
            p=c[i]; cv2.circle(im2,tuple(p.astype(int)),5,(0,255,0),2); cv2.putText(im2,name,(int(p[0])+5,int(p[1])-5),cv2.FONT_HERSHEY_SIMPLEX,0.4,(0,120,0),1)
        x,y,w,h=cv2.boundingRect(c.astype(np.int32)); cv2.imwrite(f'rect/{n}_det.png',im2[max(0,y-20):y+h+20,max(0,x-20):x+w+20])
    return W,O_,c,idx
if __name__=='__main__':
    for n in sys.argv[1:]: build(n)
