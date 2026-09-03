#!/usr/bin/env python3
"""Calendar: agenda, availability, and sending invites (including Teams).

Timezone note that has caused real mistakes: Graph returns event and
scheduleItem times in UTC unless you send a Prefer header. Everything here
sends `Prefer: outlook.timezone="Europe/London"` so the times printed are the
times the user actually means. Never quote anyone a time taken from a raw UTC field.
"""
import datetime as dt
import sys

from . import graph

TZ = "Europe/London"
PREFER = {"Prefer": f'outlook.timezone="{TZ}"'}


def _parse_day(s):
    if not s or s == "today":
        return dt.date.today()
    if s == "tomorrow":
        return dt.date.today() + dt.timedelta(days=1)
    if s == "yesterday":
        return dt.date.today() - dt.timedelta(days=1)
    return dt.date.fromisoformat(s)


def _window(args):
    """Return (start_date, end_date_exclusive) from --day / --week / --days."""
    if args.week:
        base = _parse_day(args.week if args.week != "this" else "today")
        start = base - dt.timedelta(days=base.weekday())   # Monday
        return start, start + dt.timedelta(days=7)
    start = _parse_day(args.day)
    return start, start + dt.timedelta(days=args.days)


def _fmt(iso):
    return (iso or "").replace("T", " ")[:16]


def cmd_agenda(args):
    """Calendar events in a window, expanding recurrences."""
    start, end = _window(args)
    q = (f"/me/calendarView?startDateTime={start.isoformat()}T00:00:00"
         f"&endDateTime={end.isoformat()}T00:00:00"
         "&$select=subject,start,end,location,attendees,isAllDay,isCancelled,organizer,onlineMeetingUrl"
         "&$orderby=start/dateTime&$top=100")
    status, _, data = graph.call_retry("GET", q, headers=PREFER)
    if status != 200:
        sys.exit(f"Could not read calendar ({status}): {data}")
    items = data.get("value", [])
    if not items:
        print(f"No events {start} to {end - dt.timedelta(days=1)}.")
        return

    current = None
    for e in items:
        if e.get("isCancelled") and not args.show_cancelled:
            continue
        day = (e.get("start", {}).get("dateTime") or "")[:10]
        if day != current:
            current = day
            label = dt.date.fromisoformat(day).strftime("%a %d %b") if day else "?"
            print(f"\n{label}")
        s = _fmt(e.get("start", {}).get("dateTime"))[11:]
        t = _fmt(e.get("end", {}).get("dateTime"))[11:]
        span = "all day" if e.get("isAllDay") else f"{s}-{t}"
        loc = (e.get("location") or {}).get("displayName", "")
        online = " [Teams]" if e.get("onlineMeetingUrl") else ""
        extra = f"  ({loc})" if loc and not online else ""
        print(f"  {span:<12} {e.get('subject') or '(no subject)'}{online}{extra}")
        if args.attendees:
            names = ", ".join(
                a.get("emailAddress", {}).get("name", "") for a in e.get("attendees", [])
            )
            if names:
                print(f"               with: {names[:150]}")
    print()


def cmd_free(args):
    """Free/busy for one or more people over a window.

    Cross-checks the two representations Graph returns, because
    availabilityView follows the requested timezone while scheduleItems come
    back in UTC.
    """
    start, end = _window(args)
    body = {
        "schedules": args.who,
        "startTime": {"dateTime": f"{start.isoformat()}T{args.from_hour:02d}:00:00", "timeZone": TZ},
        "endTime": {"dateTime": f"{(end - dt.timedelta(days=1)).isoformat()}T{args.to_hour:02d}:00:00", "timeZone": TZ},
        "availabilityViewInterval": args.interval,
    }
    status, _, data = graph.call("POST", "/me/calendar/getSchedule", body, headers=PREFER)
    if status != 200:
        sys.exit(f"getSchedule failed ({status}): {data}")
    for sched in data.get("value", []):
        print(f"\n{sched.get('scheduleId')}")
        err = sched.get("error")
        if err:
            print("  no access:", err.get("message"))
            continue
        print(f"  view ({args.interval}m slots from {args.from_hour:02d}:00, 0=free 2=busy):")
        print("  " + (sched.get("availabilityView") or "(none)"))
        for item in sched.get("scheduleItems", [])[:20]:
            print(f"    {_fmt(item.get('start', {}).get('dateTime'))} "
                  f"to {_fmt(item.get('end', {}).get('dateTime'))} UTC  "
                  f"{item.get('status')}  {item.get('subject', '')}")
    print()


def cmd_invite(args):
    """Create and send a calendar invite, optionally as a Teams meeting."""
    if not args.start or not args.end:
        sys.exit("Need --start and --end, e.g. --start 2026-08-03T15:00 --end 2026-08-03T15:30")
    body = {
        "subject": args.subject,
        "start": {"dateTime": args.start, "timeZone": TZ},
        "end": {"dateTime": args.end, "timeZone": TZ},
        "attendees": [
            {"emailAddress": {"address": a}, "type": "required"}
            for a in _split(args.attendees)
        ],
    }
    if args.body:
        body["body"] = {"contentType": "HTML", "content": args.body}
    elif args.body_file:
        with open(args.body_file) as f:
            body["body"] = {"contentType": "HTML", "content": f.read()}
    if args.location:
        body["location"] = {"displayName": args.location}
    if args.teams:
        body["isOnlineMeeting"] = True
        body["onlineMeetingProvider"] = "teamsForBusiness"

    status, _, data = graph.call("POST", "/me/events", body)
    if status not in (200, 201):
        sys.exit(f"Invite failed ({status}): {data}")
    print("Invite sent.")
    print("  subject:", data.get("subject"))
    print("  when:   ", _fmt(data.get("start", {}).get("dateTime")), TZ)
    print("  id:     ", data.get("id"))
    if data.get("onlineMeeting"):
        print("  join:   ", data["onlineMeeting"].get("joinUrl"))
    print("  open in:", data.get("webLink"))


def _split(s):
    if not s:
        return []
    out = []
    for chunk in s.replace(";", ",").split(","):
        for piece in chunk.split():
            if piece.strip():
                out.append(piece.strip())
    return out


def register(sub):
    def _add_window(p):
        p.add_argument("--day", default="today", help="today, tomorrow, or YYYY-MM-DD")
        p.add_argument("--days", type=int, default=1, help="how many days from --day")
        p.add_argument("--week", nargs="?", const="this",
                       help="whole Mon-Sun week containing this date (default: this week)")

    p = sub.add_parser("agenda", help="your calendar for a day or week")
    _add_window(p)
    p.add_argument("--attendees", action="store_true", help="list attendees too")
    p.add_argument("--show-cancelled", action="store_true")
    p.set_defaults(func=cmd_agenda)

    p = sub.add_parser("free", help="free/busy for colleagues")
    p.add_argument("who", nargs="+", help="email addresses")
    _add_window(p)
    p.add_argument("--from-hour", dest="from_hour", type=int, default=8)
    p.add_argument("--to-hour", dest="to_hour", type=int, default=19)
    p.add_argument("--interval", type=int, default=30, help="slot size in minutes")
    p.set_defaults(func=cmd_free)

    p = sub.add_parser("invite", help="create and send a calendar invite")
    p.add_argument("--subject", required=True)
    p.add_argument("--start", help="YYYY-MM-DDTHH:MM in Europe/London")
    p.add_argument("--end", help="YYYY-MM-DDTHH:MM in Europe/London")
    p.add_argument("--attendees", help="comma separated email addresses")
    p.add_argument("--location")
    p.add_argument("--body")
    p.add_argument("--body-file", dest="body_file")
    p.add_argument("--teams", action="store_true", help="make it a Teams meeting")
    p.set_defaults(func=cmd_invite)
