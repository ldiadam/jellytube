const state = {
  config: null,
  status: null,
};

const $ = (id) => document.getElementById(id);

function toast(message) {
  const el = $("toast");
  el.textContent = message;
  el.classList.add("visible");
  window.setTimeout(() => el.classList.remove("visible"), 2600);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || response.statusText);
  }

  return response.status === 204 ? null : response.json();
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[char]));
}

function formatDate(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return "-";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function channelStatus(channel) {
  if (channel.lastSuccess === true) return `<span class="pill good">OK</span>`;
  if (channel.lastSuccess === false) return `<span class="pill bad">Failed</span>`;
  return `<span class="pill muted">New</span>`;
}

function renderChannels() {
  const list = $("channelList");
  $("sourceCount").textContent = `${state.config.channels.length} sources`;
  list.innerHTML = "";

  if (!state.config.channels.length) {
    list.innerHTML = `<p class="hint">No sources yet. Add a YouTube channel or playlist URL.</p>`;
    return;
  }

  for (const channel of state.config.channels) {
    const row = document.createElement("div");
    row.className = "source-row";
    row.innerHTML = `
      <div class="source-main">
        <div>${channelStatus(channel)} <strong>${esc(channel.label || "Unnamed source")}</strong></div>
        <span>${esc(channel.url)}</span>
        <small>Limit ${channel.playlistEnd || state.config.playlistEnd || "all"} · Last ${formatDate(channel.lastFinishedAt)} · Exit ${channel.lastExitCode ?? "-"}</small>
      </div>
      <label class="switch mini">
        <input type="checkbox" ${channel.enabled ? "checked" : ""} data-toggle="${channel.id}">
        <span>${channel.enabled ? "On" : "Off"}</span>
      </label>
      <div class="row-actions">
        <button data-run="${channel.id}">Run</button>
        <button data-edit="${channel.id}">Edit</button>
        <button class="danger" data-delete="${channel.id}">Delete</button>
      </div>
    `;
    list.appendChild(row);
  }

  list.querySelectorAll("[data-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!confirm("Delete this source?")) return;
      await api(`/api/channels/${button.dataset.delete}`, { method: "DELETE" });
      await loadConfig();
      toast("Source deleted");
    });
  });

  list.querySelectorAll("[data-run]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api("/api/sync/start", {
        method: "POST",
        body: JSON.stringify({ channelId: button.dataset.run }),
      });
      await loadStatus();
      toast("Source sync started");
    });
  });

  list.querySelectorAll("[data-edit]").forEach((button) => {
    button.addEventListener("click", () => openChannelDialog(button.dataset.edit));
  });

  list.querySelectorAll("[data-toggle]").forEach((input) => {
    input.addEventListener("change", async () => {
      await api(`/api/channels/${input.dataset.toggle}`, {
        method: "PUT",
        body: JSON.stringify({ enabled: input.checked }),
      });
      await loadConfig();
      toast("Source updated");
    });
  });
}

function renderCookies() {
  const profiles = state.status?.cookies?.profiles || state.config.cookies || [];
  const activeId = state.status?.cookies?.activeId || state.config.activeCookieId;
  const list = $("cookieProfiles");
  $("cookieCount").textContent = `${profiles.length} profiles`;
  list.innerHTML = "";

  if (!profiles.length) {
    list.innerHTML = `<p class="hint">No cookie profiles. Paste Netscape-format cookies below.</p>`;
    return;
  }

  for (const profile of profiles) {
    const row = document.createElement("div");
    row.className = "cookie-row";
    row.innerHTML = `
      <div>
        <strong>${esc(profile.name)}</strong>
        <span>${esc(profile.path)}</span>
        <small>${formatBytes(profile.size)} · ${profile.looksNetscape ? "Netscape" : "Bad format"} · ${formatDate(profile.updatedAt)}</small>
      </div>
      <span class="pill ${profile.id === activeId ? "good" : "muted"}">${profile.id === activeId ? "Active" : "Idle"}</span>
      <div class="row-actions">
        <button data-activate-cookie="${profile.id}">Use</button>
        <button class="danger" data-delete-cookie="${profile.id}">Delete</button>
      </div>
    `;
    list.appendChild(row);
  }

  list.querySelectorAll("[data-activate-cookie]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api(`/api/cookies/${button.dataset.activateCookie}/activate`, { method: "POST", body: "{}" });
      await refreshAll();
      toast("Cookie profile activated");
    });
  });

  list.querySelectorAll("[data-delete-cookie]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!confirm("Delete this cookie profile?")) return;
      await api(`/api/cookies/${button.dataset.deleteCookie}`, { method: "DELETE" });
      await refreshAll();
      toast("Cookie profile deleted");
    });
  });
}

function renderConfig() {
  $("autoSync").checked = state.config.autoSync;
  $("intervalHours").value = state.config.intervalHours;
  $("playlistEnd").value = state.config.playlistEnd;
  $("sleepSeconds").value = state.config.sleepSeconds;
  $("maxRecentFiles").value = state.config.maxRecentFiles;
  $("formatSelector").value = state.config.formatSelector;
  $("mergeOutputFormat").value = state.config.mergeOutputFormat;
  $("outputTemplate").value = state.config.outputTemplate;
  $("archivePath").value = state.config.archivePath;
  $("writeInfoJson").checked = state.config.writeInfoJson;
  $("writeThumbnail").checked = state.config.writeThumbnail;
  $("convertThumbnails").checked = state.config.convertThumbnails;
  $("embedMetadata").checked = state.config.embedMetadata;
  $("skipUpcomingPremieres").checked = state.config.skipUpcomingPremieres;
  $("ignorePremiereErrors").checked = state.config.ignorePremiereErrors;
  renderChannels();
}

function renderRecentFiles() {
  const list = $("recentFiles");
  const recent = state.status.recent || [];
  list.innerHTML = "";
  $("thumbnailCount").textContent = `${state.status.counts.thumbnails} thumbnails`;

  if (!recent.length) {
    list.innerHTML = `<p class="hint">No downloaded files yet.</p>`;
    return;
  }

  for (const file of recent) {
    const row = document.createElement("div");
    row.className = "file-row";
    row.innerHTML = `
      <div>
        <strong>${esc(file.path)}</strong>
        <span>${file.kind} · ${formatBytes(file.size)} · ${formatDate(file.modifiedAt)}</span>
      </div>
    `;
    list.appendChild(row);
  }
}

function renderStatus() {
  const status = state.status;
  const runState = $("runState");
  const subtext = $("runSubtext");

  if (status.running) {
    runState.textContent = "Sync in progress";
    runState.className = "status-warn";
    subtext.textContent = status.currentChannel || "Running yt-dlp.";
  } else if (status.lastSuccess === false) {
    runState.textContent = "Last sync had errors";
    runState.className = "status-bad";
    subtext.textContent = `Last run ${formatDuration(status.lastRunSeconds)}. Check logs for details.`;
  } else if (status.lastSuccess === true) {
    runState.textContent = "Ready";
    runState.className = "status-good";
    subtext.textContent = `Last run completed in ${formatDuration(status.lastRunSeconds)}.`;
  } else {
    runState.textContent = "Ready";
    runState.className = "";
    subtext.textContent = "Add sources, cookies, then run a sync.";
  }

  $("nextRun").textContent = status.autoSync ? formatDate(status.nextRunAt) : "Manual";
  $("videoCount").textContent = status.counts.videos;
  $("metadataCount").textContent = status.counts.metadata;
  $("storageBytes").textContent = formatBytes(status.bytes);

  const cookies = status.cookies;
  const cookieGood = cookies.exists && cookies.looksNetscape;
  $("railCookieText").textContent = cookieGood ? `Active: ${cookies.name}` : "Cookie profile missing or invalid";
  $("activeCookieDot").className = `dot ${cookieGood ? "good" : "bad"}`;
  renderCookies();
  renderRecentFiles();
}

async function loadConfig() {
  state.config = await api("/api/config");
  renderConfig();
}

async function loadStatus() {
  state.status = await api("/api/status");
  renderStatus();
}

async function loadLogs() {
  const payload = await api("/api/logs?lines=500");
  $("logOutput").textContent = payload.logs || "";
  $("logOutput").scrollTop = $("logOutput").scrollHeight;
}

async function saveFullConfig() {
  await api("/api/config", {
    method: "PUT",
    body: JSON.stringify(state.config),
  });
}

function collectSchedule() {
  return {
    autoSync: $("autoSync").checked,
    intervalHours: Number($("intervalHours").value || 6),
    playlistEnd: Number($("playlistEnd").value || 0),
    sleepSeconds: Number($("sleepSeconds").value || 0),
    maxRecentFiles: Number($("maxRecentFiles").value || 24),
  };
}

function collectDownload() {
  return {
    formatSelector: $("formatSelector").value || "bv*+ba/b",
    mergeOutputFormat: $("mergeOutputFormat").value || "mp4",
    outputTemplate: $("outputTemplate").value,
    archivePath: $("archivePath").value,
    writeInfoJson: $("writeInfoJson").checked,
    writeThumbnail: $("writeThumbnail").checked,
    convertThumbnails: $("convertThumbnails").checked,
    embedMetadata: $("embedMetadata").checked,
    skipUpcomingPremieres: $("skipUpcomingPremieres").checked,
    ignorePremiereErrors: $("ignorePremiereErrors").checked,
  };
}

async function saveConfigPatch(patch, message) {
  state.config = await api("/api/config", {
    method: "PUT",
    body: JSON.stringify(patch),
  });
  renderConfig();
  await loadStatus();
  toast(message);
}

function openChannelDialog(channelId) {
  const channel = state.config.channels.find((item) => item.id === channelId);
  if (!channel) return;

  $("editChannelId").value = channel.id;
  $("editChannelUrl").value = channel.url;
  $("editChannelLabel").value = channel.label || "";
  $("editChannelLimit").value = channel.playlistEnd || 0;
  $("editChannelFormat").value = channel.formatSelector || "";
  $("editChannelEnabled").checked = channel.enabled;
  $("dialogTitle").textContent = channel.label || "Source";
  $("channelDialog").showModal();
}

function bindEvents() {
  $("channelForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    await api("/api/channels", {
      method: "POST",
      body: JSON.stringify({
        url: $("channelUrl").value,
        label: $("channelLabel").value,
        playlistEnd: Number($("channelLimit").value || 0),
      }),
    });
    $("channelUrl").value = "";
    $("channelLabel").value = "";
    $("channelLimit").value = "";
    await loadConfig();
    toast("Source added");
  });

  $("saveChannelEdit").addEventListener("click", async (event) => {
    event.preventDefault();
    const channelId = $("editChannelId").value;
    await api(`/api/channels/${channelId}`, {
      method: "PUT",
      body: JSON.stringify({
        url: $("editChannelUrl").value,
        label: $("editChannelLabel").value,
        playlistEnd: Number($("editChannelLimit").value || 0),
        formatSelector: $("editChannelFormat").value,
        enabled: $("editChannelEnabled").checked,
      }),
    });
    $("channelDialog").close();
    await loadConfig();
    toast("Source saved");
  });

  $("saveSchedule").addEventListener("click", () => saveConfigPatch(collectSchedule(), "Schedule saved"));
  $("saveDownload").addEventListener("click", () => saveConfigPatch(collectDownload(), "Download options saved"));

  $("runNow").addEventListener("click", async () => {
    await api("/api/sync/start", { method: "POST", body: "{}" });
    await loadStatus();
    toast("Sync started");
  });

  $("stopRun").addEventListener("click", async () => {
    await api("/api/sync/stop", { method: "POST", body: "{}" });
    await loadStatus();
    toast("Stop requested");
  });

  $("skipRun").addEventListener("click", async () => {
    await api("/api/schedule/skip", { method: "POST", body: "{}" });
    await loadStatus();
    toast("Next run reset");
  });

  $("refreshLogs").addEventListener("click", loadLogs);

  $("clearLogs").addEventListener("click", async () => {
    await api("/api/logs", { method: "DELETE" });
    await loadLogs();
    toast("Logs cleared");
  });

  $("clearArchive").addEventListener("click", async () => {
    if (!confirm("Clear the download archive? Existing files remain, but yt-dlp may download them again.")) return;
    await api("/api/archive", { method: "DELETE" });
    toast("Archive cleared");
  });

  $("saveCookies").addEventListener("click", async () => {
    await api("/api/cookies", {
      method: "POST",
      body: JSON.stringify({
        name: $("cookieName").value || "YouTube cookies",
        content: $("cookiesText").value,
        activate: true,
      }),
    });
    $("cookiesText").value = "";
    $("cookieName").value = "";
    await refreshAll();
    toast("Cookie profile created");
  });

  $("updateActiveCookies").addEventListener("click", async () => {
    const activeId = state.status?.cookies?.activeId;
    if (!activeId) {
      toast("No active cookie profile");
      return;
    }
    await api(`/api/cookies/${activeId}`, {
      method: "PUT",
      body: JSON.stringify({
        name: $("cookieName").value || undefined,
        content: $("cookiesText").value || undefined,
      }),
    });
    $("cookiesText").value = "";
    $("cookieName").value = "";
    await refreshAll();
    toast("Active cookie profile updated");
  });

  $("clearCookiesText").addEventListener("click", () => {
    $("cookiesText").value = "";
  });
}

async function refreshAll() {
  await Promise.all([loadStatus(), loadLogs()]);
}

async function boot() {
  bindEvents();
  await loadConfig();
  await refreshAll();
  window.setInterval(refreshAll, 5000);
}

boot().catch((error) => toast(error.message));
