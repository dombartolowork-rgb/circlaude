"""Quick, frame-exact video edits with ffmpeg, for the jobs that do not need Premiere.

    circle vid-probe clip.mp4                       duration, size, frame rate, audio
    circle vid-cut clip.mp4 --from 4.2 --to 9.8     trim, frame exact (re-encodes)
    circle vid-join out.mp4 --clip a.mp4 --clip b.mp4 2 7.5 [--dissolve 0.5]
    circle vid-sheet clip.mp4 [--count 9]           contact sheet of labelled frames, to check work
    circle vid-1080 clip.mp4                        fit inside 1920x1080 (after an AI upscale, say)
    circle vid-pushend in.mp4 out.mp4 --ramp 1.5 --scale 1.28
                                                    digital push-in over the end, to match the next shot

`--clip FILE [IN [OUT]]` takes seconds or m:ss. It is a separate option, not
FILE:IN:OUT, because Windows paths already contain a colon.

Every output is H.264 and AAC in an MP4, which plays in PowerPoint, Teams and on
any phone. Cuts are frame exact because everything is re-encoded; for a whole
file that only needs a container change, use the original instead.
"""
import json
import math
import os
import subprocess
import tempfile

from circle import bins
from circle.ytcmd import parse_time

ENC_V = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"]
ENC_A = ["-c:a", "aac", "-b:a", "192k"]
MP4 = ["-movflags", "+faststart"]


class VideoError(RuntimeError):
    pass


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise VideoError("ffmpeg failed:\n" + r.stderr[-2000:])
    return r.stdout


def probe(path):
    if not os.path.isfile(path):
        raise VideoError(f"No such file: {path}")
    out = _run([bins.ffprobe(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path])
    data = json.loads(out)
    v = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    a = next((s for s in data["streams"] if s.get("codec_type") == "audio"), None)
    fps = 0.0
    if v and v.get("avg_frame_rate", "0/0") != "0/0":
        n, d = v["avg_frame_rate"].split("/")
        fps = float(n) / float(d) if float(d) else 0.0
    return {
        "duration": float(data["format"].get("duration") or 0),
        "width": int(v["width"]) if v else 0,
        "height": int(v["height"]) if v else 0,
        "fps": fps,
        "vcodec": v.get("codec_name") if v else None,
        "acodec": a.get("codec_name") if a else None,
        "audio": a is not None,
        "size_mb": int(data["format"].get("size") or 0) / 1048576,
    }


def _default_out(path, suffix, ext=".mp4"):
    base, _ = os.path.splitext(path)
    return base + suffix + ext


def _even(n):
    return int(n) // 2 * 2


# ---------------------------------------------------------------- commands

def cmd_probe(args):
    for f in args.file:
        p = probe(f)
        audio = f"audio {p['acodec']}" if p["audio"] else "NO AUDIO"
        print(f"{os.path.basename(f)}: {p['duration']:.2f}s, {p['width']}x{p['height']}, "
              f"{p['fps']:.3f}fps, {p['vcodec']}, {audio}, {p['size_mb']:.1f}MB")


def cmd_cut(args):
    src = args.file
    info = probe(src)
    a = parse_time(args.start) if args.start else 0.0
    b = parse_time(args.end) if args.end else info["duration"]
    if b <= a:
        raise VideoError("--to must be after --from.")
    out = args.out or _default_out(src, f"_cut_{a:g}-{b:g}")
    cmd = [bins.ffmpeg(), "-y", "-v", "error", "-ss", f"{a:.3f}", "-i", src, "-t", f"{b - a:.3f}"]
    vf, af = [], []
    if args.speed and args.speed != 1:
        vf.append(f"setpts=PTS/{args.speed}")
        af.append(_atempo(args.speed))
    if vf:
        cmd += ["-vf", ",".join(vf)]
    if af and info["audio"]:
        cmd += ["-af", ",".join(af)]
    _run(cmd + ENC_V + (ENC_A if info["audio"] else ["-an"]) + MP4 + [out])
    print(f"saved {out}  ({probe(out)['duration']:.2f}s)")


def _atempo(speed):
    """atempo only takes 0.5 to 2.0, so chain it for bigger changes. Keeps pitch."""
    parts, s = [], float(speed)
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    parts.append(f"atempo={s:.4f}")
    return ",".join(parts)


def cmd_join(args):
    """Trim pieces and join them: hard cuts, or cross dissolves with --dissolve."""
    if not args.clip:
        raise VideoError("Give at least one --clip FILE [IN [OUT]].")
    pieces = []
    for spec in args.clip:
        if len(spec) > 3:
            raise VideoError(f"--clip takes FILE [IN [OUT]], got {spec}")
        f = spec[0]
        info = probe(f)
        a = parse_time(spec[1]) if len(spec) > 1 else 0.0
        b = parse_time(spec[2]) if len(spec) > 2 else info["duration"]
        a += args.trim_ends
        b -= args.trim_ends
        if b <= a:
            raise VideoError(f"{f}: nothing left after trimming ({a:.2f} to {b:.2f}).")
        pieces.append({"file": f, "in": a, "out": b, "dur": b - a, "audio": info["audio"], "info": info})

    first = pieces[0]["info"]
    if args.size:
        W, H = (int(x) for x in args.size.lower().split("x"))
    else:
        W, H = _even(first["width"]), _even(first["height"])
    fps = args.fps or (round(first["fps"], 3) if first["fps"] else 30)
    silent = args.silent
    d = args.dissolve or 0.0
    if d and any(p["dur"] <= d for p in pieces):
        raise VideoError("A dissolve cannot be longer than the shortest piece.")

    cmd = [bins.ffmpeg(), "-y", "-v", "error"]
    for p in pieces:
        cmd += ["-ss", f"{p['in']:.3f}", "-t", f"{p['dur']:.3f}", "-i", p["file"]]
    graph = []
    fit = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}" if args.fill else
           f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2")
    for i, p in enumerate(pieces):
        graph.append(f"[{i}:v]{fit},setsar=1,fps={fps},format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS[v{i}]")
        if not silent:
            if p["audio"]:
                graph.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS[a{i}]")
            else:
                graph.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{p['dur']:.3f}[a{i}]")

    n = len(pieces)
    if n == 1:
        vout, aout = "[v0]", "[a0]"
    elif not d:
        ins = "".join(f"[v{i}]" + ("" if silent else f"[a{i}]") for i in range(n))
        graph.append(f"{ins}concat=n={n}:v=1:a={0 if silent else 1}[vout]" + ("" if silent else "[aout]"))
        vout, aout = "[vout]", "[aout]"
    else:
        prev, offset = "[v0]", 0.0
        for i in range(1, n):
            offset += pieces[i - 1]["dur"] - d
            graph.append(f"{prev}[v{i}]xfade=transition=fade:duration={d}:offset={offset:.3f}[x{i}]")
            prev = f"[x{i}]"
        vout = prev
        if not silent:
            prev = "[a0]"
            for i in range(1, n):
                graph.append(f"{prev}[a{i}]acrossfade=d={d}[y{i}]")
                prev = f"[y{i}]"
        aout = prev

    cmd += ["-filter_complex", ";".join(graph), "-map", vout]
    cmd += ["-an"] if silent else ["-map", aout] + ENC_A
    _run(cmd + ENC_V + ["-r", str(fps)] + MP4 + [args.out])
    total = probe(args.out)["duration"]
    print(f"saved {args.out}  ({n} piece(s), {total:.2f}s, {W}x{H} at {fps}fps"
          + (", silent" if silent else "") + (f", {d}s dissolves" if d else "") + ")")


def _font():
    for f in (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\segoeui.ttf",
              "/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc",
              "/Library/Fonts/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.isfile(f):
            return f
    return None


def _esc(s):
    """Escape a value for an ffmpeg filter argument."""
    return s.replace("\\", "/").replace(":", "\\:").replace("'", "")


def cmd_sheet(args):
    """Contact sheet: frames at given times (or evenly spaced), each labelled, in a grid."""
    src = args.file
    info = probe(src)
    if args.times:
        times = [parse_time(t) for t in args.times]
    else:
        n = max(1, args.count)
        times = [info["duration"] * (i + 0.5) / n for i in range(n)]
    cols = max(1, min(args.cols, len(times)))
    rows = math.ceil(len(times) / cols)
    out = args.out or _default_out(src, "_sheet", ".jpg")
    font = _font()
    ff = bins.ffmpeg()
    with tempfile.TemporaryDirectory(prefix="vidsheet-") as tmp:
        for i, t in enumerate(times):
            vf = "scale=640:-2"
            if font:
                m, s = divmod(t, 60)
                label = _esc(f"{int(m)}:{s:05.2f}")
                vf += (f",drawtext=fontfile='{_esc(font)}':text='{label}':x=12:y=12:fontsize=28:"
                       "fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=6")
            _run([ff, "-y", "-v", "error", "-ss", f"{min(t, max(info['duration'] - 0.05, 0)):.3f}", "-i", src,
                  "-frames:v", "1", "-vf", vf, os.path.join(tmp, f"f_{i:03d}.png")])
        first = os.path.join(tmp, "f_000.png")
        for i in range(len(times), rows * cols):
            blank = os.path.join(tmp, f"f_{i:03d}.png")
            _run([ff, "-y", "-v", "error", "-i", first, "-vf", "drawbox=c=gray:t=fill", "-frames:v", "1", blank])
        _run([ff, "-y", "-v", "error", "-framerate", "1", "-i", os.path.join(tmp, "f_%03d.png"),
              "-vf", f"tile={cols}x{rows}:padding=6:margin=6:color=gray", "-frames:v", "1", "-q:v", "3", out])
    print(f"saved {out}  ({len(times)} frames" + ("" if font else ", no labels: no font found") + ")")


def cmd_1080(args):
    src = args.file
    info = probe(src)
    out = args.out or _default_out(src, "_1080")
    vf = "scale=1920:1080:force_original_aspect_ratio=decrease:flags=lanczos,setsar=1"
    if args.pad:
        vf += ",pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
    _run([bins.ffmpeg(), "-y", "-v", "error", "-i", src, "-vf", vf] + ENC_V
         + (["-c:a", "copy"] if info["audio"] else ["-an"]) + MP4 + [out])
    p = probe(out)
    print(f"saved {out}  ({p['width']}x{p['height']}, {p['duration']:.2f}s)")


def cmd_pushend(args):
    """Ease a push-in over the last seconds, so the end framing matches the next shot's opening."""
    src = args.file
    info = probe(src)
    W, H = _even(info["width"]), _even(info["height"])
    t0 = max(0.0, info["duration"] - args.ramp)
    k = args.scale
    p = f"clip((t-{t0:.3f})/{args.ramp},0,1)"
    z = f"(1+({k}-1)*({p})*({p})*(3-2*({p})))"
    vf = (f"scale=w='trunc(iw*{z}/2)*2':h='trunc(ih*{z}/2)*2':eval=frame:flags=bicubic,"
          f"crop={W}:{H}:x='(in_w-{W})/2+{args.dx}*{p}':y='(in_h-{H})/2+{args.dy}*{p}',setsar=1")
    _run([bins.ffmpeg(), "-y", "-v", "error", "-i", src, "-vf", vf] + ENC_V
         + (["-c:a", "copy"] if info["audio"] else ["-an"]) + MP4 + [args.out])
    print(f"saved {args.out}  (push to {k}x over the last {args.ramp}s)")


def register(sub):
    p = sub.add_parser("vid-probe", help="duration, size, frame rate and audio of video files")
    p.add_argument("file", nargs="+")
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("vid-cut", help="trim a video, frame exact")
    p.add_argument("file")
    p.add_argument("--from", dest="start", help="start, seconds or m:ss (default: the beginning)")
    p.add_argument("--to", dest="end", help="end (default: the end)")
    p.add_argument("--speed", type=float, help="retime, e.g. 1.25 for 25%% faster; pitch is kept")
    p.add_argument("-o", "--out")
    p.set_defaults(func=cmd_cut)

    p = sub.add_parser("vid-join", help="trim pieces and join them, hard cuts or dissolves")
    p.add_argument("out", help="output .mp4")
    p.add_argument("--clip", nargs="+", action="append", metavar="FILE [IN [OUT]]",
                   help="one piece; repeat for each, in order")
    p.add_argument("--dissolve", type=float, help="cross dissolve of this many seconds between pieces")
    p.add_argument("--size", help="output size, e.g. 1920x1080 (default: the first piece's)")
    p.add_argument("--fps", type=float, help="output frame rate (default: the first piece's)")
    p.add_argument("--fill", action="store_true", help="crop to fill the frame instead of letterboxing")
    p.add_argument("--silent", action="store_true", help="no audio track, e.g. for a looping AV screen")
    p.add_argument("--trim-ends", type=float, default=0.0,
                   help="shave this many seconds off both ends of every piece (phone start/stop wobble)")
    p.set_defaults(func=cmd_join)

    p = sub.add_parser("vid-sheet", help="contact sheet of labelled frames, to check a video at a glance")
    p.add_argument("file")
    p.add_argument("--times", nargs="+", help="exact times instead of evenly spaced frames")
    p.add_argument("--count", type=int, default=9)
    p.add_argument("--cols", type=int, default=3)
    p.add_argument("-o", "--out")
    p.set_defaults(func=cmd_sheet)

    p = sub.add_parser("vid-1080", help="fit a video inside 1920x1080")
    p.add_argument("file")
    p.add_argument("--pad", action="store_true", help="letterbox to exactly 1920x1080")
    p.add_argument("-o", "--out")
    p.set_defaults(func=cmd_1080)

    p = sub.add_parser("vid-pushend", help="ease a digital push-in over the end of a clip")
    p.add_argument("file")
    p.add_argument("out")
    p.add_argument("--ramp", type=float, required=True, help="seconds the push takes, ending on the last frame")
    p.add_argument("--scale", type=float, required=True, help="final zoom, e.g. 1.28")
    p.add_argument("--dx", type=float, default=0.0, help="drift right by this many pixels by the end")
    p.add_argument("--dy", type=float, default=0.0, help="drift down by this many pixels by the end")
    p.set_defaults(func=cmd_pushend)
