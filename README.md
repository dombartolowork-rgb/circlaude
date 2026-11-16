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
reconciles against Sent Items, a loose-ends sweep that finds the emails
nobody answered and what each one is holding up (`/loose-ends`), day planning
that blocks your tasks into Outlook round your meetings (`/plan-day`), timesheet drafting from the calendar, sent mail
and what you worked on in Claude (`claude-activity`), opening a new job in the
right order, telling finance a client needs billing (`/bill-client`), the weekly status deck, PowerPoint decks (`circle-decks`: read and summarise a deck, pull a slide out, build new decks on Circle's brand master (`deck-brand`, `deck-layouts`, `deck-add-slide`, `deck-fill`), build slides that match the deck they're going into as "to be merged" files, merge them in without breaking sections or hidden slides, swap text and pictures, and render slides to check them, with `deck-text`, `deck-render`, `deck-pick`, `deck-replace`, `deck-swap-image`, `deck-insert`), the annual leave handover, writing a call up as a Word brain dump with every link shared (`/brain-dump`), making the client copy of a budget without touching the budget (`/client-copy`: tidied, renumbered, checked to the penny against the worksheet, as a linked copy of the workbook and a values-only Excel), clearing Pleo expenses
(receipts found and attached, each one coded to the right job), handling
client transfers and shared SharePoint files safely, SwissTransfer downloads,
and taking a section out of a video too big to download.

And production tools: downloading and clipping YouTube, TikTok and Instagram
video (`yt-get`, `yt-clip`, `yt-find`), quick frame-exact edits with ffmpeg
(`vid-cut`, `vid-join` with dissolves, `vid-sheet` contact sheets, `vid-1080`,
`vid-pushend`, `vid-frames`), checking a cut against its amends or brief with a
timecoded verdict per amend (`/review-cut`, `vid-review`, VO transcribed on the laptop), Blender blockout previz for venue fly-throughs and
drone orbits, Blender models of real spaces (measured, or imported from a phone
scan) with still renders from chosen angles (`blender-run`, templates in
`tools/blender/`), and image generation with Google's Nano Banana models on
Circle's own key (`img-gen`), which can paint those stills into realistic
pictures. Public Fathom share links for drafts, taken from the user's own Chrome when Claude in Chrome is connected, or from Orbit's own clean browser after they sign in (`fathom-share`, with `browser-open`, `browser-eval`, `browser-close` for other sites with no API). Uploading to Circle's Vimeo, Unlisted with a review link
(`vi-upload`), on Circle's own key.

**Sending is gated.** Orbit ships a hook that makes every send, forward,
meeting invite and shared-file change ask you for confirmation, whatever
permission mode Claude Code is in. Personal diary blocks with nobody invited
go straight in. Nothing leaves your account unreviewed.

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
- **Git** - Orbit's instructions run through Git's shell. The Microsoft Store
  version works, no IT needed
- **Python 3.12** - the Microsoft Store version (Python Software Foundation)
  works, no IT needed. It gives `python` rather than `py`; `circle.cmd` falls
  back to it
- **ffmpeg** (for video and clips) - `circle yt-setup --ffmpeg` fetches it into
  `~/.circle/bin`, or IT push it. Checking VO in a cut needs a build with whisper
  speech recognition: the one `yt-setup --ffmpeg` fetches has it
- **Blender** (optional, for previz and spaces) - free from blender.org
- **Circle's Vertex AI key** (optional, for image generation) - from whoever holds
  Circle's Google Cloud account, saved during `/orbit:onboard`; never commit it
- **Circle's Vimeo key** (optional, for uploading to Vimeo) - from Dom, saved during
  `/orbit:onboard`; never commit it

On a Mac, Python and Git are usually already present; install ffmpeg separately.

## Setup

Orbit installs straight from this public GitHub repo. In Claude Code:

```
/plugin marketplace add dombartolowork-rgb/circlaude
/plugin install orbit@orbit
```

Restart Claude, then run `/orbit:onboard`, which does the rest with you. See
`ONBOARDING.md` for the plain-English version. `/orbit:help` shows everything
Orbit can do, with a walkthrough.

Updates: bump `version` in both `.claude-plugin` files and push; users run
`/plugin marketplace update orbit` then `/plugin update orbit@orbit` and
restart.

## Notes

- Pure Python 3 stdlib. No `pip install`, ever. That is deliberate, so it
  runs on a locked-down laptop.
- The plugin hook runs `python`; on a Mac where only `python3` exists, alias
  it or install python.org Python.
- Built and maintained by Dom Bartolo. Questions to dom.bartolo@circleagency.co.uk.
