import cv2, numpy as np, json, sys
def wing_footprint(img, sat_min=45, dark=120):
    hsv=cv2.cvtColor(img,cv2.COLOR_BGR2HSV); gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    m=((hsv[...,1]>sat_min)|(gray<dark)).astype(np.uint8)
    m=cv2.morphologyEx(m,cv2.MORPH_CLOSE,np.ones((21,21),np.uint8))
    n,lab,stats,_=cv2.connectedComponentsWithStats(m)
    big=1+np.argmax(stats[1:,cv2.CC_STAT_AREA]); fp=(lab==big).astype(np.uint8)
    # fill holes
    cnts,_=cv2.findContours(fp,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)
    c=max(cnts,key=cv2.contourArea); fp=np.zeros_like(fp); cv2.drawContours(fp,[c],-1,1,-1)
    fp=cv2.morphologyEx(fp,cv2.MORPH_OPEN,np.ones((7,7),np.uint8))
    cnts,_=cv2.findContours(fp,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE); c=max(cnts,key=cv2.contourArea)
    return fp, c.reshape(-1,2)
def kmeans_colors(img, fp, k=6):
    hsv=cv2.cvtColor(img,cv2.COLOR_BGR2HSV).astype(np.float32)
    pix=hsv[fp>0]
    # sample
    idx=np.random.RandomState(0).choice(len(pix),min(60000,len(pix)),replace=False)
    Z=pix[idx]
    crit=(cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER,50,0.5)
    _,labels,centers=cv2.kmeans(Z,k,None,crit,5,cv2.KMEANS_PP_CENTERS)
    counts=np.bincount(labels.ravel(),minlength=k)
    return centers,counts
if __name__=='__main__':
    n=sys.argv[1]; y0,y1=int(sys.argv[2]),int(sys.argv[3])
    img=cv2.imread(f'rect/{n}.png')[y0:y1]
    fp,c=wing_footprint(img)
    print('footprint bbox',cv2.boundingRect(c))
    centers,counts=kmeans_colors(img,fp)
    for cc,cn in sorted(zip(centers.tolist(),counts.tolist()),key=lambda x:-x[1]): print('HSV',np.round(cc),'count',cn)
    dbg=img.copy(); cv2.drawContours(dbg,[c.reshape(-1,1,2)],-1,(0,0,255),2); cv2.imwrite(f'rect/{n}_wing.png',dbg)
