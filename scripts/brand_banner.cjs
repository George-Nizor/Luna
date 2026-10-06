// Renders docs/images/luna-banner.png (1600x500) from the vendored brand files, the way every
// Instrumenta README banner is made: the luna surface field with the accent at the edges, the name in
// Fraunces, the crescent from InstrumentaIcons.render("luna"), and the one-line description.
//
//   node scripts/brand_banner.cjs        (needs playwright-core and a Chromium; see ui_screenshots.cjs)
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const root = path.join(__dirname, "..");
const brand = path.join(root, "app", "static", "brand");
const { chromium } = require(process.env.PLAYWRIGHT_CORE || "playwright-core");
const InstrumentaIcons = require(path.join(brand, "instrumenta-icons.js"));
const LINE = "Private, local GPU voice generation.";

function findChromium() {
  if (process.env.CHROMIUM) return process.env.CHROMIUM;
  const base = path.join(os.homedir(), ".cache", "ms-playwright");
  const dir = fs.readdirSync(base).filter((n) => n.startsWith("chromium_headless_shell-")).sort().reverse()[0];
  return path.join(base, dir, "chrome-headless-shell-linux64", "chrome-headless-shell");
}

const html = `<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="file://${brand}/fonts/fonts.css">
<style>
  html, body { margin: 0; width: 1600px; height: 500px; overflow: hidden; }
  body { display: flex; align-items: center; justify-content: center; gap: 72px; background:
    radial-gradient(ellipse 340px 420px at 0% 50%, rgba(115, 166, 196, .28), transparent 70%),
    radial-gradient(ellipse 340px 420px at 100% 50%, rgba(115, 166, 196, .28), transparent 70%), #052231; }
  .mark svg { width: 230px; height: 230px; display: block; }
  h1 { margin: 0; color: #f2ede6; font: 680 172px/0.95 "Fraunces"; font-variation-settings: "SOFT" 100, "WONK" 1, "opsz" 144; letter-spacing: -.01em; }
  p { margin: 22px 0 0 6px; color: #a4d9f9; font: 520 34px/1.25 "Commissioner"; font-variation-settings: "FLAR" 40; }
</style></head><body>
<div class="mark">${InstrumentaIcons.render("luna", { size: 230, label: "" })}</div>
<div><h1>Luna</h1><p>${LINE}</p></div>
</body></html>`;

(async () => {
  const work = fs.mkdtempSync(path.join(os.tmpdir(), "luna-banner-"));
  const file = path.join(work, "banner.html");
  fs.writeFileSync(file, html);
  const browser = await chromium.launch({ executablePath: findChromium() });
  const page = await browser.newPage({ viewport: { width: 1600, height: 500 } });
  await page.goto("file://" + file);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
  const out = path.join(root, "docs", "images", "luna-banner.png");
  await page.screenshot({ path: out });
  await browser.close();
  console.log(out);
})().catch((error) => { console.error(error); process.exit(1); });
