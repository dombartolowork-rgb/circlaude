"""Shared helpers for blockout previz scripts. Runs inside Blender (bpy), not plain Python.

The templates beside this file import it. Lessons baked in from real jobs:
flat distinct colours per zone, the Standard view transform (AgX washes blockouts
out), real gable roofs built from vertices, and signage mapped on as image panels
so the AI has nothing to invent.
"""
import math
import os
import sys

import bpy


def parse_args(default_seconds):
    """Script arguments after `--`: <out_dir> [preview] [textures_dir]."""
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = args[0] if args else os.path.join(os.path.expanduser("~"), "Documents", "previz")
    preview = len(args) > 1 and args[1] == "preview"
    tex = args[2] if len(args) > 2 else os.path.join(out, "textures")
    return out, preview, tex, default_seconds


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene


def mat(name, rgb, emit=0.0, rough=0.7):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = (*rgb, 1)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    if emit:
        b.inputs["Emission Color"].default_value = (*rgb, 1)
        b.inputs["Emission Strength"].default_value = emit
    return m


def box(name, loc, size, m, rot=0):
    """Box of size (x, y, z) metres centred on loc, rotated rot degrees about Z."""
    bpy.ops.mesh.primitive_cube_add(location=loc, rotation=(0, 0, math.radians(rot)))
    o = bpy.context.object
    o.name, o.scale = name, (size[0] / 2, size[1] / 2, size[2] / 2)
    o.data.materials.append(m)
    return o


def building(name, x0, x1, y0, y1, h, m, roof_mat, ridge=None):
    """Walls as a box, plus a real gable roof along the long side. Primitive cones as roofs go wrong."""
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    box(name, (cx, cy, h / 2), (x1 - x0, y1 - y0, h), m)
    if not ridge:
        return
    o = 0.4  # eave overhang
    a0, a1, b0, b1 = x0 - o, x1 + o, y0 - o, y1 + o
    if (x1 - x0) >= (y1 - y0):
        mid = (b0 + b1) / 2
        v = [(a0, b0, h), (a1, b0, h), (a1, b1, h), (a0, b1, h), (a0, mid, h + ridge), (a1, mid, h + ridge)]
        f = [(0, 1, 5, 4), (3, 4, 5, 2), (0, 4, 3), (1, 2, 5), (0, 3, 2, 1)]
    else:
        mid = (a0 + a1) / 2
        v = [(a0, b0, h), (a1, b0, h), (a1, b1, h), (a0, b1, h), (mid, b0, h + ridge), (mid, b1, h + ridge)]
        f = [(0, 4, 5, 3), (1, 2, 5, 4), (0, 1, 4), (3, 5, 2), (0, 3, 2, 1)]
    me = bpy.data.meshes.new(name + "_roof")
    me.from_pydata(v, [], f)
    ob = bpy.data.objects.new(name + "_roof", me)
    ob.data.materials.append(roof_mat)
    bpy.context.scene.collection.objects.link(ob)


def decal(name, tex_dir, img, loc, w, h, rot_z=0, emit=0.0):
    """Image panel w x h metres centred on loc. It faces -Y at rot_z 0; east walls need -90,
    west walls 90, and a screen facing back down the room 180 (otherwise it is mirrored).
    If the image is missing, a grey stand-in panel is placed so the layout still renders."""
    bpy.ops.mesh.primitive_plane_add(size=1, location=loc, rotation=(math.radians(90), 0, math.radians(rot_z)))
    o = bpy.context.object
    o.name, o.scale = name, (w, h, 1)
    path = next((os.path.join(tex_dir, img + ext) for ext in (".jpg", ".jpeg", ".png")
                 if os.path.isfile(os.path.join(tex_dir, img + ext))), None)
    if not path:
        print(f"WARNING: no texture '{img}' in {tex_dir}, using a grey stand-in")
        o.data.materials.append(mat("missing_texture", (0.5, 0.5, 0.5)))
        return o
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(path)
    b = nt.nodes["Principled BSDF"]
    nt.links.new(tex.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.6
    if emit:  # screens glow
        nt.links.new(tex.outputs["Color"], b.inputs["Emission Color"])
        b.inputs["Emission Strength"].default_value = emit
    o.data.materials.append(m)
    return o


def linear_keys(obj):
    """Make an object's keys linear (constant speed), on Blender 4 and Blender 5 layered actions."""
    act = obj.animation_data.action if obj.animation_data else None
    if not act:
        return
    curves = list(getattr(act, "fcurves", []) or [])
    try:
        for layer in act.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    curves.extend(bag.fcurves)
    except AttributeError:
        pass
    for fc in curves:
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"


def sky(sc, rgb=(0.75, 0.80, 0.88), strength=1.0):
    w = bpy.data.worlds.new("sky")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (*rgb, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = strength


def render(sc, out, name, preview, preview_frames, fps, seconds):
    """Save the .blend, then render four preview stills or the full H.264 guide video."""
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in engines else "BLENDER_EEVEE_NEXT"
    sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
    sc.render.resolution_percentage = 50 if preview else 100
    sc.render.fps = fps
    sc.frame_start, sc.frame_end = 1, seconds * fps
    sc.view_settings.view_transform = "Standard"
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, name + ".blend"))
    if preview:
        for f in preview_frames:
            sc.frame_set(f)
            sc.render.filepath = os.path.join(out, f"{name}_preview_{f:03d}.png")
            bpy.ops.render.render(write_still=True)
    else:
        if hasattr(sc.render.image_settings, "media_type"):
            sc.render.image_settings.media_type = "VIDEO"
        sc.render.image_settings.file_format = "FFMPEG"
        sc.render.ffmpeg.format, sc.render.ffmpeg.codec = "MPEG4", "H264"
        sc.render.ffmpeg.constant_rate_factor = "HIGH"
        sc.render.filepath = os.path.join(out, name + "_blockout.mp4")
        bpy.ops.render.render(animation=True)
    print("DONE", out)


# ---- Spaces and stills: model a room or a scan, then render stills from planned angles ----------

def wall(name, x0, y0, x1, y1, h, m, openings=(), t=0.15):
    """A straight wall from (x0, y0) to (x1, y1), h high and t thick. openings are
    (along, width, sill, top) in metres measured from the (x0, y0) end: a door is
    (2.0, 1.0, 0, 2.1), a window (4.0, 1.5, 0.9, 2.1). The gaps are real holes, so the
    camera sees through them; put a decal of the view behind a window if it matters."""
    length = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    rot = math.degrees(math.atan2(uy, ux))

    def piece(a, b, z0, z1, tag):
        if b - a < 0.01 or z1 - z0 < 0.01:
            return
        mid = (a + b) / 2
        box(f"{name}_{tag}", (x0 + ux * mid, y0 + uy * mid, (z0 + z1) / 2), (b - a, t, z1 - z0), m, rot)

    cursor = 0.0
    for i, (along, width, sill, top) in enumerate(sorted(openings)):
        piece(cursor, along, 0, h, f"run{i}")
        piece(along, along + width, 0, sill, f"sill{i}")
        piece(along, along + width, top, h, f"head{i}")
        cursor = along + width
    piece(cursor, length, 0, h, "end")


def room(name, width, depth, height, floor_m, wall_m, openings=None, ceiling_m=None):
    """A rectangular room from (0, 0) to (width, depth), floor at z=0. openings maps a wall
    ("south" y=0, "north" y=depth, "west" x=0, "east" x=width) to wall() openings. Each wall is
    measured anticlockwise from its starting corner: south from the south-west corner, east from
    the south-east, north from the north-east, west from the north-west.
    Leave the ceiling off for overhead shots; add it for anything at eye level."""
    openings = openings or {}
    box(name + "_floor", (width / 2, depth / 2, -0.05), (width, depth, 0.1), floor_m)
    wall(name + "_south", 0, 0, width, 0, height, wall_m, openings.get("south", ()))
    wall(name + "_east", width, 0, width, depth, height, wall_m, openings.get("east", ()))
    wall(name + "_north", width, depth, 0, depth, height, wall_m, openings.get("north", ()))
    wall(name + "_west", 0, depth, 0, 0, height, wall_m, openings.get("west", ()))
    if ceiling_m:
        box(name + "_ceiling", (width / 2, depth / 2, height + 0.05), (width, depth, 0.1), ceiling_m)


def cylinder(name, loc, radius, height, m):
    """Round tables, pillars, plinths. loc is the centre of the base."""
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=height, vertices=48,
                                        location=(loc[0], loc[1], loc[2] + height / 2))
    o = bpy.context.object
    o.name = name
    o.data.materials.append(m)
    try:
        bpy.ops.object.shade_auto_smooth()  # smooth sides, crisp rims
    except (AttributeError, RuntimeError):
        pass
    return o


def shot(name, pos, target, lens=24):
    """A still camera at pos looking at target. A phone's main camera is about 24-26mm
    (full-frame equivalent), so 24 matches phone photos; eye height is about 1.6m.
    Wider than 18mm stretches the edges and Nano Banana copies the distortion."""
    from mathutils import Vector
    cam = bpy.data.cameras.new(name)
    cam.lens, cam.sensor_width = lens, 36
    o = bpy.data.objects.new(name, cam)
    bpy.context.scene.collection.objects.link(o)
    o.location = pos
    o.rotation_euler = (Vector(target) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
    return o


def lights(sc, sun_strength=3.0, world_strength=0.8):
    """Even, soft light that reads cleanly as a layout. Drama comes later, in the Nano Banana prompt."""
    sky(sc, (0.85, 0.87, 0.9), world_strength)
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = sun_strength
    sun.data.angle = math.radians(15)  # soft-edged shadows
    sun.rotation_euler = (math.radians(25), 0, math.radians(30))  # high sun, short shadows
    sc.collection.objects.link(sun)


def import_scan(path):
    """Bring in a scan or photogrammetry model (.glb, .gltf, .obj, .fbx, .ply, .usd/.usdz/.usdc),
    sit it on the floor at the origin, and report its size so the scale can be checked against
    one real measurement. Returns the imported mesh objects."""
    ext = os.path.splitext(path)[1].lower()
    before = set(bpy.data.objects)
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".ply":
        bpy.ops.wm.ply_import(filepath=path)
    elif ext in (".usd", ".usdz", ".usdc", ".usda"):
        bpy.ops.wm.usd_import(filepath=path)
    else:
        raise SystemExit(f"Cannot import {ext}: export the scan as .glb, .obj, .fbx, .ply or .usdz")
    meshes = [o for o in set(bpy.data.objects) - before if o.type == "MESH"]
    if not meshes:
        raise SystemExit(f"No mesh found in {path}")
    move_to_floor(meshes)
    return meshes


def bounds(objs):
    from mathutils import Vector
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def move_to_floor(objs, scale=1.0):
    """Centre the objects on x/y = 0 with their lowest point on z = 0, after scaling."""
    roots = {o for o in objs if o.parent is None or o.parent not in objs}
    for r in roots:
        r.scale = [s * scale for s in r.scale]
    bpy.context.view_layer.update()
    lo, hi = bounds(objs)
    for r in roots:
        r.location.x -= (lo.x + hi.x) / 2
        r.location.y -= (lo.y + hi.y) / 2
        r.location.z -= lo.z
    bpy.context.view_layer.update()
    lo, hi = bounds(objs)
    print(f"SIZE  {hi.x - lo.x:.2f} m wide (x), {hi.y - lo.y:.2f} m deep (y), {hi.z - lo.z:.2f} m high (z)")
    return lo, hi


def clay(objs, m):
    """Replace every material with one plain material, to see the geometry without the scan's
    textures, or to stop Nano Banana copying a blurry scan texture."""
    for o in objs:
        o.data.materials.clear()
        o.data.materials.append(m)


def render_stills(sc, out, name, shots, preview, lines=True, size=(1920, 1080)):
    """Save the .blend, then render one PNG per shot camera. Preview renders at half size.
    lines adds thin outlines (Freestyle), which help an image model read edges and depth."""
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in engines else "BLENDER_EEVEE_NEXT"
    sc.render.resolution_x, sc.render.resolution_y = size
    sc.render.resolution_percentage = 50 if preview else 100
    sc.view_settings.view_transform = "Standard"
    sc.render.use_freestyle = lines
    if lines:
        sc.render.line_thickness_mode = "ABSOLUTE"
        sc.render.line_thickness = 1.0 if preview else 1.5
        fs = bpy.context.view_layer.freestyle_settings
        ls = fs.linesets[0] if fs.linesets else fs.linesets.new("outlines")
        if ls.linestyle is None:  # an empty factory scene has a line set with no style, so nothing draws
            ls.linestyle = bpy.data.linestyles.new("outlines")
        ls.linestyle.color = (0.1, 0.1, 0.1)
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, name + ".blend"))
    for cam in shots:
        sc.camera = cam
        sc.render.filepath = os.path.join(out, f"{name}_{cam.name}{'_preview' if preview else ''}.png")
        bpy.ops.render.render(write_still=True)
        print("still", sc.render.filepath)
    print("DONE", out)
