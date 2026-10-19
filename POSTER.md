# Framed movie poster pipeline (per film study)

Goal: one framed 13x19 theatrical poster per film study, filling the movie wall.
Status 2026-08-31: pipeline PROVEN end to end. Frames arrived; the kids beat the BTTF quiz
in The Poster Vault and printed + framed the first poster through the game. E.T. poster is
staged in the game (`films/e-t-the-extra-terrestrial/poster.pdf`), locked until they earn it.

## Hard rules for the poster wall

1. **BORDERLESS.** The art covers the whole 13x19 sheet, edge to edge, no white.
   `media=13x19.Fullbleed` in both the lp command and `PRINT_OPTS` in the game's app.py.
   On plain `13x19` the driver keeps a ~0.14in dead zone and a white edge comes back.
   (Say borderless, not "full bleed": it is what the printer calls it.)
2. **The title is sacred.** Every letter of the film's title stays clear of the frame lip.
   The crop comes off the billing-block edge and the billing block is expendable.
   Most posters put the title up top, so the crop comes off the bottom (bias 0.0);
   The Princess Bride puts its title at the bottom, so its crop comes off the top (bias 1.0).
3. **Sources are exactly 2000x3000 AND borderless**, meaning cropped to the artwork itself.
   A scan that includes the poster's own white paper border reads as proportionally taller
   and costs over an inch of crop instead of 0.53in, which clips the title. If a scan does
   not meet both, find a different scan rather than compromising the print.

Why a crop exists at all: a 2000x3000 scan is 2:3 (0.667) and the sheet is 13x19 (0.684).
They do not match, so 0.53in of height always has to go somewhere. Rule 2 decides where.

## Frames (decided, ordered 2026-08-30)

upsimples 13x19 Picture Frame, Set of 5, Black. $35.99 ($7.20/frame), 4.6 stars, 72K ratings.
https://www.amazon.com/dp/B08C2BC2LV
First 5-pack ordered; buy the same SKU again so the wall stays a matching set. Each frame
ships with an 11x17 mat: REMOVE the mat, mount the full 13x19 print directly.
Verified pricing note: 13x19 frames cost the same as 12x18 (sometimes less). No premium.

## Source the poster

1. TMDB posters page: themoviedb.org/movie/<id>/images/posters (filter language English).
2. Want the AUTHENTIC THEATRICAL ONE-SHEET at 2000x3000 (taglines + billing block beat
   textless versions for this wall: the credits mirror the worksheet facts). Skip
   anniversary/re-release variants unless you prefer them.
3. Originals download from: `https://image.tmdb.org/t/p/original/<file>.jpg` (plain curl works).
4. Pull the 2-3 biggest candidates, LOOK at them, pick the cleanest scan (file size is a
   decent proxy for scan quality at equal pixel dims).

## Compose (full bleed, no distortion)

**Sources must be exactly 2000x3000**. Prefer a BORDERLESS
scan, one cropped to the artwork itself: a scan that includes the poster's own white
paper border makes the artwork proportionally taller and costs over an inch to the
full-bleed crop. Check with `poster-compose.py`, which prints the trim and the crop cost.

Geometry: a 2000x3000 scan is 2:3 (0.667), the sheet is 13x19 (0.684). They do not match,
so **full bleed always crops height**: 0.53in off a borderless 2:3 scan, more if the scan
carries a white border. There is no arrangement that is both edge to edge and uncropped.

The old compose placed the art at 12.72x18.72 centered on 13x19, which stacked THREE white
margins on the print: the 0.14in compose margin, the scan's own litho border (up to 0.45in
on the BTTF scan), and the printer's 0.14in non-borderless dead zone, obvious on the
first print. `poster-compose.py` kills all three.

```bash
./poster-compose.py --manifest posters.json --outroot /tmp/posters   # all five
./poster-compose.py <source.jpg> <outdir> --bias 0.5                 # one film
```

`posters.json` holds the source and the crop bias per film. **bias 0.0 takes the whole crop
off the BOTTOM, 1.0 off the TOP, 0.5 centered.** The frame lip hides a further 0.25in per
side, so a line of type near an edge can vanish twice over: always judge a bias against a
render with the lip drawn on, never from the number alone. E.T. is 0.0 because its
anniversary line sits 88px from the top; BTTF and Goonies crop off the top to save the
billing block.

Output is `poster.pdf` at exactly 936x1368 pts (13x19in) and `poster.jpg` for the hub.
2000x3000 across 13in is ~153 ppi: proper poster quality at wall distance.

Needs Pillow: `pip3 install --break-system-packages pillow`.

## Print (ET-8550)

- Paper: 13x19 in the rear TRAY, print side UP (cassettes max out below Super B).
- `InputSlot=rear` is REQUIRED: without it the printer demands manual single-sheet rear feed (bit us on game night 2026-08-31).
  Matte stock preferred behind the frame's plexiglass (no glare doubling).
- Command (swap MediaType to photographic-glossy for glossy stock):

```bash
lp -d EPSON_ET_8550_Series -o media=13x19.Fullbleed -o InputSlot=rear -o MediaType=photographic-matte \
   -o cupsPrintQuality=High -o ColorModel=RGB -o print-scaling=none poster.pdf
```

- `media=13x19.Fullbleed` (borderless). On plain `13x19` the
  driver keeps a ~0.14in dead zone and the art comes back with a white edge.
- `print-scaling=none` because the PDF is already exact media size.
- UNVERIFIED until a test print: Epson borderless usually enlarges the image a little to
  guarantee coverage. If it does, the real crop is slightly more than the numbers above.
  Burn one sheet and measure before running the whole wall.
- A grown up approves the preview before ink flows.

## Per-film flow

1. Stage the poster in the game: `film-club-src/films/<slug>/poster.pdf` (13x19 compose) +
   `poster.jpg` (screen preview) on the computer that runs `app.py`, then restart it.
2. Kids play The Poster Vault, pass 8/10, the game walks them through loading the sheet
   (rear tray, print side up), they hit print.
3. Paper stock is matte (`MediaType=photographic-matte` in `PRINT_OPTS`); if that ever
   changes, update TWO places: this file's lp command AND `PRINT_OPTS` in
   `film-club-src/app.py`, then restart the server.
4. Reprints need the parent code (`parent_code` in `config.json`; change the default).

Printing only works from the self-hosted server. The static edition on Cloudflare Pages
has no printer, so the print step there just explains that.
