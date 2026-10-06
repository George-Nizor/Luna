const token = document.querySelector('meta[name="local-session-token"]').content;
const languages = ["Auto", "English", "Chinese", "Japanese", "Korean", "German", "French", "Russian", "Portuguese", "Spanish", "Italian"];
const voices = {
  david: { short: "David", label: "David Attenborough", model: "XTTS / original", fixedQuality: "best" },
  egirl: { short: "E-Girl", label: "E-Girl", model: "RVC / Fast or High", fixedQuality: null },
};
const $ = (id) => document.getElementById(id);
let profiles = [];
let generationActive = false;
let shuttingDown = false;
let selectedQuality = "fast";
let currentOutput = null;
let playbackPending = false;
let historyExpanded = false;
let toastTimer = null;
let messageTimer = null;
let lastFocusedElement = null;
let catalog = { voices: [], packs: [] };
let catalogSignature = "";
let policy = { max_text_characters: 0, chunk_max_characters: 1 };
let policyReady = false;
let policyRequest = 0;
let preferencesReady = false;
let historyOffset = 0;
let historyRequest = 0;
let historyOutputs = [];
let historySearchTimer = null;

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const INTERNAL_SIZE = 480;
let coreCanvas = $("voice-core-canvas");
coreCanvas.width = INTERNAL_SIZE;
coreCanvas.height = INTERNAL_SIZE;
let coreContext = coreCanvas.getContext("2d");
let coreState = "idle";
let coreLoop = null;
let coreFrameId = 0;
let corePulse = 0;
let analyser = null;
let audioContext = null;
let audioSource = null;
let frequencyData = null;
let timeData = null;
let waveformContext = $("playback-waveform").getContext("2d");

// Brand v2: interface icons (static/brand/luna-icons.js), the crescent mark (instrumenta-icons.js) and
// the theme. The visualiser and waveform are content: their shapes are Luna's own, their colours come
// from the --viz-* tokens so they stay readable in either theme.
const icon = (name, size = 24, hue) => window.LunaIcons ? window.LunaIcons.render(name, { size, hue }) : "";
const brandMark = (size) => window.InstrumentaIcons ? window.InstrumentaIcons.render("luna", { size, label: "" }) : "";
const plural = (count, word) => `${count} ${word}${Number(count) === 1 ? "" : "s"}`;
let viz = { hi: "#d9efff", mid: "#73a6c4", lo: "#3d5566" };
function readVizPalette() {
  const probe = document.createElement("span"); probe.hidden = true; document.body.append(probe);
  const read = (token) => { probe.style.color = `var(${token})`; return getComputedStyle(probe).color; };
  viz = { hi: read("--viz-hi"), mid: read("--viz-mid"), lo: read("--viz-lo") };
  probe.remove();
}
function applyTheme(choice) {
  const theme = ["light", "dark"].includes(choice) ? choice : "system";
  if (theme === "system") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = theme;
  try { localStorage.setItem("luna.theme", theme); } catch (_) { /* storage unavailable */ }
  document.querySelectorAll("[data-theme-choice]").forEach((button) => button.setAttribute("aria-checked", button.dataset.themeChoice === theme ? "true" : "false"));
  readVizPalette(); renderCore(performance.now()); drawWaveform();
}
function initializeBrand() {
  window.LunaIcons?.hydrate(document);
  const mark = brandMark(44); if (mark) $("brand-mark").innerHTML = mark;
  let saved = "system"; try { saved = localStorage.getItem("luna.theme") || "system"; } catch (_) { /* storage unavailable */ }
  document.querySelectorAll("[data-theme-choice]").forEach((button) => button.addEventListener("click", () => applyTheme(button.dataset.themeChoice)));
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", () => { readVizPalette(); renderCore(performance.now()); drawWaveform(); });
  applyTheme(saved);
}

function headers(json = false) {
  const result = { "X-Local-Token": token };
  if (json) result["Content-Type"] = "application/json";
  return result;
}

async function api(url, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const form = options.body instanceof FormData;
  options.headers = { ...(options.headers || {}), ...(method === "GET" ? headers() : headers(!form)) };
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error?.message || data.detail || "Request failed");
  return data;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}
function formatDuration(seconds) { return `${Number(seconds || 0).toFixed(1)}s`; }
function formatClock(seconds) { const total = Math.max(0, Math.floor(Number.isFinite(seconds) ? seconds : 0)); return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`; }
function formatDate(value) { return new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }); }
function selectedProfile() { return profiles.find((profile) => profile.id === $("profile-select").value); }
function selectedVoice() { return $("voice-model-select").value; }
function voiceProfileId(voice = selectedVoice()) { return voice.startsWith("profile:") ? voice.slice("profile:".length) : null; }
function selectedVoiceProfile() { const id = voiceProfileId(); return profiles.find((profile) => profile.id === id); }
function voiceDetails(voice = selectedVoice()) {
  if (voices[voice]) return voices[voice];
  const profile = profiles.find((item) => `profile:${item.id}` === voice);
  return profile ? { short: profile.name, label: profile.name, model: "Qwen clone / Fast or High", fixedQuality: null } : null;
}
function outputUrl(id, kind = "audio") { return `/api/outputs/${encodeURIComponent(id)}/${kind}`; }
function authenticatedUrl(url, cacheBust = false) {
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}token=${encodeURIComponent(token)}${cacheBust ? `&t=${Date.now()}` : ""}`;
}

async function initializeDesktopSettings() {
  if (!window.voiceStudio) return;
  $("desktop-output-settings").hidden = false;
  const renderDirectory = async () => {
    const directory = await window.voiceStudio.getOutputDirectory();
    $("output-directory-value").textContent = directory;
    $("output-directory-value").title = directory;
  };
  $("choose-output-directory").addEventListener("click", async () => {
    $("choose-output-directory").disabled = true;
    try {
      const result = await window.voiceStudio.chooseOutputDirectory();
      $("output-directory-value").textContent = result.path;
      $("output-directory-value").title = result.path;
      if (result.changed) showToast("Output folder changed");
    } catch (error) {
      showToast(error?.message || "Could not change the output folder", true);
    } finally {
      $("choose-output-directory").disabled = false;
    }
  });
  $("open-output-directory").addEventListener("click", async () => {
    const error = await window.voiceStudio.openOutputDirectory();
    if (error) showToast(error, true);
  });
  await renderDirectory();
}

function fillLanguages() {
  const html = languages.map((language) => `<option value="${escapeHtml(language)}">${escapeHtml(language)}</option>`).join("");
  $("generation-language").innerHTML = html;
  $("settings-language").innerHTML = html;
  $("profile-language").innerHTML = html;
  setLanguage("English");
}

function setLanguage(value) {
  const language = languages.includes(value) ? value : "English";
  $("generation-language").value = language;
  $("settings-language").value = language;
  $("profile-language").value = language;
  $("language-setting-value").textContent = language;
  refreshPolicy(); rememberPreferences();
  document.querySelectorAll("#language-menu .menu-option").forEach((option) => { const active = option.dataset.language === language; option.classList.toggle("selected", active); option.setAttribute("aria-selected", active ? "true" : "false"); });
}

function setQuality(value) {
  const fixedQuality = voiceDetails()?.fixedQuality;
  selectedQuality = fixedQuality || (value === "best" ? "best" : "fast");
  $("settings-quality").querySelector('option[value="best"]').textContent = fixedQuality ? "Original" : "High";
  $("settings-quality").value = selectedQuality;
  $("quality-setting-value").textContent = fixedQuality ? "Original" : selectedQuality === "best" ? "High" : "Fast";
  $("quality-trigger").disabled = Boolean(fixedQuality);
  $("quality-trigger").setAttribute("aria-disabled", fixedQuality ? "true" : "false");
  $("quality-trigger").title = fixedQuality ? "This voice provides one original XTTS checkpoint." : "Fast uses 0.6B; High uses 1.7B.";
  $("settings-quality").disabled = Boolean(fixedQuality);
  refreshPolicy(); rememberPreferences();
  document.querySelectorAll("#quality-menu .menu-option").forEach((option) => { const active = option.dataset.quality === selectedQuality; option.classList.toggle("selected", active); option.setAttribute("aria-selected", active ? "true" : "false"); });
}

function setVoiceModel(value) {
  const voice = value && voiceDetails(value) ? value : $("voice-model-select").options[0]?.value;
  if (!voice) return;
  const detail = voiceDetails(voice);
  $("voice-model-select").value = voice;
  $("voice-setting-value").textContent = detail.short;
  document.querySelectorAll("#voice-menu .menu-option").forEach((option) => { const active = option.dataset.model === voice; option.classList.toggle("selected", active); option.setAttribute("aria-selected", active ? "true" : "false"); });
  document.querySelectorAll(".voice-option").forEach((option) => { const active = option.dataset.model === voice; option.classList.toggle("selected", active); option.setAttribute("aria-pressed", active ? "true" : "false"); });
  const profile = selectedVoiceProfile();
  if (profile) $("profile-select").value = profile.id;
  $("profile-summary").textContent = profile ? `Using ${profile.name}` : "Fixed voice, no profile";
  const available = (catalog.voices || []).find((item) => item.id === voice)?.qualities || [];
  setQuality(!detail.fixedQuality && available.length && !available.includes(selectedQuality) ? available[0] : selectedQuality);
  rememberPreferences(); updateGenerateState();
}

function updateGenerateState() {
  const text = $("generation-text").value;
  const ready = policyReady && voiceIsReady();
  $("generate-button").disabled = generationActive || shuttingDown || !ready || !text.trim() || text.length > policy.max_text_characters || !$("generation-seed").checkValidity() || (policy.supports_sampling && !$("generation-temperature").checkValidity());
  $("generate-button").title = !ready ? "Get this voice and quality in the voice library" : "Generate voice";
  $("choose-output-directory").disabled = generationActive;
  $("unload-button").disabled = generationActive;
}

function updateTextMetrics() {
  const length = $("generation-text").value.length;
  const maximum = policy.max_text_characters;
  $("char-counter").textContent = policyReady ? length + " / " + maximum + " characters" : "Loading voice limits…";
  $("char-counter").classList.toggle("over-limit", policyReady && length > maximum);
  $("segment-counter").textContent = policyReady ? "Automatic segments up to " + policy.chunk_max_characters + " characters" : "";
  $("text-limit-help").textContent = policyReady && length > maximum ? "Reduce the text by " + (length - maximum) + " characters to generate." :
    "Long text is split safely for this model, then joined into one WAV.";
  updateGenerateState();
}

function showToast(message, error = false) {
  const toast = $("toast");
  toast.textContent = message;
  toast.className = `toast visible ${error ? "error" : ""}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 4200);
}
function showMessage(message) {
  const status = $("generation-status");
  status.textContent = message; status.classList.add("visible");
  clearTimeout(messageTimer); messageTimer = setTimeout(() => status.classList.remove("visible"), 4200);
}

function signalEnergy() {
  if (!frequencyData) return 0;
  let sum = 0;
  for (const value of frequencyData) sum += value;
  return sum / frequencyData.length / 255;
}

function bayer(x, y) { return [[0, 2], [3, 1]][y & 1][x & 1] / 4; }
function pixelCircle(x, y, radius, size, fill) { coreContext.fillStyle = fill; coreContext.fillRect(Math.round(x - size / 2), Math.round(y - size / 2), size, size); }

function renderCore(timestamp = 0) {
  const ctx = coreContext;
  ctx.imageSmoothingEnabled = false;
  ctx.clearRect(0, 0, INTERNAL_SIZE, INTERNAL_SIZE);
  const cx = 240; const cy = 240; const energy = signalEnergy();
  const live = coreState === "playing" || coreState === "generating" || coreState === "loading";
  const phase = reducedMotion.matches ? 0 : timestamp * (coreState === "loading" ? .00045 : .00012);
  const pulse = live ? energy * 8 + (coreState === "generating" ? 2.5 + Math.sin(timestamp * .012) * 1.5 : 0) : corePulse;
  corePulse *= .93;

  // Dithered hollow sphere.
  for (let y = -94; y <= 94; y += 3) for (let x = -94; x <= 94; x += 3) {
    const distance = Math.sqrt(x * x + y * y);
    if (distance > 86) continue;
    const edge = Math.max(0, 1 - Math.abs(distance - 76) / 14);
    const shade = edge * .94 + (1 - distance / 86) * .13;
    const threshold = bayer(Math.floor(x / 3), Math.floor(y / 3));
    if (shade > threshold + .18) pixelCircle(cx + x, cy + y, 0, 3, shade > .72 ? viz.hi : shade > .44 ? viz.mid : viz.lo);
  }
  // Dotted inner rings and a broken bright rim.
  for (let i = 0; i < 128; i += 1) {
    const angle = (i / 128) * Math.PI * 2;
    const ring = 96 + Math.sin(i * 1.7 + phase * 3) * .8;
    if (i % 3 !== 1) pixelCircle(cx + Math.cos(angle) * ring, cy + Math.sin(angle) * ring, 0, 2, i % 7 === 0 ? viz.hi : viz.lo);
  }
  for (let i = 0; i < 96; i += 1) {
    const angle = (i / 96) * Math.PI * 2 + phase;
    if ((i + Math.floor(phase * 16)) % 8 > 5) continue;
    const ring = 111 + pulse;
    pixelCircle(cx + Math.cos(angle) * ring, cy + Math.sin(angle) * ring, 0, i % 5 === 0 ? 4 : 2, i % 5 === 0 ? viz.hi : viz.mid);
  }
  // Radial frequency bars.
  for (let i = 0; i < 96; i += 1) {
    const angle = (i / 96) * Math.PI * 2 + phase * .45;
    const sample = frequencyData ? frequencyData[Math.floor((i / 96) * frequencyData.length)] / 255 : .06 + Math.max(0, Math.sin(i * 1.31 + timestamp * .002)) * (coreState === "generating" ? .16 : .025);
    const base = 130; const length = 4 + sample * (live ? 44 : 11);
    const x = Math.round(cx + Math.cos(angle) * base); const y = Math.round(cy + Math.sin(angle) * base);
    const x2 = Math.round(cx + Math.cos(angle) * (base + length)); const y2 = Math.round(cy + Math.sin(angle) * (base + length));
    ctx.strokeStyle = sample > .6 ? viz.hi : sample > .25 ? viz.mid : viz.lo; ctx.lineWidth = i % 6 === 0 ? 3 : 2; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x2, y2); ctx.stroke();
  }
  // Cardinal markers and sparse pixels.
  for (const [angle, length] of [[0, 19], [Math.PI / 2, 19], [Math.PI, 19], [Math.PI * 1.5, 19]]) {
    const x = Math.round(cx + Math.cos(angle + phase * .2) * 171); const y = Math.round(cy + Math.sin(angle + phase * .2) * 171);
    ctx.fillStyle = viz.mid; ctx.fillRect(x - (Math.abs(Math.cos(angle)) > .5 ? length / 2 : 2), y - (Math.abs(Math.sin(angle)) > .5 ? length / 2 : 2), Math.abs(Math.cos(angle)) > .5 ? length : 4, Math.abs(Math.sin(angle)) > .5 ? length : 4);
  }
  for (let i = 0; i < 24; i += 1) {
    const angle = i * 2.41 + phase * (i % 2 ? -.4 : .3); const radius = 156 + (i % 5) * 10;
    const strength = live ? .5 + signalEnergy() : .25;
    if (i % 3 === 0 || strength > .8) pixelCircle(cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius, 0, i % 4 === 0 ? 3 : 2, i % 5 === 0 ? viz.hi : viz.lo);
  }
  // Central waveform glyph.
  for (let i = -4; i <= 4; i += 1) {
    const sample = timeData ? Math.abs((timeData[Math.floor((i + 4) / 8 * timeData.length)] - 128) / 128) : .18 + Math.abs(Math.sin(timestamp * .006 + i)) * (coreState === "generating" ? .5 : .16);
    const height = Math.max(5, Math.round(8 + sample * (live ? 22 : 8)));
    ctx.fillStyle = i === 0 || Math.abs(i) === 3 ? viz.hi : viz.mid; ctx.fillRect(cx + i * 7 - 1, cy - height / 2, 3, height);
  }
  if (coreLoop === "live" && !document.hidden && !reducedMotion.matches) coreFrameId = requestAnimationFrame(renderCore);
}

function startCoreLoop(mode) { coreLoop = mode; cancelAnimationFrame(coreFrameId); coreFrameId = requestAnimationFrame(renderCore); }
function settleCore() { coreLoop = "idle"; cancelAnimationFrame(coreFrameId); coreFrameId = 0; renderCore(performance.now()); }
function setCoreState(state) { coreState = state; document.body.dataset.coreState = state; $("brand").classList.toggle("ii-play", ["playing", "generating", "loading"].includes(state) && !reducedMotion.matches); if (state === "playing" || state === "generating" || state === "loading") startCoreLoop("live"); else settleCore(); }

function drawWaveform() {
  const ctx = waveformContext; const width = 360; const height = 30;
  ctx.imageSmoothingEnabled = false; ctx.clearRect(0, 0, width, height);
  for (let x = 0; x < width; x += 4) {
    const index = timeData ? Math.floor((x / width) * timeData.length) : x;
    const raw = timeData ? Math.abs((timeData[index] - 128) / 128) : .08 + Math.abs(Math.sin(x * .16)) * .12;
    const bar = Math.max(1, Math.round(raw * 22)); ctx.fillStyle = currentOutput ? (x % 24 === 0 ? viz.hi : viz.mid) : viz.lo; ctx.fillRect(x, Math.round((height - bar) / 2), 2, bar);
  }
  if (currentOutput) { const audio = $("result-audio"); const progress = audio.duration ? audio.currentTime / audio.duration : 0; ctx.fillStyle = viz.hi; ctx.fillRect(Math.round(progress * (width - 2)), 1, 3, height - 2); }
}

function connectAudioAnalyser() {
  if (analyser) return;
  try {
    audioContext = new (window.AudioContext || window.webkitAudioContext)(); analyser = audioContext.createAnalyser(); analyser.fftSize = 256; analyser.smoothingTimeConstant = .8;
    audioSource = audioContext.createMediaElementSource($("result-audio")); audioSource.connect(analyser); analyser.connect(audioContext.destination); frequencyData = new Uint8Array(analyser.frequencyBinCount); timeData = new Uint8Array(analyser.fftSize);
  } catch (_) { analyser = null; }
}
function readSignal() { if (analyser) { analyser.getByteFrequencyData(frequencyData); analyser.getByteTimeDomainData(timeData); } drawWaveform(); }

function renderProfiles() {
  const selected = $("profile-select").value;
  const activeVoice = selectedVoice();
  const enabled = (catalog.voices || []).filter((voice) => voice.enabled);
  for (const item of catalog.voices || []) {
    voices[item.id] = { short: item.label, label: item.label,
      model: item.description, fixedQuality: item.id === "david" ? "best" : null, ...item };
  }
  $("profile-select").innerHTML = '<option value="">No profile selected</option>' + profiles.map((profile) =>
    `<option value="${escapeHtml(profile.id)}">${escapeHtml(profile.name)}</option>`).join("");
  $("profile-select").value = profiles.some((profile) => profile.id === selected) ? selected : (profiles[0]?.id || "");
  const choices = [...enabled.map((voice) => ({ id: voice.id, label: voice.label,
    description: voice.description, ready: voice.qualities.length > 0 })),
    ...profiles.map((profile) => ({ id: "profile:" + profile.id, label: profile.name,
      description: "Qwen voice clone", ready: true }))];
  $("voice-menu").innerHTML = choices.map((voice) =>
    `<button class="menu-option" type="button" role="option" data-model="${escapeHtml(voice.id)}" aria-selected="false">${escapeHtml(voice.label)}${voice.ready ? "" : " · get model"}</button>`).join("");
  $("voice-model-select").innerHTML = choices.map((voice) =>
    `<option value="${escapeHtml(voice.id)}">${escapeHtml(voice.label)}</option>`).join("");
  document.querySelector(".settings-voice-list").innerHTML = choices.map((voice) =>
    `<button class="voice-option" type="button" data-model="${escapeHtml(voice.id)}" aria-pressed="false">${escapeHtml(voice.label)}<small>${voice.ready ? "" : "Download required · "}${escapeHtml(voice.description)}</small></button>`).join("");
  renderProfileDetails();
  const fallback = choices.find((voice) => voice.ready)?.id || choices.find((voice) => voice.id.startsWith("qwen:"))?.id || choices[0]?.id;
  setVoiceModel(preferencesReady && choices.some((voice) => voice.id === activeVoice) ? activeVoice : fallback);
}
function renderProfileDetails() {
  const profile = selectedProfile(); const target = $("profile-details");
  if (!profile) { target.textContent = "No profile selected"; target.className = "profile-details"; return; }
  target.className = "profile-details"; target.innerHTML = `<div class="profile-heading"><div><strong>${escapeHtml(profile.name)}</strong><small>${escapeHtml(profile.language)}</small></div></div><audio controls src="/api/profiles/${encodeURIComponent(profile.id)}/reference?token=${encodeURIComponent(token)}"></audio>`;
}
async function loadProfiles() { profiles = (await api("/api/profiles")).profiles || []; renderProfiles(); }

function historyModelLabel(item) {
  const quality = item.quality === "best" ? "High" : "Fast";
  if (item.model_id === "david") return "XTTS · Original";
  if (String(item.model_id).startsWith("egirl")) return "RVC · " + quality;
  return String(item.model_id || "Unknown model").split("/").pop() + " · " + quality;
}

function setHistoryExpanded(expanded) {
  historyExpanded = Boolean(expanded);
  $("main-history-list").hidden = !historyExpanded;
  $("history-controls").hidden = !historyExpanded;
  $("history-pagination").hidden = !historyExpanded;
  $("history-toggle").setAttribute("aria-expanded", historyExpanded ? "true" : "false");
  $("history-arrow").classList.toggle("is-open", historyExpanded);
}

async function loadHistory() {
  const request = ++historyRequest;
  const params = new URLSearchParams({ offset: String(historyOffset), limit: "50",
    q: $("history-search").value, quality: $("history-quality").value, sort: $("history-sort").value });
  const data = await api("/api/outputs?" + params);
  if (request !== historyRequest) return;
  if (historyOffset && historyOffset >= data.total) { historyOffset = 0; return loadHistory(); }
  historyOutputs = data.outputs || [];
  $("history-count").textContent = `${plural(data.stats.count, "output")} · ${formatBytes(data.stats.size_bytes)}`;
  $("settings-history-count").textContent = plural(data.stats.count, "output");
  $("history-retention").textContent = data.history_limit ? `Automatic retention: ${data.history_limit} outputs` : "All generations kept until you delete them";
  $("history-page").textContent = data.total ? `${historyOffset + 1}–${Math.min(historyOffset + 50, data.total)} of ${data.total}` : "0 outputs";
  $("history-previous").disabled = historyOffset === 0;
  $("history-next").disabled = historyOffset + 50 >= data.total;
  const list = $("main-history-list");
  list.innerHTML = historyOutputs.length ? historyOutputs.map((item) =>
    `<article class="history-row" data-output-id="${escapeHtml(item.id)}">
      <button class="history-icon" data-action="play" type="button" ${item.audio_available ? "" : "disabled"} aria-label="Play ${escapeHtml(item.profile_name)}">${icon("play", 18)}</button>
      <div class="history-main"><strong>${escapeHtml(item.profile_name)}</strong>
        <span class="history-meta">${escapeHtml(historyModelLabel(item))} · <span class="mono">${formatDuration(item.duration_seconds)} · ${formatBytes(item.size_bytes)}</span> · ${escapeHtml(formatDate(item.created_at))}</span>
        <p class="history-text">${escapeHtml(item.text || "Text was not saved by this older Luna version.")}</p>
        <details><summary>Generation details</summary><dl class="generation-details">
          <dt>Model</dt><dd>${escapeHtml(item.model_id)}</dd>
          <dt>Language</dt><dd>${escapeHtml(item.language)}</dd>
          <dt>Seed</dt><dd>${item.seed ?? "Not recorded"}</dd>
          <dt>Segments / characters</dt><dd>${item.chunk_count} / ${item.text_character_count}</dd>
          <dt>Sample rate</dt><dd>${item.sample_rate ? item.sample_rate + " Hz" : "Not recorded"}</dd>
          <dt>Generation time</dt><dd>${item.generation_seconds == null ? "Not recorded" : formatDuration(item.generation_seconds)}</dd>
          <dt>Style</dt><dd>${escapeHtml(item.instruction || "Default")}</dd>
          <dt>Sampling temperature</dt><dd>${item.parameters?.temperature ?? "Original preset"}</dd>
          <dt>Output ID</dt><dd>${escapeHtml(item.id)}</dd>
        </dl><pre class="history-full-text">${escapeHtml(item.text || "")}</pre></details>
      </div><div class="history-actions">
        <button class="text-action" data-action="export" type="button" ${item.audio_available ? "" : "disabled"}>${icon("wavfile", 22)}<span>Export WAV</span></button>
        <a class="text-action" href="${authenticatedUrl(outputUrl(item.id, "metadata"))}" download>${icon("metadata", 22)}<span>Metadata</span></a>
        <button class="text-action" data-action="reuse" type="button" ${item.text == null ? "disabled title=\"This older output did not save its text\"" : ""}>${icon("reuse", 22)}<span>Reuse text</span></button>
        ${window.voiceStudio?.revealOutput ? '<button class="text-action" data-action="reveal" type="button"' + (item.audio_available ? "" : " disabled") + '>' + icon("folder", 22) + '<span>Show in folder</span></button>' : ""}
        <button class="text-action danger" data-action="delete" type="button">${icon("trash", 22)}<span>Delete</span></button>
      </div>${item.audio_available ? "" : '<small class="missing-audio">Audio file is missing. Metadata remains available.</small>'}
    </article>`).join("") : `<div class="empty-history">${icon("cassette", 48)}<p>${$("history-search").value || $("history-quality").value ? "No generations match these filters." : "Nothing generated yet. Your sounds will collect here."}</p></div>`;
}

async function exportOutput(item) {
  if (window.voiceStudio?.exportOutput) {
    await window.voiceStudio.exportOutput(item.id);
  } else {
    const link = document.createElement("a"); link.href = authenticatedUrl(outputUrl(item.id, "download")); link.download = ""; link.click();
  }
}

function reuseOutput(item) {
  if (item.text == null || generationActive) return;
  let voice = item.voice;
  if (!voice) voice = item.profile_id === "fixed:david-attenborough" ? "david" :
    item.profile_id === "fixed:egirl-rvc" ? "egirl" : "profile";
  if (voice === "profile") voice = "profile:" + item.profile_id;
  if ([...$("voice-model-select").options].some((option) => option.value === voice)) setVoiceModel(voice);
  else showToast("Original voice is unavailable. Choose another voice before generating.", true);
  setQuality(item.quality); setLanguage(item.language);
  $("generation-text").value = item.text;
  $("generation-instruction").value = item.instruction || "";
  $("generation-seed").value = item.seed ?? "";
  $("generation-seed").setCustomValidity("");
  $("generation-temperature").value = item.parameters?.temperature ?? 0.7;
  updateTextMetrics();
  $("generation-text").focus();
  $("generation-text").scrollIntoView({ behavior: reducedMotion.matches ? "auto" : "smooth", block: "center" });
  showMessage("Text and settings restored. Change parameters, then generate.");
}

async function deleteOutput(item) {
  if (!window.confirm("Delete this generation and its audio file?")) return;
  const activeOutput = currentOutput?.id === item.id ? currentOutput : null;
  if (activeOutput) clearLatestOutput();
  try { await api("/api/outputs/" + encodeURIComponent(item.id), { method: "DELETE" }); }
  catch (error) { if (activeOutput) setLatestOutput(activeOutput); throw error; }
  await loadHistory();
  showToast("Output deleted");
}
function updatePlaybackTime() {
  const audio = $("result-audio"); $("playback-current").textContent = formatClock(audio.currentTime); $("playback-duration").textContent = formatClock(audio.duration); $("playback-scrubber").value = audio.duration ? (audio.currentTime / audio.duration) * 100 : 0; readSignal();
}
function updatePlaybackState() {
  const audio = $("result-audio"); const playing = !audio.paused && !audio.ended;
  $("playback-play").disabled = playbackPending || !currentOutput; $("playback-play").classList.toggle("is-playing", playing); $("playback-play").setAttribute("aria-label", playbackPending ? "Generation pending" : playing ? "Pause output" : "Play output");
  if (playbackPending) return;
  if (playing) { setCoreState("playing"); } else if (currentOutput) { setCoreState("ready"); }
}
function enableOutputActions(enabled) {
  const active = enabled && !playbackPending;
  $("reveal-latest-button").disabled = !active; $("reveal-latest-button").hidden = !window.voiceStudio?.revealOutput;
  $("reuse-latest-button").disabled = !active || currentOutput?.text == null;
  $("playback-play").disabled = !active; $("delete-latest-button").disabled = !active; $("delete-latest-button").classList.toggle("disabled", !active); $("result-download").classList.toggle("disabled", !active); $("result-download").setAttribute("aria-disabled", active ? "false" : "true");
}
function setPlaybackPending(pending) {
  playbackPending = Boolean(pending);
  const group = $("latest-result").querySelector(".playback-group");
  group.classList.toggle("is-pending", playbackPending);
  group.setAttribute("aria-busy", playbackPending ? "true" : "false");
  updatePlaybackState();
  enableOutputActions(Boolean(currentOutput));
}
function setLatestOutput(output) {
  currentOutput = output; connectAudioAnalyser();
  const audio = $("result-audio"); audio.src = authenticatedUrl(output.audio_url, true); audio.volume = .9; audio.load();
  $("result-download").href = authenticatedUrl(output.download_url); enableOutputActions(true); drawWaveform(); setCoreState("ready");
}
function clearLatestOutput() { const audio = $("result-audio"); audio.pause(); audio.removeAttribute("src"); audio.load(); currentOutput = null; enableOutputActions(false); drawWaveform(); setCoreState("idle"); }
async function playOutput(output) {
  if (!output.audio_url) output.audio_url = outputUrl(output.id);
  if (!output.download_url) output.download_url = outputUrl(output.id, "download");
  setLatestOutput(output); const audio = $("result-audio");
  try { if (audioContext?.state === "suspended") await audioContext.resume(); await audio.play(); } catch (error) { showToast(error?.message || "Playback failed", true); }
}

async function generate() {
  if ($("generate-button").disabled) return;
  generationActive = true; setPlaybackPending(true); updateGenerateState(); $("generate-button").classList.add("is-active", "is-working"); $("generate-button").querySelector("span").textContent = "Generating…"; $("generation-progress").classList.remove("hidden"); setCoreState("loading");
  try {
    const selected = selectedVoice(); const profileId = voiceProfileId(selected); const voice = profileId ? "profile" : selected; const result = await api("/api/generate", { method: "POST", body: JSON.stringify({ profile_id: profileId, voice, text: $("generation-text").value, language: $("generation-language").value, quality: selectedQuality, temperature: policy.supports_sampling ? Number($("generation-temperature").value) : null, instruction: policy.supports_instruction ? $("generation-instruction").value : "", seed: $("generation-seed").value === "" ? null : Number($("generation-seed").value) }) });
    corePulse = 12; setLatestOutput(result); await loadHistory();
  } catch (error) { setCoreState("error"); showToast(error.message, true); showMessage(error.message); window.setTimeout(() => setCoreState("idle"), 1600); } finally { generationActive = false; $("generate-button").classList.remove("is-active", "is-working"); $("generate-button").querySelector("span").textContent = "Generate"; $("generation-progress").classList.add("hidden"); setPlaybackPending(false); updateGenerateState(); refreshStatus(); }
}

async function refreshStatus() {
  if (shuttingDown) return;
  try {
    const status = await api("/api/status");
    const workerLabels = { ready: "Ready", starting: "Loading", loading_model: "Loading", generating: "Generating", stopping: "Unloading", error: "Error", stopped: "Stopped" };
    $("worker-status").textContent = workerLabels[status.worker_status] || "Stopped"; $("app-status").textContent = status.app_status === "running" ? "Running" : "Shutting down"; $("system-gpu-detail").textContent = status.cuda_available === true ? "CUDA available" : status.cuda_available === false ? "CUDA unavailable" : "CUDA status unknown";
    if (generationActive) setCoreState(status.worker_status === "generating" ? "generating" : "loading");
    if (!generationActive && !["playing", "error"].includes(coreState)) setCoreState(status.worker_status === "ready" ? "ready" : ["starting", "loading_model"].includes(status.worker_status) ? "loading" : "idle");
  } catch (_) { $("app-status").textContent = "Offline"; }
}
async function heartbeat() { if (!shuttingDown) { try { await api("/api/heartbeat", { method: "POST", body: "{}" }); } catch (_) {} } }

function closeMenus() { document.querySelectorAll(".pixel-menu").forEach((menu) => { menu.hidden = true; }); document.querySelectorAll(".setting-trigger").forEach((trigger) => trigger.setAttribute("aria-expanded", "false")); }
function toggleMenu(menuId, trigger) { const menu = $(menuId); const open = menu.hidden; closeMenus(); menu.hidden = !open; trigger.setAttribute("aria-expanded", open ? "true" : "false"); }
function openDialog(dialog) { lastFocusedElement = document.activeElement; dialog.showModal(); }
function closeDialog(dialog) { if (dialog.open) dialog.close(); lastFocusedElement?.focus?.(); }

async function createProfile(event) {
  event.preventDefault(); const form = $("profile-form"); const data = new FormData(form); data.set("consent_confirmed", $("consent-confirmed").checked ? "true" : "false");
  try { await api("/api/profiles", { method: "POST", body: data }); form.reset(); closeDialog($("profile-dialog")); await loadProfiles(); showToast("Profile saved"); } catch (error) { showToast(error.message, true); }
}
function shutdownPage() { document.body.innerHTML = '<main class="terminal stopped"><div class="stopped-note">' + brandMark(96) + '<h1>Luna has stopped</h1><p>Close this window, or start Luna again from Instrumenta or the Start menu.</p></div></main>'; }

// Menus and main controls.
$("voice-trigger").addEventListener("click", () => toggleMenu("voice-menu", $("voice-trigger"))); $("quality-trigger").addEventListener("click", () => toggleMenu("quality-menu", $("quality-trigger"))); $("language-trigger").addEventListener("click", () => toggleMenu("language-menu", $("language-trigger")));
$("voice-menu").addEventListener("click", (event) => { const option = event.target.closest(".menu-option"); if (!option) return; setVoiceModel(option.dataset.model); closeMenus(); }); $("quality-menu").querySelectorAll(".menu-option").forEach((option) => option.addEventListener("click", () => { setQuality(option.dataset.quality); closeMenus(); }));
$("language-menu").innerHTML = languages.map((language) => `<button class="menu-option" type="button" role="option" data-language="${escapeHtml(language)}" aria-selected="false">${escapeHtml(language)}</button>`).join(""); $("language-menu").querySelectorAll(".menu-option").forEach((option) => option.addEventListener("click", () => { setLanguage(option.dataset.language); closeMenus(); }));
$("settings-quality").addEventListener("change", (event) => setQuality(event.target.value)); $("settings-language").addEventListener("change", (event) => setLanguage(event.target.value));
$("generation-text").addEventListener("paste", (event) => {
  const field = event.currentTarget;
  const inserted = event.clipboardData?.getData("text/plain") || "";
  const length = field.value.length - (field.selectionEnd - field.selectionStart) + inserted.length;
  if (!policyReady || length > policy.max_text_characters) {
    event.preventDefault();
    showToast(policyReady ? "Paste exceeds the " + policy.max_text_characters + " character limit. Shorten it before pasting." : "Wait for the voice limits to load.", true);
  }
});
$("generation-text").addEventListener("input", updateTextMetrics); $("generate-button").addEventListener("click", generate);
document.querySelector(".settings-voice-list").addEventListener("click", (event) => { const option = event.target.closest(".voice-option"); if (option) setVoiceModel(option.dataset.model); });
$("history-toggle").addEventListener("click", () => setHistoryExpanded(!historyExpanded));
$("open-history-button").addEventListener("click", () => { closeDialog($("settings-dialog")); setHistoryExpanded(true); $("sound-history").scrollIntoView({ behavior: reducedMotion.matches ? "auto" : "smooth", block: "nearest" }); });

// Playback and action controls.
const audio = $("result-audio"); audio.addEventListener("loadedmetadata", updatePlaybackTime); audio.addEventListener("timeupdate", updatePlaybackTime); audio.addEventListener("play", updatePlaybackState); audio.addEventListener("pause", updatePlaybackState); audio.addEventListener("ended", updatePlaybackState);
$("playback-play").addEventListener("click", async () => { if (!currentOutput) return; if (audio.paused) await playOutput(currentOutput); else audio.pause(); }); $("playback-scrubber").addEventListener("input", (event) => { if (audio.duration) audio.currentTime = Number(event.target.value) / 100 * audio.duration; }); $("playback-waveform").addEventListener("click", (event) => { if (!currentOutput || !audio.duration) return; const rect = event.currentTarget.getBoundingClientRect(); audio.currentTime = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)) * audio.duration; });
$("delete-latest-button").addEventListener("click", () => currentOutput && deleteOutput(currentOutput).catch((error) => showToast(error.message, true)));
$("result-download").addEventListener("click", (event) => { if (window.voiceStudio?.exportOutput && currentOutput) { event.preventDefault(); exportOutput(currentOutput).catch((error) => showToast(error.message, true)); } });
$("reveal-latest-button").addEventListener("click", () => currentOutput && window.voiceStudio?.revealOutput(currentOutput.id).catch((error) => showToast(error.message, true)));
$("reuse-latest-button").addEventListener("click", () => currentOutput && reuseOutput(currentOutput));

// Settings, profiles, history, worker, and shutdown.
$("system-menu-button").addEventListener("click", () => openDialog($("settings-dialog"))); $("close-settings").addEventListener("click", () => closeDialog($("settings-dialog"))); $("new-profile-button").addEventListener("click", () => openDialog($("profile-dialog"))); $("close-profile").addEventListener("click", () => closeDialog($("profile-dialog"))); $("cancel-profile").addEventListener("click", () => closeDialog($("profile-dialog"))); $("profile-form").addEventListener("submit", createProfile);
$("profile-select").addEventListener("change", () => { renderProfileDetails(); const profile = selectedProfile(); if (profile) setVoiceModel(`profile:${profile.id}`); else if (selectedVoice().startsWith("profile:")) setVoiceModel("david"); }); $("delete-profile-button").addEventListener("click", async () => { const profile = selectedProfile(); if (!profile || !window.confirm(`Delete the profile ${profile.name}?`)) return; try { await api(`/api/profiles/${encodeURIComponent(profile.id)}`, { method: "DELETE" }); await loadProfiles(); showToast("Profile deleted"); } catch (error) { showToast(error.message, true); } });
$("unload-button").addEventListener("click", async () => { if (generationActive) { showToast("A generation is running", true); return; } setCoreState("unloading"); try { await api("/api/worker/unload", { method: "POST", body: "{}" }); await refreshStatus(); showToast("Worker unloaded"); } catch (error) { showToast(error.message, true); } }); $("shutdown-button").addEventListener("click", () => openDialog($("shutdown-dialog"))); $("cancel-shutdown").addEventListener("click", () => closeDialog($("shutdown-dialog"))); $("confirm-shutdown").addEventListener("click", async (event) => { event.preventDefault(); shuttingDown = true; try { if (window.voiceStudio) await window.voiceStudio.shutdown(); else await api("/api/app/shutdown", { method: "POST", body: "{}" }); closeDialog($("shutdown-dialog")); closeDialog($("settings-dialog")); shutdownPage(); } catch (error) { shuttingDown = false; closeDialog($("shutdown-dialog")); showToast(error.message, true); } });
document.addEventListener("click", (event) => { if (!event.target.closest(".setting-wrap")) closeMenus(); }); document.addEventListener("keydown", (event) => { if (event.key === "Escape") { closeMenus(); if ($("profile-dialog").open) closeDialog($("profile-dialog")); else if ($("shutdown-dialog").open) closeDialog($("shutdown-dialog")); else if ($("settings-dialog").open) closeDialog($("settings-dialog")); } }); document.addEventListener("visibilitychange", () => { if (document.hidden) { cancelAnimationFrame(coreFrameId); coreFrameId = 0; } else if (coreLoop) coreFrameId = requestAnimationFrame(renderCore); }); reducedMotion.addEventListener?.("change", () => { if (reducedMotion.matches) settleCore(); });

function formatBytes(bytes) {
  return Number(bytes || 0) >= 1e9 ? (bytes / 1e9).toFixed(2) + " GB" : Number(bytes || 0) >= 1e6 ?
    (bytes / 1e6).toFixed(1) + " MB" : (Number(bytes || 0) / 1e3).toFixed(1) + " KB";
}

async function refreshPolicy() {
  const sequence = ++policyRequest;
  policyReady = false; updateGenerateState();
  const voice = selectedVoice()?.startsWith("profile:") ? "profile" : selectedVoice();
  if (!voice) return;
  try {
    const next = await api("/api/generation-policy?" + new URLSearchParams({
      voice, quality: selectedQuality, language: $("generation-language").value }));
    if (sequence !== policyRequest) return;
    policy = next; policyReady = true;
    $("generation-text").maxLength = policy.max_text_characters;
    $("generation-instruction").disabled = !policy.supports_instruction;
    $("generation-temperature").disabled = !policy.supports_sampling;
    $("style-help").textContent = policy.supports_instruction ? "Describe tone, pacing, or emotion." : "Style directions are available for Qwen voices in High mode.";
    const detail = voiceDetails();
    $("model-warning").textContent = voice === "david" ? "Original XTTS checkpoint. This voice has one model; there is no High checkpoint." :
      voice === "egirl" ? "Qwen source plus RVC conversion. The conversion can affect clarity; compare with direct Qwen voices." :
      selectedQuality === "best" ? "High uses Qwen 1.7B. More GPU memory and generation time." : "Fast uses Qwen 0.6B. Lower memory use and faster generation.";
    if (!voiceIsReady()) $("model-warning").textContent += " This quality needs a download. Open Voices in the top bar.";
    if (detail?.native_language && detail.native_language !== $("generation-language").value && $("generation-language").value !== "Auto")
      $("model-warning").textContent += " Best suited to " + detail.native_language + ".";
    updateTextMetrics();
  } catch (error) { if (sequence === policyRequest) { policyReady = false; showToast(error.message, true); } }
}

function voiceIsReady() {
  const voice = selectedVoice();
  if (voice?.startsWith("profile:")) return (catalog.packs || []).some((pack) => pack.kind === "clone" && pack.quality === selectedQuality && pack.installed) || catalog.fake;
  return Boolean((catalog.voices || []).find((item) => item.id === voice)?.qualities.includes(selectedQuality));
}

function rememberPreferences() {
  if (!preferencesReady) return;
  localStorage.setItem("luna.preferences", JSON.stringify({
    voice: selectedVoice(), quality: selectedQuality, language: $("generation-language").value }));
}

function renderVoiceLibrary() {
  const packs = catalog.packs || [];
  const job = catalog.download;
  $("model-free-space").textContent = formatBytes(catalog.free_bytes) + " free · " + catalog.model_directory;
  $("catalog-voice-list").innerHTML = (catalog.voices || []).map((voice) =>
    `<label class="catalog-voice"><input type="checkbox" data-voice-id="${escapeHtml(voice.id)}" ${voice.enabled ? "checked" : ""}>
      <span><strong>${escapeHtml(voice.label)}</strong><small>${escapeHtml(voice.native_language)} · ${escapeHtml(voice.description)}</small></span>
      ${voice.qualities.length ? `<span class="voice-state ready">${icon("done", 16)}Ready</span>` : `<span class="voice-state">${voice.legacy ? "Legacy assets required" : "Get a pack below"}</span>`}</label>`).join("");
  $("model-pack-list").innerHTML = packs.map((pack) => {
    const active = job?.pack_id === pack.id && ["downloading", "verifying"].includes(job.status);
    return `<article class="model-pack"><div>${icon(pack.kind === "voices" ? "voice" : "mic", 36, pack.installed ? undefined : "stone")}<strong>${pack.kind === "voices" ? "Nine Qwen voices" : "Voice cloning"} · ${pack.quality === "best" ? "High, 1.7B" : "Fast, 0.6B"}</strong>
      <p><span class="mono">${formatBytes(pack.size_bytes)}</span> download · ${escapeHtml(pack.license)} · ${pack.installed ? "Installed" : "Optional"}</p>
      <a href="${escapeHtml(pack.source_url)}" target="_blank" rel="noopener">Official source and pinned revision ${icon("external", 14)}</a></div>
      <div class="pack-actions">${pack.installed ? pack.managed ? '<button class="btn small" type="button" data-remove-pack="' + pack.id + '">' + icon("trash", 20) + "<span>Remove</span></button>" : `<span class="voice-state ready">${icon("done", 16)}Included locally</span>` :
      '<button class="btn small primary" type="button" data-download-pack="' + pack.id + '"' + (active || (job && ["downloading", "verifying"].includes(job.status)) ? " disabled" : "") + ">" + icon("download", 20) + "<span>" + (active ? "Downloading" : job?.pack_id === pack.id && ["failed", "paused"].includes(job.status) ? "Resume" : "Download") + "</span></button>"}</div></article>`;
  }).join("");
  updateModelDownloadProgress();
}

function updateModelDownloadProgress() {
  const job = catalog.download;
  $("model-download-progress").hidden = !job;
  if (job) {
    $("model-download-label").textContent = `${job.status.charAt(0).toUpperCase()}${job.status.slice(1)} · ${formatBytes(job.downloaded_bytes)} / ${formatBytes(job.total_bytes)} · ${job.filename || job.pack_id}`;
    $("model-download-meter").value = job.total_bytes ? job.downloaded_bytes / job.total_bytes * 100 : 0;
    $("model-download-error").textContent = job.error || "";
    $("pause-model-download").hidden = !["downloading", "verifying"].includes(job.status);
  }
}

async function refreshCatalog() {
  const next = await api("/api/models");
  const signature = JSON.stringify([next.voices, next.packs.map((pack) => [pack.id, pack.installed])]);
  const changed = signature !== catalogSignature;
  const downloadChanged = next.download?.status !== catalog.download?.status || next.download?.pack_id !== catalog.download?.pack_id;
  catalog = next;
  if (changed) { catalogSignature = signature; renderProfiles(); }
  if (changed || downloadChanged) renderVoiceLibrary();
  else updateModelDownloadProgress();
  updateGenerateState();
}

async function initializeStudio() {
  await Promise.all([loadProfiles(), refreshCatalog(), loadHistory(), initializeDesktopSettings()]);
  let preferences = {};
  try { preferences = JSON.parse(localStorage.getItem("luna.preferences") || "{}"); } catch (_) {}
  if ([...$("voice-model-select").options].some((option) => option.value === preferences.voice)) setVoiceModel(preferences.voice);
  if (preferences.quality || catalog.default_quality) setQuality(preferences.quality || catalog.default_quality);
  if (preferences.language) setLanguage(preferences.language);
  preferencesReady = true;
  await refreshPolicy(); await refreshStatus();
  if (!(catalog.voices || []).some((voice) => voice.enabled && voice.qualities.length)) openDialog($("voices-dialog"));
}

$("open-voices-button").addEventListener("click", () => openDialog($("voices-dialog")));
$("settings-voices-button").addEventListener("click", () => { closeDialog($("settings-dialog")); openDialog($("voices-dialog")); });
$("close-voices").addEventListener("click", () => closeDialog($("voices-dialog")));
$("catalog-voice-list").addEventListener("change", async () => {
  const selected = [...$("catalog-voice-list").querySelectorAll("input:checked")].map((input) => input.dataset.voiceId);
  try { await api("/api/voices/selection", { method: "POST", body: JSON.stringify({ voices: selected }) }); await refreshCatalog(); }
  catch (error) { showToast(error.message, true); renderVoiceLibrary(); }
});
$("model-pack-list").addEventListener("click", async (event) => {
  const download = event.target.closest("[data-download-pack]");
  const remove = event.target.closest("[data-remove-pack]");
  try {
    if (download) await api("/api/models/download", { method: "POST", body: JSON.stringify({ pack_id: download.dataset.downloadPack }) });
    if (remove && window.confirm("Remove this shared model pack? Its voices will need downloading again for this quality.")) await api("/api/models/" + encodeURIComponent(remove.dataset.removePack), { method: "DELETE" });
    await refreshCatalog();
  } catch (error) { showToast(error.message, true); }
});
$("pause-model-download").addEventListener("click", async () => { await api("/api/models/download/pause", { method: "POST", body: "{}" }); await refreshCatalog(); });
$("main-history-list").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button || button.disabled) return;
  const row = button.closest("[data-output-id]");
  const item = historyOutputs.find((output) => output.id === row?.dataset.outputId);
  if (!item) return;
  try {
    if (button.dataset.action === "play") await playOutput(item);
    if (button.dataset.action === "export") await exportOutput(item);
    if (button.dataset.action === "reuse") reuseOutput(item);
    if (button.dataset.action === "reveal") await window.voiceStudio.revealOutput(item.id);
    if (button.dataset.action === "delete") await deleteOutput(item);
  } catch (error) { showToast(error.message, true); }
});
$("history-search").addEventListener("input", () => { clearTimeout(historySearchTimer); historySearchTimer = setTimeout(() => { historyOffset = 0; loadHistory().catch((error) => showToast(error.message, true)); }, 250); });
for (const id of ["history-quality", "history-sort"]) $(id).addEventListener("change", () => { historyOffset = 0; loadHistory().catch((error) => showToast(error.message, true)); });
$("history-previous").addEventListener("click", () => { historyOffset = Math.max(0, historyOffset - 50); loadHistory(); });
$("history-next").addEventListener("click", () => { historyOffset += 50; loadHistory(); });
$("generation-temperature").addEventListener("input", updateGenerateState);
$("generation-seed").addEventListener("input", () => {
  const number = Number($("generation-seed").value);
  const valid = $("generation-seed").value === "" || (Number.isInteger(number) && number >= 0 && number <= 4294967295);
  $("generation-seed").setCustomValidity(valid ? "" : "Use a whole number between 0 and 4294967295.");
  updateGenerateState();
});

initializeBrand(); fillLanguages(); setHistoryExpanded(false); updateTextMetrics(); drawWaveform(); setPlaybackPending(false); enableOutputActions(false);
initializeStudio().catch((error) => showToast(error.message, true)); heartbeat();
setInterval(heartbeat, 20000);
setInterval(() => { refreshStatus(); refreshCatalog().catch(() => {}); }, 5000);
