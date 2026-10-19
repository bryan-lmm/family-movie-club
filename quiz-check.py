#!/usr/bin/env python3
"""Validate every films/<slug>/questions.json against the typed question contract."""
import json, os, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "film-club-src", "films")
bad = 0
for slug in sorted(os.listdir(ROOT)):
    p = os.path.join(ROOT, slug, "questions.json")
    if not os.path.exists(p): continue
    qs = json.load(open(p)); types = {}
    castj = json.load(open(os.path.join(ROOT, slug, "cast.json"))) if os.path.exists(os.path.join(ROOT, slug, "cast.json")) else []
    # a who option names the character, or the actor when the character is "Himself" (E.T.)
    cast = [m["actor"] if m["character"].lower() in ("himself", "herself", "themselves") else m["character"] for m in castj]
    for i, q in enumerate(qs):
        t = q.get("type", "mc"); types[t] = types.get(t, 0) + 1
        def err(m):
            global bad; bad += 1; print("  %s #%d (%s): %s" % (slug, i, t, m))
        if not q.get("q") or not q.get("explain"): err("missing q or explain")
        if "—" in json.dumps(q, ensure_ascii=False): err("em dash")
        if t in ("mc", "blank", "who"):
            o = q.get("options", []); a = q.get("answer")
            if not (isinstance(o, list) and 2 <= len(o) <= 4): err("options must be 2 to 4")
            if not (isinstance(a, int) and 0 <= a < len(o)): err("answer index out of range")
            if t == "blank" and "____" not in q["q"]: err("blank needs ____ in q")
            if t == "who" and cast and set(o) != set(cast): err("who options must be the four cast characters")
        elif t == "tf":
            if not isinstance(q.get("answer"), bool): err("tf answer must be true/false")
        elif t == "order":
            it = q.get("items", [])
            if not (isinstance(it, list) and len(it) == 4): err("order needs exactly 4 items")
        elif t == "number":
            for k in ("min", "max", "answer"):
                if not isinstance(q.get(k), (int, float)): err("number needs numeric " + k)
            else:
                if not (q["min"] <= q["answer"] <= q["max"]): err("answer outside min..max")
                if float(q["answer"]) != int(q["answer"]): err("answer should be a whole number")
        elif t == "spot":
            sc = q.get("scene"); tg = q.get("targets", [])
            if not os.path.exists(os.path.join(ROOT, slug, "scenes", "scene%s.jpg" % sc)): err("scene image missing")
            if not tg: err("no targets")
            for c in tg:
                if not (len(c) == 3 and all(0 <= v <= 1 for v in c) and c[2] >= 0.05): err("bad target %r" % (c,))
        else: err("unknown type")
    print("%-28s %2d questions  %s" % (slug, len(qs), " ".join("%s:%d" % kv for kv in sorted(types.items()))))
print("OK" if not bad else "%d problems" % bad); sys.exit(1 if bad else 0)
