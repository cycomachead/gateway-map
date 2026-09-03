import cv2, numpy as np, json, sys
from seg import wing_footprint
from flat import flatfield
def icons(n):
    img=cv2.imread(f'rect/{n}.png')[950:1850]; fp,c=wing_footprint(img); ff=flatfield(img)
    hsv=cv2.cvtColor(ff,cv2.COLOR_BGR2HSV); H,S,V=[hsv[...,i].astype(int) for i in range(3)]
    out={}
    # red "you are here": hue ~0/180, high S
    red=((H<8)|(H>172))&(S>120)&(V>100)&(fp>0)
    num,lab,st,cen=cv2.connectedComponentsWithStats(red.astype(np.uint8))
    if num>1:
        i=1+np.argmax(st[1:,cv2.CC_STAT_AREA]); out['here']=cen[i].tolist()
    # dark icons inside the light corridor: dark blobs (V<90) whose surrounding is corridor-light
    dark=((V<90)&(fp>0)).astype(np.uint8)
    num,lab,st,cen=cv2.connectedComponentsWithStats(dark,connectivity=8)
    cands=[]
    for i in range(1,num):
        a=st[i,cv2.CC_STAT_AREA]; w=st[i,cv2.CC_STAT_WIDTH]; h=st[i,cv2.CC_STAT_HEIGHT]
        if a<150 or a>2500 or w>90 or h>90: continue
        x,y=int(cen[i][0]),int(cen[i][1])
        # ring sample: is the neighbourhood light (corridor/white)?
        y0,y1,x0,x1=max(0,y-45),min(V.shape[0],y+45),max(0,x-45),min(V.shape[1],x+45)
        ring=V[y0:y1,x0:x1]; light=(ring>150).mean()
        if light>0.55: cands.append({'c':[float(cen[i][0]),float(cen[i][1])],'area':int(a),'w':int(w),'h':int(h),'fill':float(a/(w*h))})
    out['dark']=cands
    return out
if __name__=='__main__':
    for n in sys.argv[1:]:
        o=icons(n); print(n,'here',np.round(o.get('here',[0,0])))
        for d in o['dark']: print('   dark',np.round(d['c']),'a',d['area'],'wh',d['w'],d['h'],'fill %.2f'%d['fill'])
        json.dump(o,open(f'rect/{n}_icons.json','w'))
