---
description: Make the client copy of a budget - tidied, renumbered, checked to the penny, the original never touched
---
Use the `circle-client-copy` skill. Budget: $ARGUMENTS

1. **Get a copy.** A SharePoint link: `circle clientcopy-fetch`. A file on the
   computer: use it as it is. Say which budget it is, who last changed it and
   when.
2. **Read it** with `circle clientcopy-check`. If the lines do not add up to
   the worksheet's own totals, say what is off and stop.
3. **Propose the changes**: drop-downs in column C that do not suit the
   description, and obvious spelling mistakes in column D. Never reword a
   description. Show every change as before and after, list the lines that need
   a person's decision, and wait for a go.
4. **Build** with `circle clientcopy-build`. It writes Claude's copy of the
   workbook and a values-only client Excel beside the budget, and changes
   nothing in the budget itself.
5. Report the total, what was left out, what changed and what is still open,
   and open the files. Do not send or upload them without being asked.
