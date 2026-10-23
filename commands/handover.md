---
description: Build the annual leave handover doc - two weeks of signal, traffic lights, Circle's format
---

Use the `circle-handover` skill.

First ask two things if the user has not already said: **their last working day
and return date**, and **who is covering** which clients. The cover window drives
what counts as urgent, so guessing it makes every traffic light wrong.

Then gather two weeks of mail and calendar through the Microsoft 365 connector,
pin the job codes with `circle tracker find`, ask about anything agreed on WhatsApp, pull
transcripts (never summaries) for calls that carried a decision, group the
signal into projects, and set a light: `active`,
`attention` or `unlikely`.

Report back in chat first, grouped by light, one line per project. Build the
document only once they have seen that list, and upload only when they say go.
