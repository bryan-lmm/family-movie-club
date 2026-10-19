# Family Movie Club

A homeschool movie club for kids, in three parts that share one set of data per film:

1. **The hub** (`film-club-src/`): a tablet-first web app. Film pages with facts and cast,
   a ten-question quiz in seven formats (multiple choice, fill the blank, who said it,
   true/false swipe, put it in order, number dial, tap the scene), a poster vault that
   unlocks when a kid scores 8 of 10, a time machine timeline, a "coming attractions"
   board the kids vote on, per-kid stickers.
2. **The fact sheet and the worksheet** (`sheet-build.py`, one `film-*/` folder per film):
   two letter-size pages per film. The art-heavy fact sheet prints once; the ink-light
   worksheet (stars, circle your favorite character, three questions, a drawing box)
   prints once per kid.
3. **The poster wall** (`poster-compose.py`, `POSTER.md`): a borderless 13x19 theatrical
   poster per film, staged in the hub and printed when the quiz is beaten.

Five films are in the box: Back to the Future, E.T., Jurassic Park, The Goonies and
The Princess Bride. Seventeen more sit on the coming-attractions board.

## Run it

**Static (Cloudflare Pages, GitHub Pages, any file server).** No backend. The quiz is
graded in the browser by `film-club-src/static/local-club.js` and progress lives in
that device's localStorage. The answer keys ship to the browser in `data/club.json`,
so this edition is for fun, not for keeping secrets from a determined ten-year-old.

```bash
python3 film-club-src/build.py            # writes film-club-src/dist
python3 -m http.server 8899 -d film-club-src/dist
```

Deploy the `dist` folder wherever you like. The live copy is at
https://family-movie-club.pages.dev. For your own Cloudflare Pages project (current
wrangler routes `pages` commands to Workers unless you pass `--force` on the first create):

```bash
npx wrangler@latest pages project create <name> --production-branch=main --force
npx wrangler@latest pages deploy film-club-src/dist --project-name=<name> --branch=main
```

**Self-hosted (a computer at home, with a printer).** `app.py` is a stdlib-only Python
server. It grades the quiz server-side, keeps the answer keys off the wire, enforces a
ten-minute cooldown after a failed quiz, keeps state in `state/`, and prints the poster
through CUPS when a film is unlocked.

```bash
cd film-club-src && python3 app.py         # http://localhost:8891
```

`config.json`: `kids` (the names on the who-is-playing picker), `parent_code` (needed to
reprint a poster; change it), `printer` (the CUPS queue name), `printing_enabled`,
`dry_run` (log instead of print), `port`.

## Add a film

1. Make `film-club-src/films/<slug>/` with `meta.json` (title, film_no, year, tagline,
   `title_pos` for where the title sits in the banner sky), `facts.json` (pairs, story,
   quote, trivia x4, numbers x3, scenes x3, questions x3, catchphrase), `cast.json` (four
   entries: actor, character, img, character_desc, actor_facts x3) and `questions.json`
   (ten questions; `quiz-check.py` validates them, and every one of the seven types is
   documented at the top of `app.py`).
2. Art: `banner.jpg` (21:9, textless, open sky where the title goes), `poster.jpg`
   (616x900 preview), `cast/*.jpg` (square crops), `scenes/scene1..3.jpg` (16:9 stills).
3. Poster: a 2000x3000 borderless source, then `poster-compose.py` (see `POSTER.md`).
4. Sheets: add the film to `posters.json` and run `python3 sheet-build.py <slug> --render`
   (needs Google Chrome for the PDF render). Preview `preview.png` before printing.
5. Rebuild the static edition (`build.py`) or restart `app.py`.

Every printed fact should be checkable on Wikipedia. If it cannot be verified, drop it.

## Test

`webkit-walk.mjs` drives the whole hub in real WebKit as an iPad with touch: every
question type, the fact-sheet drawer, a vote, the time machine, the offline screen.
Instructions are at the top of the file. It passes against both the static build and
the Python server.

## Layout

```
film-club-src/        the hub: app.py, build.py, static/, films/<slug>/ (data, art, poster.pdf), explorer/, timeline.json
film-*/               per-film print folders: banner, cast stills, scene stills, poster source,
                      sheet.html, <short>-fact-sheet.pdf, <short>-worksheet.pdf, poster-13x19.pdf (borderless compose)
sheet-build.py        fact sheet + worksheet builder (data in, two PDFs out)
poster-compose.py     13x19 borderless poster composer (Pillow)
posters.json          per-film poster source and crop bias
quiz-check.py         validates every questions.json
webkit-walk.mjs       the Playwright WebKit acceptance walk
POSTER.md             the poster pipeline and its hard rules
```

Film stills, cast photos and poster art belong to their studios and are here for a
family's own movie nights. Fonts are Bungee and Nunito (OFL). Room, banner and
coming-attractions illustrations are generated art.
