#!/usr/bin/env python3
"""Mail: read, search, send, draft and threaded replies via Microsoft Graph.

Read side (inbox / sent / search / read / thread) plus compose, drafts and
threaded replies. Sending is gated: see cmd_send and _reply_or_draft.
"""
import base64
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse

from . import graph

# Graph message ids are ~150 characters, which makes any listing unreadable and
# expensive to pass around. So every listing numbers its results and caches the
# mapping; any command that takes an id accepts the short number instead.
IDMAP_FILE = os.path.join(graph.CONFIG_DIR, "idmap.json")


def _remember(items):
    """Cache short number -> full id for the messages just listed."""
    try:
        os.makedirs(graph.CONFIG_DIR, mode=0o700, exist_ok=True)
        with open(IDMAP_FILE, "w") as f:
            json.dump([m["id"] for m in items], f)
    except OSError:
        pass  # a broken cache must never break a listing


def resolve_id(value):
    """Turn a short number from the last listing into a full Graph message id."""
    if value is None or not str(value).isdigit() or len(str(value)) > 4:
        return value
    n = int(value)
    try:
        with open(IDMAP_FILE) as f:
            ids = json.load(f)
    except (OSError, ValueError):
        sys.exit(f"No cached listing to resolve #{n}. Run circle inbox (or search) first, "
                 "or pass the full message id.")
    if not 1 <= n <= len(ids):
        sys.exit(f"#{n} is out of range: the last listing had {len(ids)} message(s).")
    return ids[n - 1]

# Folders you can name on the command line.
FOLDERS = {
    "inbox": "inbox",
    "sent": "sentitems",
    "drafts": "drafts",
    "deleted": "deleteditems",
    "archive": "archive",
}

SELECT = "id,subject,from,toRecipients,ccRecipients,receivedDateTime,isRead,hasAttachments,conversationId,bodyPreview,webLink"


# --- helpers --------------------------------------------------------------

def _split(addrs):
    """Split a comma / semicolon / space separated address string into a list."""
    if not addrs:
        return []
    out = []
    for chunk in addrs.replace(";", ",").split(","):
        for piece in chunk.split():
            if piece.strip():
                out.append(piece.strip())
    return out


def _recipients(addrs):
    return [{"emailAddress": {"address": a}} for a in addrs]


def _editor_body():
    editor = os.environ.get("EDITOR", "notepad" if os.name == "nt" else "nano")
    with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as f:
        path = f.name
    try:
        subprocess.call([editor, path])
        with open(path) as f:
            return f.read()
    finally:
        os.unlink(path)


def _resolve_body(args):
    if getattr(args, "body", None) is not None:
        return args.body
    if getattr(args, "body_file", None):
        with open(args.body_file) as f:
            return f.read()
    body = _editor_body()
    if not body.strip():
        sys.exit("Aborted: empty body.")
    return body


def _attachments(paths):
    out = []
    for p in paths or []:
        with open(p, "rb") as f:
            data = f.read()
        out.append({
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": os.path.basename(p),
            "contentBytes": base64.b64encode(data).decode(),
        })
    return out


def _addr(m):
    return (m.get("from") or {}).get("emailAddress", {}).get("address", "")


def _name(m):
    """Who the message is with. Drafts have no sender, so show the recipient."""
    ea = (m.get("from") or {}).get("emailAddress", {})
    who = ea.get("name") or ea.get("address", "")
    if who:
        return who
    to = m.get("toRecipients") or []
    if to:
        first = to[0].get("emailAddress", {})
        label = first.get("name") or first.get("address", "")
        more = f" +{len(to) - 1}" if len(to) > 1 else ""
        return f"to {label}{more}"
    return "(no recipient)"


def _when(m):
    return (m.get("receivedDateTime") or "").replace("T", " ")[:16]


def _print_list(items, show_preview=False, show_ids=False):
    """Print a numbered listing. The numbers are usable as ids in later commands."""
    if not items:
        print("Nothing found.")
        return
    _remember(items)
    for i, m in enumerate(items, 1):
        flag = " " if m.get("isRead", True) else "*"
        clip = "@" if m.get("hasAttachments") else " "
        print(f"[{i:>2}]{flag}{clip} {_when(m)}  {_name(m)[:24]:<24}  "
              f"{(m.get('subject') or '(no subject)')[:60]}")
        if show_preview and m.get("bodyPreview"):
            print(f"        {' '.join(m['bodyPreview'].split())[:160]}")
        if show_ids:
            print(f"        id: {m['id']}")
    print(f"\n{len(items)} message(s). Use the [number] as the id, "
          "e.g. circle read 3, circle reply 3 --body '...'")


# Deliberately NOT anchored to line starts: Outlook's HTML often collapses its
# whole quote header onto one line, so an anchored pattern silently never matches.
QUOTE_MARKERS = [
    re.compile(r"_{8,}"),                                  # Outlook's divider
    re.compile(r"-{2,}\s*Original Message\s*-{2,}", re.I),
    re.compile(r"From:.{0,120}?\bSent:", re.S),             # Outlook quote header
    re.compile(r"On .{5,80}?wrote:"),                      # Gmail / Apple style
]


def _split_quote(text):
    """Return (new_text, quoted_history). Quoted history is usually noise."""
    cut = None
    for pat in QUOTE_MARKERS:
        m = pat.search(text)
        if m and (cut is None or m.start() < cut):
            cut = m.start()
    if cut is None:
        return text, ""
    return text[:cut].rstrip(), text[cut:].strip()


def _html_to_text(s):
    """Crude HTML to text, good enough to read an email body in a terminal."""
    s = re.sub(r"(?is)<(script|style).*?</\1>", "", s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</(p|div|tr|h[1-6]|li)>", "\n", s)
    s = re.sub(r"(?i)<li[^>]*>", "  - ", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    lines = [ln.rstrip() for ln in s.split("\n")]
    out, blanks = [], 0
    for ln in lines:                     # collapse runs of blank lines
        if ln.strip():
            out.append(ln)
            blanks = 0
        elif blanks == 0:
            out.append("")
            blanks = 1
    return "\n".join(out).strip()


# --- read commands --------------------------------------------------------

def cmd_list(args):
    """List a mail folder, newest first."""
    folder = FOLDERS.get(args.folder, args.folder)
    q = (f"/me/mailFolders/{folder}/messages?$top={args.limit}"
         f"&$select={SELECT}&$orderby=receivedDateTime desc")
    if args.unread:
        q += "&$filter=isRead eq false"
    status, _, data = graph.call_retry("GET", q)
    if status != 200:
        sys.exit(f"Could not list {args.folder} ({status}): {data}")
    _print_list(data.get("value", []), show_preview=args.preview,
                show_ids=getattr(args, "ids", False))


def cmd_search(args):
    """Full-text search across subject and body.

    $search is fuzzy and ranked, so verify hits rather than trusting the first.
    It cannot be combined with $orderby, hence no sort here.
    """
    term = urllib.parse.quote(f'"{args.query}"')
    scope = f"/me/mailFolders/{FOLDERS.get(args.folder, args.folder)}" if args.folder else "/me"
    status, _, data = graph.call_retry(
        "GET", f"{scope}/messages?$search={term}&$select={SELECT}&$top={args.limit}"
    )
    if status != 200:
        sys.exit(f"Search failed ({status}): {data}")
    _print_list(data.get("value", []), show_preview=args.preview,
                show_ids=getattr(args, "ids", False))


def cmd_read(args):
    """Print one message in full, with its recipients and attachment names."""
    args.id = resolve_id(args.id)
    status, _, m = graph.call(
        "GET", f"/me/messages/{args.id}?$select=id,subject,from,toRecipients,"
               "ccRecipients,receivedDateTime,body,hasAttachments,conversationId,webLink"
    )
    if status != 200:
        sys.exit(f"Could not read message ({status}): {m}")

    def addrs(key):
        return ", ".join(
            r["emailAddress"].get("address", "") for r in m.get(key, [])
        ) or "(none)"

    print("Subject:", m.get("subject") or "(no subject)")
    print("From:   ", f"{_name(m)} <{_addr(m)}>")
    print("To:     ", addrs("toRecipients"))
    if m.get("ccRecipients"):
        print("Cc:     ", addrs("ccRecipients"))
    print("Date:   ", _when(m))
    print("Thread: ", m.get("conversationId"))
    print("Open:   ", m.get("webLink"))
    body = m.get("body", {})
    raw = body.get("content", "")
    text = _html_to_text(raw) if body.get("contentType") == "html" else raw.strip()
    print("\n" + ("-" * 70) + "\n")
    fresh, quoted = _split_quote(text)
    print(fresh)
    if quoted:
        if args.quote:
            print("\n" + ("-" * 30) + " quoted history " + ("-" * 24) + "\n")
            print(quoted)
        else:
            lines = len(quoted.split("\n"))
            print(f"\n[{lines} more line(s) of quoted history omitted, use --quote to see it]")

    if m.get("hasAttachments"):
        st, _, att = graph.call(
            "GET", f"/me/messages/{args.id}/attachments?$select=id,name,size,isInline,contentType"
        )
        if st == 200 and att.get("value"):
            print("\nAttachments:")
            for a in att["value"]:
                inline = " (inline)" if a.get("isInline") else ""
                print(f"  - {a.get('name')}  {a.get('size', 0)} bytes{inline}")
                print(f"    id: {a.get('id')}")


def cmd_thread(args):
    """Every message in a conversation, oldest first, across all folders.

    This is what tells you whether the user already replied from their phone: the
    thread view spans Inbox and Sent Items together.
    """
    cid = args.conversation_id
    if not cid:  # accept a message id and resolve its thread
        args.id = resolve_id(args.id)
        st, _, m = graph.call("GET", f"/me/messages/{args.id}?$select=conversationId")
        if st != 200:
            sys.exit(f"Could not resolve thread ({st}): {m}")
        cid = m["conversationId"]
    q = urllib.parse.quote(f"conversationId eq '{cid}'")
    status, _, data = graph.call_retry(
        "GET", f"/me/messages?$filter={q}&$select={SELECT}&$top=50"
    )
    if status != 200:
        sys.exit(f"Could not load thread ({status}): {data}")
    items = sorted(data.get("value", []), key=lambda m: m.get("receivedDateTime", ""))
    if not items:
        print("No messages in that thread.")
        return
    _remember(items)
    for i, m in enumerate(items, 1):
        print(f"[{i:>2}] {_when(m)}  {_name(m)[:28]:<28}  {(m.get('subject') or '')[:50]}")
        if m.get("bodyPreview"):
            print(f"     {' '.join(m['bodyPreview'].split())[:150]}")
        print()
    print(f"{len(items)} message(s), oldest first. The [number] is now the id to use.")


def cmd_attachment(args):
    """Save one attachment to disk (use for inline screenshots too)."""
    args.id = resolve_id(args.id)
    status, _, a = graph.call("GET", f"/me/messages/{args.id}/attachments/{args.attachment_id}")
    if status != 200:
        sys.exit(f"Could not fetch attachment ({status}): {a}")
    data = base64.b64decode(a.get("contentBytes", ""))
    out = args.out or a.get("name", "attachment.bin")
    with open(out, "wb") as f:
        f.write(data)
    print(f"Saved {out} ({len(data)} bytes)")


# --- write commands -------------------------------------------------------

def _build_message(args):
    to = _split(args.to)
    if not to:
        sys.exit("Need at least one --to recipient.")
    msg = {
        "subject": args.subject or "",
        "body": {
            "contentType": "HTML" if args.html else "Text",
            "content": _resolve_body(args),
        },
        "toRecipients": _recipients(to),
    }
    if args.cc:
        msg["ccRecipients"] = _recipients(_split(args.cc))
    if args.bcc:
        msg["bccRecipients"] = _recipients(_split(args.bcc))
    att = _attachments(args.attach)
    if att:
        msg["attachments"] = att
    return msg


def cmd_send(args):
    if not args.send_now:
        # Sending is deliberately gated: without --send-now this saves a draft
        # so the text can be reviewed before anything leaves the account.
        cmd_draft(args)
        print("NOT SENT. Review it, then: circle send-draft <id>  "
              "(or re-run with --send-now).")
        return
    msg = _build_message(args)
    status, _, data = graph.call(
        "POST", "/me/sendMail", {"message": msg, "saveToSentItems": True}
    )
    if status == 202:
        print(f"Sent to {args.to}.")
    else:
        sys.exit(f"Send failed ({status}): {data}")


def cmd_draft(args):
    msg = _build_message(args)
    status, _, data = graph.call("POST", "/me/messages", msg)
    if status in (200, 201):
        print("Draft saved.")
        print("  id:     ", data.get("id"))
        print("  open in:", data.get("webLink"))
    else:
        sys.exit(f"Draft failed ({status}): {data}")


def cmd_send_draft(args):
    args.id = resolve_id(args.id)
    status, _, data = graph.call("POST", f"/me/messages/{args.id}/send")
    if status == 202:
        print("Draft sent.")
    else:
        sys.exit(f"Send failed ({status}): {data}")


def cmd_delete(args):
    args.id = resolve_id(args.id)
    status, _, data = graph.call("DELETE", f"/me/messages/{args.id}")
    if status == 204:
        print("Deleted (moved to Deleted Items).")
    else:
        sys.exit(f"Delete failed ({status}): {data}")


def _body_to_html(body_text, is_html):
    """Wrap a body for prepending above a quoted reply.

    Graph reply drafts are always HTML, so plain text is escaped and split
    into <div> lines (blank lines become <div><br></div>) to keep the breaks.
    """
    if is_html:
        return body_text
    out = []
    for line in body_text.split("\n"):
        out.append("<div>" + html.escape(line) + "</div>" if line.strip() else "<div><br></div>")
    return "".join(out)


def _prepare_reply(args, reply_all):
    """Create a threaded reply draft, inject body + attachments, return its id.

    createReply / createReplyAll let Graph handle the threading headers
    (In-Reply-To / References), the quoted original, and the recipient list.
    reply-all auto-includes every original To/Cc and excludes you.
    """
    args.id = resolve_id(args.id)
    body_text = _resolve_body(args)
    action = "createReplyAll" if reply_all else "createReply"
    status, _, draft = graph.call("POST", f"/me/messages/{args.id}/{action}")
    if status not in (200, 201):
        sys.exit(f"Could not create reply ({status}): {draft}")
    draft_id = draft["id"]

    status, _, full = graph.call("GET", f"/me/messages/{draft_id}?$select=id,body,webLink")
    if status != 200:
        sys.exit(f"Could not read reply draft ({status}): {full}")
    quoted = full.get("body", {}).get("content", "")
    status, _, data = graph.call(
        "PATCH",
        f"/me/messages/{draft_id}",
        {"body": {"contentType": "HTML",
                  "content": _body_to_html(body_text, args.html) + "<br>" + quoted}},
    )
    if status not in (200, 201):
        sys.exit(f"Could not set reply body ({status}): {data}")

    for att in _attachments(args.attach):
        status, _, data = graph.call("POST", f"/me/messages/{draft_id}/attachments", att)
        if status not in (200, 201):
            sys.exit(f"Attachment failed ({status}): {data}")

    return draft_id, full.get("webLink")


def _reply_or_draft(args, reply_all):
    draft_id, weblink = _prepare_reply(args, reply_all=reply_all)
    if not args.send_now:
        print("Reply draft saved (NOT sent).")
        print("  id:     ", draft_id)
        print("  open in:", weblink)
        print("Review it, then: circle send-draft <id>  (or re-run with --send-now).")
        return
    status, _, data = graph.call("POST", f"/me/messages/{draft_id}/send")
    if status != 202:
        sys.exit(f"Send failed ({status}): {data}")
    print("Reply-all sent." if reply_all else "Reply sent.")


def cmd_reply(args):
    _reply_or_draft(args, reply_all=False)


def cmd_reply_all(args):
    _reply_or_draft(args, reply_all=True)


def cmd_draft_reply(args):
    draft_id, weblink = _prepare_reply(args, reply_all=args.all)
    print("Reply draft saved.")
    print("  id:     ", draft_id)
    print("  open in:", weblink)


# --- argparse wiring ------------------------------------------------------

def _add_send_args(p):
    p.add_argument("--to", required=True, help="recipient(s), comma separated")
    p.add_argument("--cc")
    p.add_argument("--bcc")
    p.add_argument("--subject", default="")
    p.add_argument("--body", help="body text; omit to open $EDITOR")
    p.add_argument("--body-file", dest="body_file", help="read the body from a file")
    p.add_argument("--html", action="store_true", help="treat the body as HTML")
    p.add_argument("--attach", action="append", help="file to attach (repeatable)")


def _add_reply_args(p):
    p.add_argument("id", help="id of the message being replied to")
    p.add_argument("--body", help="body text; omit to open $EDITOR")
    p.add_argument("--body-file", dest="body_file", help="read the body from a file")
    p.add_argument("--html", action="store_true")
    p.add_argument("--attach", action="append")


def register(sub):
    p = sub.add_parser("inbox", help="list the inbox, newest first")
    p.add_argument("--limit", type=int, default=15)
    p.add_argument("--unread", action="store_true", help="unread only")
    p.add_argument("--preview", action="store_true", help="show a body preview")
    p.add_argument("--ids", action="store_true", help="also print full Graph ids")
    p.set_defaults(func=cmd_list, folder="inbox")

    p = sub.add_parser("sent", help="list Sent Items (check before assuming a reply is owed)")
    p.add_argument("--limit", type=int, default=15)
    p.add_argument("--preview", action="store_true")
    p.add_argument("--ids", action="store_true")
    p.set_defaults(func=cmd_list, folder="sent", unread=False)

    p = sub.add_parser("folder", help="list any named mail folder")
    p.add_argument("folder", help="inbox, sent, drafts, deleted, archive, or a folder id")
    p.add_argument("--limit", type=int, default=15)
    p.add_argument("--unread", action="store_true")
    p.add_argument("--preview", action="store_true")
    p.add_argument("--ids", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("search", help="full-text search subject and body")
    p.add_argument("query")
    p.add_argument("--folder", help="restrict to one folder, e.g. sent")
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--preview", action="store_true")
    p.add_argument("--ids", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("read", help="print one message in full")
    p.add_argument("id")
    p.add_argument("--quote", action="store_true",
                   help="include the quoted history below the new text")
    p.set_defaults(func=cmd_read)

    p = sub.add_parser("thread", help="every message in a conversation, oldest first")
    p.add_argument("id", nargs="?", help="a message id in the thread")
    p.add_argument("--conversation-id", dest="conversation_id")
    p.set_defaults(func=cmd_thread)

    p = sub.add_parser("attachment", help="save an attachment to disk")
    p.add_argument("id", help="message id")
    p.add_argument("attachment_id")
    p.add_argument("--out")
    p.set_defaults(func=cmd_attachment)

    p = sub.add_parser("send", help="compose and send (drafts unless --send-now)")
    _add_send_args(p)
    p.add_argument("--send-now", dest="send_now", action="store_true",
                   help="actually send; without it the message is saved to Drafts")
    p.set_defaults(func=cmd_send)

    p = sub.add_parser("draft", help="compose and save to Drafts")
    _add_send_args(p)
    p.set_defaults(func=cmd_draft)

    p = sub.add_parser("drafts", help="list recent drafts with their ids")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--preview", action="store_true")
    p.add_argument("--ids", action="store_true")
    p.set_defaults(func=cmd_list, folder="drafts", unread=False)

    p = sub.add_parser("send-draft", help="send an existing draft by id")
    p.add_argument("id")
    p.set_defaults(func=cmd_send_draft)

    p = sub.add_parser("delete", help="delete a message or draft by id")
    p.add_argument("id")
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("reply", help="threaded reply to the sender (drafts unless --send-now)")
    _add_reply_args(p)
    p.add_argument("--send-now", dest="send_now", action="store_true",
                   help="actually send; without it the reply is saved to Drafts")
    p.set_defaults(func=cmd_reply)

    p = sub.add_parser("reply-all", help="threaded reply to everyone (drafts unless --send-now)")
    _add_reply_args(p)
    p.add_argument("--send-now", dest="send_now", action="store_true",
                   help="actually send; without it the reply is saved to Drafts")
    p.set_defaults(func=cmd_reply_all)

    p = sub.add_parser("draft-reply", help="threaded reply saved to Drafts")
    _add_reply_args(p)
    p.add_argument("--all", action="store_true", help="reply to all recipients")
    p.set_defaults(func=cmd_draft_reply)
