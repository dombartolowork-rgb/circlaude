#!/usr/bin/env python3
"""Client copy budgets: the client-facing tab of a Circle budget, tidied and checked.

A budget workbook has a WORKSHEET tab (the budget itself, with IN and OUT costs)
and a client-facing tab (`Client Copy`, or `PREVIEW` on older files) that pulls
from it by formula. Getting that tab fit to send is fiddly by hand: empty lines
and unused sections to delete, formulas that stopped pulling through, numbering
to redo, rows to open up so the text shows.

  circle clientcopy-fetch "<SharePoint link>"    download a copy of the budget to work on (read only)
  circle clientcopy-check budget.xlsx            what is in the worksheet, what is wrong with the tab
  circle clientcopy-build budget.xlsx            write the two files below, beside the budget
  circle clientcopy-build budget.xlsx --fixes fixes.json

`clientcopy-build` never changes the budget it is given. It writes two new files:

  <name> - Claude's copy.xlsx    the whole workbook, with the client tab rebuilt
                                 from the worksheet and still linked to it by formula
  <name> - Client Excel.xlsx     that one tab alone, values only, no formulas and
                                 no other sheets, for a client who wants Excel

The client tab is rebuilt from the worksheet instead of being repaired, because
the worksheet is the truth and the tab's formulas are the part that breaks. Every
worksheet line with a cost or a description is carried over; empty lines and
empty sections are left out; sections and lines are renumbered in sequence.

The judgement (which drop-down suits a description, what is a spelling mistake)
is not made here. It arrives as a fixes file, see `skills/circle-client-copy/SKILL.md`:

  {"items": {"113": "Additional Insurance"},      worksheet row -> drop-down option
   "descriptions": {"115": "Safety kit"},         worksheet row -> corrected spelling
   "labels": {"167": "Healthcare practitioners"}, worksheet row -> what the client tab shows in
                                                  column C when no drop-down option fits
   "omit": [55]}                                  note-only lines to leave out

Python 3 stdlib only. An .xlsx is a zip of XML, so this reads with ElementTree
and writes the XML directly.
"""
import datetime
import difflib
import html
import json
import math
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"

LINE_HEIGHT = 13.0     # points per wrapped line, as the budgets Ella has tidied by hand
CHARS_PER_WIDTH = 1.2  # wrapped characters per unit of column width, measured against the same


def register(sub):
    p = sub.add_parser("clientcopy-fetch",
                       help="download a copy of a budget from its SharePoint link, to work on. Changes nothing online")
    p.add_argument("link", help="the SharePoint sharing link to the workbook, in quotes")
    p.add_argument("--out-dir", help="where to save it (default: Documents/Client copies)")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("clientcopy-check",
                       help="read a budget: its lines, drop-down options and what is wrong with the client tab")
    p.add_argument("budget", help="the budget workbook (.xlsx), a local copy")
    p.add_argument("--sheet", help="the client-facing tab, if it is not Client Copy or PREVIEW")
    p.add_argument("--json", action="store_true", help="print JSON instead of text")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("clientcopy-build",
                       help="write Claude's copy of a budget with the client tab rebuilt, and a values-only client Excel")
    p.add_argument("budget", help="the budget workbook (.xlsx), a local copy. It is never changed")
    p.add_argument("--fixes", help="JSON file of drop-down and spelling fixes, by worksheet row")
    p.add_argument("--sheet", help="the client-facing tab, if it is not Client Copy or PREVIEW")
    p.add_argument("--out-dir", help="where to write the two files (default: beside the budget)")
    p.add_argument("--tab-name", help="name of the single tab in the client Excel (default: the job code)")
    p.add_argument("--allow-reword", action="store_true",
                   help="let a description fix change more than spelling. Only when the budget's owner asked for it")
    p.set_defaults(func=cmd_build)


def die(msg):
    sys.exit("clientcopy: " + msg)


# ---------------------------------------------------------------- reading


def col_num(letters):
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def split_ref(ref):
    m = re.match(r"([A-Z]+)(\d+)$", ref)
    return m.group(1), int(m.group(2))


def xml_text(s):
    """Escape for element text. Excel also needs control characters gone."""
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def num_text(v):
    """A number as Excel stores it, without float noise such as 1.0900000000000001."""
    if isinstance(v, int) or float(v).is_integer():
        return str(int(v))
    return repr(round(float(v), 10))


class Book:
    def __init__(self, path):
        if not os.path.isfile(path):
            die("no such file: " + path)
        if not path.lower().endswith((".xlsx", ".xlsm")):
            die("not an Excel workbook (.xlsx): " + path)
        if os.path.basename(path).startswith("~$"):
            die("that is Excel's lock file, not the budget: " + path)
        self.path = path
        try:
            with zipfile.ZipFile(path) as z:
                self.names = z.namelist()
                self.parts = {n: z.read(n) for n in self.names}
        except zipfile.BadZipFile:
            die("cannot open it as a workbook. If it lives on SharePoint, download a copy first: " + path)
        rels = {}
        for rel in ET.fromstring(self.parts["xl/_rels/workbook.xml.rels"]):
            rels[rel.get("Id")] = self._target(rel.get("Target"))
        wb = ET.fromstring(self.parts["xl/workbook.xml"])
        self.sheets = []  # (name, path)
        for sh in wb.find(M + "sheets"):
            self.sheets.append((sh.get("name"), rels[sh.get(R + "id")]))
        self.defined = {}
        dn = wb.find(M + "definedNames")
        for d in (dn if dn is not None else []):
            # A workbook-level name wins over a sheet-local one of the same name.
            if d.get("localSheetId") is None or d.get("name") not in self.defined:
                self.defined[d.get("name")] = d.text or ""
        self.shared = []
        if "xl/sharedStrings.xml" in self.parts:
            for si in ET.fromstring(self.parts["xl/sharedStrings.xml"]):
                bits = [t.text or "" for t in si.findall(M + "t")]
                for r in si.findall(M + "r"):
                    bits += [t.text or "" for t in r.findall(M + "t")]
                self.shared.append("".join(bits))
        self._cells = {}

    @staticmethod
    def _target(t):
        return t.lstrip("/") if t.startswith("/") else "xl/" + t

    def text(self, name):
        return self.parts[name].decode("utf-8")

    def sheet_path(self, name):
        for n, p in self.sheets:
            if n == name:
                return p
        return None

    def find_sheet(self, wanted):
        """A sheet by name, forgiving case and stray spaces ('Client Copy ')."""
        w = wanted.strip().lower()
        for n, _ in self.sheets:
            if n.strip().lower() == w:
                return n
        return None

    def cells(self, sheet):
        """{ref: {"v": value, "f": formula or None, "s": style, "t": type}} for one sheet."""
        if sheet in self._cells:
            return self._cells[sheet]
        root = ET.fromstring(self.parts[self.sheet_path(sheet)])
        out, shared_f = {}, {}
        for row in root.find(M + "sheetData"):
            for c in row:
                ref, t = c.get("r"), c.get("t")
                f_el, v_el = c.find(M + "f"), c.find(M + "v")
                raw = v_el.text if v_el is not None else None
                if t == "s" and raw is not None:
                    v = self.shared[int(raw)]
                elif t == "inlineStr":
                    is_el = c.find(M + "is")
                    v = "".join(x.text or "" for x in is_el.iter(M + "t")) if is_el is not None else ""
                elif t in ("str", "e", "b"):
                    v = raw or ""
                elif raw is None:
                    v = None
                else:
                    try:
                        v = float(raw)
                    except ValueError:
                        v = raw
                f = None
                if f_el is not None:
                    f = f_el.text or ""
                    if f_el.get("t") == "shared":
                        si = f_el.get("si")
                        if f:
                            shared_f[si] = (f, split_ref(ref))
                        elif si in shared_f:
                            base, (bc, br) = shared_f[si]
                            f = shift_rows(base, split_ref(ref)[1] - br)
                out[ref] = {"v": v, "f": f, "s": c.get("s"), "t": t}
        self._cells[sheet] = out
        return out


def shift_rows(formula, by):
    """Move the relative row numbers in a formula. Enough to read a shared formula's target."""
    def sub(m):
        return m.group(1) + (m.group(2) if m.group(2).startswith("$") else str(int(m.group(2)) + by))
    return re.sub(r"(\$?[A-Z]{1,3})(\$?\d+)\b", sub, formula)


def as_text(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return "" if v == 0 else num_text(v)
    return str(v)


def as_num(v):
    return v if isinstance(v, float) else 0.0


# ---------------------------------------------------------------- the worksheet


def read_worksheet(book, ws):
    """Sections, their lines, the fee rows under them and the total, from the WORKSHEET tab."""
    cells = book.cells(ws)
    rows = {}
    for ref, c in cells.items():
        col, r = split_ref(ref)
        rows.setdefault(r, {})[col] = c
    hidden = set()
    for m in re.finditer(r"<row\b([^>]*)", book.text(book.sheet_path(ws))):
        if re.search(r'\bhidden="(1|true)"', m.group(1)):
            hidden.add(int(re.search(r'\br="(\d+)"', m.group(1)).group(1)))

    def val(r, col):
        return rows.get(r, {}).get(col, {}).get("v")

    sections, extras, cur = [], [], None
    subtotal = total = None
    for r in sorted(rows):
        a, b, c = as_text(val(r, "A")).strip(), as_text(val(r, "B")).strip(), as_text(val(r, "C")).strip()
        if b.upper() == "GLCODE" and re.fullmatch(r"\d+", a):
            cur = {"number": int(a), "name": c, "row": r, "lines": []}
            sections.append(cur)
            continue
        if a.upper().startswith("END"):
            cur = None
            continue
        if cur is not None:
            e = val(r, "E")
            desc = as_text(val(r, "D"))
            line = {"row": r, "item": c, "desc": desc, "out": round(as_num(e), 2),
                    "gl": val(r, "B"), "hidden": r in hidden,
                    "error": e if (rows.get(r, {}).get("E", {}).get("t") == "e") else None}
            line["used"] = abs(line["out"]) >= 0.005 or bool(desc.strip()) or bool(line["error"])
            if c or desc.strip() or line["used"]:
                cur["lines"].append(line)
        elif sections:
            if a.upper() == "SUBTOTAL":
                subtotal = round(as_num(val(r, "C")) or as_num(val(r, "E")), 2)
            elif re.fullmatch(r"\d+", a) and c:
                if "total" in c.lower():
                    total = {"row": r, "label": c, "out": round(as_num(val(r, "E")), 2)}
                    break
                extras.append({"row": r, "label": c, "rate": val(r, "D"), "out": round(as_num(val(r, "E")), 2)})
    if not sections:
        die("no budget sections found on the %s tab. Is this a Circle budget workbook?" % ws)
    if total is None:
        die("found the sections on %s but no TOTAL row under them" % ws)
    return {"sections": sections, "extras": extras, "subtotal": subtotal, "total": total}


def dropdown_options(book, ws):
    """{worksheet row: [options]} for the column C drop-downs."""
    xml = book.text(book.sheet_path(ws))
    found = []
    for m in re.finditer(r"<dataValidation\b([^>]*)>(.*?)</dataValidation>", xml, re.S):
        if 'type="list"' not in m.group(1):
            continue
        sq = re.search(r'sqref="([^"]*)"', m.group(1))
        f1 = re.search(r"<formula1>(.*?)</formula1>", m.group(2), re.S)
        if sq and f1:
            found.append((sq.group(1), html.unescape(f1.group(1))))
    for m in re.finditer(r"<x14:dataValidation\b([^>]*)>(.*?)</x14:dataValidation>", xml, re.S):
        if 'type="list"' not in m.group(1):
            continue
        sq = re.search(r"<xm:sqref>(.*?)</xm:sqref>", m.group(2), re.S)
        f1 = re.search(r"<x14:formula1>\s*<xm:f>(.*?)</xm:f>", m.group(2), re.S)
        if sq and f1:
            found.append((sq.group(1), html.unescape(f1.group(1))))

    def resolve(f, depth=0):
        f = f.strip().lstrip("=")
        if f.startswith('"'):
            return [x.strip() for x in f.strip('"').split(",") if x.strip()]
        if f in book.defined and depth < 3:
            return resolve(book.defined[f], depth + 1)
        m = re.fullmatch(r"'?([^'!\[\]]+)'?!\$?([A-Z]+)\$?(\d+)(?::\$?([A-Z]+)\$?(\d+))?", f)
        if not m:
            return None
        sheet = book.find_sheet(m.group(1))
        if not sheet:
            return None
        c1, r1 = col_num(m.group(2)), int(m.group(3))
        c2, r2 = (col_num(m.group(4)), int(m.group(5))) if m.group(4) else (c1, r1)
        out = []
        for ref, c in book.cells(sheet).items():
            col, r = split_ref(ref)
            if c1 <= col_num(col) <= c2 and r1 <= r <= r2 and as_text(c["v"]).strip():
                out.append((r, col_num(col), as_text(c["v"]).strip()))
        return [t for _, _, t in sorted(out)]

    by_row = {}
    for sqref, f in found:
        opts = resolve(f)
        if not opts:
            continue
        for rng in sqref.split():
            m = re.fullmatch(r"\$?([A-Z]+)\$?(\d+)(?::\$?([A-Z]+)\$?(\d+))?", rng)
            if not m or m.group(1) != "C":
                continue
            for r in range(int(m.group(2)), int(m.group(4) or m.group(2)) + 1):
                by_row[r] = opts
    return by_row


# ---------------------------------------------------------------- the client tab


def pick_client_sheet(book, wanted=None):
    if wanted:
        n = book.find_sheet(wanted)
        if not n:
            die("no tab called %r. Tabs: %s" % (wanted, ", ".join(n for n, _ in book.sheets)))
        return n
    for n, _ in book.sheets:
        if re.fullmatch(r"client\s*copy", n.strip(), re.I):
            return n
    for n, _ in book.sheets:
        if n.strip().upper() == "PREVIEW":
            return n
    die("no Client Copy or PREVIEW tab. Tabs: %s. Name the client-facing one with --sheet"
        % ", ".join(n for n, _ in book.sheets))


def read_client(book, client, ws, data):
    """What each row of the client tab points at, and which rows to borrow styles from."""
    cells = book.cells(client)
    pat = re.compile(r"(?:'%s'|%s)!\$?([A-Z]+)\$?(\d+)" % (re.escape(ws), re.escape(ws)))
    rows = {}
    for ref, c in cells.items():
        col, r = split_ref(ref)
        row = rows.setdefault(r, {"cells": {}, "refs": {}})
        row["cells"][col] = c
        if c["f"]:
            m = pat.search(c["f"])
            if m:
                row["refs"][col] = int(m.group(2))
    header_rows = {s["row"]: s for s in data["sections"]}
    line_rows = {l["row"]: l for s in data["sections"] for l in s["lines"]}
    extra_rows = {x["row"]: x for x in data["extras"]}

    total_row = None
    for r in sorted(rows):
        c = rows[r]["cells"].get("C")
        if c and not c["f"] and "TOTAL" in as_text(c["v"]).upper():
            total_row = r
        elif rows[r]["refs"].get("E") == data["total"]["row"]:
            total_row = r
    if total_row is None:
        die("cannot find the PROJECT TOTAL row on the %s tab, so its layout cannot be copied. "
            "Try --sheet PREVIEW if the workbook has an untouched one" % client)

    first = None
    style = {"header": None, "line": None, "spacer": None, "extra": {}, "extra_gap": None}
    prev_kind = None
    for r in sorted(rows):
        if r > total_row:
            break
        refs = rows[r]["refs"]
        kind = None
        if (refs.get("A") in header_rows or refs.get("C") in header_rows) and "E" not in refs:
            kind = "header"
            first = first or r
            style["header"] = style["header"] or r
        elif refs.get("E") in line_rows and refs.get("C") in line_rows:
            kind = "line"
            style["line"] = style["line"] or r
        elif refs.get("E") in extra_rows:
            kind = "extra"
            style["extra"].setdefault(refs["E"], r)
        elif first and r < total_row:
            a = rows[r]["cells"].get("A")
            static_a = a and not a["f"] and as_text(a["v"]).strip()
            if prev_kind == "extra" and style["extra_gap"] is None:
                style["extra_gap"] = r
            elif not static_a and style["spacer"] is None and not style["extra"]:
                style["spacer"] = r  # the blank row between sections, not the black TO ADD A LINE row
        prev_kind = kind
    if not first or not style["header"] or not style["line"]:
        die("the %s tab does not look like a Circle client copy (no section or line rows pulling from %s). "
            "Try --sheet PREVIEW" % (client, ws))

    # What is wrong with the tab as it stands.
    issues = {"missing": [], "misaligned": [], "ref_errors": [], "empty_rows": 0}
    shown = {}
    for r in sorted(rows):
        if first <= r < total_row:
            e = rows[r]["refs"].get("E")
            if e in line_rows:
                shown.setdefault(e, r)
                for col in ("C", "D"):
                    if col in rows[r]["cells"] and rows[r]["refs"].get(col) not in (None, e):
                        issues["misaligned"].append({"client_row": r, "column": col, "cost_from": e,
                                                     "text_from": rows[r]["refs"][col]})
                if not line_rows[e]["used"]:
                    issues["empty_rows"] += 1
            for col, c in rows[r]["cells"].items():
                if "#REF!" in (c["f"] or "") or as_text(c["v"]) == "#REF!":
                    issues["ref_errors"].append("%s%d" % (col, r))
    for lr, l in line_rows.items():
        if l["used"] and lr not in shown:
            issues["missing"].append(lr)
    return {"rows": rows, "first": first, "total_row": total_row, "style": style, "issues": issues,
            "last": max(rows)}


# ---------------------------------------------------------------- the plan


def load_fixes(path):
    if not path:
        return {"items": {}, "descriptions": {}, "labels": {}, "omit": []}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        die("cannot read the fixes file: %s" % e)
    unknown = set(raw) - {"items", "descriptions", "labels", "omit"}
    if unknown:
        die("fixes file has keys it should not: %s" % ", ".join(sorted(unknown)))
    try:
        return {"items": {int(k): str(v) for k, v in raw.get("items", {}).items()},
                "descriptions": {int(k): str(v) for k, v in raw.get("descriptions", {}).items()},
                "labels": {int(k): str(v).strip() for k, v in raw.get("labels", {}).items()},
                "omit": [int(x) for x in raw.get("omit", [])]}
    except (TypeError, ValueError):
        die("fixes file: every key must be a worksheet row number")


def spelling_only(old, new):
    """True when `new` differs from `old` by spelling alone: same number of words, each close to the old."""
    a, b = old.split(), new.split()
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x != y and difflib.SequenceMatcher(None, x.lower(), y.lower()).ratio() < 0.6:
            return False
    return True


def apply_fixes(data, options, fixes, allow_reword):
    lines = {l["row"]: l for s in data["sections"] for l in s["lines"]}
    changes = []
    for row, item in fixes["items"].items():
        l = lines.get(row)
        if not l:
            die("fixes: worksheet row %d is not a budget line" % row)
        opts = options.get(row)
        if opts and item not in opts:
            close = difflib.get_close_matches(item, opts, n=3, cutoff=0.4)
            die("fixes: %r is not a drop-down option for row %d.%s"
                % (item, row, " Closest: " + ", ".join(close) if close else ""))
        if item != l["item"]:
            changes.append({"row": row, "column": "C", "was": l["item"], "now": item})
            l["item"], l["item_changed"] = item, True
    for row, desc in fixes["descriptions"].items():
        l = lines.get(row)
        if not l:
            die("fixes: worksheet row %d is not a budget line" % row)
        if desc != l["desc"]:
            if not allow_reword and not spelling_only(l["desc"], desc):
                die("fixes: row %d changes more than spelling.\n  was: %s\n  now: %s\n"
                    "A description says what the cost includes, so it is not reworded here. "
                    "If the budget's owner asked for this wording, pass --allow-reword." % (row, l["desc"], desc))
            changes.append({"row": row, "column": "D", "was": l["desc"], "now": desc})
            l["desc"], l["desc_changed"] = desc, True
    for row, label in fixes["labels"].items():
        l = lines.get(row)
        if not l:
            die("fixes: worksheet row %d is not a budget line" % row)
        if row in fixes["items"]:
            die("fixes: row %d has both a drop-down fix and a label. Pick one" % row)
        if label and label != l["item"]:
            changes.append({"row": row, "column": "client tab C", "was": l["item"], "now": label})
            l["label"] = label
    for row in fixes["omit"]:
        l = lines.get(row)
        if not l:
            die("fixes: worksheet row %d is not a budget line" % row)
        if abs(l["out"]) >= 0.005:
            die("fixes: row %d has a cost of %.2f, so leaving it out would break the total" % (row, l["out"]))
        l["used"] = False
    return changes


def make_plan(data):
    """The order of rows in the rebuilt tab, with the new numbering."""
    plan, n = [], 0
    for s in data["sections"]:
        used = [l for l in s["lines"] if l["used"]]
        if not used:
            continue
        n += 1
        if len(used) > 99:
            die("section %s has %d lines, more than the two-digit numbering can hold" % (s["name"], len(used)))
        plan.append({"kind": "header", "number": n, "section": s})
        for i, l in enumerate(used, 1):
            plan.append({"kind": "line", "number": round(n + i / 100.0, 2), "line": l, "section": s})
        plan.append({"kind": "spacer"})
    for x in data["extras"]:
        if abs(x["out"]) < 0.005:
            continue
        n += 1
        plan.append({"kind": "extra", "number": n, "extra": x})
        plan.append({"kind": "extra_gap"})
    n += 1
    plan.append({"kind": "total", "number": n})
    return plan


def reconcile(data, plan):
    lines_sum = round(sum(p["line"]["out"] for p in plan if p["kind"] == "line"), 2)
    extras_sum = round(sum(p["extra"]["out"] for p in plan if p["kind"] == "extra"), 2)
    total = data["total"]["out"]
    checks = []
    if data["subtotal"] is not None:
        checks.append({"what": "lines add up to the worksheet SUBTOTAL", "ours": lines_sum,
                       "worksheet": data["subtotal"], "ok": abs(lines_sum - data["subtotal"]) < 0.015})
    checks.append({"what": "lines plus insurance, contingency and fee add up to the worksheet TOTAL",
                   "ours": round(lines_sum + extras_sum, 2), "worksheet": total,
                   "ok": abs(lines_sum + extras_sum - total) < 0.025})
    return checks


# ---------------------------------------------------------------- writing rows


def lines_needed(text, width):
    per = max(10, int(width * CHARS_PER_WIDTH))
    return sum(max(1, math.ceil(len(p) / float(per))) for p in text.split("\n"))


def sheet_ref(ws):
    return ws if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", ws) else "'%s'" % ws.replace("'", "''")


class Rows:
    """Builds <row> XML twice over: linked to the worksheet by formula, and as plain values."""

    def __init__(self, client, ws, d_width, line_a_style):
        self.c, self.ws, self.d_width, self.line_a_style = client, sheet_ref(ws), d_width, line_a_style

    def style(self, src_row, col):
        if src_row is None:
            return None
        return self.c["rows"].get(src_row, {}).get("cells", {}).get(col, {}).get("s")

    @staticmethod
    def cell(ref, s, kind=None, value=None, formula=None):
        a = ' r="%s"' % ref + (' s="%s"' % s if s else "")
        f = "<f>%s</f>" % xml_text(formula) if formula else ""
        if kind == "num":
            return "<c%s>%s<v>%s</v></c>" % (a, f, num_text(value))
        if kind == "text":
            if formula:
                return '<c%s t="str">%s<v xml:space="preserve">%s</v></c>' % (a, f, xml_text(value))
            return '<c%s t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (a, xml_text(value))
        if formula:  # a formula whose value Excel works out when it opens the file
            return "<c%s>%s</c>" % (a, f)
        return "<c%s/>" % a if s else ""

    def row(self, r, cells, ht=None):
        h = ' ht="%s" customHeight="1"' % num_text(ht) if ht else ""
        return '<row r="%d" spans="1:5"%s>%s</row>' % (r, h, "".join(cells))

    def build(self, r, p, linked):
        st, cell, ws = self.c["style"], self.cell, self.ws
        k = p["kind"]
        if k == "header":
            src, s = st["header"], p["section"]
            return self.row(r, [
                cell("A%d" % r, self.style(src, "A"), "num", p["number"]),
                cell("B%d" % r, self.style(src, "B")),
                cell("C%d" % r, self.style(src, "C"), "text", s["name"],
                     "%s!C%d" % (ws, s["row"]) if linked else None),
                cell("D%d" % r, self.style(src, "D")),
                cell("E%d" % r, self.style(src, "E"))])
        if k == "line":
            src, l = st["line"], p["line"]
            lr = l["row"]
            n = lines_needed(l["desc"].rstrip(), self.d_width)
            cells = [cell("A%d" % r, self.line_a_style, "num", p["number"])]
            if linked:  # the GL code column is hidden, and stays out of the client's file altogether
                gl = l["gl"]
                if l.get("item_changed") or gl is None or (isinstance(gl, str) and gl.startswith("#")):
                    cells.append(cell("B%d" % r, self.style(src, "B"), formula="%s!B%d" % (ws, lr)))
                else:
                    cells.append(cell("B%d" % r, self.style(src, "B"), "num" if isinstance(gl, float) else "text",
                                      gl, "%s!B%d" % (ws, lr)))
            else:
                cells.append(cell("B%d" % r, self.style(src, "B")))
            if l.get("label"):  # typed for the client, because no drop-down option fits
                cells.append(cell("C%d" % r, self.style(src, "C"), "text", l["label"]))
            else:
                cells.append(cell("C%d" % r, self.style(src, "C"), "text", l["item"],
                                  'IF((%s!C%d=0),"",%s!C%d)' % (ws, lr, ws, lr) if linked else None))
            cells.append(cell("D%d" % r, self.style(src, "D"), "text", l["desc"],
                              'IF((%s!D%d=0),"",%s!D%d)' % (ws, lr, ws, lr) if linked else None))
            cells.append(self.cost("E%d" % r, self.style(src, "E"), l["out"], lr, linked))
            return self.row(r, cells, LINE_HEIGHT * n if n > 1 else None)
        if k in ("spacer", "extra_gap"):
            src = st[k]
            return self.row(r, [cell("%s%d" % (col, r), self.style(src, col)) for col in "ABCDE"])
        if k == "extra":
            x = p["extra"]
            src = st["extra"].get(x["row"]) or next(iter(st["extra"].values()), st["line"])
            cells = [cell("A%d" % r, self.style(src, "A"), "num", p["number"]),
                     cell("B%d" % r, self.style(src, "B")),
                     cell("C%d" % r, self.style(src, "C"), "text", x["label"],
                          "%s!C%d" % (ws, x["row"]) if linked else None)]
            if isinstance(x["rate"], float) and x["rate"]:
                cells.append(cell("D%d" % r, self.style(src, "D"), "num", x["rate"],
                                  "%s!D%d" % (ws, x["row"]) if linked else None))
            elif as_text(x["rate"]).strip():
                cells.append(cell("D%d" % r, self.style(src, "D"), "text", as_text(x["rate"]),
                                  "%s!D%d" % (ws, x["row"]) if linked else None))
            else:
                cells.append(cell("D%d" % r, self.style(src, "D")))
            cells.append(self.cost("E%d" % r, self.style(src, "E"), x["out"], x["row"], linked))
            return self.row(r, cells)
        if k == "total":
            src, t = self.c["total_row"], p["total"]
            return self.row(r, [
                cell("A%d" % r, self.style(src, "A"), "num", p["number"]),
                cell("B%d" % r, self.style(src, "B")),
                cell("C%d" % r, self.style(src, "C"), "text", "PROJECT TOTAL"),
                cell("D%d" % r, self.style(src, "D")),
                self.cost("E%d" % r, self.style(src, "E"), t["out"], t["row"], linked)])
        raise ValueError(k)

    def cost(self, ref, s, out, ws_row, linked):
        f = 'IF((%s!E%d=0)," ",%s!E%d)' % (self.ws, ws_row, self.ws, ws_row) if linked else None
        if abs(out) < 0.005:
            return self.cell(ref, s, "text", " ", f) if linked else self.cell(ref, s)
        return self.cell(ref, s, "num", out, f)


def raw_rows(sheet_xml):
    """{row number: its <row> XML} for one sheet."""
    out = {}
    for m in re.finditer(r"<row\b[^>]*?(?:/>|>.*?</row>)", sheet_xml, re.S):
        out[int(re.search(r'\br="(\d+)"', m.group(0)).group(1))] = m.group(0)
    return out


def renumber_row(xml, new):
    xml = re.sub(r'(<row\b[^>]*?\br=")\d+(")', lambda m: m.group(1) + str(new) + m.group(2), xml, count=1)
    return re.sub(r'(<c\b[^>]*?\br="[A-Z]+)\d+(")', lambda m: m.group(1) + str(new) + m.group(2), xml)


def value_row(book, client_cells, src, new, today):
    """One row of the original tab as plain values: static text kept, formulas replaced by their results."""
    cells = []
    for ref in sorted((r for r in client_cells if split_ref(r)[1] == src), key=lambda r: col_num(split_ref(r)[0])):
        c, col = client_cells[ref], split_ref(ref)[0]
        v = c["v"]
        if c["f"] and "TODAY()" in c["f"].upper():
            v = float(today)
        if isinstance(v, float):
            cells.append(Rows.cell("%s%d" % (col, new), c["s"], "num", v))
        elif v is not None and str(v) != "" and c["t"] != "e":
            cells.append(Rows.cell("%s%d" % (col, new), c["s"], "text", str(v)))
        else:
            cells.append(Rows.cell("%s%d" % (col, new), c["s"]))
    return cells


def excel_serial(day):
    return (day - datetime.date(1899, 12, 30)).days


# ---------------------------------------------------------------- writing sheets and packages


def ensure_two_decimals(styles_xml, s):
    """The style id to use for line numbers: `s` if it already shows two decimals, else a copy that does.

    Without this a line numbered 10.10 shows as 10.1, which is the trailing zero the template drops.
    """
    m = re.search(r"(<cellXfs\b[^>]*>)(.*?)(</cellXfs>)", styles_xml, re.S)
    xfs = re.findall(r"<xf\b[^>]*?(?:/>|>.*?</xf>)", m.group(2), re.S)
    if s is None or int(s) >= len(xfs):
        base = '<xf numFmtId="2" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    else:
        base = xfs[int(s)]
        if re.search(r'numFmtId="2"', base):
            return styles_xml, s
        base = re.sub(r'numFmtId="\d+"', 'numFmtId="2"', base, count=1)
        if "applyNumberFormat" not in base:
            base = base.replace("<xf ", '<xf applyNumberFormat="1" ', 1)
    head = re.sub(r'count="\d+"', 'count="%d"' % (len(xfs) + 1), m.group(1))
    new = styles_xml[:m.start()] + head + m.group(2) + base + m.group(3) + styles_xml[m.end():]
    return new, str(len(xfs))


def d_column_width(sheet_xml):
    for m in re.finditer(r"<col\b([^>]*)/>", sheet_xml):
        lo, hi = int(re.search(r'min="(\d+)"', m.group(1)).group(1)), int(re.search(r'max="(\d+)"', m.group(1)).group(1))
        w = re.search(r'width="([\d.]+)"', m.group(1))
        if lo <= 4 <= hi and w:
            return float(w.group(1))
    return 46.0


def rebuild_sheet(sheet_xml, rows_xml, last_row, total_row_new, first_row, tail_shift, old_total_row, linked):
    """The client tab's XML with new sheetData, and everything that points at row numbers put right."""
    start = sheet_xml.index("<sheetData")
    end = sheet_xml.index("</sheetData>") + len("</sheetData>")
    head, tail = sheet_xml[:start], sheet_xml[end:]

    head = re.sub(r"<dimension\b[^>]*/>", '<dimension ref="A1:E%d"/>' % last_row, head)
    head = re.sub(r'\stopLeftCell="[^"]*"', "", head)
    head = re.sub(r"<selection\b[^>]*/>", '<selection activeCell="A1" sqref="A1"/>', head)
    if not linked:
        head = re.sub(r'\stabSelected="[^"]*"', "", head)
        head = head.replace("<sheetView ", '<sheetView tabSelected="1" ', 1)

    def fix_merges(m):
        kept = []
        for ref in re.findall(r'<mergeCell ref="([^"]+)"', m.group(0)):
            a, b = (ref.split(":") + [ref])[:2]
            (c1, r1), (c2, r2) = split_ref(a), split_ref(b)
            if r2 < first_row:
                kept.append(ref)
            elif r1 > old_total_row:
                kept.append("%s%d:%s%d" % (c1, r1 + tail_shift, c2, r2 + tail_shift))
        if not kept:
            return ""
        return '<mergeCells count="%d">%s</mergeCells>' % (
            len(kept), "".join('<mergeCell ref="%s"/>' % k for k in kept))
    tail = re.sub(r"<mergeCells\b.*?</mergeCells>", fix_merges, tail, flags=re.S)

    # One hide-the-zeros rule over the whole body replaces the patchwork of ranges.
    cfs = re.findall(r"<conditionalFormatting\b.*?</conditionalFormatting>", tail, re.S)
    tail = re.sub(r"<conditionalFormatting\b.*?</conditionalFormatting>", "", tail, flags=re.S)
    if cfs and linked:
        cf = re.sub(r'sqref="[^"]*"', 'sqref="A%d:E%d"' % (first_row, total_row_new), cfs[0], count=1)
        anchor = re.search(r"<(dataValidations|hyperlinks|printOptions|pageMargins|pageSetup|headerFooter|"
                           r"rowBreaks|colBreaks|drawing|legacyDrawing|tableParts|extLst)\b", tail)
        pos = anchor.start() if anchor else tail.index("</worksheet>")
        tail = tail[:pos] + cf + tail[pos:]
    tail = re.sub(r"<rowBreaks\b.*?</rowBreaks>", "", tail, flags=re.S)
    if not linked:
        # Nothing in the client's file may point outside it.
        tail = re.sub(r"<pageSetup\b[^>]*/>", lambda m: re.sub(r'\sr:id="[^"]*"', "", m.group(0)), tail)
        for tag in ("legacyDrawing", "legacyDrawingHF", "tableParts", "extLst", "dataValidations", "hyperlinks",
                    "sheetProtection", "picture", "oleObjects", "controls"):
            tail = re.sub(r"<%s\b[^>]*/>|<%s\b.*?</%s>" % (tag, tag, tag), "", tail, flags=re.S)
    return head + "<sheetData>" + "".join(rows_xml) + "</sheetData>" + tail


def set_cell_text(sheet_xml, ref, text):
    """Put plain text in one worksheet cell, keeping its style."""
    col, r = split_ref(ref)
    rm = re.search(r'<row\b[^>]*\br="%d"[^>]*?(/>|>.*?</row>)' % r, sheet_xml, re.S)
    if not rm:
        die("worksheet row %d not found" % r)
    row = rm.group(0)
    cm = re.search(r'<c\b[^>]*\br="%s"[^>]*?(?:/>|>.*?</c>)' % ref, row, re.S)
    s = re.search(r'\bs="(\d+)"', cm.group(0).split(">")[0]) if cm else None
    new = Rows.cell(ref, s.group(1) if s else None, "text", text)
    if cm:
        row2 = row[:cm.start()] + new + row[cm.end():]
    elif row.endswith("/>"):
        row2 = row[:-2] + ">" + new + "</row>"
    else:
        pos = len(row) - len("</row>")
        for m in re.finditer(r'<c\b[^>]*\br="([A-Z]+)\d+"', row):
            if col_num(m.group(1)) > col_num(col):
                pos = m.start()
                break
        row2 = row[:pos] + new + row[pos:]
    return sheet_xml[:rm.start()] + row2 + sheet_xml[rm.end():]


def write_zip(path, names, parts):
    tmp = path + ".part"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.writestr(n, parts[n])
    os.replace(tmp, path)


def free_name(folder, stem, suffix):
    """A file name nobody has yet. An open workbook will not refresh, so a rebuild gets a new name."""
    p = os.path.join(folder, "%s - %s.xlsx" % (stem, suffix))
    n = 2
    while os.path.exists(p):
        p = os.path.join(folder, "%s - %s v%d.xlsx" % (stem, suffix, n))
        n += 1
    return p


def write_linked(book, out, client, ws, new_sheet_xml, styles_xml, ws_changes, last_row):
    parts = dict(book.parts)
    names = list(book.names)
    parts[book.sheet_path(client)] = new_sheet_xml.encode("utf-8")
    parts["xl/styles.xml"] = styles_xml.encode("utf-8")
    if ws_changes:
        wsx = book.text(book.sheet_path(ws))
        for ch in ws_changes:
            if ch["column"] not in ("C", "D"):
                continue  # a client-tab label, not a worksheet edit
            wsx = set_cell_text(wsx, "%s%d" % (ch["column"], ch["row"]), ch["now"])
        parts[book.sheet_path(ws)] = wsx.encode("utf-8")

    wb = book.text("xl/workbook.xml")
    # Cached results no longer match every formula, so Excel recalculates on opening,
    # and the stale calculation chain goes.
    if re.search(r"<calcPr\b", wb):
        wb = re.sub(r"<calcPr\b([^>]*?)/>",
                    lambda m: "<calcPr%s fullCalcOnLoad=\"1\"/>" % re.sub(r'\sfullCalcOnLoad="[^"]*"', "", m.group(1)),
                    wb, count=1)
    else:
        for anchor in ("<oleSize", "<customWorkbookViews", "<pivotCaches", "<smartTagPr", "<smartTagTypes",
                       "<webPublishing", "<fileRecoveryPr", "<webPublishObjects", "<extLst", "</workbook>"):
            if anchor in wb:
                wb = wb.replace(anchor, '<calcPr fullCalcOnLoad="1"/>' + anchor, 1)
                break
    idx = [n for n, _ in book.sheets].index(client)
    wb = re.sub(r'(<definedName\b[^>]*name="_xlnm\.Print_Area"[^>]*localSheetId="%d"[^>]*>)[^<]*(</definedName>)' % idx,
                lambda m: m.group(1) + xml_text("%s!$A$1:$E$%d" % (sheet_ref(client), last_row)) + m.group(2), wb)
    parts["xl/workbook.xml"] = wb.encode("utf-8")
    if "xl/calcChain.xml" in parts:
        del parts["xl/calcChain.xml"]
        names.remove("xl/calcChain.xml")
        ct = book.text("[Content_Types].xml")
        parts["[Content_Types].xml"] = re.sub(r'<Override\b[^>]*PartName="/xl/calcChain\.xml"[^>]*/>', "", ct).encode("utf-8")
        rels = book.text("xl/_rels/workbook.xml.rels")
        parts["xl/_rels/workbook.xml.rels"] = re.sub(r'<Relationship\b[^>]*Target="calcChain\.xml"[^>]*/>', "", rels).encode("utf-8")
    write_zip(out, names, parts)


def write_values(book, out, client, sheet_xml, styles_xml, tab_name, last_row):
    """A new workbook holding the one tab and nothing else.

    Built from nothing instead of by deleting tabs from the budget, so no hidden sheet,
    shared text, comment or external link from the budget can travel with it.
    """
    parts, names = {}, []

    def add(name, data):
        names.append(name)
        parts[name] = data if isinstance(data, bytes) else data.encode("utf-8")

    overrides = [
        ("/xl/workbook.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"),
        ("/xl/worksheets/sheet1.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"),
        ("/xl/styles.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml")]
    wb_rels = [("rId1", "worksheet", "worksheets/sheet1.xml"), ("rId2", "styles", "styles.xml")]
    if "xl/theme/theme1.xml" in book.parts:
        overrides.append(("/xl/theme/theme1.xml", "application/vnd.openxmlformats-officedocument.theme+xml"))
        wb_rels.append(("rId3", "theme", "theme/theme1.xml"))

    # The logo: the tab's drawing and the pictures it uses, and nothing else it might point at.
    media, drawing = [], None
    src_path = book.sheet_path(client)
    rel_path = os.path.dirname(src_path) + "/_rels/" + os.path.basename(src_path) + ".rels"
    dm = re.search(r'<drawing\b[^>]*r:id="([^"]+)"', sheet_xml)
    if dm and rel_path in book.parts:
        for rel in ET.fromstring(book.parts[rel_path]):
            if rel.get("Id") == dm.group(1) and rel.get("Type", "").endswith("/drawing"):
                drawing = os.path.normpath(os.path.join(os.path.dirname(src_path), rel.get("Target"))).replace("\\", "/")
    if drawing and drawing in book.parts:
        dxml = book.text(drawing)
        drel_path = os.path.dirname(drawing) + "/_rels/" + os.path.basename(drawing) + ".rels"
        drels, keep = [], set(re.findall(r'r:embed="([^"]+)"', dxml))
        if drel_path in book.parts:
            for rel in ET.fromstring(book.parts[drel_path]):
                if rel.get("Id") in keep and rel.get("Type", "").endswith("/image") and rel.get("TargetMode") != "External":
                    src = os.path.normpath(os.path.join(os.path.dirname(drawing), rel.get("Target"))).replace("\\", "/")
                    if src in book.parts:
                        name = "image%d%s" % (len(media) + 1, os.path.splitext(src)[1].lower())
                        media.append((name, book.parts[src]))
                        drels.append((rel.get("Id"), name))
        if set(i for i, _ in drels) == keep:
            sheet_xml = re.sub(r'(<drawing\b[^>]*r:id=")[^"]+(")', r"\g<1>rId1\g<2>", sheet_xml)
            overrides.append(("/xl/drawings/drawing1.xml", "application/vnd.openxmlformats-officedocument.drawing+xml"))
        else:
            drawing = None
    if not drawing or drawing not in book.parts:
        drawing = None
        sheet_xml = re.sub(r"<drawing\b[^>]*/>", "", sheet_xml)

    exts = {"rels": "application/vnd.openxmlformats-package.relationships+xml", "xml": "application/xml"}
    for name, _ in media:
        ext = name.rsplit(".", 1)[1]
        exts[ext] = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif",
                     "emf": "image/x-emf", "wmf": "image/x-wmf"}.get(ext, "application/octet-stream")
    add("[Content_Types].xml",
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        + "".join('<Default Extension="%s" ContentType="%s"/>' % kv for kv in sorted(exts.items()))
        + "".join('<Override PartName="%s" ContentType="%s"/>' % o for o in overrides) + "</Types>")
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    add("_rels/.rels",
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="%s/officeDocument" Target="xl/workbook.xml"/></Relationships>' % rel_ns)
    add("xl/workbook.xml",
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="%s">'
        '<bookViews><workbookView xWindow="0" yWindow="0" windowWidth="24000" windowHeight="16000"/></bookViews>'
        '<sheets><sheet name="%s" sheetId="1" r:id="rId1"/></sheets>'
        '<definedNames><definedName name="_xlnm.Print_Area" localSheetId="0">%s</definedName></definedNames>'
        "</workbook>" % (rel_ns, xml_text(tab_name).replace('"', "&quot;"),
                         xml_text("%s!$A$1:$E$%d" % (sheet_ref(tab_name), last_row))))
    add("xl/_rels/workbook.xml.rels",
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join('<Relationship Id="%s" Type="%s/%s" Target="%s"/>' % (i, rel_ns, t, tg) for i, t, tg in wb_rels)
        + "</Relationships>")
    add("xl/worksheets/sheet1.xml", sheet_xml)
    add("xl/styles.xml", styles_xml)
    if "xl/theme/theme1.xml" in book.parts:
        add("xl/theme/theme1.xml", book.parts["xl/theme/theme1.xml"])
    if drawing:
        add("xl/worksheets/_rels/sheet1.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="%s/drawing" Target="../drawings/drawing1.xml"/></Relationships>' % rel_ns)
        add("xl/drawings/drawing1.xml", dxml)
        add("xl/drawings/_rels/drawing1.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join('<Relationship Id="%s" Type="%s/image" Target="../media/%s"/>' % (i, rel_ns, n) for i, n in drels)
            + "</Relationships>")
        for name, data in media:
            add("xl/media/" + name, data)
    write_zip(out, names, parts)


# ---------------------------------------------------------------- commands


def cmd_fetch(args):
    """Download the workbook behind a sharing link. Two GETs, nothing is written to SharePoint."""
    import base64
    from circle import graph
    if not re.match(r"https://[^/]+\.sharepoint\.com/", args.link):
        die("that is not a SharePoint link: " + args.link)
    share = "u!" + base64.urlsafe_b64encode(args.link.encode()).decode().rstrip("=")
    st, _, item = graph.call_retry("GET", "/shares/%s/driveItem?$select=id,name,size,lastModifiedDateTime,"
                                          "lastModifiedBy,parentReference" % share)
    if st != 200:
        die("could not open that link (%s). Check it opens for you in the browser, and that you are "
            "signed in: circle whoami" % st)
    name = item.get("name", "")
    if not name.lower().endswith((".xlsx", ".xlsm")):
        die("the link points at %r, which is not an Excel workbook" % name)
    st, _, data = graph.call_retry("GET", "/drives/%s/items/%s/content"
                                   % (item["parentReference"]["driveId"], item["id"]), raw=True)
    if st != 200 or not isinstance(data, (bytes, bytearray)):
        die("found %s but could not download it (%s)" % (name, st))
    folder = args.out_dir or os.path.join(os.path.expanduser("~"), "Documents", "Client copies")
    os.makedirs(folder, exist_ok=True)
    out = os.path.join(folder, name)
    n = 2
    while os.path.exists(out):  # never over a copy someone may have open
        stem, ext = os.path.splitext(name)
        out = os.path.join(folder, "%s (%d)%s" % (stem, n, ext))
        n += 1
    with open(out, "wb") as f:
        f.write(data)
    who = (item.get("lastModifiedBy") or {}).get("user", {}).get("displayName", "?")
    print("Saved a copy: %s" % out)
    print("  %s bytes, last changed %s by %s" % ("{:,}".format(len(data)), item.get("lastModifiedDateTime", "?"), who))
    print("  from: %s" % (item.get("parentReference", {}).get("path", "").split("root:")[-1] or "?"))
    print("The one on SharePoint is untouched. If it changes after this, fetch again before building.")


def analyse(args):
    book = Book(args.budget)
    ws = book.find_sheet("WORKSHEET")
    if not ws:
        die("no WORKSHEET tab. Tabs: %s" % ", ".join(n for n, _ in book.sheets))
    client = pick_client_sheet(book, getattr(args, "sheet", None))
    data = read_worksheet(book, ws)
    options = dropdown_options(book, ws)
    c = read_client(book, client, ws, data)
    return book, ws, client, data, options, c


def money(v):
    return "£{:,.2f}".format(v)


def cmd_check(args):
    book, ws, client, data, options, c = analyse(args)
    plan = make_plan(data)
    checks = reconcile(data, plan)
    notes = line_notes(data, options)
    if args.json:
        out = {"budget": os.path.basename(args.budget), "worksheet": ws, "client_tab": client,
               "sections": [{"number": s["number"], "name": s["name"], "row": s["row"],
                             "options": options.get(s["lines"][0]["row"]) if s["lines"] else None,
                             "lines": [{k: l[k] for k in ("row", "item", "desc", "out", "used", "hidden")}
                                       for l in s["lines"] if l["used"]]}
                            for s in data["sections"]],
               "extras": data["extras"], "subtotal": data["subtotal"], "total": data["total"],
               "client_tab_issues": c["issues"], "checks": checks, "notes": notes}
        print(json.dumps(out, indent=1, ensure_ascii=False))
        return
    print("Budget:      %s" % os.path.basename(args.budget))
    print("Client tab:  %s   (pulls from %s)" % (client, ws))
    print("Nothing has been changed. Row numbers below are WORKSHEET rows.\n")
    for s in data["sections"]:
        used = [l for l in s["lines"] if l["used"]]
        if not used:
            print("%2d  %s: empty, will be left out" % (s["number"], s["name"]))
            continue
        print("%2d  %s   %d line(s), %s" % (s["number"], s["name"], len(used), money(sum(l["out"] for l in used))))
        opts = options.get(used[0]["row"])
        if opts:
            print("    drop-down options: " + " | ".join(opts))
        for l in used:
            print("    row %-4d %-34s %10s  %s" % (l["row"], (l["item"] or "(no item chosen)")[:34],
                                                  money(l["out"]) if abs(l["out"]) >= 0.005 else "-",
                                                  l["desc"].replace("\n", " / ")))
    print()
    for x in data["extras"]:
        rate = " (%s%%)" % num_text(round(x["rate"] * 100, 4)) if isinstance(x["rate"], float) else ""
        print("    row %-4d %-34s %10s" % (x["row"], x["label"] + rate, money(x["out"])))
    print("    row %-4d %-34s %10s" % (data["total"]["row"], "TOTAL", money(data["total"]["out"])))

    i = c["issues"]
    print("\nThe %s tab as it stands:" % client)
    print("  worksheet lines with nothing pulling them through: %s"
          % (", ".join("row %d" % r for r in sorted(i["missing"])) or "none"))
    print("  rows whose text comes from a different worksheet row than their cost: %s"
          % (", ".join("%s%d" % (m["column"], m["client_row"]) for m in i["misaligned"]) or "none"))
    print("  #REF! errors: %s" % (", ".join(i["ref_errors"]) or "none"))
    print("  empty lines still showing: %d" % i["empty_rows"])
    print("\nChecks:")
    for ch in checks:
        print("  %s  %s: %s against %s" % ("OK " if ch["ok"] else "NO ", ch["what"], money(ch["ours"]), money(ch["worksheet"])))
    if notes:
        print("\nFor a person to look at:")
        for n in notes:
            print("  - " + n)


def line_notes(data, options):
    notes = []
    for s in data["sections"]:
        for l in s["lines"]:
            if not l["used"]:
                continue
            where = "row %d (%s)" % (l["row"], s["name"])
            if l["error"]:
                notes.append("%s: the cost is an Excel error (%s)" % (where, l["error"]))
            if abs(l["out"]) >= 0.005 and not l["desc"].strip():
                notes.append("%s: a cost of %s with no description" % (where, money(l["out"])))
            if abs(l["out"]) < 0.005 and l["desc"].strip() and not l["error"]:
                notes.append("%s: a description with no cost, kept as a note to the client: %s"
                             % (where, l["desc"].strip()[:70]))
            if not l["item"]:
                notes.append("%s: no drop-down option chosen in column C" % where)
            elif options.get(l["row"]) and l["item"] not in options[l["row"]]:
                notes.append("%s: column C says %r, which is not one of that section's options" % (where, l["item"]))
            if l["hidden"]:
                notes.append("%s: the row is hidden in the worksheet but still counts towards the total" % where)
    for x in data["extras"]:
        if abs(x["out"]) < 0.005:
            notes.append("%s is zero, so its row is left out" % x["label"])
    return notes


def cmd_build(args):
    book, ws, client, data, options, c = analyse(args)
    fixes = load_fixes(args.fixes)
    changes = apply_fixes(data, options, fixes, args.allow_reword)
    plan = make_plan(data)
    for p in plan:
        if p["kind"] == "total":
            p["total"] = data["total"]
    checks = reconcile(data, plan)
    if not all(ch["ok"] for ch in checks):
        for ch in checks:
            print("  %s  %s: %s against %s" % ("OK " if ch["ok"] else "NO ", ch["what"], money(ch["ours"]), money(ch["worksheet"])))
        die("the lines do not add up to the worksheet's own totals, so nothing was written. "
            "A cost is probably sitting outside a section, or the workbook was saved without recalculating. "
            "Run clientcopy-check and look at the worksheet.")

    client_xml = book.text(book.sheet_path(client))
    styles_xml, a_style = ensure_two_decimals(book.text("xl/styles.xml"),
                                              c["rows"][c["style"]["line"]]["cells"].get("A", {}).get("s"))
    rows = Rows(c, ws, d_column_width(client_xml), a_style)
    raw = raw_rows(client_xml)
    client_cells = book.cells(client)
    today = excel_serial(datetime.date.today())

    first, old_total, old_last = c["first"], c["total_row"], c["last"]
    total_new = first + len(plan) - 1
    shift = total_new - old_total
    linked_rows, value_rows = [], []
    for r in range(1, first):
        if r in raw:
            linked_rows.append(raw[r])
            ht = re.search(r'\bht="([\d.]+)"', raw[r].split(">")[0])
            value_rows.append(rows.row(r, value_row(book, client_cells, r, r, today), float(ht.group(1)) if ht else None))
    for i, p in enumerate(plan):
        linked_rows.append(rows.build(first + i, p, True))
        value_rows.append(rows.build(first + i, p, False))
    for r in range(old_total + 1, old_last + 1):
        if r in raw:
            linked_rows.append(renumber_row(raw[r], r + shift))
            ht = re.search(r'\bht="([\d.]+)"', raw[r].split(">")[0])
            value_rows.append(rows.row(r + shift, value_row(book, client_cells, r, r + shift, today),
                                       float(ht.group(1)) if ht else None))
    last_new = old_last + shift

    folder = args.out_dir or os.path.dirname(os.path.abspath(args.budget))
    os.makedirs(folder, exist_ok=True)
    stem = os.path.splitext(os.path.basename(args.budget))[0]
    out_linked = free_name(folder, stem, "Claude's copy")
    out_values = free_name(folder, stem, "Client Excel")
    for o in (out_linked, out_values):
        if os.path.abspath(o) == os.path.abspath(args.budget):
            die("refusing to write over the budget itself")
    code = re.match(r"[A-Za-z]{2,6}\d{2,4}", stem)
    tab = (args.tab_name or (code.group(0).upper() if code else "Estimate"))[:31]
    tab = re.sub(r"[\[\]:*?/\\]", " ", tab)

    write_linked(book, out_linked, client, ws,
                 rebuild_sheet(client_xml, linked_rows, last_new, total_new, first, shift, old_total, True),
                 styles_xml, changes, last_new)
    write_values(book, out_values, client,
                 rebuild_sheet(client_xml, value_rows, last_new, total_new, first, shift, old_total, False),
                 styles_xml, tab, last_new)
    verify(out_linked, out_values, client, tab, data, plan, first, total_new)

    n_lines = sum(1 for p in plan if p["kind"] == "line")
    n_sections = sum(1 for p in plan if p["kind"] == "header")
    dropped = [s["name"] for s in data["sections"] if not any(l["used"] for l in s["lines"])]
    print("The budget itself was not changed: %s\n" % os.path.basename(args.budget))
    print("Wrote:")
    print("  %s\n      the whole workbook; the %s tab rebuilt and still linked to %s" % (out_linked, client, ws))
    print("  %s\n      one tab (%s), values only, no formulas, no other sheets" % (out_values, tab))
    print("\n%d sections, %d lines, numbered in sequence." % (n_sections, n_lines))
    if dropped:
        print("Left out as empty: " + ", ".join(dropped))
    if changes:
        print("\nChanged in Claude's copy (columns C and D on the worksheet, labels on the client tab only):")
        for ch in changes:
            print("  row %d, %s: %r -> %r" % (ch["row"], ch["column"], ch["was"], ch["now"]))
    print("\nChecks:")
    for ch in checks:
        print("  OK   %s: %s" % (ch["what"], money(ch["ours"])))
    print("  OK   client Excel reread: %d lines, total %s, no formulas, one sheet" % (n_lines, money(data["total"]["out"])))
    notes = line_notes(data, options)
    if notes:
        print("\nFor a person to look at:")
        for n in notes:
            print("  - " + n)
    print("\nOpen both in Excel and read them before anything goes to a client.")


def verify(out_linked, out_values, client, tab, data, plan, first, total_row):
    """Reread what was written. A file that fails here is removed, not left looking finished."""
    try:
        v = Book(out_values)
        if [n for n, _ in v.sheets] != [tab]:
            raise RuntimeError("client Excel has sheets %s" % [n for n, _ in v.sheets])
        allowed = re.compile(r"(\[Content_Types\]\.xml|_rels/\.rels|xl/workbook\.xml|xl/_rels/workbook\.xml\.rels|"
                             r"xl/worksheets/sheet1\.xml|xl/worksheets/_rels/sheet1\.xml\.rels|xl/styles\.xml|"
                             r"xl/theme/theme1\.xml|xl/drawings/drawing1\.xml|xl/drawings/_rels/drawing1\.xml\.rels|"
                             r"xl/media/image\d+\.\w+)$")
        extra = [n for n in v.names if not allowed.match(n)]
        if extra:
            raise RuntimeError("client Excel carries parts it should not: %s" % extra)
        if b"<f>" in v.parts["xl/worksheets/sheet1.xml"] or b"<f " in v.parts["xl/worksheets/sheet1.xml"]:
            raise RuntimeError("client Excel still has a formula in it")
        cells = v.cells(tab)
        want = round(sum(p["line"]["out"] for p in plan if p["kind"] == "line"), 2)
        got = round(sum(as_num(cells.get("E%d" % (first + i), {}).get("v"))
                        for i, p in enumerate(plan) if p["kind"] == "line"), 2)
        if abs(want - got) > 0.015:
            raise RuntimeError("client Excel lines add to %.2f, expected %.2f" % (got, want))
        if abs(as_num(cells.get("E%d" % total_row, {}).get("v")) - data["total"]["out"]) > 0.015:
            raise RuntimeError("client Excel total does not match the worksheet")
        k = Book(out_linked)
        for name in k.names:
            if name.endswith((".xml", ".rels")):
                ET.fromstring(k.parts[name])
        kc = k.cells(client)
        if abs(as_num(kc.get("E%d" % total_row, {}).get("v")) - data["total"]["out"]) > 0.015:
            raise RuntimeError("Claude's copy total does not match the worksheet")
    except (RuntimeError, ET.ParseError, KeyError) as e:
        for o in (out_linked, out_values):
            if os.path.exists(o):
                os.remove(o)
        die("the files failed their own check and were removed: %s" % e)
