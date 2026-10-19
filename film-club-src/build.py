#!/usr/bin/env python3
"""Build the static edition of the club into dist/ for Cloudflare Pages (or any file host).

Mirrors the URL space app.py serves, as files on disk, and bundles every film's data
(including the quiz answer keys, which a static site cannot hide) into data/club.json
for static/local-club.js to grade in the browser.

    python3 build.py            # writes ./dist
    python3 build.py --out DIR
"""
import argparse, json, os, shutil
from app import ROOT, FILMS_DIR, film_slugs, jpeg_size, load_config, load_explorer, scene_path, sheet_files, sheet_source


def opt_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    out = ap.parse_args().out
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)

    # the page, with the static flag set BEFORE local-club.js loads
    with open(os.path.join(ROOT, "static", "index.html")) as f:
        html = f.read()
    marker = '<script src="/static/local-club.js"></script>'
    assert marker in html, "index.html must load /static/local-club.js"
    html = html.replace(marker, "<script>window.CLUB_STATIC = true;</script>\n" + marker)
    with open(os.path.join(out, "index.html"), "w") as f:
        f.write(html)

    shutil.copytree(os.path.join(ROOT, "static"), os.path.join(out, "static"),
                    ignore=shutil.ignore_patterns("index.html", ".DS_Store"))
    shutil.copytree(os.path.join(ROOT, "explorer"), os.path.join(out, "explorer-img"),
                    ignore=shutil.ignore_patterns(".DS_Store"))

    films = []
    for slug in film_slugs():
        base = os.path.join(FILMS_DIR, slug)
        for name, sub in (("banner.jpg", "banner"), ("poster.jpg", "poster")):
            os.makedirs(os.path.join(out, sub), exist_ok=True)
            shutil.copy(os.path.join(base, name), os.path.join(out, sub, slug + ".jpg"))
        if os.path.isdir(os.path.join(base, "cast")):
            shutil.copytree(os.path.join(base, "cast"), os.path.join(out, "cast", slug),
                            ignore=shutil.ignore_patterns(".DS_Store"))
        aspects = {}
        for n in (1, 2, 3):
            sp = scene_path(slug, n)
            if os.path.isfile(sp):
                os.makedirs(os.path.join(out, "scene", slug), exist_ok=True)
                shutil.copy(sp, os.path.join(out, "scene", slug, "%d.jpg" % n))
                w, h = jpeg_size(sp)
                aspects[str(n)] = (w / h) if h else 16 / 9
        films.append({"slug": slug,
                      "meta": opt_json(os.path.join(base, "meta.json"), {}),
                      "facts": opt_json(os.path.join(base, "facts.json"), {}),
                      "cast": opt_json(os.path.join(base, "cast.json"), []),
                      "questions": opt_json(os.path.join(base, "questions.json"), []),
                      "scene_aspect": aspects})

    # the printable sheets, from the per-film print folders listed in ../posters.json
    sheets = sheet_files()
    for f in films:
        f["sheets"] = sheets.get(f["slug"], {})
        for kind, rel in f["sheets"].items():
            dst = os.path.join(out, rel.lstrip("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy(os.path.join(os.path.dirname(ROOT), rel.lstrip("/").replace("sheets/" + f["slug"] + "/", "", 1)
                                     if False else sheet_source(f["slug"], kind)), dst)

    cfg = load_config()
    data = {"kids": [str(k) for k in cfg.get("kids", [])],
            "films": films,
            "timeline": opt_json(os.path.join(ROOT, "timeline.json"), {"people": [], "movies": {}, "tech": {}}),
            "explorer": load_explorer()}
    os.makedirs(os.path.join(out, "data"))
    with open(os.path.join(out, "data", "club.json"), "w") as f:
        json.dump(data, f, separators=(",", ":"))
    with open(os.path.join(out, "_headers"), "w") as f:
        f.write("/data/*\n  Cache-Control: no-cache\n/index.html\n  Cache-Control: no-cache\n")
    total = sum(os.path.getsize(os.path.join(d, x)) for d, _, fs in os.walk(out) for x in fs)
    print("built %s: %d films, %.1f MB" % (out, len(films), total / 1e6))


if __name__ == "__main__":
    main()
