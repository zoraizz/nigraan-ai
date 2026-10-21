# Indus villages from Taunsa to Kotri

`villages.json` lists 926 OpenStreetMap settlements whose nodes sit inside the UNOSAT July–August 2022 flood water and within 15 km of the Indus between Taunsa Barrage and Kotri Barrage. `indus.geojson` is the centreline those river kilometres are measured on.

Neither file is a gauge reading. Populations are grid estimates, not a census.

## Method

The build script is `scripts/flood/build_villages.py`. It is a batch job. The first run downloads sources and queries Overpass. Later runs read a local cache and do not use the network.

### Centreline

OpenStreetMap ways tagged `waterway=river` whose `name` or `name:en` matches "Indus", from upstream of Tarbela to the river mouth. Endpoints within 200 m are joined. The line kept is the shortest path from the junction nearest Tarbela Dam to the mouth, so a side channel cannot pull the stem off the barrages. It is then cut to the nearest point on that path to Tarbela Dam and the nearest point to Kotri Barrage.

Distances used only to join and cut the line are in EPSG:32642. `river_km` is the WGS84 geodesic length along the published line, starting at 0 at Tarbela. The line is Douglas–Peucker simplified to 300 vertices. The published line is 1,467.9 km.

Structure anchors used to cut the line, not gauge coordinates:

| Place | Latitude | Longitude |
| --- | --- | --- |
| Tarbela Dam | 34.089722 | 72.698333 |
| Taunsa Barrage | 30.51278 | 70.84917 |
| Kotri Barrage | 25.44222 | 68.31667 |

After simplification the line is about 790 m from the Tarbela Dam coordinate (the dam is much wider than the river node), 80 m from Taunsa Barrage, 20 m from Kotri Barrage, and about 1.9 km from the Sukkur Barrage coordinate. Kalabagh, Chashma, Taunsa, Guddu, Sukkur and Kotri fall in that downstream order.

### Villages

A settlement is kept only when all of these are true:

1. OpenStreetMap `place` is `village`, `town`, or `city` (nodes, plus ways and relations by their centre), with a name.
2. The point is within 15 km of the Taunsa–Kotri portion of the centreline, measured in EPSG:32642. The Taunsa end includes the round 15 km cap.
3. The point intersects the UNOSAT VIIRS cumulative flood-water polygon for Pakistan, 1 July–31 August 2022.

For each kept settlement:

- `river_km` is the geodesic kilometre of the closest point on the full Tarbela–Kotri centreline.
- `bank` is `left` or `right` facing downstream. In the UTM plane the cross product of the segment direction and the vector to the settlement is positive on the left bank.
- `district` is the OCHA admin-2 polygon that contains the point, or the nearest admin-2 polygon when the point falls in a boundary gap.
- `population` is the sum of WorldPop 2020 Pakistan 100 m people-per-pixel values whose centres lie inside a 1 km circle around the node, rounded to the nearest integer. `population_source` is `WorldPop 2020 estimate`.
- `sources` cites the OSM object, the UNOSAT layer, the WorldPop raster, the admin boundaries, and the centreline.

1,979 named settlements were within 15 km. 926 of those nodes fall inside the 2022 water polygon. Counts by admin-2 district:

| District | Settlements |
| --- | --- |
| Larkana | 252 |
| Dadu | 176 |
| Shikarpur | 141 |
| Khairpur | 82 |
| Jamshoro | 59 |
| Sukkur | 55 |
| Naushahro Feroze | 44 |
| Kashmore | 31 |
| Matiari | 24 |
| Hyderabad | 24 |
| Muzaffargarh | 13 |
| Rajanpur | 9 |
| Ghotki | 5 |
| Sanghar | 4 |
| Shaheed Benazir Abad | 3 |
| Rahim Yar Khan | 2 |
| Dera Ghazi Khan | 1 |
| Kambar Shahdad Kot | 1 |

Larkana, Dadu and Jamshoro settlements in this file are on the right bank. Khairpur and Ghotki settlements in this file are on the left bank. Sukkur district is split across the river. That matches the banks facing downstream.

## Sources

- OpenStreetMap, ODbL. Indus ways via Overpass (`waterway=river`, name matching Indus). Settlements via Overpass (`place=village|town|city`).
- Tarbela Dam, Taunsa Barrage and Kotri Barrage coordinates: Wikipedia structure locations, used only to cut the centreline.
- UNOSAT VIIRS cumulative satellite-detected flood water over Pakistan, 1 July–31 August 2022, event FL20220808PAK. HDX dataset "Satellite detected water extents between 01 and 29 August 2022 over Pakistan", resource `viirs_20220701_20220831_floodextent_pak.zip`. Mapped area about 86,600 km². Water class on the layer is flood water. Not field validated.
- WorldPop unconstrained Pakistan 2020, 100 m (3 arc-second) people per pixel, `pak_ppp_2020.tif`. Random-forest dasymetric redistribution, not a census count.
- OCHA COD-AB Pakistan administrative boundaries, HDX `cod-ab-pak`, layer `pak_admin2` (160 districts).

## Limits

Populations are estimates. The number is people on the WorldPop grid within 1 km of the OpenStreetMap node, not the official population of that named place. A node in a dense town sums the surrounding circle, so it can include people who do not live in that settlement, and it can miss people who live further than 1 km from the node. Do not present these figures as census or as gauge data.

The 2022 extent is detected water, including breach flooding away from the main channel. The barrage-to-barrage routing model cannot predict those breaches. A row in this file means the settlement node fell in mapped water in July–August 2022. It does not mean a flood wave travelling only in the channel reaches that village.

The same rule excludes dry-bank towns. Sukkur, Rohri, Larkana, Khairpur, Dadu, Kandhkot, Ghotki, Kotri and Jamshoro town coordinates used as a check are within 15 km of the centreline and outside the water polygon, so those towns are not rows. Smaller settlements in those districts are included where the node itself lies in the mapped water. VIIRS resolution is about 375 m, and a node just outside a polygon is dropped.

The centreline is one named OSM channel, not every braid. Simplification to 300 vertices can move a bend by a few hundred metres. `river_km` follows that simplified line.

District names are the COD-AB spellings, including "Kambar Shahdad Kot" and "Shaheed Benazir Abad".

Files in `flood-tracker/data/fixtures/` are hand-made contract examples. They are not this table.

## Regenerate

```text
pip install -r scripts/flood/requirements-geo.txt
python scripts/flood/build_villages.py
python scripts/flood/build_villages.py --check
```

The cache directory is `FLOOD_GEO_CACHE`, or `~/.cache/nigraan-flood-geo` when that variable is unset. The WorldPop raster is about 519 MB.
