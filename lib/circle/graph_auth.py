#!/usr/bin/env python3
"""Device-code sign-in for Microsoft Graph.

Prints a short code and a URL. You sign in once in a browser; the resulting
token (including a refresh token) is saved to ~/.circle/graph_token.json and
refreshed silently from then on.
"""
import sys
import time

from . import graph


def login():
    dc, err = _devicecode()
    if err:
        print("DEVICECODE_ERROR:", dc)
        sys.exit(1)

    print("\n" + "=" * 64)
    print("SIGN IN TO MICROSOFT")
    print("=" * 64)
    print(dc["message"])
    print("=" * 64 + "\n", flush=True)

    interval = dc.get("interval", 5)
    deadline = time.time() + dc.get("expires_in", 900)
    while time.time() < deadline:
        time.sleep(interval)
        tok, err = graph._post_form(
            f"{graph.AUTH_BASE}/token",
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": graph.CLIENT_ID,
                "device_code": dc["device_code"],
            },
        )
        if not err:
            graph.save_token(tok)
            upn, scp = graph.whoami()
            print(f"Signed in as {upn}.")
            print("Token saved to", graph.TOKEN_FILE)
            print("Scopes:", scp)
            return
        if tok.get("error") in ("authorization_pending", "slow_down"):
            if tok.get("error") == "slow_down":
                interval += 5
            continue
        print("AUTH_ERROR:", tok.get("error_description", tok))
        sys.exit(1)
    print("AUTH_TIMEOUT: the sign-in window expired. Run circle login again.")
    sys.exit(1)


def _devicecode():
    return graph._post_form(
        f"{graph.AUTH_BASE}/devicecode",
        {"client_id": graph.CLIENT_ID, "scope": graph.SCOPE},
    )
