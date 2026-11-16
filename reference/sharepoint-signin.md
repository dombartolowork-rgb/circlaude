# The SharePoint sign-in, on first use

Most of Orbit works through the Microsoft 365 connector and needs nothing
extra. A few jobs need Orbit's own Microsoft sign-in, because they need a
**whole file**, which the connector cannot give back (it turns Office files
into text and drops sheets from big workbooks):

- reading the Project Tracker for the next job code (`circle tracker`)
- downloading Circle's brand template for a new deck (`circle deck-brand`)
- downloading a budget for its client copy (`circle clientcopy-fetch`)
- saving a handover or a cut review to SharePoint (`handover-upload`,
  `vid-review` uploads)

Onboarding no longer asks for it. Ask the first time one of these is needed.

## How to tell

Any of those commands fails with **"Not signed in to Microsoft. Run: circle
login"** (or "Token expired ... Run: circle login") when the sign-in is
missing. That is the cue. It is not a fault: do not show them the error.

## What to do

Say what is coming, in their terms:

> To do this I need one quick extra sign-in, so I can open the full file on
> SharePoint. I'll give you a short code, you type it into a Microsoft page,
> and that's it. It signs in as you, so I can only see what you can already
> see. You only do this once.

Run `circle login` **in the background** and read its output. It prints a short
code and a URL. Give them both, clearly:

> Open **microsoft.com/devicelogin** and enter this code: **XXXXXXXXX**
> Then sign in with your normal Circle email, the same as Outlook.
> You have about 15 minutes, so no rush. Tell me when you are done.

When they say they are done, run `circle whoami` and check it reports their
address. Then run the command that failed again and carry on with what they
asked for. If it still fails, say so plainly and that Dom can sort it: do not
reason your way past it.

If the code expired, say so lightly and get a new one.
