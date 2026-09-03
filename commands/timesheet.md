---
description: Log time to Teamwork for a period, dry run first
---

Use the `circle-timesheet` skill. The period is: $ARGUMENTS (default: this
week).

Work in this order and do not skip step 1.

1. `circle tw-logged --week <period>` to see what is already logged and where
   the real gaps inside each day are.
2. `circle agenda --week <period> --attendees` for the calendar.
3. Sort events billable vs internal using the skill's rules and the user's own
   conventions in `~/.circle/timesheet-policy.md` (ask and offer to save them
   if that file does not exist).
4. Resolve every code with `circle tw-projects`. Never guess one.
5. Write the entries file covering only this period, then dry run
   `circle tw-log <file>`.
6. Show a table of what lands where, with each day's before → after total.

**Stop there.** Commit (`circle tw-log <file> --commit`) only after the user
explicitly says go, in that same turn.
