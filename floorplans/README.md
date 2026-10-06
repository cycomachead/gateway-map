# Floorplan references

Inventory of all 26 reference files in this checkout. Paths and spelling match the files on disk.

Use the October 2025 vector floorplans for wall geometry and alignment. Building-sign photos
are secondary references for room numbers and broad shape corrections; do not replace precise
CAD walls with photo distortion. The website PNGs are low-resolution overview references.

`lowerlevel-whole-floor.jpeg`, requested in the ticket, is not present in this checkout.
Lower-level numbering below comes from the teaching-spaces PDF instead; check it against
that sign when the photo becomes available.

## Building signs

- [level1-northeast.jpg](builsding-signs/level1-northeast.jpg)
- [level1-whole-floor.jpg](builsding-signs/level1-whole-floor.jpg)
- [level2-northeast.jpg](builsding-signs/level2-northeast.jpg)
- [level2-southwest.jpg](builsding-signs/level2-southwest.jpg)
- [level2-whole-floor.jpg](builsding-signs/level2-whole-floor.jpg)
- [level3-northeast.jpg](builsding-signs/level3-northeast.jpg)
- [level3-southwest.jpg](builsding-signs/level3-southwest.jpg)
- [level3-whole-floor-sw.jpg](builsding-signs/level3-whole-floor-sw.jpg)
- [level3-whole-floor.jpg](builsding-signs/level3-whole-floor.jpg)

## Architect floorplans and teaching references

- [1210 LH - Seating Numbers.pdf](architect-pdfs/floorplans/1210%20LH%20-%20Seating%20Numbers.pdf)
- [230628_Berkeley Gateway_Teaching Spaces_Final_R (3).pdf](architect-pdfs/floorplans/230628_Berkeley%20Gateway_Teaching%20Spaces_Final_R%20%283%29.pdf)
- [Gateway Furniture Floor 1.pdf](architect-pdfs/floorplans/Gateway%20Furniture%20Floor%201.pdf)
- [Gateway Plan View 10_2_2025.pdf](architect-pdfs/floorplans/Gateway%20Plan%20View%2010_2_2025.pdf)
- [floorplan_floor-1_2025-10-02.pdf](architect-pdfs/floorplans/floorplan_floor-1_2025-10-02.pdf)
- [floorplan_floor-2_2025-10-02.pdf](architect-pdfs/floorplans/floorplan_floor-2_2025-10-02.pdf)
- [floorplan_floor-3_2025-10-02.pdf](architect-pdfs/floorplans/floorplan_floor-3_2025-10-02.pdf)
- [floorplan_floor-4_2025-10-02.pdf](architect-pdfs/floorplans/floorplan_floor-4_2025-10-02.pdf)
- [floorplan_floor-5_2025-10-02.pdf](architect-pdfs/floorplans/floorplan_floor-5_2025-10-02.pdf)
- [floorplan_floor-lower-level_2025-10-02.pdf](architect-pdfs/floorplans/floorplan_floor-lower-level_2025-10-02.pdf)

## Website overview images

- [FLAT-1-2x.png](architect-pdfs/lowres-website-images/FLAT-1-2x.png)
- [FLAT-2-2x.png](architect-pdfs/lowres-website-images/FLAT-2-2x.png)
- [FLAT-3-2x.png](architect-pdfs/lowres-website-images/FLAT-3-2x.png)
- [FLAT-4-2x.png](architect-pdfs/lowres-website-images/FLAT-4-2x.png)
- [FLAT-5-2x.png](architect-pdfs/lowres-website-images/FLAT-5-2x.png)
- [LOWER_LEVEL-2x.png](architect-pdfs/lowres-website-images/LOWER_LEVEL-2x.png)

## AV studio

- [av studio.pdf](architect-pdfs/av%20studio.pdf)

## Lower-level teaching rooms

Source: [Teaching Spaces PDF](architect-pdfs/floorplans/230628_Berkeley%20Gateway_Teaching%20Spaces_Final_R%20%283%29.pdf),
**one-based PDF pages 3, 4 and 10**. These are design-plan annotations, not a verification of
current installed furniture or occupancy limits. The filename begins with 230628, but page 3
also records a 5.23.24 meeting update.

| Room | Use | Seats shown on pages 4 and 10 | Location on the plan |
| --- | --- | --- | --- |
| B1026 | Classroom | 40 | Left end of the upper curved band |
| B1022 | Classroom | 50 | Left middle of the upper curved band |
| B1016 | Classroom | 50 | Right middle of the upper curved band |
| B1012 | Classroom | 40 | Right end of the upper curved band |
| B1019 | Active learning classroom | 50 | Large central room below the piazza |
| B1015 | Classroom | 30 | Immediately right of B1019 |
| B1013 | Group study | Not stated | Immediately right of B1015 |
| B1023 | Classroom | 40 | Rectangular room below-left of B1019 |
| B1008 | Classroom | 30 | Upper room beside the right curved stair |
| B1009 | Classroom | 30 | Lower room beside the right curved stair |

- Page 3 identifies the two rounded piazza/open-study areas and shows work-height tables,
  chairs and mobile markerboards. It does not supply room numbers for those areas.
  The map numbers them B1030 (the curve on the west side) and B1010 (inside the main stair).
- Page 4 identifies B1019 as an active learning classroom with rectangular tables and
  stackable chairs, and marks its storage closet and a nearby storage room.
- Page 10 shows tablet-arm classroom seating and repeats the room-number key.
  Its comments request more whiteboard space in B1008/B1009 and consideration of a table
  layout in B1023; these are design requests, not confirmed room amenities.

Pages 18 (1220, 150-seat lecture hall) and 21 (1210, 300-seat lecture hall) outline the two
Floor 1 lecture halls in red dashes; the map uses those outlines for the hall shapes.

The map uses the numbers and uses above, with simplified classroom walls from the October
2025 CAD plan. `tools/trace_cad/floors.py` keeps these corrections reproducible; regeneration
preserves the common coordinate frame used by all floors.
