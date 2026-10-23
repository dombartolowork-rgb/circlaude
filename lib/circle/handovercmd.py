#!/usr/bin/env python3
"""Handover: build the leave handover document and put it where Circle keeps them.

Gathering the signal (mail, calendar, Teams, Fathom) happens through the
Microsoft 365 connector inside Claude, and job codes are pinned with
`circle tracker find`. See `skills/circle-handover/SKILL.md` for that half and
for the judgement. This module only does the two mechanical steps:

  circle handover-render plan.json --out handover.docx
  circle handover-upload handover.docx        (only on the user's explicit go)
"""
import datetime as dt
import json
import os
import sys

from . import graph
from .trackercmd import TRACKER_DRIVE


def register(sub):
    p = sub.add_parser("handover-render",
                       help="a handover plan (JSON) to a Word doc in Circle's format")
    p.add_argument("plan", help="the plan JSON")
    p.add_argument("--out", required=True, help="output .docx path")
    p.add_argument("--mono", action="store_true",
                   help="no traffic-light colour, just the words")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("handover-upload",
                       help="put a finished handover in WOW- Team Handover Documents")
    p.add_argument("file", help="the .docx to upload")
    p.add_argument("--month", help='target subfolder, default this month, e.g. "October 2026"')
    p.add_argument("--name", help="filename on SharePoint, default the local name")
    p.set_defaults(func=cmd_upload)




# --- rendering and upload -------------------------------------------------

# Circle's own handover format, taken from the most recent one in
# "WOW- Team Handover Documents": a header block, then one block per project
# with its number, then an action table of Item / Action / Who / Deadline.
# Matching it matters more than any layout invented here: a covering colleague
# already knows how to read this one.
# Bare hex, no leading "#": OOXML rejects the CSS spelling and Word then shows
# the cell unshaded rather than complaining.
LIGHTS = {
    "active": ("ACTIVE PROJECT", "C00000", "FBE4E4"),
    "attention": ("MAY NEED ATTENTION", "BF8F00", "FDF2D0"),
    "unlikely": ("UNLIKELY TO NEED WORK", "375623", "E2EFDA"),
}
LIGHT_ORDER = ["active", "attention", "unlikely"]

HANDOVER_FOLDER = "/General/WOW- Team Handover Documents"


def _text(v):
    """A string or a list of points, as one cell's worth of text."""
    if isinstance(v, (list, tuple)):
        return "\n".join(str(x) for x in v)
    return str(v or "")


def render_plan(plan, mono=False):
    """A handover plan (JSON) into a document in Circle's own handover format."""
    from . import docxbuild
    d = docxbuild.Doc()
    d.heading(plan.get("title") or "Annual Leave Handover", 1)

    head = [("Name", plan.get("name")),
            ("Last day before leave", plan.get("last_day")),
            ("Return date", plan.get("return_date")),
            ("Covering", plan.get("covering")),
            ("Team upcoming leave", plan.get("team_leave"))]
    d.table([[{"text": k, "bold": True, "fill": docxbuild.GREY_FILL},
              _text(v)] for k, v in head if v], widths=[26, 74])

    if plan.get("preamble"):
        d.para(_text(plan["preamble"]))

    for status in LIGHT_ORDER:
        group = [p for p in plan.get("projects", []) if p.get("status") == status]
        if not group:
            continue
        label, ink, fill = LIGHTS[status]
        d.heading(f"{label} ({len(group)})", 2)
        for p in group:
            rows = [[{"text": "Project name", "bold": True, "fill": docxbuild.GREY_FILL},
                     {"text": _text(p.get("name")), "bold": True}],
                    [{"text": "Project number", "bold": True, "fill": docxbuild.GREY_FILL},
                     _text(p.get("code") or "no code found")],
                    [{"text": "Status", "bold": True, "fill": docxbuild.GREY_FILL},
                     {"text": label, "bold": True,
                      "fill": None if mono else fill,
                      "ink": None if mono else ink}]]
            for key, title in (("lead", "Client services lead"),
                               ("client_contact", "Client contact"),
                               ("where_it_is", "Where it is up to"),
                               ("in_window", "Happening while I am out"),
                               ("watch_out", "Do not get this wrong")):
                if p.get(key):
                    rows.append([{"text": title, "bold": True,
                                  "fill": docxbuild.GREY_FILL}, _text(p[key])])
            d.table(rows, widths=[26, 74])

            actions = p.get("actions") or []
            if actions:
                d.table([["Item / category", "Action required",
                          "Person responsible", "Deadline / notes"]]
                        + [[_text(a.get("item")), _text(a.get("required")),
                            _text(a.get("who")), _text(a.get("deadline"))]
                           for a in actions],
                        widths=[20, 44, 18, 18], header=True)

    if plan.get("notes"):
        d.heading("Anything else", 2)
        d.para(_text(plan["notes"]))
    return d


def cmd_render(args):
    from . import docxbuild
    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)
    missing = docxbuild.check_fonts()
    if missing:
        print("WARNING: not installed, so Word will substitute: "
              + ", ".join(missing), file=sys.stderr)
    render_plan(plan, mono=args.mono).save(args.out)

    counts = {}
    for p in plan.get("projects", []):
        counts[p.get("status", "unset")] = counts.get(p.get("status", "unset"), 0) + 1
    print(f"Wrote {args.out} ({os.path.getsize(args.out):,} bytes)")
    for k in LIGHT_ORDER + ["unset"]:
        if counts.get(k):
            print(f"  {LIGHTS.get(k, ('UNSET',))[0]:<22} {counts[k]}")
    print("\nNot uploaded. Show the user the content in chat first, then "
          "`circle handover-upload` on their go.")


def cmd_upload(args):
    """Put a finished handover in the folder Circle already keeps them in.

    Outward facing: this lands in a shared agency folder, so it is deliberately
    a separate command from building the document.
    """
    if not os.path.exists(args.file):
        sys.exit(f"No such file: {args.file}")
    month = args.month or dt.date.today().strftime("%B %Y")
    name = args.name or os.path.basename(args.file)
    path = f"{HANDOVER_FOLDER}/{month}/{name}"
    size = os.path.getsize(args.file)
    with open(args.file, "rb") as f:
        data = f.read()

    if size > 4 * 1024 * 1024:
        sys.exit("Over 4 MB, which needs a Graph upload session. "
                 "A handover document should never be this big: check the file.")
    st, _, d = graph.call_retry(
        "PUT", f"/drives/{TRACKER_DRIVE}/root:{path}:/content",
        body=data, content_type=("application/vnd.openxmlformats-officedocument"
                                 ".wordprocessingml.document"))
    if st not in (200, 201):
        sys.exit(f"Upload failed ({st}): {d}")
    print(f"Uploaded to {path}")
    print("Link:", (d or {}).get("webUrl", "(no webUrl returned)"))
