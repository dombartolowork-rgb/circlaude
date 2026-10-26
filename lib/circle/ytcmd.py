"""Download video from YouTube (and TikTok, Instagram reels) for reference and edits.

yt-dlp does the downloading. YouTube refuses to serve video unless the client can
run its JavaScript challenge, so yt-dlp also needs a JS runtime: Deno. Neither is
Python we could ship, so `circle yt-setup` downloads both as standalone binaries
into ~/.circle/bin and checks each against the checksum its project publishes.
ffmpeg merges the separate HD video and audio streams; on Windows yt-setup can
fetch that too (`--ffmpeg`), elsewhere install it or ask IT to push it.

    circle yt-setup [--ffmpeg]                  install or update the tools
    circle yt-get <url> [<url> ...]             whole video, best quality, as MP4
    circle yt-clip <url> --from 1:20 --to 2:05  just one section
    circle yt-find <url> "phrase"               search the auto-captions for a moment

Only download what you have the right to use: Circle's own films, client-supplied
material, or reference for internal work. To put a finished film on Circle's Vimeo,
see `circle vi-upload`.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile

from circle import bins

YTDLP = bins.exe("yt-dlp")
DENO = bins.exe("deno")
DEFAULT_OUT = os.path.join(os.path.expanduser("~"), "Downloads", "YouTube")

YTDLP_REL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/"
DENO_REL = "https://github.com/denoland/deno/releases/latest/download/"
FFMPEG_REL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
FFMPEG_WIN = "ffmpeg-master-latest-win64-gpl"

# bv (not bv*) means a video-only stream, so YouTube's combined 360p file is never
# chosen by accident. avc1 and m4a play everywhere, PowerPoint included.
VIDEO_FMT = "bv[ext=mp4][vcodec^=avc1]/bv[ext=mp4]"
VIDEO_FALLBACK = "b[ext=mp4]"
AUDIO_FMT = "ba[ext=m4a]/ba[acodec^=mp4a]"
SINGLE_FILE_FMT = "b[vcodec!=none][acodec!=none]/b"
CLIP_FMT = ("bv[ext=mp4][vcodec^=avc1]+ba[ext=m4a]/bv[ext=mp4]+ba[ext=m4a]/"
            "bv*+ba/" + SINGLE_FILE_FMT)


class YTError(RuntimeError):
    pass


# ---------------------------------------------------------------- setup

def _fetch_to(url, path):
    """Stream a download to disk and return its SHA-256."""
    req = urllib.request.Request(url, headers={"User-Agent": "orbit-circle-cli"})
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=600) as r, open(path, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
            f.write(chunk)
    return h.hexdigest()


def _fetch_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "orbit-circle-cli"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8", "replace")


def _sum_for(sums_text, filename):
    """Checksum for one file from a SHA256SUMS-style listing."""
    for line in sums_text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == filename:
            return parts[0].lower()
    return None


def _first_hash(text):
    m = re.search(r"\b[0-9a-fA-F]{64}\b", text)
    return m.group(0).lower() if m else None


def _place(src, dest):
    os.makedirs(bins.BIN, exist_ok=True)
    tmp = dest + ".part"
    shutil.copyfile(src, tmp)
    if not bins.WINDOWS:
        os.chmod(tmp, 0o755)
    os.replace(tmp, dest)
    if platform_is_mac():
        # downloaded binaries carry the quarantine flag, which stops them running
        subprocess.run(["xattr", "-c", dest], check=False)


def platform_is_mac():
    return os.uname().sysname == "Darwin" if hasattr(os, "uname") else False


def _ytdlp_asset():
    if bins.WINDOWS:
        return "yt-dlp.exe"
    return "yt-dlp_macos" if platform_is_mac() else "yt-dlp_linux"


def _deno_asset():
    if bins.WINDOWS:
        return "deno-x86_64-pc-windows-msvc.zip"
    if platform_is_mac():
        return f"deno-{bins.arch()}-apple-darwin.zip"
    return f"deno-{bins.arch()}-unknown-linux-gnu.zip"


def cmd_setup(args):
    with tempfile.TemporaryDirectory(prefix="orbit-setup-") as tmp:
        name = _ytdlp_asset()
        print(f"yt-dlp: downloading {name}")
        want = _sum_for(_fetch_text(YTDLP_REL + "SHA2-256SUMS"), name)
        got = _fetch_to(YTDLP_REL + name, os.path.join(tmp, name))
        if not want or got != want:
            raise YTError("yt-dlp checksum did not match its published SHA2-256SUMS; nothing installed.")
        _place(os.path.join(tmp, name), YTDLP)
        print("  checksum ok, installed", YTDLP)

        name = _deno_asset()
        print(f"deno: downloading {name}")
        want = _first_hash(_fetch_text(DENO_REL + name + ".sha256sum"))
        zpath = os.path.join(tmp, name)
        if _fetch_to(DENO_REL + name, zpath) != want:
            raise YTError("deno checksum did not match its published .sha256sum; nothing installed.")
        with zipfile.ZipFile(zpath) as z:
            inner = "deno.exe" if bins.WINDOWS else "deno"
            z.extract(inner, tmp)
        _place(os.path.join(tmp, inner), DENO)
        print("  checksum ok, installed", DENO)

        if args.ffmpeg:
            if not bins.WINDOWS:
                print("ffmpeg: --ffmpeg only fetches the Windows build. On a Mac, install ffmpeg "
                      "(for example `brew install ffmpeg`).")
            else:
                name = FFMPEG_WIN + ".zip"
                print(f"ffmpeg: downloading {name} (about 150MB)")
                want = _sum_for(_fetch_text(FFMPEG_REL + "checksums.sha256"), name)
                zpath = os.path.join(tmp, name)
                if not want or _fetch_to(FFMPEG_REL + name, zpath) != want:
                    raise YTError("ffmpeg checksum did not match its published checksums.sha256; nothing installed.")
                with zipfile.ZipFile(zpath) as z:
                    for tool in ("ffmpeg.exe", "ffprobe.exe"):
                        member = f"{FFMPEG_WIN}/bin/{tool}"
                        z.extract(member, tmp)
                        _place(os.path.join(tmp, *member.split("/")), os.path.join(bins.BIN, tool))
                print("  checksum ok, installed ffmpeg and ffprobe in", bins.BIN)

    for exe in (YTDLP, DENO):
        out = subprocess.run([exe, "--version"], capture_output=True, text=True).stdout.strip().splitlines()
        print(f"{os.path.basename(exe)}: {out[0] if out else '?'}")
    ff = bins.find("ffmpeg")
    print("ffmpeg:", ff or "NOT FOUND (needed to merge HD video and audio, and for clips)")


# ---------------------------------------------------------------- yt-dlp

def _need_tools():
    if not (os.path.exists(YTDLP) and os.path.exists(DENO)):
        raise YTError("Not set up yet. Run: circle yt-setup")


def _ytdlp(extra):
    # android_vr and web_embedded reliably list the HD streams; the default client
    # often offers only 360p, so ask those first and fall back to it
    cmd = [YTDLP, "--js-runtimes", f"deno:{DENO}", "--extractor-args",
           "youtube:player_client=android_vr,web_embedded,default",
           "--no-playlist", "--no-progress"]
    ff = bins.find("ffmpeg")
    if ff:
        cmd += ["--ffmpeg-location", ff]
    r = subprocess.run(cmd + extra, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        tail = "\n".join(l for l in r.stderr.splitlines() if "ERROR" in l or "WARNING" in l)[-1500:]
        raise YTError("yt-dlp failed:\n" + (tail or r.stderr[-1500:]))
    return r.stdout


def _safe(name):
    name = re.sub(r'[\\/:*?"<>|]+', " ", name).strip().rstrip(".")
    return re.sub(r"\s+", " ", name)[:150] or "video"


def _fetch_stream(fmt, path, url, what, tries=3):
    """One stream, retried: YouTube fails the odd request on a stream it does serve."""
    last = None
    for i in range(tries):
        try:
            _ytdlp(["-f", fmt, "-o", path, url])
            if os.path.exists(path) and os.path.getsize(path) > 0:
                return
        except YTError as e:
            last = e
        time.sleep(3 * (i + 1))
    raise YTError(f"Could not download the {what} stream after {tries} tries.\n{last or ''}")


def _info(url):
    return json.loads(_ytdlp(["-J", url]))


def download(url, out_dir):
    """Download one video at the best quality. Returns the file path."""
    _need_tools()
    os.makedirs(out_dir, exist_ok=True)
    info = _info(url)
    title = _safe(info.get("title") or info.get("id") or "video")
    final = os.path.join(out_dir, title + ".mp4")
    print(f"{info.get('title')}  ({info.get('duration_string') or '?'}, "
          f"{info.get('channel') or info.get('uploader') or '?'})")

    if (info.get("extractor_key") or "").lower() != "youtube":
        # TikTok and Instagram serve picture and sound in one file, so no merge is needed
        _fetch_stream(SINGLE_FILE_FMT, final, url, "video")
        print(f"saved {final}  ({os.path.getsize(final) / 1048576:.0f}MB)")
        return final

    ff = bins.ffmpeg()
    with tempfile.TemporaryDirectory(prefix="ytget-") as tmp:
        v = os.path.join(tmp, "video.mp4")
        a = os.path.join(tmp, "audio.m4a")
        try:
            _fetch_stream(VIDEO_FMT, v, url, "video")
        except YTError:
            print("  WARNING: no HD stream came back after retries, falling back to the combined 360p file")
            _fetch_stream(VIDEO_FALLBACK, v, url, "video")
        # Never fall back to a silent file: a stream that exists can still fail one request.
        _fetch_stream(AUDIO_FMT, a, url, "audio")
        # HD DASH streams can carry a frozen tail well past the real end, so cut to
        # YouTube's own duration. Stream copy: no re-encode, no quality loss.
        cmd = [ff, "-y", "-v", "error", "-i", v, "-i", a, "-map", "0:v:0", "-map", "1:a:0",
               "-c", "copy", "-movflags", "+faststart"]
        if info.get("duration"):
            cmd += ["-t", str(info["duration"])]
        r = subprocess.run(cmd + [final], capture_output=True, text=True)
        if r.returncode != 0:
            raise YTError("Merging video and audio failed:\n" + r.stderr[-1500:])

    print(f"saved {final}  ({os.path.getsize(final) / 1048576:.0f}MB)")
    return final


def parse_time(s):
    """'83', '83.5', '1:23', '0:01:23.4' -> seconds."""
    parts = [float(p) for p in str(s).strip().split(":")]
    secs = 0.0
    for p in parts:
        secs = secs * 60 + p
    return secs


def _hms(t):
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}" if h else f"{int(m)}:{s:05.2f}"


# ---------------------------------------------------------------- commands

def cmd_get(args):
    out = os.path.expanduser(args.out)
    for url in args.url:
        download(url, out)


def cmd_clip(args):
    """Fetch only one section, cut on frame-exact boundaries."""
    _need_tools()
    bins.ffmpeg()
    a, b = parse_time(args.start), parse_time(args.end)
    if b <= a:
        raise YTError("--to must be after --from.")
    out_dir = os.path.expanduser(args.out)
    os.makedirs(out_dir, exist_ok=True)
    info = _info(args.url)
    title = _safe(info.get("title") or info.get("id") or "clip")
    stamp = f"{_hms(a)}-{_hms(b)}".replace(":", ".")
    final = os.path.join(out_dir, f"{title} [{stamp}].mp4")
    try:
        # fetch only the section: ffmpeg reads the stream directly, so long videos stay quick
        _ytdlp(["-f", CLIP_FMT, "--download-sections", f"*{a}-{b}", "--force-keyframes-at-cuts",
                "--merge-output-format", "mp4", "-o", final, args.url])
    except YTError as e:
        # Some ffmpeg builds cannot open HTTPS themselves (certificate store, TLS library).
        # Fall back to yt-dlp's own download of the whole video, then cut it locally.
        print("  section download failed, fetching the whole video and cutting locally")
        print("  (" + str(e).splitlines()[-1][:160] + ")")
        with tempfile.TemporaryDirectory(prefix="ytclip-") as tmp:
            whole = download(args.url, tmp)
            r = subprocess.run([bins.ffmpeg(), "-y", "-v", "error", "-ss", f"{a:.3f}", "-i", whole,
                                "-t", f"{b - a:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                                "-movflags", "+faststart", final], capture_output=True, text=True)
            if r.returncode != 0:
                raise YTError("Cutting the clip failed:\n" + r.stderr[-1500:])
    if not os.path.exists(final):
        raise YTError("yt-dlp reported success but no clip was written.")
    print(f"saved {final}  ({os.path.getsize(final) / 1048576:.1f}MB, {_hms(a)} to {_hms(b)})")
    print("Check it with: circle vid-sheet \"" + final + "\"")


_CUE = re.compile(r"(\d+:)?(\d+):(\d+\.\d+)\s+-->\s+")


def cmd_find(args):
    """Search the auto-captions for a phrase and print the moments it is said."""
    _need_tools()
    with tempfile.TemporaryDirectory(prefix="ytfind-") as tmp:
        _ytdlp(["--write-auto-subs", "--write-subs", "--sub-langs", f"{args.lang},{args.lang}-orig",
                "--sub-format", "vtt", "--skip-download", "-o", os.path.join(tmp, "subs"), args.url])
        files = [f for f in os.listdir(tmp) if f.endswith(".vtt")]
        if not files:
            raise YTError("No captions came back for that video.")
        with open(os.path.join(tmp, sorted(files)[0]), encoding="utf-8") as f:
            text = f.read()

    cues, start = [], None
    for line in text.splitlines():
        m = _CUE.match(line)
        if m:
            start = int((m.group(1) or "0:")[:-1]) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
            continue
        if start is not None and line.strip():
            clean = re.sub(r"<[^>]+>", "", line).strip()
            if clean and (not cues or cues[-1][1] != clean):
                cues.append((start, clean))

    needle = args.phrase.lower()
    hits, last = [], -99
    for t, line in cues:
        if needle in line.lower() and t - last > 5:
            hits.append((t, line))
            last = t
    if not hits:
        print(f"'{args.phrase}' is not in the captions. Auto-captions mishear names, so try a shorter word.")
        return
    for t, line in hits:
        print(f"{_hms(t):>12}  {line}")
    print(f"\n{len(hits)} moment(s). Pad a few seconds either side, then: "
          f"circle yt-clip <url> --from <start> --to <end>")


def register(sub):
    p = sub.add_parser("yt-setup", help="install or update yt-dlp and Deno (and ffmpeg on Windows) in ~/.circle/bin")
    p.add_argument("--ffmpeg", action="store_true", help="Windows: also fetch ffmpeg and ffprobe")
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("yt-get", help="download whole videos as MP4 (YouTube, TikTok, Instagram reels)")
    p.add_argument("url", nargs="+")
    p.add_argument("--out", default=DEFAULT_OUT, help="folder, default ~/Downloads/YouTube")
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("yt-clip", help="download only one section of a video")
    p.add_argument("url")
    p.add_argument("--from", dest="start", required=True, help="start, e.g. 1:20 or 80")
    p.add_argument("--to", dest="end", required=True, help="end, e.g. 2:05")
    p.add_argument("--out", default=DEFAULT_OUT)
    p.set_defaults(func=cmd_clip)

    p = sub.add_parser("yt-find", help="find when a phrase is said, from the auto-captions")
    p.add_argument("url")
    p.add_argument("phrase")
    p.add_argument("--lang", default="en")
    p.set_defaults(func=cmd_find)
