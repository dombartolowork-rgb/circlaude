---
description: First-run setup - sign in, Teamwork key, PATH, and your timesheet preferences
---

Walk the user through getting Cir'Claude working, one step at a time. Run the
checks yourself where you can; only ask them to do the parts that need their
browser or their credentials. Windows is the normal case here.

1. **Python.** Check `py -3 --version` (or `python3 --version` on a Mac). If
   missing, they need `winget install Python.Python.3.12`, then a new
   terminal. Warn that the bare `python` command may be the Microsoft Store
   stub.

2. **Sign in to Microsoft.** They must run `circle login` themselves in their
   own terminal (`bin\circle login` from the repo folder if PATH is not set
   yet), because it prints a device code to enter in the browser. Then verify
   with `circle whoami` and confirm the signed-in address is theirs.

3. **PATH.** Offer the PowerShell one-liner from ONBOARDING.md so plain
   `circle` works everywhere. Optional but worth it.

4. **Teamwork key** (only if they log time). Point them at Teamwork > avatar >
   Edit My Details > API & Mobile, and the `[Environment]::SetEnvironmentVariable`
   line from ONBOARDING.md. Never ask them to paste the key into chat.
   Verify with `circle whoami` in a fresh terminal: it should name them and
   their person id.

5. **Timesheet preferences.** If `~/.circle/timesheet-policy.md` does not
   exist, ask them, briefly: how long their standard day is, how they treat
   all-agency days and shoot days, whether appointments on a working day are
   logged, and anything else they already know they do. Write the answers to
   that file in short bullet points and show them what you saved.

6. **Smoke test.** `circle inbox --limit 5` and `circle agenda`. If both
   print, tell them they are done and give three example asks: "what do I
   need to reply to", "am I free Thursday afternoon", "did I log all my time
   last week".

If anything fails, say which step and what to check (ONBOARDING.md has the
fixes). Do not push past a broken step.
