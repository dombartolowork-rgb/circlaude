# Orbit Assistant

The Circle Agency work assistant, as one Claude Code plugin.

Two halves:

- **The Microsoft 365 connector in Claude** does mail, calendar, people and
  Teams: reading, searching, threaded reply drafts, availability, invites. It is
  the organisation's connector, managed and assigned by IT, so Orbit adds no
  new route into anyone's mailbox.
- **A small `circle` command** does what that connector cannot: read and edit
  the Project Tracker, upload large files to SharePoint, build and file the
  leave handover, and Teamwork timesheets with a real dry run.

Plus skills that carry the agency's own processes: inbox triage that
reconciles against Sent Items, timesheet logging, opening a new job in the
right order, the weekly status deck, the annual leave handover, handling
client transfers and shared SharePoint files safely, SwissTransfer downloads,
and taking a section out of a video too big to download.

**Sending is gated.** Orbit ships a hook that makes every send, forward,
meeting invite and shared-file change ask you for confirmation, whatever
permission mode Claude Code is in. Nothing leaves your account unreviewed.

**Your credentials stay yours.** The connector signs in as you inside Claude.
Orbit's own sign-in, used only for SharePoint files, is a one-time device code;
its token is stored at `~/.circle/orbit_token.json`, outside this folder.
Which Entra app it uses is set in `~/.circle/config.json` (`client_id`,
`tenant`), falling back to Microsoft's Office client until Circle's own app
registration exists. Teamwork uses your own API key or the Teamwork connector.

## Requirements (Windows)

- **Claude Code Desktop**, signed in with a Circle Claude Team seat
- **The Microsoft 365 connector** switched on in Claude, and the person assigned
  to it by IT
- **Git for Windows** - Orbit's instructions run through Git's shell
- **Python 3.12** - all users, with the py launcher

IT push the installs. On a Mac, Python and Git are usually already present.

## Setup

See `ONBOARDING.md` for the walkthrough, or in Claude Code run `/orbit:onboard`
and it will do the whole thing with you.

Orbit installs from a folder, so it does not need GitHub. The plan is a
SharePoint library synced to each laptop by OneDrive. In Claude Code:

```
/plugin marketplace add "<path to the synced Orbit folder>"
/plugin install orbit@orbit
```

Updates: publish a new version (bump `version` in both `.claude-plugin` files)
into the library; users run `/plugin marketplace update orbit` then
`/plugin update orbit@orbit` and restart. Verified 30 Sep 2026 against a plain
folder.

## Notes

- Pure Python 3 stdlib. No `pip install`, ever. That is deliberate, so it
  runs on a locked-down laptop.
- The plugin hook runs `python`; on a Mac where only `python3` exists, alias
  it or install python.org Python.
- Built and maintained by Dom Bartolo. Questions to dom.bartolo@circleagency.co.uk.
