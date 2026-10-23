"""Template: import a 3D scan of a real space and render stills from planned angles.

    circle blender-run tools/blender/scan_template.py -- <out_dir> [preview] <scan_file>

The scan comes from a phone scanning app or photogrammetry software, exported as
.glb, .obj, .fbx, .ply or .usdz (see the blender-spaces skill for which to use).
Copy this file per job.

First run: leave SHOTS empty. It renders four corner views and an overhead, and prints
the model's size. Check one real measurement (a door is about 2.0-2.1 m high, a
standard table 0.75 m), set SCALE if it is off, then set SHOTS for the angles you want.

Axes after import: the model is centred on x/y = 0 with the floor at z = 0. x runs
left to right on the overhead still, y runs bottom to top, all in metres.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from previz_lib import (bounds, clay, import_scan, lights, mat, move_to_floor, parse_args,  # noqa: E402
                        render_stills, reset, shot)

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT, PREVIEW, _, _ = parse_args(default_seconds=0)
SCAN = next((a for a in args[1:] if a != "preview"), None)
if not SCAN or not os.path.isfile(SCAN):
    raise SystemExit("Pass the scan file: blender-run scan_template.py -- <out_dir> [preview] <scan_file>")
NAME = os.path.splitext(os.path.basename(SCAN))[0]

SCALE = 1.0       # e.g. 0.5 if a 2 m door measures 4 m. Some apps export in centimetres: try 0.01
CLAY = False      # True renders plain grey: use it when the scan's textures are blurry or patchy,
                  # because Nano Banana copies blur as if it were part of the look
LINES = True      # thin outlines help the image model read the geometry

# Shots once you know the space: name, camera position, the point it looks at, lens.
# Eye height is about 1.6 m; lens 24 matches a phone photo.
SHOTS_PLANNED = [
    # ("entrance", (-4.0, -3.0, 1.6), (0, 0, 1.0), 24),
]

sc = reset()
meshes = import_scan(SCAN)
if SCALE != 1.0:
    move_to_floor(meshes, SCALE)
if CLAY:
    clay(meshes, mat("clay", (0.75, 0.75, 0.75)))
lights(sc)

lo, hi = bounds(meshes)
if SHOTS_PLANNED:
    shots = [shot(n, p, t, lens) for n, p, t, lens in SHOTS_PLANNED]
else:
    # Survey: from each corner, just inside the model, at eye height, looking at the middle.
    inset = 0.15
    xs = (lo.x + (hi.x - lo.x) * inset, hi.x - (hi.x - lo.x) * inset)
    ys = (lo.y + (hi.y - lo.y) * inset, hi.y - (hi.y - lo.y) * inset)
    eye = min(1.6, hi.z * 0.6)
    shots = [shot(f"corner_{a}", (x, y, eye), (0, 0, eye * 0.6), 20)
             for a, (x, y) in zip(("sw", "se", "nw", "ne"), [(xs[0], ys[0]), (xs[1], ys[0]),
                                                              (xs[0], ys[1]), (xs[1], ys[1])])]
    span = max(hi.x - lo.x, hi.y - lo.y)
    shots.append(shot("overhead", (0, -0.01, hi.z + span * 1.1), (0, 0, 0), 24))

render_stills(sc, OUT, NAME, shots, PREVIEW, lines=LINES)
