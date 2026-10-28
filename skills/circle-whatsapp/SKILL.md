---
name: circle-whatsapp
description: Read and send the user's own WhatsApp through Orbit's WhatsApp link - check what a freelancer, crew member or colleague said, find what was agreed in a chat or group, pull a file or photo someone sent, or send a message. Also connects WhatsApp in the first place. Use when asked to "check WhatsApp", "what did they say on WhatsApp", "message him on WhatsApp", "text her", "the group chat", "send it to him on WhatsApp", "connect my WhatsApp", or when WhatsApp "is not working".
---

# WhatsApp

**Invoking it:** where this says `circle`, run `"$CLAUDE_PLUGIN_ROOT/bin/circle"`
unless `circle` is already on PATH (on Windows, `bin\circle.cmd`).

Orbit links to the user's WhatsApp as one of the **linked devices** on their phone,
the same way WhatsApp Web does. A small program keeps that link open in the
background and saves a copy of their messages on this laptop, in
`~/.circle/whatsapp`. Nothing goes anywhere else.

```
circle wa-status                       linked? running? how fresh?
circle wa-chats --query "Rich"         chats, most recent first
circle wa-read "Tom O" --after 7d      one chat, oldest first
circle wa-search "PO" --after 30d      find text across chats (or --chat "...")
circle wa-who "Tom"                    a contact's number and chat id
circle wa-send <chat id> --text "..."  send (asks the user first)
circle wa-send <chat id> --file x.pdf --text "caption"
circle wa-media <message id> --chat <chat id>   download a photo or document
circle wa-connect                      link WhatsApp (the code opens in their browser)
```

## Connecting it

If `wa-status` says no phone is linked, or they ask to connect WhatsApp, follow
step 9 of `/orbit:onboard`. In short: run `circle wa-connect` **in the
background**, tell them their browser is opening with a code, and walk them
through the phone side. Only they can scan it. Never try to work around that.

`wa-connect` waits up to five minutes and prints `CONNECTED` when the phone has
scanned it. After that the link **starts by itself at every login**, so it is
normally already up. If `wa-status` says linked but not running, `circle wa-start`
fixes it, and reading commands try that by themselves.

If the browser page says **"This needs an update"**, WhatsApp has retired the
version of the link Orbit ships. Only a new Orbit release fixes that: tell them
to let Dom know, and stop.

## This is their personal WhatsApp

It carries family and friends alongside work. So:

- **Work chats only.** When asked for "anything on WhatsApp", look at work chats:
  colleagues, freelancers, crew, suppliers, clients. Do not read out, quote or
  summarise personal chats they did not ask about. If you are unsure whether a
  chat is work, give its name and ask.
- **Confirm the recipient before sending.** Names repeat ("Tom" matches several
  chats) and a group can share a phone number with a person. Resolve the chat
  with `wa-who` or `wa-chats`, tell them who you resolved it to, and send to the
  **chat id** (the part in brackets), never a bare name.
- **Show the wording first** for anything of substance, the same as email, and
  send only when they say so. The confirm prompt on `wa-send` is the backstop, not
  the check.

## Writing for WhatsApp

Short lines, no greeting block, no sign-off, no subject. Match how they already
write in that chat: read the last few messages first. No em dashes.

Anything that needs a paper trail (quotes, scope, dates a client will be billed
for) belongs in email, so it can be found later. If something important was
agreed on WhatsApp, offer to confirm it by email.

## Good to know

- **Messages the link missed.** While the laptop is off, nothing is lost: when
  it comes back, WhatsApp catches it up. Allow a minute or two after a restart
  before concluding a message never arrived.
- **Files to send** must be on this laptop. `wa-send --file` copies them to the
  outbox the link is allowed to send from.
- **Unlinking** is `circle wa-disconnect --yes`. It stops the link and deletes this
  laptop's copy of their messages. Then they remove "Orbit" from Linked devices on
  their phone.
- **Personal volume only.** The link is an unofficial WhatsApp client, so heavy
  or bulk use risks the account. Never use it for mass messages.
