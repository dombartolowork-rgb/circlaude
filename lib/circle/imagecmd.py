"""Generate and edit images with Google's Nano Banana models (Gemini image), on Vertex AI.

    circle img-gen "prompt" -o out.png                      text to image
    circle img-gen "prompt" --ref blockout.png --ref a.jpg  guided by reference images, in order
    circle img-gen "prompt" --model pro --size 2K --aspect 16:9
    circle img-models                                       the model short names
    circle img-setup --key-stdin < key.txt                  save Circle's Vertex key (or from the clipboard)

It goes through Vertex AI in Circle's Google Cloud project, never the Gemini app
or AI Studio: Vertex is the route that meets Circle's AI policy (enterprise data
terms, no training on inputs, admin controls). The key is Circle's, billed to
the agency: VERTEX_API_KEY, or the file ~/.circle/vertex_key, and the project id
is "vertex_project" in ~/.circle/config.json (orbit-images unless told otherwise).
Anyone at Circle may have the key; it must never go into this repo, and it is
never printed.

Every image is saved with its prompt beside it (out.txt), and each call is added
to ~/.circle/image_log.csv so spend can be checked against the Google bill.
"""
import base64
import csv
import datetime
import json
import mimetypes
import os
import urllib.error
import urllib.request

HOST = "https://aiplatform.googleapis.com/v1"
LOCATION = "global"   # the image models are served from global only
DEFAULT_PROJECT = "orbit-images"   # Circle's central Google Cloud project
CIRCLE_DIR = os.path.join(os.path.expanduser("~"), ".circle")
KEY_FILE = os.path.join(CIRCLE_DIR, "vertex_key")
CONFIG_FILE = os.path.join(CIRCLE_DIR, "config.json")
LOG_FILE = os.path.join(CIRCLE_DIR, "image_log.csv")

# Short names for the models. Anything else is passed through as a model id,
# so a newer model works without a code change: check `circle img-models`.
MODELS = {
    "2": "gemini-3.1-flash-image",   # Nano Banana 2: fast and cheap, the default
    "pro": "gemini-3-pro-image",     # Nano Banana Pro: best quality, about twice the price
    "1": "gemini-2.5-flash-image",   # the original Nano Banana
}
ASPECTS = ["1:1", "3:2", "2:3", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]


class ImageError(RuntimeError):
    pass


def _key():
    k = os.environ.get("VERTEX_API_KEY", "").strip()
    if not k and os.path.isfile(KEY_FILE):
        with open(KEY_FILE, encoding="utf-8") as f:
            k = f.read().strip()
    if not k:
        raise ImageError("No image key. Get Circle's image key from Dom and save it with "
                         "`circle img-setup` (or run /orbit:onboard).")
    return k


def _config():
    if not os.path.isfile(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def _project():
    return os.environ.get("VERTEX_PROJECT", "").strip() or _config().get("vertex_project") \
        or DEFAULT_PROJECT


def _call(method, path, body=None):
    url = f"{HOST}/projects/{_project()}/locations/{LOCATION}/publishers/google{path}"
    req = urllib.request.Request(url, method=method,
                                 data=json.dumps(body).encode("utf-8") if body is not None else None,
                                 headers={"x-goog-api-key": _key(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        try:
            detail = json.loads(detail)["error"]["message"]
        except (ValueError, KeyError, TypeError):
            detail = detail[:800]
        if e.code == 404:
            detail += ("\nThat model id may have changed: check Google's Vertex model list "
                       "and pass --model <id>.")
        elif e.code in (401, 403):
            detail += "\nCheck the key and project with `circle img-setup`, and that the Vertex AI API is on."
        raise ImageError(f"Google returned {e.code}: {detail}")


def _image_part(path):
    if not os.path.isfile(path):
        raise ImageError(f"No such image: {path}")
    mime = mimetypes.guess_type(path)[0] or "image/png"
    if not mime.startswith("image/"):
        raise ImageError(f"Not an image: {path}")
    with open(path, "rb") as f:
        return {"inline_data": {"mime_type": mime, "data": base64.b64encode(f.read()).decode("ascii")}}


def _log(model, size, aspect, refs, out):
    new = not os.path.isfile(LOG_FILE)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["when", "model", "size", "aspect", "refs", "file"])
        w.writerow([datetime.datetime.now().isoformat(timespec="seconds"), model, size, aspect, refs, out])


def cmd_gen(args):
    model = MODELS.get(args.model, args.model)
    if len(args.ref) > 10:
        raise ImageError("At most 10 reference images (Nano Banana Pro takes 6 objects reliably).")
    parts = [_image_part(p) for p in args.ref] + [{"text": args.prompt}]
    image_config = {"imageSize": args.size}
    if args.aspect:
        image_config["aspectRatio"] = args.aspect
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"], "imageConfig": image_config}}

    base, _ = os.path.splitext(args.out)
    saved = []
    for i in range(args.n):
        out = args.out if args.n == 1 else f"{base}_{i + 1}.png"
        data = _call("POST", f"/models/{model}:generateContent", body)
        images, notes = [], []
        for cand in data.get("candidates", []):
            for p in (cand.get("content") or {}).get("parts", []):
                blob = p.get("inlineData") or p.get("inline_data")
                if blob:
                    images.append(blob["data"])
                elif p.get("text") and not p.get("thought"):
                    notes.append(p["text"].strip())
        if not images:
            reason = (data.get("candidates") or [{}])[0].get("finishReason") or \
                (data.get("promptFeedback") or {}).get("blockReason") or "no image returned"
            raise ImageError(f"No image came back ({reason}). " + " ".join(notes)[:500])
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "wb") as f:
            f.write(base64.b64decode(images[-1]))
        with open(os.path.splitext(out)[0] + ".txt", "w", encoding="utf-8") as f:
            f.write(f"model: {model}\nsize: {args.size}\naspect: {args.aspect or 'from the first reference'}\n")
            f.write("refs (in order):\n" + "".join(f"  {i + 1}. {r}\n" for i, r in enumerate(args.ref)))
            f.write("\nprompt:\n" + args.prompt + "\n")
        _log(model, args.size, args.aspect, len(args.ref), out)
        saved.append(out)
        print(f"saved {out}")
        if notes:
            print("  model said:", " ".join(notes)[:300])
    return saved


def cmd_models(args):
    for short, model in MODELS.items():
        print(f"--model {short:5} {model}")
    print("Any other Vertex model id can be passed to --model, e.g. a newer Nano Banana.")


def _clipboard():
    import subprocess
    import sys
    cmd = ["pbpaste"] if sys.platform == "darwin" else \
        ["powershell", "-NoProfile", "-Command", "Get-Clipboard"]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def cmd_setup(args):
    import getpass
    import sys
    cfg = _config()
    project = args.project or cfg.get("vertex_project") or DEFAULT_PROJECT
    if args.key_stdin:
        key = "".join(sys.stdin.read().split())
        if not 30 <= len(key) <= 200:
            raise ImageError("That does not look like the image key. Nothing saved.")
    elif sys.stdin.isatty() and not args.clipboard:
        key = getpass.getpass("Paste Circle's Vertex key (it will not show): ").strip()
    else:
        # Claude's ! prompt cannot take typed input, so read the copied key instead
        key = "".join(_clipboard().split())
        if not 30 <= len(key) <= 200:
            raise ImageError("Copy the key first, then run this again. Nothing saved.")
    if not key:
        raise ImageError("No key entered, nothing saved.")
    os.makedirs(CIRCLE_DIR, exist_ok=True)
    cfg["vertex_project"] = project
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    with open(KEY_FILE, "w", encoding="utf-8") as f:
        f.write(key + "\n")
    try:
        os.chmod(KEY_FILE, 0o600)
    except OSError:
        pass
    print(f"Saved. Key in {KEY_FILE}, project {project} in {CONFIG_FILE}.")


def register(sub):
    p = sub.add_parser("img-gen", help="make or edit an image with Nano Banana (Gemini image)")
    p.add_argument("prompt")
    p.add_argument("--ref", action="append", default=[], metavar="IMAGE",
                   help="reference image, repeatable; the model sees them in this order")
    p.add_argument("--model", default="2", help="2 (Nano Banana 2, default), pro, 1, or a full model id")
    p.add_argument("--size", default="2K", choices=["1K", "2K", "4K"])
    p.add_argument("--aspect", choices=ASPECTS, help="default: follow the first reference, else square")
    p.add_argument("--n", type=int, default=1, help="how many takes (each is billed)")
    p.add_argument("-o", "--out", default="image.png")
    p.set_defaults(func=cmd_gen)

    sub.add_parser("img-models", help="the image model short names and their Vertex ids").set_defaults(func=cmd_models)
    p = sub.add_parser("img-setup", help="save Circle's Vertex key and project (copy the key first)")
    p.add_argument("--project", help=f"the Google Cloud project id (default {DEFAULT_PROJECT})")
    p.add_argument("--key-stdin", action="store_true", help="read the key from standard input")
    p.add_argument("--clipboard", action="store_true", help="take the key from the clipboard")
    p.set_defaults(func=cmd_setup)
