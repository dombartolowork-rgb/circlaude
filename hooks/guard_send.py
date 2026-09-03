#!/usr/bin/env python3
"""PreToolUse guard: any command that would actually send email must be
confirmed by the human, whatever permission mode the session is in.

Claude Code pipes the tool call in as JSON on stdin. If the Bash command
matches a send operation, we answer with permissionDecision "ask", which
forces a confirmation prompt even in auto-accept modes. Everything else
passes through untouched (empty output, exit 0).

This is the harness-enforced half of the draft-first rule. The CLI half is
that `circle send` / `reply` / `reply-all` only draft unless --send-now is
passed. Prose rules get skipped under pressure; this does not.
"""
import json
import re
import sys

SEND_PATTERNS = [
    r"circle(\.cmd)?\s+[^|;&]*--send-now",   # gated sends being un-gated
    r"circle(\.cmd)?\s+send-draft\b",        # sending an existing draft
    r"/me/sendMail",                          # raw Graph send, e.g. via python
    r"/me/messages/[^\s\"']+/send\b",         # raw Graph draft-send
]


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return  # never break the tool call on a malformed payload
    if payload.get("tool_name") != "Bash":
        return
    command = (payload.get("tool_input") or {}).get("command", "")
    if not any(re.search(p, command) for p in SEND_PATTERNS):
        return
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                "This command sends email from your account. Check the draft "
                "text is what you want before approving."
            ),
        }
    }))


if __name__ == "__main__":
    main()
