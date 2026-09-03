import cv2, numpy as np
def flatfield(img):
    """Divide by a smooth (quadratic) estimate of the paper-white illumination."""
    hsv=cv2.cvtColor(img,cv2.COLOR_BGR2HSV)
    white=(hsv[...,1]<30)&(hsv[...,2]>150)
    h,w=white.shape; ys,xs=np.nonzero(white)
    sel=np.random.RandomState(0).choice(len(ys),min(40000,len(ys)),replace=False); ys=ys[sel];xs=xs[sel]
    X=np.stack([np.ones_like(xs),xs,ys,xs*xs,xs*ys,ys*ys],1).astype(float)
    gx,gy=np.meshgrid(np.arange(w),np.arange(h)); G=np.stack([np.ones(gx.size),gx.ravel(),gy.ravel(),(gx*gx).ravel(),(gx*gy).ravel(),(gy*gy).ravel()],1)
    out=np.zeros_like(img,np.float32)
    for c in range(3):
        coef,_,_,_=np.linalg.lstsq(X,img[ys,xs,c].astype(float),rcond=None)
        field=(G@coef).reshape(h,w); out[...,c]=img[...,c]/np.maximum(field,1)*235
    return np.clip(out,0,255).astype(np.uint8)
