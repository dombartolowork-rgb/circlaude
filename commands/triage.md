---
description: Find the email threads the user genuinely owes a reply on, reconciled against Sent Items
---
## Invoking the CLI

Examples below write `circle` for readability. **Run it as
`"$CLAUDE_PLUGIN_ROOT/bin/circle"`** unless `circle` is already on PATH: when
this is installed as a plugin there is no `circle` on PATH and no repo folder
in the home directory, so a bare `circle` fails with "command not found".
Check with `command -v circle` once and use whichever works for the rest of
the session.

Use the `circle-inbox-triage` skill.

Pull the inbox, discard the noise, and for every real candidate check
`circle thread <id>` so phone-sent replies are counted. Report a short list,
newest first: who, what they are waiting on, how old, and whether anyone is
blocked on the user.

Do not draft anything yet. Ask which they want to take first, then work
through them one at a time, drafting and showing each before sending.

$ARGUMENTS
