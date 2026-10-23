"""Template: a grey blockout of a room and a keyed camera walkthrough.

    circle blender-run tools/blender/walkthrough_template.py -- <out_dir> [preview] [textures_dir]

Copy this file per job. Replace the EXAMPLE room with the as-built layout: get it
from someone who was there, because plans and what was actually built differ.

Rules that came from real jobs:
- Yaw 180 looks down the room (-Y), -90 looks east (+X), 90 looks west (-X).
  Keep the yaw values continuous (no jumps from 180 to -180) or the camera spins.
- A path that turns sharply mid-shot makes the AI hard-cut. Keep turns gentle;
  when the shot needs a new angle, end the take and cut in the edit.
- Keep props (TVs, easels) clear of the signage they stand in front of.
- Wall decals: east wall rot_z -90, west wall 90, a screen facing the room 180.
"""
import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from previz_lib import box, decal, mat, parse_args, render, reset, sky  # noqa: E402

OUT, PREVIEW, TEX, SECONDS = parse_args(default_seconds=16)
FPS = 24
NAME = "walkthrough"

sc = reset()

FLOOR = mat("floor", (0.62, 0.45, 0.28), rough=0.5)
WALL = mat("wall", (0.92, 0.90, 0.86))
BLACK = mat("black", (0.04, 0.04, 0.04))
SEAT = mat("seat", (0.85, 0.82, 0.74))
CHAIR = mat("chair", (0.10, 0.08, 0.07))
SOFA = mat("sofa", (0.55, 0.62, 0.52))
DOOR = mat("doorway", (0.55, 0.70, 0.55), emit=0.8)       # bright daylight through the door
WINDOW = mat("window", (0.80, 0.88, 0.95), emit=0.8)

# ---- EXAMPLE room: 8 m wide, 20 m long, door at y=0, stage at y=-20 ------------------------
W, L, H = 8.0, 20.0, 3.2
box("floor", (0, -L / 2, -0.05), (W, L, 0.1), FLOOR)
box("wall_w", (-W / 2 - 0.05, -L / 2, H / 2), (0.1, L, H), WALL)
box("wall_e", (W / 2 + 0.05, -L / 2, H / 2), (0.1, L, H), WALL)
box("wall_n", (0, 0.05, H / 2), (W, 0.1, H), WALL)
box("wall_s", (0, -L - 0.05, H / 2), (W, 0.1, H), WALL)
box("ceiling", (0, -L / 2, H + 0.05), (W, L, 0.1), WALL)
box("door", (0, 0.0, 1.15), (1.4, 0.12, 2.3), DOOR)
for y in (-3, -8, -13):
    for x in (-W / 2 + 0.01, W / 2 - 0.01):
        box(f"window_{x}_{y}", (x, y, 1.6), (0.04, 1.4, 1.8), WINDOW)

# exhibitor booths along the east wall, graphic facing the room
for i, y in enumerate((-1.6, -4.2, -6.8)):
    decal(f"booth_{i}", TEX, f"booth_{i}", (W / 2 - 0.05, y, 1.25), 2.2, 2.5, rot_z=-90)
    box(f"booth_{i}_frame", (W / 2 - 0.02, y, 1.25), (0.04, 2.3, 2.6), BLACK)

# audience: 6 rows of 10 chairs with a centre aisle
for r in range(6):
    y = -9.0 - r * 1.0
    for c in range(10):
        x = -3.4 + c * 0.68 + (0.5 if c >= 5 else 0) - 0.25
        box(f"seat_{r}_{c}", (x, y, 0.45), (0.45, 0.45, 0.06), SEAT)
        box(f"back_{r}_{c}", (x, y + 0.22, 0.75), (0.45, 0.05, 0.6), CHAIR)

# stage: riser, glowing screen facing the audience, sofas
box("riser", (0, -18.6, 0.2), (7.0, 2.6, 0.4), BLACK)
decal("screen", TEX, "screen", (0, -19.9, 2.0), 3.6, 2.0, rot_z=180, emit=1.2)
box("screen_frame", (0, -19.95, 2.0), (3.9, 0.05, 2.3), BLACK)
for i, x in enumerate([-2.6, -1.4, 1.4, 2.6]):
    box(f"sofa_{i}", (x, -18.6, 0.65), (1.0, 0.8, 0.5), SOFA)

# lighting: soft ceiling panels
for y in (-3, -9, -15):
    bpy.ops.object.light_add(type="AREA", location=(0, y, H - 0.1))
    bpy.context.object.data.energy, bpy.context.object.data.size = 150, 4
sky(sc, (0.85, 0.9, 1.0), 0.3)

# ---- camera path: (frame, position, tilt, yaw). Tilt 90 is level; yaw as in the docstring --
bpy.ops.object.camera_add()
cam = bpy.context.object
cam.data.lens = 20
sc.camera = cam
end = SECONDS * FPS
KEYS = [(1, (-1.6, -0.7, 1.65), 86, -125),        # in the doorway, looking at the booths
        (100, (-1.0, -6.0, 1.65), 86, -115),      # glide past them
        (190, (0, -7.5, 1.6), 87, -180),          # turn gently down the aisle
        (end, (0, -15.6, 1.35), 88, -180)]        # arrive in front of the stage
for f, loc, tilt, yaw in KEYS:
    cam.location = loc
    cam.rotation_euler = (math.radians(tilt), 0, math.radians(yaw))
    cam.keyframe_insert("location", frame=f)
    cam.keyframe_insert("rotation_euler", frame=f)

render(sc, OUT, NAME, PREVIEW, (1, 100, 190, end), FPS, SECONDS)
