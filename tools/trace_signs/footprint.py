import cv2, numpy as np, json, sys
def footprint(path, dark_thresh=110, out=None, eps=6):
    img=cv2.imread(path); gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    hsv=cv2.cvtColor(img,cv2.COLOR_BGR2HSV)
    dark=(gray<dark_thresh).astype(np.uint8)
    dark=cv2.dilate(dark,np.ones((3,3),np.uint8))
    # flood from corners over non-dark region
    h,w=gray.shape
    ff=(1-dark).copy(); mask=np.zeros((h+2,w+2),np.uint8)
    for seed in [(2,2),(w-3,2),(2,h-3),(w-3,h-3)]:
        if ff[seed[1],seed[0]]==1: cv2.floodFill(ff,mask,seed,2)
    inside=(ff!=2).astype(np.uint8)
    n,lab,stats,_=cv2.connectedComponentsWithStats(inside)
    big=1+np.argmax(stats[1:,cv2.CC_STAT_AREA])
    fp=(lab==big).astype(np.uint8)*255
    fp=cv2.morphologyEx(fp,cv2.MORPH_OPEN,np.ones((9,9),np.uint8))
    cnts,_=cv2.findContours(fp,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)
    c=max(cnts,key=cv2.contourArea)
    ap=cv2.approxPolyDP(c,eps,True).reshape(-1,2)
    if out:
        dbg=img.copy(); cv2.polylines(dbg,[ap],True,(0,0,255),2)
        for i,(x,y) in enumerate(ap):
            cv2.circle(dbg,(int(x),int(y)),4,(0,255,0),-1)
            cv2.putText(dbg,str(i),(int(x)+4,int(y)-4),cv2.FONT_HERSHEY_SIMPLEX,0.45,(0,120,0),1)
        cv2.imwrite(out,dbg)
    return ap, c.reshape(-1,2)
if __name__=='__main__':
    res={}
    for n in ['IMG_9058','IMG_9060','IMG_9066','IMG_9067']:
        ap,c=footprint(f'rect/{n}.png',out=f'rect/{n}_fp.png')
        res[n]={'approx':ap.tolist(),'contour':c.tolist()}
        print(n,len(ap),ap.tolist())
    json.dump(res,open('rect/footprints.json','w'))
