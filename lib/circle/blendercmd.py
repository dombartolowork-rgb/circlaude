"""Run Blender scripts headless, and crop signage photos for decals.

    circle blender-find                                  where Blender is, and its version
    circle blender-run script.py -- <out_dir> [preview]  run a previz script without opening Blender
    circle img-crop photo.jpg --box 120,340,900,420 -o sign.jpg
                                                         cut a sign out of a front-on photo

The templates live in the plugin's tools/blender folder; copy one per job.
"""
import argparse
import os
import subprocess

from circle import bins


class BlenderError(RuntimeError):
    pass


def _blender():
    b = bins.blender()
    if not b:
        raise BlenderError("Blender is not installed. Get it from blender.org (free); Orbit finds it in "
                           "Program Files on Windows or /Applications on a Mac.")
    return b


def cmd_find(args):
    b = _blender()
    out = subprocess.run([b, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(b)
    print((out.stdout.strip().splitlines() or ["(version unknown)"])[0])


def cmd_run(args):
    script = os.path.abspath(args.script)
    if not os.path.isfile(script):
        raise BlenderError(f"No such script: {script}")
    rest = list(args.rest)
    if rest and rest[0] == "--":
        rest = rest[1:]
    cmd = [_blender(), "--background", "--python", script, "--"] + rest
    print("running:", " ".join(f'"{c}"' if " " in c else c for c in cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise BlenderError(f"Blender exited {r.returncode}. Read the Python traceback above.")


def cmd_crop(args):
    try:
        x, y, w, h = (int(v) for v in args.box.split(","))
    except ValueError:
        raise BlenderError("--box takes x,y,width,height in pixels, e.g. 120,340,900,420")
    out = args.out or os.path.splitext(args.file)[0] + "_crop.jpg"
    r = subprocess.run([bins.ffmpeg(), "-y", "-v", "error", "-i", args.file, "-vf", f"crop={w}:{h}:{x}:{y}",
                        "-frames:v", "1", "-q:v", "2", out], capture_output=True, text=True)
    if r.returncode != 0:
        raise BlenderError("Crop failed:\n" + r.stderr[-1500:])
    print(f"saved {out}  ({w}x{h})")


def register(sub):
    sub.add_parser("blender-find", help="where Blender is installed, and its version").set_defaults(func=cmd_find)

    p = sub.add_parser("blender-run", help="run a Blender Python script headless")
    p.add_argument("script")
    p.add_argument("rest", nargs=argparse.REMAINDER, help="-- then the script's own arguments")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("img-crop", help="crop part of an image, e.g. a sign for a blockout decal")
    p.add_argument("file")
    p.add_argument("--box", required=True, help="x,y,width,height in pixels")
    p.add_argument("-o", "--out")
    p.set_defaults(func=cmd_crop)
