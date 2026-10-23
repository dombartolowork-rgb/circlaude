---
name: blender-spaces
description: Turn photos, phone videos, a 3D scan or a floor plan of a real space into a 3D model in Blender, then render stills from chosen camera angles - to visualise a venue, plan a build or stand, show a client the space, or give Nano Banana an exact layout to paint a realistic image over. Use when someone says "model this room", "3D of the venue", "from my photos", "from this video of the space", "visualise the space", "mock up the stand in the venue", "floor plan to 3D", "what would it look like from the door", or has a scan (.glb, .obj, .usdz, .ply) to look at.
---

# Spaces in Blender, and stills from them

For a **camera move** (orbit, fly-through, walkthrough video), use `blender-previz`.
This skill is for the space itself and **stills**: the commonest job is a layout render
that `image-generation` turns into a realistic picture, with the camera, proportions and
positions under our control instead of the model's.

**Invoking it:** where this says `circle`, run `"$CLAUDE_PLUGIN_ROOT/bin/circle"`
unless `circle` is already on PATH (on Windows, `bin\circle.cmd`). Blender is free from
blender.org; `circle blender-find` shows which one Orbit will use.

Templates are in `$CLAUDE_PLUGIN_ROOT/tools/blender/`. Copy one, with `previz_lib.py`
beside it, into the job's folder and edit the copy:
- `space_template.py`: a measured room (walls with real door and window gaps, stage, bar,
  tables, a brand wall) and four shots
- `scan_template.py`: imports a scan, sits it on the floor, prints its size, and renders
  a survey (four corners and an overhead) until you set the shots

```
circle blender-run <job>/space.py -- <out_dir> preview <textures_dir>   # half-size stills, seconds
circle blender-run <job>/space.py -- <out_dir> full <textures_dir>      # full size
circle blender-run <job>/scan.py -- <out_dir> preview <scan.glb>
circle vid-frames walkround.mp4 --every 1                              # stills from a phone video
```

## 1. Pick the route to a model

**A. Measured blockout (the default).** A floor plan, or a few tape measurements, plus
photos and videos to see what goes where. Fastest, works from anything, and the clean
flat-colour result is exactly what an image model follows best. Most jobs need nothing more.

**B. A phone scan.** An iPhone or iPad Pro with LiDAR, walked slowly round the room in a
scanning app, exported as .glb, .obj or .usdz, then `scan_template.py`. Good when the
room is irregular or full of fixed detail. Prefer an app that processes on the phone;
an app that uploads to its own servers is a new tool under Circle's AI policy, so check
it is approved before scanning a client's venue.

**C. Photogrammetry from photos or video.** Desktop software builds a model from 50 to
200 overlapping photos (`circle vid-frames video.mp4 --every 0.5` makes them from a slow
walk-round). It needs software IT have installed and usually a good graphics card.
Shiny, glass, mirrored and plain painted walls come out as holes or mush.

**Be honest about camera-roll photos.** Photos people took at an event rarely overlap
enough to scan. They are excellent **references**: for placing things in route A, and
for Nano Banana to copy materials and light from. Ask for a slow walk-round video of the
empty space when there is a chance to get one.

## 2. Build or check the model

- **Get the final, as-built layout.** Concept plans and pre-build visuals show intent,
  not what was built. Ask someone who was there.
- **Scale.** The room template is in metres by construction. For a scan, check the
  printed SIZE against one known measurement (a door is about 2.0-2.1 m high, a table
  0.75 m) and set `SCALE`; some apps export in centimetres (`SCALE = 0.01`).
- **Flat, distinct colours per object type**, and the Standard view transform (the
  helpers set it). The image model reads a colour change as a different thing.
- **Everything you want in the picture must be in the model.** A missing doorway stays
  missing. Placeholders get copied literally: a grey disc comes back as a grey disc.
- **Real artwork as decals**: crop each sign or screen from a front-on photo
  (`circle img-crop photo.jpg --box x,y,w,h -o textures/sign.jpg`) and place it with
  `decal()`. Plain-coloured stand-ins come back as invented artwork.
- **Blurry scan textures:** set `CLAY = True`. The model copies blur as if it were the look.
- **Tables:** a top plus a leg (as in the template). One solid cylinder reads as a drum.

## 3. Shots

`shot(name, position, look_at, lens)`. x runs east, y north, z up, metres.
- **Eye height 1.6 m, lens 24** matches a phone photo, so the still can sit beside the
  real photos. Wider than 18 bends the edges and the image model copies the bend.
- Choose angles a person would actually take: the entrance, the speaker's view, the
  queue, the brand moment. An overhead (lens 20, high above the middle) doubles as a plan.
- To match a real photo, stand the camera where the photographer stood, at lens 24,
  and adjust until the walls line up.
- Render the preview, **look at every still**, then render full size.

## 4. Into Nano Banana

Show the person the stills, then offer the next step rather than assuming it:
- **Make it real:** paint the space's own surfaces, light and materials over the layout,
  from their photos.
- **Reimagine it:** keep the layout and camera, change the surfaces (a new floor, the
  client's branding, an evening event look), from their description or mood images.
- **Leave it:** the clean stills are enough, for a plan or a build conversation.

Use the `image-generation` skill: the full-size still as the **first** `--ref`, two or
three real photos of the space after it, and a prompt that says to keep image 1's camera
and layout exactly. The outlines help the model read edges; if it starts drawing them,
render with `lines=False`.

## 5. Where things go

Keep the script copy, textures, scan, stills and generated images together in the job's
folder, versioned v1, v2. Save the .blend (the helpers do) so a colleague can open it in
Blender and move a camera without rebuilding anything.
