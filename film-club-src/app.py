#!/usr/bin/env python3
"""Family Movie Club - poster unlock quiz game (self-hosted server).

Stdlib only. Serves the title screen + per-film quiz, grades server-side,
enforces a server-side fail cooldown, and prints the pre-staged 13x19 poster
on the CUPS printer named in config.json when a film is unlocked.

Layout:
  app.py
  config.json                {"port":8891,"printing_enabled":false,"dry_run":false,"parent_code":"...",
                              "printer":"<CUPS queue>","kids":["..."]}
  films/<slug>/meta.json     {"title":..,"film_no":..,"year":..,"tagline":..}
  films/<slug>/questions.json[{"q":..,"options":[..],"answer":0,"explain":..}, ...]  answer = index into options
  films/<slug>/poster.pdf    print-ready 13x19
  films/<slug>/poster.jpg    thumbnail art
  state/<slug>.json          {"cooldown_until":0,"unlocked":false,"printed":false,...}
"""
import json, math, os, random, struct, subprocess, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
FILMS_DIR = os.path.join(ROOT, "films")
STATE_DIR = os.path.join(ROOT, "state")
PASS_SCORE = 8
COOLDOWN_SECONDS = 600
# Borderless. The poster PDFs are composed to cover the full 13x19 sheet, so the
# media MUST be the .Fullbleed variant: on plain "13x19" the driver keeps a
# ~0.14in dead zone and the art comes back with a white edge. print-scaling=none
# because the PDF is already exact media size. These options are for an Epson ET-8550;
# adjust for your printer (lpoptions -p <queue> -l lists what it accepts).
PRINT_OPTS = ["-o", "media=13x19.Fullbleed", "-o", "InputSlot=rear",
             "-o", "MediaType=photographic-matte", "-o", "cupsPrintQuality=High",
             "-o", "ColorModel=RGB", "-o", "print-scaling=none"]

_lock = threading.Lock()
_sessions = {}  # sid -> {"slug","order","next_i","correct","done"}


def load_config():
    with open(os.path.join(ROOT, "config.json")) as f:
        return json.load(f)


def kids(cfg=None):
    """The crew who can play: names only, from config.json. Scores are kept per kid."""
    cfg = cfg or load_config()
    return [str(k) for k in cfg.get("kids", [])]


VOTES_PATH = os.path.join(STATE_DIR, "votes.json")


def load_votes():
    try:
        with open(VOTES_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_votes(v):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = VOTES_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(v, f, indent=1)
    os.replace(tmp, VOTES_PATH)


POSTERS_JSON = os.path.join(os.path.dirname(ROOT), "posters.json")


def sheet_source(slug, kind):
    """Path on disk of a film's printable PDF: kind is "fact" or "worksheet". None if absent."""
    try:
        with open(POSTERS_JSON) as f:
            entries = json.load(f).get("films", [])
    except (OSError, ValueError):
        return None
    for e in entries:
        if e.get("slug") == slug:
            name = e.get("short", slug) + ("-fact-sheet.pdf" if kind == "fact" else "-worksheet.pdf")
            path = os.path.join(os.path.dirname(ROOT), e.get("dir", ""), name)
            return path if os.path.isfile(path) else None
    return None


def sheet_files():
    """{slug: {"fact": "/sheets/<slug>/<short>-fact-sheet.pdf", "worksheet": ...}} for every film with PDFs."""
    out = {}
    for slug in film_slugs():
        d = {}
        for kind in ("fact", "worksheet"):
            src = sheet_source(slug, kind)
            if src:
                d[kind] = "/sheets/%s/%s" % (slug, os.path.basename(src))
        if d:
            out[slug] = d
    return out


def load_explorer():
    try:
        with open(os.path.join(ROOT, "explorer.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


# ---- question types ----
# mc / blank / who : "options" + "answer" (index). who lists the four cast characters.
# tf               : "answer" true/false
# order            : "items" in the CORRECT order (the client gets them shuffled)
# number           : "answer" + "min" "max" "step" "unit" "tolerance"
# spot             : "scene" (1..3, films/<slug>/scenes/scene<n>.jpg) + "targets" [[cx, cy, r], ...]
#                    normalized to the image WIDTH (r too), any target counts
OPTION_TYPES = ("mc", "blank", "who")


def q_type(q):
    return q.get("type", "mc")


_img_dims = {}


def jpeg_size(path):
    """(w, h) of a JPEG from its SOF marker, stdlib only; cached."""
    if path in _img_dims:
        return _img_dims[path]
    w = h = 0
    try:
        with open(path, "rb") as f:
            data = f.read()
        i = 2
        while i < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                break
            i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    except (OSError, struct.error):
        pass
    _img_dims[path] = (w, h)
    return w, h


def scene_path(slug, n):
    return os.path.join(FILMS_DIR, slug, "scenes", "scene%d.jpg" % int(n))


def film_slugs():
    return sorted(d for d in os.listdir(FILMS_DIR)
                  if os.path.isfile(os.path.join(FILMS_DIR, d, "meta.json")))


def load_film(slug):
    base = os.path.join(FILMS_DIR, slug)
    with open(os.path.join(base, "meta.json")) as f:
        meta = json.load(f)
    with open(os.path.join(base, "questions.json")) as f:
        questions = json.load(f)
    return meta, questions


def state_path(slug):
    return os.path.join(STATE_DIR, slug + ".json")


def load_state(slug):
    try:
        with open(state_path(slug)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"cooldown_until": 0, "unlocked": False, "printed": False,
                "printed_at": None, "attempts": 0, "best_score": 0}


def save_state(slug, st):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = state_path(slug) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, state_path(slug))


def do_print(slug, cfg):
    pdf = os.path.join(FILMS_DIR, slug, "poster.pdf")
    if cfg.get("dry_run"):
        return "DRY RUN (no job sent)"
    printer = str(cfg.get("printer") or "")
    if not printer:
        raise RuntimeError("no printer named in config.json")
    out = subprocess.run(["lp", "-d", printer] + PRINT_OPTS + [pdf], capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or "lp failed")
    return out.stdout.strip()


def grade(q, shuffle, body, slug):
    """Returns (correct, reveal). Raises on a malformed body; the caller turns that into a 400.
    The reveal is in SHUFFLED space (indices the client is holding), never the key itself."""
    t = q_type(q)
    if t in OPTION_TYPES:
        choice = int(body["choice"])
        if not 0 <= choice < len(shuffle):
            raise ValueError("choice out of range")
        correct = shuffle[choice] == q["answer"]
        return correct, {"correct_index": shuffle.index(q["answer"]), "correct_text": q["options"][q["answer"]]}
    if t == "tf":
        value = body["value"]
        if not isinstance(value, bool):
            raise ValueError("value must be true or false")
        return value == bool(q["answer"]), {"answer": bool(q["answer"])}
    if t == "order":
        order = body["order"]
        n = len(q["items"])
        if not (isinstance(order, list) and len(order) == n and sorted(int(k) for k in order) == list(range(n))):
            raise ValueError("order must list every item once")
        chosen = [shuffle[int(k)] for k in order]
        correct_order = [shuffle.index(k) for k in range(n)]
        return chosen == list(range(n)), {"correct_order": correct_order}
    if t == "number":
        value = float(body["value"])
        ans = float(q["answer"])
        return abs(value - ans) <= float(q.get("tolerance", 0)) + 1e-9, {"answer": q["answer"]}
    if t == "spot":
        x, y = float(body["x"]), float(body["y"])
        if not (0 <= x <= 1 and 0 <= y <= 1):
            raise ValueError("tap outside the picture")
        w, h = jpeg_size(scene_path(slug, q.get("scene", 1)))
        aspect = (w / h) if h else 16 / 9
        hit = False
        for cx, cy, r in q["targets"]:
            # r is a fraction of the WIDTH; y runs over the HEIGHT, so scale dy into width units
            if math.hypot(x - cx, (y - cy) / aspect) <= r:
                hit = True
        return hit, {"targets": q["targets"]}
    raise ValueError("unknown question type")


class Handler(BaseHTTPRequestHandler):
    server_version = "FilmClub/1.0"

    def log_message(self, fmt, *args):
        pass

    # ---- helpers ----
    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, ctype):
        try:
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 65536:
            raise ValueError("body too large")
        return json.loads(self.rfile.read(n) or b"{}")

    # ---- routes ----
    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/" or p == "/index.html":
            return self.send_file(os.path.join(ROOT, "static", "index.html"), "text/html; charset=utf-8")
        if p.startswith("/static/"):
            name = os.path.basename(p)
            ctypes = {".html": "text/html; charset=utf-8", ".json": "application/manifest+json",
                      ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                      ".svg": "image/svg+xml", ".js": "text/javascript", ".css": "text/css",
                      ".woff2": "font/woff2"}
            ext = os.path.splitext(name)[1].lower()
            if ext in ctypes:
                return self.send_file(os.path.join(ROOT, "static", name), ctypes[ext])
            return self.send_error(404)
        if p == "/api/films":
            out = []
            for slug in film_slugs():
                meta, questions = load_film(slug)
                st = load_state(slug)
                out.append({"slug": slug, "title": meta["title"], "film_no": meta["film_no"],
                            "year": meta.get("year"), "tagline": meta.get("tagline", ""),
                            "title_pos": meta.get("title_pos"),
                            "question_count": len(questions),
                            "unlocked": st["unlocked"], "printed": st["printed"],
                            "kids": st.get("kids", {})})
            return self.send_json({"films": out, "pass_score": PASS_SCORE, "kids": kids()})
        if p == "/api/timeline":
            try:
                with open(os.path.join(ROOT, "timeline.json")) as f:
                    return self.send_json(json.load(f))
            except (OSError, ValueError):
                return self.send_json({"people": [], "movies": {}, "tech": {}})
        if p == "/api/explorer":
            return self.send_json({"ideas": load_explorer(), "votes": load_votes(), "kids": kids()})
        if p.startswith("/api/film/"):
            slug = os.path.basename(p[len("/api/film/"):])
            if slug not in film_slugs():
                return self.send_error(404)
            meta, questions = load_film(slug)
            st = load_state(slug)
            base = os.path.join(FILMS_DIR, slug)
            def opt_json(name, default):
                try:
                    with open(os.path.join(base, name)) as f:
                        return json.load(f)
                except (OSError, ValueError):
                    return default
            return self.send_json({"slug": slug, "meta": meta,
                                   "sheets": sheet_files().get(slug, {}),
                                   "facts": opt_json("facts.json", {}),
                                   "cast": opt_json("cast.json", []),
                                   "question_count": len(questions),
                                   "unlocked": st["unlocked"], "printed": st["printed"],
                                   "best_score": st.get("best_score", 0),
                                   "attempts": st.get("attempts", 0),
                                   "kids": st.get("kids", {})})
        if p.startswith("/cast/"):
            parts = [x for x in p.split("/") if x]
            if len(parts) == 3 and parts[1] in film_slugs():
                name = os.path.basename(parts[2])
                if name.endswith((".jpg", ".jpeg", ".png")):
                    ct = "image/png" if name.endswith(".png") else "image/jpeg"
                    return self.send_file(os.path.join(FILMS_DIR, parts[1], "cast", name), ct)
            return self.send_error(404)
        if p.startswith("/explorer-img/"):
            name = os.path.basename(p)
            if name.endswith((".jpg", ".jpeg", ".png")):
                ct = "image/png" if name.endswith(".png") else "image/jpeg"
                return self.send_file(os.path.join(ROOT, "explorer", name), ct)
            return self.send_error(404)
        if p.startswith("/scene/"):
            # scene stills for spot-it questions and the fact sheet: not the poster, safe when locked
            parts = [x for x in p.split("/") if x]
            if len(parts) == 3 and parts[1] in film_slugs() and parts[2][:-4].isdigit() and parts[2].endswith(".jpg"):
                return self.send_file(scene_path(parts[1], int(parts[2][:-4])), "image/jpeg")
            return self.send_error(404)
        if p.startswith("/sheets/"):
            # the printable fact sheet and worksheet PDFs, from the per-film print folders
            parts = [x for x in p.split("/") if x]
            if len(parts) == 3 and parts[1] in film_slugs():
                for kind in ("fact", "worksheet"):
                    src = sheet_source(parts[1], kind)
                    if src and os.path.basename(src) == os.path.basename(parts[2]):
                        return self.send_file(src, "application/pdf")
            return self.send_error(404)
        if p.startswith("/banner/"):
            # the worksheet banner art (not the poster): safe to show for every film, locked or not
            slug = os.path.basename(p[len("/banner/"):])
            if slug in film_slugs():
                return self.send_file(os.path.join(FILMS_DIR, slug, "banner.jpg"), "image/jpeg")
            return self.send_error(404)
        if p.startswith("/poster/"):
            slug = os.path.basename(p[len("/poster/"):])
            if slug in film_slugs():
                # the art is the prize: locked films do not serve it at all, even by direct URL
                if not load_state(slug)["unlocked"]:
                    return self.send_error(403)
                return self.send_file(os.path.join(FILMS_DIR, slug, "poster.jpg"), "image/jpeg")
            return self.send_error(404)
        return self.send_error(404)

    def do_POST(self):
        try:
            p = self.path.split("?")[0]
            body = self.read_body()
            if p == "/api/vote":
                return self.api_vote(body)
            slug = os.path.basename(str(body.get("slug", "")))
            if slug not in film_slugs():
                return self.send_json({"error": "unknown film"}, 400)
            if p == "/api/start":
                return self.api_start(slug, body)
            if p == "/api/answer":
                return self.api_answer(body)
            if p == "/api/hint":
                return self.api_hint(body)
            if p == "/api/print":
                return self.api_print(slug, body)
            return self.send_error(404)
        except Exception as e:
            return self.send_json({"error": str(e)}, 500)

    def api_start(self, slug, body):
        who = str(body.get("who", ""))[:24]
        if who not in kids():
            who = ""
        with _lock:
            st = load_state(slug)
            remaining = int(st["cooldown_until"] - time.time())
            if remaining > 0:
                return self.send_json({"cooldown": remaining})
            meta, questions = load_film(slug)
            # fixed order is for the dev harness only: honored only when the server is a dry run
            fixed = bool(body.get("fixed")) and bool(load_config().get("dry_run"))
            order = list(range(len(questions)))
            if not fixed:
                random.shuffle(order)
            sid = uuid.uuid4().hex
            _sessions[sid] = {"slug": slug, "order": order, "next_i": 0, "correct": 0,
                              "done": False, "shuffles": {}, "who": who, "hint_used": False,
                              "streak": 0, "max_streak": 0}
            # prune stale sessions
            if len(_sessions) > 200:
                for k in list(_sessions)[:100]:
                    _sessions.pop(k, None)
            payload = []
            for qi in order:
                q = questions[qi]
                t = q_type(q)
                item = {"qid": qi, "type": t, "q": q["q"]}
                if t in OPTION_TYPES:
                    opts = list(range(len(q["options"])))
                    if not fixed:
                        random.shuffle(opts)
                    _sessions[sid]["shuffles"][qi] = opts
                    item["options"] = [q["options"][o] for o in opts]
                elif t == "order":
                    perm = list(range(len(q["items"])))
                    if not fixed:
                        random.shuffle(perm)
                        if perm == list(range(len(perm))):
                            perm.reverse()
                    _sessions[sid]["shuffles"][qi] = perm
                    item["items"] = [q["items"][k] for k in perm]
                elif t == "number":
                    item.update({"min": q.get("min", 0), "max": q.get("max", 100), "step": q.get("step", 1),
                                 "unit": q.get("unit", "")})
                elif t == "spot":
                    w, h = jpeg_size(scene_path(slug, q.get("scene", 1)))
                    item.update({"img": "/scene/%s/%d.jpg" % (slug, int(q.get("scene", 1))),
                                 "aspect": (w / h) if h else 16 / 9})
                payload.append(item)
            return self.send_json({"sid": sid, "questions": payload,
                                   "pass_score": PASS_SCORE, "title": meta["title"]})

    def api_answer(self, body):
        sid = str(body.get("sid", ""))
        with _lock:
            sess = _sessions.get(sid)
            if not sess or sess["done"]:
                return self.send_json({"error": "no active game - start again"}, 400)
            slug = sess["slug"]
            _, questions = load_film(slug)
            expected_qi = sess["order"][sess["next_i"]]
            if int(body.get("qid", -1)) != expected_qi:
                return self.send_json({"error": "answer questions in order"}, 400)
            q = questions[expected_qi]
            try:
                correct, reveal = grade(q, sess["shuffles"].get(expected_qi), body, slug)
            except (TypeError, ValueError, KeyError, IndexError) as e:
                return self.send_json({"error": "bad answer: %s" % e}, 400)
            if correct:
                sess["correct"] += 1
                sess["streak"] += 1
                sess["max_streak"] = max(sess["max_streak"], sess["streak"])
            else:
                sess["streak"] = 0
            sess["next_i"] += 1
            result = {"correct": correct, "explain": q.get("explain", ""),
                      "score": sess["correct"], "answered": sess["next_i"],
                      "total": len(questions)}
            result.update(reveal)
            if sess["next_i"] >= len(sess["order"]):
                sess["done"] = True
                st = load_state(slug)
                st["attempts"] += 1
                st["best_score"] = max(st["best_score"], sess["correct"])
                passed = sess["correct"] >= PASS_SCORE
                if passed:
                    st["unlocked"] = True
                else:
                    st["cooldown_until"] = time.time() + COOLDOWN_SECONDS
                who = sess.get("who") or ""
                if who:
                    # each kid keeps their own best; the poster itself is the family's
                    k = st.setdefault("kids", {}).setdefault(who, {"best": 0, "attempts": 0, "passed": False})
                    k["attempts"] += 1
                    k["best"] = max(k["best"], sess["correct"])
                    k["passed"] = bool(k["passed"] or passed)
                    # sticker material: best streak ever, a perfect game, a pass without the usher
                    k["best_streak"] = max(int(k.get("best_streak", 0)), int(sess.get("max_streak", 0)))
                    k["perfect"] = bool(k.get("perfect")) or sess["correct"] >= len(questions)
                    k["no_usher"] = bool(k.get("no_usher")) or (passed and not sess.get("hint_used"))
                save_state(slug, st)
                result["final"] = {"passed": passed, "score": sess["correct"],
                                   "unlocked": st["unlocked"], "printed": st["printed"],
                                   "cooldown": COOLDOWN_SECONDS if not passed else 0,
                                   "who": who}
            return self.send_json(result)

    def api_hint(self, body):
        """The usher: once per game, point out one WRONG ticket for the current question.
        Server side because the client never holds the answer key."""
        sid = str(body.get("sid", ""))
        with _lock:
            sess = _sessions.get(sid)
            if not sess or sess["done"]:
                return self.send_json({"error": "no active game - start again"}, 400)
            if sess.get("hint_used"):
                return self.send_json({"error": "the usher already helped this game"}, 400)
            _, questions = load_film(sess["slug"])
            expected_qi = sess["order"][sess["next_i"]]
            if int(body.get("qid", -1)) != expected_qi:
                return self.send_json({"error": "that is not the current question"}, 400)
            q = questions[expected_qi]
            t = q_type(q)
            if t in OPTION_TYPES:
                shuffled = sess["shuffles"][expected_qi]
                wrong = [j for j, o in enumerate(shuffled) if o != q["answer"]]
                if not wrong:
                    return self.send_json({"error": "nothing to remove"}, 400)
                hint = {"remove": random.choice(wrong)}
            elif t == "order":
                perm = sess["shuffles"][expected_qi]
                hint = {"first": perm.index(0)}          # which shuffled item goes first
            elif t == "number":
                lo0, hi0 = float(q.get("min", 0)), float(q.get("max", 100))
                width = max((hi0 - lo0) / 4.0, float(q.get("step", 1)) * 2)
                ans = float(q["answer"])
                lo = max(lo0, ans - random.random() * width)
                hi = min(hi0, lo + width)
                lo = max(lo0, hi - width)
                hint = {"lo": lo, "hi": hi}
            elif t == "spot":
                cx, cy, r = q["targets"][0]
                hint = {"ring": [cx, cy, r * 2.4]}
            else:
                return self.send_json({"error": "The usher only knows the tickets, not the truth"}, 400)
            sess["hint_used"] = True
            return self.send_json(hint)

    def api_vote(self, body):
        """Coming attractions: each kid can want a film. Toggle. The grown ups read the tally."""
        who = str(body.get("who", ""))[:24]
        title = str(body.get("title", ""))[:120]
        if who not in kids():
            return self.send_json({"error": "pick who is voting first"}, 400)
        if title not in [i.get("title") for i in load_explorer()]:
            return self.send_json({"error": "unknown film"}, 400)
        with _lock:
            votes = load_votes()
            names = votes.setdefault(title, [])
            if who in names:
                names.remove(who)
            else:
                names.append(who)
            save_votes(votes)
            return self.send_json({"ok": True, "votes": votes})

    def api_print(self, slug, body):
        cfg = load_config()
        with _lock:
            st = load_state(slug)
            if not st["unlocked"]:
                return self.send_json({"error": "Not unlocked yet - beat the quiz first!"}, 403)
            if not cfg.get("printing_enabled"):
                return self.send_json({"error": "Poster printing opens when the frames arrive. Hang tight!"}, 403)
            if st["printed"] and str(body.get("parent_code", "")) != str(cfg.get("parent_code")):
                return self.send_json({"error": "already_printed"}, 403)
            try:
                job = do_print(slug, cfg)
            except Exception as e:
                return self.send_json({"error": "Printer problem: %s" % e}, 500)
            st["printed"] = True
            st["printed_at"] = time.strftime("%Y-%m-%d %H:%M")
            save_state(slug, st)
            return self.send_json({"ok": True, "job": job})


def main():
    cfg = load_config()
    port = int(cfg.get("port", 8891))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("Film Club serving on :%d" % port)
    srv.serve_forever()


if __name__ == "__main__":
    main()
