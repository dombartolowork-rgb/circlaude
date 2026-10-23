"""Generate and edit images with Google's Nano Banana models (Gemini image).

    circle img-gen "prompt" -o out.png                      text to image
    circle img-gen "prompt" --ref blockout.png --ref a.jpg  guided by reference images, in order
    circle img-gen "prompt" --model pro --size 2K --aspect 16:9
    circle img-models                                       which image models this key can use

The key is Circle's, billed to the agency: GEMINI_API_KEY, or the file
~/.circle/gemini_key. It is never printed. Only use a key from a Google Cloud
project with billing on: the free tier lets Google train on what you send.

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

API = "https://generativelanguage.googleapis.com/v1beta"
KEY_FILE = os.path.join(os.path.expanduser("~"), ".circle", "gemini_key")
LOG_FILE = os.path.join(os.path.expanduser("~"), ".circle", "image_log.csv")

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
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    if not k and os.path.isfile(KEY_FILE):
        with open(KEY_FILE, encoding="utf-8") as f:
            k = f.read().strip()
    if not k:
        raise ImageError("No image key. Save Circle's Gemini API key to ~/.circle/gemini_key "
                         "(or set GEMINI_API_KEY). See the image-generation skill for how to get one.")
    return k


def _call(method, path, body=None):
    req = urllib.request.Request(API + path, method=method,
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
            detail += "\nThat model id may have changed: run `circle img-models` and pass --model <id>."
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
    data = _call("GET", "/models?pageSize=1000")
    rows = [m for m in data.get("models", []) if "image" in m.get("name", "")]
    if not rows:
        print("No image models visible to this key.")
    for m in rows:
        print(f"{m['name'].split('/')[-1]:40} {m.get('displayName', '')}")


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

    sub.add_parser("img-models", help="list the image models Circle's key can use").set_defaults(func=cmd_models)
