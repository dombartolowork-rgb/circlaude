# Teamwork project codes

Ids are point-in-time. **Reconfirm before committing time**, because projects and
ids change: `circle tw-projects "<code or stem>"` (or `twprojects-list_projects`
with a `search_term` on the Teamwork MCP connector, if that is what is attached).

Client prefixes: **CCEP** = Coca-Cola Europacific Partners, **SUB** = Subway,
**FR** = Frontier Developments, **CC** = Costa variants, **N1** = N1 Partners.

## Internal

**354873 - Non-billable activities**, `billable: false`. Log to a **task inside**
it, not the bare project. See `circle-timesheet` for the task ids.

## CCEP

| Shorthand seen in calendar or email | Code | Teamwork id |
|---|---|---|
| CCEP Weekly Catch Up (billable, settled) | CCEP General Account Management | 365652 |
| Feeding Britain's Future, Wakefield, Morrisons video | CCEP393 | 365891 |
| ARTD **budget / videographer sourcing** | CCEP374 ARTD CBP 2026 | 362989 |
| ARTD **filming logistics, quotes, shoot** | CCEP399 ARTD Sizzle Film & CBP Day Filming | 366092 |
| Brand Plans 2026, brand-plan video edits | CCEP397 | 365930 |
| Brand Plan 2027, ABP 2027, "Road to 6th July" | CCEP389 | 366091 |
| Powerade, Commonwealth Games activations | CCEP392 | 364883 |
| Glasgow shoot, East Kilbride Baton Relay, King's Baton | CCEP401 | 366479 |
| 360IA sell-in videos | CCEP353 | 360495 |
| Virtual / May Town Hall | CCEP378 | 365889 |
| DRS video work | CCEP318 | 360102 |
| Half One Video GB CSSC (Kayleigh reels, P&C Q&A) | CCEP300 | 357127 |
| Year-end recon jobs | CCEP340 / CCEP346 | 359975 / 360238 |

**ARTD has two codes.** Budget and sourcing is CCEP374; filming logistics and the
shoot is CCEP399. Getting this wrong is the most likely mistake here.

## Subway

| Shorthand | Code | Teamwork id |
|---|---|---|
| Subtopia (an activation *inside* SUB100) | SUB100 | 363123 |
| Latitude festival, "subway ads" on a Latitude week | SUB115 | 364178 |
| Cookieway | SUB107 | 363601 |
| Players Cup | SUB126 | 366012 |
| Bournemouth 7's / "B7's" | SUB100 | 363123 |
| Spudway (award-winning jacket potato launch) | SUB067 | |

### Live 2026 Subway jobs, read from the Project Tracker 29 Jul 2026

Teamwork ids for SUB113-119 confirmed from the connector 4 Aug 2026. Where the
Teamwork project name carries different dates to the tracker, both are shown:
**the Teamwork name is what the job is actually booked as.**

| Code | Job | Dates | Teamwork id |
|---|---|---|---|
| SUB110 | SBGB PARK Concrete Waves, Newquay | 9-12 Jul '26 | |
| SUB111 | SBGB STREET BaySixty6, London | 12-13 Sep '26 | |
| SUB112 | NI FA Finals | 4 May '26 | |
| SUB113 | CarFest | 28-30 Aug '26 | 364176 |
| SUB114 | Camp Wildfire | Aug-Sep '26 | 364177 |
| SUB115 | Latitude | 23-26 Jul '26 | 364178 |
| SUB116 | Boardmasters | 5-9 Aug '26 | 364179 |
| **SUB117** | **Ballout London Finals** | tracker 4-11 Aug, **Teamwork 25-26 Aug** | 364180 |
| **SUB118** | **Ball Out Regional Qualifiers '26** | tracker 7-14 Jul, **Teamwork 1-2 Aug** | 364181 |
| **SUB119** | **KISSTORY Bristol Day Party** | **27 Jun '26** | 364182 |
| SUB120 | PR Stunt, Grilled Chicken | Apr '26 |
| SUB121 | C3 Journalist Launch | Jun '26 |
| SUB122 | Melt House Launch, Southampton Swaythling | |
| SUB123 | Summer Merch (separate rows UK / Germany / Netherlands) | |
| SUB124 | SBGB Nationals Shoelaces | May-Jul '26 |
| SUB125 | C4 Student roadshow | 2026 |
| SUB126 | Subway Players Cup 2026 Series | |
| SUB127 | Subrina & Subastian Rewrap | Summer '26 |
| SUB128 | Microsite Updates, Latitude Social & Festivals | 2026 |
| SUB129 | C5 Festive | 2026 |

Ella Bell is client services lead on nearly all of these.

**"Ball Out" is a recurring property with many codes**, so the year and stage
matter: SUB052-055 and SUB071 are all Deadcode. For 2026 the qualifiers
(SUB118) and the finals (SUB117) are **separate jobs**, so post-production has
to be pinned to the right one rather than to "Ball Out".

**"Kisstory" is a Subway job, not a separate client, and there are two of them.**
SUB119 (364182) is the **Bristol Day Party, 27 June**. SUB097 (**362006**) is
**KISSTORY July '26**, which is the one Ryan shot on Sat 25 July and the one the
summer edits belong to. SUB097 is confirmed for the July work. Do not default to
SUB119 just because it appears in the live-jobs table.

## Frontier

| Shorthand | Code | Teamwork id |
|---|---|---|
| Planet Zoo 2, Chester Zoo events, **"Wallace"** | FR001 | 364004 |

**"Wallace" is Frontier's internal codename for Planet Zoo 2.** Wallace Preview
and Launch Event work books to FR001. Frontier work is **billable**, not
business development.

## Finding a code

0. **The Project Tracker is authoritative**, and is the place to look when a
   campaign name means nothing to Teamwork. Verified working recipe:

   ```python
   import os, sys
   sys.path.insert(0, os.path.expanduser("~/CirClaude/lib"))
   from circle import graph
   DRIVE = "b!btnAx0EMLUaFyzSCxuDrhOoZ9iBVLqhMoaIg-ctFYgk8FFSkIzgKRZsYdgK9oiXv"
   ITEM  = "01LHYCQA575R6LB4GBZVI2EFJVZ7YDCTJB"
   # one worksheet per client; reading is fine without a workbook session
   st, _, d = graph.call_retry("GET",
       f"/drives/{DRIVE}/items/{ITEM}/workbook/worksheets/Subway"
       "/usedRange(valuesOnly=true)?$select=values")
   rows = d["values"]           # col B = PROJECT NO., col C = DESCRIPTION
   ```

   Columns: A CLIENT, B PROJECT NO., C DESCRIPTION OF PROJECT, D CLIENT CONTACT,
   E CLIENT SERVICES LEAD, F PROJECT MANAGER, G DEADCODE, H DATE CLIENT APPROVED
   BUDGET. A row with "Deadcode" in G/H is closed, so do not book to it.
   Only **writes** need a persisted workbook session; reads do not.

1. `twprojects-list_projects` with `search_term` - fastest, returns code + id. A
   code stem works too: `"SUB11"` returns SUB113 through SUB119 in one call.
2. SharePoint project folders are named `<CODE> - <Job Name>`, so searching for
   the activation name usually pins it down. Campaign names often differ from job
   names.
3. Finance trackers as a fallback: "CCEP Project Finance Tracker.xlsx", "Subway
   Payment Tracker V2.xlsx". These use **merged cells**, so code-to-job pairings
   can be ambiguous. Never commit a code taken only from these.

## Companies and categories (for creating projects)

Company **118392 = CCEP**, category **24893 = Campaign Library**. Also 118389
Costa Coffee, 118623 Costa Express, 118624 Costa RTD. Only create projects for
clients whose account you actually work on. If a code belongs to another team's client, ask where to book the time instead.
