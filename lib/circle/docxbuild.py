#!/usr/bin/env python3
"""Write a Word document directly, in Circle's house typography. Stdlib only.

A .docx is a zip of XML, so it is built here by hand. That is deliberate.

The converters that look like the easy route (macOS `textutil`, HTML saved as
.doc) flatten every table into loose paragraphs, and Circle's handover format
is entirely tables. python-docx would do it, but this repo runs on the stdlib
so it still works on a locked-down agency laptop. Writing the XML directly
costs about two hundred lines.

House typography: headings BBH Hegarty and never bold, everything else Roboto
Serif with bold allowed on sub-headings, monochrome apart from anything whose
colour carries meaning.

The font name matters. Roboto Serif is installed as a variable font whose legacy
family name is **"Roboto Serif 20pt"**, and Word matches on that name, so plain
"Roboto Serif" silently substitutes.
"""
import os
import struct
import zipfile

HEADING_FONT = "BBH Hegarty"
BODY_FONT = "Roboto Serif 20pt"     # the legacy family name, not "Roboto Serif"

GREY_RULE = "7F7F7F"
GREY_FILL = "E6E6E6"
GREY_INK = "595959"

# Point sizes. Word stores half-points, so these are doubled on the way in.
SIZES = {"h1": 22, "h2": 15, "h3": 12, "h4": 11, "body": 11, "meta": 9.5}


class DocxError(Exception):
    pass


def esc(s):
    return (str("" if s is None else s).replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def _run(text, font, size, bold=False, colour=None, italic=False):
    """One run. rFonts goes on all four slots or Word falls back for some text."""
    rpr = [f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:cs="{font}" '
           f'w:eastAsia="{font}"/>']
    if bold:
        rpr.append("<w:b/>")
    if italic:
        rpr.append("<w:i/>")
    if colour:
        rpr.append(f'<w:color w:val="{colour}"/>')
    half = int(round(size * 2))
    rpr.append(f'<w:sz w:val="{half}"/><w:szCs w:val="{half}"/>')
    # A literal newline inside a cell becomes a real line break.
    body = "".join(f"<w:br/>" if part == "\n" else
                   f'<w:t xml:space="preserve">{esc(part)}</w:t>'
                   for part in _split_breaks(text))
    return f'<w:r><w:rPr>{"".join(rpr)}</w:rPr>{body}</w:r>'


def _split_breaks(text):
    out = []
    for i, part in enumerate(str("" if text is None else text).split("\n")):
        if i:
            out.append("\n")
        out.append(part)
    return out


class Doc:
    """A document being built. Call the methods in reading order, then save()."""

    def __init__(self):
        self.body = []
        self.media = []   # (part name, bytes), for image()

    # --- paragraphs ---

    def heading(self, text, level=1):
        """Headings 1 and 2 are BBH Hegarty and never bold; 3 and 4 are
        sub-headings, so Roboto Serif bold."""
        key = f"h{level}"
        font = HEADING_FONT if level <= 2 else BODY_FONT
        before = {1: 0, 2: 16, 3: 12, 4: 10}[level]
        self._para(_run(text, font, SIZES[key], bold=level >= 3),
                   before=before, after=4,
                   outline=level, keep_next=True)
        return self

    def para(self, text, bold=False, meta=False, italic=False):
        size = SIZES["meta"] if meta else SIZES["body"]
        colour = GREY_INK if meta else None
        self._para(_run(text, BODY_FONT, size, bold=bold, colour=colour,
                        italic=italic), after=6)
        return self

    def bullets(self, items):
        for it in items:
            self._para(_run("• " + str(it), BODY_FONT, SIZES["body"]),
                       after=2, indent=280)
        return self

    def spacer(self, pt=6):
        self.body.append(f'<w:p><w:pPr><w:spacing w:after="{int(pt * 20)}"/>'
                         "</w:pPr></w:p>")
        return self

    def _para(self, runs, before=0, after=0, indent=0, outline=None,
              keep_next=False):
        ppr = [f'<w:spacing w:before="{int(before * 20)}" '
               f'w:after="{int(after * 20)}"/>']
        if indent:
            ppr.append(f'<w:ind w:left="{indent}" w:hanging="{indent}"/>')
        if outline:
            ppr.append(f'<w:outlineLvl w:val="{outline - 1}"/>')
        if keep_next:
            ppr.append("<w:keepNext/>")
        self.body.append(f'<w:p><w:pPr>{"".join(ppr)}</w:pPr>{runs}</w:p>')

    # --- tables ---

    def table(self, rows, widths=None, header=False):
        """rows: list of rows; a cell is a string or {text, bold, fill, ink}.

        widths are percentages and must total 100. Fixed layout, because Word's
        auto layout ignores the widths and makes every handover look different.
        """
        if not rows:
            return self
        cols = max(len(r) for r in rows)
        widths = widths or [round(100 / cols, 2)] * cols
        total = 9026  # twips inside default A4 margins
        grid = [int(total * w / 100) for w in widths]

        border = (f'<w:{{}} w:val="single" w:sz="4" w:space="0" '
                  f'w:color="{GREY_RULE}"/>')
        borders = "".join(border.format(e)
                          for e in ("top", "left", "bottom", "right",
                                    "insideH", "insideV"))
        xml = ['<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/>'
               f"<w:tblBorders>{borders}</w:tblBorders>"
               '<w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid>'
               + "".join(f'<w:gridCol w:w="{g}"/>' for g in grid)
               + "</w:tblGrid>"]
        for i, row in enumerate(rows):
            xml.append("<w:tr>")
            if header and i == 0:
                xml.append("<w:trPr><w:tblHeader/></w:trPr>")
            for j in range(cols):
                cell = row[j] if j < len(row) else ""
                if not isinstance(cell, dict):
                    cell = {"text": cell}
                bold = cell.get("bold", header and i == 0)
                fill = cell.get("fill", GREY_FILL if (header and i == 0) else None)
                shd = (f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>'
                       if fill else "")
                xml.append(
                    f'<w:tc><w:tcPr><w:tcW w:w="{grid[j]}" w:type="dxa"/>{shd}'
                    '<w:tcMar><w:top w:w="60" w:type="dxa"/>'
                    '<w:bottom w:w="60" w:type="dxa"/>'
                    '<w:left w:w="90" w:type="dxa"/>'
                    '<w:right w:w="90" w:type="dxa"/></w:tcMar></w:tcPr>'
                    '<w:p><w:pPr><w:spacing w:after="0"/></w:pPr>'
                    + _run(cell.get("text", ""), BODY_FONT, SIZES["body"],
                           bold=bold, colour=cell.get("ink"))
                    + "</w:p></w:tc>")
            xml.append("</w:tr>")
        xml.append("</w:tbl>")
        self.body.append("".join(xml))
        # Word needs a paragraph after a table, or two tables merge into one.
        return self.spacer(4)

    # --- images ---

    def image(self, path, width_cm=16.0, max_height_cm=None):
        """An inline JPEG or PNG, scaled to width_cm (A4 text width is about 16cm),
        or smaller if that would make it taller than max_height_cm."""
        with open(path, "rb") as f:
            data = f.read()
        w, h = image_size(data)
        ext = "png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "jpg"
        n = len(self.media) + 1
        self.media.append((f"media/image{n}.{ext}", data))
        cx = int(width_cm * 360000)
        cy = int(cx * h / w) if w else cx
        if max_height_cm and cy > max_height_cm * 360000:
            cx, cy = int(cx * max_height_cm * 360000 / cy), int(max_height_cm * 360000)
        A = "http://schemas.openxmlformats.org/drawingml/2006/main"
        PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
        self.body.append(
            '<w:p><w:pPr><w:spacing w:after="80"/></w:pPr><w:r><w:drawing>'
            f'<wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
            f'<wp:docPr id="{n}" name="Picture {n}"/>'
            f'<a:graphic xmlns:a="{A}"><a:graphicData uri="{PIC}"><pic:pic xmlns:pic="{PIC}">'
            f'<pic:nvPicPr><pic:cNvPr id="{n}" name="image{n}.{ext}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="rIdImg{n}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
            '</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>')
        return self

    # --- output ---

    def xml(self):
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/'
            'wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/'
            'officeDocument/2006/relationships" xmlns:wp="http://schemas.openxmlformats.org/'
            'drawingml/2006/wordprocessingDrawing"><w:body>'
            + "".join(self.body)
            + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
              '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" '
              'w:left="1134" w:header="709" w:footer="709"/></w:sectPr>'
              "</w:body></w:document>")

    def save(self, path):
        path = os.path.abspath(path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        parts = {
            "[Content_Types].xml":
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
                'content-types"><Default Extension="rels" ContentType='
                '"application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Default Extension="jpg" ContentType="image/jpeg"/>'
                '<Default Extension="png" ContentType="image/png"/>'
                '<Override PartName="/word/document.xml" ContentType='
                '"application/vnd.openxmlformats-officedocument.'
                'wordprocessingml.document.main+xml"/></Types>',
            "_rels/.rels":
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/'
                'package/2006/relationships"><Relationship Id="rId1" Type='
                '"http://schemas.openxmlformats.org/officeDocument/2006/'
                'relationships/officeDocument" Target="word/document.xml"/>'
                "</Relationships>",
            "word/document.xml": self.xml(),
        }
        if self.media:
            parts["word/_rels/document.xml.rels"] = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                + "".join(f'<Relationship Id="rIdImg{i}" Type="http://schemas.openxmlformats.org/'
                          f'officeDocument/2006/relationships/image" Target="{name}"/>'
                          for i, (name, _) in enumerate(self.media, 1))
                + "</Relationships>")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for name, content in parts.items():
                z.writestr(name, content)
            for name, data in self.media:
                z.writestr("word/" + name, data)
        return path


def image_size(data):
    """(width, height) of a PNG or JPEG, from its header."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return w, h
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    raise DocxError("Not a JPEG or PNG this can size.")


def check_fonts():
    """Warn, never fail: a document in a substituted font still beats none."""
    files = ""
    dirs = [os.path.expanduser("~/Library/Fonts"), "/Library/Fonts"]   # macOS
    windir = os.environ.get("WINDIR", r"C:\Windows")
    dirs += [os.path.join(windir, "Fonts"),                              # Windows
             os.path.join(os.environ.get("LOCALAPPDATA", ""),
                          "Microsoft", "Windows", "Fonts")]
    for d in dirs:
        if os.path.isdir(d):
            files += " ".join(os.listdir(d)).lower()
    missing = []
    if "hegarty" not in files:
        missing.append(HEADING_FONT)
    if "robotoserif" not in files.replace(" ", ""):
        missing.append(BODY_FONT)
    return missing
