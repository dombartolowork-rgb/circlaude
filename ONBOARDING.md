# Cir'Claude, for Circle colleagues

This lets Claude work with your Circle email, calendar, the staff directory
and Teamwork, plus the way we do things here: working out what you owe a reply
on, timesheets, opening a job, the weekly status deck.

It signs in **as you**. It can only see what you can already see, nothing is
shared, and nobody else can read your mail through it.

## What you need first

Ask IT for these as **one** request, not three:

1. **Claude Code**, which runs inside the Claude desktop app
2. **Git**
3. **Python 3**

On Windows, Python is the one that catches people out, so mention it
specifically. On a Mac they are usually there already.

## Setting it up

You do not need to download anything, and you do not need a terminal.

In Claude Code, run these two:

```
/plugin marketplace add https://github.com/dombartolowork-rgb/circlaude
/plugin install circlaude@circlaude
```

Restart Claude Code when it asks. Then run:

```
/circlaude:onboard
```

That does the rest for you. The only part you do yourself is signing in: it
gives you a short code, you open **microsoft.com/devicelogin**, type the code
in and sign in with your normal Circle email. That is once, not every time.

## Using it

Just ask, in normal English. There are no commands to learn.

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

If you are properly stuck, ask Dom (dom.bartolo@circleagency.co.uk).
