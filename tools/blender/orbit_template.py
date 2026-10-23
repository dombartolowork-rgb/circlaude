"""Template: a grey blockout of an outdoor venue and one continuous 360 drone orbit.

    circle blender-run tools/blender/orbit_template.py -- <out_dir> [preview] [textures_dir]

Copy this file per job and replace the EXAMPLE layout with the real one, measured
off the FINAL floor plan. The AI (Seedance) paints the real place over the guide
video; the camera move is ours. Keep each zone a flat, distinct colour.

Rules that came from real jobs:
- Every feature you want in the shot must exist in the blockout. The AI does not
  invent structure the guide video lacks (a missing entrance stays missing).
- Keep foreground objects (parasols, poles) OUTSIDE the camera's orbit. Anything
  that crosses close to the lens comes back as flat grey panels.
- Map real signage on with decal(), cropped front-on from photos
  (`circle img-crop`). Plain stand-ins come back as invented artwork.
"""
import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from previz_lib import box, building, decal, linear_keys, mat, parse_args, render, reset, sky  # noqa: E402

OUT, PREVIEW, TEX, SECONDS = parse_args(default_seconds=10)
FPS = 24
NAME = "orbit"

sc = reset()

GROUND = mat("ground", (0.78, 0.72, 0.62))
GRASS = mat("grass", (0.35, 0.45, 0.25))
BRICK = mat("brick", (0.55, 0.30, 0.22))
ROOF = mat("roof", (0.40, 0.22, 0.16))
TIMBER = mat("timber", (0.72, 0.55, 0.36))
GLASS = mat("glass", (0.15, 0.25, 0.30))
WOOD = mat("wood", (0.45, 0.33, 0.22))
DARK = mat("dark", (0.12, 0.12, 0.12))
TREE = mat("tree", (0.22, 0.38, 0.18))
UMB = {k: mat("umb_" + k, v) for k, v in {
    "blue": (0.25, 0.30, 0.85), "pink": (0.90, 0.35, 0.70), "yellow": (0.98, 0.70, 0.15),
    "white": (0.88, 0.86, 0.80)}.items()}

# ---- EXAMPLE layout: a 26 x 28 m courtyard. Replace with the real plan. ------------------
bpy.ops.mesh.primitive_plane_add(size=120)
bpy.context.object.data.materials.append(GRASS)
box("courtyard", (0, 0, 0.01), (26, 28, 0.02), GROUND)

building("west_range", -19, -13, -14, 14, 5, BRICK, ROOF, ridge=3.5)
building("north_range", -13, 13, 14, 20, 4.5, BRICK, ROOF, ridge=3.5)
building("east_hall", 13, 21, -18, 14, 4.2, TIMBER, ROOF, ridge=2.2)
box("east_glazing", (12.95, -3, 1.6), (0.1, 8, 2.6), GLASS)
building("south_range", -13, 13, -20, -14, 4.5, BRICK, ROOF, ridge=3.5)
# an entrance arch with daylight beyond, so the AI keeps the opening
box("entrance_mouth", (-2, -14.02, 1.4), (2.8, 0.3, 2.8), mat("tunnel", (0.03, 0.03, 0.03)))
box("entrance_light", (-2, -19.9, 1.4), (2.6, 0.2, 2.6), mat("daylight", (0.75, 0.85, 0.60)))

# background trees so the orbit has a skyline
for x, y, s in [(-8, 28, 9), (8, 30, 11), (26, 20, 8), (-26, 16, 8), (-24, -24, 7), (24, -26, 9)]:
    bpy.ops.mesh.primitive_ico_sphere_add(radius=s / 2, location=(x, y, s), subdivisions=2)
    bpy.context.object.data.materials.append(TREE)

# a vendor and its signage, as an example of a decal on a face
box("vendor_kiosk", (6, 12.6, 1.4), (3.4, 2.0, 2.8), mat("kiosk", (0.70, 0.88, 0.85)))
decal("vendor_sign", TEX, "vendor_sign", (6, 11.58, 2.4), 3.2, 0.8)

# the centrepiece the camera orbits
bpy.ops.mesh.primitive_cylinder_add(radius=2.6, depth=0.5, location=(0, 1, 0.25))
bpy.context.object.data.materials.append(WOOD)
box("centre_sign", (0, 1, 3.5), (1.4, 0.15, 1.8), DARK)

# parasols on a ring OUTSIDE the 9.5 m orbit, never between the camera and the centre
for i, (ang, col) in enumerate([(-30, "white"), (-80, "yellow"), (-140, "pink"), (150, "blue"), (40, "yellow")]):
    x, y = 11.5 * math.cos(math.radians(ang)), 1 + 11.5 * math.sin(math.radians(ang))
    box(f"pole_{i}", (x, y, 1.3), (0.08, 0.08, 2.6), DARK)
    bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=1.9, depth=0.7, location=(x, y, 2.75),
                                    rotation=(0, 0, math.radians(45)))
    bpy.context.object.data.materials.append(UMB[col])
    box(f"table_{i}", (x, y, 0.75), (1.8, 0.8, 0.08), WOOD)

# ---- camera: one continuous 360 orbit (a rotating parent empty, linear keys) -------------
CENTRE, RADIUS, HEIGHT, LENS = (0, 1), 9.5, 6.0, 18
target = bpy.data.objects.new("orbit_target", None)
target.location = (CENTRE[0], CENTRE[1], 2.0)
sc.collection.objects.link(target)
rig = bpy.data.objects.new("orbit_rig", None)
rig.location = (CENTRE[0], CENTRE[1], 0)
sc.collection.objects.link(rig)
bpy.ops.object.camera_add(location=(CENTRE[0], CENTRE[1] - RADIUS, HEIGHT))
cam = bpy.context.object
cam.parent = rig
cam.data.lens = LENS
c = cam.constraints.new("TRACK_TO")
c.target, c.track_axis, c.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"
sc.camera = cam
end = SECONDS * FPS
rig.rotation_euler = (0, 0, 0)
rig.keyframe_insert("rotation_euler", frame=1)
rig.rotation_euler = (0, 0, math.radians(360))
rig.keyframe_insert("rotation_euler", frame=end + 1)
linear_keys(rig)

bpy.ops.object.light_add(type="SUN", rotation=(math.radians(50), 0, math.radians(30)))
bpy.context.object.data.energy = 2
sky(sc)

render(sc, OUT, NAME, PREVIEW, (1, end // 4, end // 2, 3 * end // 4), FPS, SECONDS)
