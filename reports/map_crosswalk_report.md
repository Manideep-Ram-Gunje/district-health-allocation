# Map Crosswalk

geoBoundaries ADM2 polygons matched to NFHS-5 districts.

The ADM2 file carries an **empty `shapeISO`** on every feature, so it has no state column. Matching district names nationally would confuse same-named districts in different states, and a choropleth that colours the wrong polygon is worse than no map because it still looks authoritative.

State is therefore recovered geometrically: each district polygon's *representative point* — guaranteed to lie inside the polygon, unlike a centroid, which can fall outside a concave or multipart shape — is spatially joined into the ADM1 state polygons. Name matching is then restricted within state, and the Phase 1 directional guard still applies.

## Coverage

| Metric | Value |
|---|---|
| ADM2 polygons | 735 |
| State resolved by spatial join | 734 |
| Polygons matched to a district | 683 (92.9%) |
| Our districts with a polygon | 683 of 705 (96.9%) |
| Duplicate polygons released to keep 1:1 | 1 |
| Polygons sharing a district_id (must be 0) | 0 |

## Districts with no polygon

These will be absent from the choropleth. The map is an illustration; the allocation table is the deliverable, and it is unaffected.

| State | District |
|---|---|
| Andhra Pradesh | Y.S.R. |
| Assam | Karbi Anglong |
| Bihar | Buxer |
| Chhattisgarh | Dantewada |
| Gujarat | Botad |
| Gujarat | Dahod |
| Gujarat | Panchmahal |
| Gujarat | Sabarkantha |
| Haryana | Charkhi Dadri |
| Madhya Pradesh | Agar Malwa |
| Puducherry | Yanam |
| Telangana | Bhadradri Kothagudem |
| Telangana | Jayashankar Bhupalapally |
| Telangana | Jogulamba Gadwal |
| Telangana | Komaram Bheem Asifabad |
| Telangana | Medchal-Malkajgiri |
| Telangana | Warangal Rural |
| Telangana | Warangal Urban |
| Tripura | Sepahijala |
| Uttar Pradesh | Prayagraj |
| Uttarakhand | Pauri Garhwal |
| West Bengal | Purba Barddhaman |
