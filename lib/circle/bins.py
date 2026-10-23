"""Where Orbit finds the outside programs it drives: ffmpeg, yt-dlp, Deno, Blender.

Orbit's own code is stdlib Python. Video and 3D work shell out to these, found in
this order: Orbit's private folder (~/.circle/bin, filled by `circle yt-setup`),
then PATH, then the usual install locations.
"""
import glob
import os
import platform
import shutil

BIN = os.path.join(os.path.expanduser("~"), ".circle", "bin")
WINDOWS = os.name == "nt"


class ToolMissing(RuntimeError):
    pass


def exe(name):
    """Name of a binary on this platform, inside Orbit's folder."""
    return os.path.join(BIN, name + (".exe" if WINDOWS else ""))


def arch():
    m = platform.machine().lower()
    return "aarch64" if m in ("arm64", "aarch64") else "x86_64"


def find(name, extra=()):
    """First working copy of a program, or None."""
    candidates = [exe(name)]
    on_path = shutil.which(name)
    if on_path:
        candidates.append(on_path)
    candidates.extend(extra)
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def ffmpeg():
    p = find("ffmpeg")
    if not p:
        hint = ("Run: circle yt-setup --ffmpeg" if WINDOWS
                else "Install ffmpeg (for example `brew install ffmpeg`), or ask IT to push it.")
        raise ToolMissing("ffmpeg is not installed. " + hint)
    return p


def ffprobe():
    p = find("ffprobe")
    if not p:
        raise ToolMissing("ffprobe is not installed (it comes with ffmpeg). "
                          + ("Run: circle yt-setup --ffmpeg" if WINDOWS else "Install ffmpeg."))
    return p


def blender():
    """Newest Blender found, or None."""
    extra = []
    if WINDOWS:
        for root in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            extra += sorted(glob.glob(os.path.join(root, "Blender Foundation", "Blender*", "blender.exe")),
                            reverse=True)
        extra += sorted(glob.glob(os.path.join(os.path.expanduser("~"), "AppData", "Local", "Programs",
                                               "Blender Foundation", "Blender*", "blender.exe")), reverse=True)
    else:
        extra += ["/Applications/Blender.app/Contents/MacOS/Blender",
                  os.path.expanduser("~/Applications/Blender.app/Contents/MacOS/Blender")]
    return find("blender", extra)
