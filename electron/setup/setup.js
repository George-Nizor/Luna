"use strict";

// Renderer for the first-run runtime setup. It only talks to the main process through
// window.lunaSetup (preload.cjs); the main process owns every path, URL and process.
(() => {
  const setup = window.lunaSetup;
  const $ = (id) => document.getElementById(id);
  const title = $("setup-title");
  const lead = $("setup-lead");
  const primary = $("primary");
  const secondary = $("secondary");
  const steps = $("steps");
  const meter = $("meter");
  const bar = $("meter-bar");
  const fill = $("meter-fill");
  const errorBox = $("error");
  const order = ["python", "download", "install", "verify"];
  let state = null;
  let busy = false;

  function bytes(value) {
    if (!Number.isFinite(value)) return "";
    if (value >= 1e9) return `${(value / 1e9).toFixed(2)} GB`;
    if (value >= 1e6) return `${(value / 1e6).toFixed(0)} MB`;
    return `${Math.max(0, Math.round(value / 1e3))} KB`;
  }

  function duration(seconds) {
    if (!Number.isFinite(seconds) || seconds <= 0) return "";
    if (seconds < 90) return `${Math.ceil(seconds)} s left`;
    if (seconds < 5400) return `${Math.ceil(seconds / 60)} min left`;
    return `${(seconds / 3600).toFixed(1)} h left`;
  }

  function button(element, label, handler) {
    element.textContent = label;
    element.hidden = !label;
    element.disabled = false;
    element.onclick = handler || null;
  }

  function markStep(phase) {
    const index = order.indexOf(phase);
    if (index < 0) return;
    steps.hidden = false;
    for (const item of steps.querySelectorAll("li")) {
      const position = order.indexOf(item.dataset.step);
      item.classList.toggle("done", position < index);
      item.classList.toggle("active", position === index);
    }
  }

  function showIntro() {
    const { summary, gpu, version } = state;
    $("version").textContent = version ? `v${version}` : "";
    $("step-python-label").textContent = `Install Python ${summary.python}`;
    $("facts").hidden = false;
    steps.hidden = false;
    $("fact-download").textContent = `${bytes(summary.downloadBytes)} once`;
    $("fact-disk").textContent = `about ${bytes(summary.installBytes)}`;
    $("fact-location").textContent = summary.root;
    const gpuFact = $("fact-gpu");
    const warning = $("gpu-warning");
    if (gpu.found) {
      gpuFact.textContent = `${gpu.name}${gpu.driver ? ` · driver ${gpu.driver}` : ""}`;
      gpuFact.className = "";
      warning.hidden = true;
    } else {
      gpuFact.textContent = "No NVIDIA GPU found";
      gpuFact.className = "gpu-missing";
      warning.hidden = false;
      warning.textContent = `${gpu.reason} Luna generates speech on an NVIDIA graphics card with CUDA (driver 570 or newer). You can still set Luna up, but it will not be able to generate speech until an NVIDIA GPU and driver are present.`;
    }
    const resumable = summary.alreadyDownloaded > 0;
    title.textContent = summary.replacing ? "Luna's voice engine needs an update" : "Set up Luna's voice engine";
    lead.textContent = summary.replacing
      ? `This version of Luna uses a different set of Python libraries. Luna downloads them once and switches over when they are ready; your voices, settings and recordings stay as they are.`
      : `Before its first voice, Luna installs Python ${summary.python} and the libraries it speaks with: PyTorch with CUDA 12.8 and the code of the Qwen, XTTS and RVC voice engines. This happens once. Voices themselves are chosen afterwards, in the voice library.`;
    if (resumable) lead.textContent += ` ${bytes(summary.alreadyDownloaded)} is already downloaded and will not be fetched again.`;
    button(primary, resumable ? "Resume setup" : gpu.found ? "Download and set up" : "Set up anyway", start);
    button(secondary, "Quit", () => setup.quit());
  }

  async function start() {
    if (busy) return;
    busy = true;
    errorBox.hidden = true;
    $("gpu-warning").hidden = true;
    title.textContent = "Setting up Luna's voice engine";
    lead.textContent = "You can keep using your computer. Cancelling keeps what has been downloaded.";
    meter.hidden = false;
    markStep("python");
    button(primary, "");
    button(secondary, "Cancel", async () => { secondary.disabled = true; secondary.textContent = "Cancelling…"; await setup.cancel(); });
    const outcome = await setup.start();
    busy = false;
    if (outcome.ok) return finished(outcome.result);
    meter.hidden = true;
    for (const item of steps.querySelectorAll("li.active")) item.classList.remove("active");
    if (outcome.cancelled) {
      title.textContent = "Setup paused";
      lead.textContent = "Nothing has been switched over. What was downloaded is kept, so the setup continues where it stopped.";
      button(primary, "Resume setup", start);
      button(secondary, "Quit", () => setup.quit());
      return;
    }
    title.textContent = "Setup did not finish";
    lead.textContent = outcome.code === "DISK_SPACE"
      ? "There is not enough free disk space. Free some space, then try again."
      : outcome.code === "DOWNLOAD"
        ? "A download failed. Check the internet connection, then try again; finished files are kept."
        : "Luna could not finish setting up its runtime. Try again; finished downloads are kept.";
    errorBox.textContent = outcome.error;
    errorBox.hidden = false;
    button(primary, "Try again", start);
    button(secondary, "Quit", () => setup.quit());
  }

  function finished(result) {
    markStep("verify");
    for (const item of steps.querySelectorAll("li")) { item.classList.remove("active"); item.classList.add("done"); }
    meter.hidden = true;
    const verification = result.verification || {};
    if (verification.cuda) {
      title.textContent = "Ready";
      lead.textContent = `The voice engine runs on ${verification.device}. Opening Luna…`;
      button(secondary, "");
      setTimeout(() => setup.proceed(), 700);
      return;
    }
    title.textContent = "Set up, but no GPU";
    lead.textContent = "The voice engine is installed, but PyTorch cannot reach an NVIDIA GPU, so Luna will not be able to generate speech. Install or update the NVIDIA driver (version 570 or newer), then restart Luna. You can still open Luna to manage voices and your library.";
    if (verification.cudaError) { errorBox.textContent = verification.cudaError; errorBox.hidden = false; }
    button(primary, "Open Luna", () => setup.proceed());
    button(secondary, "Quit", () => setup.quit());
  }

  setup.onProgress((update) => {
    if (update.phase === "log") {
      if (update.line) $("meter-detail").textContent = update.line;
      return;
    }
    markStep(update.phase === "cleanup" || update.phase === "done" ? "verify" : update.phase);
    if (update.phase === "download") {
      const percent = update.total ? (100 * update.done) / update.total : 0;
      bar.classList.remove("indeterminate");
      bar.setAttribute("aria-valuenow", String(Math.floor(percent)));
      fill.style.width = `${percent.toFixed(1)}%`;
      $("meter-bytes").textContent = `${bytes(update.done)} of ${bytes(update.total)}`;
      $("meter-rate").textContent = [update.rate > 0 ? `${bytes(update.rate)}/s` : "", duration(update.eta)].filter(Boolean).join(" · ");
      $("meter-detail").textContent = update.active?.length ? update.active.join(", ") : "";
    } else {
      bar.classList.add("indeterminate");
      bar.removeAttribute("aria-valuenow");
      fill.style.width = "";
      $("meter-bytes").textContent = update.message || "";
      $("meter-rate").textContent = "";
    }
  });

  setup.getState().then((value) => { state = value; showIntro(); }, (error) => {
    title.textContent = "Luna could not start its setup";
    errorBox.textContent = String(error?.message || error);
    errorBox.hidden = false;
    button(secondary, "Quit", () => setup.quit());
  });
})();
