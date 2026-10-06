// Screenshot harness for Luna's interface: a visual check, not a test.
//
// It drives a running Luna backend in headless Chromium and shoots the main screens. Start the
// backend with the fake engine first, so nothing needs a GPU or a model pack:
//
//   ENGINE=fake ALLOW_CPU=true PORT=7891 APP_IDLE_SHUTDOWN_SECONDS=0 FAKE_DELAY_SECONDS=1 \
//     DATA_DIRECTORY=/tmp/luna-shots/data OUTPUT_DIRECTORY=/tmp/luna-shots/out \
//     RUNTIME_DIRECTORY=/tmp/luna-shots/rt LOG_DIRECTORY=/tmp/luna-shots/logs python run.py
//   node scripts/ui_screenshots.cjs [scene,scene,...]
//
// Environment: URL (default http://127.0.0.1:7891/), OUT (default build/ui-shots), THEME (dark|light,
// the emulated system scheme, default dark), REDUCED=1 (prefers-reduced-motion), W/H (1440x960),
// P (file-name prefix), CHROMIUM (browser executable), PLAYWRIGHT_CORE (module path).
// On WSL the headless shell needs libnspr4, libnss3 and libasound2t64 on LD_LIBRARY_PATH.
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

function loadPlaywright() {
  for (const id of [process.env.PLAYWRIGHT_CORE, "playwright-core"]) {
    if (!id) continue;
    try { return require(id); } catch { /* try the next */ }
  }
  console.error("playwright-core not found: npm i --no-save --no-package-lock playwright-core, or set PLAYWRIGHT_CORE.");
  process.exit(2);
}
function findChromium() {
  if (process.env.CHROMIUM) return process.env.CHROMIUM;
  const base = path.join(os.homedir(), ".cache", "ms-playwright");
  const dirs = fs.existsSync(base) ? fs.readdirSync(base).filter((n) => n.startsWith("chromium_headless_shell-")).sort().reverse() : [];
  for (const d of dirs) {
    const exe = path.join(base, d, "chrome-headless-shell-linux64", "chrome-headless-shell");
    if (fs.existsSync(exe)) return exe;
  }
  console.error("No chromium_headless_shell under ~/.cache/ms-playwright; set CHROMIUM.");
  process.exit(2);
}

const { chromium } = loadPlaywright();
const url = process.env.URL || "http://127.0.0.1:7891/";
const out = path.resolve(process.env.OUT || path.join(__dirname, "..", "build", "ui-shots"));
const theme = process.env.THEME === "light" ? "light" : "dark";
const prefix = process.env.P || `${theme}-`;
fs.mkdirSync(out, { recursive: true });

const SAMPLE = "The moon was a ghostly galleon tossed upon cloudy seas. The road was a ribbon of moonlight over the purple moor.";

async function ensureOutputs(page) {
  const count = await page.evaluate(async () => {
    const token = document.querySelector('meta[name="local-session-token"]').content;
    const data = await (await fetch("/api/outputs?limit=5", { headers: { "X-Local-Token": token } })).json();
    return data.total || 0;
  });
  if (count >= 2) return;
  for (const text of [SAMPLE, "Good evening. This is a short test of the Fast voice."]) {
    await page.fill("#generation-text", text);
    await page.waitForFunction(() => !document.getElementById("generate-button").disabled, null, { timeout: 15000 });
    await page.click("#generate-button");
    await page.waitForFunction(() => !document.body.querySelector(".generate-button.is-active"), null, { timeout: 30000 });
  }
}

async function settled(page) {
  await page.waitForFunction(() => !document.getElementById("generate-button").disabled || !document.getElementById("generation-text").value, null, { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(400);
}

async function fresh(page) {
  await page.goto(url, { waitUntil: "networkidle" });
  await page.evaluate(() => document.querySelectorAll("dialog[open]").forEach((d) => d.close()));
  await page.waitForTimeout(250);
}

const scenes = {
  async main(page) { await fresh(page); await ensureOutputs(page); await fresh(page); await page.fill("#generation-text", SAMPLE); await page.evaluate(() => document.activeElement.blur()); await settled(page); },
  async latest(page) {
    await fresh(page); await page.fill("#generation-text", SAMPLE);
    await page.click("#generate-button");
    await page.waitForFunction(() => !document.body.querySelector(".generate-button.is-active"), null, { timeout: 30000 });
    await page.waitForTimeout(300);
  },
  async generating(page) {
    await fresh(page); await page.fill("#generation-text", SAMPLE);
    await page.click("#generate-button"); await page.waitForTimeout(450);
  },
  async history(page) {
    await fresh(page); await page.click("#history-toggle"); await page.waitForTimeout(300);
    await page.evaluate(() => document.getElementById("sound-history").scrollIntoView({ block: "start" }));
    await page.evaluate(() => document.querySelector(".history-row details")?.setAttribute("open", ""));
  },
  async menu(page) { await fresh(page); await page.click("#voice-trigger"); },
  async settings(page) { await fresh(page); await page.click("#system-menu-button"); await page.waitForTimeout(200); },
  async voices(page) { await fresh(page); await page.click("#open-voices-button"); await page.waitForTimeout(200); },
  async profile(page) { await fresh(page); await page.click("#system-menu-button"); await page.click("#new-profile-button"); await page.waitForTimeout(200); },
  async shutdown(page) { await fresh(page); await page.click("#system-menu-button"); await page.click("#shutdown-button"); await page.waitForTimeout(200); },
  async focus(page) {
    await fresh(page); await page.fill("#generation-text", SAMPLE);
    await settled(page); await page.focus("#generation-text"); await page.keyboard.press("Tab"); await page.waitForTimeout(200);
  },
  async focusmenu(page) {
    await fresh(page); await page.focus("#voice-trigger"); await page.keyboard.press("Tab");
  },
  async narrow(page) { await page.setViewportSize({ width: 420, height: 900 }); await fresh(page); await page.fill("#generation-text", SAMPLE); await settled(page); },
};

(async () => {
  const pick = (process.argv[2] || Object.keys(scenes).join(",")).split(",").filter(Boolean);
  const browser = await chromium.launch({ executablePath: findChromium() });
  const context = await browser.newContext({
    viewport: { width: Number(process.env.W || 1440), height: Number(process.env.H || 960) },
    colorScheme: theme,
    reducedMotion: process.env.REDUCED ? "reduce" : "no-preference",
  });
  const page = await context.newPage();
  page.on("pageerror", (error) => console.error("page error:", error.message));
  for (const name of pick) {
    if (!scenes[name]) { console.error("unknown scene", name); continue; }
    await page.setViewportSize({ width: Number(process.env.W || 1440), height: Number(process.env.H || 960) });
    await scenes[name](page);
    const file = path.join(out, `${prefix}${name}.png`);
    await page.screenshot({ path: file });
    console.log(file);
  }
  await browser.close();
})().catch((error) => { console.error(error); process.exit(1); });
