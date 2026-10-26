"""Vimeo, through the API rather than the browser, on Circle's Vimeo account.

    circle vi-setup                           save Circle's Vimeo key (or --key-stdin, --clipboard)
    circle vi-whoami                          which Vimeo account the key opens
    circle vi-list [--query NAME]             videos, newest first
    circle vi-video <id>                      one video: duration, privacy, link, review link
    circle vi-upload <file> --name "..."      upload, Unlisted by default, with a review link
    circle vi-comments <id>                   review comments on a video

The key is Circle's, a personal access token on the agency's Vimeo account, the same
for everyone who has it: VIMEO_TOKEN, or the file ~/.circle/vimeo_token.json. Like the
image key it may be pasted in chat, but it must never go into this repo, and it is
never printed.

Privacy is set when the video is created, never afterwards, so an upload is never
briefly public. A finished upload is not a playable video yet: wait for vi-video to
show a duration before sending anyone the link.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.vimeo.com"
CIRCLE_DIR = os.path.join(os.path.expanduser("~"), ".circle")
TOKEN_FILE = os.path.join(CIRCLE_DIR, "vimeo_token.json")


class VimeoError(RuntimeError):
    pass


def _token():
    t = os.environ.get("VIMEO_TOKEN", "").strip()
    if not t and os.path.isfile(TOKEN_FILE):
        with open(TOKEN_FILE, encoding="utf-8") as f:
            t = (json.load(f).get("access_token") or "").strip()
    if not t:
        raise VimeoError("No Vimeo key. Get Circle's Vimeo key from Dom and save it with "
                         "`circle vi-setup` (or run /orbit:onboard).")
    return t


def call(path, params=None, method="GET", body=None):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "bearer " + _token())
    req.add_header("Accept", "application/vnd.vimeo.*+json;version=3.4")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"error": raw.decode("utf-8", "replace")[:300]}


def _check(st, d, ok=(200,)):
    if st == 401:
        raise VimeoError("Vimeo did not accept the key. Save it again with `circle vi-setup`.")
    if st not in ok:
        raise VimeoError(f"Vimeo said {st}: {str(d)[:200]}")


def _dur(sec):
    sec = int(sec or 0)
    return f"{sec // 60}m{sec % 60:02d}s"


def _clipboard():
    import subprocess
    cmd = ["pbpaste"] if sys.platform == "darwin" else \
        ["powershell", "-NoProfile", "-Command", "Get-Clipboard"]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def cmd_setup(args):
    import getpass
    if args.key_stdin:
        key = "".join(sys.stdin.read().split())
    elif sys.stdin.isatty() and not args.clipboard:
        key = getpass.getpass("Paste Circle's Vimeo key (it will not show): ").strip()
    else:
        # Claude's ! prompt cannot take typed input, so read the copied key instead
        key = "".join(_clipboard().split())
    if not key:
        raise VimeoError("No key entered, nothing saved.")
    if not 20 <= len(key) <= 100 or not key.isalnum():
        raise VimeoError("That does not look like the Vimeo key. Nothing saved.")
    os.makedirs(CIRCLE_DIR, exist_ok=True)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump({"access_token": key}, f)
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass
    st, me = call("/me")
    if st != 200:
        raise VimeoError(f"Saved to {TOKEN_FILE}, but Vimeo did not accept it ({st}). "
                         "It may have been copied short.")
    print(f"Saved. Key in {TOKEN_FILE}, opens the {me.get('name')} Vimeo account.")


def cmd_whoami(args):
    st, me = call("/me")
    _check(st, me)
    print("name:   ", me.get("name"))
    print("account:", me.get("account"))
    print("videos: ", (me.get("metadata", {}).get("connections", {}).get("videos", {}) or {}).get("total"))


def cmd_list(args):
    params = {"per_page": args.limit, "fields": "uri,name,duration,created_time,privacy,link,status"}
    if args.query:
        params["query"] = args.query
    st, d = call("/me/videos", params)
    _check(st, d)
    for v in d.get("data", []):
        vid = (v.get("uri") or "").rsplit("/", 1)[-1]
        print(f"[{vid}] {_dur(v.get('duration')):>7}  {v.get('created_time', '')[:10]}  "
              f"{(v.get('privacy') or {}).get('view', '?'):9} {v.get('name', '')[:58]}")
    total = d.get("total")
    if total is not None:
        print(f"\n{len(d.get('data', []))} shown of {total}")


def cmd_video(args):
    st, v = call(f"/videos/{args.id}", {"fields":
        "uri,name,duration,created_time,privacy,link,review_page,status,width,height,"
        "transcode.status,is_playable"})
    _check(st, v)
    print("name:     ", v.get("name"))
    print("duration: ", _dur(v.get("duration")), f"({v.get('duration')}s)")
    print("size:     ", f"{v.get('width')}x{v.get('height')}")
    print("created:  ", (v.get("created_time") or "")[:16])
    print("privacy:  ", (v.get("privacy") or {}).get("view"))
    print("status:   ", v.get("status"), "| transcode", (v.get("transcode") or {}).get("status"),
          "| playable", v.get("is_playable"))
    print("link:     ", v.get("link"))
    rp = (v.get("review_page") or {}).get("link")
    if rp:
        print("review:   ", rp)


def cmd_upload(args):
    """Upload a local file with tus, privacy set at creation, resuming after drops."""
    path = os.path.expanduser(args.file)
    if not os.path.isfile(path):
        raise VimeoError(f"No such file: {path}")
    size = os.path.getsize(path)
    name = args.name or os.path.splitext(os.path.basename(path))[0]

    body = {
        "upload": {"approach": "tus", "size": str(size)},
        "name": name,
        "privacy": {"view": args.privacy, "embed": "whitelist", "download": True},
    }
    if args.description:
        body["description"] = args.description
    st, v = call("/me/videos", method="POST", body=body)
    _check(st, v, ok=(200, 201))
    link = (v.get("upload") or {}).get("upload_link")
    vid = (v.get("uri") or "").rsplit("/", 1)[-1]
    if not link:
        raise VimeoError(f"No upload link came back: {str(v)[:300]}")
    print(f"created [{vid}] {name}, uploading {size / 1048576:.0f}MB", flush=True)

    chunk = 8 * 1024 * 1024
    sent = 0
    fails = 0
    with open(path, "rb") as fh:
        while sent < size:
            # Vimeo can accept only part of a chunk. Always read from the offset
            # it reports, or every later byte lands in the wrong place: the
            # upload still reaches full size, then fails verification.
            fh.seek(sent)
            data = fh.read(chunk)
            req = urllib.request.Request(link, data=data, method="PATCH")
            req.add_header("Tus-Resumable", "1.0.0")
            req.add_header("Upload-Offset", str(sent))
            req.add_header("Content-Type", "application/offset+octet-stream")
            try:
                with urllib.request.urlopen(req, timeout=600) as r:
                    sent = int(r.headers.get("Upload-Offset", sent + len(data)))
                fails = 0
            except (urllib.error.URLError, OSError) as e:
                # a dropped connection: ask Vimeo where it got to and resume
                fails += 1
                if fails > 20:
                    raise VimeoError(f"Upload failed at {sent} of {size} bytes: {e}")
                time.sleep(min(60, 5 * fails))
                head = urllib.request.Request(link, method="HEAD")
                head.add_header("Tus-Resumable", "1.0.0")
                try:
                    with urllib.request.urlopen(head, timeout=60) as r:
                        sent = int(r.headers.get("Upload-Offset", sent))
                except (urllib.error.URLError, OSError):
                    pass
                sys.stderr.write(f"\n  connection dropped, resuming at {sent}\n")
            sys.stderr.write(f"\r  {sent * 100 // size}%")
    sys.stderr.write("\r  done   \n")

    if args.review:
        # review_page is on by default for pro accounts, but say so rather than assume
        st, _ = call(f"/videos/{vid}", method="PATCH", body={"review_page": {"active": True}})
        if st not in (200, 204):
            print("Note: could not confirm the review page is on, check in Vimeo.")
    st, v = call(f"/videos/{vid}", {"fields": "link,review_page,privacy,transcode.status"})
    print("\nlink:     ", v.get("link") or f"https://vimeo.com/{vid}")
    rp = (v.get("review_page") or {}).get("link")
    if rp:
        print("review:   ", rp)
    print("privacy:  ", (v.get("privacy") or {}).get("view"))
    print("transcode:", (v.get("transcode") or {}).get("status"),
          f"(not playable until this is complete: check with `circle vi-video {vid}`)")


def cmd_comments(args):
    st, d = call(f"/videos/{args.id}/comments", {"per_page": 100})
    _check(st, d)
    rows = d.get("data", [])
    if not rows:
        print("No comments.")
        return
    for c in rows:
        who = (c.get("user") or {}).get("name", "?")
        when = (c.get("created_on") or "")[:16].replace("T", " ")
        print(f"- {when}  {who}: {c.get('text', '')}")
    print(f"\n{len(rows)} comment(s)")


def register(sub):
    p = sub.add_parser("vi-setup", help="save Circle's Vimeo key (copy the key first)")
    p.add_argument("--key-stdin", action="store_true", help="read the key from standard input")
    p.add_argument("--clipboard", action="store_true", help="take the key from the clipboard")
    p.set_defaults(func=cmd_setup)

    sub.add_parser("vi-whoami", help="which Vimeo account the key opens").set_defaults(func=cmd_whoami)

    p = sub.add_parser("vi-list", help="list videos on Circle's Vimeo, newest first")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--query", help="search by name")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("vi-video", help="one video: duration, privacy, link, review link")
    p.add_argument("id")
    p.set_defaults(func=cmd_video)

    p = sub.add_parser("vi-upload", help="upload a file to Circle's Vimeo, Unlisted, with a review link")
    p.add_argument("file")
    p.add_argument("--name", help="title in Vimeo, defaults to the filename")
    p.add_argument("--description")
    p.add_argument("--privacy", default="unlisted",
                   choices=["unlisted", "nobody", "anybody", "disable", "password"])
    p.add_argument("--no-review", dest="review", action="store_false",
                   help="do not force the review page on")
    p.set_defaults(func=cmd_upload, review=True)

    p = sub.add_parser("vi-comments", help="review comments on a video")
    p.add_argument("id")
    p.set_defaults(func=cmd_comments)
