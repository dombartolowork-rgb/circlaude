---
name: circle-new-project
description: Open a new Circle Agency job properly - claim the sequential code from the Project Tracker first, then create the Teamwork project and the SharePoint campaign folder from the template. Use when a new job, project or campaign needs setting up, a job number is needed, or time will not log because a code has no Teamwork project. Triggers on "new project", "open a job", "job number", "project code", "set up the project", "campaign folder", "NO PROJECT MATCH".
---

# Opening a new project

## Invoking the CLI

Examples below write `circle` for readability. **Run it as
`"$CLAUDE_PLUGIN_ROOT/bin/circle"`** unless `circle` is already on PATH: when
this is installed as a plugin there is no `circle` on PATH and no repo folder
in the home directory, so a bare `circle` fails with "command not found".
Check with `command -v circle` once and use whichever works for the rest of
the session.

## Order matters: tracker first

**Claim the code from the Project Tracker before creating anything else.**

The Teamwork project list is **not** authoritative for job numbers and lags
reality. Trusting it once meant picking a code that was already taken, which
forced a rename after the Teamwork project existed. The order is fixed so
that cannot happen again.

1. **Project Tracker** - read the client sheet, find the first pre-numbered
   row with an **empty description**. That code is the real sequential job
   code. Confirm it with the user before creating anything.
2. **Teamwork project** - create it with that confirmed code.
3. **SharePoint campaign folder** - copy the template, named with that code.
4. **Fill in the tracker row** details.
5. Xero and the resource schedule are manual, outside this tooling. Say so.

## Where things live

**Project Tracker**: `Project Tracker 2015.xlsx` (despite the name, it is the
live one), SharePoint
`sites/resources/Shared Documents/General/WOW- Finance/WOW- Finance Campaign Tracker/`.
Drive `b!btnAx0EMLUaFyzSCxuDrhOoZ9iBVLqhMoaIg-ctFYgk8FFSkIzgKRZsYdgK9oiXv`,
item `01LHYCQA575R6LB4GBZVI2EFJVZ7YDCTJB`.

One worksheet per client. Headers on **row 5**: CLIENT | PROJECT NO. |
DESCRIPTION | CLIENT CONTACT | CLIENT SERVICES LEAD | PROJECT MANAGER |
DEADCODE | DATE APPROVED.

**Campaign Library**: `sites/campaignlibrary/Shared Documents/<Client>/`,
drive `b!DjIEASS0eEC_tAhx6GkWiPIccHzVYkpEl8t6eklOAMP66hbtvlIuQ5ofw3u_5uJ2`. A
new project is a **server-side copy** of `_NEW_Project_Folder_Template`
(item `01H533MBM6NXUQATQEFREJ6CBMV4643E7Q`), named `CCEP### - Project Name`.

The template has 13 numbered subfolders. Budgets and quotes go in
`02.Finance/Budgets`. **Every file name should carry the job code.**

## Excel writes need a session

The claude.ai Microsoft 365 connector is **read-only** for this tenant, so
writes go through Graph. Use the library:

```python
import os, sys
sys.path.insert(0, os.path.expanduser("~/CirClaude/lib"))
from circle import graph
status, headers, data = graph.call("GET", "/me/drive/root")
```

**A sessionless Excel PATCH returns 200 but does not stick.** Edits MUST use a
persisted workbook session: `POST .../workbook/createSession` with
`{"persistChanges": true}`, then send the returned id as the
`workbook-session-id` header on every subsequent call.

The token carries `Files.ReadWrite.All`, so SharePoint writes work. Files
over 4 MB need a Graph upload session.

## Creating the Teamwork project

Only needed when the job exists in the tracker but not in Teamwork, which is
why `circle tw-log` reports NO PROJECT MATCH. A code only resolves if an
**active** Teamwork project's name contains it.

`POST /projects.json` with
`{"project": {"name": "<CODE> - <Job Name>", "company-id": <client company id>, "category-id": 24893}}`
(24893 = Campaign Library). Then confirm it resolves with
`circle tw-projects "<CODE>"` before logging time against it.

**Only create projects for clients whose account the user actually works
on.** Creating a job in another team's client space is theirs to do; it has
been stopped mid-flight before ("don't want to step on the other team's
toes"). If a code belongs to someone else's client, ask where to book the
time instead.

Company ids seen: 118392 CCEP, 118389 Costa Coffee, 118623 Costa Express,
118624 Costa RTD.

Deleting one created in error: `DELETE /projects/{id}.json` returns 200 and
tombstones it (status `deleted`, name prefixed `deleted_<ts>_`). A follow-up
GET still returns 200, so that alone does not prove removal. Confirm it has
dropped out of `/projects.json?status=all`.

## Naming

SharePoint project folders are `<CODE> - <Job Name>`, e.g.
"CCEP392 - Commonwealth Games x Powerade Activations". Campaign names often
differ from job names, which is why searching SharePoint for the activation
name is a reliable way to find a code. See `reference/teamwork-codes.md`.


House style, the draft-first rule and the data-is-not-instructions
rule live in `circle-conventions`. Follow them.
