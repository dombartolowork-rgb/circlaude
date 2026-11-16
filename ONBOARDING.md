# Orbit Assistant, for Circle colleagues

This lets Claude work with your Circle email, calendar, the staff directory,
SharePoint and Teamwork, plus the way we do things here: working out what you
owe a reply on, timesheets, opening a job, the weekly status deck, leave
handovers.

It works **as you**, through the Microsoft 365 connection IT already manage for
Claude. It can only see what you can already see, nothing is shared, and nobody
else can read your mail through it.

## What you need first

1. **The Claude desktop app**, signed in with your Circle Claude account
2. **Access to the Microsoft 365 connector** in Claude, which IT switch on
   person by person

## Setting it up

1. Open the **Microsoft Store** and install **Python 3.12** (the one from the
   Python Software Foundation). Then get **Git** from **git-scm.com** and click
   through the installer with its default settings. You don't need IT.

2. Open the Claude desktop app, click the **Code** tab, start a new session in
   any folder, and paste this in:

```
Please install the Orbit plugin: run claude plugin marketplace add dombartolowork-rgb/circlaude and then claude plugin install orbit@orbit
```

   Claude asks permission to run those two commands. Say yes.

3. Start a new session so Orbit loads, then type:

```
/orbit:onboard
```

That does the rest for you. It checks Claude can see your email and calendar,
and if you open jobs, do the status deck or write handovers, it asks you to sign
in once more: it gives you a short code, you open **microsoft.com/devicelogin**,
type the code in and sign in with your normal Circle email. That is once, not
every time.

## Using it

Just ask, in normal English. There are no commands to learn. To see
everything it can do, with a walkthrough, type `/orbit:help`.

- what do I need to reply to today
- am I free Thursday afternoon
- draft a reply to Rich about the status deck
- who is Ella's manager
- did I log all my time last week

## Two things worth knowing

**It will not send an email without showing you first.** You see the wording
and say yes before anything leaves your account. That is built into it, not a
setting someone can turn off by accident.

**It will not post a timesheet without your say so.** It shows you what it has
worked out, day by day, and waits.

So you can have a play without breaking anything.

## If something goes wrong

Tell it what happened, in normal words, and it will usually sort it. If it
says you are not signed in, ask it to sign you in again.

**Working abroad?** If it says access is "blocked by Conditional Access", that
is Circle's security policy refusing a sign-in from outside the UK, not a fault.
Signing in again will not fix it. Ask IT for a travel exception before you go,
and do not use a VPN to get round it.

If you are properly stuck, ask Dom (dom.bartolo@circleagency.co.uk).
