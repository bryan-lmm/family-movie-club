import { webkit, devices } from 'playwright';
/* The hardware-class check: drive the whole club in REAL WebKit as an iPad Pro 11 with
   touch, through every question type, the drawer, the member card, a vote and the time
   machine. Run against a LOCAL scratch server (dry_run true, empty state/), or against the
   static build (python3 film-club-src/build.py; python3 -m http.server 8899 -d film-club-src/dist):
     mkdir -p /tmp/pw && cd /tmp/pw && npm i playwright && npx playwright install webkit
     node webkit-walk.mjs http://localhost:8899 /tmp/pw/shots/
   Prints PASS/FAIL per check and any page errors; screenshots land in the out dir. */
const U = process.argv[2] || 'http://localhost:8899';
const OUT = (process.argv[3] || './shots/').replace(/\/?$/, '/');
import { mkdirSync } from 'fs'; mkdirSync(OUT, { recursive: true });
const iPad = devices['iPad Pro 11'];
const browser = await webkit.launch();
const ctx = await browser.newContext({ ...iPad });
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', e => errors.push('pageerror: ' + String(e)));
page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
await page.addInitScript(() => { window.DEV_FIXED = true; try { localStorage.setItem('fc_who', 'Riley'); sessionStorage.setItem('fc_intro', '1'); } catch (e) {} });
const log = []; const ok = (name, cond) => { log.push((cond ? 'PASS ' : 'FAIL ') + name); };
const shot = (n) => page.screenshot({ path: OUT + n + '.png' });
const W = (ms) => page.waitForTimeout(ms);
try {
  await page.goto(U + '/#/'); await page.waitForSelector('.mcard'); await W(900); await shot('w-home');
  const card = page.locator('.mcard').first(); const box = await card.boundingBox();
  await page.mouse.move(box.x + box.width * 0.8, box.y + box.height * 0.3); await page.mouse.down(); await W(150);
  ok('tilt applies a perspective transform on press', (await card.evaluate(el => el.style.transform)).includes('perspective'));
  await page.mouse.up(); await W(700);
  ok('tilt springs back on release', (await card.evaluate(el => el.style.transform)) === '');
  await page.tap('#whobtn'); await page.waitForSelector('.member'); await W(300); await shot('w-member'); ok('member card opens from the chip', true);
  await page.tap('#mclose'); await W(300);
  await page.tap('.mcard >> nth=0'); await page.waitForSelector('#playbtn'); await W(700); await shot('w-film');
  ok('film page shows crew scores', await page.locator('.cs').count() === 3);
  await page.tap('#playbtn');
  await page.waitForSelector('.stage', { timeout: 15000 }); await W(500); await shot('w-q-mc');
  await page.tap('.opt >> nth=0'); await page.waitForSelector('#nextbtn'); ok('mc reveals one correct ticket', await page.locator('.opt.correct').count() === 1);
  await page.tap('#sheetbtn'); await page.waitForSelector('.drawer.on'); await W(600); await shot('w-drawer'); ok('fact sheet opens after an answer', true);
  await page.tap('#dclose'); await W(700); ok('fact sheet closes', await page.locator('.drawer').count() === 0);
  ok('question survived the drawer', await page.locator('#nextbtn').count() === 1);
  await page.tap('#nextbtn');
  await page.waitForSelector('#range'); await W(300); const r = await page.locator('#range').boundingBox();
  await page.mouse.move(r.x + r.width / 2, r.y + r.height / 2); await page.mouse.down(); await page.mouse.move(r.x + r.width * 0.735, r.y + r.height / 2, { steps: 14 }); await page.mouse.up();
  const val = await page.locator('#range').inputValue(); ok('dial knob drags, value now ' + val, +val > 65);
  await shot('w-q-number'); await page.tap('#lock'); await page.waitForSelector('#nextbtn'); await W(1000); await shot('w-r-number'); await page.tap('#nextbtn');
  await page.waitForSelector('.facebtn'); await W(300); await page.tap('.facebtn >> nth=1'); await page.waitForSelector('#nextbtn');
  ok('who reveals the right face', await page.locator('.facebtn.correct').count() === 1); await shot('w-r-who'); await page.tap('#nextbtn');
  await page.waitForSelector('.bank .tile'); await W(300);
  await page.tap('.bank .tile >> nth=0'); await W(750); await page.tap('.bank .tile >> nth=1'); await W(750);
  ok('order: two slots filled', await page.locator('.oslot.filled').count() === 2);
  await page.tap('.oslot >> nth=1'); await W(350);
  ok('order: tapping a slot undoes it', await page.locator('.oslot.filled').count() === 1 && await page.locator('.bank .tile.used').count() === 1);
  // the kids' tap burst: three tiles tapped while the first is still flying must land in three different slots
  await page.tap('.bank .tile >> nth=1'); await page.tap('.bank .tile >> nth=2'); await page.tap('.bank .tile >> nth=3'); await W(900);
  ok('order: burst taps fill every slot, no stranded tile', await page.locator('.oslot.filled').count() === 4 && await page.locator('.bank .tile.used').count() === 4);
  ok('order: lock appears when full', await page.locator('#lockrow:not(.hidden)').count() === 1); await shot('w-q-order');
  await page.tap('#lock'); await page.waitForSelector('#nextbtn'); ok('order graded all right', await page.locator('.oslot.right').count() === 4); await page.tap('#nextbtn');
  await page.waitForSelector('.screenwrap.swipe'); await W(300); const s = await page.locator('.screen').boundingBox();
  await page.mouse.move(s.x + 80, s.y + 40); await page.mouse.down(); await page.mouse.move(s.x + 320, s.y + 46, { steps: 12 }); await shot('w-q-tf-drag');
  ok('swipe selects no text under the card', (await page.evaluate(() => String(window.getSelection ? window.getSelection().toString() : ''))) === '');
  await page.mouse.up();
  await page.waitForSelector('#nextbtn'); ok('swipe right answers true', await page.locator('.tfbtn.t.correct').count() === 1);
  await page.mouse.move(s.x + 80, s.y + 40); await page.mouse.down(); await page.mouse.move(s.x - 220, s.y + 46, { steps: 8 }); await page.mouse.up(); await W(900);
  ok('a second swipe stays in the quiz', await page.locator('.stage').count() === 1 && await page.locator('#nextbtn').count() === 1);
  await page.tap('#nextbtn');
  await page.waitForSelector('.tiles .tile'); await W(300); await page.tap('.tiles .tile >> nth=0'); await page.waitForSelector('#nextbtn');
  ok('blank: the tile lands in the slot', (await page.locator('#slot').innerText()).includes('roads')); await shot('w-r-blank'); await page.tap('#nextbtn');
  for (let k = 0; k < 3; k++) { await page.waitForSelector('.opt'); await W(200); await page.tap('.opt >> nth=0'); await page.waitForSelector('#nextbtn'); await page.tap('#nextbtn'); }
  await page.waitForSelector('#spot img'); await W(600); const sp = await page.locator('#spot').boundingBox();
  await page.tap('#spot', { position: { x: sp.width * 0.47, y: sp.height * 0.33 } }); await W(350); ok('spot: a pin lands where you tap', await page.locator('.pin').count() === 1);
  await shot('w-q-spot'); await page.tap('#lock'); await page.waitForSelector('#nextbtn'); ok('spot: the tap on Mr. Fusion counts', await page.locator('.pin.right').count() === 1); await shot('w-r-spot');
  await page.tap('#nextbtn'); await page.waitForSelector('.tally'); await W(1300); await shot('w-tally'); await W(5000); await shot('w-after');
  const cel = await page.locator('.celebrate').count(), cool = await page.locator('#cd').count();
  ok('tally resolves to a celebration or a cooldown', cel + cool === 1);
  if (cel) { await page.tap('#cback'); await W(600); }
  await page.evaluate(() => { location.hash = '#/vault'; }); await page.waitForSelector('.slot'); await W(1600); await shot('w-vault');
  await page.evaluate(() => { location.hash = '#/explorer'; }); await page.waitForSelector('.idea'); await W(1200); await shot('w-explorer');
  await page.tap('.heart >> nth=0'); await page.waitForSelector('.whopick'); await W(300); ok('a vote asks who is voting', true);
  await page.tap('.whopick >> nth=0'); await W(1200); ok('a vote lights the heart', await page.locator('.heart.on').count() >= 1);
  await page.evaluate(() => { location.hash = '#/timeline'; }); await page.waitForSelector('#next'); await W(800); await page.tap('#next'); await W(2600); await shot('w-timeline');
  ok('time machine jumps a stop', (await page.locator('.tm-dot.on').count()) === 1);
  await page.tap('#whobtn'); await page.waitForSelector('.member'); await W(400); await shot('w-stickers');
  ok('member card shows six stickers', await page.locator('.sticker').count() === 6);
  ok('a vault opener sticker is earned after the walk', await page.locator('.sticker:not(.locked)').count() >= 1);
  await page.tap('#mclose'); await W(300);
  await page.route('**/api/films', r => r.abort()); await page.route('**/data/club.json', r => r.abort());
  await page.evaluate(() => { if (window.LocalClub) LocalClub.dropCache(); location.hash = '#/vault'; }); await W(300); await page.evaluate(() => { location.hash = '#/'; }); await page.waitForSelector('.offline', { timeout: 8000 }); await W(300); await shot('w-offline');
  ok('an unreachable server shows the projector-is-off screen', true);
  await page.unroute('**/api/films'); await page.unroute('**/data/club.json'); await page.tap('#retry-online'); await page.waitForSelector('.mcard', { timeout: 8000 }); await W(300);
  ok('try again recovers when the server is back', await page.locator('.offline').count() === 0);
} catch (e) { log.push('EXCEPTION ' + e.message); await shot('w-exception'); }
console.log(log.join('\n')); console.log('page errors:', errors.length ? errors : 'none');
await browser.close();
