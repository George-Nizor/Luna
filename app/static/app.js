const token = document.querySelector('meta[name="local-session-token"]').content;
const languages = ["Auto", "English", "Chinese", "Japanese", "Korean", "German", "French", "Russian", "Portuguese", "Spanish", "Italian"];
const voices = {
  david: { short: "DAVID", label: "DAVID ATTENBOROUGH", model: "XTTS / FIXED BEST", fixedQuality: "best" },
  egirl: { short: "E-GIRL", label: "E-GIRL", model: "RVC / FAST OR BEST", fixedQuality: null },
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
  return profile ? { short: profile.name.toUpperCase(), label: profile.name.toUpperCase(), model: "QWEN CLONE / FAST OR BEST", fixedQuality: null } : null;
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
      if (result.changed) showToast("OUTPUT DIRECTORY CHANGED");
    } catch (error) {
      showToast(error?.message || "COULD NOT CHANGE OUTPUT DIRECTORY", true);
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
  const html = languages.map((language) => `<option value="${escapeHtml(language)}">${escapeHtml(language.toUpperCase())}</option>`).join("");
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
  $("language-setting-value").textContent = language.toUpperCase();
  document.querySelectorAll("#language-menu .menu-option").forEach((option) => { const active = option.dataset.language === language; option.classList.toggle("selected", active); option.setAttribute("aria-selected", active ? "true" : "false"); });
}

function setQuality(value) {
  const fixedQuality = voiceDetails()?.fixedQuality;
  selectedQuality = fixedQuality || (value === "best" ? "best" : "fast");
  $("settings-quality").value = selectedQuality;
  $("quality-setting-value").textContent = selectedQuality.toUpperCase();
  $("quality-trigger").disabled = Boolean(fixedQuality);
  $("quality-trigger").setAttribute("aria-disabled", fixedQuality ? "true" : "false");
  $("quality-trigger").title = fixedQuality ? "This repository provides one XTTS model; its configured best path is used." : "Select the Qwen source engine quality.";
  $("settings-quality").disabled = Boolean(fixedQuality);
  document.querySelectorAll("#quality-menu .menu-option").forEach((option) => { const active = option.dataset.quality === selectedQuality; option.classList.toggle("selected", active); option.setAttribute("aria-selected", active ? "true" : "false"); });
}

function setVoiceModel(value) {
  const voice = voiceDetails(value) ? value : "david";
  const detail = voiceDetails(voice);
  $("voice-model-select").value = voice;
  $("voice-setting-value").textContent = detail.short;
  document.querySelectorAll("#voice-menu .menu-option").forEach((option) => { const active = option.dataset.model === voice; option.classList.toggle("selected", active); option.setAttribute("aria-selected", active ? "true" : "false"); });
  document.querySelectorAll(".voice-option").forEach((option) => { const active = option.dataset.model === voice; option.classList.toggle("selected", active); option.setAttribute("aria-pressed", active ? "true" : "false"); });
  const profile = selectedVoiceProfile();
  if (profile) $("profile-select").value = profile.id;
  $("profile-summary").textContent = profile ? `USING ${profile.name.toUpperCase()}` : "FIXED VOICE / NO PROFILE";
  setQuality(selectedQuality);
  updateGenerateState();
}

function updateGenerateState() {
  const needsProfile = selectedVoice().startsWith("profile:");
  $("generate-button").disabled = generationActive || shuttingDown || (needsProfile && !selectedVoiceProfile()) || !$("generation-text").value.trim();
}

function updateTextMetrics() {
  const length = $("generation-text").value.length;
  $("char-counter").textContent = `${length} / 5000`;
  $("segment-counter").textContent = `${length ? Math.max(1, Math.ceil(length / 350)) : 0} segments`;
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
  ctx.fillStyle = "#000"; ctx.fillRect(0, 0, INTERNAL_SIZE, INTERNAL_SIZE);
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
    if (shade > threshold + .18) pixelCircle(cx + x, cy + y, 0, 3, shade > .72 ? "#fff" : shade > .44 ? "#bcbcbc" : "#707070");
  }
  // Dotted inner rings and a broken bright rim.
  for (let i = 0; i < 128; i += 1) {
    const angle = (i / 128) * Math.PI * 2;
    const ring = 96 + Math.sin(i * 1.7 + phase * 3) * .8;
    if (i % 3 !== 1) pixelCircle(cx + Math.cos(angle) * ring, cy + Math.sin(angle) * ring, 0, 2, i % 7 === 0 ? "#fff" : "#707070");
  }
  for (let i = 0; i < 96; i += 1) {
    const angle = (i / 96) * Math.PI * 2 + phase;
    if ((i + Math.floor(phase * 16)) % 8 > 5) continue;
    const ring = 111 + pulse;
    pixelCircle(cx + Math.cos(angle) * ring, cy + Math.sin(angle) * ring, 0, i % 5 === 0 ? 4 : 2, i % 5 === 0 ? "#fff" : "#bcbcbc");
  }
  // Radial frequency bars.
  for (let i = 0; i < 96; i += 1) {
    const angle = (i / 96) * Math.PI * 2 + phase * .45;
    const sample = frequencyData ? frequencyData[Math.floor((i / 96) * frequencyData.length)] / 255 : .06 + Math.max(0, Math.sin(i * 1.31 + timestamp * .002)) * (coreState === "generating" ? .16 : .025);
    const base = 130; const length = 4 + sample * (live ? 44 : 11);
    const x = Math.round(cx + Math.cos(angle) * base); const y = Math.round(cy + Math.sin(angle) * base);
    const x2 = Math.round(cx + Math.cos(angle) * (base + length)); const y2 = Math.round(cy + Math.sin(angle) * (base + length));
    ctx.strokeStyle = sample > .6 ? "#fff" : sample > .25 ? "#bcbcbc" : "#707070"; ctx.lineWidth = i % 6 === 0 ? 3 : 2; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x2, y2); ctx.stroke();
  }
  // Cardinal markers and sparse pixels.
  for (const [angle, length] of [[0, 19], [Math.PI / 2, 19], [Math.PI, 19], [Math.PI * 1.5, 19]]) {
    const x = Math.round(cx + Math.cos(angle + phase * .2) * 171); const y = Math.round(cy + Math.sin(angle + phase * .2) * 171);
    ctx.fillStyle = "#fff"; ctx.fillRect(x - (Math.abs(Math.cos(angle)) > .5 ? length / 2 : 2), y - (Math.abs(Math.sin(angle)) > .5 ? length / 2 : 2), Math.abs(Math.cos(angle)) > .5 ? length : 4, Math.abs(Math.sin(angle)) > .5 ? length : 4);
  }
  for (let i = 0; i < 24; i += 1) {
    const angle = i * 2.41 + phase * (i % 2 ? -.4 : .3); const radius = 156 + (i % 5) * 10;
    const strength = live ? .5 + signalEnergy() : .25;
    if (i % 3 === 0 || strength > .8) pixelCircle(cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius, 0, i % 4 === 0 ? 3 : 2, i % 5 === 0 ? "#fff" : "#707070");
  }
  // Central waveform glyph.
  for (let i = -4; i <= 4; i += 1) {
    const sample = timeData ? Math.abs((timeData[Math.floor((i + 4) / 8 * timeData.length)] - 128) / 128) : .18 + Math.abs(Math.sin(timestamp * .006 + i)) * (coreState === "generating" ? .5 : .16);
    const height = Math.max(5, Math.round(8 + sample * (live ? 22 : 8)));
    ctx.fillStyle = i === 0 || Math.abs(i) === 3 ? "#fff" : "#bcbcbc"; ctx.fillRect(cx + i * 7 - 1, cy - height / 2, 3, height);
  }
  if (coreLoop === "live" && !document.hidden && !reducedMotion.matches) coreFrameId = requestAnimationFrame(renderCore);
}

function startCoreLoop(mode) { coreLoop = mode; cancelAnimationFrame(coreFrameId); coreFrameId = requestAnimationFrame(renderCore); }
function settleCore() { coreLoop = "idle"; cancelAnimationFrame(coreFrameId); coreFrameId = 0; renderCore(performance.now()); }
function setCoreState(state) { coreState = state; document.body.dataset.coreState = state; if (state === "playing" || state === "generating" || state === "loading") startCoreLoop("live"); else settleCore(); }

function drawWaveform() {
  const ctx = waveformContext; const width = 360; const height = 30;
  ctx.imageSmoothingEnabled = false; ctx.clearRect(0, 0, width, height); ctx.fillStyle = "#000"; ctx.fillRect(0, 0, width, height);
  for (let x = 0; x < width; x += 4) {
    const index = timeData ? Math.floor((x / width) * timeData.length) : x;
    const raw = timeData ? Math.abs((timeData[index] - 128) / 128) : .08 + Math.abs(Math.sin(x * .16)) * .12;
    const bar = Math.max(1, Math.round(raw * 22)); ctx.fillStyle = currentOutput ? (x % 24 === 0 ? "#fff" : "#bcbcbc") : "#707070"; ctx.fillRect(x, Math.round((height - bar) / 2), 2, bar);
  }
  if (currentOutput) { const audio = $("result-audio"); const progress = audio.duration ? audio.currentTime / audio.duration : 0; ctx.fillStyle = "#fff"; ctx.fillRect(Math.round(progress * (width - 2)), 2, 2, height - 4); }
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
  $("profile-select").innerHTML = `<option value="">NO PROFILE SELECTED</option>${profiles.map((profile) => `<option value="${escapeHtml(profile.id)}">${escapeHtml(profile.name.toUpperCase())}</option>`).join("")}`;
  $("profile-select").value = profiles.some((profile) => profile.id === selected) ? selected : (profiles[0]?.id || "");
  const profileMenu = profiles.map((profile) => `<button class="menu-option" type="button" role="option" data-model="profile:${escapeHtml(profile.id)}" aria-selected="false">${escapeHtml(profile.name.toUpperCase())}</button>`).join("");
  $("voice-menu").innerHTML = `<button class="menu-option" type="button" role="option" data-model="david" aria-selected="false">DAVID ATTENBOROUGH</button><button class="menu-option" type="button" role="option" data-model="egirl" aria-selected="false">E-GIRL</button>${profileMenu}`;
  $("voice-model-select").innerHTML = `<option value="david">David Attenborough — XTTS</option><option value="egirl">E-Girl — RVC</option>${profiles.map((profile) => `<option value="profile:${escapeHtml(profile.id)}">${escapeHtml(profile.name)} — Qwen clone</option>`).join("")}`;
  document.querySelector(".settings-voice-list").innerHTML = `<button class="voice-option" type="button" data-model="david" aria-pressed="false">DAVID ATTENBOROUGH <small>XTTS / FIXED BEST</small></button><button class="voice-option" type="button" data-model="egirl" aria-pressed="false">E-GIRL <small>RVC / FAST OR BEST</small></button>${profiles.map((profile) => `<button class="voice-option" type="button" data-model="profile:${escapeHtml(profile.id)}" aria-pressed="false">${escapeHtml(profile.name.toUpperCase())} <small>QWEN CLONE / FAST OR BEST</small></button>`).join("")}`;
  renderProfileDetails(); setVoiceModel(voiceDetails(activeVoice) ? activeVoice : "david");
}
function renderProfileDetails() {
  const profile = selectedProfile(); const target = $("profile-details");
  if (!profile) { target.textContent = "NO PROFILE SELECTED"; target.className = "profile-details"; return; }
  target.className = "profile-details"; target.innerHTML = `<div class="profile-heading"><div><strong>${escapeHtml(profile.name.toUpperCase())}</strong><small>${escapeHtml(profile.language.toUpperCase())}</small></div></div><audio controls src="/api/profiles/${encodeURIComponent(profile.id)}/reference?token=${encodeURIComponent(token)}"></audio>`;
}
async function loadProfiles() { profiles = (await api("/api/profiles")).profiles || []; renderProfiles(); }

function historyModelLabel(item) {
  if (item.model_id === "david") return "DAVID · XTTS / FIXED BEST";
  if (item.model_id === "egirl-best") return "E-GIRL · RVC / QWEN BEST 1.7B";
  if (item.model_id === "egirl-fast" || item.model_id === "egirl") return "E-GIRL · RVC / QWEN FAST 0.6B";
  if (item.model_id === "Qwen/Qwen3-TTS-12Hz-1.7B-Base") return "VOICE PROFILE · QWEN BEST 1.7B";
  if (item.model_id === "Qwen/Qwen3-TTS-12Hz-0.6B-Base") return "VOICE PROFILE · QWEN FAST 0.6B";
  return String(item.model_id || "UNKNOWN MODEL").toUpperCase();
}

function setHistoryExpanded(expanded) {
  historyExpanded = Boolean(expanded);
  const list = $("main-history-list");
  list.hidden = !historyExpanded;
  $("history-toggle").setAttribute("aria-expanded", historyExpanded ? "true" : "false");
  $("history-arrow").classList.toggle("is-open", historyExpanded);
}

async function loadHistory() {
  const outputs = (await api("/api/outputs")).outputs || []; const list = $("main-history-list");
  $("history-count").textContent = `${outputs.length} OUTPUT${outputs.length === 1 ? "" : "S"}`;
  $("settings-history-count").textContent = `${outputs.length} OUTPUT${outputs.length === 1 ? "" : "S"}`;
  if (!outputs.length) { list.innerHTML = '<div class="empty-history">NO OUTPUTS</div>'; return; }
  list.innerHTML = outputs.map((item) => `<div class="history-row"><button class="history-icon history-play" type="button" data-id="${escapeHtml(item.id)}" data-label="${escapeHtml(item.profile_name)}" data-model="${escapeHtml(item.model_id)}" data-duration="${escapeHtml(item.duration_seconds)}" data-chunks="${escapeHtml(item.chunk_count)}" aria-label="Play ${escapeHtml(item.profile_name)}">▶</button><div class="history-main"><strong>${escapeHtml(item.profile_name.toUpperCase())}</strong><span>${escapeHtml(historyModelLabel(item))} · ${escapeHtml(formatDuration(item.duration_seconds))}</span><small>${escapeHtml(formatDate(item.created_at))}</small></div><a class="text-action" href="${authenticatedUrl(outputUrl(item.id, "download"))}" download aria-label="Download ${escapeHtml(item.profile_name)}">↓</a><button class="text-action delete-output" type="button" data-id="${escapeHtml(item.id)}" aria-label="Delete ${escapeHtml(item.profile_name)}">×</button></div>`).join("");
  list.querySelectorAll(".history-play").forEach((button) => button.addEventListener("click", async () => { await playOutput({ id: button.dataset.id, profile_name: button.dataset.label, model_id: button.dataset.model, duration_seconds: Number(button.dataset.duration), chunk_count: Number(button.dataset.chunks) }); }));
  list.querySelectorAll(".delete-output").forEach((button) => button.addEventListener("click", async () => { try { await api(`/api/outputs/${encodeURIComponent(button.dataset.id)}`, { method: "DELETE" }); if (currentOutput?.id === button.dataset.id) clearLatestOutput(); await loadHistory(); showToast("OUTPUT DELETED"); } catch (error) { showToast(error.message, true); } }));
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
function clearLatestOutput() { $("result-audio").pause(); $("result-audio").removeAttribute("src"); currentOutput = null; enableOutputActions(false); drawWaveform(); setCoreState("idle"); }
async function playOutput(output) {
  if (!output.audio_url) output.audio_url = outputUrl(output.id);
  if (!output.download_url) output.download_url = outputUrl(output.id, "download");
  setLatestOutput(output); const audio = $("result-audio");
  try { if (audioContext?.state === "suspended") await audioContext.resume(); await audio.play(); } catch (error) { showToast(error?.message || "PLAYBACK FAILED", true); }
}

async function generate() {
  generationActive = true; setPlaybackPending(true); updateGenerateState(); $("generate-button").classList.add("is-active"); $("generation-progress").classList.remove("hidden"); setCoreState("loading");
  try {
    const selected = selectedVoice(); const profileId = voiceProfileId(selected); const voice = profileId ? "profile" : selected; const result = await api("/api/generate", { method: "POST", body: JSON.stringify({ profile_id: profileId, voice, text: $("generation-text").value, language: $("generation-language").value, quality: selectedQuality }) });
    corePulse = 12; setLatestOutput(result); await loadHistory();
  } catch (error) { setCoreState("error"); showToast(error.message, true); showMessage(error.message); window.setTimeout(() => setCoreState("idle"), 1600); } finally { generationActive = false; $("generate-button").classList.remove("is-active"); $("generation-progress").classList.add("hidden"); setPlaybackPending(false); updateGenerateState(); refreshStatus(); }
}

async function refreshStatus() {
  if (shuttingDown) return;
  try {
    const status = await api("/api/status");
    const workerLabels = { ready: "READY", starting: "LOADING", loading_model: "LOADING", generating: "GENERATING", stopping: "UNLOADING", error: "ERROR", stopped: "STOPPED" };
    $("worker-status").textContent = workerLabels[status.worker_status] || "STOPPED"; $("app-status").textContent = status.app_status === "running" ? "RUNNING" : "SHUTTING DOWN"; $("system-gpu-detail").textContent = status.cuda_available === true ? "CUDA AVAILABLE" : status.cuda_available === false ? "CUDA UNAVAILABLE" : "CUDA STATUS UNKNOWN";
    if (!generationActive && !["playing", "error"].includes(coreState)) setCoreState(status.worker_status === "ready" ? "ready" : ["starting", "loading_model"].includes(status.worker_status) ? "loading" : "idle");
  } catch (_) { $("app-status").textContent = "OFFLINE"; }
}
async function heartbeat() { if (!shuttingDown) { try { await api("/api/heartbeat", { method: "POST", body: "{}" }); } catch (_) {} } }

function closeMenus() { document.querySelectorAll(".pixel-menu").forEach((menu) => { menu.hidden = true; }); document.querySelectorAll(".setting-trigger").forEach((trigger) => trigger.setAttribute("aria-expanded", "false")); }
function toggleMenu(menuId, trigger) { const menu = $(menuId); const open = menu.hidden; closeMenus(); menu.hidden = !open; trigger.setAttribute("aria-expanded", open ? "true" : "false"); }
function openDialog(dialog) { lastFocusedElement = document.activeElement; dialog.showModal(); }
function closeDialog(dialog) { if (dialog.open) dialog.close(); lastFocusedElement?.focus?.(); }

async function createProfile(event) {
  event.preventDefault(); const form = $("profile-form"); const data = new FormData(form); data.set("consent_confirmed", $("consent-confirmed").checked ? "true" : "false");
  try { await api("/api/profiles", { method: "POST", body: data }); form.reset(); closeDialog($("profile-dialog")); await loadProfiles(); showToast("PROFILE SAVED"); } catch (error) { showToast(error.message, true); }
}
function shutdownPage() { document.body.innerHTML = '<main class="terminal"><p class="generation-status visible">APPLICATION STOPPED</p></main>'; }

// Menus and main controls.
$("voice-trigger").addEventListener("click", () => toggleMenu("voice-menu", $("voice-trigger"))); $("quality-trigger").addEventListener("click", () => toggleMenu("quality-menu", $("quality-trigger"))); $("language-trigger").addEventListener("click", () => toggleMenu("language-menu", $("language-trigger")));
$("voice-menu").addEventListener("click", (event) => { const option = event.target.closest(".menu-option"); if (!option) return; setVoiceModel(option.dataset.model); closeMenus(); }); $("quality-menu").querySelectorAll(".menu-option").forEach((option) => option.addEventListener("click", () => { setQuality(option.dataset.quality); closeMenus(); }));
$("language-menu").innerHTML = languages.map((language) => `<button class="menu-option" type="button" role="option" data-language="${escapeHtml(language)}" aria-selected="false">${escapeHtml(language.toUpperCase())}</button>`).join(""); $("language-menu").querySelectorAll(".menu-option").forEach((option) => option.addEventListener("click", () => { setLanguage(option.dataset.language); closeMenus(); }));
$("settings-quality").addEventListener("change", (event) => setQuality(event.target.value)); $("settings-language").addEventListener("change", (event) => setLanguage(event.target.value));
$("generation-text").addEventListener("input", updateTextMetrics); $("generate-button").addEventListener("click", generate);
document.querySelector(".settings-voice-list").addEventListener("click", (event) => { const option = event.target.closest(".voice-option"); if (option) setVoiceModel(option.dataset.model); });
$("history-toggle").addEventListener("click", () => setHistoryExpanded(!historyExpanded));
$("open-history-button").addEventListener("click", () => { closeDialog($("settings-dialog")); setHistoryExpanded(true); $("sound-history").scrollIntoView({ behavior: reducedMotion.matches ? "auto" : "smooth", block: "nearest" }); });

// Playback and action controls.
const audio = $("result-audio"); audio.addEventListener("loadedmetadata", updatePlaybackTime); audio.addEventListener("timeupdate", updatePlaybackTime); audio.addEventListener("play", updatePlaybackState); audio.addEventListener("pause", updatePlaybackState); audio.addEventListener("ended", updatePlaybackState);
$("playback-play").addEventListener("click", async () => { if (!currentOutput) return; if (audio.paused) await playOutput(currentOutput); else audio.pause(); }); $("playback-scrubber").addEventListener("input", (event) => { if (audio.duration) audio.currentTime = Number(event.target.value) / 100 * audio.duration; }); $("playback-waveform").addEventListener("click", (event) => { if (!currentOutput || !audio.duration) return; const rect = event.currentTarget.getBoundingClientRect(); audio.currentTime = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)) * audio.duration; });
$("delete-latest-button").addEventListener("click", async () => { if (!currentOutput?.id) return; try { await api(`/api/outputs/${encodeURIComponent(currentOutput.id)}`, { method: "DELETE" }); clearLatestOutput(); await loadHistory(); showToast("OUTPUT DELETED"); } catch (error) { showToast(error.message, true); } });

// Settings, profiles, history, worker, and shutdown.
$("system-menu-button").addEventListener("click", () => openDialog($("settings-dialog"))); $("close-settings").addEventListener("click", () => closeDialog($("settings-dialog"))); $("new-profile-button").addEventListener("click", () => openDialog($("profile-dialog"))); $("close-profile").addEventListener("click", () => closeDialog($("profile-dialog"))); $("cancel-profile").addEventListener("click", () => closeDialog($("profile-dialog"))); $("profile-form").addEventListener("submit", createProfile);
$("profile-select").addEventListener("change", () => { renderProfileDetails(); const profile = selectedProfile(); if (profile) setVoiceModel(`profile:${profile.id}`); else if (selectedVoice().startsWith("profile:")) setVoiceModel("david"); }); $("delete-profile-button").addEventListener("click", async () => { const profile = selectedProfile(); if (!profile || !window.confirm(`DELETE ${profile.name.toUpperCase()}?`)) return; try { await api(`/api/profiles/${encodeURIComponent(profile.id)}`, { method: "DELETE" }); await loadProfiles(); showToast("PROFILE DELETED"); } catch (error) { showToast(error.message, true); } });
$("unload-button").addEventListener("click", async () => { if (generationActive) { showToast("GENERATION ACTIVE", true); return; } setCoreState("unloading"); try { await api("/api/worker/unload", { method: "POST", body: "{}" }); await refreshStatus(); showToast("WORKER UNLOADED"); } catch (error) { showToast(error.message, true); } }); $("shutdown-button").addEventListener("click", () => openDialog($("shutdown-dialog"))); $("cancel-shutdown").addEventListener("click", () => closeDialog($("shutdown-dialog"))); $("confirm-shutdown").addEventListener("click", async (event) => { event.preventDefault(); shuttingDown = true; try { if (window.voiceStudio) await window.voiceStudio.shutdown(); else await api("/api/app/shutdown", { method: "POST", body: "{}" }); closeDialog($("shutdown-dialog")); closeDialog($("settings-dialog")); shutdownPage(); } catch (error) { shuttingDown = false; closeDialog($("shutdown-dialog")); showToast(error.message, true); } });
document.addEventListener("click", (event) => { if (!event.target.closest(".setting-wrap")) closeMenus(); }); document.addEventListener("keydown", (event) => { if (event.key === "Escape") { closeMenus(); if ($("profile-dialog").open) closeDialog($("profile-dialog")); else if ($("shutdown-dialog").open) closeDialog($("shutdown-dialog")); else if ($("settings-dialog").open) closeDialog($("settings-dialog")); } }); document.addEventListener("visibilitychange", () => { if (document.hidden) { cancelAnimationFrame(coreFrameId); coreFrameId = 0; } else if (coreLoop) coreFrameId = requestAnimationFrame(renderCore); }); reducedMotion.addEventListener?.("change", () => { if (reducedMotion.matches) settleCore(); });

fillLanguages(); setQuality("best"); setVoiceModel("david"); setHistoryExpanded(false); updateTextMetrics(); drawWaveform(); setPlaybackPending(false); enableOutputActions(false); Promise.all([loadProfiles(), loadHistory(), refreshStatus(), initializeDesktopSettings()]).catch((error) => showToast(error.message, true)); heartbeat(); setInterval(heartbeat, 20000); setInterval(refreshStatus, 5000);
