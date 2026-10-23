#!/usr/bin/env python3
"""The Project Tracker: the authority on job codes and client services leads.

This is the reason Orbit keeps its own narrow Microsoft sign-in. The workbook is
83 sheets, over 1MB and edited live by client services, and the Microsoft 365
connector can neither read a single sheet of it (it truncates after the first
few) nor edit a cell. Graph's workbook API does both.

  circle tracker sheets                   every client sheet
  circle tracker sheet Subway             the live rows of one sheet
  circle tracker next Subway              the first pre-numbered row with no job
  circle tracker find SUB133 CCEP399      codes to rows, and codes it cannot find
  circle tracker find --text notes.txt    every code mentioned in some text

Read-only. Writing a row is done in the new-project skill, inside a persisted
workbook session, because a sessionless PATCH returns 200 and does not stick.
"""
import re
import sys
import urllib.parse

from . import graph

TRACKER_DRIVE = "b!btnAx0EMLUaFyzSCxuDrhOoZ9iBVLqhMoaIg-ctFYgk8FFSkIzgKRZsYdgK9oiXv"
TRACKER_ITEM = "01LHYCQA575R6LB4GBZVI2EFJVZ7YDCTJB"
BOOK = f"/drives/{TRACKER_DRIVE}/items/{TRACKER_ITEM}/workbook"

# Sheets that are not a client's job list.
NOT_CLIENTS = {"contents", "notes"}

# Used until the tracker has been read and the real prefixes are known.
DEFAULT_PREFIXES = ["CCEP", "SUB", "FR", "CC"]


def norm_code(s):
    return re.sub(r"[\s-]", "", s or "").upper()


def code_regex(prefixes):
    alts = "|".join(sorted({re.escape(p) for p in prefixes if p}, key=len, reverse=True))
    return re.compile(rf"\b((?:{alts})\s?-?\d{{3}}(?:_\d{{2}})?)\b", re.I)


def find_codes(pattern, *texts):
    """Every job code mentioned across some strings, de-duplicated, in order."""
    out = []
    for t in texts:
        for m in pattern.finditer(t or ""):
            code = norm_code(m.group(1))
            if code not in out:
                out.append(code)
    return out


def sheets():
    st, _, d = graph.call_retry("GET", f"{BOOK}/worksheets?$select=name")
    if st != 200:
        raise RuntimeError(f"could not list tracker sheets ({st}): {d}")
    return [w["name"] for w in d.get("value", []) if w["name"].lower() not in NOT_CLIENTS]


def _first_row(address):
    """'Subway'!A1:V240 -> 1. The Excel row number of the first used row."""
    m = re.search(r"!\$?[A-Z]+\$?(\d+)", address or "")
    return int(m.group(1)) if m else 1


def read_sheet(sheet, live_only=True):
    """Rows of one client sheet as dicts, with their real Excel row number.

    Columns: A CLIENT, B PROJECT NO., C DESCRIPTION, D CLIENT CONTACT,
    E CLIENT SERVICES LEAD, F PROJECT MANAGER, G DEADCODE, H APPROVED.
    Headers sit on row 5, above them is a title block, so rows are only taken
    after the header row is seen.
    """
    st, _, d = graph.call_retry(
        "GET", f"{BOOK}/worksheets/{urllib.parse.quote(sheet)}"
               "/usedRange(valuesOnly=true)?$select=address,values")
    if st != 200:
        raise RuntimeError(f"sheet {sheet} returned {st}")
    start = _first_row(d.get("address"))
    rows, seen_header = [], False
    for i, row in enumerate(d.get("values") or []):
        row = [str(c).strip() for c in row] + [""] * 8
        if not seen_header:
            seen_header = row[1].upper().startswith("PROJECT NO")
            continue
        code = norm_code(row[1])
        if not code:
            continue
        dead = "deadcode" in (row[6] + row[7]).lower()
        if live_only and dead:
            continue
        rows.append({
            "sheet": sheet, "row": start + i, "code": code, "description": row[2],
            "client_contact": row[3], "cs_lead": row[4], "pm": row[5], "dead": dead,
        })
    return rows


def read_all(names=None):
    out = []
    for s in names or sheets():
        try:
            out += read_sheet(s)
        except RuntimeError as e:
            print(f"  ({e})", file=sys.stderr)
    return out


def resolve(seen, tracker):
    """Pair codes with their tracker rows. Unknown codes are returned, not dropped.

    A code with no tracker row is worth surfacing: codes have lived in Teamwork
    and not the tracker, and one code has briefly pointed at two jobs.
    """
    by_code = {}
    for r in tracker:
        if r["description"]:
            by_code.setdefault(r["code"], r)
    hits, unknown = [], []
    for code in seen:
        row = by_code.get(code)
        if row:
            hits.append(dict(row, seen_as=code))
            continue
        subs = [r for c, r in by_code.items() if c.startswith(code + "_")]
        if subs:
            hits.append(dict(subs[0], seen_as=code,
                             description=subs[0]["description"] + " (sub-code row)"))
        else:
            unknown.append(code)
    return hits, unknown


def _print_row(r):
    lead = r["cs_lead"] or "(no lead)"
    print(f"  {r.get('seen_as', r['code']):<11} {r['description'][:50]:<50} "
          f"lead: {lead[:18]:<18} [{r['sheet']} row {r['row']}]")
    if r["client_contact"]:
        print(f"              client contact: {r['client_contact'][:60]}")


def cmd_sheets(args):
    for s in sheets():
        print(s)


def cmd_sheet(args):
    rows = read_sheet(args.name, live_only=not args.all)
    for r in rows:
        if r["description"] or args.all:
            _print_row(r)
    print(f"\n{len(rows)} rows. The tracker is edited live, so this is a reading, not a ruling.")


def cmd_next(args):
    rows = read_sheet(args.name, live_only=False)
    free = [r for r in rows if not r["description"] and not r["dead"]]
    if not free:
        sys.exit(f"No pre-numbered empty row on {args.name}. Ask client services "
                 "to extend the sheet rather than inventing a code.")
    r = free[0]
    print(f"Next free code on {args.name}: {r['code']}  (row {r['row']})")
    print("Before claiming it: search Teamwork for the same code. If either system")
    print("already uses it, stop and ask. Re-read this just before writing the row,")
    print("because client services edit the tracker while you work.")


def cmd_find(args):
    tracker = read_all()
    prefixes = {re.match(r"[A-Z]+", r["code"]).group(0)
                for r in tracker if re.match(r"[A-Z]+\d", r["code"])}
    pattern = code_regex(prefixes | set(DEFAULT_PREFIXES))
    seen = [norm_code(c) for c in args.codes]
    if args.text:
        text = sys.stdin.read() if args.text == "-" else open(args.text, encoding="utf-8").read()
        seen += [c for c in find_codes(pattern, text) if c not in seen]
    hits, unknown = resolve(seen, tracker)
    print(f"Read {len(tracker)} live rows from the tracker.\n")
    for r in hits:
        _print_row(r)
    if unknown:
        print(f"\n  NOT in the tracker: {', '.join(unknown)}")
        print("  Check Teamwork before assuming these are wrong. A code in one system")
        print("  and not the other is a collision worth raising, not a typo to fix.")


def register(sub):
    p = sub.add_parser("tracker", help="read the Project Tracker: sheets, rows, next free code, code lookup")
    tsub = p.add_subparsers(dest="tracker_cmd", required=True, metavar="<action>")

    tsub.add_parser("sheets", help="list the client sheets").set_defaults(func=cmd_sheets)

    q = tsub.add_parser("sheet", help="the live rows of one client sheet")
    q.add_argument("name", help='sheet name, e.g. "Subway"')
    q.add_argument("--all", action="store_true", help="include dead codes and empty rows")
    q.set_defaults(func=cmd_sheet)

    q = tsub.add_parser("next", help="the first pre-numbered row with no job on it")
    q.add_argument("name", help='sheet name, e.g. "Subway"')
    q.set_defaults(func=cmd_next)

    q = tsub.add_parser("find", help="look codes up, or find every code in some text")
    q.add_argument("codes", nargs="*", help="job codes, e.g. SUB133 CCEP399")
    q.add_argument("--text", metavar="FILE",
                   help="also scan this file for codes ('-' for stdin)")
    q.set_defaults(func=cmd_find)
