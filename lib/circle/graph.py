#!/usr/bin/env python3
"""Microsoft Graph core: token storage, silent refresh, and API calls.

Orbit's own sign-in is deliberately narrow. Mail, calendar, people and Teams all
go through the organisation's Microsoft 365 connector inside Claude, which IT
already manages. This sign-in exists only for the SharePoint work the connector
cannot do: reading and editing the Project Tracker workbook (83 sheets, edited
live, over the connector's 1MB file limit) and uploading large files such as the
status deck. So it asks for file and site scopes only, never mail.

Which Entra app it signs in through is configuration, not code:

  ~/.circle/config.json   {"client_id": "...", "tenant": "..."}
  or CIRCLE_CLIENT_ID / CIRCLE_TENANT in the environment

With neither set it falls back to Microsoft's first-party Office client, which
is pre-consented on the Circle tenant. That is a stopgap until IT issues a
Circle-owned app registration, and it is not narrow: see SCOPE below.

Pure Python 3 stdlib. No pip install, so it runs on a locked-down Windows
laptop as long as Python 3 itself is present.

The token lives OUTSIDE this repo, at ~/.circle/orbit_token.json, so it can
never be committed or shared by accident. Override with CIRCLE_TOKEN_FILE.
"""
import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

CONFIG_DIR = os.path.expanduser("~/.circle")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

OFFICE_CLIENT_ID = "d3590ed6-52b3-4102-aeff-aad2292ab01c"  # Microsoft Office, first-party


def _config():
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


_CFG = _config()
CLIENT_ID = os.environ.get("CIRCLE_CLIENT_ID") or _CFG.get("client_id") or OFFICE_CLIENT_ID
TENANT = os.environ.get("CIRCLE_TENANT") or _CFG.get("tenant") or "organizations"

# Files and sites only. With a Circle-owned app registration this is exactly
# what the token carries. The fallback Office client cannot take named scopes:
# as a first-party app it may only request what Microsoft has preauthorised
# for it, and asking for these by name fails at sign-in with AADSTS65002
# (hit on a Windows install, 2 Oct 2026). So on the Office client we ask for
# .default, its whole pre-consented set, mail included. Orbit never calls mail
# through this sign-in either way, but only the Circle-owned app makes that a
# guarantee rather than a habit.
NARROW_SCOPE = ("https://graph.microsoft.com/Files.ReadWrite.All "
                "https://graph.microsoft.com/Sites.Read.All "
                "https://graph.microsoft.com/User.Read offline_access")
SCOPE = ("https://graph.microsoft.com/.default offline_access"
         if CLIENT_ID == OFFICE_CLIENT_ID else NARROW_SCOPE)
AUTH_BASE = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0"
GRAPH = "https://graph.microsoft.com/v1.0"

TOKEN_FILE = os.environ.get("CIRCLE_TOKEN_FILE") or os.path.join(CONFIG_DIR, "orbit_token.json")

class AuthError(Exception):
    """No usable token: the caller should tell the user to run `circle login`."""


# --- low-level HTTP -------------------------------------------------------

def _post_form(url, data):
    req = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(data).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r), None
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}"), e.code


# --- token storage --------------------------------------------------------

def load_token():
    if not os.path.exists(TOKEN_FILE):
        raise AuthError("Not signed in to Microsoft. Run: circle login")
    with open(TOKEN_FILE) as f:
        return json.load(f)


def save_token(tok):
    # Stamp an absolute expiry so we can refresh proactively rather than on 401.
    if "expires_in" in tok:
        tok["expires_at"] = int(time.time()) + int(tok["expires_in"]) - 60
    os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump(tok, f)
    os.chmod(TOKEN_FILE, 0o600)
    return tok


def _refresh(tok):
    rt = tok.get("refresh_token")
    if not rt:
        raise AuthError("Token expired and there is no refresh token. Run: circle login")
    new, err = _post_form(
        f"{AUTH_BASE}/token",
        {
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "refresh_token": rt,
            "scope": SCOPE,
        },
    )
    if err:
        raise AuthError(
            f"Token refresh failed ({err}): {new.get('error_description', new)}\n"
            "Run: circle login"
        )
    new.setdefault("refresh_token", rt)  # some responses omit it; keep the old one
    return save_token(new)


def access_token():
    """A valid access token, refreshed silently if it has expired."""
    tok = load_token()
    if int(time.time()) >= int(tok.get("expires_at", 0)):
        tok = _refresh(tok)
    return tok["access_token"]


# --- Graph API ------------------------------------------------------------

def call(method, path, body=None, content_type="application/json", raw=False,
         full_url=None, headers=None):
    """Call Graph. Returns (status, headers, parsed_body).

    `path` is relative to /v1.0. Pass `full_url` for @odata.nextLink paging.
    `headers` adds request headers, e.g. the Prefer timezone header.
    """
    url = full_url or (GRAPH + path)
    # A raw space in a query ($orderby=x desc, $filter=... eq '...') makes urllib
    # raise InvalidURL: "URL can't contain control characters". Spaces are never
    # legal in a URL, so encoding them here is always safe and saves every caller
    # from remembering.
    url = url.replace(" ", "%20")
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + access_token())
    if data is not None:
        req.add_header("Content-Type", content_type)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req) as r:
            out = r.read()
            if raw:
                return r.status, dict(r.headers), out
            return r.status, dict(r.headers), json.loads(out) if out else {}
    except urllib.error.HTTPError as e:
        body_bytes = e.read() or b"{}"
        if raw:
            return e.code, dict(e.headers), body_bytes
        try:
            return e.code, dict(e.headers), json.loads(body_bytes)
        except ValueError:
            return e.code, dict(e.headers), {"raw": body_bytes.decode(errors="replace")}


# Throttling plus the transient server-side failures Graph returns readily on
# larger listings (a bare 504 "UnknownError" is common with a big $top).
RETRY_STATUS = (429, 500, 502, 503, 504)


def call_retry(method, path, body=None, tries=4, **kw):
    """As call(), but retries throttling and transient 5xx with backoff.

    Directory lookups throttle readily and list endpoints time out, so anything
    reading a collection should come through here rather than call().
    """
    delay = 2
    for attempt in range(tries):
        status, hdrs, data = call(method, path, body, **kw)
        if status not in RETRY_STATUS or attempt == tries - 1:
            return status, hdrs, data
        time.sleep(int(hdrs.get("Retry-After") or delay))
        delay *= 2
    return status, hdrs, data


def paged(path, limit=None, headers=None):
    """Yield items across @odata.nextLink pages, up to `limit` items.

    `headers` is carried onto every page, not just the first: a Prefer timezone
    header dropped on page two silently mixes UTC rows into local ones.
    """
    status, _, data = call("GET", path, headers=headers)
    if status != 200:
        raise RuntimeError(f"Graph GET {path} failed ({status}): {data}")
    seen = 0
    while True:
        for item in data.get("value", []):
            yield item
            seen += 1
            if limit and seen >= limit:
                return
        nxt = data.get("@odata.nextLink")
        if not nxt:
            return
        status, _, data = call("GET", None, full_url=nxt, headers=headers)
        if status != 200:
            return


def whoami():
    """(upn, scopes) decoded from the current access token, no network call."""
    payload = access_token().split(".")[1]
    payload += "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))
    return claims.get("upn") or claims.get("preferred_username", ""), claims.get("scp", "")
