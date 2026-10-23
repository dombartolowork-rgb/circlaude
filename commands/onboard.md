---
description: First-run setup - get Orbit connected to your Circle account
---

You are setting someone up who may never have used a tool like this. Assume
they do not know what an API key, a terminal, a PATH or a command line is, and
that they should not have to.

**How to talk to them.** Plain English, one step at a time, and say what is
about to happen before it happens. Never paste a command at them and ask them
to run it. Never use the words API, CLI, PATH, environment variable, token or
repository unless they use them first. If something technical goes wrong,
tell them what it means for them and what you are doing about it, not the
error text.

**Do the work yourself.** Everything here is something you run, apart from one
browser sign-in that only they can do. Do not narrate each command. Just do
it and tell them how it went.

Go one step at a time and stop at the first thing that fails. Tell them
plainly which bit did not work, and that Dom can sort it, rather than trying
to push through.

---

**1. Find the command.**

Run `command -v circle`. If nothing comes back, use
`"$CLAUDE_PLUGIN_ROOT/bin/circle"` for everything below. That is normal.
Do not mention any of this to them.

**2. Check Python is there.**

Run `py -3 --version` on Windows, `python3 --version` on a Mac. If it is
missing, tell them:

> You need one thing installed first, called Python. IT should have put it on
> your laptop, so it is worth asking them. Then come back and we will pick up
> where we left off.

Then stop. If Windows reports a version but things still fail later, it is
probably the Microsoft Store placeholder rather than the real thing.

**3. Check Claude can see their mail and calendar.**

That comes from the Microsoft 365 connector in their Claude account, not from
anything installed here. Quietly call `get_me`, then a small inbox search and
today's calendar through it. Do not show them the raw output. Tell them what you
can see, in a sentence:

> I can see your inbox and your calendar. You have four unread and a Costa
> call at two.

That is the proof it works. If the connector tools are not there at all:

> Claude is not connected to your Circle email yet. Open Claude's settings, go
> to Connectors, and switch on Microsoft 365. It will ask you to sign in with
> your normal Circle email.

If signing in to it says they are blocked or not assigned, that is IT's side:
they add people to it one by one. Say Dom can sort it, and stop there.

**4. The SharePoint sign-in, only if they need it.**

Ask first:

> Do you ever open new jobs, do the weekly status deck, or write a handover
> before leave? Those need one more quick sign-in. If not, we can skip it.

If they say no, skip to step 5. If yes, say what is coming:

> This one lets me read the Project Tracker and save files to SharePoint for
> you. I will get you a short code, you type it into a Microsoft page, and that
> is the only bit you have to do. It signs in as you, so it can only ever see
> what you can already see.

Run `circle login` **in the background** and read its output. It prints a
short code and a URL. Give them both, clearly:

> Open **microsoft.com/devicelogin** and enter this code: **XXXXXXXXX**
> Then sign in with your normal Circle email, the same as Outlook.
> You have about 15 minutes, so no rush. Tell me when you are done.

While they do that the sign-in is waiting in the background and will pick
itself up. When they say they are done, run `circle whoami` and read back the
address it reports. Then check it works with `circle tracker sheets`, and tell
them in a sentence ("I can see the Project Tracker.").

If it did not take, the code may have expired. Say so lightly and get a new one.

**5. Ask how they log time.** Only if they want time logging at all. If they
are just trying this out, skip it and say they can set it up later.

First check whether the **Teamwork MCP connector** is attached to their
Claude account, by quietly trying a Teamwork tool. If it works, they need
nothing else. Say so and move on.

If it does not, they need a key from Teamwork. Put it in their terms:

> If you want it to help with timesheets, there is a long password you copy
> out of Teamwork. It is under your avatar, Edit My Details, then API &
> Mobile. Do not paste it to me, just save it somewhere on your machine and I
> will show you where it goes. Or skip this, it is only for timesheets.

**Never ask them to paste a key into the chat.**

**6. Learn how they log their time.** Only if step 5 happened.

If `~/.circle/timesheet-policy.md` does not exist, ask them a few short
questions, conversationally, not as a form: how long their normal working day
is, what they do with all-agency days and shoot days, whether they log a
dentist appointment. Write the answers to that file as short bullets and tell
them what you have saved, so they can correct it.

**7. Show them what to say.**

End here, with examples rather than instructions:

> That is it, you are set up. You do not need to remember any commands, just
> ask. Things people ask most:
>
> - what do I need to reply to today
> - am I free Thursday afternoon
> - draft a reply to Rich about the status deck
> - did I log all my time last week
>
> One thing worth knowing: it will never send an email without showing you
> first and asking. Same with timesheets, it shows you what it worked out and
> waits for you to say go. So have a play, you cannot break anything.
