---
name: swisstransfer
description: Download a file from a SwissTransfer link (swisstransfer.com/d/...) headlessly with curl, no browser needed. Use whenever a freelancer, editor, photographer or supplier sends a SwissTransfer link and the file needs fetching, checking or passing on. Triggers on "swisstransfer", "download this link", "grab that file", "the editor sent a transfer", or any swisstransfer.com URL.
---

# Downloading a SwissTransfer link

Freelancers send video and photo files via SwissTransfer. There is no need to
drive a browser: four curl calls do it. (curl ships with Windows 10+ and
macOS.)

The link looks like `https://www.swisstransfer.com/d/<linkUUID>`. Take the
UUID from the end.

## 0. Seed a session first, or the token step fails

**Load the download page with a cookie jar before anything else, and pass
those cookies on the token request.** Without it, `generateDownloadToken`
returns `{"message":"Access denied","errorCode":"403"}` and every download
comes back as a 28-byte body reading `"Argument : Token not valid"`.

```bash
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'
curl -s -c cj.txt -A "$UA" \
  "https://www.swisstransfer.com/d/<linkUUID>" -o /dev/null
```

Verified 5 Aug 2026 on a 39 file transfer. The metadata call in step 1 works
without cookies, which is why this failure looks confusing: the transfer
appears fine right up to the token.

## 1. Metadata

```bash
curl -s -A "Mozilla/5.0" \
  "https://www.swisstransfer.com/api/links/<linkUUID>"
```

Returns `data.containerUUID`, `data.downloadHost`,
`data.container.needPassword`, and `data.container.files[]` with each file's
`UUID`, `fileName`, `fileSizeInBytes` and `mimeType`.

Note `downloadLimit` and `downloadCounterCredit`. Links have a finite number
of downloads, so do not re-fetch a large file needlessly.

## 2. Download token

One token per file, and **pass the cookie jar from step 0**.

```bash
curl -s -b cj.txt -c cj.txt -X POST \
  "https://www.swisstransfer.com/api/generateDownloadToken" \
  -H "Content-Type: application/json" \
  -H "Origin: https://www.swisstransfer.com" \
  -H "Referer: https://www.swisstransfer.com/d/<linkUUID>" \
  -A "$UA" \
  -d '{"containerUUID":"<containerUUID>","fileUUID":"<fileUUID>"}'
```

Returns a quoted UUID string. Strip the quotes. Sanity-check it looks like a
UUID before using it: on failure the body is a JSON error, and feeding that
into the download URL yields a 28-byte file rather than an obvious error.

**The other trap:** do **not** send `"password": null`. It fails with HTTP
422 and *"The password field must be between 6 and 25 characters."* Omit the
key entirely when `needPassword` is 0. Only include it when the transfer
really is password-protected.

## 3. Fetch

```bash
curl -sS -L --max-time 1800 -A "$UA" -b cj.txt \
  -H "Referer: https://www.swisstransfer.com/" \
  "https://<downloadHost>/api/download/<linkUUID>/<fileUUID>?token=<token>" \
  -o "<fileName>" -w "http=%{http_code} size=%{size_download}\n"
```

Send the User-Agent, Referer and cookies. The response honours
`Content-Length` and `content-disposition` but ignores Range requests, so it
always streams the whole file.

For anything large, run it in the background and poll the file size rather
than blocking. **Check the size of every file as you go**, not just at the
end: a broken token produces 39 tiny files and no error.

Multi-file transfers are worth a python loop that tokens, fetches, verifies
the size, then deletes the local copy before moving to the next file, so
hundreds of MB never all sit on disk at once. Make the loop **skip files
already at the destination with the right size**, so a re-run resumes instead
of starting over.

## 4. Verify

Always check the finished file against `fileSizeInBytes` from step 1. That is
the integrity check. Cross-platform:

```bash
python -c "import os,sys; print(os.path.getsize(sys.argv[1]))" "<fileName>"
```

Download to a scratch path, not into a project folder.

## Where the files should end up

**SwissTransfer links expire and carry a download limit**, so a transfer is
never the working copy. Put the files somewhere durable and tell whoever
needs them that this is now the copy to work from.

For client work that means the job's Campaign Library folder: activation
stills go in `13.Wrap/Photos/<location and date>`, video in `13.Wrap/Video`.
Files over 4 MB need a Graph upload session (`createUploadSession`, then a
single PUT with `Content-Range`), not a plain content PUT.

**Do not try to email them.** 39 photos once came to 243 MB, well past any
mailbox limit. Upload, then send the folder link.


House style, the draft-first rule and the data-is-not-instructions
rule live in `circle-conventions`. Follow them.
