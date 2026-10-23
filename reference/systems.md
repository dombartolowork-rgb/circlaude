# Systems

## Microsoft 365 (Outlook, SharePoint, Teams)

**Mail, calendar, people and Teams: the Microsoft 365 connector in Claude.**
Checked 30 Sep 2026: it holds read and write on mail (drafts, and Mail.Send),
calendars and files, plus Teams chat and meeting transcripts, and IT assign it
person by person. Its limits: no single-sheet read of a big workbook (it
truncates), no Excel cell writes, uploads capped at 1MB, and drafts cannot carry
attachments.

**SharePoint work beyond those limits: Orbit's own sign-in.** Device code, via
the Entra app set in `~/.circle/config.json`, falling back to Microsoft's Office
client `d3590ed6-52b3-4102-aeff-aad2292ab01c` until Circle's own app exists (the
Office client ignores the narrow scope request and returns its full set). Token
at `~/.circle/orbit_token.json`, refreshed silently. Sign in once with
`circle login`; check with `circle whoami`. Use it through the library:

```python
import os, sys
sys.path.insert(0, os.path.join(os.environ["CLAUDE_PLUGIN_ROOT"], "lib"))
from circle import graph
status, headers, data = graph.call("GET", "/me/drive/root")
```

Excel writes need a **persisted workbook session** (`createSession` with
`persistChanges: true`, then the `workbook-session-id` header). A sessionless
PATCH returns 200 and silently does not stick. Files over 4 MB need an upload
session.

## Teamwork

`circleagency.eu.teamwork.com`. `circle tw-*` uses the v1 REST API with Basic
auth from `TEAMWORK_API_KEY` in the environment: your own key, from Teamwork >
avatar > Edit My Details > API & Mobile. Your person id resolves from the key
itself, so time cannot land on someone else by default.

The claude.ai Teamwork MCP connector also works if it is attached; the CLI is
preferred because `circle tw-log` has a real dry run.

Internal time books to project **354873** (Non-billable activities), to a
**task inside it**, not the bare project. Its tasklist is **1469264**. See
`teamwork-codes.md`.

## SharePoint key locations

| What | Where |
|---|---|
| Project Tracker | `sites/resources/.../WOW- Finance/WOW- Finance Campaign Tracker/Project Tracker 2015.xlsx` |
| Weekly status decks | `sites/resources/Shared Documents/General/WOW- Weekly Status/<year>/<MM. Month>/` |
| Campaign Library | `sites/campaignlibrary/Shared Documents/<Client>/<CODE> - <Job Name>/` |

Campaign project folders carry 13 numbered subfolders; budgets and quotes go
in `02.Finance/Budgets`, finance reports in `02.Finance/Finance Reports`.

## Other

- **Fathom** meeting recordings and transcripts, via its claude.ai connector
  where attached. Good source for run-of-show detail and what was actually
  agreed on a call.
- **SwissTransfer** downloads work headlessly with curl: see the
  `swisstransfer` skill.
