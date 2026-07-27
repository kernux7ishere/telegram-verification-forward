# Pet sprite

`cat-eris.webp` is the idle animation of **Eris** from
[Petdex](https://petdex.dev/pets/cat-eris), shown in the dashboard hero.

## What is committed

The full Petdex sheet is a 1536×1872 grid — 192×208 frames, 8 columns × 9 rows,
one animation state per row. Only the **idle** row (row 0, six frames) is used
here, so the sheet was cropped to that row before committing:

| | Full sheet | Committed strip |
| --- | --- | --- |
| Size | 1536 × 1872 | 1152 × 208 |
| Frames | 66 across 9 states | 6, idle only |
| File | 1782 KB | 201 KB |

Cropping cuts ~89% of the transfer. Encoding is lossless WebP: the art has hard
pixel edges and an alpha channel, which lossy WebP visibly softens.

## How it animates

Entirely in CSS ([`style.css`](../../css/style.css)) — no JavaScript:

```css
background-size: 1152px 208px;
animation: pet-idle 1100ms steps(6) infinite;   /* 0 → -1152px */
```

`steps(6)` walks `background-position` across the six frames on a 1100ms loop,
which is the timing Petdex uses for idle. The element is a fixed 192×208 at
every breakpoint — `image-rendering: pixelated` combined with a fractional
downscale would alias the art.

## Replacing it

Any 6-frame, 192×208 strip drops in under the same filename. Different
dimensions need `background-size`, the `-1152px` keyframe end, and the
`steps(n)` count updated together.

To use one of the other eight states instead, re-crop that row from the full
sheet and update the frame count:

| Row | State | Frames | Duration |
| --- | --- | --- | --- |
| 0 | idle | 6 | 1100ms |
| 1 | running-right | 8 | 1060ms |
| 2 | running-left | 8 | 1060ms |
| 3 | waving | 4 | 700ms |
| 4 | jumping | 5 | 840ms |
| 5 | failed | 8 | 1220ms |
| 6 | waiting | 6 | 1010ms |
| 7 | running | 6 | 820ms |
| 8 | review | 6 | 1030ms |

## Licensing

The artwork belongs to Petdex and its creators, not to this project. Check the
terms on the pet's page before redistributing it.
