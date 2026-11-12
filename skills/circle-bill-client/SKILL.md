---
name: circle-bill-client
description: Tell Circle's finance team a client needs invoicing, by raising an "Invoice client" task in the job's Teamwork Finance tasklist, assigned to Helen Chapman and tagged Client Billing, with the amount inc VAT and the PO number if there is one. Use whenever a job is ready to bill, a client needs invoicing, or someone asks to "bill the client", "raise the invoice", "invoice Subway", "let finance know". Triggers on "bill client", "bill the client", "invoice the client", "invoice client", "raise an invoice", "client billing", "let billing know", "ready to bill".
---

# Billing a client

Every job that needs invoicing gets an **"Invoice client" task in Teamwork**.
That task is how finance learns a client needs billing, **whether or not the
client has a PO**. With a PO, the number goes in the task. Without one, write
"N/a".

## Step 1: confirm the job

The user gives either a job code (`SUB133`) or a description ("the Subway
conference drone flythrough").

- **Code given:** check it with `circle tracker find <CODE>` and
  `twprojects-list_projects` (`search_term: "<CODE>"`). Both should agree on the
  job name.
- **Description given:** search for it. Read the client's sheet with
  `circle tracker sheet <Client>` and match the description column (`tracker
  find` only looks up codes, it does not search descriptions), try
  `twprojects-list_projects` with a key word from the description, and search the
  user's mail (`outlook_email_search`) for the client and job, then read the
  code off what you find.

Say the code and full job name back to the user and get a yes before going
on. Never bill on a guessed code: the money lands on the wrong job.

## Step 2: verify the amount

Find what the client actually approved, in this order:

1. **The most recent budget in the job's finance folder.** The Campaign
   Library folder for the job is `<Client>/<CODE> - <Job Name>/02.Finance/Budgets`
   (`sharepoint_folder_search` for the job folder, then list `Budgets`). Take
   the newest version by its version number and modified date, not the first
   one listed. Read its total from the PREVIEW sheet (that is the client-facing
   view).
   `read_resource` can drop sheets and rows from an xlsx, so if the total is
   missing or looks wrong, do not trust it: go on to 2.
2. **Failing that, the approved client copy in the user's inbox.** Search the
   mail (`outlook_email_search`) for the code and the client, looking for the
   PDF budget or quote sent to the client and the client's reply approving it.
   Read the total from the PDF.

Then work out the figure **inc VAT**:

- Circle budgets total **ex VAT**. Add 20% and show the working:
  `£6,227.50 + 20% VAT (£1,245.50) = £7,473.00 inc VAT`.
- If the document already shows a VAT line or an inc VAT total, use that and
  say so.
- Clients billed from outside the UK can be zero-rated. If the client entity
  is overseas, flag it and ask rather than assuming either way.

Tell the user where the figure came from (file name and version, or the email
and its date), and flag anything that disagrees: two budget versions with
different totals, a client email approving a different number, or a PO for a
different amount. If there is a PO, its number goes in the task, and its value
should match.

## Step 3: the task

- **Project:** the job's Teamwork project, named `<CODE> - <Job Name>`, from
  step 1.
- **Tasklist:** **Finance** (`twprojects-list_tasklists` on that project).
- **Name:** `Invoice client`
- **Assignee:** **Helen Chapman**. Look her up with `twprojects-list_users`,
  `search_term: "helen"`. At the time of writing she is user 358867.
- **Tag:** **Client Billing**. Look it up with `twprojects-list_tags`,
  `search_term: "client billing"`. At the time of writing it is tag 87733.
- **Description**, in this shape (Markdown is fine):

```
Hi Helen,

Please can you bill the following:

**Project code**: <CODE> - <Job Name>

**Client entity:** <legal name>
<address, one line each>

**Amount**: £<amount> inc VAT

**PO**: <PO number, or N/a>

**Invoicing instructions**: Please send invoice to <Name> <<email>>

Many thanks,

<user's first name>
```

The amount is the verified inc VAT figure from step 2. Never guess the client
entity or address. Take them from a previous invoice task on the same client,
the contract or PO, or ask.

## Check before you create

1. **The template already holds one.** New projects are cloned from a
   template whose Finance list includes an "Invoice client" task. Read it
   first (`twprojects-list_tasks` with the Finance `tasklist_id`,
   `show_completed: true`). If it already has billing details in it, someone
   has billed this job: show it to the user and stop. If it is the blank
   template task, fill **that** task in with `twprojects-update_task` rather
   than creating a second one.
2. **Several invoices on one job** (a deposit, then a balance) each get their
   own task. Name them `Invoice client - deposit`, `Invoice client - balance`.
3. **Show the full task text and wait for a clear go.** Assigning the task
   emails Helen, so it is outbound, the same as sending an email.

## Related

- Supplier POs are a different process, in Xero, and an unapproved PO number
  never goes to a supplier.
- Opening the job and its Teamwork project in the first place:
  `circle-new-project`.
