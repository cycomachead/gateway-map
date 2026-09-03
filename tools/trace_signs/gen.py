"""Generate per-floor room/POI data (frame coordinates) from the segmented, registered detail signs."""
import json, numpy as np, cv2, sys
import register5 as R5
import gen_geom as G
from labels import SIGNS, NAMES, cat_for, special
from register import outline_pts, O
FLOOR_OUTLINE={'1':O['O1'],'2':O['O2'],'3':O['O34']}
def wall_dirs(O_):
    d={}
    for k,v in enumerate(O_):
        w=O_[(k+1)%len(O_)]; d[v['name']]=(np.array([w['x']-v['x'],w['y']-v['y']]))
    return d
WALL_BY_NAME={'neNorth':'neNW','swSouth':'swSE','neWest':'notchE','swNorth':'swNW'}
def snapper_for(O_):
    walls={}; corners={}
    for k,v in enumerate(O_):
        w=O_[(k+1)%len(O_)]; corners[v['name']]=(v['x'],v['y'])
        if abs(v['bulge'])<1e-9: walls[v['name']]=((v['x'],v['y']),(w['x'],w['y']))
    return G.Snapper(walls,corners,tol=9.0,corner_tol=12.0), outline_pts(O_,None,step=1)
def snap_arcs(poly,dense,tol=7.0):
    from scipy.spatial import cKDTree
    t=cKDTree(dense); d,j=t.query(poly); out=poly.copy()
    for i in range(len(poly)):
        if d[i]<tol: out[i]=dense[j[i]]
    return out
def gen_floor(floor, signs):
    O_=FLOOR_OUTLINE[floor]; snapper,dense=snapper_for(O_); dirs=wall_dirs(O_)
    rooms=[]; pois=[]
    for n in signs:
        spec=SIGNS[n]; wing=spec['wing']; W,_,c,idx=R5.build(n,dbg=False)
        comps=json.load(open(f'rect/{n}_rooms.json'))
        polys={}
        for key,lst in comps.items():
            for k,cp in enumerate(lst): polys[f'{key[0]}{k}']=np.array(cp['poly'],float)
        for k,p in spec.get('manual',{}).items(): polys[k]=np.array(p,float)
        for k,parts in spec.get('merge',{}).items(): polys[k]=G.hull(np.vstack([polys[q] for q in parts]))
        for k in spec.get('hull',[]): polys[k]=G.hull(polys[k])
        out={}  # id -> frame poly
        for k,lab in spec['rooms'].items():
            if k in spec.get('split',{}): continue
            out[(k,lab)]=W(polys[k])
        for k,sp in spec.get('split',{}).items():
            wallname,ids=sp[0],sp[1]; fr=sp[2] if len(sp)>2 else [i/len(ids) for i in range(1,len(ids))]
            d=(0,1) if wallname=='y' else dirs[WALL_BY_NAME.get(wallname,wallname)]
            pieces=G.split_along(G.hull(W(polys[k])),d,fr)
            # order pieces along direction
            for pid,pc in zip(ids,pieces): out[(k+'/'+pid,pid)]=pc
        unl=0
        for (k,lab),p in out.items():
            p=G.clean(p); p,tags=snapper.snap(p); p=G.dedupe(p,1.0)
            if len(p)<3: print('skip tiny',n,k); continue
            sp=special(wing)
            if lab=='?':
                unl+=1; rid=f"{ {'Northeast':'ne','Southwest':'sw'}[wing] }-room-{unl}"; rooms.append(dict(wing=wing,id=rid,cat='office',poly=p,name='Unlabelled room',label='',tags=['unlabelled']))
            elif lab in sp:
                rid,cat,name,label,tags=sp[lab]; rooms.append(dict(wing=wing,id=rid,cat=cat,poly=p,name=name,label=label,tags=tags))
            else:
                extra={}
                if lab in NAMES: extra={'name':NAMES[lab][0]}; cat=NAMES[lab][1]
                else: cat=cat_for(lab,floor)
                rooms.append(dict(wing=wing,id=lab,cat=cat,poly=p,**extra))
        for kind,xy in spec.get('pois',{}).items():
            p=W(np.array([xy],float))[0]
            if kind=='kitchen': pois.append(dict(id=f"{ {'Northeast':'ne','Southwest':'sw'}[wing] }-kitchen",name=f'{wing} social kitchen',kind='cafe',at=p.tolist()))
            elif kind=='porch': pois.append(dict(id=f"{ {'Northeast':'ne','Southwest':'sw'}[wing] }-porch",name=f'{wing} front porch',kind='porch',at=p.tolist()))
    if floor=='1':
        T67=np.array(json.load(open('T67.json')))
        from register import affine_fit, apply
        hull_src=np.array([[-19.1,371.1],[289.2,271.7],[473.5,939.2]]); V=O['V']
        def lerp(a,b,t): return [a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t]
        isl_dst=np.array([V['swNW'],lerp(V['swNW'],V['swNE'],0.76),lerp(V['swSE'],V['swSW'],0.74)])
        A=affine_fit(hull_src,isl_dst)
        def m(p): return apply(A,apply(T67,np.array(p,float)))
        sw=[('sw-stair-2','circulation','Southwest Stair (north)','Stair',['stairs'],[(185,225),(215,218),(220,252),(190,258)]),
            ('sw-room-1','open','Open workspace','',['unlabelled'],[(115,265),(175,252),(185,315),(125,328)]),
            ('sw-elevator','circulation','Southwest Elevator','Elevator',['elevator'],[(150,340),(175,338),(177,365),(152,367)]),
            ('sw-restrooms','service','Restrooms (SW)','WC',['restroom','women','men','all gender'],[(177,336),(222,328),(226,362),(180,368)]),
            ('sw-stair','circulation','Southwest Stair','Stair',['stairs'],[(195,372),(225,366),(230,398),(200,404)]),
            ('sw-room-2','office','Unlabelled room','',['unlabelled'],[(200,410),(240,402),(250,450),(210,458)])]
        for rid,cat,name,label,tags,poly in sw:
            rooms.append(dict(wing='Southwest',id=rid,cat=cat,poly=G.clockwise(m(poly)),name=name,label=label,tags=tags))
        pois.append(dict(id='sw-porch',name='Southwest front porch',kind='porch',at=m([(215,352)])[0].tolist()))
    # weld shared vertices across rooms
    welded=G.weld([r['poly'] for r in rooms],tol=4.5)
    for r,p in zip(rooms,welded): r['poly']=[[round(float(x),1),round(float(y),1)] for x,y in G.dedupe(p,0.5)]
    wf=json.load(open('wholefloor_items.json'))[floor]
    pois.append(dict(id='ne-entrance',name='Northeast entrance',kind='exit',at=wf['ne_entrance']))
    pois.append(dict(id='sw-entrance',name='Southwest entrance',kind='exit',at=wf['sw_entrance']))
    pois.append(dict(id='east-stair',name='East stair',kind='stairs',at=wf['east_stair']))
    if 'nw_stair' in wf: pois.append(dict(id='nw-stair',name='Northwest stair',kind='stairs',at=wf['nw_stair']))
    for p in pois: p['at']=[round(float(p['at'][0]),1),round(float(p['at'][1]),1)]
    return dict(floor=floor,rooms=rooms,pois=pois,atrium=dict(c=wf['atrium'],r=wf['atrium_r']))
CAT_COL={'office':(90,130,220),'open':(150,180,240),'meeting':(230,150,60),'focus':(240,200,90),'lab':(120,200,120),'amenity':(220,120,200),'service':(200,200,200),'circulation':(230,230,230),'classroom':(100,180,200)}
def render(data, out):
    O_=FLOOR_OUTLINE[data['floor']]; im=np.full((1100,2050,3),255,np.uint8)
    fr=outline_pts(O_,None,step=2)
    for r in data['rooms']:
        p=np.array(r['poly'],np.int32); col=CAT_COL.get(r['cat'],(0,0,0)); cv2.fillPoly(im,[p],col[::-1]); cv2.polylines(im,[p],True,(60,60,60),1)
        c=p.mean(0).astype(int); cv2.putText(im,r.get('label',r['id']) if r.get('label') is not None else r['id'],(c[0]-12,c[1]+4),cv2.FONT_HERSHEY_SIMPLEX,0.32,(0,0,0),1)
    cv2.polylines(im,[fr.astype(np.int32)],True,(0,0,0),2)
    for p in data['pois']:
        x,y=map(int,p['at']); cv2.circle(im,(x,y),7,(0,0,200),2); cv2.putText(im,p['kind'],(x+8,y+4),cv2.FONT_HERSHEY_SIMPLEX,0.35,(0,0,200),1)
    c=data['atrium']['c']; r=data['atrium']['r']; cv2.ellipse(im,(int(c[0]),int(c[1])),(int(r[0]),int(r[1])),0,0,360,(120,120,120),1)
    cv2.imwrite(out,im)
if __name__=='__main__':
    plan={'3':['IMG_9059','IMG_9061'],'2':['IMG_9064','IMG_9062'],'1':['IMG_9068']}
    for f,signs in plan.items():
        data=gen_floor(f,signs)
        json.dump(data,open(f'floor{f}.json','w'))
        render(data,f'rect/floor{f}_render.png')
        print('floor',f,'rooms',len(data['rooms']),'pois',len(data['pois']))
