"""Template: a measured room blockout and still renders from planned camera angles.

    circle blender-run tools/blender/space_template.py -- <out_dir> [preview] [textures_dir]

Copy this file per job. Replace the EXAMPLE function room with the real space: a
floor plan or a few tape measurements, plus photos and phone videos for what goes where.
The stills it renders are layouts for Nano Banana (`circle img-gen --ref`), which
paints the real look over them, or simply a quick 3D view of a space for a client.

Axes: x runs east, y runs north, z is up, all in metres. The room sits from (0, 0) to
(W, D), so a camera at (1, 1, 1.6) is in the south-west corner at eye height.

Rules that came from real jobs:
- Flat, distinct colours per thing. The image model reads colour as "a different object".
- Anything you want in the picture must be in the blockout. Missing structure stays missing.
- Map real signage and artwork on as decals (`circle img-crop`); plain stand-ins come back
  as invented artwork.
- Lens 24 matches a phone photo. Wider than 18 bends the edges, and the model copies it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from previz_lib import (box, cylinder, decal, lights, mat, parse_args, render_stills,  # noqa: E402
                        reset, room, shot)

OUT, PREVIEW, TEX, _ = parse_args(default_seconds=0)
NAME = "space"

sc = reset()

FLOOR = mat("floor", (0.55, 0.42, 0.30), rough=0.5)
WALL = mat("wall", (0.90, 0.89, 0.86))
STAGE = mat("stage", (0.12, 0.12, 0.14))
BAR = mat("bar", (0.45, 0.25, 0.15))
TABLE = mat("table", (0.95, 0.95, 0.92))
BRAND = mat("brand", (0.80, 0.10, 0.10))  # a stand-in for a branded build: swap for a decal when you have the art

# ---- EXAMPLE: a 14 m x 10 m function room, 3.6 m high ---------------------------------------
W, D, H = 14.0, 10.0, 3.6
# No ceiling: it lets the light in and the overhead shot see down. Nano Banana adds one if asked.
room("room", W, D, H, FLOOR, WALL, openings={
    "south": [(1.0, 1.8, 0, 2.2)],                       # double doors near the south-west corner
    "east": [(2.0, 2.0, 0.9, 2.6), (6.0, 2.0, 0.9, 2.6)],  # two windows
})

box("stage", (W / 2, D - 1.5, 0.3), (6.0, 3.0, 0.6), STAGE)
decal("screen", TEX, "screen", (W / 2, D - 0.2, 2.2), 4.0, 2.25, rot_z=180, emit=1.0)
box("bar", (W - 1.0, D / 2 - 2.5, 0.55), (1.0, 4.0, 1.1), BAR)
box("brand_wall", (2.5, 0.4, 1.25), (3.0, 0.4, 2.5), BRAND)
for i, (x, y) in enumerate([(4, 3.5), (7, 3.5), (10, 3.5), (5.5, 6), (8.5, 6)]):
    cylinder(f"table{i}_top", (x, y, 0.72), 0.8, 0.04, TABLE)  # a top and a leg reads as a table;
    cylinder(f"table{i}_leg", (x, y, 0), 0.08, 0.72, TABLE)    # one solid cylinder reads as a drum

lights(sc)

# ---- Shots: name, camera position, the point it looks at, lens --------------------------------
SHOTS = [
    shot("entrance", (1.9, 0.6, 1.6), (W / 2, D - 1.5, 1.2), lens=24),     # walking in through the doors
    shot("from_stage", (W / 2, D - 2.5, 2.2), (W / 2, 1.0, 1.0), lens=24),  # the speaker's view
    shot("bar_corner", (W - 1.5, 1.0, 1.6), (4.0, D - 2.0, 1.0), lens=24),
    shot("overhead", (W / 2, D / 2 - 0.01, 11.0), (W / 2, D / 2, 0), lens=20),  # a floor plan view
]

render_stills(sc, OUT, NAME, SHOTS, PREVIEW)
