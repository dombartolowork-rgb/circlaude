"""What you asked Claude, and when: Claude Code sessions as timesheet evidence.

    circle claude-activity                       yesterday
    circle claude-activity --date 2026-10-26     one day
    circle claude-activity --date 2026-10-19 --to 2026-10-23
    circle claude-activity --date 2026-10-26 --gap 30 --prompts 0

Claude Code keeps every session on this machine, in ~/.claude/projects/<folder>/
<session>.jsonl. The prompts the person typed are the record of what they were
working on and when, which fills the gaps the calendar and Sent Items leave: an
afternoon in Claude on a budget, an edit or a brief leaves no meeting and often
no email until the end.

Prompts are grouped per session into blocks. A session's title only describes how
it started, and one session often covers several jobs, so judge each block by its
prompts, not the title. Two windows open at once give overlapping blocks: count the
clock time once: a new block starts after --gap
minutes with no prompt and no reply. A block runs from its first prompt to the
last reply Claude gave inside it, so the time Claude spent working counts, but a
reply that lands after the gap (a background job finishing at night) does not.

Only typed prompts count, including ones sent while Claude was busy. Tool output,
subagents, system text and slash-command plumbing are skipped. Anything that
looks like a key or password is masked before it is printed. Conversations on
claude.ai or in the Claude app's chat are not on this machine, so they are not
covered.
"""
import datetime
import glob
import json
import os
import re

LOCAL = datetime.datetime.now().astimezone().tzinfo
SECRET = re.compile(r"[A-Za-z0-9_\-\.]{28,}")   # tokens, keys: long and unbroken
# the summary Claude Code writes when a long session is compacted, not a typed prompt
CONTINUED = "This session is being continued from a previous conversation"


def _root():
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(base, "projects")


def _when(ts):
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(LOCAL)
    except (AttributeError, ValueError):
        return None


def _prompt_text(d):
    """The typed text of a user record, or None if it is not a typed prompt."""
    if d.get("isMeta") or d.get("isSidechain"):
        return None
    content = (d.get("message") or {}).get("content")
    if isinstance(content, list):
        if any(isinstance(p, dict) and p.get("type") == "tool_result" for p in content):
            return None
        content = " ".join(p.get("text", "") for p in content
                           if isinstance(p, dict) and p.get("type") == "text")
    if not isinstance(content, str):
        return None
    text = content.strip()
    # slash-command plumbing, hook output and notifications all arrive as tagged text
    if not text or text.startswith(("<", "[Request interrupted", CONTINUED)):
        return None
    return text


def _clean(text, width):
    # links stay whole; any other long unbroken string is treated as a key
    words = [w if w.startswith(("http", "www.")) else SECRET.sub("[key hidden]", w)
             for w in text.split()]
    text = " ".join(words)
    return text if len(text) <= width else text[:width - 3] + "..."


def _read_session(path, lo, hi):
    """Prompts and reply times inside [lo, hi), plus the session's title."""
    prompts, replies, title, folder = [], [], None, None
    seen = set()
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"ai-title"' in line:
                try:
                    title = json.loads(line).get("aiTitle") or title
                except ValueError:
                    pass
                continue
            if '"timestamp"' not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            when = _when(d.get("timestamp"))
            if when is None or not lo <= when < hi:
                continue
            folder = folder or d.get("cwd")
            kind = d.get("type")
            text = None
            if kind == "user":
                text = _prompt_text(d)
            elif kind == "attachment" and (d.get("attachment") or {}).get("type") == "queued_command":
                text = ((d.get("attachment") or {}).get("prompt") or "").strip() or None
                if text and text.startswith("<"):
                    text = None
            elif kind == "assistant" and not d.get("isSidechain"):
                replies.append(when)
            if text:
                key = (text[:200], when.strftime("%H:%M"))
                if key not in seen:   # a queued prompt can be recorded twice
                    seen.add(key)
                    prompts.append((when, text))
    return prompts, replies, title, folder


def _blocks(prompts, replies, gap):
    """Group prompts into blocks, each extended to the last reply before the gap."""
    events = sorted([(t, "p", x) for t, x in prompts] + [(t, "r", None) for t in replies],
                    key=lambda e: e[0])
    blocks, cur = [], None
    for t, kind, text in events:
        if cur and t - cur["last"] > gap:
            blocks.append(cur)
            cur = None
        if cur is None:
            if kind != "p":
                continue   # replies with no prompt in reach belong to nothing
            cur = {"start": t, "last": t, "prompts": []}
        cur["last"] = t
        if kind == "p":
            cur["prompts"].append((t, text))
    if cur:
        blocks.append(cur)
    return blocks


def cmd_activity(args):
    today = datetime.date.today()
    first = datetime.date.fromisoformat(args.date) if args.date else today - datetime.timedelta(days=1)
    last = datetime.date.fromisoformat(args.to) if args.to else first
    if last < first:
        raise RuntimeError("--to is before --date.")
    lo = datetime.datetime.combine(first, datetime.time(), LOCAL)
    hi = datetime.datetime.combine(last + datetime.timedelta(days=1), datetime.time(), LOCAL)
    gap = datetime.timedelta(minutes=args.gap)

    root = _root()
    if not os.path.isdir(root):
        raise RuntimeError(f"No Claude Code sessions found at {root}.")
    found = []
    for path in glob.glob(os.path.join(root, "*", "*.jsonl")):
        # a session last written before the period cannot hold anything in it
        if datetime.datetime.fromtimestamp(os.path.getmtime(path), LOCAL) < lo:
            continue
        prompts, replies, title, folder = _read_session(path, lo, hi)
        for b in _blocks(prompts, replies, gap):
            b["title"] = title or "(untitled session)"
            b["folder"] = folder or os.path.basename(os.path.dirname(path))
            found.append(b)

    found.sort(key=lambda b: b["start"])
    if args.json:
        out = [{"date": b["start"].date().isoformat(), "start": b["start"].strftime("%H:%M"),
                "end": b["last"].strftime("%H:%M"),
                "minutes": round((b["last"] - b["start"]).total_seconds() / 60),
                "session": b["title"], "folder": b["folder"],
                "prompts": [{"time": t.strftime("%H:%M"), "text": _clean(x, 400)} for t, x in b["prompts"]]}
               for b in found]
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return
    if not found:
        print(f"No Claude prompts between {first} and {last}.")
        return
    day = None
    for b in found:
        if b["start"].date() != day:
            day = b["start"].date()
            print(f"\n{day.strftime('%a %d %b %Y')} (local time)")
        mins = round((b["last"] - b["start"]).total_seconds() / 60)
        home = b["folder"].replace(os.path.expanduser("~"), "~")
        print(f"  {b['start']:%H:%M}-{b['last']:%H:%M}  {mins:>3} min  {len(b['prompts']):>2} prompts  "
              f"session: {_clean(b['title'], 50)}  [{home}]")
        shown = b["prompts"] if args.prompts < 0 else b["prompts"][:args.prompts]
        for t, x in shown:
            print(f"      {t:%H:%M}  {_clean(x, args.width)}")
        if shown and len(shown) < len(b["prompts"]):
            print(f"      ... {len(b['prompts']) - len(shown)} more")
    print("\nBlock times are Claude activity, not proof of hours: where a block overlaps a "
          "meeting, count the meeting.")


def register(sub):
    p = sub.add_parser("claude-activity",
                       help="what you asked Claude and when, grouped into blocks, as timesheet evidence")
    p.add_argument("--date", help="YYYY-MM-DD, default yesterday")
    p.add_argument("--to", help="YYYY-MM-DD, last day of a range")
    p.add_argument("--gap", type=int, default=20, help="minutes of silence that end a block (default 20)")
    p.add_argument("--prompts", type=int, default=6, help="prompts shown per block, -1 for all, 0 for none")
    p.add_argument("--width", type=int, default=110, help="characters shown per prompt")
    p.add_argument("--json", action="store_true", help="machine-readable, every prompt")
    p.set_defaults(func=cmd_activity)
