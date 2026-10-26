---
name: video-edit
description: Quick, frame-exact video edits without Premiere - trim, join with hard cuts or dissolves, retime, build a silent looping screen video, fit to 1080p, push in over the end of a clip, and make contact sheets to check work. Use when someone asks to "cut this down", "trim", "join these clips", "make a loop for the screen", "crossfade", "speed it up", "make it 1080p", "check this video", "put it on Vimeo", "Vimeo link", or to inspect a file's length, size or audio.
---

# Video edits with ffmpeg

**Invoking it:** where this says `circle`, run `"$CLAUDE_PLUGIN_ROOT/bin/circle"`
unless `circle` is already on PATH (on Windows, `bin\circle.cmd`).

**Needs ffmpeg.** On Windows, `circle yt-setup --ffmpeg` installs it into
`~/.circle/bin`. Elsewhere install it or ask IT. Every command says so if it is
missing.

| Job | Command |
|---|---|
| What is this file? | `circle vid-probe a.mp4 b.mp4` |
| Trim | `circle vid-cut a.mp4 --from 4.2 --to 0:19.8` |
| Trim and speed up 25% (pitch kept) | `circle vid-cut a.mp4 --from 2 --speed 1.25` |
| Join, hard cuts | `circle vid-join out.mp4 --clip a.mp4 --clip b.mp4 2 7.5 --clip c.mp4` |
| Join with half-second dissolves | add `--dissolve 0.5` |
| Silent loop for an AV screen | `circle vid-join loop.mp4 --clip a.mp4 --clip b.mp4 --silent --fill --size 1920x1080 --fps 30 --trim-ends 0.2` |
| Fit inside 1920x1080 | `circle vid-1080 big.mp4` (add `--pad` for exactly 1920x1080) |
| Push in over the end to match the next shot | `circle vid-pushend a.mp4 out.mp4 --ramp 1.5 --scale 1.28` |
| Contact sheet to check it | `circle vid-sheet out.mp4 --count 9` or `--times 0 3.5 7` |

`--clip FILE [IN [OUT]]`: times are seconds or m:ss. Leave OUT off for "to the end".
It is a separate option rather than `file:in:out` because Windows paths contain colons.

## How it behaves

- Everything re-encodes to H.264 and AAC MP4, so cuts are frame exact and the result
  plays in PowerPoint, Teams and on phones.
- Pieces of different sizes are letterboxed to the first piece's size, or cropped to
  fill with `--fill`. A piece with no audio gets silence for its length.
- Dissolves eat into the running time: N pieces lose (N-1) x the dissolve.
- `--trim-ends` shaves both ends of every piece, which hides the wobble at the start
  and end of phone footage.

## Check the result, not the command

A command that ran cleanly can still produce the wrong thing. Always look at the
output before saying it is done:

- `vid-probe` for length, size and audio.
- `vid-sheet` for the content: open the image and look at it.

Report what you checked.

## Putting it on Vimeo

`circle vi-upload cut.mp4 --name "CCEP420 THINK Pod - V2"` uploads to Circle's Vimeo
account as **Unlisted**, with a review link for frame-accurate comments. It needs
Circle's Vimeo key (`circle vi-setup`, or `/orbit:onboard`); if it is missing, say
Dom gives it out.

- Upload only when the person has asked for it. It puts the file on the agency's
  account, so the hook asks them to confirm.
- Check the file before uploading (`vid-probe`, `vid-sheet`), not after.
- Run it in the background and do not pipe it into `head` or `tail`: progress goes
  to stderr, and a 3GB file takes around 20 minutes. Dropped connections resume on
  their own.
- **Uploaded is not playable.** Vimeo then transcodes. Before anyone is sent the
  link, run `circle vi-video <id>` and wait for `transcode complete`, `playable
  True` and a real duration. Until then the link shows a spinner.
- `vi-list` finds a video's id (the link can be had mid-upload from there),
  `vi-comments <id>` reads review comments.
