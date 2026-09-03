#!/usr/bin/env python3
"""People: look up a colleague's real address instead of guessing it.

Guessing an address is how mail goes to the wrong person or bounces silently.
Always look it up. The /users endpoint throttles readily, so every call here
goes through graph.call_retry.
"""
import sys
import urllib.parse

from . import graph

SELECT = "displayName,mail,userPrincipalName,jobTitle,department,officeLocation,mobilePhone"


def cmd_who(args):
    """Find people by name fragment, or by address if it looks like one."""
    term = args.name
    if "@" in term:
        flt = f"mail eq '{term}' or userPrincipalName eq '{term}'"
    else:
        # startswith on displayName is the reliable filter; also try surname.
        flt = (f"startswith(displayName,'{term}') or startswith(surname,'{term}') "
               f"or startswith(givenName,'{term}') or startswith(mail,'{term}')")
    q = urllib.parse.quote(flt)
    status, _, data = graph.call_retry(
        "GET", f"/users?$filter={q}&$select={SELECT}&$top={args.limit}"
    )
    if status != 200:
        sys.exit(f"Lookup failed ({status}): {data}")
    items = data.get("value", [])
    if not items:
        print(f"No directory match for '{term}'. Try a shorter fragment, or a surname.")
        return
    for u in items:
        addr = u.get("mail") or u.get("userPrincipalName") or "(no address)"
        print(f"{u.get('displayName')}  <{addr}>")
        bits = [u.get("jobTitle"), u.get("department"), u.get("officeLocation")]
        detail = "  ".join(b for b in bits if b)
        if detail:
            print(f"    {detail}")


def cmd_oof(args):
    """Check who is out of office before chasing them."""
    body = {"EmailAddresses": args.who, "MailTipsOptions": "automaticReplies"}
    status, _, data = graph.call("POST", "/me/getMailTips", body)
    if status != 200:
        sys.exit(f"getMailTips failed ({status}): {data}")
    for tip in data.get("value", []):
        addr = tip.get("emailAddress", {}).get("address", "?")
        ar = tip.get("automaticReplies") or {}
        msg = (ar.get("message") or "").strip()
        if msg:
            import re
            clean = re.sub(r"<[^>]+>", " ", msg)
            clean = " ".join(clean.split())
            print(f"{addr}: OUT OF OFFICE")
            print(f"    {clean[:400]}")
        else:
            print(f"{addr}: no auto-reply set")


def cmd_me(args):
    status, _, data = graph.call("GET", "/me?$select=" + SELECT)
    if status != 200:
        sys.exit(f"Could not read profile ({status}): {data}")
    for k, v in data.items():
        if not k.startswith("@") and v:
            print(f"{k:<20} {v}")


def register(sub):
    p = sub.add_parser("who", help="look up a colleague's address in the directory")
    p.add_argument("name", help="name fragment, surname, or an email address")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_who)

    p = sub.add_parser("oof", help="check whether people are out of office")
    p.add_argument("who", nargs="+", help="email addresses")
    p.set_defaults(func=cmd_oof)

    p = sub.add_parser("me", help="your own directory profile")
    p.set_defaults(func=cmd_me)
