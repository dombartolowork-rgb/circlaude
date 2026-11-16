---
description: See everything Orbit can do, then try one with a guided walkthrough
---

The user wants to know what Orbit can do. They may not be technical. Use plain
English, never the words API, CLI, PATH, token, skill or repository unless they
use them first, and never paste a command at them to run.

## 1. Build the menu from what is installed

Do not rely on a list written here. Read the `description:` line of every
`"$CLAUDE_PLUGIN_ROOT/skills/*/SKILL.md"` and every
`"$CLAUDE_PLUGIN_ROOT/commands/*.md"`, quietly, so anything added since this
was written shows up. Skip `circle-conventions` (it is house rules, not a job)
and `help` itself.

Group what you find into these headings, in this order, putting anything new
under whichever fits best:

1. **Decks** - build a Circle-branded deck from the brand template, slides to
   match a pitch or client deck, pull slides out, merge into a master
2. **Images** - concept visuals, mood and storyboard frames, a set or stand
   painted into a real venue
3. **Email and diary** - what you owe a reply on, drafting replies, morning
   brief, planning your day, loose ends, booking meetings
4. **Timesheets and money** - timesheets, billing a client, Pleo expenses,
   client copies of budgets
5. **Jobs and files** - opening a new job, the weekly status deck, leave
   handovers, brain dumps from a call, client transfer links and zips
6. **Video and 3D** - YouTube clips, quick edits, checking a cut against
   amends, Vimeo, Blender previz and models of a space
7. **WhatsApp**

Show it as a short numbered list: the heading, one line on what it is for, and
one example of something they could say, in quotes. Decks and Images first,
because they are what most people use. Keep the whole menu to one screen.

End with:

> Pick a number and I'll show you how it works, using your own work. Or just
> ask for something in your own words, you never need the menu.

## 2. Walk them through the one they pick

When they choose (a number, a heading, or something in their own words):

- Read that area's SKILL.md properly before saying anything about it.
- Say in two or three sentences what it does and when it is useful.
- Give three things they could say, written the way a person talks, from
  simple to ambitious.
- Offer to try one **for real, now**, on their own work: "Want to try it? Tell
  me what you're working on and I'll do the first one with you."
- If they say yes, do it, following that skill exactly. Afterwards, say in a
  line what they could ask next ("you can ask me to change the colours, or add
  a slide on the budget").

Then ask if they want to see another one, and show the menu again only if
they say yes.

**Decks:** suggest a two or three slide test, such as a title slide and an
agenda for something they are actually working on. Build it on Circle's brand
template, open it in PowerPoint for them, and say it is a real file they can
edit.

**Images:** suggest one concept image for something they are working on.
Before you try, check the image key is set up: the file `~/.circle/vertex_key`
exists. If it does not, do not try: say image making needs a one-off setup and
that Dom can sort it, or that `/orbit:onboard` will do it if they have the key.

**Email, timesheets, WhatsApp:** say plainly, before they try, that nothing is
sent or posted without them seeing it and saying yes. That is built in.

**Anything that needs a setup they have not done** (Teamwork, WhatsApp, Vimeo,
video tools, Blender): do not troubleshoot. Say it needs a quick setup, offer
`/orbit:onboard`, and move on.

## Things not to do

- Do not list every command or skill name. They want to know what they can
  get done, not what the parts are called.
- Do not demo anything that sends, posts, uploads or deletes. Drafts and new
  files only.
- Do not show raw output, file paths or errors. Say what it means for them.
