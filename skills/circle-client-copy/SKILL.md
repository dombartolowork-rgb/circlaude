---
name: circle-client-copy
description: Turn a Circle budget workbook into its client copy - the client-facing tab tidied, renumbered and checked against the worksheet, saved as a separate "Claude's copy" of the workbook and as a values-only Excel for the client, without ever touching the original budget. Use when someone needs a client copy of a budget, a client asks for the estimate in Excel, the Client Copy or PREVIEW tab is a mess of empty lines, broken formulas or wrong numbering, or a budget needs its drop-down items and spelling checked before it goes out. Triggers on "client copy", "client-copy the budget", "client version of the budget", "client Excel", "estimate for the client", "tidy the client copy", "PREVIEW tab", "renumber the budget", "budget to send to the client".
---

# Client copy budgets

**Microsoft sign-in:** if a `circle` command here fails with "Not signed in to Microsoft" or "Run: circle login", follow `"$CLAUDE_PLUGIN_ROOT/reference/sharepoint-signin.md"` to sign them in, then carry on. Don't show them the error.

A budget workbook has a **WORKSHEET** tab (the budget itself, with IN and OUT
costs side by side) and a client-facing tab that pulls from it by formula:
**Client Copy**, or **PREVIEW** on budgets where nobody has duplicated it yet.
Getting that tab fit to send is fiddly by hand, and it is the part Orbit does.
A person still reads the result before it goes anywhere.

**Invoking it:** examples below write `circle` for readability. Run it as
`"$CLAUDE_PLUGIN_ROOT/bin/circle"` unless `circle` is already on PATH.

## The rule that matters most

**Never change the budget itself.** Whoever built it has to be able to trust
that it is exactly as they left it. Every command here reads a local copy and
writes new files beside it:

| File | What it is |
|---|---|
| `<name> - Claude's copy.xlsx` | the whole workbook, client tab rebuilt and still linked to the worksheet by formula, so a later change on the worksheet pulls through |
| `<name> - Client Excel.xlsx` | that one tab alone: values only, no formulas, no other sheets |

If the result is wrong, the original is untouched and the PREVIEW tab inside
Claude's copy is still the untouched template. Nothing here uploads anything.

## 1. Get a copy to work on

From a SharePoint link (the usual case, a budget in the job's
`02.Finance/Budgets` folder):

```bash
circle clientcopy-fetch "<the sharing link>"
```

It downloads to `Documents/Client copies` and says who last changed the budget
and when. Budgets get edited right up to the moment they go out, so **fetch
again just before the final build** if any time has passed.

A workbook already on the computer works as it is. Not Excel's `~$` lock file.

## 2. Read it

```bash
circle clientcopy-check "<budget.xlsx>"
```

This changes nothing. It prints every worksheet line that has a cost or a
description (with its **worksheet row number**, which is how lines are named
from here on), each section's drop-down options, what is wrong with the client
tab as it stands, and whether the lines add up to the worksheet's own SUBTOTAL
and TOTAL. `--json` gives the same with descriptions in full: use it for the
next step, because the text view shortens nothing but is harder to scan.

If the checks say NO, stop. A cost is sitting outside a section, or the workbook
was saved without recalculating. Tell the user what does not add up. Do not
build.

## 3. The two judgements

These are the only places judgement comes in. Make both, **show the user every
proposed change as a before and after table, and build only on their go.**

### Does the drop-down in column C suit the description in column D?

The item column is a drop-down, and budgets are built fast: lines get typed
under whatever the template row happened to say. So "Fuel" can sit next to
"HOP onsite for set up and derig". The client sees column C, so it has to make
sense beside column D.

- Choose **only from that section's own drop-down options**, as `clientcopy-check`
  lists them. The command refuses anything else.
- Settled examples: RAMS is **Additional Insurance**. A large event kit, a safety
  kit and packing materials are **Consumables**, not Postage. A hired Luton or
  chiller van is **Vehicle/Van Hire**. Van mileage is **Fuel**. Van insurance is
  **Additional Insurance**. Parking, tolls and congestion charges are
  **Parking, Fines & Tolls**. Someone from Circle on site is **Onsite Support**.
  Remote support for an AV asset is **Kit Maintenance - Skilled**. Crew for set
  up and derig is **Rigging Labour**.
- Look at how the same person labelled the same kind of line in their other
  budgets for the job. Their own precedent beats a guess.
- A line with **no item chosen** needs one, or the client sees a blank.
- **When no option fits**, do not force one. Ask. If the user wants a label that
  is not in the list (a healthcare budget once needed "Healthcare practitioners"
  and "Tests"), that goes in as a `label`: shown on the client tab only, the
  worksheet's drop-down left alone.
- Changing an item changes its GL code on the worksheet in Claude's copy. That
  is the point, but say so: it is one more reason the original is never touched.
- Leave anything you are not sure of, and list it as a question.

### Is anything in column D misspelt?

**Obvious spelling mistakes only.** "Saftey", "stratergy", "incldued",
"Wearhouse". Nothing else.

**Never reword a description.** It states what the cost includes. Change the
wording and Circle has told the client something different is included. The
command enforces this: a fix that changes the number of words, or swaps a word
for a different one, is refused. Leave grammar, capitals, abbreviations (EM,
AEM, BA, HOP, FOC, RAMS), double spaces and brand spellings alone, and mention
anything odd instead of fixing it.

### Lines to raise, not decide

`clientcopy-check` lists these under "For a person to look at":

- **A description with no cost.** Usually deliberate, a note to the client
  ("offered FOC", "not included in this budget"), so it is kept. Sometimes it is
  an internal note that should not go out. Ask about any that reads like a note
  to self; `omit` leaves a line out.
- **A cost with no description**, a hidden row that still counts, an Excel error.
- **Insurance, contingency or fee at zero**: the row is left out.

## 4. Build

Write the agreed changes to a JSON file in the scratch folder, keyed by
**worksheet row**:

```json
{
  "items":        {"119": "Additional Insurance", "121": "Fuel"},
  "descriptions": {"115": "Safety kit"},
  "labels":       {"167": "Healthcare practitioners"},
  "omit":         [26]
}
```

A description fix is the **whole corrected description**, identical to the
original but for the spelling.

```bash
circle clientcopy-build "<budget.xlsx>" --fixes fixes.json
```

No fixes file is fine when nothing needs changing. What the build does:

- carries over every worksheet line with a cost or a description, **reading the
  worksheet, not repairing the old tab**, so a broken or dragged formula on the
  old tab cannot lose a line
- leaves out empty lines, empty sections and the black "TO ADD A LINE" rows,
  with one blank row between sections
- renumbers sections 1, 2, 3 and lines 1.01, 1.02, always two digits, so line
  ten shows as 10.10 and not 10.1
- opens up each row so the whole description shows
- keeps the logo, header, terms and page set-up
- checks its own work: the lines must add up to the worksheet SUBTOTAL, and with
  insurance, contingency and fee to the TOTAL, to the penny. If not, it writes
  nothing. It then rereads the client Excel and removes both files if the total
  is off, a formula survived or a second sheet got in.

It never overwrites: a second build is saved as `v2`, because a workbook that is
open in Excel does not refresh.

## 5. Hand it over

Tell the user where the two files are, the total, the sections left out, each
change made, and every question still open. Open them for the user to read.

Which file goes to the client:

- **Normally a PDF.** Open Claude's copy, go to the client tab, and save that
  one sheet as PDF (File > Save As > PDF, "Sheet" not "Workbook"). It is already
  set to A4 portrait.
- **When the client asked for Excel**, send the `Client Excel` file. It is built
  from nothing instead of by deleting tabs, so no hidden sheet, rate calculator,
  comment or link to another workbook travels with it. A budget "saved as" with
  the other tabs deleted still carries those. The GL code column is left empty.

**Do not send, upload or attach either file without being asked**, and treat a
save into a shared SharePoint folder as a send: confirm first, and add the files
beside the budget, never over it.

## What this does not do

- It does not write or price a budget, and it does not change a cost, ever.
- It does not fix the worksheet's sums. If they are wrong, it says so and stops.
- It reads Excel's saved results. A budget edited by a tool that does not
  recalculate may carry stale figures; opening and saving it in Excel cures that.
- Budgets with a client tab laid out differently from Circle's template
  (`--sheet` names the tab) may be refused. That is the safe outcome.
