const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const LunaIcons = require("../app/static/brand/luna-icons.js");
const InstrumentaIcons = require("../app/static/brand/instrumenta-icons.js");
const root = path.join(__dirname, "..");

test("every Luna interface icon renders CSP-safe SVG at each tier", () => {
  for (const name of LunaIcons.names) {
    for (const size of [16, 24, 48]) {
      const svg = LunaIcons.render(name, { size });
      assert.match(svg, /^<svg class="li /);
      assert.match(svg, new RegExp(`width="${size}"`));
      assert.doesNotMatch(svg, /style=|<script|href=|on\w+=/i, name);
      assert.match(svg, /aria-hidden="true"/);
    }
  }
  assert.match(LunaIcons.render("trash", { label: "Delete" }), /role="img" aria-label="Delete"/);
  assert.throws(() => LunaIcons.render("nope"), /Unknown Luna icon/);
});

test("the lunar hue is the luna block of the brand tokens", () => {
  assert.deepEqual(LunaIcons.HUES.lunar, { accent: "#73A6C4", light: "#A4D9F9", deep: "#20536E", ink: "#041824" });
  const css = fs.readFileSync(path.join(root, "app", "static", "styles.css"), "utf8");
  for (const value of ["#73a6c4", "#a4d9f9", "#20536e", "#041824"]) assert.ok(css.includes(value), value);
});

test("the crescent mark comes from the vendored brand library", () => {
  const svg = InstrumentaIcons.render("luna", { size: 44, label: "" });
  assert.match(svg, /aria-hidden="true"/);
  assert.match(svg, /#73A6C4/);
});

test("every interface icon the page asks for exists", () => {
  const html = fs.readFileSync(path.join(root, "app", "templates", "index.html"), "utf8");
  const js = fs.readFileSync(path.join(root, "app", "static", "app.js"), "utf8");
  const wanted = new Set([...html.matchAll(/data-icon="([^"]+)"/g), ...js.matchAll(/icon\("([^"]+)"/g)].map((m) => m[1]));
  assert.ok(wanted.size > 10);
  for (const name of wanted) assert.ok(LunaIcons.names.includes(name), name);
});
