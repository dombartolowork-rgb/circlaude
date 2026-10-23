---
description: Morning brief - today's calendar, unread mail, replies owed
---
Give the user a tight morning brief, using the Microsoft 365 connector (see the
`circle-email` skill). Report, do not dump raw output.

- Today's calendar: `outlook_calendar_search` with `query: "*"` from the start to
  the end of today.
- Mail: `outlook_email_search` with `folderName: "Inbox"`, `order: "newest"`,
  `limit: 25`.

Report in this order, and keep it short:

1. **Today** - meetings with times and who is in them. Flag anything needing
   prep, and anything that clashes.
2. **Needs a reply** - only threads they genuinely owe. Ignore newsletters,
   automatic replies and calendar notices. Where a thread looks unanswered,
   check what they sent that person first, because people reply from their
   phones. See the `circle-inbox-triage` rule.
3. **Deadlines and commitments** visible in the mail, with dates.

End with the two or three things that actually matter today. No filler, no
restating the calendar back in prose.
