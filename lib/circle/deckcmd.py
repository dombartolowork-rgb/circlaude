"""PowerPoint decks, edited as the files they are, without breaking them.

    circle deck-text deck.pptx [--notes]            every slide in order: text, pictures, hidden
    circle deck-images deck.pptx --out dir          the pictures, named by slide
    circle deck-render deck.pptx --out dir          each slide as a PNG, exported by PowerPoint
    circle deck-pick deck.pptx --slides 4,9 -o new.pptx      keep only those slides
    circle deck-replace deck.pptx --slide 4 --old "x" --new "y" -o out.pptx
    circle deck-swap-image deck.pptx --slide 4 --image "Picture 3" --with new.jpg -o out.pptx
    circle deck-insert master.pptx new.pptx --after 12 -o merged.pptx
    circle deck-brand -o "New deck.pptx"           start a deck from Circle's brand master
    circle deck-layouts deck.pptx [--render dir]   the layouts, numbered, with their boxes
    circle deck-add-slide deck.pptx --layout 12 -o out.pptx
    circle deck-fill deck.pptx --slide 3 --box title --text "..." -o out.pptx

Why not python-pptx: Orbit is stdlib only, and more to the point, every part of a
shared master that these commands don't need to touch is copied byte for byte.
Re-saving a whole deck through a library rewrites parts the user never asked to
change (sections, hidden flags, custom XML), which is how a colleague's deck gets
"repaired" by PowerPoint or quietly loses something.

Slide numbers are the ones the user sees in PowerPoint (1-based, presentation
order, hidden slides included).
"""
import hashlib
import html
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

from . import bins
from .docxbuild import image_size

R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
SLIDE_T = R_NS + "/slide"
SLIDE_CT = "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"
EMU_CM = 360000


class DeckError(RuntimeError):
    pass


# ---------------------------------------------------------------- package

def _attrs(tag):
    return dict(re.findall(r'([\w:]+)="([^"]*)"', tag))


class Pkg:
    """A .pptx held in memory: part name -> bytes, with the original zip order."""

    def __init__(self, path):
        if not zipfile.is_zipfile(path):
            raise DeckError(f"{path} is not a .pptx (a .ppt or .key needs saving as .pptx first).")
        with zipfile.ZipFile(path) as z:
            self.infos = z.infolist()
            self.parts = {i.filename: z.read(i.filename) for i in self.infos}
        self.added = []
        if "ppt/presentation.xml" not in self.parts:
            raise DeckError(f"{path} has no presentation in it.")

    def text(self, name):
        return self.parts[name].decode("utf-8")

    def put(self, name, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        if name not in self.parts:
            self.added.append(name)
        self.parts[name] = data

    def drop(self, name):
        self.parts.pop(name, None)

    @staticmethod
    def rels_name(part):
        d, b = posixpath.split(part)
        return posixpath.join(d, "_rels", b + ".rels")

    def rels(self, part):
        rn = self.rels_name(part)
        if rn not in self.parts:
            return []
        return [_attrs(t) for t in re.findall(r"<Relationship\b[^>]*>", self.text(rn))]

    def set_rels(self, part, rels):
        body = "".join(
            "<Relationship " + " ".join(f'{k}="{v}"' for k, v in r.items()) + "/>" for r in rels)
        self.put(self.rels_name(part),
                 '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 + body + "</Relationships>")

    @staticmethod
    def resolve(part, target):
        if target.startswith("/"):
            return target[1:]
        return posixpath.normpath(posixpath.join(posixpath.dirname(part), target))

    @staticmethod
    def relative(part, target_part):
        return posixpath.relpath(target_part, posixpath.dirname(part))

    def slides(self):
        """[(sldId id, rId, slide part)] in presentation order."""
        pres = self.text("ppt/presentation.xml")
        rmap = {r["Id"]: self.resolve("ppt/presentation.xml", r["Target"])
                for r in self.rels("ppt/presentation.xml")}
        out = []
        for t in re.findall(r"<p:sldId\b[^>]*>", pres):
            a = _attrs(t)
            out.append((int(a["id"]), a["r:id"], rmap[a["r:id"]]))
        return out

    def content_type(self, part):
        ct = self.text("[Content_Types].xml")
        m = re.search(r'<Override\b[^>]*PartName="/%s"[^>]*>' % re.escape(part), ct)
        if m:
            return _attrs(m.group(0))["ContentType"]
        ext = part.rsplit(".", 1)[-1].lower()
        m = re.search(r'<Default\b[^>]*Extension="%s"[^>]*>' % re.escape(ext), ct, re.I)
        return _attrs(m.group(0))["ContentType"] if m else None

    def add_override(self, part, ctype):
        ct = self.text("[Content_Types].xml")
        if f'PartName="/{part}"' not in ct:
            ct = ct.replace("</Types>", f'<Override PartName="/{part}" ContentType="{ctype}"/></Types>')
            self.put("[Content_Types].xml", ct)

    def ensure_default(self, ext, ctype):
        ct = self.text("[Content_Types].xml")
        if not re.search(r'<Default\b[^>]*Extension="%s"' % re.escape(ext), ct, re.I):
            ct = ct.replace("<Override", f'<Default Extension="{ext}" ContentType="{ctype}"/><Override', 1)
            self.put("[Content_Types].xml", ct)

    def drop_override(self, part):
        ct = self.text("[Content_Types].xml")
        ct2 = re.sub(r'<Override\b[^>]*PartName="/%s"[^>]*/>' % re.escape(part), "", ct)
        if ct2 != ct:
            self.put("[Content_Types].xml", ct2)

    def free_name(self, part):
        """part if unused, else the same name with the next free number."""
        if part not in self.parts:
            return part
        d, b = posixpath.split(part)
        stem, ext = (b.rsplit(".", 1) + [""])[:2]
        stem = re.sub(r"\d+$", "", stem)
        n = 1
        while True:
            cand = posixpath.join(d, f"{stem}{n}.{ext}" if ext else f"{stem}{n}")
            if cand not in self.parts:
                return cand
            n += 1

    def save(self, path):
        tmp = path + ".tmp"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            seen = set()
            for i in self.infos:
                if i.filename in self.parts:
                    z.writestr(i, self.parts[i.filename])
                    seen.add(i.filename)
            for name in self.added:
                if name in self.parts and name not in seen:
                    z.writestr(name, self.parts[name])
                    seen.add(name)
        os.replace(tmp, path)
        return path


# ---------------------------------------------------------------- reading

def _paras(xml):
    out = []
    for p in re.findall(r"<a:p>.*?</a:p>|<a:p .*?</a:p>", xml, re.S):
        p = re.sub(r"<a:br\b[^>]*/>", "<a:t> / </a:t>", p)
        t = html.unescape("".join(re.findall(r"<a:t>([^<]*)</a:t>", p))).strip()
        if t:
            out.append(t)
    return out


def _layout_name(pkg, layout_part):
    m = re.search(r'<p:cSld\b[^>]*name="([^"]*)"', pkg.text(layout_part))
    return html.unescape(m.group(1)) if m else ""


def _rel_of(pkg, part, suffix):
    for r in pkg.rels(part):
        if r["Type"].endswith(suffix) and r.get("TargetMode") != "External":
            return pkg.resolve(part, r["Target"])
    return None


def _pictures(pkg, part):
    xml = pkg.text(part)
    rmap = {r["Id"]: r for r in pkg.rels(part)}
    out = []
    for pic in re.findall(r"<p:pic>.*?</p:pic>", xml, re.S):
        name = _attrs(re.search(r"<p:cNvPr\b[^>]*>", pic).group(0)).get("name", "")
        emb = re.search(r'r:embed="([^"]+)"', pic)
        ext = re.search(r'<a:ext cx="(\d+)" cy="(\d+)"', pic)
        target = None
        if emb and emb.group(1) in rmap:
            target = pkg.resolve(part, rmap[emb.group(1)]["Target"])
        out.append({"name": html.unescape(name), "rid": emb.group(1) if emb else None, "part": target,
                    "cx": int(ext.group(1)) if ext else 0, "cy": int(ext.group(2)) if ext else 0,
                    "xml": pic})
    return out


PH_RE = r"<p:ph\b[^>]*/>|<p:ph\b[^>]*>.*?</p:ph>"


def _ph_info(tag):
    a = _attrs(re.match(r"<p:ph\b[^>]*", tag).group(0) + ">")
    return a.get("type", "body"), a.get("idx", "0")


def _layout_geometry(pkg, layout):
    """{(type, idx): (cx, cy)} for the placeholders a layout defines."""
    out = {}
    for sp in re.findall(r"<p:sp>.*?</p:sp>", pkg.text(layout), re.S):
        ph = re.search(PH_RE, sp, re.S)
        ext = re.search(r'<a:ext cx="(\d+)" cy="(\d+)"', sp)
        if ph and ext:
            kind, idx = _ph_info(ph.group(0))
            out[(kind, idx)] = (int(ext.group(1)), int(ext.group(2)))
            out.setdefault(("idx", idx), out[(kind, idx)])
    return out


def _placeholders(pkg, part):
    """The layout boxes on a slide (title, body, picture...), and whether each is empty."""
    xml = pkg.text(part)
    lay = _rel_of(pkg, part, "/slideLayout")
    geo = _layout_geometry(pkg, lay) if lay else {}
    out = []
    for sp in re.findall(r"<p:sp>.*?</p:sp>", xml, re.S):
        ph = re.search(PH_RE, sp, re.S)
        if not ph:
            continue
        kind, idx = _ph_info(ph.group(0))
        ext = re.search(r'<a:ext cx="(\d+)" cy="(\d+)"', sp)
        cx, cy = (int(ext.group(1)), int(ext.group(2))) if ext else geo.get((kind, idx), geo.get(("idx", idx), (0, 0)))
        name = _attrs(re.search(r"<p:cNvPr\b[^>]*>", sp).group(0)).get("name", "")
        out.append({"name": html.unescape(name), "kind": kind, "idx": idx, "ph": ph.group(0),
                    "empty": "<a:t>" not in sp, "xml": sp, "cx": cx, "cy": cy})
    return out


def _slide_no(pkg, n):
    sl = pkg.slides()
    if not 1 <= n <= len(sl):
        raise DeckError(f"There is no slide {n}: the deck has {len(sl)}.")
    return sl[n - 1]


def _parse_slides(spec, count):
    if spec == "none":
        return []
    if not spec:
        return list(range(1, count + 1))
    out = []
    for bit in spec.split(","):
        bit = bit.strip()
        if "-" in bit:
            a, b = bit.split("-")
            out.extend(range(int(a), int(b) + 1))
        elif bit:
            out.append(int(bit))
    bad = [n for n in out if not 1 <= n <= count]
    if bad:
        raise DeckError(f"No slide {bad[0]}: the deck has {count}.")
    return out


def cmd_text(a):
    pkg = Pkg(a.deck)
    sl = pkg.slides()
    for n in _parse_slides(a.slides, len(sl)):
        _, _, part = sl[n - 1]
        xml = pkg.text(part)
        hidden = bool(re.search(r'<p:sld\b[^>]*\bshow="0"', xml))
        lay = _rel_of(pkg, part, "/slideLayout")
        print(f"=== {n}{' (HIDDEN)' if hidden else ''}  [{_layout_name(pkg, lay) if lay else '?'}]")
        for t in _paras(xml):
            if t != "\u2039#\u203a":
                print("  " + t)
        for ph in _placeholders(pkg, part):
            if ph["empty"] and ph["kind"] != "sldNum":
                size = f" {ph['cx'] / EMU_CM:.1f}x{ph['cy'] / EMU_CM:.1f}cm" if ph["cx"] else ""
                print(f"  [empty {'picture' if ph['kind'] == 'pic' else ph['kind']} box \"{ph['name']}\"{size}]")
        for p in _pictures(pkg, part):
            print(f"  [picture \"{p['name']}\" {posixpath.basename(p['part'] or '?')} "
                  f"{p['cx'] / EMU_CM:.1f}x{p['cy'] / EMU_CM:.1f}cm]")
        if a.notes:
            notes = _rel_of(pkg, part, "/notesSlide")
            if notes:
                nt = [t for t in _paras(pkg.text(notes)) if not t.isdigit()]
                if nt:
                    print("  NOTES: " + " / ".join(nt))


def cmd_images(a):
    pkg = Pkg(a.deck)
    sl = pkg.slides()
    os.makedirs(a.out, exist_ok=True)
    n_out = 0
    for n in _parse_slides(a.slides, len(sl)):
        for k, p in enumerate(_pictures(pkg, sl[n - 1][2]), 1):
            if not p["part"] or p["part"] not in pkg.parts:
                continue
            ext = p["part"].rsplit(".", 1)[-1]
            dst = os.path.join(a.out, f"s{n:02d}-{k}.{ext}")
            with open(dst, "wb") as f:
                f.write(pkg.parts[p["part"]])
            n_out += 1
    print(f"{n_out} picture(s) written to {a.out}")


# ---------------------------------------------------------------- rendering

def render(deck, out, width=1600):
    """Each slide as out/slideNN.png, exported by PowerPoint itself, so fonts and
    layouts are exactly what the user will see."""
    deck = os.path.abspath(deck)
    out = os.path.abspath(out)
    os.makedirs(out, exist_ok=True)
    if bins.WINDOWS:
        ps = r"""
$ErrorActionPreference = 'Stop'
$app = New-Object -ComObject PowerPoint.Application
$p = $app.Presentations.Open('%s', -1, 0, 0)
$w = %d; $h = [int]($w * $p.PageSetup.SlideHeight / $p.PageSetup.SlideWidth)
for ($i = 1; $i -le $p.Slides.Count; $i++) {
  $p.Slides.Item($i).Export(('%s\slide{0:D2}.png' -f $i), 'PNG', $w, $h)
}
$p.Close()
if ($app.Presentations.Count -eq 0) { $app.Quit() }
""" % (deck.replace("'", "''"), width, out.replace("'", "''"))
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           capture_output=True, text=True)
        if r.returncode:
            raise DeckError("PowerPoint could not export the slides: " + (r.stderr or r.stdout).strip()[-400:])
    elif sys.platform == "darwin":
        if not os.path.isdir("/Applications/Microsoft PowerPoint.app"):
            raise DeckError("PowerPoint is not installed, so the slides can't be rendered.")
        # PowerPoint for Mac is sandboxed: work inside its own container folder.
        box = os.path.expanduser("~/Library/Containers/com.microsoft.Powerpoint/Data/orbit-render")
        shutil.rmtree(box, ignore_errors=True)
        os.makedirs(box)
        src = os.path.join(box, "deck.pptx")
        shutil.copy(deck, src)
        pdf = os.path.join(box, "deck.pdf")
        # PNG export doesn't work from AppleScript on the Mac; PDF does, and the
        # delays matter (PowerPoint returns before the file is open).
        script = f'''
tell application "Microsoft PowerPoint"
  open (POSIX file "{src}")
  delay 4
  set ap to active presentation
  save ap in (POSIX file "{pdf}") as save as PDF
  delay 2
  close ap saving no
end tell'''
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=600)
        if r.returncode or not os.path.isfile(pdf):
            raise DeckError("PowerPoint could not export the slides: " + (r.stderr.strip()[-400:] or "no PDF written"))
        jxa = """
ObjC.import('PDFKit'); ObjC.import('AppKit');
function run(argv) {
  const doc = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0]));
  const w = parseInt(argv[2]); let n = 0;
  for (let i = 0; i < doc.pageCount; i++) {
    const pg = doc.pageAtIndex(i), b = pg.boundsForBox(0);
    const h = Math.round(w * b.size.height / b.size.width);
    const img = pg.thumbnailOfSizeForBox($.NSMakeSize(w, h), 0);
    const rep = $.NSBitmapImageRep.imageRepWithData(img.TIFFRepresentation);
    const png = rep.representationUsingTypeProperties(4, $({}));
    const name = argv[1] + '/slide' + String(i + 1).padStart(2, '0') + '.png';
    png.writeToFileAtomically(name, true); n++;
  }
  return n;
}"""
        r = subprocess.run(["osascript", "-l", "JavaScript", "-e", jxa, pdf, out, str(width)],
                           capture_output=True, text=True)
        if r.returncode:
            raise DeckError("Could not turn the PDF into images: " + r.stderr.strip()[-400:])
        shutil.rmtree(box, ignore_errors=True)
    else:
        raise DeckError("Rendering needs PowerPoint (Windows or Mac).")
    return sorted(os.path.join(out, f) for f in os.listdir(out) if f.endswith(".png"))


def cmd_render(a):
    files = render(a.deck, a.out, a.width)
    print(f"{len(files)} slide image(s) in {a.out}")


# ---------------------------------------------------------------- changing

def _check_out(a):
    out = a.out
    if os.path.abspath(out) == os.path.abspath(a.deck) and not getattr(a, "in_place", False):
        raise DeckError("Write to a new file (-o), so the original is there to compare against.")
    return out


def _gc(pkg):
    """Drop parts nothing reachable points at any more (the media, notes and charts of
    removed slides). Walks from the package root, so a removed slide and its notes,
    which point at each other, still go."""
    seen, todo = set(), []
    for r in [_attrs(t) for t in re.findall(r"<Relationship\b[^>]*>", pkg.text("_rels/.rels"))]:
        todo.append(r["Target"].lstrip("/"))
    while todo:
        part = todo.pop()
        if part in seen or part not in pkg.parts:
            continue
        seen.add(part)
        for r in pkg.rels(part):
            if r.get("TargetMode") != "External":
                todo.append(pkg.resolve(part, r["Target"]))
    for n in list(pkg.parts):
        if (not n.endswith(".rels") and n not in seen
                and n.startswith(("ppt/media/", "ppt/notesSlides/", "ppt/slides/", "ppt/charts/",
                                  "ppt/embeddings/", "ppt/diagrams/", "ppt/comments/", "ppt/tags/"))):
            pkg.drop(n)
            pkg.drop(pkg.rels_name(n))
            pkg.drop_override(n)


def cmd_pick(a):
    pkg = Pkg(a.deck)
    sl = pkg.slides()
    keep = set(_parse_slides(a.slides, len(sl)))
    pres = pkg.text("ppt/presentation.xml")
    prels = pkg.rels("ppt/presentation.xml")
    gone_ids, gone_rids = set(), set()
    for n, (sid, rid, part) in enumerate(sl, 1):
        if n not in keep:
            gone_ids.add(sid)
            gone_rids.add(rid)
    pres = re.sub(r'<p:sldId\b[^>]*r:id="(rId\d+)"[^>]*/>',
                  lambda m: "" if m.group(1) in gone_rids else m.group(0), pres)
    pres = re.sub(r'<p14:sldId id="(\d+)"\s*/>',
                  lambda m: "" if int(m.group(1)) in gone_ids else m.group(0), pres)
    pres = re.sub(r"<p:sldIdLst>\s*</p:sldIdLst>", "", pres)
    pkg.put("ppt/presentation.xml", pres)
    pkg.set_rels("ppt/presentation.xml", [r for r in prels if r["Id"] not in gone_rids])
    _gc(pkg)
    out = _check_out(a)
    pkg.save(out)
    print(f"Kept slide(s) {', '.join(str(n) for n in sorted(keep)) or 'none (layouts only)'} of {len(sl)}: {out}")


def cmd_replace(a):
    pkg = Pkg(a.deck)
    sl = pkg.slides()
    targets = _parse_slides(a.slide, len(sl)) if a.slide else list(range(1, len(sl) + 1))
    old_x = html.escape(a.old, quote=False)
    new_x = html.escape(a.new, quote=False)
    hits, spans = 0, []
    for n in targets:
        part = sl[n - 1][2]
        xml = pkg.text(part)
        count = 0

        def sub(m):
            nonlocal count
            c = m.group(1).count(old_x)
            count += c
            return "<a:t>" + m.group(1).replace(old_x, new_x) + "</a:t>"
        xml2 = re.sub(r"<a:t>([^<]*)</a:t>", sub, xml)
        if count:
            pkg.put(part, xml2)
            hits += count
            print(f"slide {n}: {count} replaced")
        elif any(a.old in p for p in _paras(xml)):
            spans.append(n)
    if not hits:
        if spans:
            raise DeckError(
                f"Found on slide(s) {spans}, but split across formatting runs, so it can't be swapped "
                "safely in one go. Replace a shorter piece that sits in one run, or edit it in PowerPoint.")
        raise DeckError("Not found. Check the exact text with deck-text (curly quotes and apostrophes count).")
    if hits > 1 and not a.all:
        raise DeckError(f"Found {hits} times. Narrow it with --slide, or pass --all to change every one.")
    out = _check_out(a)
    pkg.save(out)
    print(f"Saved {out}")


def _cover_crop(img_w, img_h, frame_w, frame_h):
    """srcRect (l, t, r, b in 1/1000 %) that fills the frame without stretching."""
    if not (img_w and img_h and frame_w and frame_h):
        return None
    ir, fr = img_w / img_h, frame_w / frame_h
    if abs(ir - fr) / fr < 0.01:
        return None
    if ir > fr:      # too wide: trim the sides
        cut = (1 - fr / ir) / 2
        return (int(cut * 100000), 0, int(cut * 100000), 0)
    cut = (1 - ir / fr) / 2
    return (0, int(cut * 100000), 0, int(cut * 100000))


def cmd_swap_image(a):
    pkg = Pkg(a.deck)
    _, _, part = _slide_no(pkg, a.slide)
    pics = _pictures(pkg, part)
    hit = [p for p in pics if p["name"] == a.image or posixpath.basename(p["part"] or "") == a.image]
    if not hit:   # an empty picture box from the layout
        for ph in _placeholders(pkg, part):
            if ph["kind"] == "pic" and ph["name"] == a.image:
                cid = _attrs(re.search(r"<p:cNvPr\b[^>]*>", ph["xml"]).group(0)).get("id", "2")
                pic_xml = (f'<p:pic><p:nvPicPr><p:cNvPr id="{cid}" name="{html.escape(ph["name"])}"/>'
                           '<p:cNvPicPr><a:picLocks noGrp="1" noChangeAspect="1"/></p:cNvPicPr>'
                           f'<p:nvPr>{ph["ph"]}</p:nvPr></p:nvPicPr><p:blipFill><a:blip r:embed="rIdNEW"/>'
                           '<a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr/></p:pic>')
                pkg.put(part, pkg.text(part).replace(ph["xml"], pic_xml, 1))
                hit = [{"name": ph["name"], "rid": "rIdNEW", "part": None, "cx": ph["cx"], "cy": ph["cy"],
                        "xml": pic_xml}]
                break
    if len(hit) != 1:
        boxes = [ph["name"] for ph in _placeholders(pkg, part) if ph["kind"] == "pic" and ph["empty"]]
        names = ", ".join(f'"{n}"' for n in [p["name"] for p in pics] + boxes) or "none"
        raise DeckError(f"{'No' if not hit else 'More than one'} picture called {a.image!r} on slide "
                        f"{a.slide}. Pictures there: {names}.")
    p = hit[0]
    with open(a.with_, "rb") as f:
        data = f.read()
    ext = "png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "jpeg" if data[:2] == b"\xff\xd8" else None
    if not ext:
        raise DeckError("The new picture must be a PNG or a JPEG.")
    iw, ih = image_size(data)
    newpart = pkg.free_name(f"ppt/media/image1.{ext}")
    pkg.put(newpart, data)
    pkg.ensure_default(ext, "image/png" if ext == "png" else "image/jpeg")
    rels = pkg.rels(part)
    ids = {r["Id"] for r in rels}
    n = 1
    while f"rId{n}" in ids:
        n += 1
    rid = f"rId{n}"
    rels.append({"Id": rid, "Type": R_NS + "/image", "Target": pkg.relative(part, newpart)})
    pkg.set_rels(part, rels)
    pic = p["xml"]
    new_pic = pic.replace(f'r:embed="{p["rid"]}"', f'r:embed="{rid}"', 1)
    new_pic = re.sub(r"<a:srcRect\b[^>]*/>|<a:srcRect\b[^>]*>.*?</a:srcRect>", "", new_pic, flags=re.S)
    crop = None if a.stretch else _cover_crop(iw, ih, p["cx"], p["cy"])
    if crop:
        new_pic = re.sub(r"(<a:blip\b.*?(?:/>|</a:blip>))",
                         lambda m: m.group(1) + '<a:srcRect l="%d" t="%d" r="%d" b="%d"/>' % crop,
                         new_pic, count=1, flags=re.S)
    xml = pkg.text(part).replace(pic, new_pic, 1)
    pkg.put(part, xml)
    _gc(pkg)
    out = _check_out(a)
    pkg.save(out)
    note = " (cropped to fill the frame, centred)" if crop else ""
    print(f"Swapped \"{p['name']}\" on slide {a.slide}{note}: {out}")


# ---------------------------------------------------------------- inserting

def _place(pres, dsl, new_entries, after):
    """Put new (sldId, rId) entries into presentation.xml after slide `after`
    (0 = at the start), and into the same PowerPoint section as that slide."""
    new_xml = "".join(f'<p:sldId id="{s}" r:id="{r}"/>' for s, r in new_entries)
    tags = list(re.finditer(r"<p:sldId\b[^>]*/>", pres))
    if tags:
        pos = tags[0].start() if after == 0 else tags[after - 1].end()
        pres = pres[:pos] + new_xml + pres[pos:]
    elif re.search(r"<p:sldIdLst\s*/>", pres):
        pres = re.sub(r"<p:sldIdLst\s*/>", "<p:sldIdLst>" + new_xml + "</p:sldIdLst>", pres, count=1)
    elif "<p:sldIdLst>" in pres:
        pres = pres.replace("<p:sldIdLst>", "<p:sldIdLst>" + new_xml, 1)
    else:   # the list sits just before the slide size
        pres = pres.replace("<p:sldSz", "<p:sldIdLst>" + new_xml + "</p:sldIdLst><p:sldSz", 1)
    if "<p14:sectionLst" in pres:
        sec_xml = "".join(f'<p14:sldId id="{s}"/>' for s, _ in new_entries)
        anchor = dsl[after - 1][0] if after else (dsl[0][0] if dsl else None)
        m = re.search(r'<p14:sldId id="%d"\s*/>' % anchor, pres) if anchor else None
        if m and after:
            pres = pres[:m.end()] + sec_xml + pres[m.end():]
        elif m:
            pres = pres[:m.start()] + sec_xml + pres[m.start():]
        else:   # no slides yet: the first section
            m = re.search(r"<p14:sldIdLst\s*/>|<p14:sldIdLst>", pres)
            if m:
                pres = pres[:m.start()] + "<p14:sldIdLst>" + sec_xml + (
                    "</p14:sldIdLst>" if m.group(0).endswith("/>") else "") + pres[m.end():]
    return pres



DROP_REL = ("/notesSlide", "comments", "/commentAuthors")


def _copy_part(src, dst, part, memo, media_hash):
    """Copy one part (and everything it relates to) from src into dst. Returns the new name."""
    if part in memo:
        return memo[part]
    data = src.parts[part]
    if part.startswith("ppt/media/"):
        h = hashlib.sha1(data).hexdigest()
        if h in media_hash:
            memo[part] = media_hash[h]
            return media_hash[h]
    new = dst.free_name(part)
    memo[part] = new
    ctype = src.content_type(part)
    dst.put(new, data)
    if part.startswith("ppt/media/"):
        media_hash[hashlib.sha1(data).hexdigest()] = new
    ext = new.rsplit(".", 1)[-1]
    if ctype:
        src_ct = src.text("[Content_Types].xml")
        if f'PartName="/{part}"' in src_ct:
            dst.add_override(new, ctype)
        else:
            dst.ensure_default(ext, ctype)
    rels = []
    for r in src.rels(part):
        r = dict(r)
        if r.get("TargetMode") == "External":
            rels.append(r)
            continue
        if any(k in r["Type"] for k in DROP_REL):
            continue
        tgt = src.resolve(part, r["Target"])
        if r["Type"] == SLIDE_T or tgt not in src.parts:
            raise DeckError(f"{part} links to {r['Target']}, which can't be carried across. "
                            "Remove that link in PowerPoint first.")
        r["Target"] = dst.relative(new, _copy_part(src, dst, tgt, memo, media_hash))
        rels.append(r)
    if rels or src.rels_name(part) in src.parts:
        dst.set_rels(new, rels)
    return new


def insert(master_path, src_path, out, after=None, after_text=None, slides=None, allow_dup=False):
    dst = Pkg(master_path)
    src = Pkg(src_path)
    dsl = dst.slides()
    ssl = src.slides()
    pick = _parse_slides(slides, len(ssl))

    # where: after slide N (0 = at the start), after the slide holding some text, or at the end
    if after_text:
        hits = [i for i, (_, _, p) in enumerate(dsl, 1) if after_text in " ".join(_paras(dst.text(p)))]
        if len(hits) != 1:
            raise DeckError(f"{'No' if not hits else str(len(hits))} slide(s) in the master contain "
                            f"{after_text!r}; it needs exactly one.")
        after = hits[0]
    if after is None:
        after = len(dsl)
    if not 0 <= after <= len(dsl):
        raise DeckError(f"--after must be 0 to {len(dsl)}.")

    # layouts by name, so new slides use the master's own
    layouts = {}
    for name in dst.parts:
        if re.match(r"ppt/slideLayouts/slideLayout\d+\.xml$", name):
            layouts.setdefault(_layout_name(dst, name), name)

    existing = {" ".join(_paras(dst.text(p))) for _, _, p in dsl}
    media_hash = {hashlib.sha1(d).hexdigest(): n for n, d in dst.parts.items() if n.startswith("ppt/media/")}
    pres = dst.text("ppt/presentation.xml")
    prels = dst.rels("ppt/presentation.xml")
    rid_n = max([int(r["Id"][3:]) for r in prels if r["Id"][3:].isdigit()] + [0])
    sid = max([s for s, _, _ in dsl] + [255])
    new_entries = []
    for n in pick:
        part = ssl[n - 1][2]
        text = " ".join(_paras(src.text(part)))
        if text and text in existing and not allow_dup:
            raise DeckError(f"Slide {n} of {src_path} is already in the master (same text). "
                            "Pass --allow-duplicate if that's intended.")
        lay_src = _rel_of(src, part, "/slideLayout")
        lay_name = _layout_name(src, lay_src) if lay_src else ""
        if lay_name not in layouts:
            raise DeckError(f"Slide {n} uses the layout {lay_name!r}, which the master doesn't have. "
                            f"The master's layouts: {', '.join(sorted(layouts))}. Build new slides from a "
                            "deck-pick of the master itself so the layouts match.")
        new_part = dst.free_name("ppt/slides/slide1.xml")
        dst.put(new_part, src.parts[part])
        dst.add_override(new_part, SLIDE_CT)
        memo = {}
        rels = []
        for r in src.rels(part):
            r = dict(r)
            if r.get("TargetMode") == "External":
                rels.append(r)
            elif r["Type"].endswith("/slideLayout"):
                r["Target"] = dst.relative(new_part, layouts[lay_name])
                rels.append(r)
            elif any(k in r["Type"] for k in DROP_REL):
                continue
            else:
                tgt = src.resolve(part, r["Target"])
                if r["Type"] == SLIDE_T or tgt not in src.parts:
                    raise DeckError(f"Slide {n} links to {r['Target']}, which can't be carried across. "
                                    "Remove that link in PowerPoint first.")
                r["Target"] = dst.relative(new_part, _copy_part(src, dst, tgt, memo, media_hash))
                rels.append(r)
        dst.set_rels(new_part, rels)
        rid_n += 1
        sid += 1
        prels.append({"Id": f"rId{rid_n}", "Type": SLIDE_T, "Target": dst.relative("ppt/presentation.xml", new_part)})
        new_entries.append((sid, f"rId{rid_n}"))

    dst.set_rels("ppt/presentation.xml", prels)
    pres = _place(pres, dsl, new_entries, after)
    dst.put("ppt/presentation.xml", pres)
    dst.save(out)
    return after, len(new_entries)


def cmd_insert(a):
    if os.path.abspath(a.out) == os.path.abspath(a.master):
        raise DeckError("Write to a new file (-o), so the original master is there to compare against.")
    after, n = insert(a.master, a.slides_deck, a.out, a.after, a.after_text, a.slides, a.allow_duplicate)
    first = after + 1
    print(f"Inserted {n} slide(s) as slide {first}{'-%d' % (first + n - 1) if n > 1 else ''}: {a.out}")
    print("Only the new slides and the slide list changed; every other part is copied as it was.")


# ---------------------------------------------------------------- building from layouts

P_NS = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')


def layouts(pkg):
    """[(number, name, layout part, [placeholder kinds])] in master order, numbered from 1."""
    pres = pkg.text("ppt/presentation.xml")
    prm = {r["Id"]: pkg.resolve("ppt/presentation.xml", r["Target"]) for r in pkg.rels("ppt/presentation.xml")}
    out = []
    for t in re.findall(r"<p:sldMasterId\b[^>]*>", pres):
        master = prm[_attrs(t)["r:id"]]
        mrm = {r["Id"]: pkg.resolve(master, r["Target"]) for r in pkg.rels(master)}
        for lt in re.findall(r"<p:sldLayoutId\b[^>]*>", pkg.text(master)):
            part = mrm[_attrs(lt)["r:id"]]
            kinds = [_ph_info(m.group(0))[0] for m in re.finditer(PH_RE, pkg.text(part), re.S)]
            kinds = [k for k in kinds if k not in ("dt", "ftr", "sldNum")]
            out.append((len(out) + 1, _layout_name(pkg, part), part, kinds))
    return out


def _find_layout(pkg, want):
    ls = layouts(pkg)
    if str(want).isdigit():
        n = int(want)
        if 1 <= n <= len(ls):
            return ls[n - 1]
        raise DeckError(f"There is no layout {n}: the deck has {len(ls)}. See deck-layouts.")
    hits = [l for l in ls if l[1].strip().lower() == want.strip().lower()]
    if len(hits) == 1:
        return hits[0]
    if hits:
        raise DeckError(f"{len(hits)} layouts are called {want!r} (numbers "
                        f"{', '.join(str(l[0]) for l in hits)}). Give the number instead.")
    raise DeckError(f"No layout called {want!r}. See deck-layouts for the names and numbers.")


def add_slide(pkg, layout_part, after=None):
    """A new slide on a layout, with that layout's empty boxes (title, text, pictures)
    ready to fill. Returns the new slide's number."""
    shapes, nid = [], 2
    for sp in re.findall(r"<p:sp>.*?</p:sp>", pkg.text(layout_part), re.S):
        ph = re.search(PH_RE, sp, re.S)
        if not ph:
            continue
        kind, _ = _ph_info(ph.group(0))
        if kind in ("dt", "ftr"):
            continue
        name = _attrs(re.search(r"<p:cNvPr\b[^>]*>", sp).group(0)).get("name", f"Placeholder {nid}")
        body = ""
        if kind == "sldNum":
            body = ('<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:fld id="{B6F15528-21DE-4FAA-801E-634DDDAF4B2B}" '
                    'type="slidenum"><a:rPr lang="en-GB"/><a:t>‹#›</a:t></a:fld></a:p></p:txBody>')
        elif kind != "pic":
            body = '<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:endParaRPr lang="en-GB" dirty="0"/></a:p></p:txBody>'
        shapes.append(f'<p:sp><p:nvSpPr><p:cNvPr id="{nid}" name="{name}"/><p:cNvSpPr><a:spLocks noGrp="1"/>'
                      f'</p:cNvSpPr><p:nvPr>{ph.group(0)}</p:nvPr></p:nvSpPr><p:spPr/>{body}</p:sp>')
        nid += 1
    xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
           f'<p:sld {P_NS}><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/>'
           '</p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/>'
           '<a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>' + "".join(shapes) +
           '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>')
    dsl = pkg.slides()
    if after is None:
        after = len(dsl)
    if not 0 <= after <= len(dsl):
        raise DeckError(f"--after must be 0 to {len(dsl)}.")
    part = pkg.free_name("ppt/slides/slide1.xml")
    pkg.put(part, xml)
    pkg.add_override(part, SLIDE_CT)
    pkg.set_rels(part, [{"Id": "rId1", "Type": R_NS + "/slideLayout",
                         "Target": pkg.relative(part, layout_part)}])
    prels = pkg.rels("ppt/presentation.xml")
    rid_n = max([int(r["Id"][3:]) for r in prels if r["Id"][3:].isdigit()] + [0]) + 1
    sid = max([x for x, _, _ in dsl] + [255]) + 1
    prels.append({"Id": f"rId{rid_n}", "Type": SLIDE_T, "Target": pkg.relative("ppt/presentation.xml", part)})
    pkg.set_rels("ppt/presentation.xml", prels)
    pkg.put("ppt/presentation.xml", _place(pkg.text("ppt/presentation.xml"), dsl, [(sid, f"rId{rid_n}")], after))
    return after + 1


def fill(pkg, part, box, text):
    """Put text into a box on a slide: by its name, or title / subtitle / body / body2...
    Each line becomes a paragraph; the box's own formatting is kept."""
    phs = _placeholders(pkg, part)
    xml = pkg.text(part)
    target = None
    for ph in phs:
        if ph["name"] == box:
            target = ph["xml"]
    if target is None:
        m = re.fullmatch(r"(title|subtitle|body|text)(\d*)", box.lower())
        if m:
            want = {"title": ("title", "ctrTitle"), "subtitle": ("subTitle",),
                    "body": ("body", "obj"), "text": ("body", "obj")}[m.group(1)]
            cands = [ph["xml"] for ph in phs if ph["kind"] in want]
            k = int(m.group(2) or 1)
            if len(cands) >= k:
                target = cands[k - 1]
    if target is None:
        for sp in re.findall(r"<p:sp>.*?</p:sp>", xml, re.S):   # a plain text box, by name
            if re.search(r'<p:cNvPr\b[^>]*name="%s"' % re.escape(html.escape(box)), sp) and "<p:txBody>" in sp:
                target = sp
    if target is None or "<p:txBody>" not in target:
        names = ", ".join(f'"{ph["name"]}" ({ph["kind"]})' for ph in phs if ph["kind"] not in ("pic", "sldNum"))
        raise DeckError(f"No text box {box!r} on that slide. Boxes there: {names or 'none'}.")
    body = re.search(r"<p:txBody>.*?</p:txBody>", target, re.S).group(0)
    head = re.match(r"<p:txBody>(<a:bodyPr\b.*?(?:/>|</a:bodyPr>))?\s*(<a:lstStyle\b.*?(?:/>|</a:lstStyle>))?",
                    body, re.S)
    ppr = re.search(r"<a:pPr\b[^>]*/>|<a:pPr\b.*?</a:pPr>", body, re.S)
    rpr = re.search(r"<a:rPr\b[^>]*/>|<a:rPr\b.*?</a:rPr>", body, re.S)
    rpr_x = rpr.group(0) if rpr else '<a:rPr lang="en-GB" dirty="0"/>'
    paras = "".join(
        f"<a:p>{ppr.group(0) if ppr else ''}"
        + (f"<a:r>{rpr_x}<a:t>{html.escape(line, quote=False)}</a:t></a:r>" if line else
           '<a:endParaRPr lang="en-GB" dirty="0"/>') + "</a:p>"
        for line in text.split("\n"))
    new_body = ("<p:txBody>" + (head.group(1) or "<a:bodyPr/>") + (head.group(2) or "<a:lstStyle/>")
                + paras + "</p:txBody>")
    pkg.put(part, xml.replace(target, target.replace(body, new_body, 1), 1))


def cmd_layouts(a):
    pkg = Pkg(a.deck)
    ls = layouts(pkg)
    for n, name, part, kinds in ls:
        counts = {}
        for k in kinds:
            k = {"ctrTitle": "title", "subTitle": "subtitle", "obj": "body", "pic": "picture"}.get(k, k)
            counts[k] = counts.get(k, 0) + 1
        desc = ", ".join(f"{v} {k}" if v > 1 else k for k, v in counts.items()) or "no boxes (fixed design)"
        print(f"{n:3d}. {name}  [{desc}]")
    if a.render:
        tmp = tempfile.mkdtemp()
        try:
            keep = os.path.join(tmp, "layouts.pptx")
            cmd_pick(type("A", (), {"deck": a.deck, "slides": "none", "out": keep})())
            pk = Pkg(keep)
            for n, name, part, kinds in layouts(pk):
                no = add_slide(pk, part)
                sp = pk.slides()[no - 1][2]
                for ph in _placeholders(pk, sp):
                    if ph["kind"] not in ("pic", "sldNum"):
                        fill(pk, sp, ph["name"], ph["name"])
            pk.save(keep)
            files = render(keep, a.render, 800)
            print(f"\n{len(files)} layout previews in {a.render}: slideNN.png is layout NN, and every "
                  "text box shows its own name, which is what deck-fill --box takes")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def cmd_add_slide(a):
    pkg = Pkg(a.deck)
    n, name, part, _ = _find_layout(pkg, a.layout)
    no = add_slide(pkg, part, a.after)
    out = _check_out(a)
    pkg.save(out)
    print(f"Added slide {no} on layout {n}. {name}: {out}")
    print("Fill it with deck-fill (text) and deck-swap-image (pictures); deck-text lists its empty boxes.")


def cmd_fill(a):
    pkg = Pkg(a.deck)
    _, _, part = _slide_no(pkg, a.slide)
    text = sys.stdin.read() if a.text == "-" else a.text.replace("\\n", "\n")
    fill(pkg, part, a.box, text.rstrip("\n"))
    out = _check_out(a)
    pkg.save(out)
    print(f"Filled \"{a.box}\" on slide {a.slide}: {out}")


# ---------------------------------------------------------------- Circle's brand master

BRAND_DRIVE = "b!btnAx0EMLUaFyzSCxuDrhOoZ9iBVLqhMoaIg-ctFYgk8FFSkIzgKRZsYdgK9oiXv"   # resources
BRAND_PATH = "/General/WOW-Circle Templates & Forms/Circle Brand Master 2026 (layouts).pptx"
BRAND_CACHE = os.path.join(os.path.expanduser("~"), ".circle", "brand", "Circle Brand Master.pptx")


def brand_master(refresh=False):
    """Local copy of Circle's brand master (the current brand book's layouts, no slides),
    re-downloaded when the SharePoint copy is newer."""
    from . import graph
    import urllib.parse
    q = urllib.parse.quote(BRAND_PATH)
    st, _, meta = graph.call_retry("GET", f"/drives/{BRAND_DRIVE}/root:{q}?$select=id,lastModifiedDateTime,size")
    if st != 200:
        if os.path.isfile(BRAND_CACHE):
            print("(SharePoint unreachable, using the saved copy)", file=sys.stderr)
            return BRAND_CACHE
        raise DeckError(f"Could not reach Circle's brand master on SharePoint ({st}). It lives in "
                        "resources > General > WOW-Circle Templates & Forms.")
    stamp = BRAND_CACHE + ".stamp"
    have = open(stamp).read().strip() if os.path.isfile(stamp) else ""
    if refresh or have != meta.get("lastModifiedDateTime") or not os.path.isfile(BRAND_CACHE):
        st, _, data = graph.call_retry("GET", f"/drives/{BRAND_DRIVE}/items/{meta['id']}/content", raw=True)
        if st != 200 or not data[:2] == b"PK":
            raise DeckError(f"Could not download the brand master ({st}).")
        os.makedirs(os.path.dirname(BRAND_CACHE), exist_ok=True)
        with open(BRAND_CACHE + ".tmp", "wb") as f:
            f.write(data)
        os.replace(BRAND_CACHE + ".tmp", BRAND_CACHE)
        with open(stamp, "w") as f:
            f.write(meta.get("lastModifiedDateTime", ""))
    return BRAND_CACHE


def cmd_brand(a):
    path = brand_master(a.refresh)
    if a.out:
        if os.path.exists(a.out):
            raise DeckError(f"{a.out} already exists; pick a new name.")
        shutil.copy(path, a.out)
        path = a.out
    print(path)


# ---------------------------------------------------------------- cli

def _run(fn):
    def go(a):
        try:
            fn(a)
        except DeckError as e:
            sys.exit(str(e))
    return go


def register(sub):
    p = sub.add_parser("deck-text", help="a deck's slides in order: text, pictures, hidden, layout")
    p.add_argument("deck")
    p.add_argument("--slides", help="e.g. 3,5-8 (default all)")
    p.add_argument("--notes", action="store_true", help="include speaker notes")
    p.set_defaults(func=_run(cmd_text))

    p = sub.add_parser("deck-images", help="pull the pictures out of a deck, named by slide")
    p.add_argument("deck")
    p.add_argument("--out", required=True)
    p.add_argument("--slides")
    p.set_defaults(func=_run(cmd_images))

    p = sub.add_parser("deck-render", help="each slide as a PNG, exported by PowerPoint")
    p.add_argument("deck")
    p.add_argument("--out", required=True)
    p.add_argument("--width", type=int, default=1600, help="pixels wide")
    p.set_defaults(func=_run(cmd_render))

    p = sub.add_parser("deck-pick", help="a copy of a deck with only some slides")
    p.add_argument("deck")
    p.add_argument("--slides", required=True, help="e.g. 4 or 4,9-11, or none to keep only the layouts")
    p.add_argument("-o", "--out", required=True)
    p.set_defaults(func=_run(cmd_pick))

    p = sub.add_parser("deck-replace", help="change text on slides, keeping its formatting")
    p.add_argument("deck")
    p.add_argument("--old", required=True)
    p.add_argument("--new", required=True)
    p.add_argument("--slide", help="slide number(s); default every slide")
    p.add_argument("--all", action="store_true", help="allow more than one change")
    p.add_argument("-o", "--out", required=True)
    p.set_defaults(func=_run(cmd_replace))

    p = sub.add_parser("deck-swap-image", help="replace a picture, cropped to fill its frame")
    p.add_argument("deck")
    p.add_argument("--slide", type=int, required=True)
    p.add_argument("--image", required=True, help="picture name or media file name, from deck-text")
    p.add_argument("--with", dest="with_", required=True, help="the new PNG or JPEG")
    p.add_argument("--stretch", action="store_true", help="don't crop, stretch to the frame")
    p.add_argument("-o", "--out", required=True)
    p.set_defaults(func=_run(cmd_swap_image))

    p = sub.add_parser("deck-insert", help="put slides into a master deck, touching nothing else")
    p.add_argument("master")
    p.add_argument("slides_deck", help="the deck holding the new slides")
    where = p.add_mutually_exclusive_group()
    where.add_argument("--after", type=int, help="after this slide number (0 = at the start)")
    where.add_argument("--after-text", help="after the one slide containing this text")
    p.add_argument("--slides", help="which slides of the new deck (default all)")
    p.add_argument("--allow-duplicate", action="store_true")
    p.add_argument("-o", "--out", required=True)
    p.set_defaults(func=_run(cmd_insert))

    p = sub.add_parser("deck-layouts", help="a deck's layouts, numbered, with the boxes each one has")
    p.add_argument("deck")
    p.add_argument("--render", metavar="DIR", help="also render one preview slide per layout into DIR")
    p.set_defaults(func=_run(cmd_layouts))

    p = sub.add_parser("deck-add-slide", help="add a new slide on one of the deck's layouts")
    p.add_argument("deck")
    p.add_argument("--layout", required=True, help="layout name or number, from deck-layouts")
    p.add_argument("--after", type=int, help="after this slide number (0 = at the start; default the end)")
    p.add_argument("-o", "--out", required=True)
    p.set_defaults(func=_run(cmd_add_slide))

    p = sub.add_parser("deck-fill", help="put text into a box on a slide, keeping its formatting")
    p.add_argument("deck")
    p.add_argument("--slide", type=int, required=True)
    p.add_argument("--box", required=True, help="title, subtitle, body, body2... or the box's name")
    p.add_argument("--text", required=True, help="the text; \\n or a new line starts a paragraph; - reads stdin")
    p.add_argument("-o", "--out", required=True)
    p.set_defaults(func=_run(cmd_fill))

    p = sub.add_parser("deck-brand", help="Circle's brand master (layouts only), to build new slides from")
    p.add_argument("-o", "--out", help="copy it here as the start of a new deck")
    p.add_argument("--refresh", action="store_true", help="download it again even if unchanged")
    p.set_defaults(func=_run(cmd_brand))
