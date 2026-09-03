---
description: First-run setup - find the CLI, sign in to Microsoft, and set up time logging if you want it
---

Walk the user through getting Cir'Claude working, one step at a time. Run the
checks yourself where you can, and only ask them to do the parts that need
their own browser or credentials. Windows is the normal case here.

Stop at the first step that fails and say which one it was. Do not push past a
broken step.

1. **Find the CLI.** Run `command -v circle`. If that prints nothing, the CLI
   is at `"$CLAUDE_PLUGIN_ROOT/bin/circle"`, which is normal for a plugin
   install. Use that form for everything below. Tell them which one is in play,
   and that typing a bare `circle` in their own terminal will not work unless
   they add it to PATH themselves.

2. **Check Python.** `py -3 --version` on Windows, `python3 --version` on a
   Mac. If it is missing they need `winget install Python.Python.3.12` and then
   a new terminal. Warn them that the bare `python` command on Windows may be
   the Microsoft Store stub, which looks installed but is not.

3. **Sign in to Microsoft.** They must run `circle login` themselves, in their
   own terminal, because it prints a device code to type into a browser. Then
   verify with `circle whoami` and read back the address it reports, so they
   can confirm it is theirs.

4. **Time logging.** Optional, and worth skipping entirely if they are only
   testing the install. There are two routes and either is fine:

   - If the **claude.ai Teamwork MCP connector** is attached to their Claude
     account, that already works and needs no key at all. Check by calling a
     Teamwork tool rather than asking them.
   - Otherwise a **`TEAMWORK_API_KEY`** from Teamwork > their avatar > Edit My
     Details > API & Mobile, set in their own environment. **Never ask them to
     paste the key into the chat.** Verify with `circle whoami` in a fresh
     terminal: it should name them and show a person id.

   The difference that matters: `circle tw-log` has a real dry run and the
   connector does not, so on the connector you build the per-day table
   yourself before posting anything. Either way nothing posts without their
   explicit go.

5. **Timesheet preferences.** If `~/.circle/timesheet-policy.md` does not
   exist, ask them briefly: how long their standard day is, how they treat
   all-agency days and shoot days, whether appointments on a working day get
   logged, and anything else they already know they do. Write the answers to
   that file as short bullets and show them what you saved.

6. **Smoke test.** `circle inbox --limit 5` and `circle agenda`. If both
   print, they are done. Give them three things to try in plain English: "what
   do I need to reply to", "am I free Thursday afternoon", "did I log all my
   time last week".

If anything fails, name the step and what to check. ONBOARDING.md has the
fixes for the common ones.
