---
description: Tell finance a client needs billing - verify the job and the amount, then an "Invoice client" task for Helen in Teamwork
---

Use the `circle-bill-client` skill. Job: $ARGUMENTS

1. **Confirm the job.** The user gives a code or describes the job. Check it
   in the Project Tracker and Teamwork, and say the code and name back.
2. **Verify the amount.** Take the newest budget in the job's
   `02.Finance/Budgets` folder; failing that, the approved client copy PDF in
   the user's inbox. Bring the total through **inc VAT**, show the working,
   and say where it came from.
3. Look in the project's **Finance** tasklist for an "Invoice client" task
   that is already filled in. If there is one, show it and stop.
4. Draft the task: client entity and address, amount inc VAT, PO number (or
   "N/a"), and who the invoice goes to. Show the full text and wait for a
   clear go, because creating it emails Helen.
5. Create it, assigned to Helen Chapman and tagged **Client Billing**.
