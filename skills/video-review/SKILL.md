---
name: video-review
description: Check a video cut against the amends, client feedback or brief it was made to - build the list of what was asked for, gather evidence from the file (shots, supers, VO transcript, loudness, what changed since the last version), give each amend a verdict with a timecode, and report in chat before anything goes anywhere. Use when someone sends a new version of an edit, asks "have they done the amends", "check this cut", "check v2", "QC this", "review the edit", "does it match the brief", "is it ready to send to the client", or pastes a Vimeo, WeTransfer, SwissTransfer or SharePoint link to a cut.
---

# Checking a cut against amends or a brief

**Microsoft sign-in:** if a `circle` command here fails with "Not signed in to Microsoft" or "Run: circle login", follow `"$CLAUDE_PLUGIN_ROOT/reference/sharepoint-signin.md"` to sign them in, then carry on. Don't show them the error.

**Invoking it:** where this says `circle`, run `"$CLAUDE_PLUGIN_ROOT/bin/circle"`
unless `circle` is already on PATH (on Windows, `bin\circle.cmd`). Needs ffmpeg:
see `video-edit`. Load `circle-conventions` before writing anything for someone
else to read.

The job is to answer one question honestly: **did the editor do what was asked, and
did anything else change or break?** The checks that are genuinely numbers
(duration, loudness, black frames, which shots changed) are measured. Anything about
how the film looks or feels gets looked at, and if it can't be judged from stills
and a transcript, it goes back to the user as **Needs your eyes**.

## The rule that matters most

**Never mark something Done because a number moved or a shot changed.** A
changed shot only shows that the editor changed something, not that they made
the change that was asked for. Open the frame or the before-and-after pair and
check that it shows what was asked.

Plausible metrics have repeatedly passed work a person rejected on sight:
total duration when a quarter of the speech was missing, pixel change when the
character no longer looked like himself, a single sync figure that hid drift.
So:

- every **Done** cites a frame you looked at, or a transcript line
- every visual judgement comes from looking at the frames
- anything to do with feel, pacing, grade subtleties, music mood, lip sync or a
  likeness is **Needs your eyes**, with the timecode to look at

## 1. Build the checklist before touching the video

Work out what the cut is being judged against. Look for, in this order:

- **the latest amends round**: the email thread (Microsoft 365 connector), a
  WhatsApp chat with the editor or client, Vimeo review comments
  (`circle vi-comments <id>`), or a call. For a call, read the Fathom
  **transcript**, not the summary, because summaries garble timings and asks.
- **earlier rounds**, so an old note that has come back is caught
- **the brief**: length, aspect ratios, deliverables, supers, legal lines, end
  card, music, subtitles

The job code in the file name (CCEP420_V2, SUB125...) is the quickest way into the
thread and the job folder. If you can't find anything to check against, ask the
user what was asked for rather than reviewing blind.

Turn it into a numbered list, one amend per line. Split compound notes ("tighten
the intro and lose the second logo" is two items). Keep **who asked** and their
**exact words** for each, because the user needs to see if you have read an
amend wrong.

## 2. Get the files

- **local file or job folder**: use it
- **WeTransfer, SwissTransfer, Dropbox**: `circle-files` / `swisstransfer`, and
  download now, because the links expire
- **YouTube, Vimeo or other video links**: `circle yt-get <url>`
- **the previous version**: find it too (job folder, earlier transfer, earlier
  Vimeo). The comparison is the most useful evidence there is.

**A streamed copy is not the master.** A file pulled from a Vimeo or YouTube page
has been re-encoded: its resolution, bitrate and loudness are the platform's, not
the editor's. Check the content on it, but report the spec only from the delivery
file, and say which one you checked.

## 3. Gather the evidence

```
circle vid-review CCEP420_V2.mp4 --prev CCEP420_V1.mp4
```

It writes `<video>_review/` beside the file:

| What | Where |
|---|---|
| spec, loudness, black, silences, shots, transcript, comparison | `review.json` |
| a still every ~2s of every shot, big enough to read supers | `frames/` |
| one labelled thumbnail per shot, 16 to a sheet | `sheets/` |
| timecoded VO and dialogue | `transcript.txt`, `transcript.srt` |
| before-and-after pairs for every shot that changed | `compare/` |

Options: `--no-speech` to skip the transcript, `--language fr` (or `auto`) for
other languages, `--model base` if it's slow, `--model medium` if it mishears.
Shots are found from hard cuts: a dissolve or a whip can hide a cut, so lower
`--scene` (0.2) if the shot count looks too low.

**The transcript is speech recognition, run on the laptop: the audio never leaves
it.** It mishears brand names, product names and people's names. If the transcript
differs from the script on a name, mark it **check by ear**, not wrong. If it says
`NOT TRANSCRIBED`, the VO was not checked: say so, don't assume it's right.

## 4. Look, then judge each amend

Read `review.json`. Look at **every contact sheet**, at the **frames** wherever
there's text on screen (supers, lower thirds, legal lines, end card), and at
**every pair** in `compare/`. Read text letter by letter for spelling,
capitalisation, hyphens and punctuation: this is where most errors get past people.

Give each checklist item one verdict:

| Verdict | When |
|---|---|
| **Done** | you can point at the frame or transcript line that shows it |
| **Partly** | some of it was done; say exactly what is missing |
| **Not done** | the evidence shows it unchanged, or done differently |
| **Needs your eyes** | it's about how the film feels, or can't be judged from stills and a transcript |

Then sweep for what nobody asked about:

- **changed but not asked for**: every changed, added or removed shot in the
  comparison that no amend explains, plus any change to the transcript.
  Unrequested changes are often accidents.
- **text**: spelling, client and product names exactly as the brand writes them,
  legal lines and T&Cs present and readable for long enough, end card, URL and
  handles
- **brand**: the client's rules (logo clear space, colours, strapline). On
  Circle's own films: never more than one orb on screen, and the logo and the
  strapline never together.
- **vertical (9:16)**: supers and logos clear of the bottom fifth and the right
  edge, where platform buttons and captions sit
- **technical**: length against the brief; loudness (about -14 LUFS for social
  and web, -23 for UK broadcast); true peak above -1 dBTP; black or flash frames;
  a silent gap mid-film; sound cutting off at the end; file name against the
  delivery spec

## 5. Report in chat first

Nothing goes anywhere until the user has read it. Keep it short:

> **CCEP420 V2** (1:50, 1920x1080, 25fps), against Marta's amends of 22 Oct and V1
>
> | # | Amend (who) | Verdict | Where |
> |---|---|---|---|
> | 1 | Swap the opening for the wider shot (Marta) | Done | 0:00 |
> | 2 | Hyphen in Coca-Cola on the end card (Marta) | **Not done** | 1:47 |
> | 3 | Make it punchier (Rich) | Needs your eyes | whole film |
>
> **Changed but not asked for:** shot at 0:32 trimmed by 0.6s.
> **Also found:** super at 1:12 sits in the 9:16 caption zone. 1:50 against a 1:47 brief.

Under the table, one line per thing that needs the user's eyes, with the timecode.
Show the relevant frames or before-and-after pairs inline if the user can see
images. If nothing failed, say so plainly, and list what you could not check.

## 6. Then ask where it goes

Once they've read it, ask with `AskUserQuestion` (multi-select), offering:

- **Email the editor**: a reply on the amends thread with timecoded notes, in
  house style, **as a draft**, shown in chat in full first (`circle-email`). If
  several people are named, put them all on one email.
- **Report in the job folder**: write the checked findings to a JSON file and
  run `circle vid-review-doc findings.json --out "<job> <version> review.docx"`
  (the JSON shape is in the command's docstring; images are paths from
  `frames/` and `compare/`). Show it, then on their go
  `circle vid-review-upload <docx> --folder <job folder link>`. It never
  overwrites, so a new round gets a new name.
- **Comment on Vimeo**: only for a video on Circle's Vimeo. Show the text first,
  then `circle vi-comment <id> --file notes.txt` on their go. The API can't pin
  a note to a timecode like the review page does, so the timecodes go in the
  text, and **anyone who can open the video can read it, the client included**.
  Say so before posting.
- **WhatsApp the editor**: the same notes, short, via `circle-whatsapp`, after
  confirming the recipient
- **Nothing**: the chat report was enough

Notes to an editor read as a list they can work through: timecode, what's wrong,
what to do. Lead with what's still not done, then the new issues, then thanks.
Nothing about the review process or the tools.
