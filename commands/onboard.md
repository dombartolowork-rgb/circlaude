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

If `$CLAUDE_PLUGIN_ROOT` is set, use `"$CLAUDE_PLUGIN_ROOT/bin/circle"` for
everything below, even when `command -v circle` finds one. A `circle` already
on the PATH can belong to something else (Claude'menico, or an old circlaude
plugin), which has a different sign-in file and no `tracker` command. Only fall
back to the bare `circle` when `$CLAUDE_PLUGIN_ROOT` is empty.
Do not mention any of this to them.

**2. Check Python is there.**

Run `py -3 --version` on Windows, `python3 --version` on a Mac. If it is
missing, tell them:

> You need one thing installed first, called Python. Open the Microsoft Store,
> search for **Python 3.12**, and install the one from the Python Software
> Foundation. It is free and you don't need IT. Then restart Claude and run
> this again.

Then stop. If Windows reports a version but things still fail later, it is
probably the Microsoft Store placeholder rather than the real thing: ask them
to install Python 3.12 from the Store as above.

Only if they say they will use the video, YouTube or Blender tools: run
`circle yt-setup` (add `--ffmpeg` on Windows) to install the downloaders, and
`circle blender-find` to check Blender. Skip this for everyone else.

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

**4. No SharePoint sign-in here.**

Do not run `circle login` during onboarding, and do not mention it. The few
jobs that need Orbit's own Microsoft sign-in (job codes, the deck template,
budgets, saving handovers) ask for it the first time they are used, as
`"$CLAUDE_PLUGIN_ROOT/reference/sharepoint-signin.md"` describes. If they
already signed in on an earlier version, that still works. Go to step 5.

**5. Images, if they want them.**

Ask:

> Do you want to make images with it, things like concept visuals, mock-ups, or a
> real-looking picture of a venue? It uses Circle's account, so there is a key for
> it that Dom gives out. If you have it, paste it here. If not, we can skip this
> and you can add it any time.

If they paste it, save it without repeating it back to them:

`printf '%s' '<the key>' | circle img-setup --key-stdin`

Then make one small test picture to prove it works, and open it for them:

`circle img-gen "a white coffee cup on a wooden table, morning light" --size 1K -o ~/orbit_test.png`

> That worked, here is your first one. Just ask for images in plain words from
> now on, and you can give it photos to work from.

If it fails with a permission or key error, the key was probably copied short.
Ask them to copy it again. If it still fails, say Dom can sort it and move on.

**6. Vimeo, if they share videos.**

Ask:

> Do you ever put videos on Vimeo, to send a cut to a client or a colleague? It
> can do that for you, on Circle's Vimeo account. There is a key for it that Dom
> gives out. If you have it, paste it here. If not, skip this and add it any time.

If they paste it, save it without repeating it back to them:

`printf '%s' '<the key>' | circle vi-setup --key-stdin`

That checks the key with Vimeo as it saves. If it worked, prove it by listing the
three newest videos with `circle vi-list --limit 3`, and tell them in a sentence:

> That worked, I can see Circle's Vimeo. Just ask me to put a video on Vimeo and
> I will upload it as unlisted and give you the link to send.

Do not upload anything as a test: that would put a file on the agency's account. If
it says the key was not accepted, it was probably copied short. Ask them to copy it
again. If it still fails, say Dom can sort it and move on.

**7. Ask how they log time.** Only if they want time logging at all. If they
are just trying this out, skip it and say they can set it up later.

Before saying anything about Teamwork, check whether the **Teamwork MCP
connector** is attached to their Claude account, by quietly trying a Teamwork
tool (`twprojects-get_user_me`). Do not mention a key until that check has
failed. If it works, they need nothing else: tell them timesheets are ready
and move on. `circle whoami` saying no key is set is expected here, not a fault.

If it does not, they need to switch the Teamwork connector on. **Never ask for a
Teamwork key**: the connector replaces it. Put it in their terms:

> For timesheets I need Teamwork switched on in Claude. Open Claude's
> **Settings**, then **Connectors**, find **Teamwork**, click **Connect** and
> sign in with your normal Teamwork login. Then start a new chat and run
> /orbit:onboard again. Or skip this, it is only for timesheets.

If Teamwork is not in their list of connectors, say Dom can sort it and move on.

**8. Learn how they log their time.** Only if step 7 happened.

If `~/.circle/timesheet-policy.md` does not exist, build their timesheet
profile as the `circle-timesheet` skill describes: look at their last few weeks
of calendar, sent mail and Teamwork time first, tell them in a few lines what
their week looks like, then ask only the questions that raised, conversationally,
one at a time, with your suggestion first. Write it to that file as short
bullets and show them, so they can correct it.

Tell them how approval works, because it is the one thing they must remember:

> When I draft your timesheet, nothing goes into Teamwork until you reply
> **Final Draft Approved for logging**. A plain "yes" just answers my questions,
> so you can never log the wrong thing by accident.

**9. WhatsApp, if they want it.**

Ask, and make clear it is optional:

> Last one, and it is entirely up to you. I can connect to your WhatsApp, so I can
> check what a freelancer or the crew said, find something agreed in a group chat,
> or send a message for you. It is your own WhatsApp, so I will stick to work
> chats, and I will always show you a message before it goes. Do you want to set
> it up now? It takes about a minute, and you need your phone.

If they say no, skip to step 10 and mention they can say "connect my WhatsApp"
any time.

If yes, tell them what is about to happen **before** it happens:

> Get your phone ready. In a moment a page opens in your browser with a square
> code on it. On your phone, open WhatsApp, then:
>
> - **iPhone:** tap **Settings**, then **Linked devices**, then **Link a device**.
> - **Android:** tap the **three dots** at the top right, then **Linked devices**,
>   then **Link a device**.
>
> Then point your phone at the code on the screen. The code changes every 20
> seconds or so, and the page keeps up by itself, so just scan whatever is showing.

Then run `circle wa-connect` **in the background** and read its output as it
comes. It installs the WhatsApp link, starts it, and opens the page in their
browser. If the output says it could not open the browser, it prints the page
address instead: give them that as a link to click.

It prints `CONNECTED` once the phone has scanned the code. Then confirm with
`circle wa-status`, and tell them in a sentence, **without reading out any of
their chats**:

> That worked, your WhatsApp is connected. It starts by itself whenever your
> laptop does, so you never need to do this again. Your older messages will keep
> arriving for a few minutes. On your phone it shows as "Orbit" under Linked
> devices, which is also where you would remove it.

If it says the codes ran out, that is normal if the phone was not ready. Say so
lightly and run it again. If it says this needs an Apple Silicon Mac, or the page
says **"This needs an update"**, tell them Dom can sort it, and move on. If
anything else goes wrong, do not troubleshoot it with them: say it did not work
this time, that Dom can sort it, and carry on to step 10.

**10. Show them what to say.**

End here, with examples rather than instructions:

> That is it, you are set up. You do not need to remember any commands, just
> ask. Things people ask most:
>
> - what do I need to reply to today
> - am I free Thursday afternoon
> - draft a reply to Rich about the status deck
> - draft my timesheet for yesterday
> - did I log all my time last week
> - make me a concept image of a pop-up coffee bar in a station
> - put this video on Vimeo and give me the link
> - what did Tom say on WhatsApp about Monday's shoot
> - sort out my Pleo expenses
>
> One thing worth knowing: it will never send an email without showing you
> first and asking. Same with timesheets, it shows you what it worked out and
> waits for you to say go. So have a play, you cannot break anything.
>
> To see everything I can do, with a walkthrough, type **/orbit:help** any
> time.
