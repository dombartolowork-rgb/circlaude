---
name: blender-previz
description: Build a grey 3D blockout of a real space in Blender from a floor plan and photos, animate a planned camera move, and render it as a guide video, either as previz in its own right or for an AI video model (Seedance) to paint the real place over a camera move we control. Use for venue fly-throughs, drone orbits, walkthroughs, product moves, or any shot where the camera must do exactly what was planned. Triggers on "blockout", "previz", "drone shot", "fly-through", "orbit", "360 shot", "camera move", "walkthrough", "guide video". For a model of a space and still renders (including layouts for Nano Banana), use blender-spaces instead.
---

# Blender blockout previz

The technique: Claude writes the Blender Python, the grey blockout becomes the shot,
and an AI video model paints reality over it. The blockout alone is also useful:
editors use it as stand-in CAD, and clients see the move before anything is spent.

**Invoking it:** where this says `circle`, run `"$CLAUDE_PLUGIN_ROOT/bin/circle"`
unless `circle` is already on PATH (on Windows, `bin\circle.cmd`).

**Blender** is free from blender.org. `circle blender-find` shows which one Orbit
will use (Program Files on Windows, /Applications on a Mac).

**Templates** are in `$CLAUDE_PLUGIN_ROOT/tools/blender/`. Copy one into the job's
folder and edit the copy, never the template:
- `orbit_template.py`: an outdoor courtyard and one continuous 360 drone orbit
- `walkthrough_template.py`: a room and a keyed camera path (door to stage)
- `previz_lib.py`: shared helpers (boxes, gable roofs, decals, render). Keep it next to the copy.

```
circle blender-run <job>/orbit.py -- <out_dir> preview <textures_dir>   # 4 stills at half size, seconds
circle blender-run <job>/orbit.py -- <out_dir> full <textures_dir>      # the guide video, a few minutes
```

## 1. Gather the evidence first

Get the **final** floor plan, not the concept plan; concept plans put things in
the wrong places. Then get event photos and, best of all, any **empty-venue footage**.
Pre-build scamps and concept visuals show intent, not what was built, so never lay
them over the plan as truth. Ask someone who was there where things actually stood:
plans and what was built often differ (booths where PCs were planned, and so on).

## 2. Build the blockout

- Boxes for buildings, with real gable roofs from vertices (`building()`). Primitive
  cones or cylinders as roofs go wrong.
- Flat, distinct colours per zone. The templates set the Standard view transform,
  because AgX washes blockouts out.
- Keep foreground objects (parasols, poles) **off the camera path**. The AI returns
  anything that passes close to the lens as flat grey shapes.
- **Map the real signage on as image panels** with `decal()`. Crop each shopfront,
  sign and photo-op from a front-on photo:
  `circle img-crop photo.jpg --box x,y,width,height -o textures/sign.jpg`.
  Plain-coloured stand-ins come back as invented artwork.
- **Every feature you want must exist in the blockout.** The AI does not invent
  structure the guide video lacks: a missing entrance stays missing.
- Preview first: render the 4 stills and look at every one before the full render.

## 3. Camera

- **Orbit:** a parent empty rotating 0 to 360 degrees with linear keys, the camera
  parented to it with a Track To constraint on a centre target. 18mm lens, about 6m
  up, a radius that clears the buildings. One continuous move holds far better than a
  winding FPV route.
- **Walkthrough:** `KEYS` of (frame, position, tilt, yaw). Yaw 180 looks down -Y,
  -90 east, 90 west; keep values continuous or the camera spins.
- **Turns:** keep them gentle. A sharp turn or a fast swing round a subject (75
  degrees in 4 seconds) makes the AI hard-cut. When the shot needs a new angle, end
  the take and cut in the edit.
- **Decal facing:** east wall decals need `rot_z=-90`, west walls `90`, and a screen
  facing back down the room `180` (otherwise it is mirrored). Keep props (TVs, easels)
  clear of the signage behind them.

## 4. Optional: AI video over the blockout

This needs an account on an AI video service (Seedance via Higgsfield or Magnific),
and it costs credits, so check with whoever holds the budget first. Under Circle's
AI policy, only use services the agency has approved.

What worked:
- **Video reference plus a few photos.** Use the signage-mapped blockout as the video
  reference, about 6 real photos as image references, and a prompt stating drone
  height, the move ("one continuous take") and the sky. This looked like real drone
  footage, held the orbit and kept the signage close.
- **Not too many photos.** About 30 photos overrode the guide: the camera dropped
  to ground level.
- **Prompt-only restyle of the blockout.** It kept the camera move perfectly but looked
  like a game render.

Rules:
- **Only references that agree with the whole take.** A close-up with no head in it
  made a character's hat vanish mid-shot. State props that must persist ("the SAME hat
  for the whole shot").
- **Placeholders are traced literally.** A grey disc for a puddle came back as a flat
  disc. For organic effects (liquids, plants, melting), drop the blockout and give a
  start frame plus a prompt asking for real-world physics.
- **Sound:** prompt for sound effects only, no music, unless asked.
- **Resolution:** AI output is often 720p. Upscale only the approved final take, then
  `circle vid-1080` to land exactly on 1080p.
- **Signage:** AI text still drifts, so for finals plan to have the editor track the
  real artwork on.
- **Checking:** run `circle vid-sheet` on every take and look at it before showing anyone.

## 5. Where things go

Keep the script copy, textures, previews and renders together in the job's folder,
versioned v1, v2 and so on.
