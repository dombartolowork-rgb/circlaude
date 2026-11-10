"""A browser Orbit can drive, for sites with no API: Chrome (or Edge) in its own
clean profile, with a debug port on this machine only.

    circle browser-open <url>        start it if needed and open the page
    circle browser-eval "<js>"       run JavaScript in the open page, print the result
    circle browser-close [--wipe]    shut it, and with --wipe forget every sign-in
    circle fathom-share <link|id>    the public fathom.video/share/ link for a call

The profile lives in ~/.circle/browser-profile and starts empty: the user signs
in to the site themselves in the window that opens, once. No cookies or
passwords are copied from their normal browser. While it is open, any program on
this laptop can drive it through the port, so close it when the job is done.

Talks to the browser over the DevTools protocol with a small stdlib websocket
client, so nothing needs installing.
"""
import base64
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import time
import urllib.parse
import urllib.request

from . import bins

PORT = 9333
HOST = "127.0.0.1"
PROFILE = os.path.join(os.path.expanduser("~"), ".circle", "browser-profile")


# ---------------------------------------------------------------- the browser

def _browser():
    if bins.WINDOWS:
        roots = [os.environ.get(k, "") for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        tails = [r"Google\Chrome\Application\chrome.exe", r"Microsoft\Edge\Application\msedge.exe"]
        cands = [os.path.join(r, t) for t in tails for r in roots if r]
    else:
        cands = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                 "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
        cands += [shutil.which(n) or "" for n in ("google-chrome", "chromium", "microsoft-edge")]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    raise bins.ToolMissing("Neither Chrome nor Edge was found on this laptop.")


def _http(path, method="GET"):
    req = urllib.request.Request("http://%s:%d%s" % (HOST, PORT, path), method=method)
    with urllib.request.urlopen(req, timeout=3) as r:
        return json.loads(r.read().decode() or "null")


def running():
    try:
        _http("/json/version")
        return True
    except OSError:
        return False


def start():
    if running():
        return
    os.makedirs(PROFILE, exist_ok=True)
    args = [_browser(), "--remote-debugging-port=%d" % PORT,
            "--remote-debugging-address=" + HOST,
            "--user-data-dir=" + PROFILE, "--no-first-run",
            "--no-default-browser-check", "about:blank"]
    kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if bins.WINDOWS:
        kw["creationflags"] = 0x00000008 | 0x00000200  # detached, new process group
    else:
        kw["start_new_session"] = True
    subprocess.Popen(args, **kw)
    for _ in range(40):
        if running():
            return
        time.sleep(0.5)
    raise RuntimeError("The browser started but its debug port never answered.")


def pages():
    return [t for t in _http("/json/list") if t.get("type") == "page"]


def open_tab(url):
    start()
    q = urllib.parse.quote(url, safe="")
    try:
        return _http("/json/new?" + q, method="PUT")
    except OSError:
        return _http("/json/new?" + q)


def find_tab(match=None):
    ps = pages()
    if match:
        ps = [p for p in ps if match in p.get("url", "")]
    if not ps:
        raise RuntimeError("No open page%s." % (" matching " + match if match else ""))
    return ps[0]


# ---------------------------------------------------------------- websocket

class Tab:
    """One page, over its DevTools websocket."""

    def __init__(self, tab):
        u = urllib.parse.urlparse(tab["webSocketDebuggerUrl"])
        self.sock = socket.create_connection((u.hostname, u.port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(("GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\n"
                           "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
                           "Sec-WebSocket-Version: 13\r\n\r\n"
                           % (u.path, u.hostname, u.port, key)).encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(1024)
            if not chunk:
                raise RuntimeError("The browser closed the connection.")
            head += chunk
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise RuntimeError("The browser refused the connection: %r" % head[:80])
        self.buf = head.split(b"\r\n\r\n", 1)[1]
        self.n = 0

    def _send(self, text):
        data = text.encode()
        hdr = bytearray([0x81])
        n = len(data)
        if n < 126:
            hdr.append(0x80 | n)
        elif n < 65536:
            hdr.append(0x80 | 126)
            hdr += struct.pack(">H", n)
        else:
            hdr.append(0x80 | 127)
            hdr += struct.pack(">Q", n)
        mask = os.urandom(4)
        self.sock.sendall(bytes(hdr) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError("The browser closed the connection.")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _recv(self):
        msg = b""
        while True:
            b1, b2 = self._read(2)
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n)
            op = b1 & 0x0F
            if op == 0x8:
                raise RuntimeError("The browser closed the connection.")
            if op in (0x9, 0xA):
                continue
            msg += payload
            if b1 & 0x80:
                return msg.decode("utf-8", "replace")

    def call(self, method, **params):
        self.n += 1
        self._send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            m = json.loads(self._recv())
            if m.get("id") == self.n:
                if "error" in m:
                    raise RuntimeError(m["error"].get("message", str(m["error"])))
                return m.get("result", {})

    def eval(self, js):
        r = self.call("Runtime.evaluate", expression=js, awaitPromise=True,
                      returnByValue=True, userGesture=True, replMode=True)
        if r.get("exceptionDetails"):
            d = r["exceptionDetails"]
            raise RuntimeError((d.get("exception") or {}).get("description") or d.get("text"))
        return (r.get("result") or {}).get("value")

    def go(self, url):
        self.call("Page.navigate", url=url)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


# ---------------------------------------------------------------- Fathom

SHARE_RE = re.compile(r"https://fathom\.video/share/[A-Za-z0-9_\-]+")

# Anything on the page that already holds a share link: links, inputs, text.
SCAN_JS = r"""(() => {
  const re = /https:\/\/fathom\.video\/share\/[A-Za-z0-9_\-]+/;
  for (const el of document.querySelectorAll('a[href], input, textarea')) {
    const v = el.href || el.value || '';
    const m = v.match(re); if (m) return m[0];
  }
  const m = (document.body ? document.body.innerText : '').match(re);
  return m ? m[0] : null;
})()"""

# Click the button labelled Share. It only opens the dialog: nothing here turns
# sharing on or changes who can see the call.
CLICK_SHARE_JS = r"""(() => {
  const els = [...document.querySelectorAll('button, [role=button], a')];
  const hit = els.find(e => /^\s*share\s*$/i.test(e.innerText || '')
                        || /^share$/i.test(e.getAttribute('aria-label') || ''));
  if (!hit) return false;
  hit.click(); return true;
})()"""

STATE_JS = "JSON.stringify({path: location.pathname, host: location.host})"


def _call_url(arg):
    arg = arg.strip()
    if SHARE_RE.match(arg):
        return arg
    if re.fullmatch(r"\d+", arg):
        return "https://fathom.video/calls/" + arg
    m = re.search(r"fathom\.video/calls/(\d+)", arg)
    if not m:
        raise SystemExit("Give a fathom.video/calls/ link or the call number.")
    return "https://fathom.video/calls/" + m.group(1)


def fathom_share(arg, wait=300, quiet=False):
    url = _call_url(arg)
    if "/share/" in url:
        return url
    tab_info = open_tab(url)
    tab = Tab(tab_info)
    try:
        tab.call("Page.enable")
        told = False
        deadline = time.time() + wait
        while True:
            time.sleep(2)
            st = json.loads(tab.eval(STATE_JS) or "{}")
            on_call = st.get("host", "").endswith("fathom.video") and st.get("path", "").startswith("/calls/")
            if on_call:
                break
            signing_in = re.search(r"sign|login|auth|oauth", st.get("path", "") + st.get("host", ""), re.I)
            if not signing_in and st.get("host", "").endswith("fathom.video"):
                tab.go(url)   # signed in, but Fathom landed on its home page
                continue
            if not told and not quiet:
                print("Sign in to Fathom in the browser window that just opened "
                      "(waiting up to %d minutes)..." % (wait // 60), file=sys.stderr, flush=True)
                told = True
            if time.time() > deadline:
                raise SystemExit("Nobody signed in to Fathom in time. Run it again when ready.")
        for _ in range(10):           # let the call page render
            link = tab.eval(SCAN_JS)
            if link:
                return link
            if tab.eval("!!document.querySelector('button, [role=button]')"):
                break
            time.sleep(1)
        if not tab.eval(CLICK_SHARE_JS):
            raise SystemExit("Signed in, but there is no Share button on the call page. "
                             "This account may not have access to the call.")
        for _ in range(10):
            time.sleep(1)
            link = tab.eval(SCAN_JS)
            if link:
                return link
        raise SystemExit("The Share dialog opened but shows no share link. Sharing may be off "
                         "for this call: look at the browser window, and turn it on only if the "
                         "user agrees.")
    finally:
        tab.close()


# ---------------------------------------------------------------- commands

def cmd_open(a):
    t = open_tab(a.url)
    print("Opened %s in Orbit's browser (port %d)." % (t.get("url") or a.url, PORT))


def cmd_eval(a):
    js = sys.stdin.read() if a.js == "-" else a.js
    tab = Tab(find_tab(a.tab))
    try:
        v = tab.eval(js)
    finally:
        tab.close()
    print(v if isinstance(v, str) else json.dumps(v, indent=2))


def cmd_close(a):
    if running():
        try:
            Tab(_http("/json/version")).call("Browser.close")
        except Exception:
            pass
        for _ in range(20):
            if not running():
                break
            time.sleep(0.5)
    if a.wipe and os.path.isdir(PROFILE):
        shutil.rmtree(PROFILE, ignore_errors=True)
        print("Closed, and forgot every sign-in in Orbit's browser.")
    else:
        print("Closed.")


def cmd_fathom_share(a):
    link = fathom_share(a.call, wait=a.wait)
    print(link)
    if a.close:
        cmd_close(type("A", (), {"wipe": False})())


def register(sub):
    p = sub.add_parser("browser-open", help="open a page in Orbit's own browser (clean profile)")
    p.add_argument("url")
    p.set_defaults(func=cmd_open)

    p = sub.add_parser("browser-eval", help="run JavaScript in a page open in Orbit's browser")
    p.add_argument("js", help="the script, or - to read it from standard input")
    p.add_argument("--tab", help="pick the page whose address contains this")
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("browser-close", help="close Orbit's browser")
    p.add_argument("--wipe", action="store_true", help="also forget every sign-in in it")
    p.set_defaults(func=cmd_close)

    p = sub.add_parser("fathom-share", help="the public fathom.video/share/ link for a call")
    p.add_argument("call", help="the fathom.video/calls/ link, or the call number")
    p.add_argument("--wait", type=int, default=300, help="seconds to wait for sign-in")
    p.add_argument("--close", action="store_true", help="close the browser afterwards")
    p.set_defaults(func=cmd_fathom_share)
