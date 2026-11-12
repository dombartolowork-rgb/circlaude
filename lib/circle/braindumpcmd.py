#!/usr/bin/env python3
"""Brain dump: a call written up as a Word document in Circle's typography.

Reading the call (Fathom summary and transcript, the invite, any follow-up
mail) happens through the connectors inside Claude. See
`skills/circle-brain-dump/SKILL.md` for that half and for the judgement. This
module only does the mechanical step:

  circle braindump-links notes.txt                  every URL in a text file, de-duplicated
  circle braindump-render plan.json --out dump.docx

The plan is JSON:

  {"title": "...", "call": "...", "date": "...", "attendees": ["..."],
   "source": {"label": "Fathom recording", "url": "https://..."},
   "summary": "one paragraph" | ["points"],
   "sections": [{"heading": "...", "text": "...", "points": ["..."]}],
   "decisions": ["..."],
   "actions": [{"action": "...", "who": "...", "when": "..."}],
   "open_questions": ["..."],
   "links": [{"label": "...", "url": "https://...", "from": "who shared it", "note": "why it matters"}]}

Every key but title is optional, and an empty one leaves its section out.
"""
import json
import os
import re
import sys

URL_RE = re.compile(r"https?://[^\s<>\"'\)\]]+")


def register(sub):
    p = sub.add_parser("braindump-render",
                       help="a brain dump plan (JSON) to a Word doc in Circle's typography")
    p.add_argument("plan", help="the plan JSON")
    p.add_argument("--out", required=True, help="output .docx path")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("braindump-links",
                       help="list every URL in one or more text files, de-duplicated")
    p.add_argument("files", nargs="+", help="text files: a transcript, a summary, an email")
    p.set_defaults(func=cmd_links)


def find_links(text):
    """URLs in reading order, de-duplicated, with trailing punctuation removed."""
    seen, out = set(), []
    for m in URL_RE.finditer(text):
        u = m.group(0).rstrip(".,;:!?")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _points(v):
    if not v:
        return []
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v if str(x).strip()]
    return [str(v)]


def render_plan(plan):
    from . import docxbuild
    d = docxbuild.Doc()
    d.heading(plan.get("title") or "Brain dump", 1)

    head = [("Call", plan.get("call")),
            ("Date", plan.get("date")),
            ("On the call", ", ".join(_points(plan.get("attendees")))),
            ("Written up by", plan.get("author"))]
    rows = [[{"text": k, "bold": True, "fill": docxbuild.GREY_FILL}, str(v)]
            for k, v in head if v]
    if rows:
        d.table(rows, widths=[22, 78])
    src = plan.get("source") or {}
    if src.get("url"):
        d.link(src.get("label") or "Recording", src["url"])

    summary = _points(plan.get("summary"))
    if summary:
        d.heading("In short", 2)
        if len(summary) == 1:
            d.para(summary[0])
        else:
            d.bullets(summary)

    for s in plan.get("sections") or []:
        d.heading(s.get("heading") or "Notes", 2)
        for t in _points(s.get("text")):
            d.para(t)
        if s.get("points"):
            d.bullets(_points(s["points"]))

    if plan.get("decisions"):
        d.heading("Decided", 2)
        d.bullets(_points(plan["decisions"]))

    actions = plan.get("actions") or []
    if actions:
        d.heading("Actions", 2)
        d.table([["Action", "Who", "By when"]]
                + [[str(a.get("action") or ""), str(a.get("who") or ""),
                    str(a.get("when") or "")] for a in actions],
                widths=[60, 20, 20], header=True)

    if plan.get("open_questions"):
        d.heading("Still open", 2)
        d.bullets(_points(plan["open_questions"]))

    links = [l for l in (plan.get("links") or []) if l.get("url")]
    if links:
        d.heading("Links shared", 2)
        for l in links:
            d.link(l.get("label") or l["url"], l["url"],
                   note=("from " + l["from"]) if l.get("from") else None)
            if l.get("note"):
                d._para(docxbuild._run(str(l["note"]), docxbuild.BODY_FONT,
                                       docxbuild.SIZES["meta"],
                                       colour=docxbuild.GREY_INK), after=8)
    return d, len(links)


def cmd_render(args):
    from . import docxbuild
    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)
    blob = json.dumps(plan, ensure_ascii=False)
    if "\u2014" in blob or "\u2013" in blob:
        sys.exit("The plan contains an em or en dash. House style: use a comma, "
                 "brackets, a colon, a full stop or a spaced hyphen, then render again.")
    missing = docxbuild.check_fonts()
    if missing:
        print("WARNING: not installed, so Word will substitute: "
              + ", ".join(missing), file=sys.stderr)
    d, n_links = render_plan(plan)
    d.save(args.out)
    print(f"Wrote {args.out} ({os.path.getsize(args.out):,} bytes)")
    print(f"  sections: {len(plan.get('sections') or [])}, "
          f"actions: {len(plan.get('actions') or [])}, links: {n_links}")
    print("\nSaved on this computer only. Show the user what is in it before "
          "filing or sending it anywhere.")


def cmd_links(args):
    text = ""
    for path in args.files:
        with open(path, encoding="utf-8", errors="replace") as f:
            text += f.read() + "\n"
    links = find_links(text)
    for u in links:
        print(u)
    print(f"\n{len(links)} link(s).", file=sys.stderr)
