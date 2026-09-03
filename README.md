# Cir'Claude

The Circle Agency work assistant, as one Claude Code plugin.

One CLI, `circle`, covering:

- **Outlook** - read, search, thread, draft, threaded replies, gated sending
- **Calendar** - agenda, colleague free/busy, sending invites including Teams
- **Directory** - look up a colleague's real address, check who is out of office
- **Teamwork** - audit what time is logged, find project codes, log time
  (dry run by default)

Plus skills that carry the agency's own processes: inbox triage that
reconciles against Sent Items, timesheet logging, opening a new job in the
right order, the weekly status deck, and SwissTransfer downloads.

**Sending is gated.** `circle send`, `reply` and `reply-all` save to Drafts
unless `--send-now` is passed, and the plugin ships a hook that makes every
actual send ask you for confirmation, whatever permission mode Claude Code is
in. Nothing leaves your account unreviewed.

**Your credentials stay yours.** Sign-in is a one-time device code against
your own Circle Microsoft account; the token is stored at
`~/.circle/graph_token.json`, outside this folder. Teamwork uses your own API
key from the environment. Nothing is shared and nobody can read your mail
through this.

## Requirements (Windows)

- **Claude Code Desktop**
- **Git** - Claude Code Desktop needs it on Windows
- **Python 3** - `winget install Python.Python.3.12` (per-user, no admin)

Raise all three with IT as one request. On a Mac, Python and Git are usually
already present.

## Setup

See `ONBOARDING.md` for the walkthrough, or in Claude Code just run
`/circlaude:onboard` and it will do the whole thing with you.

The short version:

```
git clone <this repo> %USERPROFILE%\CirClaude
cd %USERPROFILE%\CirClaude
bin\circle login
bin\circle whoami
```

Then in Claude Code:

```
/plugin marketplace add %USERPROFILE%\CirClaude
/plugin install circlaude@circlaude
```

## Notes

- Pure Python 3 stdlib. No `pip install`, ever. That is deliberate, so it
  runs on a locked-down laptop.
- The plugin hook runs `python`; on a Mac where only `python3` exists, alias
  it or install python.org Python.
- Built and maintained by Dom Bartolo. Questions to dom.bartolo@circleagency.co.uk.
