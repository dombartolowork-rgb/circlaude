#!/usr/bin/env python3
"""PreToolUse guard: anything that would actually send email, or change a shared
file, must be confirmed by the human, whatever permission mode the session is in.

Claude Code pipes the tool call in as JSON on stdin. If the Bash command
matches a send operation, we answer with permissionDecision "ask", which
forces a confirmation prompt even in auto-accept modes. Everything else
passes through untouched (empty output, exit 0).

This is the harness-enforced half of the draft-first rule. The CLI half is
that mail is drafted through the connector and only sent once the user
has seen it. Prose rules get skipped under pressure; this does not.
"""
import json
import re
import sys

# Uploads into a shared agency folder that colleagues read and act on. Not an
# email, but just as hard to take back once someone has opened it.
SHARE_PATTERNS = [
    r"circle(\.cmd)?\s+handover-upload\b",
]

# Puts a file on Circle's Vimeo account, where anyone with the link can watch it.
PUBLISH_PATTERNS = [
    r"circle(\.cmd)?\s+vi-upload\b",
]

# Sends from the person's own WhatsApp, which they cannot unsend for the other
# side once it is read. Unlinking deletes this laptop's copy of their messages.
WHATSAPP_PATTERNS = [
    r"circle(\.cmd)?\s+wa-send\b",
]
WHATSAPP_UNLINK_PATTERNS = [
    r"circle(\.cmd)?\s+wa-disconnect\b",
]

SEND_PATTERNS = [
    r"circle(\.cmd)?\s+[^|;&]*--send-now",   # gated sends being un-gated
    r"circle(\.cmd)?\s+send-draft\b",        # sending an existing draft
    r"/me/sendMail",                          # raw Graph send, e.g. via python
    r"/me/messages/[^\s\"']+/send\b",         # raw Graph draft-send
]


# The Microsoft 365 connector's tools, by the name Claude Code gives them.
# Sending, forwarding and invites leave the account; SharePoint writes change
# shared files colleagues rely on. Drafts, reads and folder creation pass.
MCP_SEND = re.compile(
    r"^mcp__.*Microsoft_365__(outlook_send_draft|outlook_send_mail|"
    r"outlook_forward_mail|outlook_create_event|outlook_update_event|"
    r"outlook_respond_to_event)$")
MCP_SHARE = re.compile(
    r"^mcp__.*Microsoft_365__(sharepoint_upload_file|sharepoint_update_file|"
    r"sharepoint_delete_item|sharepoint_move_item|sharepoint_rename_item)$")


def _has_attendees(payload):
    """True if a new event would invite anyone. Any input field naming attendees
    counts, whatever the connector calls it, so a renamed field fails safe. Only
    create is relaxed: updating an existing meeting can notify its attendees even
    when the update itself lists none."""
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return True
    return any("attendee" in k.lower() and v for k, v in tool_input.items())


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return  # never break the tool call on a malformed payload
    tool = payload.get("tool_name") or ""
    command = (payload.get("tool_input") or {}).get("command", "") if tool == "Bash" else ""
    # A personal time-on-task block (no attendees) reaches nobody, so it passes.
    # Anything that invites people still asks, case by case.
    if tool.endswith("__outlook_create_event") and not _has_attendees(payload):
        return
    if MCP_SEND.search(tool):
        reason = ("This sends from your account (an email, a forward or a meeting "
                  "invite). Check the wording and recipients before approving.")
    elif MCP_SHARE.search(tool):
        reason = ("This changes a file on SharePoint or OneDrive that others may "
                  "rely on. Check it is the right file before approving.")
    elif tool != "Bash":
        return
    elif any(re.search(p, command) for p in SHARE_PATTERNS):
        reason = ("This uploads a document to a shared agency folder where "
                  "colleagues will read it. Check the content before approving.")
    elif any(re.search(p, command) for p in PUBLISH_PATTERNS):
        reason = ("This uploads a video to Circle's Vimeo account. Check it is the "
                  "right file, and the privacy setting, before approving.")
    elif any(re.search(p, command) for p in WHATSAPP_PATTERNS):
        reason = ("This sends a WhatsApp message from your own WhatsApp. Check who it "
                  "is going to and the wording before approving.")
    elif any(re.search(p, command) for p in WHATSAPP_UNLINK_PATTERNS):
        reason = ("This unlinks WhatsApp from this laptop and deletes its copy of your "
                  "messages. Approve only if that is what you want.")
    elif any(re.search(p, command) for p in SEND_PATTERNS):
        reason = ("This command sends email from your account. Check the draft "
                  "text is what you want before approving.")
    else:
        return
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }))


if __name__ == "__main__":
    main()
