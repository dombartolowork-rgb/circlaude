"""Evidence for checking a cut against amends or a brief.

    circle vid-review cut_v2.mp4 [--prev cut_v1.mp4]   spec, shots, loudness, black frames,
                                                       silences, transcript, and what changed
    circle vid-transcribe cut.mp4                      timecoded transcript of VO and dialogue
    circle vid-review-doc findings.json --out r.docx   the checked findings as a Word report
    circle vid-review-upload r.docx --folder <link>    put that report in the job folder (on a go)

vid-review gathers evidence; it does not judge. It writes a folder beside the video:

    review.json       everything below, for Claude to read
    frames/           a still every ~2s of every shot, full enough to read supers
    sheets/           contact sheets, one labelled thumbnail per shot
    transcript.srt    what is said, with timecodes (ffmpeg's whisper filter)
    compare/          with --prev: side-by-side pairs of the shots that changed

"Does this look right" is not something a number answers, so every visual property is
left as frames for Claude and a person to look at. The numbers here are the ones that
genuinely are numbers: duration, size, loudness, true peak, black and silent stretches,
shot lengths.

Speech recognition is ffmpeg's built-in whisper filter, running on this machine: the
audio never leaves the laptop. It needs an ffmpeg built with whisper (on Windows,
`circle yt-setup --ffmpeg` installs one) and a speech model, which is downloaded once
into ~/.circle/models and checked against its published checksum.
"""
import base64
import datetime as dt
import difflib
import json
import math
import os
import re
import subprocess
import tempfile
import urllib.request

from circle import bins
from circle.videocmd import VideoError, _esc, _font, probe
from circle.ytcmd import _fetch_to

MODEL_DIR = os.path.join(os.path.expanduser("~"), ".circle", "models")
HF = "https://huggingface.co/{repo}/resolve/main/{name}"
# name: (repo, file, sha256, MB). small is the default: base mishears brand names and
# product names noticeably more often, which is exactly what a copy check is for.
MODELS = {
    "base": ("ggerganov/whisper.cpp", "ggml-base.bin",
             "60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe", 148),
    "small": ("ggerganov/whisper.cpp", "ggml-small.bin",
              "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b", 488),
    "medium": ("ggerganov/whisper.cpp", "ggml-medium.bin",
               "6c14d5adee5f86394037b4e4e8b59f1673b6cee10e3cf0b11bbdbee79c156208", 1534),
}
# voice activity detection, so whisper hears whole phrases instead of 3 second scraps
VAD = ("ggml-org/whisper-vad", "ggml-silero-v5.1.2.bin",
       "29940d98d42b91fbd05ce489f3ecf7c72f0a42f027e4875919a28fb4c04ea2cf", 1)

FRAME_EVERY = 2.0     # seconds between stills inside a shot
MATCH = 0.75          # shot similarity that counts as "the same shot" between versions
SAME = 0.97           # above this a matched shot is treated as unchanged


# ---------------------------------------------------------------- helpers

def _ff_log(args):
    """Run ffmpeg and return its log (stderr), where the analysis filters report."""
    r = subprocess.run([bins.ffmpeg(), "-hide_banner", "-nostats", *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise VideoError("ffmpeg failed:\n" + r.stderr[-2000:])
    return r.stderr


def tc(t):
    m, s = divmod(max(0.0, t), 60)
    return f"{int(m)}:{s:04.1f}"


def smpte(t, fps):
    fps = fps or 25
    f = int(round(max(0.0, t) * fps))
    r = int(round(fps))
    s, fr = divmod(f, r)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}:{fr:02d}"


def _aspect(w, h):
    if not w or not h:
        return "?"
    for a, b in ((16, 9), (9, 16), (4, 5), (5, 4), (1, 1), (4, 3), (3, 4), (21, 9), (2, 1)):
        if abs(w / h - a / b) < 0.02:
            return f"{a}:{b}"
    g = math.gcd(w, h)
    return f"{w // g}:{h // g}"


# ---------------------------------------------------------------- speech

_WHISPER = None


def has_whisper():
    global _WHISPER
    if _WHISPER is None:
        r = subprocess.run([bins.ffmpeg(), "-hide_banner", "-filters"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        _WHISPER = bool(re.search(r"^\s*\S+\s+whisper\s", r.stdout, re.M))
    return _WHISPER


def _ensure(repo, name, sha, mb):
    path = os.path.join(MODEL_DIR, name)
    if os.path.isfile(path):
        return path  # only ever renamed into place after its checksum passed
    os.makedirs(MODEL_DIR, exist_ok=True)
    print(f"speech model: downloading {name} ({mb}MB, once)")
    part = path + ".part"
    got = _fetch_to(HF.format(repo=repo, name=name), part)
    if got != sha:
        os.remove(part)
        raise VideoError(f"{name} did not match its published checksum; nothing kept.")
    os.replace(part, path)
    print("  checksum ok, saved", path)
    return path


def _srt_time(s):
    h, m, rest = s.strip().split(":")
    sec, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000


def parse_srt(text):
    segs = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.strip().splitlines()
        arrow = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if arrow is None:
            continue
        a, b = lines[arrow].split("-->")
        words = " ".join(lines[arrow + 1:]).strip()
        if words:
            segs.append({"start": _srt_time(a), "end": _srt_time(b), "text": words})
    return segs


def transcribe(src, out_srt, language="en", model="small"):
    """Timecoded segments of what is said. Raises VideoError if this ffmpeg cannot."""
    if not has_whisper():
        hint = ("Run `circle yt-setup --ffmpeg` to replace it with the build that has it."
                if bins.WINDOWS else "It needs an ffmpeg built with --enable-whisper.")
        raise VideoError("This ffmpeg has no speech recognition (whisper filter). " + hint)
    if model not in MODELS:
        raise VideoError(f"--model must be one of {', '.join(MODELS)}")
    m = _ensure(*MODELS[model])
    v = _ensure(*VAD)
    af = (f"aresample=16000,whisper=model='{_esc(m)}':language={language}:queue=20"
          f":vad_model='{_esc(v)}':destination='{_esc(out_srt)}':format=srt")
    if os.path.exists(out_srt):
        os.remove(out_srt)
    _ff_log(["-i", src, "-vn", "-af", af, "-f", "null", "-"])
    if not os.path.exists(out_srt):
        return []
    with open(out_srt, encoding="utf-8", errors="replace") as f:
        return parse_srt(f.read())


# ---------------------------------------------------------------- analysis passes

def video_pass(src, scene):
    """Cuts (scene changes) and black stretches, in one decode at low resolution."""
    vf = (f"scale=320:-2,blackdetect=d=0.04:pix_th=0.10,"
          f"select='gt(scene,{scene})',showinfo")
    log = _ff_log(["-i", src, "-an", "-vf", vf, "-f", "null", "-"])
    cuts = [float(x) for x in re.findall(r"Parsed_showinfo.*?pts_time:\s*([\d.]+)", log)]
    black = [{"start": float(a), "end": float(b)}
             for a, b in re.findall(r"black_start:\s*([\d.]+)\s+black_end:\s*([\d.]+)", log)]
    return sorted(set(round(c, 3) for c in cuts)), black


def audio_pass(src, duration):
    """Loudness (EBU R128), true peak, and silent stretches."""
    log = _ff_log(["-i", src, "-vn", "-af",
                   "ebur128=peak=true:framelog=verbose,silencedetect=n=-45dB:d=0.4",
                   "-f", "null", "-"])
    summary = log[log.rfind("Summary:"):] if "Summary:" in log else ""

    def grab(pat):
        m = re.search(pat, summary)
        if not m:
            return None
        return None if "inf" in m.group(1) else float(m.group(1))

    loud = {"integrated_lufs": grab(r"I:\s+(-?[\d.]+|-inf)\s+LUFS"),
            "range_lu": grab(r"LRA:\s+(-?[\d.]+)\s+LU"),
            "true_peak_dbfs": grab(r"True peak:\s+Peak:\s+(-?[\d.]+|-inf)\s+dBFS")}
    silences, start = [], None
    for kind, val in re.findall(r"silence_(start|end):\s*(-?[\d.]+)", log):
        if kind == "start":
            start = max(0.0, float(val))
        elif start is not None:
            silences.append({"start": start, "end": float(val)})
            start = None
    if start is not None:
        silences.append({"start": start, "end": duration})
    return loud, silences


def shots_from(cuts, duration, fps):
    edges = [0.0] + [c for c in cuts if 0 < c < duration] + [duration]
    shots = []
    for a, b in zip(edges, edges[1:]):
        if b - a > 0.001:
            shots.append({"n": len(shots) + 1, "start": a, "end": b, "dur": b - a})
    flash = 2.5 / (fps or 25)
    for s in shots:
        s["flash"] = s["dur"] < flash
    return shots


def _scale_box(info):
    portrait = info["height"] > info["width"]
    return (270, 480) if portrait else (480, 270)


def grab_frames(src, info, shots, out_dir):
    """Stills every ~FRAME_EVERY seconds within each shot, big enough to read supers."""
    os.makedirs(out_dir, exist_ok=True)
    cap = "scale='if(gt(iw,ih),min(1280,iw),-2)':'if(gt(iw,ih),-2,min(1280,ih))'"
    last = max(info["duration"] - 0.05, 0)
    for s in shots:
        n = max(1, math.ceil(s["dur"] / FRAME_EVERY))
        s["frames"] = []
        for k in range(n):
            t = min(s["start"] + s["dur"] * (k + 0.5) / n, last)
            path = os.path.join(out_dir, f"s{s['n']:03d}-{k + 1}_{tc(t).replace(':', 'm')}s.jpg")
            _ff_log(["-y", "-v", "error", "-ss", f"{t:.3f}", "-i", src, "-frames:v", "1",
                     "-vf", cap, "-q:v", "3", path])
            s["frames"].append({"t": round(t, 3), "file": path})
        s["key"] = s["frames"][len(s["frames"]) // 2]["file"]


def contact_sheets(shots, info, out_dir, prefix="sheet", per=16, cols=4):
    """One labelled thumbnail per shot, 16 to a sheet."""
    os.makedirs(out_dir, exist_ok=True)
    bw, bh = _scale_box(info)
    font = _font()
    tmp = os.path.join(out_dir, "_tiles")
    os.makedirs(tmp, exist_ok=True)
    sheets = []
    for page in range(math.ceil(len(shots) / per)):
        group = shots[page * per:(page + 1) * per]
        for i, s in enumerate(group):
            vf = (f"scale={bw}:{bh}:force_original_aspect_ratio=decrease,"
                  f"pad={bw}:{bh}:(ow-iw)/2:(oh-ih)/2:color=gray")
            if font:
                label = _esc(f"S{s['n']}  {tc(s['start'])}  ({s['dur']:.1f}s)")
                vf += (f",drawtext=fontfile='{_esc(font)}':text='{label}':x=8:y=8:fontsize=18:"
                       "fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=4")
            _ff_log(["-y", "-v", "error", "-i", s["key"], "-frames:v", "1", "-vf", vf,
                     os.path.join(tmp, f"t_{i:03d}.png")])
        c = min(cols, len(group))
        rows = math.ceil(len(group) / c)
        for i in range(len(group), rows * c):
            _ff_log(["-y", "-v", "error", "-f", "lavfi", "-i", f"color=gray:s={bw}x{bh}",
                     "-frames:v", "1", os.path.join(tmp, f"t_{i:03d}.png")])
        out = os.path.join(out_dir, f"{prefix}_{page + 1:02d}.jpg")
        _ff_log(["-y", "-v", "error", "-framerate", "1", "-i", os.path.join(tmp, "t_%03d.png"),
                 "-vf", f"tile={c}x{rows}:padding=6:margin=6:color=gray", "-frames:v", "1",
                 "-q:v", "3", out])
        for f in os.listdir(tmp):
            os.remove(os.path.join(tmp, f))
        sheets.append(out)
    os.rmdir(tmp)
    return sheets


# ---------------------------------------------------------------- comparing versions

def _signature(jpg):
    """A 24x24 grey thumbnail, normalised so a regrade alone does not break the match."""
    r = subprocess.run([bins.ffmpeg(), "-v", "error", "-i", jpg, "-vf", "scale=24:24,format=gray",
                        "-f", "rawvideo", "-"], capture_output=True)
    px = list(r.stdout[:576])
    if len(px) < 576:
        return None
    mean = sum(px) / 576
    sd = math.sqrt(sum((p - mean) ** 2 for p in px) / 576) or 1.0
    return [(p - mean) / sd for p in px], mean


def _similar(a, b):
    if not a or not b:
        return 0.0
    return sum(x * y for x, y in zip(a[0], b[0])) / 576


def align(prev, new):
    """Line the two versions' shots up in order, like a diff. Returns ops:
    ("same"|"changed", i, j, similarity), ("removed", i, None, 0), ("added", None, j, 0)."""
    n, m = len(prev), len(new)
    sim = [[_similar(p["sig"], q["sig"]) for q in new] for p in prev]
    best = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            take = (1 + sim[i][j] + best[i + 1][j + 1]) if sim[i][j] >= MATCH else -1
            best[i][j] = max(take, best[i + 1][j], best[i][j + 1])
    ops, i, j = [], 0, 0
    while i < n and j < m:
        if sim[i][j] >= MATCH and best[i][j] == 1 + sim[i][j] + best[i + 1][j + 1]:
            ops.append(("match", i, j, sim[i][j]))
            i, j = i + 1, j + 1
        elif best[i + 1][j] >= best[i][j + 1]:
            ops.append(("removed", i, None, 0.0))
            i += 1
        else:
            ops.append(("added", None, j, 0.0))
            j += 1
    ops += [("removed", k, None, 0.0) for k in range(i, n)]
    ops += [("added", None, k, 0.0) for k in range(j, m)]
    return ops


def _pair(prev_jpg, new_jpg, label, out, info):
    """Previous version's shot on the left, this version's on the right."""
    bw, bh = _scale_box(info)
    font = _font()
    fit = (f"scale={bw * 2}:{bh * 2}:force_original_aspect_ratio=decrease,"
           f"pad={bw * 2}:{bh * 2}:(ow-iw)/2:(oh-ih)/2:color=gray")

    def tag(text):
        if not font:
            return ""
        return (f",drawtext=fontfile='{_esc(font)}':text='{_esc(text)}':x=10:y=10:fontsize=26:"
                "fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=5")

    _ff_log(["-y", "-v", "error", "-i", prev_jpg, "-i", new_jpg, "-filter_complex",
             f"[0:v]{fit}{tag('BEFORE')}[a];[1:v]{fit}{tag('NOW  ' + label)}[b];[a][b]hstack=inputs=2",
             "-frames:v", "1", "-q:v", "3", out])


def _words(segs):
    out = []
    for s in segs:
        ws = s["text"].split()
        for k, w in enumerate(ws):
            t = s["start"] + (s["end"] - s["start"]) * k / max(1, len(ws))
            out.append((re.sub(r"[^\w']", "", w.lower()), w, t))
    return [w for w in out if w[0]]


def transcript_changes(prev_segs, new_segs):
    a, b = _words(prev_segs), _words(new_segs)
    sm = difflib.SequenceMatcher(a=[w[0] for w in a], b=[w[0] for w in b], autojunk=False)
    changes = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        at = b[j1][2] if j1 < len(b) else (b[-1][2] if b else 0.0)
        changes.append({"type": op, "at": round(at, 2), "at_tc": tc(at),
                        "was": " ".join(w[1] for w in a[i1:i2]),
                        "now": " ".join(w[1] for w in b[j1:j2])})
    return changes


# ---------------------------------------------------------------- one version

def analyse(src, out_dir, args, label):
    info = probe(src)
    print(f"{label}: {os.path.basename(src)}  {tc(info['duration'])}  {info['width']}x{info['height']}")
    cuts, black = video_pass(src, args.scene)
    shots = shots_from(cuts, info["duration"], info["fps"])
    grab_frames(src, info, shots, os.path.join(out_dir, "frames"))
    for s in shots:
        s["sig"] = _signature(s["key"])
    loud, silences = audio_pass(src, info["duration"]) if info["audio"] else ({}, [])
    transcript, note = None, None
    if not info["audio"]:
        note = "no audio track"
    elif args.no_speech:
        note = "skipped (--no-speech)"
    else:
        try:
            transcript = transcribe(src, os.path.join(out_dir, "transcript.srt"), args.language, args.model)
        except VideoError as e:
            note = str(e)
    return {"file": os.path.abspath(src), "info": info, "shots": shots, "black": black,
            "loudness": loud, "silences": silences, "transcript": transcript, "transcript_note": note}


def _public(shot):
    return {k: v for k, v in shot.items() if k != "sig"}


def cmd_review(args):
    src = args.file
    base = os.path.splitext(src)[0]
    out = args.out or base + "_review"
    os.makedirs(out, exist_ok=True)

    cur = analyse(src, out, args, "now")
    info = cur["info"]
    sheets = contact_sheets(cur["shots"], info, os.path.join(out, "sheets"))

    compare = None
    if args.prev:
        pdir = os.path.join(out, "prev")
        os.makedirs(pdir, exist_ok=True)
        old = analyse(args.prev, pdir, args, "previous")
        contact_sheets(old["shots"], old["info"], os.path.join(pdir, "sheets"))
        cdir = os.path.join(out, "compare")
        os.makedirs(cdir, exist_ok=True)
        rows = []
        for op, i, j, s in align(old["shots"], cur["shots"]):
            if op == "match":
                p, q = old["shots"][i], cur["shots"][j]
                delta = q["dur"] - p["dur"]
                retimed = abs(delta) > 1.5 / (info["fps"] or 25)
                changed = s < SAME
                row = {"op": "changed" if (changed or retimed) else "same", "prev_shot": p["n"],
                       "shot": q["n"], "at": tc(q["start"]), "similarity": round(s, 3),
                       "dur_change": round(delta, 2), "retimed": retimed, "picture_changed": changed}
                if changed or retimed:
                    pair = os.path.join(cdir, f"S{q['n']:03d}_vs_prev_S{p['n']:03d}.jpg")
                    _pair(p["key"], q["key"], f"S{q['n']} {tc(q['start'])}", pair, info)
                    row["pair"] = pair
            elif op == "removed":
                p = old["shots"][i]
                row = {"op": "removed", "prev_shot": p["n"], "prev_at": tc(p["start"]),
                       "dur": round(p["dur"], 2), "frame": p["key"]}
            else:
                q = cur["shots"][j]
                row = {"op": "added", "shot": q["n"], "at": tc(q["start"]),
                       "dur": round(q["dur"], 2), "frame": q["key"]}
            rows.append(row)
        compare = {"prev_file": old["file"], "prev_duration": round(old["info"]["duration"], 2),
                   "duration_change": round(info["duration"] - old["info"]["duration"], 2),
                   "shots": rows,
                   "transcript_changes": (transcript_changes(old["transcript"], cur["transcript"])
                                          if old["transcript"] is not None and cur["transcript"] is not None
                                          else None),
                   "prev_loudness": old["loudness"]}

    report = {
        "file": cur["file"],
        "spec": {"duration": round(info["duration"], 3), "duration_tc": smpte(info["duration"], info["fps"]),
                 "width": info["width"], "height": info["height"], "aspect": _aspect(info["width"], info["height"]),
                 "fps": round(info["fps"], 3), "video_codec": info["vcodec"], "audio_codec": info["acodec"],
                 "size_mb": round(info["size_mb"], 1), "file_name": os.path.basename(src)},
        "loudness": cur["loudness"],
        "black": cur["black"],
        "silences": cur["silences"],
        "shots": [_public(s) for s in cur["shots"]],
        "flash_frames": [s["n"] for s in cur["shots"] if s["flash"]],
        "transcript": cur["transcript"],
        "transcript_note": cur["transcript_note"],
        "sheets": sheets,
        "compare": compare,
    }
    with open(os.path.join(out, "review.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    if cur["transcript"]:
        with open(os.path.join(out, "transcript.txt"), "w", encoding="utf-8") as f:
            for s in cur["transcript"]:
                f.write(f"{tc(s['start'])}  {s['text']}\n")
    _summary(report, out)


def _summary(r, out):
    sp = r["spec"]
    print(f"\nspec:      {sp['duration']:.2f}s ({sp['duration_tc']}), {sp['width']}x{sp['height']} "
          f"({sp['aspect']}), {sp['fps']}fps, {sp['video_codec']}, "
          f"{sp['audio_codec'] or 'NO AUDIO'}, {sp['size_mb']}MB")
    ld = r["loudness"]
    if ld:
        i, tp = ld.get("integrated_lufs"), ld.get("true_peak_dbfs")
        flags = []
        if tp is not None and tp > -1.0:
            flags.append("true peak above -1 dBTP, may clip after encoding")
        print(f"loudness:  {i} LUFS integrated, {tp} dBTP true peak, {ld.get('range_lu')} LU range"
              + (f"  [{'; '.join(flags)}]" if flags else "")
              + "\n           (social and web about -14 LUFS, UK broadcast -23)")
    print(f"shots:     {len(r['shots'])}" + (f", possible flash frames at shots {r['flash_frames']}"
                                             if r["flash_frames"] else ""))
    if r["black"]:
        print("black:     " + ", ".join(f"{tc(b['start'])}-{tc(b['end'])}" for b in r["black"]))
    if r["silences"]:
        print("silent:    " + ", ".join(f"{tc(s['start'])}-{tc(s['end'])}" for s in r["silences"]))
    if r["transcript"] is not None:
        print(f"speech:    {len(r['transcript'])} line(s) transcribed, see transcript.txt")
    else:
        print(f"speech:    NOT TRANSCRIBED ({r['transcript_note']}). Listen to the VO; do not assume it.")
    c = r["compare"]
    if c:
        ops = [s["op"] for s in c["shots"]]
        print(f"vs prev:   {c['duration_change']:+.2f}s; {ops.count('same')} shots unchanged, "
              f"{ops.count('changed')} changed, {ops.count('added')} added, {ops.count('removed')} removed")
        if c["transcript_changes"]:
            for t in c["transcript_changes"]:
                print(f"           {t['at_tc']}  {t['type']}: \"{t['was']}\" -> \"{t['now']}\"")
    print(f"\nsaved {out}  (review.json, frames/, sheets/"
          + (", compare/" if c else "") + "). Look at the frames before judging anything visual.")


def cmd_transcribe(args):
    out = args.out or os.path.splitext(args.file)[0] + ".srt"
    if not probe(args.file)["audio"]:
        raise VideoError("That file has no audio track.")
    segs = transcribe(args.file, out, args.language, args.model)
    for s in segs:
        print(f"{tc(s['start'])}  {s['text']}")
    print(f"\nsaved {out}  ({len(segs)} line(s))")


# ---------------------------------------------------------------- the report

VERDICTS = {  # fill, ink: colour carries meaning here, so it is allowed
    "done": ("D9EAD3", "274E13"),
    "not done": ("F4CCCC", "990000"),
    "partly": ("FFF2CC", "7F6000"),
    "needs your eyes": ("E6E6E6", None),
}


def _thumb(path, tmp, width=800):
    """A smaller copy for the document, so a report with twenty stills stays well under 4MB."""
    out = os.path.join(tmp, f"t{len(os.listdir(tmp)):03d}.jpg")
    try:
        _ff_log(["-y", "-v", "error", "-i", path, "-vf", f"scale='min({width},iw)':-2",
                 "-frames:v", "1", "-q:v", "4", out])
        return out
    except Exception:
        return path


def cmd_doc(args):
    """findings.json (written after the review was checked and shown in chat) to a Word report.

    {"title", "file", "compared_with", "checked_against": [..], "summary",
     "amends": [{"n", "ask", "who", "verdict", "where", "note", "images": [..]}],
     "unrequested": [{"where", "note", "images"}], "issues": [{"where", "note", "images"}],
     "spec": [["Duration", "1:50", "brief says 1:47"], ...]}
    """
    from circle import docxbuild
    with open(args.findings, encoding="utf-8") as f:
        F = json.load(f)
    d = docxbuild.Doc()
    d.heading(F.get("title") or "Video review", 1)
    head = [("File", F.get("file")), ("Compared with", F.get("compared_with")),
            ("Checked against", "\n".join(F.get("checked_against") or [])),
            ("Date", F.get("date") or dt.date.today().strftime("%-d %B %Y" if os.name != "nt" else "%d %B %Y"))]
    d.table([[{"text": k, "bold": True, "fill": docxbuild.GREY_FILL}, v] for k, v in head if v],
            widths=[24, 76])
    if F.get("summary"):
        d.para(F["summary"])

    with tempfile.TemporaryDirectory(prefix="vidreview-doc-") as tmp:
        def pics(item):
            for img in item.get("images") or []:
                if os.path.isfile(img):
                    d.image(_thumb(img, tmp), width_cm=12 if "_vs_" not in img else 16, max_height_cm=9)
                else:
                    print(f"  WARNING: image not found, left out: {img}")

        if F.get("amends"):
            d.heading("Amends", 2)
            for a in F["amends"]:
                fill, ink = VERDICTS.get((a.get("verdict") or "").lower(), (None, None))
                rows = [[{"text": f"{a.get('n', '')}", "bold": True, "fill": docxbuild.GREY_FILL},
                         {"text": a.get("ask", ""), "bold": True}]]
                for key, title in (("who", "Asked by"), ("verdict", "Verdict"),
                                   ("where", "Where"), ("note", "Notes")):
                    if a.get(key):
                        cell = a[key]
                        if key == "verdict":
                            cell = {"text": a[key], "bold": True, "fill": fill, "ink": ink}
                        rows.append([{"text": title, "bold": True, "fill": docxbuild.GREY_FILL}, cell])
                d.table(rows, widths=[18, 82])
                pics(a)

        for key, title in (("unrequested", "Changed, but not asked for"),
                           ("issues", "Other things found")):
            if F.get(key):
                d.heading(title, 2)
                for it in F[key]:
                    d.table([[{"text": it.get("where", ""), "bold": True, "fill": docxbuild.GREY_FILL},
                              it.get("note", "")]], widths=[18, 82])
                    pics(it)

        if F.get("spec"):
            d.heading("Spec", 2)
            d.table([["Check", "This file", "Note"]] + [list(r) + [""] * (3 - len(r)) for r in F["spec"]],
                    widths=[24, 30, 46], header=True)
        out = d.save(args.out)
    print(f"saved {out}  ({os.path.getsize(out) / 1048576:.1f}MB)")
    print("Not uploaded. `circle vid-review-upload` puts it in the job folder, on the user's go.")


def _share_id(url):
    return "u!" + base64.urlsafe_b64encode(url.strip().encode()).decode().rstrip("=")


def cmd_upload(args):
    """Put the report in a SharePoint folder. Never overwrites: a new version gets a new name."""
    from circle import graph
    if not os.path.isfile(args.file):
        raise VideoError(f"No such file: {args.file}")
    st, _, item = graph.call_retry("GET", f"/shares/{_share_id(args.folder)}/driveItem")
    if st != 200 or "folder" not in item:
        raise VideoError(f"Could not open that link as a folder ({st}). Use the job folder's own link.")
    drive, fid = item["parentReference"]["driveId"], item["id"]
    name = args.name or os.path.basename(args.file)
    q = urllib.request.quote(name)
    st, _, _ = graph.call("GET", f"/drives/{drive}/items/{fid}:/{q}")
    if st == 200:
        raise VideoError(f"{name} is already in {item.get('name')}. Give this one a new name "
                         "(--name), so nobody's copy is overwritten.")
    with open(args.file, "rb") as f:
        data = f.read()
    ctype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if len(data) <= 4 * 1024 * 1024:
        st, _, d = graph.call_retry(
            "PUT", f"/drives/{drive}/items/{fid}:/{q}:/content?@microsoft.graph.conflictBehavior=fail",
            body=data, content_type=ctype)
    else:
        st, _, s = graph.call("POST", f"/drives/{drive}/items/{fid}:/{q}:/createUploadSession",
                              {"item": {"@microsoft.graph.conflictBehavior": "fail"}})
        if st != 200:
            raise VideoError(f"Upload session refused ({st}): {s}")
        chunk, pos, d = 10 * 327680, 0, {}
        while pos < len(data):
            part = data[pos:pos + chunk]
            req = urllib.request.Request(s["uploadUrl"], data=part, method="PUT")
            req.add_header("Content-Range", f"bytes {pos}-{pos + len(part) - 1}/{len(data)}")
            with urllib.request.urlopen(req) as r:  # the upload URL is pre-signed: no token
                st = r.status
                raw = r.read()
                d = json.loads(raw) if raw else {}
            pos += len(part)
    if st not in (200, 201):
        raise VideoError(f"Upload failed ({st}): {d}")
    print(f"uploaded {name} to {item.get('name')}")
    print("link:", d.get("webUrl", "(none returned)"))


def register(sub):
    p = sub.add_parser("vid-review", help="gather evidence to check a cut against amends or a brief")
    p.add_argument("file")
    p.add_argument("--prev", help="the previous version, to see what changed")
    p.add_argument("-o", "--out", help="folder (default: <video>_review beside the video)")
    p.add_argument("--no-speech", action="store_true", help="skip the transcript")
    p.add_argument("--language", default="en", help="spoken language, e.g. en, fr, or auto (default en)")
    p.add_argument("--model", default="small", choices=sorted(MODELS),
                   help="speech model: base is faster, medium more accurate (default small)")
    p.add_argument("--scene", type=float, default=0.30,
                   help="cut detection sensitivity, lower finds more cuts (default 0.30)")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("vid-transcribe", help="timecoded transcript of a video's speech, on this machine")
    p.add_argument("file")
    p.add_argument("-o", "--out", help=".srt path (default: beside the video)")
    p.add_argument("--language", default="en")
    p.add_argument("--model", default="small", choices=sorted(MODELS))
    p.set_defaults(func=cmd_transcribe)

    p = sub.add_parser("vid-review-doc", help="the checked review findings as a Word report")
    p.add_argument("findings", help="findings JSON (see `circle vid-review-doc --help` in the code)")
    p.add_argument("--out", required=True, help="output .docx")
    p.set_defaults(func=cmd_doc)

    p = sub.add_parser("vid-review-upload", help="put a review report in a SharePoint folder (never overwrites)")
    p.add_argument("file")
    p.add_argument("--folder", required=True, help="the job folder's SharePoint link")
    p.add_argument("--name", help="file name in SharePoint (default: the file's own)")
    p.set_defaults(func=cmd_upload)
