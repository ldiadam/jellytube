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

  return response.json();
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

function renderChannels() {
  const list = $("channelList");
  list.innerHTML = "";

  if (!state.config.channels.length) {
    list.innerHTML = `<p class="hint">No channels yet. Add a channel or playlist URL to start syncing.</p>`;
    return;
  }

  for (const channel of state.config.channels) {
    const row = document.createElement("div");
    row.className = "channel-row";
    row.innerHTML = `
      <div>
        <strong>${channel.label || "Unnamed source"}</strong>
        <span>${channel.url}</span>
      </div>
      <label class="switch">
        <input type="checkbox" ${channel.enabled ? "checked" : ""} data-toggle="${channel.id}">
        <span>${channel.enabled ? "On" : "Off"}</span>
      </label>
      <button data-delete="${channel.id}">Delete</button>
    `;
    list.appendChild(row);
  }

  list.querySelectorAll("[data-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api(`/api/channels/${button.dataset.delete}`, { method: "DELETE" });
      await loadConfig();
      toast("Channel deleted");
    });
  });

  list.querySelectorAll("[data-toggle]").forEach((input) => {
    input.addEventListener("change", async () => {
      const channel = state.config.channels.find((item) => item.id === input.dataset.toggle);
      channel.enabled = input.checked;
      await saveFullConfig();
      await loadConfig();
      toast("Channel updated");
    });
  });
}

function renderConfig() {
  $("autoSync").checked = state.config.autoSync;
  $("intervalHours").value = state.config.intervalHours;
  $("playlistEnd").value = state.config.playlistEnd;
  $("sleepSeconds").value = state.config.sleepSeconds;
  $("formatSelector").value = state.config.formatSelector;
  $("outputTemplate").value = state.config.outputTemplate;
  renderChannels();
}

function renderStatus() {
  const status = state.status;
  const runState = $("runState");

  if (status.running) {
    runState.textContent = `Syncing ${status.currentChannel || ""}`;
    runState.className = "status-warn";
  } else if (status.lastSuccess === false) {
    runState.textContent = "Last sync had errors";
    runState.className = "status-bad";
  } else if (status.lastSuccess === true) {
    runState.textContent = `Ready. Last run ${formatDuration(status.lastRunSeconds)}`;
    runState.className = "status-good";
  } else {
    runState.textContent = "Ready";
    runState.className = "";
  }

  $("nextRun").textContent = status.autoSync ? formatDate(status.nextRunAt) : "Manual";
  $("videoCount").textContent = status.counts.videos;
  $("metadataCount").textContent = status.counts.metadata;

  const cookies = status.cookies;
  $("cookiesPath").textContent = `${cookies.path} · ${cookies.exists ? `${cookies.size} bytes` : "missing"}`;
  $("cookiesState").textContent = cookies.looksNetscape ? "Valid" : cookies.exists ? "Bad format" : "Missing";
  $("cookiesState").className = cookies.looksNetscape ? "status-good" : "status-bad";
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

async function saveSettings() {
  state.config.autoSync = $("autoSync").checked;
  state.config.intervalHours = Number($("intervalHours").value || 6);
  state.config.playlistEnd = Number($("playlistEnd").value || 0);
  state.config.sleepSeconds = Number($("sleepSeconds").value || 0);
  state.config.formatSelector = $("formatSelector").value || "bv*+ba/b";
  state.config.outputTemplate = $("outputTemplate").value;
  await saveFullConfig();
  await loadStatus();
  toast("Settings saved");
}

function bindEvents() {
  $("channelForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    await api("/api/channels", {
      method: "POST",
      body: JSON.stringify({
        url: $("channelUrl").value,
        label: $("channelLabel").value,
      }),
    });
    $("channelUrl").value = "";
    $("channelLabel").value = "";
    await loadConfig();
    toast("Channel added");
  });

  $("saveSettings").addEventListener("click", saveSettings);

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

  $("refreshLogs").addEventListener("click", loadLogs);

  $("saveCookies").addEventListener("click", async () => {
    await api("/api/cookies", {
      method: "POST",
      body: JSON.stringify({ content: $("cookiesText").value }),
    });
    $("cookiesText").value = "";
    await loadStatus();
    toast("Cookies saved");
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
