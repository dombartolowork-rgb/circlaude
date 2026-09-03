# Systems

## Microsoft 365 (Outlook, SharePoint, Teams)

Access is via **Microsoft Graph**, using device-code auth against Microsoft's
first-party Office client `d3590ed6-52b3-4102-aeff-aad2292ab01c`. That client
is pre-consented on Circle's tenant, so no Azure app registration and no
admin approval are needed. (The "Microsoft Graph Command Line Tools" client
is blocked on this tenant, which is why the Office one is used.)

Token at `~/.circle/graph_token.json` (chmod 600), refreshed silently. Sign in
once with `circle login`. Check scopes with `circle whoami`.

**The claude.ai Microsoft 365 MCP connector is read-only** on this tenant. It
reads fine, but every **write** (copy, upload, draft, create) must go through
Graph, via the library:

```python
import os, sys
sys.path.insert(0, os.path.expanduser("~/CirClaude/lib"))
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
