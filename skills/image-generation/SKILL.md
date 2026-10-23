---
name: image-generation
description: Make or edit images with Google's Nano Banana models through Circle's own key - concept visuals, mood frames, storyboard frames, a Blender layout painted into a realistic still, a product or set dressed into a real space, variations of an existing image. Use when someone asks to "generate an image", "make a visual", "mock this up", "concept image", "storyboard frame", "Nano Banana", "Gemini image", "paint over this render", "make this look real", or "put our stand in this venue".
---

# Image generation (Nano Banana)

**Invoking it:** where this says `circle`, run `"$CLAUDE_PLUGIN_ROOT/bin/circle"`
unless `circle` is already on PATH (on Windows, `bin\circle.cmd`).

```
circle img-gen "prompt" -o concept.png                               text to image
circle img-gen "prompt" --ref layout.png --ref venue1.jpg -o v1.png  guided by references
circle img-gen "prompt" --model pro --size 2K --aspect 16:9 -o v1.png
circle img-models                                                    the model ids this key can use
```

## Before the first image

- **The key.** It is Circle's, billed to the agency, and lives in `~/.circle/gemini_key`
  (or the `GEMINI_API_KEY` variable). Never print it, paste it into chat or commit it. If
  it is missing, the command says so: ask whoever holds Circle's Google Cloud account.
- **Only a billed key.** Google's free tier can use what you send to train its models, so
  a key from a project without billing must never see client material.
- **Policy.** Follow Circle's AI policy: no personal data or confidential client material
  unless the tool is approved for it, and say when a visual is AI-generated.
- **It costs money per image.** Roughly 5p to 20p each depending on model and size
  (check Google's pricing page; it changes). `--n 4` is four charges. Every call is
  logged to `~/.circle/image_log.csv`.

## Choosing the model

- `--model 2` (default): Nano Banana 2. Fast and cheap; right for exploring.
- `--model pro`: Nano Banana Pro. Better text, likeness and fine detail; use it for the
  frame that goes to a client, not for the twenty that do not.
- A newer model may exist: `circle img-models`, then pass its id to `--model`.
- `--size 2K` is the default. 4K only for the approved final.

## References

`--ref` images reach the model **in the order given**, so the prompt can say "image 1",
"image 2". Up to 10; Pro holds about 6 objects reliably. Fewer, better references beat
many: a pile of photos dilutes what matters.

- Say what each reference is for: "image 1 sets the layout and camera; images 2 and 3
  show the materials and lighting".
- Without `--aspect`, the output follows the first reference's shape, so put the layout
  or the frame you are matching first.

## Painting a Blender layout into a realistic still

The main use. The `blender-spaces` skill renders the layout; this paints reality over it.

```
circle img-gen "Image 1 is a 3D layout of a function room. Keep its exact camera angle,
perspective and the position and size of every object. Render it as a real photograph of
the room in images 2 and 3: their wood floor, wall colour and window light. The red block
is a branded photo wall; the dark platform is a stage with a screen. No outlines, no text."
  --ref space_entrance.png --ref room1.jpg --ref room2.jpg --aspect 16:9 -o entrance_v1.png
```

This is a first recipe, not yet proven on a real job: update this section with what
works. Things to try when it goes wrong:
- **It moved things or changed the camera:** fewer photo references, and repeat "keep the
  exact layout of image 1" at the end of the prompt.
- **It drew the outlines:** render the still without them (`LINES = False`, or
  `render_stills(..., lines=False)`).
- **It invented artwork:** map the real artwork onto the blockout as a decal, so it is
  in image 1, or pass the artwork as its own reference and say where it goes.

## Rules that came from real jobs

- **An approved likeness is the asset.** Never put an approved face or character plate
  back through the model to relight it or change the pose: each pass softens the face
  and the client notices. Use the plate itself, and ask the model only for faces that
  do not exist yet.
- **Work from originals, not outputs.** Generating from a frame of an earlier AI output
  is a second generation, and quality drops at each step.
- **Look at the saved file**, at full size, before showing anyone. Check hands, text,
  logos and anything the client knows well.
- **Iterate by editing**: pass the last good image back as `--ref` with a short change
  ("same image, make the lighting evening"), rather than rewriting the whole prompt.
- Each image is saved with its prompt beside it (`v1.txt`), so a good result can be
  reproduced and a bad one explained. Keep versions in the job folder: v1, v2.
