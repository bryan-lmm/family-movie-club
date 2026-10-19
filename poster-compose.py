#!/usr/bin/env python3
"""Compose a full-bleed 13x19 poster PDF from a theatrical one-sheet scan.

Three margins used to stack up on the printed poster:
  1. the compose margin (art was placed at 12.72x18.72 on a 13x19 page),
  2. the scan's OWN white litho border (up to 0.45in on some scans),
  3. the printer's non-borderless dead zone (~0.14in).
This kills all three: trim the litho border, scale the artwork to COVER the
full sheet (no distortion), and print on 13x19.Fullbleed.

13x19 is 0.684 and a one-sheet is ~0.66, so covering the sheet always crops a
little off the top and bottom. --bias moves where that crop is taken from.
Check it against the art: the frame lip hides another 0.25in per side on top of
the crop, so a line of type near an edge can vanish twice over.

Usage:
  ./poster-compose.py <source.jpg> <outdir> [--bias 0.5] [--dpi 300] [--no-trim]
     bias 0.0 = take the whole crop off the BOTTOM (protects a top tagline)
     bias 0.5 = centered (default)
     bias 1.0 = take the whole crop off the TOP    (protects the billing block)
Writes <outdir>/poster.pdf (exactly 936x1368pt) and <outdir>/poster.jpg (screen art).
"""
import argparse, os, sys
from PIL import Image

SHEET_W_IN, SHEET_H_IN = 13.0, 19.0
LIP_IN = 0.25          # the upsimples frame lip overlaps this much per side
PREVIEW_H = 900        # px, for the hub's poster.jpg


EDGE_NOISE = 8   # scans carry a dark scanner line in the outermost few pixels


def find_litho_border(im, thresh=225, frac=0.96):
    """Inset of the scan's own white paper border, in pixels (l, t, r, b).

    Starts inside EDGE_NOISE because these scans have a dark line at the very
    edge of the sheet; without the skip, one dark line hides a 70px border
    (this is exactly how the BTTF poster kept 0.45in of white on one side)."""
    g = im.convert("L")
    w, h = g.size
    px = g.load()
    sx = range(EDGE_NOISE, w - EDGE_NOISE, 3)
    sy = range(EDGE_NOISE, h - EDGE_NOISE, 3)
    row_white = lambda y: sum(1 for x in sx if px[x, y] >= thresh) / len(sx) >= frac
    col_white = lambda x: sum(1 for y in sy if px[x, y] >= thresh) / len(sy) >= frac

    def walk(is_white, lo, hi, limit):
        """First index from lo toward hi where the white run really ends."""
        i = lo
        step = 1 if hi > lo else -1
        while i != limit and is_white(i):
            i += step
        return i

    t = walk(row_white, EDGE_NOISE, h, h // 5)
    b = walk(row_white, h - 1 - EDGE_NOISE, 0, 4 * h // 5)
    l = walk(col_white, EDGE_NOISE, w, w // 5)
    r = walk(col_white, w - 1 - EDGE_NOISE, 0, 4 * w // 5)

    # A litho border is symmetric by design, so take the wider reading on each
    # axis. That also rescues an edge whose reading was killed by scanner noise.
    ix = max(l, w - 1 - r)
    iy = max(t, h - 1 - b)
    return ix, iy, w - 1 - ix, h - 1 - iy


def cover_box(aw, ah, target_aspect, bias):
    """Crop box (in source px) that makes the art exactly target_aspect, cropping
    only the long dimension. Returns (left, top, right, bottom) and inches lost."""
    art_aspect = aw / ah
    if art_aspect < target_aspect:            # art is too tall: trim height
        keep_h = round(aw / target_aspect)
        excess = ah - keep_h
        top = round(excess * bias)
        return (0, top, aw, top + keep_h), excess / ah
    keep_w = round(ah * target_aspect)         # art is too wide: trim width
    excess = aw - keep_w
    left = round(excess * bias)
    return (left, 0, left + keep_w, ah), excess / aw


def build(source, outdir, bias, dpi):
    im = Image.open(source).convert("RGB")
    sw, sh = im.size
    if (sw, sh) != (2000, 3000):
        print(f"  WARNING {os.path.basename(source)} is {sw}x{sh}, not 2000x3000")
    l, t, r, b = find_litho_border(im)
    art = im.crop((l, t, r + 1, b + 1))
    aw, ah = art.size
    box, lost = cover_box(aw, ah, SHEET_W_IN / SHEET_H_IN, bias)
    art = art.crop(box)
    px_w, px_h = int(SHEET_W_IN * dpi), int(SHEET_H_IN * dpi)
    os.makedirs(outdir, exist_ok=True)
    pdf = os.path.join(outdir, "poster.pdf")
    art.resize((px_w, px_h), Image.LANCZOS).save(pdf, "PDF", resolution=dpi, quality=95)
    prev = art.copy()
    prev.thumbnail((PREVIEW_H, PREVIEW_H), Image.LANCZOS)
    prev.save(os.path.join(outdir, "poster.jpg"), quality=88)
    print(f"  {os.path.basename(outdir):<28} trim {l},{t}  artwork {aw}x{ah} ({aw/ah:.4f})"
          f"  bias {bias}  crop {lost*SHEET_H_IN:.2f}in  {aw/SHEET_W_IN:.0f} ppi")
    return lost


def run_manifest(path, outroot, dpi):
    import json
    cfg = json.load(open(path))
    root = os.path.dirname(os.path.abspath(path))
    for f in cfg["films"]:
        src = os.path.join(root, f["dir"], f["source"])
        build(src, os.path.join(outroot, f["slug"]), f.get("bias", 0.5), dpi)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", nargs="?")
    ap.add_argument("outdir", nargs="?")
    ap.add_argument("--manifest", help="posters.json: rebuild every film")
    ap.add_argument("--outroot", default=".", help="where --manifest writes <slug>/poster.pdf")
    ap.add_argument("--bias", type=float, default=0.5)
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--no-trim", action="store_true")
    a = ap.parse_args()

    if a.manifest:
        return run_manifest(a.manifest, a.outroot, a.dpi)

    im = Image.open(a.source).convert("RGB")
    sw, sh = im.size

    if a.no_trim:
        l, t, r, b = 0, 0, sw - 1, sh - 1
    else:
        l, t, r, b = find_litho_border(im)
    art = im.crop((l, t, r + 1, b + 1))
    aw, ah = art.size

    box, lost = cover_box(aw, ah, SHEET_W_IN / SHEET_H_IN, a.bias)
    art = art.crop(box)

    px_w, px_h = int(SHEET_W_IN * a.dpi), int(SHEET_H_IN * a.dpi)
    sheet = art.resize((px_w, px_h), Image.LANCZOS)

    os.makedirs(a.outdir, exist_ok=True)
    pdf = os.path.join(a.outdir, "poster.pdf")
    sheet.save(pdf, "PDF", resolution=a.dpi, quality=95)

    prev = art.copy()
    prev.thumbnail((PREVIEW_H, PREVIEW_H), Image.LANCZOS)
    prev.save(os.path.join(a.outdir, "poster.jpg"), quality=88)

    ppi_in = aw / SHEET_W_IN
    print(
        f"{os.path.basename(a.outdir):<28} scan {sw}x{sh}"
        f"  litho trim L{l} T{t} R{sw-1-r} B{sh-1-b}"
        f"  artwork {aw}x{ah} ({aw/ah:.4f})"
        f"  cover crop {lost*100:.1f}% ({lost*SHEET_H_IN:.2f}in)"
        f"  {ppi_in:.0f} ppi  -> {pdf}"
    )


if __name__ == "__main__":
    sys.exit(main())
