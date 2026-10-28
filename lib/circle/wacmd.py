"""WhatsApp, through a small bridge program that runs in the background.

    circle wa-connect                    link this laptop to your WhatsApp: opens the code in your browser
    circle wa-status                     is it running, is a phone linked, how fresh are the messages
    circle wa-chats [--query NAME]       chats, most recently active first
    circle wa-read <chat> [--limit N]    one chat's messages, oldest first
    circle wa-search <text> [--chat C]   find messages containing some text
    circle wa-who <name>                 look up a contact's number
    circle wa-send <chat> --text "..."   send a message (or --file to send a file)
    circle wa-media <msg-id> --chat C    download a photo, video or document from a message
    circle wa-start / wa-stop            start or stop the bridge
    circle wa-disconnect --yes           unlink this laptop and delete its copy of your messages

The bridge is a copy of the open-source whatsapp-mcp bridge (tools/whatsapp/bridge),
built in advance for Windows and Mac so nobody installs anything. It links as one of
the "linked devices" on the person's phone, the same as WhatsApp Web, keeps a copy of
their messages in ~/.circle/whatsapp, and listens only on this laptop.

Pairing opens a page in their browser that always shows the current code, because
WhatsApp changes it every 20 seconds or so. Once a phone is linked, the bridge is
set to start by itself at login: a login item on Windows, a launchd agent on a Mac.

This is the person's own WhatsApp, family chats and all. Sending is gated by the
confirm hook, and the skill says to work only with work chats.
"""
import datetime
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

PORT = 8094   # not the upstream 8080, so it never collides with another bridge
LABEL = "com.circleagency.orbit.whatsapp"
RUN_KEY_NAME = "OrbitWhatsApp"

CIRCLE_DIR = os.path.join(os.path.expanduser("~"), ".circle")
WA_DIR = os.path.join(CIRCLE_DIR, "whatsapp")
STORE = os.path.join(WA_DIR, "store")
MESSAGES_DB = os.path.join(STORE, "messages.db")
DEVICE_DB = os.path.join(STORE, "whatsapp.db")
TOKEN_FILE = os.path.join(STORE, ".bridge-token")
LOG_FILE = os.path.join(WA_DIR, "bridge.log")
# The bridge only sends files from under this folder (see media_path.go).
OUTBOX = os.path.join(os.path.expanduser("~"), ".local", "share", "whatsapp-mcp", "outbox")

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WINDOWS = os.name == "nt"
MAC = sys.platform == "darwin"


class WhatsAppError(RuntimeError):
    pass


# ---------------------------------------------------------------- the program

def _shipped_binary():
    machine = platform.machine().lower()
    if WINDOWS:
        # Windows on ARM runs the x64 build through its own emulation.
        name = "whatsapp-bridge-windows-amd64.exe"
    elif MAC:
        if machine not in ("arm64", "aarch64"):
            raise WhatsAppError("WhatsApp needs an Apple Silicon Mac (M1 or later) for now. "
                                "Ask Dom for an Intel build.")
        name = "whatsapp-bridge-darwin-arm64"
    else:
        raise WhatsAppError("WhatsApp is only built for Windows and Mac.")
    path = os.path.join(PLUGIN_ROOT, "tools", "whatsapp", "bin", name)
    if not os.path.isfile(path):
        raise WhatsAppError(f"The WhatsApp program is missing from Orbit ({name}). "
                            "Ask Dom for an update.")
    return path


def _installed_binary():
    return os.path.join(WA_DIR, "bin", "whatsapp-bridge.exe" if WINDOWS else "whatsapp-bridge")


def _install_binary():
    """Copy the program out of the plugin, whose folder changes with every update,
    to a fixed place the login item can point at. Returns True if it changed."""
    src, dst = _shipped_binary(), _installed_binary()
    if os.path.isfile(dst) and os.path.getsize(dst) == os.path.getsize(src) \
            and _same_file(src, dst):
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".new"
    shutil.copyfile(src, tmp)
    if not WINDOWS:
        os.chmod(tmp, 0o755)
    if MAC:
        # A copy that arrived through a download or sync can carry the quarantine
        # flag, and then macOS refuses to run it with no explanation.
        subprocess.run(["xattr", "-d", "com.apple.quarantine", tmp],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.replace(tmp, dst)
    return True


def _same_file(a, b):
    with open(a, "rb") as fa, open(b, "rb") as fb:
        while True:
            ca, cb = fa.read(1 << 20), fb.read(1 << 20)
            if ca != cb:
                return False
            if not ca:
                return True


def _args():
    return [_installed_binary(), "-dir", WA_DIR, "-port", str(PORT),
            "-log", LOG_FILE, "-no-webhook"]


# ---------------------------------------------------------------- running it

def _token():
    try:
        with open(TOKEN_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _http(path, body=None, timeout=10):
    url = f"http://127.0.0.1:{PORT}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("Authorization", "Bearer " + _token())
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"message": raw.decode("utf-8", "replace")[:300]}
    except (urllib.error.URLError, OSError):
        return None, {}


def _running():
    st, _ = _http("/api/health", timeout=3)
    return st is not None


def _paired():
    """A phone is linked once the device table has a row. The health check says
    "connected" even while it is still waiting for a scan, so do not use that."""
    if not os.path.isfile(DEVICE_DB):
        return False
    try:
        with _ro(DEVICE_DB) as c:
            return c.execute("SELECT count(*) FROM whatsmeow_device").fetchone()[0] > 0
    except sqlite3.Error:
        return False


def _launchd_plist():
    return os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents", LABEL + ".plist")


def _write_launchd():
    args = "".join(f"<string>{_xml(a)}</string>" for a in _args())
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{LABEL}</string>
  <key>ProgramArguments</key><array>{args}</array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>ThrottleInterval</key><integer>30</integer>
</dict></plist>
"""
    path = _launchd_plist()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(plist)
    return path


def _xml(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _gui():
    return f"gui/{os.getuid()}"


def _start():
    """Start the bridge so it outlives this command and Claude's own session."""
    if MAC:
        path = _write_launchd()
        subprocess.run(["launchctl", "bootout", f"{_gui()}/{LABEL}"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        r = subprocess.run(["launchctl", "bootstrap", _gui(), path],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise WhatsAppError("Could not start the WhatsApp program: " + r.stderr.strip())
    else:
        # Through WMI, so the new process belongs to Windows rather than to Claude's
        # shell, and is not closed with it.
        cmdline = subprocess.list2cmdline(_args())
        ps = ("$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
              "-Arguments @{CommandLine=$env:ORBIT_WA_CMD}; exit $r.ReturnValue")
        env = dict(os.environ, ORBIT_WA_CMD=cmdline)
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           capture_output=True, text=True, env=env)
        if r.returncode != 0:
            raise WhatsAppError("Could not start the WhatsApp program: "
                                + (r.stderr or r.stdout).strip()[:300])
    for _ in range(40):
        if _running() and _token():
            return
        time.sleep(0.5)
    raise WhatsAppError("The WhatsApp program did not start. " + _log_tail())


def _stop():
    if MAC:
        subprocess.run(["launchctl", "bootout", f"{_gui()}/{LABEL}"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.run(["taskkill", "/F", "/IM", "whatsapp-bridge.exe"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(20):
        if not _running():
            return
        time.sleep(0.5)


def _set_login_item(on):
    """Mac: the launchd agent already runs at login. Windows: the Run key."""
    if not WINDOWS:
        if not on and os.path.isfile(_launchd_plist()):
            os.remove(_launchd_plist())
        return
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                         r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                         winreg.KEY_SET_VALUE)
    try:
        if on:
            winreg.SetValueEx(key, RUN_KEY_NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(_args()))
        else:
            try:
                winreg.DeleteValue(key, RUN_KEY_NAME)
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)


def _login_item_set():
    if not WINDOWS:
        return os.path.isfile(_launchd_plist())
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run")
        winreg.QueryValueEx(key, RUN_KEY_NAME)
        return True
    except OSError:
        return False


def _log_tail(n=8):
    try:
        with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
            lines = [l.rstrip() for l in f if l.strip()]
        return "Last lines of " + LOG_FILE + ":\n  " + "\n  ".join(lines[-n:])
    except OSError:
        return ""


def ensure_running():
    if not _paired():
        raise WhatsAppError("WhatsApp is not connected on this laptop yet. "
                            "Run `circle wa-connect` (or /orbit:onboard).")
    if _running():
        return
    if _install_binary() or not _running():
        _start()


def _freshen():
    """Reading works from the saved copy even when the bridge is down, but start it
    if we can, so what we read is current."""
    if _paired() and not _running():
        try:
            ensure_running()
        except WhatsAppError:
            print("(WhatsApp is not running, so this may be missing the newest messages.)")


# ---------------------------------------------------------------- commands

def cmd_connect(args):
    if _paired() and _running() and not args.again:
        print("WhatsApp is already connected on this laptop.")
        _set_login_item(True)
        return
    if args.again and _paired():
        print("Unlinking the old session first.")
        _forget()

    if _running():
        _stop()
    _install_binary()
    _start()

    url = f"http://127.0.0.1:{PORT}/pair?t={_token()}"
    opened = False if args.no_browser else _open(url)
    if opened:
        print("The WhatsApp code is open in your browser.")
    else:
        print("Open this page in your browser to see the WhatsApp code:")
        print("  " + url)
    print("On your phone: WhatsApp > Settings (or the three dots on Android) > "
          "Linked devices > Link a device, then point it at the code.")
    sys.stdout.flush()

    deadline = time.time() + args.wait
    while time.time() < deadline:
        if _paired():
            _set_login_item(True)
            print("CONNECTED: WhatsApp is linked. It will start by itself whenever "
                  "this laptop starts. Older messages keep arriving for a few minutes.")
            return
        if not _running():
            raise WhatsAppError("The codes ran out before a phone scanned one. "
                                "Run `circle wa-connect` again when the phone is ready.")
        time.sleep(2)
    print("WAITING: no phone has scanned the code yet. The page stays live for a few "
          "minutes. Run `circle wa-status` to check.")


def _open(url):
    try:
        if WINDOWS:
            os.startfile(url)  # noqa: the default browser
            return True
        if MAC:
            return subprocess.run(["open", url]).returncode == 0
        return webbrowser.open(url)
    except Exception:
        return False


def cmd_status(args):
    paired, running = _paired(), _running()
    print("WhatsApp")
    print("  phone linked:   ", "yes" if paired else "no")
    print("  running:        ", "yes" if running else "no")
    if running:
        st, d = _http("/api/health")
        print("  online:         ", "yes" if d.get("connected") else "no")
    print("  starts at login:", "yes" if _login_item_set() else "no")
    if os.path.isfile(MESSAGES_DB):
        with _ro(MESSAGES_DB) as c:
            n = c.execute("SELECT count(*) FROM messages").fetchone()[0]
            newest = c.execute("SELECT max(timestamp) FROM messages").fetchone()[0]
        print(f"  messages:        {n:,}, newest {_when(newest)}")
    if not paired:
        print("\nNot linked yet: run `circle wa-connect`.")
    elif not running:
        print("\nLinked but not running: run `circle wa-start`.")


def cmd_start(args):
    ensure_running()
    print("WhatsApp is running.")


def cmd_stop(args):
    _stop()
    print("WhatsApp is stopped. It will start again at the next login, or with "
          "`circle wa-start`.")


def _forget():
    _stop()
    if _running():
        raise WhatsAppError("Could not stop the WhatsApp program, so nothing was deleted.")
    _set_login_item(False)
    shutil.rmtree(STORE, ignore_errors=True)


def cmd_disconnect(args):
    if not args.yes:
        raise WhatsAppError("This deletes this laptop's copy of your WhatsApp messages. "
                            "Run it again with --yes to go ahead.")
    _forget()
    print("Done. This laptop is unlinked and its copy of your messages is deleted.")
    print("To finish, remove it on your phone too: WhatsApp > Linked devices, tap "
          "the Orbit entry, Log out.")


# ---------------------------------------------------------------- reading

def _ro(path):
    uri = "file:" + path.replace("\\", "/") + "?mode=ro"
    if WINDOWS and not uri.startswith("file:/"):
        uri = "file:/" + uri[5:]
    c = sqlite3.connect(uri, uri=True, timeout=10)
    return c


def _messages_db():
    if not os.path.isfile(MESSAGES_DB):
        raise WhatsAppError("WhatsApp is not connected on this laptop yet. "
                            "Run `circle wa-connect` (or /orbit:onboard).")
    return _ro(MESSAGES_DB)


def _parse_ts(ts):
    if not ts:
        return None
    s = str(ts).replace("T", " ")
    s = re.sub(r"(\.\d{6})\d+", r"\1", s)          # nanoseconds down to micro
    s = re.sub(r"([+-]\d\d)(\d\d)$", r"\1:\2", s)   # +0100 to +01:00
    s = s.replace("Z", "+00:00")
    try:
        d = datetime.datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    return d.astimezone()


def _when(ts):
    d = _parse_ts(ts)
    return d.strftime("%a %d %b %H:%M") if d else "?"


def _since(text):
    """'2026-10-01', '7d', 'yesterday' or 'today', as the stored timestamp format."""
    if not text:
        return None
    now = datetime.datetime.now().astimezone()
    t = text.strip().lower()
    if t == "today":
        d = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif t == "yesterday":
        d = (now - datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif re.fullmatch(r"\d+d", t):
        d = now - datetime.timedelta(days=int(t[:-1]))
    else:
        d = datetime.datetime.fromisoformat(text).astimezone()
    return d.astimezone(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class _Names:
    """Phone numbers to names, from the chat list and WhatsApp's own contact list."""

    def __init__(self, conn):
        self.conn, self.cache = conn, {}
        self.dev = _ro(DEVICE_DB) if os.path.isfile(DEVICE_DB) else None

    def __call__(self, sender):
        if not sender:
            return "?"
        if sender in self.cache:
            return self.cache[sender]
        bare = sender.split("@")[0]
        name = None
        if self.dev:
            try:
                row = self.dev.execute(
                    "SELECT full_name, push_name, first_name, business_name FROM whatsmeow_contacts "
                    "WHERE their_jid IN (?, ?) LIMIT 1",
                    (bare + "@s.whatsapp.net", bare + "@lid")).fetchone()
                if not row:
                    pn = self.dev.execute("SELECT pn FROM whatsmeow_lid_map WHERE lid = ?",
                                          (bare,)).fetchone()
                    if pn:
                        row = self.dev.execute(
                            "SELECT full_name, push_name, first_name, business_name FROM "
                            "whatsmeow_contacts WHERE their_jid = ? LIMIT 1",
                            (pn[0] + "@s.whatsapp.net",)).fetchone()
                name = next((x for x in (row or ()) if x), None)
            except sqlite3.Error:
                pass
        if not name:
            row = self.conn.execute("SELECT name FROM chats WHERE jid = ?",
                                    (bare + "@s.whatsapp.net",)).fetchone()
            name = row[0] if row and row[0] else None
        self.cache[sender] = name or bare
        return self.cache[sender]


def _resolve_chat(conn, chat):
    """A chat by JID, phone number or name. Ambiguous names list the candidates
    rather than guessing, because a guess here means messaging the wrong person."""
    if "@" in chat:
        row = conn.execute("SELECT jid, name FROM chats WHERE jid = ?", (chat,)).fetchone()
        return row or (chat, chat)
    digits = re.sub(r"[^\d]", "", chat)
    if digits and len(digits) >= 7 and not re.search(r"[A-Za-z]", chat):
        if digits.startswith("0"):
            digits = "44" + digits[1:]       # a UK number typed the local way
        jid = digits + "@s.whatsapp.net"
        row = conn.execute("SELECT jid, name FROM chats WHERE jid = ?", (jid,)).fetchone()
        return row or (jid, digits)
    rows = conn.execute(
        "SELECT jid, name FROM chats WHERE instr(LOWER(name), LOWER(?)) > 0 "
        "ORDER BY last_message_time DESC LIMIT 15", (chat,)).fetchall()
    exact = [r for r in rows if (r[1] or "").lower() == chat.lower()]
    if len(exact) == 1:
        return exact[0]
    if len(rows) == 1:
        return rows[0]
    if not rows:
        raise WhatsAppError(f"No chat matches '{chat}'. Try `circle wa-who {chat}`.")
    lines = "\n".join(f"  {r[1]}  ({r[0]})" for r in rows)
    raise WhatsAppError(f"'{chat}' matches several chats, so name one exactly or use its "
                        f"id:\n{lines}")


def _print_message(names, row, show_chat=False, ids=False):
    mid, chat_jid, chat_name, sender, content, ts, mine, media, filename = row
    who = "Me" if mine else names(sender)
    text = (content or "").strip()
    if media:
        text = (f"[{media}{': ' + filename if filename else ''}] " + text).strip()
    where = f"{chat_name or chat_jid} | " if show_chat else ""
    tail = f"   (id {mid})" if ids or media else ""
    print(f"[{_when(ts)}] {where}{who}: {text}{tail}")


_MSG_COLS = ("SELECT m.id, m.chat_jid, c.name, m.sender, m.content, m.timestamp, m.is_from_me, "
             "m.media_type, m.filename FROM messages m JOIN chats c ON m.chat_jid = c.jid ")


def cmd_chats(args):
    _freshen()
    with _messages_db() as conn:
        q = ("SELECT jid, name, last_message_time FROM chats "
             + ("WHERE instr(LOWER(name), LOWER(?)) > 0 OR jid LIKE ? " if args.query else "")
             + "ORDER BY last_message_time DESC LIMIT ?")
        params = ([args.query, f"%{args.query}%"] if args.query else []) + [args.limit]
        rows = conn.execute(q, params).fetchall()
    for jid, name, last in rows:
        kind = "group" if jid.endswith("@g.us") else "chat"
        print(f"{_when(last):<17} {kind:<5} {name or jid}   ({jid})")
    if not rows:
        print("No chats found.")


def cmd_read(args):
    _freshen()
    with _messages_db() as conn:
        jid, name = _resolve_chat(conn, args.chat)
        where, params = ["m.chat_jid = ?"], [jid]
        if args.after:
            where.append("m.timestamp >= ?")
            params.append(_since(args.after))
        rows = conn.execute(_MSG_COLS + "WHERE " + " AND ".join(where)
                            + " ORDER BY m.timestamp DESC LIMIT ?", params + [args.limit]).fetchall()
        print(f"{name or jid}  ({jid})")
        names = _Names(conn)
        for row in reversed(rows):
            _print_message(names, row, ids=args.ids)
        if not rows:
            print("No messages in that range.")


def cmd_search(args):
    _freshen()
    with _messages_db() as conn:
        where, params = ["instr(LOWER(m.content), LOWER(?)) > 0"], [args.text]
        if args.chat:
            jid, _ = _resolve_chat(conn, args.chat)
            where.append("m.chat_jid = ?")
            params.append(jid)
        if args.after:
            where.append("m.timestamp >= ?")
            params.append(_since(args.after))
        rows = conn.execute(_MSG_COLS + "WHERE " + " AND ".join(where)
                            + " ORDER BY m.timestamp DESC LIMIT ?", params + [args.limit]).fetchall()
        names = _Names(conn)
        for row in rows:
            _print_message(names, row, show_chat=True, ids=args.ids)
        if not rows:
            print("Nothing found.")


def cmd_who(args):
    seen, out = set(), []
    with _messages_db() as conn:
        for jid, name in conn.execute(
                "SELECT jid, name FROM chats WHERE (instr(LOWER(name), LOWER(?)) > 0 OR jid LIKE ?) "
                "AND jid NOT LIKE '%@g.us' ORDER BY last_message_time DESC LIMIT 30",
                (args.name, f"%{args.name}%")):
            seen.add(jid)
            out.append((name, jid))
    if os.path.isfile(DEVICE_DB):
        with _ro(DEVICE_DB) as dev:
            for row in dev.execute(
                    "SELECT their_jid, full_name, push_name, first_name, business_name "
                    "FROM whatsmeow_contacts WHERE instr(LOWER(full_name), LOWER(?)) > 0 "
                    "OR instr(LOWER(push_name), LOWER(?)) > 0 OR instr(LOWER(business_name), LOWER(?)) > 0 "
                    "LIMIT 30", (args.name,) * 3):
                if row[0] not in seen:
                    seen.add(row[0])
                    out.append((next((x for x in row[1:] if x), ""), row[0]))
    for name, jid in out:
        num = jid.split("@")[0]
        print(f"{name or '?'}   +{num}   ({jid})" if jid.endswith("@s.whatsapp.net")
              else f"{name or '?'}   ({jid})")
    if not out:
        print("No contacts match.")


def cmd_send(args):
    if not args.text and not args.file:
        raise WhatsAppError("Give --text, --file, or both.")
    ensure_running()
    with _messages_db() as conn:
        jid, name = _resolve_chat(conn, args.chat)
    if args.file:
        os.makedirs(OUTBOX, exist_ok=True)
        staged = os.path.join(OUTBOX, os.path.basename(args.file))
        shutil.copyfile(args.file, staged)
        st, d = _http("/api/send", {"recipient": jid, "message": args.text or "",
                                    "media_path": staged}, timeout=180)
    else:
        st, d = _http("/api/send", {"recipient": jid, "message": args.text}, timeout=60)
    if st != 200 or not d.get("success"):
        raise WhatsAppError(f"WhatsApp did not send it: {d.get('message') or st}")
    print(f"Sent to {name or jid}.")


def cmd_media(args):
    ensure_running()
    with _messages_db() as conn:
        jid, _ = _resolve_chat(conn, args.chat)
    st, d = _http("/api/download", {"message_id": args.message_id, "chat_jid": jid}, timeout=180)
    if st != 200 or not d.get("success"):
        raise WhatsAppError(f"Could not download it: {d.get('message') or st}")
    print(d.get("path"))


def run(func):
    def wrapped(args):
        try:
            func(args)
        except WhatsAppError as e:
            sys.exit(str(e))
    return wrapped


def register(sub):
    p = sub.add_parser("wa-connect", help="link this laptop to your WhatsApp (opens the code in your browser)")
    p.add_argument("--wait", type=int, default=300, help="seconds to wait for the scan")
    p.add_argument("--no-browser", action="store_true", help="print the page address instead of opening it")
    p.add_argument("--again", action="store_true", help="unlink first and pair afresh")
    p.set_defaults(func=run(cmd_connect))

    sub.add_parser("wa-status", help="is WhatsApp running and linked").set_defaults(func=run(cmd_status))
    sub.add_parser("wa-start", help="start the WhatsApp bridge").set_defaults(func=run(cmd_start))
    sub.add_parser("wa-stop", help="stop the WhatsApp bridge").set_defaults(func=run(cmd_stop))

    p = sub.add_parser("wa-disconnect", help="unlink this laptop and delete its copy of your messages")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=run(cmd_disconnect))

    p = sub.add_parser("wa-chats", help="WhatsApp chats, most recent first")
    p.add_argument("--query", help="filter by name")
    p.add_argument("--limit", type=int, default=30)
    p.set_defaults(func=run(cmd_chats))

    p = sub.add_parser("wa-read", help="one chat's messages, oldest first")
    p.add_argument("chat", help="name, phone number or chat id")
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--after", help="2026-10-01, 7d, yesterday or today")
    p.add_argument("--ids", action="store_true", help="show message ids")
    p.set_defaults(func=run(cmd_read))

    p = sub.add_parser("wa-search", help="find messages containing some text")
    p.add_argument("text")
    p.add_argument("--chat", help="only this chat")
    p.add_argument("--after", help="2026-10-01, 7d, yesterday or today")
    p.add_argument("--limit", type=int, default=30)
    p.add_argument("--ids", action="store_true", help="show message ids")
    p.set_defaults(func=run(cmd_search))

    p = sub.add_parser("wa-who", help="look up a WhatsApp contact")
    p.add_argument("name")
    p.set_defaults(func=run(cmd_who))

    p = sub.add_parser("wa-send", help="send a WhatsApp message or file (asks first)")
    p.add_argument("chat", help="name, phone number or chat id")
    p.add_argument("--text")
    p.add_argument("--file", help="a file to send, with --text as its caption")
    p.set_defaults(func=run(cmd_send))

    p = sub.add_parser("wa-media", help="download a photo, video or document from a message")
    p.add_argument("message_id")
    p.add_argument("--chat", required=True)
    p.set_defaults(func=run(cmd_media))
