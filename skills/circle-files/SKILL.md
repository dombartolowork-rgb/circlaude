---
name: circle-files
description: Handle client and supplier files safely - fetch WeTransfer and other transfer links before they expire, extract big zips without silent truncation, find what a client uploaded to SharePoint, overwrite a shared SharePoint file without wiping a colleague's edit, and share a folder externally and check it actually worked. Use whenever a transfer link arrives, a client says they have uploaded something, a zip needs extracting, a shared deck or workbook needs updating, or someone outside Circle needs access to a folder. Triggers on "wetransfer", "we.tl", "transfer link", "they sent a link", "download the files", "unzip", "extract", "client uploaded", "can't find the files", "Transfer site", "share the folder", "give them access", "update the deck", "overwrite", "423", "locked".
---

# Files from clients and suppliers, and shared SharePoint files

Every rule here is one that has already gone wrong on a live job.

**Invoking it:** where this says `circle`, run `"$CLAUDE_PLUGIN_ROOT/bin/circle"`
unless `circle` is on PATH. On Windows run Python as `py -3`, elsewhere `python3`.
Download to a scratch or temp folder, never into a project folder.

## Transfer links: download the moment one arrives

Three client asset drops expired uncollected in a single week, one of them on a
**two hour** link. So when a transfer link turns up, fetch it before doing anything
else, and check the real expiry rather than assuming seven days.

Then put the files somewhere durable (the job's SharePoint folder) and tell whoever
needs them that this is now the copy to work from. A transfer is never the working
copy. The longer-term fix is to ask clients to upload to a Circle folder instead:
one client used a folder within five minutes of being given access.

Check chat as well as email: freelancers send deliverables by whichever route is to
hand, so "nothing in the inbox" is not "nothing has arrived".

### WeTransfer, headlessly

It works without a browser while the link is live. A 403 `"No download access to
this Transfer"` means the link has **expired**, not that it is blocked.

Resolve a `we.tl` short link with `curl -sIL` to get the transfer id and security
hash from the final URL. If the URL has a middle segment
(`/downloads/<transfer>/<recipient>/<hash>`), pass it as `recipient_id` too.

```bash
# the file list, real sizes and expiry, no sign-in needed
curl -sS -X POST "https://wetransfer.com/api/v4/transfers/<id>/prepare-download" \
  -H "Content-Type: application/json" -d '{"security_hash":"<hash>"}'

# one file at a time: returns direct_link
curl -sS -X POST "https://wetransfer.com/api/v4/transfers/<id>/download" \
  -H "Content-Type: application/json" \
  -d '{"security_hash":"<hash>","intent":"single_file","file_ids":["<file id>"]}'
```

**Pull files one at a time with `single_file`**, not `entire_transfer`. No zip to
extract, you can skip files you already have, and the link lasts about four hours
rather than about ten minutes. An `entire_transfer` link expiring mid-download
killed a 6GB fetch at 92%.

`prepare-download` gives the total size up front: **check it against free disk
before starting**. If the disk is tight, fetch, verify, upload, delete, one file at
a time. Downloads resume (`curl -C -` with a freshly minted link), so a dropped
file does not have to start again.

A single-file transfer serves the file itself, not a zip, whatever the name says.

SwissTransfer has its own skill. TransferNow and Dropbox Transfer need a browser.

## Big zips: extract with Python, and check every file

A 6.5GB zip of ten renders extracted **two files, truncated a third, and stopped
without an error**. The truncated video went to a client-facing review link at 36
seconds instead of six minutes before anyone noticed. Archives written by transfer
services often need Zip64 handling that built-in unzip tools get wrong.

Use Python's `zipfile`, which is stdlib and handles Zip64, and check each entry as
you go:

```python
import os, zipfile
z = zipfile.ZipFile(SRC)
for info in z.infolist():
    if info.is_dir():
        continue
    out = os.path.join(DST, info.filename)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if os.path.exists(out) and os.path.getsize(out) == info.file_size:
        continue                                    # already good
    with z.open(info) as fin, open(out, "wb") as fout:
        while True:
            b = fin.read(8 << 20)
            if not b:
                break
            fout.write(b)
    assert os.path.getsize(out) == info.file_size, info.filename
```

**Byte size is necessary, not sufficient.** Before a video goes to anyone, open it
and check it plays for its real length. Better still, avoid the zip entirely by
pulling files one at a time as above.

## "The client says they uploaded it, but the folder is empty"

Each job has **two** folders with the same name:

- **Campaign Library**: `sites/campaignlibrary/Shared Documents/<Client>/<CODE> - <Name>/`,
  the internal job folder made from the 13-folder template.
- **Transfer**: `sites/Transfer/Shared Documents/<Client> Transfers/<CODE> - <Name>/`,
  where clients and contributors upload.

On a client-supplied job the Campaign Library folder stays empty of client assets
indefinitely, which looks exactly like "nothing was sent". One brief confidently
reported no uploads when the Transfer folder held fifteen photographs and a video.
**Check both before telling anyone content is missing**, and ask which folder they
used rather than guessing.

Graph site search is refused on these tokens, so resolve the site by path:

```python
graph.call("GET", "/sites/circleagency.sharepoint.com:/sites/Transfer")
# then /sites/<id>/drive/root:/<Client> Transfers/<CODE> - <Name>:/children
```

## Overwriting a shared file (decks, trackers, workbooks)

**Re-download immediately before editing, and re-check `lastModifiedDateTime` and
`size` just before uploading.** A colleague edited the weekly status deck while an
update was being built; uploading the stale copy would have wiped their changes
with no warning and no conflict error.

**423 Locked** means someone has it open in the desktop app. Do not keep retrying,
and never force a whole-file replace over a lock: that discards what they are doing
in it. An interrupted upload session discards itself, but re-read size and modified
time to confirm nothing changed, then either wait or hand the content to the user
to paste in.

Excel writes need a persisted workbook session: a sessionless PATCH returns 200 and
silently does not stick. Some formatting (tab colour, freeze panes, copying a
sheet) is not reachable through the API at all; offer the user the two-second
click rather than rebuilding the file.

## Sharing a folder with someone outside Circle

**Never trust the invite response. Check the folder's permissions afterwards.**
Both failure modes have happened on one job: a 504 timeout where the grants were
applied anyway and surfaced over the next few minutes, and a 200 success where
nothing was created at all (most likely a guest invitation limit after a large
batch).

So read `/permissions` before and after, compare against who should have access,
and grant a few at a time with a pause. Make sure it is the **Transfer** folder, not
the Campaign Library one of the same name: granting on the wrong one looks like it
worked and achieves nothing.

External sharing puts client material in front of someone new, so confirm who and
which folder with the user before granting, and let them do large batches through
the SharePoint Share button if the permission prompt refuses it.
