#!/usr/bin/env python3
"""Build a Family Movie Club film study (fact sheet + worksheet) from the film's data.

    sheet-build.py <slug> [--render]

Reads film-club-src/films/<slug>/{meta,facts,cast}.json (the SAME data the hub and the
quiz fact sheet show) plus timeline.json for the time check, writes <dir>/sheet.html,
and with --render prints TWO single-page PDFs: <short>-fact-sheet.pdf (the program,
print once) and <short>-worksheet.pdf (the review, ink-light, print one per kid), plus
a two-page preview.png. Two separate sheets, not two sides: the fact sheet prints once,
the worksheet once per kid.
"""
import json, os, subprocess, sys, time, html, shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
FONTS = "../film-club-src/static"

def esc(s): return html.escape(str(s if s is not None else ""), quote=False)

def load(slug):
    man = json.load(open(os.path.join(ROOT, "posters.json")))
    film = next(f for f in man["films"] if f["slug"] == slug)
    base = os.path.join(ROOT, "film-club-src", "films", slug)
    J = lambda n, d: json.load(open(os.path.join(base, n))) if os.path.exists(os.path.join(base, n)) else d
    tl = json.load(open(os.path.join(ROOT, "film-club-src", "timeline.json")))
    return film, J("meta.json", {}), J("facts.json", {}), J("cast.json", []), tl.get("people", [])

def timecheck(year, people):
    if not people: return ""
    parts, seen = [], set()
    for p in people:
        if p["name"] in seen: continue
        twin = next((q for q in people if q is not p and q["year"] == p["year"] and q["name"] not in seen), None)
        who = p["name"] + (" and " + twin["name"] if twin else "")
        seen.add(p["name"]);
        if twin: seen.add(twin["name"])
        age = year - p["year"]
        if age < 0: parts.append("%s: not born for another %d years" % (who, -age))
        elif age == 0: parts.append("%s %s born that very year!" % (who, "were" if twin else "was"))
        else: parts.append("%s %s %d" % (who, "were" if twin else "was", age))
    return "When this movie came out, " + ". ".join(parts) + "."

STAR = '<svg class="star" viewBox="0 0 50 50"><path d="M25 4 L31 19 L47 19 L34 29 L39 45 L25 35 L11 45 L16 29 L3 19 L19 19 Z"/></svg>'

CSS = """
@font-face { font-family: 'Bungee'; src: url('%(fonts)s/bungee.woff2') format('woff2'); }
@font-face { font-family: 'Nunito'; src: url('%(fonts)s/nunito-400.woff2') format('woff2'); font-weight: 400; }
@font-face { font-family: 'Nunito'; src: url('%(fonts)s/nunito-700.woff2') format('woff2'); font-weight: 700; }
@font-face { font-family: 'Nunito'; src: url('%(fonts)s/nunito-800.woff2') format('woff2'); font-weight: 800; }
@page { size: 8.5in 11in; margin: 0; }
* { margin: 0; padding: 0; box-sizing: border-box; }
:root { --velvet: #5c1a22; --brass: #d9a900; --brass-lt: #f5c518; --cream: #fdf6e7; --ink: #2a1a14; --mut: #7a5f52; --line: #cdb48c; }
html, body { width: 8.5in; background: #888; }
body { font-family: 'Nunito', 'Avenir Next', sans-serif; color: var(--ink); -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.page { width: 8.5in; height: 11in; position: relative; overflow: hidden; background: var(--cream); display: flex; flex-direction: column; page-break-after: always; }
.page:last-child { page-break-after: auto; }
.only-front .back, .only-back .front { display: none; }
.only-front .front, .only-back .back { page-break-after: auto; }
h2 { font-family: 'Bungee', sans-serif; font-weight: 400; font-size: 10.5px; letter-spacing: .1em; text-transform: uppercase; color: var(--velvet); display: flex; align-items: center; gap: .08in; margin-bottom: .05in; }
h2::after { content: ''; flex: 1; height: 2px; background: linear-gradient(90deg, var(--brass-lt), transparent); }
p { font-size: 11.5px; line-height: 1.4; }

/* ---- front: the program ---- */
.sprocket { height: .13in; background-color: #1a0a0d;
  background-image: repeating-linear-gradient(90deg, transparent 0, transparent .11in, var(--cream) .11in, var(--cream) .20in, transparent .20in, transparent .31in);
  background-size: .31in .07in; background-position: .045in center; background-repeat: repeat-x; }
.banner { position: relative; height: 2.05in; overflow: hidden; background: #0d0609; }
.banner img { width: 100%%; height: 100%%; object-fit: cover; object-position: 50%% 45%%; }
.banner .scrim { position: absolute; inset: 0; background: linear-gradient(180deg, rgba(10,4,7,.55) 0%%, rgba(10,4,7,.15) 38%%, transparent 55%%); }
.banner .ttl { position: absolute; top: .22in; left: .3in; right: .3in; text-align: center; }
.banner .ttl.pos-right { left: 42%%; text-align: right; }
.banner .ttl.pos-left { right: 42%%; text-align: left; }
.banner .yr { font-family: 'Nunito'; font-weight: 800; font-size: 11px; letter-spacing: .24em; color: var(--brass-lt); text-shadow: 0 1px 0 #000; -webkit-text-stroke: .6px rgba(0,0,0,.8); paint-order: stroke fill; }
.banner h1 { font-family: 'Bungee', sans-serif; font-weight: 400; font-size: %(titlesize)spx; line-height: 1.02; color: #fff8e6; margin-top: 2px;
  /* NO blurred text-shadow here: Quartz (sips, Preview and CUPS) renders Chrome's blurred
     text-shadow as a black box behind the line. A hard shadow, a stroke and a drop-shadow
     filter all print clean (tested 2026-09-02). */
  text-shadow: 0 3px 0 rgba(58,26,0,.95); -webkit-text-stroke: 1.2px rgba(20,8,10,.85); paint-order: stroke fill;
  filter: drop-shadow(0 6px 12px rgba(0,0,0,.65)); }
.body { flex: 1; padding: .12in .42in .08in; display: flex; flex-direction: column; gap: .11in; }
.row { display: flex; gap: .22in; }
.facts { flex: 0 0 3.15in; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: .045in .15in; }
.f { font-size: 11px; line-height: 1.22; font-weight: 700; }
.f b { display: block; font-size: 7.5px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; color: var(--velvet); margin-bottom: 1px; }
.story { flex: 1; }
.quote { margin-top: .07in; font-style: italic; font-weight: 700; font-size: 11.5px; color: var(--velvet); }
.quote span { font-style: normal; font-weight: 800; font-size: 8.5px; letter-spacing: .1em; text-transform: uppercase; color: var(--mut); margin-left: .06in; }
.castrow { display: flex; gap: .16in; justify-content: space-between; }
.card { flex: 1; text-align: center; }
.card img { width: 100%%; aspect-ratio: 1 / 1; object-fit: cover; object-position: 50%% 22%%; border-radius: .09in; border: 2px solid var(--velvet); display: block; }
.card .cap { font-size: 9px; line-height: 1.2; margin-top: 3px; color: var(--mut); }
.card .cap b { display: block; font-size: 10px; color: var(--ink); }
.scenes .row { gap: .14in; }
.scenes figure { flex: 1; }
.scenes img { width: 100%%; aspect-ratio: 16 / 9; object-fit: cover; border-radius: .07in; border: 2px solid var(--velvet); display: block; }
.scenes figcaption { font-size: 9.5px; line-height: 1.3; margin-top: 3px; display: flex; gap: 4px; }
.scenes figcaption b { flex: none; width: 14px; height: 14px; border-radius: 50%%; background: var(--velvet); color: #fff; font-family: 'Bungee'; font-weight: 400; font-size: 8px; display: inline-flex; align-items: center; justify-content: center; margin-top: 1px; }
.numbers { flex: 0 0 2.5in; display: flex; flex-direction: column; }
.numbers .list { display: flex; flex-direction: column; justify-content: space-between; flex: 1; gap: .04in; }
.num { display: flex; align-items: baseline; gap: .1in; }
.num b { font-family: 'Bungee', sans-serif; font-weight: 400; font-size: 21px; color: var(--velvet); white-space: nowrap; line-height: 1; }
.num span { font-size: 9.5px; line-height: 1.25; color: var(--mut); font-weight: 700; }
.wow { flex: 1; background: #fff3d8; border: 2px solid var(--brass-lt); border-radius: .12in; padding: .09in .13in .08in; }
.wow h2 { margin-bottom: .03in; }
.wow ul { list-style: none; }
.wow li { position: relative; padding-left: .17in; font-size: 10px; line-height: 1.32; margin-bottom: .035in; }
.wow li::before { content: ''; position: absolute; left: 0; top: 3px; width: 9px; height: 9px; background: var(--brass);
  clip-path: polygon(50%% 0, 61%% 35%%, 98%% 35%%, 68%% 57%%, 79%% 91%%, 50%% 70%%, 21%% 91%%, 32%% 57%%, 2%% 35%%, 39%% 35%%); }
.timecheck { border-top: 2px solid var(--velvet); padding-top: .05in; font-size: 10px; line-height: 1.3; color: var(--ink); font-weight: 700; display: flex; gap: .1in; align-items: baseline; }
.timecheck b { font-family: 'Bungee'; font-weight: 400; font-size: 9px; letter-spacing: .08em; color: var(--velvet); white-space: nowrap; }
.footer { background: #1a0a0d; color: #f0d9a8; text-align: center; font-weight: 800; letter-spacing: .16em; text-transform: uppercase; font-size: 9px; padding: .075in 0; }
.footer .cq { color: var(--brass-lt); }

/* ---- back: the review ---- */
.back .head { background: var(--velvet); color: var(--cream); padding: .12in .42in .1in; display: flex; align-items: baseline; gap: .2in; border-bottom: .06in solid var(--brass-lt); }
.back .head h1 { font-family: 'Bungee', sans-serif; font-weight: 400; font-size: 26px; color: #fff8e6; }
.back .head .of { font-weight: 800; font-size: 12px; color: var(--brass-lt); letter-spacing: .04em; }
.back .head .club { margin-left: auto; font-size: 8.5px; letter-spacing: .2em; text-transform: uppercase; font-weight: 800; color: #f0d9a8; }
.back .body { gap: .1in; padding-top: .14in; }
.prompt { font-weight: 800; font-size: 12.5px; line-height: 1.35; }
.line { border-bottom: 1.5px solid var(--line); height: .31in; }
.namerow { display: flex; gap: .15in; align-items: baseline; }
.namerow .prompt { flex: none; }
.namerow .fill { flex: 1; border-bottom: 1.5px solid var(--line); }
.namerow .fill.short { flex: 0 0 1.4in; }
.rating { display: flex; align-items: center; gap: .1in; }
.rating .stars { display: flex; gap: .09in; }
.star { width: .32in; height: .32in; }
.star path { fill: none; stroke: var(--velvet); stroke-width: 3.5; stroke-linejoin: round; }
.rating .key { font-size: 9px; color: var(--mut); font-weight: 700; margin-left: .05in; }
.faces { display: flex; justify-content: space-between; gap: .1in; margin: .02in 0 .06in; }
.face { flex: 1; text-align: center; }
.face img { width: .82in; height: .82in; object-fit: cover; object-position: 50%% 22%%; border-radius: 50%%; border: 2.5px solid var(--velvet); display: block; margin: 0 auto; }
.face span { display: block; font-weight: 800; font-size: 10px; margin-top: 3px; }
.q { display: flex; flex-direction: column; }
.q .prompt { display: flex; gap: .1in; }
.q .n { flex: none; width: .28in; height: .28in; border-radius: 50%%; background: var(--velvet); color: #fff8e6; font-family: 'Bungee'; font-weight: 400; font-size: 12px; display: inline-flex; align-items: center; justify-content: center; }
.draw { flex: 1; display: flex; flex-direction: column; }
.draw .box { flex: 1; border: 2px dashed var(--line); border-radius: .12in; min-height: 1.3in; }
""" 

def build(slug, render=False):
    film, meta, facts, cast, people = load(slug)
    d = os.path.join(ROOT, film["dir"])
    year = meta.get("year") or ""
    pos = " pos-" + meta["title_pos"] if meta.get("title_pos") else ""
    title = meta.get("title", slug)
    tsize = 44 if len(title) <= 18 else 36 if len(title) <= 26 else 30
    pairs = facts.get("pairs") or [[k, facts[j]] for k, j in [("Year it came out","year"),("How long it is","runtime"),("Directed by","director"),("Presented by","presented"),("It won an Oscar for","oscar"),("Rated","rated")] if facts.get(j)]
    scenes = facts.get("scenes") or []
    numbers = facts.get("numbers") or []
    trivia = facts.get("trivia") or []
    qs = facts.get("questions") or []
    catch = facts.get("catchphrase") or facts.get("quote") or ""
    front = f"""
<div class="page front">
  <div class="sprocket"></div>
  <div class="banner"><img src="banner.jpg"><div class="scrim"></div>
    <div class="ttl{pos}"><div class="yr">{esc(year)}</div><h1>{esc(title)}</h1></div></div>
  <div class="sprocket"></div>
  <div class="body">
    <div class="row">
      <div class="facts"><h2>The facts</h2><div class="grid">{''.join(f'<div class="f"><b>{esc(a)}</b>{esc(b)}</div>' for a, b in pairs)}</div></div>
      <div class="story"><h2>The story</h2><p>{esc(facts.get("story",""))}</p>
        {f'<div class="quote">&ldquo;{esc(facts["quote"])}&rdquo;<span>{esc(facts.get("quote_by",""))}</span></div>' if facts.get("quote") else ''}</div>
    </div>
    <div class="cast"><h2>Starring</h2><div class="castrow">{''.join(f'<div class="card"><img src="{esc(m["img"])}"><div class="cap"><b>{esc(m["actor"])}</b>as {esc(m["character"])}</div></div>' for m in cast[:4])}</div></div>
    <div class="scenes"><h2>Spot it while you watch</h2><div class="row">{''.join(f'<figure><img src="scene{i+1}.jpg"><figcaption><b>{i+1}</b><span>{esc(c)}</span></figcaption></figure>' for i, c in enumerate(scenes[:3]))}</div></div>
    <div class="row">
      <div class="numbers"><h2>By the numbers</h2><div class="list">{''.join(f'<div class="num"><b>{esc(a)}</b><span>{esc(b)}</span></div>' for a, b in numbers[:3])}</div></div>
      <div class="wow"><h2>{esc(facts.get("trivia_title","Did you know..."))}</h2><ul>{''.join(f'<li>{esc(t)}</li>' for t in trivia[:4])}</ul></div>
    </div>
    {('<div class="timecheck"><b>Time check</b><span>' + esc(timecheck(int(year), people)) + '</span></div>') if (year and people) else ''}
  </div>
  <div class="footer">Family Movie Club &nbsp;&bull;&nbsp; <span class="cq">&ldquo;{esc(catch)}&rdquo;</span></div>
</div>"""
    back = f"""
<div class="page back">
  <div class="head"><h1>My Review</h1><div class="of">of {esc(title)}</div><div class="club">Family Movie Club</div></div>
  <div class="body">
    <div class="namerow"><span class="prompt">My name</span><span class="fill"></span><span class="prompt">Date watched</span><span class="fill short"></span></div>
    <div class="rating"><span class="prompt">My rating</span><div class="stars">{STAR*5}</div><span class="key">Color in the stars. 1 = never again, 5 = all-time favorite</span></div>
    <div class="fav"><h2>Circle your favorite character</h2>
      <div class="faces">{''.join(f'<div class="face"><img src="{esc(m["img"])}"><span>{esc(m["actor"] if m["character"].lower() in ("himself","herself","themselves") else m["character"])}</span></div>' for m in cast[:4])}</div>
      <div class="prompt">Why? What makes them your favorite?</div><div class="line"></div><div class="line"></div></div>
    {''.join(f'<div class="q"><div class="prompt"><span class="n">{i+1}</span><span>{esc(q)}</span></div><div class="line"></div><div class="line"></div><div class="line"></div></div>' for i, q in enumerate(qs[:3]))}
    <div class="draw"><h2>Draw your favorite scene</h2><div class="box"></div></div>
  </div>
  <div class="footer">Family Movie Club &nbsp;&bull;&nbsp; <span class="cq">&ldquo;{esc(catch)}&rdquo;</span></div>
</div>"""
    switch = "<script>var q=location.search;if(q.indexOf('only=front')>=0)document.documentElement.classList.add('only-front');if(q.indexOf('only=back')>=0)document.documentElement.classList.add('only-back');</script>"
    page = "<!doctype html>\n<html><head><meta charset=\"utf-8\"><title>%s</title><style>%s</style>%s</head><body>%s%s</body></html>" % (
        esc(title), CSS % {"fonts": FONTS, "titlesize": tsize}, switch, front, back)
    out = os.path.join(d, "sheet.html")
    open(out, "w").write(page)
    print("wrote", out)
    if render:
        short = film.get("short", slug)
        old = os.path.join(d, short + "-film-study.pdf")
        if os.path.exists(old): os.remove(old)      # the two-sided combined PDF is retired
        for name, only in (("fact-sheet", "front"), ("worksheet", "back")):
            pdf = os.path.join(d, short + "-" + name + ".pdf")
            chrome(["--print-to-pdf=" + pdf, "--no-pdf-header-footer"], out + "?only=" + only, pdf)
            n = pdf_pages(pdf)
            print("pdf", pdf, "pages:", n, "" if n == 1 else "  <-- NOT 1, something overflowed")
        png = os.path.join(d, "preview.png")
        chrome(["--screenshot=" + png, "--window-size=816,2112", "--hide-scrollbars"], out, png)

def pdf_pages(pdf):
    import re
    try:
        return len(re.findall(rb"/Type\s*/Page[^s]", open(pdf, "rb").read()))
    except OSError:
        return 0


def chrome(args, src, expect):
    """headless Chrome writes its file and then never exits here: wait for the file, then kill it."""
    if os.path.exists(expect): os.remove(expect)
    ud = "/tmp/fs-chrome-%d" % os.getpid()
    p = subprocess.Popen([CHROME, "--headless", "--disable-gpu", "--no-first-run", "--user-data-dir=" + ud] + args + ["file://" + src],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(240):
        if os.path.exists(expect) and os.path.getsize(expect) > 0: break
        time.sleep(0.25)
    time.sleep(0.4)
    subprocess.run(["pkill", "-9", "-f", "user-data-dir=" + ud])
    shutil.rmtree(ud, ignore_errors=True)

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a: sys.exit(__doc__)
    build(a[0], "--render" in a)
