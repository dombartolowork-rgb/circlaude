---
name: footage-from-youtube
description: Find, download and clip moments from YouTube, TikTok or Instagram videos (gameplay, creator content, reviews, our own films) - search recent uploads, locate the moment from auto-captions, fetch only that section, cut frame-exact clips, check them on a contact sheet, and hand them to an editor. Use when someone asks for "footage of X", "clips of", "gameplay showing", "download this YouTube/TikTok/Short/reel", or reference shots for an edit.
---

# Footage from YouTube, TikTok and Instagram

**Invoking it:** where this says `circle`, run `"$CLAUDE_PLUGIN_ROOT/bin/circle"`
unless `circle` is already on PATH (on Windows, `bin\circle.cmd`).

**First time on a laptop:** run `circle yt-setup` (on Windows, `circle yt-setup --ffmpeg`
also fetches ffmpeg). It downloads yt-dlp and Deno into `~/.circle/bin` and checks
each against its published checksum. Re-run it when downloads start failing:
YouTube changes often and a fresh yt-dlp usually fixes it.

**Rights:** only download what Circle can use: our own films, client-supplied
material, or reference for internal work. Creators' footage in a client deliverable
needs the creator's permission, so flag that to whoever asked.

## Whole videos

```
circle yt-get <url> [<url> ...]          # saves to ~/Downloads/YouTube
```

It picks the best HD video and audio streams and merges them, never the combined
360p file. It also trims to YouTube's stated duration, because HD streams can carry
a frozen tail well past the real end. A missing audio stream is an error, never a
silent file. TikTok and Instagram reels come back as one file with sound.

## A moment from a long video

1. **Find candidate videos.** Search recent uploads with YouTube's "this week" filter:
   ```
   ~/.circle/bin/yt-dlp --flat-playlist --playlist-end 20 --print "%(id)s|%(duration)s|%(channel)s|%(title)s" "https://www.youtube.com/results?search_query=<words+joined+by+plus>&sp=EgIIAw%253D%253D"
   ```
   Run several queries (the thing's name, "gameplay", "review"), then de-dupe.

2. **Find when it is said.**
   ```
   circle yt-find <url> "the phrase"
   ```
   Auto-captions mishear names (a brand name often comes through as ordinary words), so
   search a short, distinctive word. Captions say when something is *mentioned*,
   not when it is *on screen*: pad a few seconds either side.

3. **Fetch only that section.**
   ```
   circle yt-clip <url> --from 1:12:30 --to 1:13:10
   ```
   Long streams stay quick because only the section is fetched. If that fails, it
   downloads the whole video and cuts locally.

4. **Look at it before handing it on.**
   ```
   circle vid-sheet "<clip>.mp4" --count 9
   ```
   Then open the sheet image and actually look. Note facecams and stream overlays for
   the editor, and check the subject is really on screen. A clip that downloaded
   cleanly can still be the wrong moment.

5. **Tidy and name.** Trim with `circle vid-cut`, fit to 1080p with `circle vid-1080`.
   Name clips `<Subject>_<shot>_<Creator>.mp4`.

## Handing it to an editor

Put the clips in the job's SharePoint folder (see the circle-files skill for large
uploads) and draft a short note listing each clip, what it shows, and which need
cropping. Drafts only: the person who asked sends it.
