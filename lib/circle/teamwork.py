#!/usr/bin/env python3
"""Teamwork: project code lookup, timesheet audit, and time logging.

Uses the Teamwork v1 REST API directly. The Teamwork MCP tools are disabled in
Circle's org AI settings (they 403 with "MCP is disabled in the AI settings"),
so REST is the only route that works.

Auth comes from the TEAMWORK_API_KEY environment variable. Never hard-code it,
never print it, never write it to a file.

Hard rule carried over from the original logger: `log` is a DRY RUN unless you
pass --commit, and --commit needs the user's explicit go in that same turn. A wrong
project code books a client's money to the wrong job.
"""
import base64
import collections
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DOMAIN = os.environ.get("TEAMWORK_DOMAIN", "circleagency.eu.teamwork.com")
BASE = f"https://{DOMAIN}"

# Set TEAMWORK_PERSON_ID to skip the /me.json lookup; otherwise the key's
# own account is used, so time can never land on someone else by default.
PERSON_ID = os.environ.get("TEAMWORK_PERSON_ID")
INTERNAL_PROJECT = os.environ.get("TEAMWORK_INTERNAL_PROJECT", "354873")

FULL_DAY_HOURS = float(os.environ.get("TEAMWORK_DAY_HOURS", "8"))  # used to flag light days

_ME_CACHE = {}


def person_id():
    """The id time is audited and logged against: env override, else /me.json."""
    if PERSON_ID:
        return PERSON_ID
    if "id" not in _ME_CACHE:
        me = api("GET", "/me.json").get("person", {})
        if not me.get("id"):
            raise TeamworkError("Could not resolve your Teamwork person id from /me.json")
        _ME_CACHE["id"] = str(me["id"])
    return _ME_CACHE["id"]


class TeamworkError(Exception):
    pass


def _auth():
    key = os.environ.get("TEAMWORK_API_KEY")
    if not key:
        raise TeamworkError(
            "TEAMWORK_API_KEY is not set. Export it in your shell first:\n"
            "  export TEAMWORK_API_KEY='...'\n"
            "Get one from Teamwork > your avatar > Edit My Details > API & Mobile."
        )
    return "Basic " + base64.b64encode(f"{key}:X".encode()).decode()


def api(method, path, body=None, tries=3):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(tries):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", _auth())
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as r:
                out = r.read()
                return json.loads(out) if out else {}
        except urllib.error.HTTPError as e:
            payload = (e.read() or b"").decode(errors="replace")
            if e.code in (429, 502, 503) and attempt < tries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            raise TeamworkError(f"{method} {path} -> {e.code}: {payload[:300]}")
        except urllib.error.URLError as e:
            if attempt < tries - 1:
                time.sleep(2)
                continue
            raise TeamworkError(f"{method} {path} -> {e.reason}")


def _norm(s):
    return "".join(str(s or "").lower().split())


def _ymd(iso):
    """YYYY-MM-DD to the YYYYMMDD the API wants."""
    try:
        return dt.date.fromisoformat(iso).strftime("%Y%m%d")
    except (ValueError, TypeError):
        raise TeamworkError(f'Bad date "{iso}", expected YYYY-MM-DD')


def load_projects(status="active"):
    """Every project, paged. Needed because code matching is a substring match."""
    all_p, page = [], 1
    while True:
        data = api("GET", f"/projects.json?status={status}&pageSize=250&page={page}")
        batch = data.get("projects", [])
        all_p.extend(batch)
        if len(batch) < 250 or page > 20:
            return all_p
        page += 1


# --- commands -------------------------------------------------------------

def cmd_projects(args):
    """Find a project code and its numeric id.

    The tracker, not Teamwork, is authoritative for NEW job numbers. This tells
    you what already exists in Teamwork so time can be logged to it.
    """
    projects = load_projects("all" if args.all else "active")
    term = _norm(args.search)
    hits = [p for p in projects if term in _norm(p.get("name"))] if term else projects
    if not hits:
        print(f"No {'' if args.all else 'active '}project matching '{args.search}'.")
        print("If the job exists in the tracker but not Teamwork, it needs creating")
        print("before time will log against it (see the circle-new-project skill).")
        return
    for p in sorted(hits, key=lambda p: p.get("name", "")):
        state = p.get("status", "")
        mark = "" if state == "active" else f"  [{state}]"
        print(f"{p.get('id'):>8}  {p.get('name')}{mark}")
        if args.verbose:
            print(f"          company: {(p.get('company') or {}).get('name', '?')}")


def cmd_tasks(args):
    """List tasks in a project. Defaults to Non-billable activities.

    Internal time books to a TASK inside 354873, not the bare project, so this
    is how you find the right task id (holiday, expenses, social media, etc).
    """
    pid = args.project or INTERNAL_PROJECT
    data = api("GET", f"/projects/{pid}/tasks.json?pageSize=250")
    tasks = data.get("todo-items", [])
    if not tasks:
        print(f"No tasks in project {pid}.")
        return
    term = _norm(args.search) if args.search else None
    for t in tasks:
        name = t.get("content", "")
        if term and term not in _norm(name):
            continue
        print(f"{t.get('id'):>10}  {name}")


def cmd_logged(args):
    """What is already logged in a date range, summed per day.

    Run this BEFORE logging anything, to avoid double-logging, and to answer
    "did I log all my time for w/c 13th?". Days under a full day are flagged.
    """
    frm, to = _resolve_range(args)
    path = (f"/time_entries.json?fromdate={frm.strftime('%Y%m%d')}"
            f"&todate={to.strftime('%Y%m%d')}&userId={args.user or person_id()}&pageSize=500")
    data = api("GET", path)
    entries = data.get("time-entries", [])
    if not entries:
        print(f"Nothing logged {frm} to {to}.")
        return

    by_day = collections.defaultdict(list)
    for e in entries:
        day = (e.get("date") or "")[:10]
        by_day[day].append(e)

    grand = 0.0
    for day in sorted(by_day):
        rows = by_day[day]
        total = sum(float(r.get("hours", 0)) + float(r.get("minutes", 0)) / 60 for r in rows)
        grand += total
        try:
            label = dt.date.fromisoformat(day).strftime("%a %d %b")
        except ValueError:
            label = day
        flag = "" if total >= FULL_DAY_HOURS - 0.01 else f"   << light, {FULL_DAY_HOURS - total:.2f}h short"
        print(f"\n{label}  {total:.2f}h{flag}")
        if not args.summary:
            for r in sorted(rows, key=lambda r: r.get("date", "")):
                mins = float(r.get("hours", 0)) * 60 + float(r.get("minutes", 0))
                bill = "B" if str(r.get("isbillable")) in ("1", "true", "True") else "i"
                start = (r.get("date") or "")[11:16]
                print(f"    {start}  {mins / 60:>5.2f}h {bill}  "
                      f"{(r.get('project-name') or '?')[:34]:<34} {(r.get('description') or '')[:40]}")

    days = len(by_day)
    print(f"\nTotal {grand:.2f}h across {days} day(s).")
    # Only meaningful for a Mon-Fri window.
    workdays = sum(1 for i in range((to - frm).days + 1)
                   if (frm + dt.timedelta(days=i)).weekday() < 5)
    if workdays:
        target = workdays * FULL_DAY_HOURS
        print(f"Target for {workdays} working day(s): {target:.2f}h "
              f"({'over by' if grand > target else 'short by'} {abs(grand - target):.2f}h)")


def cmd_log(args):
    """Log time from an entries JSON file. Dry run unless --commit.

    Entry shape (same as the original teamwork-logger.js, so old files work):
      {"project": "CCEP393", "projectId": 365891, "taskId": 16625652,
       "date": "2026-07-28", "startTime": "09:00", "hours": 1, "minutes": 30,
       "billable": true, "description": "..."}
    Give projectId or taskId to skip the name lookup entirely.
    """
    if not os.path.exists(args.entries):
        sys.exit(f"Entries file not found: {args.entries}")
    with open(args.entries) as f:
        entries = json.load(f)
    if not isinstance(entries, list):
        sys.exit("The entries file must contain a JSON array.")

    print(f"Mode: {'COMMIT (will log time)' if args.commit else 'DRY RUN (posts nothing)'}")
    print(f"Site: {BASE}")
    print(f"Logging as person id: {args.user or person_id()}\n")

    projects = load_projects()
    planned = []
    for i, e in enumerate(entries, 1):
        pid = e.get("projectId")
        pname, note = None, ""
        if not pid and e.get("project"):
            code = _norm(e["project"])
            hits = [p for p in projects if code in _norm(p.get("name"))]
            if len(hits) == 1:
                pid, pname = hits[0]["id"], hits[0]["name"]
            elif not hits:
                note = (f'NO PROJECT MATCH for "{e["project"]}". It may not exist in '
                        "Teamwork yet. Add a projectId, or create the project.")
            else:
                note = (f'AMBIGUOUS "{e["project"]}" matches {len(hits)}: '
                        + " | ".join(f"{h['name']} (id {h['id']})" for h in hits)
                        + " - set projectId")
        elif pid:
            match = next((p for p in projects if str(p["id"]) == str(pid)), None)
            pname = match["name"] if match else "(id given, not in active list)"
        elif not e.get("taskId"):
            note = "No project, projectId or taskId given"

        dur = f"{e.get('hours', 0)}h {e.get('minutes', 0)}m"
        bill = "BILLABLE" if e.get("billable") else "internal"
        target = f"task {e['taskId']}" if e.get("taskId") else (f"project {pid}" if pid else "???")
        print(f"#{i}  {e.get('description') or '(no description)'}")
        print(f"    {e.get('date')}  {e.get('startTime', '09:00')}  {dur}  {bill}"
              f"  -> {pname or e.get('project', '')} ({target})")
        if note:
            print(f"    !! {note}")
        print()
        planned.append((e, pid, note))

    total = sum(float(e.get("hours", 0)) + float(e.get("minutes", 0)) / 60 for e, _, _ in planned)
    billable = sum(float(e.get("hours", 0)) + float(e.get("minutes", 0)) / 60
                   for e, _, _ in planned if e.get("billable"))
    bad = sum(1 for _, _, n in planned if n)
    print(f"{len(planned)} entries, {total:.2f}h total "
          f"({billable:.2f}h billable, {total - billable:.2f}h internal), {bad} need attention.")

    if not args.commit:
        print("\nDry run complete. Nothing was logged.")
        print("Show this summary to the user and get an explicit go before re-running with --commit.")
        return
    if bad:
        sys.exit(f"\nRefusing to commit: {bad} entr{'y' if bad == 1 else 'ies'} unresolved. "
                 "Fix the project codes first.")

    ok = fail = 0
    for e, pid, _ in planned:
        payload = {"time-entry": {
            "description": e.get("description", ""),
            "person-id": args.user or person_id(),
            "date": _ymd(e.get("date")),
            "time": e.get("startTime", "09:00"),
            "hours": e.get("hours", 0),
            "minutes": e.get("minutes", 0),
            "isbillable": "1" if e.get("billable") else "0",
        }}
        path = (f"/tasks/{e['taskId']}/time_entries.json" if e.get("taskId")
                else f"/projects/{pid}/time_entries.json")
        try:
            api("POST", path, payload)
            print(f"OK    {e.get('description')}")
            ok += 1
        except TeamworkError as err:
            print(f"FAIL  {e.get('description')}: {err}")
            fail += 1
        time.sleep(0.4)  # gentle on rate limits
    print(f"\nDone. {ok} logged, {fail} failed.")


def cmd_whoami(args):
    me = api("GET", "/me.json").get("person", {})
    print(f"{me.get('first-name', '')} {me.get('last-name', '')}".strip())
    print("id:   ", me.get("id"))
    print("email:", me.get("email-address"))
    print("site: ", BASE)


def _resolve_range(args):
    """Resolve --from/--to, or --week, into two dates."""
    if args.week is not None:
        base = dt.date.today() if args.week in ("this", None) else dt.date.fromisoformat(args.week)
        if args.week == "last":
            base = dt.date.today() - dt.timedelta(days=7)
        mon = base - dt.timedelta(days=base.weekday())
        return mon, mon + dt.timedelta(days=6)
    if args.frm and args.to:
        return dt.date.fromisoformat(args.frm), dt.date.fromisoformat(args.to)
    if args.frm:
        d = dt.date.fromisoformat(args.frm)
        return d, d
    today = dt.date.today()
    mon = today - dt.timedelta(days=today.weekday())
    return mon, mon + dt.timedelta(days=6)


def register(sub):
    p = sub.add_parser("tw-projects", help="find a Teamwork project code and its numeric id")
    p.add_argument("search", nargs="?", default="", help="code, campaign or job name")
    p.add_argument("--all", action="store_true", help="include non-active projects")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_projects)

    p = sub.add_parser("tw-tasks", help="list tasks in a project (default: Non-billable activities)")
    p.add_argument("--project", help=f"project id (default {INTERNAL_PROJECT})")
    p.add_argument("--search", help="filter task names")
    p.set_defaults(func=cmd_tasks)

    p = sub.add_parser("tw-logged", help="what is already logged, summed per day")
    p.add_argument("--from", dest="frm", help="YYYY-MM-DD")
    p.add_argument("--to", help="YYYY-MM-DD")
    p.add_argument("--week", nargs="?", const="this",
                   help="this, last, or any YYYY-MM-DD inside the week")
    p.add_argument("--user", help="Teamwork person id (default: you)")
    p.add_argument("--summary", action="store_true", help="day totals only")
    p.set_defaults(func=cmd_logged)

    p = sub.add_parser("tw-log", help="log time from an entries JSON file (dry run by default)")
    p.add_argument("entries", nargs="?", default="entries.json")
    p.add_argument("--commit", action="store_true",
                   help="actually post the entries; needs the user's explicit go")
    p.add_argument("--user", help="Teamwork person id (default: you)")
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("tw-whoami", help="confirm the Teamwork account and person id")
    p.set_defaults(func=cmd_whoami)
