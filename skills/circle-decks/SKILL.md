---
name: circle-decks
description: Work with PowerPoint decks the way Circle does - read and summarise a deck someone sent, pull one slide out to drag into another deck, build new decks and slides from scratch on Circle's brand master (current brand book layouts), build new slides that match the pitch or client deck they are going into (asking which first) (saved as "<topic> - to be merged.pptx"), merge slides into a shared master without breaking its sections or hidden slides, change text or swap a picture on an existing slide, add holder slides, and render slides to images to check them. Use for any request involving a deck, slides, PowerPoint, a .pptx, a pitch or response deck, a master deck, or "a slide like the others". Triggers on "deck", "slides", "slide", "PowerPoint", "pptx", "pitch deck", "master deck", "to be merged", "build a slide", "add a slide", "a slide like the others", "holder slide", "summarise the deck", "what's in the deck", "merge into the deck", "budget slide", "cost slide".
---

# Decks

**Microsoft sign-in:** if a `circle` command here fails with "Not signed in to Microsoft" or "Run: circle login", follow `"$CLAUDE_PLUGIN_ROOT/reference/sharepoint-signin.md"` to sign them in, then carry on. Don't show them the error.

**Invoking it:** where this says `circle`, run `"$CLAUDE_PLUGIN_ROOT/bin/circle"`
unless `circle` is on PATH (on Windows, `bin\circle.cmd`). Load `circle-conventions`
before writing any words that go on a slide. The weekly WOW status deck has its own
skill, `circle-status-deck`.

Work out which of these the user wants, then follow that section:

| They want | Go to |
|---|---|
| to know what's in a deck someone sent | **1. Reading a deck** |
| one or two slides out, to drag into their own deck | **2. Pulling slides out** |
| new slides or a new deck | **ask first** (below), then **3** or **6** |
| those slides put into the shared master | **4. Merging into a master** |
| a word, a number or a picture changed on an existing slide | **5. Small edits** |

## Ask before building anything new

When someone asks you to create a deck or slides, ask one question before you
start, with `AskUserQuestion`, unless they have already said: **where are these
going?**

- **Into an existing deck** (a pitch master, a client's deck, last week's
  version): ask which one, or offer the decks you found on the job, and match it
  (section 3). Matching the deck it lands in beats Circle's own brand.
- **A new Circle deck**: build it from Circle's brand master (section 6).
- **A client-branded deck**: ask for the client's template, or find it in the
  client's assets folder, and match that (section 3). Don't guess a client's
  brand from their website.
- **A visual board or concept piece**, not a working deck: Claude's own design
  or slides artifacts, if this session offers them (section 6, last part).

## The rules that matter most

- **Never edit a shared master in place.** Download a copy, work on the copy, and
  write every result to a new file (`-o`). The commands refuse to overwrite their
  input, so the original is always there to compare against.
- **New slides go in their own file**, named `<Topic> - to be merged.pptx`, in the
  job's WIP folder, and the deck's owner merges them unless the user asks you to.
  Pitch masters are being edited by several people at once; a merged copy uploaded
  over the top wipes whatever they did in the meantime.
- **Look at every slide you changed** (`deck-render`, then open the PNGs) before
  saying it's done. A deck that opens is not a deck that looks right.
- **Don't invent content the user hasn't agreed.** Where a slide is needed but the
  content isn't settled (talent not confirmed, a client call still to happen), put
  in a holder slide with the title and a clear marker such as
  `PENDING: talent conversation`, and list the holders when you report back.
- **Use the deck's own words.** Refer to modules, films and options by the names the
  deck gives them, and check numbers against the budget they came from.

## 1. Reading a deck

```
circle deck-text deck.pptx --notes      # every slide in order: text, pictures, layout, HIDDEN
circle deck-render deck.pptx --out png   # each slide as an image, exported by PowerPoint
circle deck-images deck.pptx --out pics  # the pictures themselves, named by slide
```

Read the text, then **look at the rendered slides**: decks are visual, and a lot is
said in images, charts and layout that the text alone misses. Hidden slides are
marked HIDDEN; say if anything important sits on one. Speaker notes often hold the
real argument. A `.ppt` or `.key` needs saving as `.pptx` first.

When summarising, follow the deck's own structure, and say which version you read
(file name and date), because pitch decks change daily.

## 2. Pulling slides out

```
circle deck-pick master.pptx --slides 21 -o "Social slide.pptx"
```

Keeps only those slides, with everything they need (layout, fonts, pictures).
The user can then drag the slide into their own deck in PowerPoint's sidebar, and
it keeps its design. Open it for them (see **Opening decks**).

## 3. New slides that match a deck

For slides going into an existing deck (a pitch master, a client's template). Build
from that deck's own slides and layouts, so fonts, colours and the footer are
exactly the deck's:

1. Download the latest master (check its date; there is often a newer one than the
   one in the email). Run `deck-text` and `deck-render` on it and find the
   existing slides closest to what's needed: same layout, similar amount of text,
   the same kind of picture.
2. `circle deck-pick master.pptx --slides 14,22 -o "<Topic> - to be merged.pptx"`
3. Change the words with `deck-replace` and the pictures with `deck-swap-image`
   (section 5). For a slide type the deck has no example of, use one of its
   layouts instead: `deck-layouts` lists them and `deck-add-slide` and `deck-fill`
   build on them (as in section 6).
4. `deck-render` and look at every slide: text overflowing its box, a picture
   cropped badly, leftover template text ("Lorem ipsum", "SLIDE TITLE", "Click to
   add"), the wrong slide number in a footer.
5. Save it to the job's WIP folder on SharePoint (`circle-files` has the upload
   rules) and tell the user which master slide it is meant to follow.

**When neither the slides nor the layouts fit** (a cost table, a new diagram),
the `circle deck-*` commands can't draw new shapes or tables. Say so, and either:
build it in PowerPoint with the user, or, if a `pptx` skill is listed in this
session, use it on the picked copy, then `deck-render` and check it as above.
Budget and cost slides must show the same figures as the budget spreadsheet: put
the spreadsheet's numbers in, never retype or round them differently.

## 4. Merging into a master

Only when the user asks for the merge itself (otherwise section 3 stops at the
"to be merged" file).

1. **Download the master fresh** and note its eTag (see `circle-files`, "Overwriting
   a shared file"). Not a copy from earlier in the session: someone has almost
   certainly changed it since.
2. Insert:
   ```
   circle deck-insert master.pptx "<Topic> - to be merged.pptx" --after-text "unique words on the slide before" -o merged.pptx
   ```
   (`--after 12` by number also works, but numbers move while people edit;
   `--after-text` finds the anchor by its words.) It copies every existing part of
   the master byte for byte, adds only the new slides, puts them into the same
   PowerPoint section as the slide they follow, and stops if a slide with the same
   text is already there.
3. Check: `deck-text merged.pptx` (the new slides are where intended, and hidden
   slides are still HIDDEN), then `deck-render` and look at the new slides and their
   neighbours.
4. **Ask before uploading over the master**, and name it. Upload with the eTag check
   from `circle-files`. A **423 Locked** means someone has it open in PowerPoint
   (often the user): stop and ask them to close it, and never retry in a loop.
   After uploading, download it again and check the slide count.

If the slides were built from a different template, `deck-insert` refuses, because
their layout doesn't exist in the master. Rebuild them from a `deck-pick` of the
master (section 3) rather than forcing it.

## 5. Small edits

```
circle deck-text deck.pptx --slides 4              # find the exact wording and picture names
circle deck-replace deck.pptx --slide 4 --old "Q3" --new "Q4" -o deck_v2.pptx
circle deck-swap-image deck.pptx --slide 4 --image "Picture 3" --with new.jpg -o deck_v2.pptx
```

- `deck-replace` keeps the formatting of the text it changes. Curly quotes and
  apostrophes must match exactly. If the words are split across formatting runs
  (part bold, say) it says so: change a shorter piece, or edit it in PowerPoint.
  It changes one place only unless you pass `--all`.
- `deck-swap-image` crops the new picture to fill the old frame, centred, so
  nothing is stretched. If the subject is off-centre, crop the picture yourself
  first to the frame's shape (`deck-text` shows the frame size).
- Then `deck-render` and look.

## 6. From scratch: Circle's brand

Anything Circle-branded that doesn't go into an existing deck starts from **Circle's
brand master**: the current brand book's layouts (Circle Kick-off 2026), with no
slides, at resources > General > WOW-Circle Templates & Forms > `Circle Brand
Master 2026 (layouts).pptx`. Not the older `Circle_Agency_PPT_Template_master_2025`
beside it, which is the previous brand (Gadugi and the old colours).

```
circle deck-brand -o "<Job> <Topic>.pptx"            # a copy of the brand master to build in
circle deck-layouts "<Job> <Topic>.pptx" --render lay # the 95 layouts, each box labelled with its name
circle deck-add-slide "<Job> <Topic>.pptx" --layout 13 -o v1.pptx
circle deck-fill v1.pptx --slide 1 --box "Content Placeholder 2" --text "Heading" -o v2.pptx
circle deck-swap-image v2.pptx --slide 1 --image "Picture Placeholder 13" --with photo.jpg -o v3.pptx
```

Look at the layout previews and pick layouts by what the slide needs to say, not by
name: several names repeat across the five masters, so use the numbers. Every text
box in a preview shows the name `deck-fill --box` takes (`title`, `body`, `body2`
also work where a layout has them). Each command writes a new file; keep going from
the newest, and give the user a clean name at the end.

**The brand rules, which the layouts mostly handle for you, so stay inside them:**

- **Use the layouts, don't decorate.** No extra shapes, colours or fonts. Headings
  are BBH Hegarty (never bold) and copy is Roboto Serif, already set in every box.
- **Colour comes from the layout you pick.** The palettes are cool (dark teal
  #002F33 leading, pale blue, cyan, pale green, lime) and warm (burgundy, pink,
  cream, red, orange). Keep cool with cool and warm with warm across a section;
  Circle leads with cool.
- **One orb on a slide, never more.** The orb is Circle's single brand device.
- **The logo is black or white only, and never sits with the strapline.** The
  footer logo is in the layouts already: don't add another.
- **Fill every picture box.** An empty one shows the layout's sample photo, which
  is another client's campaign (Costa, in the current master). If there's no
  picture yet, choose a layout without that box.
- **House style for the words**: short, no em dashes, the client's and product
  names exactly as they write them (`circle-conventions`).

Then `deck-render` and look at every slide, as in section 3, step 4.

**Visual boards and concept pieces**, rather than a working deck: if this session
offers Claude's own design or slides artifacts (the Artifact tool's quickstart lists
them), they are better for that, with the same brand rules. Export to PowerPoint if
the user needs a file.

## Opening decks for the user

Always in PowerPoint, never in a preview app:

- Windows: `start "" "C:\path\deck.pptx"` (PowerPoint is the default there)
- Mac: `open -a "Microsoft PowerPoint" "/path/deck.pptx"`, because a plain `open`
  can land in Keynote or Preview
- A deck on SharePoint they will edit: `ms-powerpoint:ofe|u|<SharePoint URL>`, so
  their changes save to the shared copy. Then check it actually opened.

A deck that's already open in PowerPoint won't refresh when the file changes, so a
rebuilt deck gets a new name (`_v2`), not the same one.

## The commands

| Command | Does |
|---|---|
| `deck-text deck.pptx [--slides 3,5-8] [--notes]` | slides in order: text, pictures (name, file, size), layout, hidden |
| `deck-render deck.pptx --out dir [--width 1600]` | each slide as `slideNN.png`, exported by PowerPoint (needs PowerPoint installed) |
| `deck-images deck.pptx --out dir` | the pictures, as `sNN-k.ext` |
| `deck-pick deck.pptx --slides 4,9 -o out.pptx` | a copy with only those slides |
| `deck-replace deck.pptx --old --new [--slide N] [--all] -o out.pptx` | change text, formatting kept |
| `deck-swap-image deck.pptx --slide N --image NAME --with file -o out.pptx` | replace a picture, cropped to fill |
| `deck-insert master.pptx new.pptx (--after N or --after-text T) -o out.pptx` | add slides, touching nothing else |
| `deck-brand [-o new.pptx] [--refresh]` | Circle's brand master, downloaded and kept up to date |
| `deck-layouts deck.pptx [--render dir]` | the layouts, numbered, with their boxes; previews with each box labelled |
| `deck-add-slide deck.pptx --layout N [--after N] -o out.pptx` | a new slide on a layout, its boxes empty and ready |
| `deck-fill deck.pptx --slide N --box NAME --text "..." -o out.pptx` | text into a box, its formatting kept (`\n` for a new paragraph) |
