# Cir'Claude, for Circle colleagues

This gives Claude Code the ability to work with your Circle email, calendar,
the staff directory and Teamwork, plus the agency processes we have written
down (triage, timesheets, opening a job, the weekly status deck).

You use **your own** Microsoft and Teamwork credentials. Nothing is shared,
and no one else can read your mail through this. Email cannot be sent without
you confirming it first: that guard is built in.

## What you need first

Raise these with IT as **one** request, not three:

1. **Claude Code Desktop**
2. **Git** - required by Claude Code Desktop on Windows
3. **Python 3** - Windows does not ship it; `winget install Python.Python.3.12`
   installs per-user without admin rights

## Setup (Windows)

In PowerShell:

```powershell
git clone https://github.com/dombartolowork-rgb/circlaude.git $HOME\CirClaude
cd $HOME\CirClaude
bin\circle login
```

`login` prints a short code and a URL. Sign in once in a browser with your
Circle account, and you are done: the token is cached and refreshes itself.
It is stored at `~/.circle/graph_token.json`, outside the project folder, so
it cannot end up in a repo.

Check it worked:

```powershell
bin\circle whoami
```

So you can type `circle` from anywhere, add the folder to PATH:

```powershell
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";$HOME\CirClaude\bin", "User")
```

(Restart the terminal after that.)

For the timesheet commands, add your own Teamwork key from
Teamwork > your avatar > Edit My Details > API & Mobile:

```powershell
[Environment]::SetEnvironmentVariable("TEAMWORK_API_KEY", "<your key>", "User")
```

## Install the plugin

In Claude Code:

```
/plugin marketplace add https://github.com/dombartolowork-rgb/circlaude
/plugin install circlaude@circlaude
```

Or skip all of the above and run `/circlaude:onboard` after the plugin is
installed: it walks through sign-in, the Teamwork key, and your timesheet
preferences interactively.

## Try it

```
circle inbox --limit 10        # numbered; the [number] is the id
circle read 3
circle agenda --week
circle who <a colleague's name>
```

Then just ask in plain English: "what do I need to reply to today", "draft a
reply to Richard about the status deck", "am I free Thursday afternoon", "did
I log all my time last week".

## Three things to know

**It drafts before it sends.** Email goes to your Drafts and you see the text
before anything is sent, and actually sending always asks you to confirm.
That is deliberate and built in, not a setting.

**It will not guess an address.** It looks people up in the Circle directory.

**Timesheets never post without your go.** `circle tw-log` is a dry run by
default, and your own conventions are saved to `~/.circle/timesheet-policy.md`
the first time you set them.

## If something breaks

- "Not signed in" → `circle login` again.
- Teamwork commands failing → check `TEAMWORK_API_KEY` is set (new terminal
  after setting it).
- `python` opens the Microsoft Store → install Python properly with winget,
  or use `py -3`.

Ask Dom (dom.bartolo@circleagency.co.uk) if you get stuck.
