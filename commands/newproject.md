---
description: Open a new Circle job - tracker code first, then Teamwork and SharePoint
---

Use the `circle-new-project` skill. Job: $ARGUMENTS

Order is not optional:

1. **Project Tracker first.** Read the client sheet, find the first
   pre-numbered row with an empty description. That is the real job code.
   Confirm it with the user before creating anything.
2. Create the Teamwork project named `<CODE> - <Job Name>`.
3. Copy the SharePoint `_NEW_Project_Folder_Template` to `<CODE> - <Job Name>`.
4. Fill in the tracker row.
5. Say plainly that Xero and the resource schedule are still manual.

The Teamwork list is not authoritative for job numbers and has caused a
rename before. Trust the tracker.
