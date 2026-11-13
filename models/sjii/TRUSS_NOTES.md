# SJII trusses: reading so far (not modelled yet)

Sheets: S-8101 (CTB1, CTB2, CTB3) and S-8201 (ES1, ES1a, HS1), elevations at 1:50 = 17.64 mm/pt, members drawn as outlines.

## Where they are (plans name them "Truss <name>" beside an unmarked line)
- CTB 4th storey S-2104: CTB1 x 9 (along A-letter grids AE-AJ, 36 m, every 4.5 m), CTB2 x 2 (A1-A3, 18 m), CTB3 x 5 (9 m bays).
- ES 4th storey S-2224: ES1 x 4, ES1a x 2 (BN-BR, 27 m; ES1a is three 9 m pieces between columns).
- HS 4th storey S-2324: HS1 x 4, skewed 45 degrees.
- HS 6th storey S-2326: HS2 x 3 and HS5 x 2 - NO elevation on the set. The HS1 elevation is tagged "Level EDU-6TH STOREY +34.500"
  and shows cross beams that match the 6th storey plan, so HS1 (elevation) may be what the plan calls HS2. Decision for Yang.
- So 26 truss positions from six elevations, not six trusses. Rough weight: CTB1 alone about 60 t each.

## Elevation numbers (PDF points; scan with the scratch script idea: pair parallel outline lines 5-32 pt apart)
- CTB3: chords C35FF web in plane, centres y 941.9 / 1066.6 (2,200 c/c), x 1748-2213; verticals C35M at x 1853.0, 1980.6, 2108.2;
  4 diagonals C35M at 44.5 degrees, concentric at the nodes.
- CTB1: chords lie flat (web horizontal, drawn width = flange width): top C35FF y 340.9-365.4, bottom C35CC y 470.8-494.9, x 342-2368;
  9 verticals C30G, 16 diagonals C35F (V between verticals, apex on the top chord), end diagonals C35M to the 800 dia columns.
- CTB2: chords y 927.7-951.6 and 1044.0-1067.9, x 338-1312, NO chord mark on the sheet (drawn 421 wide = BU09 / C35CC, assume BU09);
  7 verticals C35K, 8 diagonals BU09 at 40 degrees.
- ES1: bottom chord C35Z y 301.4-326.2; top chord C35Z in three pieces (x 352-844, 856-1440, 1443-1859) - top edge still to settle;
  18 verticals and 18 diagonals, S30H at the ends and S20G in the middle.
- ES1a: chords C35W, three pieces each, centres y 677.5 / 762.6; 15 verticals and 18 diagonals S20G.
- HS1: top chord drawn 419 deep (y 1090.0-1113.7) but labelled B61T | C35W | B61T; bottom chord y 1174.9-1198.7 (C35W size, no label);
  10 verticals C35F; 12 diagonals (C35W x 3 at each end, C35F x 6). Follow the labels or the drawn size: Decision for Yang.

## Plan for the model
- Top chords go into the floor's beam list before ga_plan.connect so floor beams frame into them (flat chords: bear, not cope).
- Bottom chords, verticals, diagonals from the elevation, centred on the plan line; top chord TOS = floor TOS.
- Tags TC / BC / W per distinct mark; one lift unit per truss ("Truss CTB1 @ grid"); own MTO category.
