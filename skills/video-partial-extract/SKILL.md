---
name: video-partial-extract
description: Pull one section out of a huge video file held on Dropbox, SharePoint or any HTTP host, without downloading the whole thing. Fetches the index, works out which bytes hold the wanted section, and rebuilds a playable MP4 from just those. Use when a supplier sends broadcast records, camera rushes or multi-hour masters that are too big to download, when someone only needs a few minutes out of a long file, or when a download keeps failing on size. Triggers on "only needs the last X minutes", "the file is too big", "can we download part of it", "70GB", "broadcast record", "camera rushes", "byte range", "partial download".
---

# Taking a section out of a file you cannot download

A broadcast supplier once sent 770GB of records for a live launch event: eight
cameras at 69 to 91GB each, a 90GB programme record and two stream encodes. The
editor needed 25 minutes of it and was facing a 650GB download.

It came to 56GB, and the first camera took nine minutes.

**The file does not have to come down for you to cut from it.** An MP4 is an index
and a pile of sample data. Fetch the index, work out which bytes you want, fetch
those, and write a new file around them.

## When this applies

Any progressive MP4 or MOV on a host that honours HTTP range requests. Dropbox
does, so does SharePoint, and so do most CDNs. Check before assuming:

```bash
curl -sIL "$URL" | grep -i accept-ranges            # want "bytes"
curl -s -r 0-99 -o /dev/null -w '%{http_code}\n' -L "$URL"   # want 206
```

It does **not** apply to fragmented MP4, HLS or DASH, or where the host only
serves whole files.

For a Dropbox **file** link, change `dl=0` on the end to `dl=1` so it is a direct
download. A Dropbox **folder** link is a JavaScript page with no file URLs in it,
so ask the sender for the individual file links rather than trying to scrape it.

## Do it

The tool ships with the plugin. On Windows run Python as `py -3`, elsewhere
`python3`:

```bash
py -3 "$CLAUDE_PLUGIN_ROOT/tools/mp4tail.py" <url> <out.mp4> <tail-seconds> [--dur seconds] [--moov cache.bin]
```

Always quote the URL: Dropbox and SharePoint links carry `&` and `?`.

- `tail-seconds` is how much of the **end** of the file you want, measured back
  from the end.
- `--dur` stops the extract that many seconds after the cut instead of running to
  the end. This is how to take a window from the middle, and how to grab a few
  seconds cheaply to see what a camera is pointing at.
- `--moov` caches the index, so repeated passes on the same file cost nothing.

Put the output in a scratch or temp folder, not a project folder, and check free
disk space against the byte range it prints before it gets going.

## What it actually does

1. Range-fetch the first bytes and read the `ftyp` and `mdat` box sizes. On a
   recorder file the layout is `ftyp`, one enormous `mdat`, then `moov` at the very
   end, so this gives the index offset.
2. Range-fetch `moov` alone: typically around 13MB out of 75GB.
3. Parse the sample tables to get every sample's duration, size and byte offset.
4. Snap the in-point back to the nearest keyframe, and take the byte span from
   there to the out-point across all tracks.
5. Write a new file around the fetched slice. Codec configuration and track headers
   are copied **verbatim**, so the picture and sound are untouched.

## The traps, all of which have already bitten

**With no `--dur` you get the LAST N seconds.** Frames from that are the end of
the recording, not the start of your window. On the job above that meant end cards
and a camera abandoned pointing at a brick wall, which would have produced a
confidently wrong set of labels. Sample inside the window before describing
anything.

**A `.mov` may not have the same box order.** A programme record that did not put
`mdat` first failed where the camera files worked. If it errors on the layout,
say so rather than forcing it.

**Verify every output by watching it.** Open it, check the duration is what you
asked for, scrub to the start, middle and end, and check there is both picture and
sound. A file that muxes cleanly is not a file that is right: an early version of
this tool produced files that played audio and had no video track at all. Where
the property is "does this look correct", the check is a person looking at it.

## Cameras from one shoot usually line up

Check before assuming a tail-aligned cut gives the same moment on every angle. On
the shoot above all eight cameras started and stopped within 0.4 seconds of each
other, so the same tail length gave the same content everywhere. If the durations
printed for each file differ by more than a second or two, work out the offset
before cutting.

## Then get it to whoever needs it

Extract, deliver, delete, one file at a time, so the disk only ever holds one.

For an editor who needs to **cut**, put the files on SharePoint in the job's folder
and send the folder link. For someone who only needs to **watch**, a review link
is fine. Do not email video: it is always past the mailbox limit.

Budget for the upload, not the download. Fetching the slice ran at about 20MB/s
and uploading at about 4MB/s, so a 7.5GB camera is nine minutes down and half an
hour up.
