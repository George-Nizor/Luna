// Luna's interface icons in the Instrumenta brand v2 style (Instrumenta brand/ALIGNMENT.md): a flat,
// friendly drawing on a 48-unit grid with a dark ink outline and a stepped extrusion down and to the
// right, no container behind it. The renderer is the suite's algorithm (Instrumenta's
// instrumenta-icons.js, Discere's discere-icons.ts, Forge3D's forge-icons.mjs); only the glyphs and
// their meaning hues are Luna's. The product mark itself is not here: it is InstrumentaIcons.render("luna").
//
// Output is presentation attributes and classes only: no style="", no <script>, no href, so it is safe
// under a strict Content-Security-Policy. Motion lives in luna-icons.css and keys off the m-* classes
// left on the moving parts. Exposed as window.LunaIcons (and module.exports under Node, for tests).
(function expose(root, factory) {
  const icons = factory();
  if (typeof module === "object" && module.exports) module.exports = icons;
  else root.LunaIcons = icons;
}(typeof self !== "undefined" ? self : this, () => {
  function oklchToHex(L, C, h) {
    const a = C * Math.cos((h * Math.PI) / 180);
    const b = C * Math.sin((h * Math.PI) / 180);
    const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
    const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
    const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
    const lin = [
      4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
      -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
      -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
    ];
    return "#" + lin.map((x) => {
      const v = x <= 0.0031308 ? 12.92 * x : 1.055 * Math.max(x, 0) ** (1 / 2.4) - 0.055;
      return Math.round(Math.min(1, Math.max(0, v)) * 255).toString(16).padStart(2, "0");
    }).join("").toUpperCase();
  }

  // The suite formula at Luna's quieter chroma, so no meaning hue is louder than the lunar accent.
  function colours(hue, chroma) {
    return {
      accent: oklchToHex(0.7, chroma, hue),
      light: oklchToHex(0.86, Math.min(chroma, 0.09), hue),
      deep: oklchToHex(0.42, Math.min(chroma, 0.11), hue),
      ink: oklchToHex(0.2, 0.035, hue),
    };
  }

  // Meaning hues, never decoration. Lunar is the exact luna block of Instrumenta's brand/tokens.json.
  const HUES = {
    lunar: { accent: "#73A6C4", light: "#A4D9F9", deep: "#20536E", ink: "#041824" },
    green: colours(150, 0.11),
    gold: colours(85, 0.11),
    rose: colours(10, 0.11),
    stone: { accent: "#A9A29A", light: "#D9D3CC", deep: "#4A443E", ink: "#171411" },
  };

  // Class tokens: f accent fill, f2 light fill, s ink line, thin lighter line, solid ink fill,
  // flat (casts no depth), dt (detail dropped at 24px and below), m-* motion hooks, d1..d4 delays.
  const PAGE = "M10 4H30L39 13V44H10Z";
  const G = {
    voice: { hue: "lunar", d: [[7, 15], [15.5, 9], [24, 4], [32.5, 9], [41, 15]].map(([x, top], i) =>
      `<g class="m-bar d${Math.abs(i - 2)}"><rect class="${i % 2 ? "f2" : "f"}" x="${x - 3}" y="${top}" width="6" height="${48 - top * 2}" rx="3"/>`
      + `<rect class="s" x="${x - 3}" y="${top}" width="6" height="${48 - top * 2}" rx="3"/></g>`).join("") },
    cassette: { hue: "lunar", d: '<rect class="f" x="4" y="10" width="40" height="28" rx="3.5"/><rect class="s" x="4" y="10" width="40" height="28" rx="3.5"/>'
      + '<rect class="f2" x="11" y="16" width="26" height="11" rx="2"/><rect class="s thin" x="11" y="16" width="26" height="11" rx="2"/>'
      + '<circle class="solid m-reel" cx="18" cy="21.5" r="2.6"/><circle class="solid m-reel" cx="30" cy="21.5" r="2.6"/>'
      + '<path class="f2" d="M13 38 16 32H32L35 38Z"/><path class="s" d="M13 38 16 32H32L35 38Z"/>' },
    wavfile: { hue: "lunar", d: `<path class="f2" d="${PAGE}"/><path class="s" d="${PAGE}"/><path class="f" d="M30 4V13H39Z"/><path class="s" d="M30 4V13H39Z"/>`
      + '<path class="s thin" d="M14 30H17L19.5 23 23 37 26.5 20 29.5 34 31.5 28H35"/>' },
    metadata: { hue: "lunar", d: `<path class="f2" d="${PAGE}"/><path class="s" d="${PAGE}"/><path class="f" d="M30 4V13H39Z"/><path class="s" d="M30 4V13H39Z"/>`
      + '<path class="s thin" d="M16 22H33M16 29H33M16 36H26"/>' },
    download: { hue: "lunar", d: '<path class="f" d="M19 5H29V18H36L24 31 12 18H19Z"/><path class="s" d="M19 5H29V18H36L24 31 12 18H19Z"/>'
      + '<path class="f2" d="M6 33H42V40A3 3 0 0 1 39 43H9A3 3 0 0 1 6 40Z"/><path class="s" d="M6 33H42V40A3 3 0 0 1 39 43H9A3 3 0 0 1 6 40Z"/>' },
    folder: { hue: "lunar", d: '<path class="f" d="M4 9H18L22 14H44V41H4Z"/><path class="s" d="M4 9H18L22 14H44V41H4Z"/><path class="f2" d="M4 19H44V41H4Z"/><path class="s" d="M4 19H44V41H4Z"/>' },
    reuse: { hue: "lunar", d: '<path class="f" d="M8 18A16 16 0 0 1 36 12L38 8 42 20 30 20 33 16A11 11 0 0 0 13 19Z"/><path class="s" d="M8 18A16 16 0 0 1 36 12L38 8 42 20 30 20 33 16A11 11 0 0 0 13 19Z"/>'
      + '<path class="f2" d="M40 30A16 16 0 0 1 12 36L10 40 6 28 18 28 15 32A11 11 0 0 0 35 29Z"/><path class="s" d="M40 30A16 16 0 0 1 12 36L10 40 6 28 18 28 15 32A11 11 0 0 0 35 29Z"/>' },
    gear: { hue: "lunar", d: '<g class="m-turn"><path class="f" d="M21 5H27L28 10.5 32.5 12.5 37 9.3 41.2 13.5 38 18 40 22.5 45.5 23.5V29.5L40 30.5 38 35 41.2 39.5 37 43.7 32.5 40.5 28 42.5 27 48H21L20 42.5 15.5 40.5 11 43.7 6.8 39.5 10 35 8 30.5 2.5 29.5V23.5L8 22.5 10 18 6.8 13.5 11 9.3 15.5 12.5 20 10.5Z" transform="translate(24 26.5) scale(.82) translate(-24 -26.5)"/>'
      + '<path class="s" d="M21 5H27L28 10.5 32.5 12.5 37 9.3 41.2 13.5 38 18 40 22.5 45.5 23.5V29.5L40 30.5 38 35 41.2 39.5 37 43.7 32.5 40.5 28 42.5 27 48H21L20 42.5 15.5 40.5 11 43.7 6.8 39.5 10 35 8 30.5 2.5 29.5V23.5L8 22.5 10 18 6.8 13.5 11 9.3 15.5 12.5 20 10.5Z" transform="translate(24 26.5) scale(.82) translate(-24 -26.5)"/>'
      + '<circle class="f2" cx="24" cy="26.5" r="6"/><circle class="s" cx="24" cy="26.5" r="6"/></g>' },
    sliders: { hue: "lunar", d: [11, 22, 33].map((y) => `<rect class="f2" x="6" y="${y}" width="36" height="5" rx="2.5"/><rect class="s thin" x="6" y="${y}" width="36" height="5" rx="2.5"/>`).join("")
      + '<rect class="f" x="12" y="7.5" width="9" height="12" rx="3"/><rect class="s" x="12" y="7.5" width="9" height="12" rx="3"/>'
      + '<rect class="f" x="27" y="18.5" width="9" height="12" rx="3"/><rect class="s" x="27" y="18.5" width="9" height="12" rx="3"/>'
      + '<rect class="f" x="17" y="29.5" width="9" height="12" rx="3"/><rect class="s" x="17" y="29.5" width="9" height="12" rx="3"/>' },
    profile: { hue: "lunar", d: '<path class="f2" d="M7 43C7 33 14 28 24 28S41 33 41 43Z"/><path class="s" d="M7 43C7 33 14 28 24 28S41 33 41 43Z"/>'
      + '<circle class="f" cx="24" cy="15.5" r="9"/><circle class="s" cx="24" cy="15.5" r="9"/>' },
    mic: { hue: "lunar", d: '<path class="f2" d="M10 20H14.5C14.5 26.5 18.5 30.5 24 30.5S33.5 26.5 33.5 20H38C38 28.5 32.5 34.5 26.5 35.6V39.5H32.5V44H15.5V39.5H21.5V35.6C15.5 34.5 10 28.5 10 20Z"/><path class="s" d="M10 20H14.5C14.5 26.5 18.5 30.5 24 30.5S33.5 26.5 33.5 20H38C38 28.5 32.5 34.5 26.5 35.6V39.5H32.5V44H15.5V39.5H21.5V35.6C15.5 34.5 10 28.5 10 20Z"/>'
      + '<rect class="f" x="16.5" y="3" width="15" height="24" rx="7.5"/><rect class="s" x="16.5" y="3" width="15" height="24" rx="7.5"/>'
      + '<path class="s thin dt" d="M16.5 12H22M16.5 18H22"/>' },
    clock: { hue: "lunar", d: '<circle class="f" cx="24" cy="24" r="19"/><circle class="s" cx="24" cy="24" r="19"/><circle class="f2" cx="24" cy="24" r="13"/>'
      + '<path class="s" d="M24 15V24L30.5 28"/><circle class="solid" cx="24" cy="24" r="2"/>' },
    chip: { hue: "lunar", d: [17, 22.5, 28].map((p) => [[p, 4, 3, 9], [p, 35, 3, 9], [4, p, 9, 3], [35, p, 9, 3]]
      .map(([x, y, w, h]) => `<rect class="f2" x="${x}" y="${y}" width="${w}" height="${h}" rx="1.2"/><rect class="s thin" x="${x}" y="${y}" width="${w}" height="${h}" rx="1.2"/>`).join("")).join("")
      + '<rect class="f" x="10" y="10" width="28" height="28" rx="3.5"/><rect class="s" x="10" y="10" width="28" height="28" rx="3.5"/>'
      + '<rect class="f2" x="17.5" y="17.5" width="13" height="13" rx="2"/><rect class="s thin" x="17.5" y="17.5" width="13" height="13" rx="2"/>' },
    power: { hue: "rose", d: '<circle class="f" cx="24" cy="24" r="19"/><circle class="s" cx="24" cy="24" r="19"/><path class="s" d="M17.5 16.5A10.5 10.5 0 1 0 30.5 16.5M24 12V24"/>' },
    trash: { hue: "rose", d: '<path class="f" d="M11 15H37L34 43H14Z"/><path class="s" d="M11 15H37L34 43H14Z"/><g class="m-lid"><rect class="f2" x="7" y="9" width="34" height="6" rx="2"/><rect class="s" x="7" y="9" width="34" height="6" rx="2"/>'
      + '<path class="s thin" d="M19 9V5H29V9"/></g><path class="s thin" d="M20 21V37M28 21V37"/>' },
    done: { hue: "green", d: '<circle class="f" cx="24" cy="24" r="18"/><circle class="s" cx="24" cy="24" r="18"/><path class="s m-tick" d="M15.5 24.5 21.5 30.5 33 18"/>' },
    alert: { hue: "gold", d: '<path class="f" d="M24 6 43 39H5Z"/><path class="s" d="M24 6 43 39H5Z"/><path class="s" d="M24 17V27"/><circle class="solid" cx="24" cy="32.5" r="1.8"/>' },
    failed: { hue: "rose", d: '<g class="m-shake"><circle class="f" cx="24" cy="24" r="18"/><circle class="s" cx="24" cy="24" r="18"/><path class="s" d="M17.5 17.5 30.5 30.5M30.5 17.5 17.5 30.5"/></g>' },
  };

  // Utilities that stay lines, on a 24 grid, in currentColor.
  const LINES = {
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
    chevronDown: '<path d="m6 9 6 6 6-6"/>',
    search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m20 20-4.9-4.9"/>',
    external: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    play: '<path d="M7.5 4.8v14.4a.8.8 0 0 0 1.2.7l11.3-7.2a.8.8 0 0 0 0-1.4L8.7 4.1a.8.8 0 0 0-1.2.7Z" fill="currentColor"/>',
    pause: '<rect x="6" y="4.5" width="4" height="15" rx="1.2" fill="currentColor"/><rect x="14" y="4.5" width="4" height="15" rx="1.2" fill="currentColor"/>',
    monitor: '<rect x="3" y="4.5" width="18" height="12" rx="2"/><path d="M8.5 20h7M12 16.5V20"/>',
    moon: '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6"/>',
  };

  const TIERS = {
    full: { steps: 6, dx: 0.5, dy: 0.55, line: 2.3, thin: 1.7, depthLine: 3.2, details: true },
    medium: { steps: 3, dx: 0.85, dy: 0.95, line: 2.8, thin: 2.1, depthLine: 3.4, details: false },
    small: { steps: 2, dx: 1.1, dy: 1.25, line: 3.4, thin: 2.6, depthLine: 3.6, details: false },
  };
  const tierFor = (size) => (size && size <= 16 ? "small" : size && size <= 24 ? "medium" : "full");
  const TAG = /<(\/?)(g|rect|path|circle|ellipse)\b([^>]*?)(\/?)>/g;

  function paint(markup, look) {
    return markup.replace(TAG, (whole, closing, tag, attrs, selfClose) => {
      if (closing) return whole;
      const match = attrs.match(/\sclass="([^"]*)"/);
      const tokens = match && match[1] ? match[1].split(/\s+/) : [];
      const rest = attrs.replace(/\sclass="[^"]*"/, "");
      const motion = tokens.filter((t) => /^(m-|d\d)/.test(t));
      const extra = look(tag, tokens);
      if (extra === null) return "";
      const cls = motion.length ? ` class="${motion.join(" ")}"` : "";
      return `<${tag}${cls}${rest}${extra}${selfClose ? "/" : ""}>`;
    });
  }
  const dropDetails = (s) => s.replace(/<(rect|path|circle|ellipse)\b[^>]*\bclass="[^"]*\bdt\b[^"]*"[^>]*\/>/g, "");
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  /**
   * render(name, { size, hue, label, tier }) returns an SVG string.
   * size: pixels (default 24). hue: lunar|green|gold|rose|stone, overriding the glyph's meaning hue.
   * label: accessible name; without it the icon is aria-hidden.
   */
  function render(name, options = {}) {
    const size = options.size || 24;
    const label = options.label ? ` role="img" aria-label="${esc(options.label)}"` : ' aria-hidden="true" focusable="false"';
    if (LINES[name]) {
      return `<svg class="li li-line li-${name}" viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"${label}>${LINES[name]}</svg>`;
    }
    const glyph = G[name];
    if (!glyph) throw new Error(`Unknown Luna icon: ${name}`);
    const tier = TIERS[options.tier || tierFor(size)];
    const col = HUES[options.hue || glyph.hue];
    if (!col) throw new Error(`Unknown Luna icon hue: ${options.hue}`);
    const d = tier.details ? glyph.d : dropDetails(glyph.d);
    const round = ' stroke-linecap="round" stroke-linejoin="round"';
    const front = paint(d, (tag, t) => {
      if (tag === "g") return "";
      if (t.includes("f")) return ` fill="${col.accent}"`;
      if (t.includes("f2")) return ` fill="${col.light}"`;
      if (t.includes("solid")) return ` fill="${col.ink}"`;
      if (t.includes("s")) return ` fill="none" stroke="${col.ink}" stroke-width="${t.includes("thin") ? tier.thin : tier.line}"${round}`;
      return "";
    });
    const depthLayer = paint(d, (tag, t) => {
      if (tag === "g") return "";
      if (t.includes("flat")) return null;
      return ` fill="${col.deep}" stroke="${col.deep}" stroke-width="${tier.depthLine}" stroke-linejoin="round"`;
    });
    const depth = [...Array(tier.steps)].map((_, i) => {
      const n = tier.steps - i;
      return `<g transform="translate(${(n * tier.dx).toFixed(2)} ${(n * tier.dy).toFixed(2)})">${depthLayer}</g>`;
    }).join("");
    const shift = `translate(${(-tier.steps * tier.dx * 0.5).toFixed(2)} ${(-tier.steps * tier.dy * 0.5).toFixed(2)})`;
    return `<svg class="li li-${name}" viewBox="-2 -2 52 52" width="${size}" height="${size}"${label}><g transform="${shift}"><g class="li-body"><g>${depth}</g><g>${front}</g></g></g></svg>`;
  }

  /** Replace every <i data-icon="name" data-size="24" data-hue="..."></i> under root with its SVG. */
  function hydrate(root = document) {
    root.querySelectorAll("i[data-icon]").forEach((slot) => {
      const holder = document.createElement("span");
      holder.innerHTML = render(slot.dataset.icon, { size: Number(slot.dataset.size) || 24, hue: slot.dataset.hue || undefined });
      slot.replaceWith(holder.firstElementChild);
    });
  }

  return { HUES, names: [...Object.keys(G), ...Object.keys(LINES)], render, hydrate, glyphHue: (name) => (G[name] ? G[name].hue : null) };
}));
