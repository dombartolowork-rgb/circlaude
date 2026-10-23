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
