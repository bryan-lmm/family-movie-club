/* Family Movie Club, static edition.
   When the club is hosted as plain files (Cloudflare Pages, GitHub Pages, any file server)
   there is no app.py to grade the quiz, so this file does it in the browser: same question
   types, same scoring, same stickers, same cooldown (shorter). State lives in localStorage on
   this device only. index.html calls LocalClub.api(path, body) whenever window.LocalClub
   exists; build.py sets window.CLUB_STATIC before loading this file. Under app.py this file
   loads too but defines nothing, so the server keeps grading. */
(function () {
  if (!window.CLUB_STATIC) return;
  const PASS_SCORE = 8;
  const COOLDOWN_SECONDS = 60;          // the server uses 600; a visitor should not be locked out for ten minutes
  const KEY = 'fmc_state_v1';
  const OPTION_TYPES = ['mc', 'blank', 'who'];
  let DATA = null;
  const sessions = {};

  async function load() {
    if (DATA) return DATA;
    const r = await fetch('/data/club.json', { cache: 'no-cache' });
    if (!r.ok) throw new Error('club data ' + r.status);
    DATA = await r.json();
    return DATA;
  }
  function loadAll() {
    try { return JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { return {}; }
  }
  function saveAll(s) { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) {} }
  function loadState(slug) {
    const all = loadAll();
    return Object.assign({ cooldown_until: 0, unlocked: false, printed: false, printed_at: null, attempts: 0, best_score: 0 },
      (all.films || {})[slug] || {});
  }
  function saveState(slug, st) { const all = loadAll(); all.films = all.films || {}; all.films[slug] = st; saveAll(all); }
  function loadVotes() { return loadAll().votes || {}; }
  function saveVotes(v) { const all = loadAll(); all.votes = v; saveAll(all); }
  function shuffle(a) { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; }
  const range = n => Array.from({ length: n }, (_, i) => i);
  const qType = q => q.type || 'mc';
  const now = () => Date.now() / 1000;
  const kids = () => (DATA && DATA.kids) || [];

  function filmSummary(f) {
    const st = loadState(f.slug);
    return { slug: f.slug, title: f.meta.title, film_no: f.meta.film_no, year: f.meta.year, tagline: f.meta.tagline || '',
      title_pos: f.meta.title_pos, question_count: f.questions.length, unlocked: st.unlocked, printed: st.printed, kids: st.kids || {} };
  }

  function grade(q, shuf, body, film) {
    const t = qType(q);
    if (OPTION_TYPES.includes(t)) {
      const choice = parseInt(body.choice, 10);
      if (!(choice >= 0 && choice < shuf.length)) throw new Error('choice out of range');
      return [shuf[choice] === q.answer, { correct_index: shuf.indexOf(q.answer), correct_text: q.options[q.answer] }];
    }
    if (t === 'tf') {
      if (typeof body.value !== 'boolean') throw new Error('value must be true or false');
      return [body.value === !!q.answer, { answer: !!q.answer }];
    }
    if (t === 'order') {
      const order = body.order, n = q.items.length;
      if (!Array.isArray(order) || order.length !== n || order.map(Number).sort((a, b) => a - b).join() !== range(n).join()) throw new Error('order must list every item once');
      const chosen = order.map(k => shuf[Number(k)]);
      return [chosen.join() === range(n).join(), { correct_order: range(n).map(k => shuf.indexOf(k)) }];
    }
    if (t === 'number') {
      const v = parseFloat(body.value), ans = parseFloat(q.answer);
      return [Math.abs(v - ans) <= parseFloat(q.tolerance || 0) + 1e-9, { answer: q.answer }];
    }
    if (t === 'spot') {
      const x = parseFloat(body.x), y = parseFloat(body.y);
      if (!(x >= 0 && x <= 1 && y >= 0 && y <= 1)) throw new Error('tap outside the picture');
      const aspect = (film.scene_aspect || {})[String(q.scene || 1)] || 16 / 9;
      let hit = false;
      for (const [cx, cy, r] of q.targets) if (Math.hypot(x - cx, (y - cy) / aspect) <= r) hit = true;
      return [hit, { targets: q.targets }];
    }
    throw new Error('unknown question type');
  }

  function start(film, body) {
    const st = loadState(film.slug);
    const remaining = Math.floor(st.cooldown_until - now());
    if (remaining > 0) return { cooldown: remaining };
    let who = String(body.who || '').slice(0, 24);
    if (!kids().includes(who)) who = '';
    const fixed = !!body.fixed;
    const order = range(film.questions.length);
    if (!fixed) shuffle(order);
    const sid = Math.random().toString(36).slice(2) + Date.now().toString(36);
    const sess = { slug: film.slug, order, next_i: 0, correct: 0, done: false, shuffles: {}, who, hint_used: false, streak: 0, max_streak: 0 };
    sessions[sid] = sess;
    const payload = order.map(qi => {
      const q = film.questions[qi], t = qType(q);
      const item = { qid: qi, type: t, q: q.q };
      if (OPTION_TYPES.includes(t)) {
        const opts = range(q.options.length); if (!fixed) shuffle(opts);
        sess.shuffles[qi] = opts; item.options = opts.map(o => q.options[o]);
      } else if (t === 'order') {
        const perm = range(q.items.length);
        if (!fixed) { shuffle(perm); if (perm.join() === range(perm.length).join()) perm.reverse(); }
        sess.shuffles[qi] = perm; item.items = perm.map(k => q.items[k]);
      } else if (t === 'number') {
        Object.assign(item, { min: q.min ?? 0, max: q.max ?? 100, step: q.step ?? 1, unit: q.unit || '' });
      } else if (t === 'spot') {
        const n = parseInt(q.scene || 1, 10);
        Object.assign(item, { img: '/scene/' + film.slug + '/' + n + '.jpg', aspect: (film.scene_aspect || {})[String(n)] || 16 / 9 });
      }
      return item;
    });
    return { sid, questions: payload, pass_score: PASS_SCORE, title: film.meta.title };
  }

  function answer(body) {
    const sess = sessions[String(body.sid || '')];
    if (!sess || sess.done) return { error: 'no active game - start again' };
    const film = DATA.films.find(f => f.slug === sess.slug);
    const expected = sess.order[sess.next_i];
    if (parseInt(body.qid ?? -1, 10) !== expected) return { error: 'answer questions in order' };
    const q = film.questions[expected];
    let correct, reveal;
    try { [correct, reveal] = grade(q, sess.shuffles[expected], body, film); }
    catch (e) { return { error: 'bad answer: ' + e.message }; }
    if (correct) { sess.correct++; sess.streak++; sess.max_streak = Math.max(sess.max_streak, sess.streak); } else sess.streak = 0;
    sess.next_i++;
    const result = Object.assign({ correct, explain: q.explain || '', score: sess.correct, answered: sess.next_i, total: film.questions.length }, reveal);
    if (sess.next_i >= sess.order.length) {
      sess.done = true;
      const st = loadState(sess.slug);
      st.attempts++; st.best_score = Math.max(st.best_score, sess.correct);
      const passed = sess.correct >= PASS_SCORE;
      if (passed) st.unlocked = true; else st.cooldown_until = now() + COOLDOWN_SECONDS;
      if (sess.who) {
        st.kids = st.kids || {};
        const k = st.kids[sess.who] = st.kids[sess.who] || { best: 0, attempts: 0, passed: false };
        k.attempts++; k.best = Math.max(k.best, sess.correct); k.passed = !!(k.passed || passed);
        k.best_streak = Math.max(k.best_streak || 0, sess.max_streak);
        k.perfect = !!k.perfect || sess.correct >= film.questions.length;
        k.no_usher = !!k.no_usher || (passed && !sess.hint_used);
      }
      saveState(sess.slug, st);
      result.final = { passed, score: sess.correct, unlocked: st.unlocked, printed: st.printed, cooldown: passed ? 0 : COOLDOWN_SECONDS, who: sess.who };
    }
    return result;
  }

  function hint(body) {
    const sess = sessions[String(body.sid || '')];
    if (!sess || sess.done) return { error: 'no active game - start again' };
    if (sess.hint_used) return { error: 'the usher already helped this game' };
    const film = DATA.films.find(f => f.slug === sess.slug);
    const expected = sess.order[sess.next_i];
    if (parseInt(body.qid ?? -1, 10) !== expected) return { error: 'that is not the current question' };
    const q = film.questions[expected], t = qType(q);
    let h;
    if (OPTION_TYPES.includes(t)) {
      const wrong = sess.shuffles[expected].map((o, j) => o !== q.answer ? j : -1).filter(j => j >= 0);
      if (!wrong.length) return { error: 'nothing to remove' };
      h = { remove: wrong[Math.floor(Math.random() * wrong.length)] };
    } else if (t === 'order') {
      h = { first: sess.shuffles[expected].indexOf(0) };
    } else if (t === 'number') {
      const lo0 = parseFloat(q.min ?? 0), hi0 = parseFloat(q.max ?? 100);
      const width = Math.max((hi0 - lo0) / 4, parseFloat(q.step ?? 1) * 2), ans = parseFloat(q.answer);
      let lo = Math.max(lo0, ans - Math.random() * width), hi = Math.min(hi0, lo + width);
      lo = Math.max(lo0, hi - width);
      h = { lo, hi };
    } else if (t === 'spot') {
      const [cx, cy, r] = q.targets[0]; h = { ring: [cx, cy, r * 2.4] };
    } else return { error: 'The usher only knows the tickets, not the truth' };
    sess.hint_used = true;
    return h;
  }

  function vote(body) {
    const who = String(body.who || '').slice(0, 24), title = String(body.title || '').slice(0, 120);
    if (!kids().includes(who)) return { error: 'pick who is voting first' };
    if (!DATA.explorer.some(i => i.title === title)) return { error: 'unknown film' };
    const votes = loadVotes(); const names = votes[title] = votes[title] || [];
    const i = names.indexOf(who); if (i >= 0) names.splice(i, 1); else names.push(who);
    saveVotes(votes);
    return { ok: true, votes };
  }

  async function api(path, body) {
    let d;
    try { d = await load(); }
    catch (e) { if (typeof showOffline === 'function') showOffline(); throw e; }
    const p = path.split('?')[0];
    if (!body) {
      if (p === '/api/films') return { films: d.films.map(filmSummary), pass_score: PASS_SCORE, kids: kids() };
      if (p === '/api/timeline') return d.timeline;
      if (p === '/api/explorer') return { ideas: d.explorer, votes: loadVotes(), kids: kids() };
      if (p.startsWith('/api/film/')) {
        const slug = decodeURIComponent(p.slice('/api/film/'.length));
        const f = d.films.find(x => x.slug === slug);
        if (!f) return { error: 'unknown film' };
        const st = loadState(slug);
        return { slug, meta: f.meta, facts: f.facts, cast: f.cast, sheets: f.sheets || {}, question_count: f.questions.length, unlocked: st.unlocked,
          printed: st.printed, best_score: st.best_score, attempts: st.attempts, kids: st.kids || {} };
      }
      return { error: 'not found' };
    }
    if (p === '/api/vote') return vote(body);
    const film = d.films.find(x => x.slug === String(body.slug || ''));
    if (!film) return { error: 'unknown film' };
    if (p === '/api/start') return start(film, body);
    if (p === '/api/answer') return answer(body);
    if (p === '/api/hint') return hint(body);
    if (p === '/api/print') {
      if (!loadState(film.slug).unlocked) return { error: 'Not unlocked yet - beat the quiz first!' };
      return { error: 'Printing needs the home server. Run app.py on the computer with the poster printer to print for real.' };
    }
    return { error: 'not found' };
  }

  window.LocalClub = { api, dropCache: () => { DATA = null; }, reset: () => { try { localStorage.removeItem(KEY); } catch (e) {} } };
})();
