---
description: Morning brief - today's calendar, unread mail, replies owed
---

Give the user a tight morning brief. Run these, then report, do not dump raw
output.

```bash
circle agenda --attendees
circle inbox --limit 25 --preview
```

Report in this order, and keep it short:

1. **Today** - meetings with times and who is in them. Flag anything needing
   prep, and anything that clashes.
2. **Needs a reply** - only threads they genuinely owe. Ignore newsletters,
   automatic replies and calendar notices. Where a thread looks unanswered,
   check `circle thread <id>` before listing it, because people reply from
   their phones. See the `circle-inbox-triage` rule: reconcile against Sent
   Items.
3. **Deadlines and commitments** visible in the mail, with dates.

End with the two or three things that actually matter today. No filler, no
restating the calendar back in prose.
