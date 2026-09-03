import cv2, numpy as np, json, sys
from seg import wing_footprint
from flat import flatfield
def segment(n, kind):
    img=cv2.imread(f'rect/{n}.png')[950:1850]; fp,c=wing_footprint(img); ff=flatfield(img)
    hsv=cv2.cvtColor(ff,cv2.COLOR_BGR2HSV); S=hsv[...,1].astype(int); Vv=hsv[...,2].astype(int)
    if kind=='NE': colored=(S>=125)&(Vv>=140); corr=(S>=45)&(S<125)&(Vv>=170)
    else: colored=(S>=180)&(Vv>=170); corr=(S>=40)&(S<180)&(Vv>=190)
    white=(S<40)&(Vv>=190)
    # dark divider lines relative to local surroundings (robust to glare)
    Vf=Vv.astype(np.float32); loc=cv2.blur(Vf,(25,25)); rel=(Vf<loc-18)
    colored&=~rel; corr&=~rel
    colored&=fp>0; corr&=fp>0; white&=fp>0
    out={}
    for name,m in [('room',colored),('corr',corr),('white',white)]:
        m=m.astype(np.uint8)
        m=cv2.morphologyEx(m,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
        num,lab,stats,cent=cv2.connectedComponentsWithStats(m,connectivity=4)
        comps=[]
        for i in range(1,num):
            a=stats[i,cv2.CC_STAT_AREA]
            if a<(250 if name!='white' else 800): continue
            mask=(lab==i).astype(np.uint8)
            mask=cv2.dilate(mask,np.ones((3,3),np.uint8))  # undo the erosion/opening & anti-alias inset
            cnts,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE); cc=max(cnts,key=cv2.contourArea)
            poly=cv2.approxPolyDP(cc,2.0,True).reshape(-1,2)
            comps.append({'area':int(a),'centroid':cent[i].tolist(),'poly':poly.tolist(),'medS':float(np.median(S[lab==i])),'medV':float(np.median(Vv[lab==i]))})
        out[name]=comps
    return img,out,c
if __name__=='__main__':
    n,kind=sys.argv[1],sys.argv[2]
    img,out,c=segment(n,kind)
    json.dump(out,open(f'rect/{n}_rooms.json','w'))
    print(n,{k:len(v) for k,v in out.items()})
    dbg=img.copy()
    col={'room':(0,0,255),'corr':(0,180,0),'white':(255,0,255)}
    for k,comps in out.items():
        for i,cp in enumerate(comps):
            cv2.polylines(dbg,[np.array(cp['poly'],np.int32)],True,col[k],1)
            cx,cy=map(int,cp['centroid'])
            if k=='room': cv2.putText(dbg,str(i),(cx-8,cy+12),cv2.FONT_HERSHEY_SIMPLEX,0.4,(0,0,0),2); cv2.putText(dbg,str(i),(cx-8,cy+12),cv2.FONT_HERSHEY_SIMPLEX,0.4,(0,255,255),1)
    x,y,w,h=cv2.boundingRect(c); dbg=dbg[max(0,y-10):y+h+10,max(0,x-10):x+w+10]
    cv2.imwrite(f'rect/{n}_comp.png',cv2.resize(dbg,None,fx=1.5,fy=1.5,interpolation=cv2.INTER_CUBIC))
