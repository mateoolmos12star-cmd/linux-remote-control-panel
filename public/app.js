const messagesEl = document.querySelector("#messages");
const tasksEl = document.querySelector("#tasks");
const taskCountEl = document.querySelector("#taskCount");
const remoteHostEl = document.querySelector("#remoteHost");
const statusButton = document.querySelector("#statusButton");
const urlForm = document.querySelector("#urlForm");
const urlInput = document.querySelector("#urlInput");
const youtubeSearchForm = document.querySelector("#youtubeSearchForm");
const youtubeSearchInput = document.querySelector("#youtubeSearchInput");
const youtubeResults = document.querySelector("#youtubeResults");
const refreshAppsButton = document.querySelector("#refreshAppsButton");
const appSearch = document.querySelector("#appSearch");
const appsList = document.querySelector("#appsList");
const mediaRefreshButton = document.querySelector("#mediaRefreshButton");
const mediaTitle = document.querySelector("#mediaTitle");
const mediaMeta = document.querySelector("#mediaMeta");
const mediaCurrent = document.querySelector("#mediaCurrent");
const mediaDuration = document.querySelector("#mediaDuration");
const mediaSeek = document.querySelector("#mediaSeek");
const screenshotButton = document.querySelector("#screenshotButton");
const remoteScreen = document.querySelector("#remoteScreen");
const remoteText = document.querySelector("#remoteText");
const typeTextButton = document.querySelector("#typeTextButton");
const windowsList = document.querySelector("#windowsList");
const filesForm = document.querySelector("#filesForm");
const filesPath = document.querySelector("#filesPath");
const filesList = document.querySelector("#filesList");
const refreshFilesButton = document.querySelector("#refreshFilesButton");
const systemInfo = document.querySelector("#systemInfo");
const audioSinks = document.querySelector("#audioSinks");
const commandForm = document.querySelector("#commandForm");
const commandInput = document.querySelector("#commandInput");
const copySource = document.querySelector("#copySource");
const copyDestination = document.querySelector("#copyDestination");
const copyToRemoteButton = document.querySelector("#copyToRemoteButton");
const copyFromRemoteButton = document.querySelector("#copyFromRemoteButton");

let state = { messages: [], tasks: [], remoteHost: "remote-linux", apps: [], youtubeResults: [], media: null };
let apps = [];
let videoResults = [];
let mediaPoll = null;

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => {
    const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" };
    return map[char];
  });
}

function renderMessages() {
  messagesEl.innerHTML = state.messages
    .map((message) => `<article class="message ${message.role}">${escapeHtml(message.content)}</article>`)
    .join("");
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function renderTasks() {
  taskCountEl.textContent = String(state.tasks.length);
  if (!state.tasks.length) {
    tasksEl.innerHTML = `<p class="empty">Sin tareas todavia.</p>`;
    return;
  }
  tasksEl.innerHTML = state.tasks
    .map(
      (task) => `
        <article class="task ${task.status}">
          <strong>${escapeHtml(task.title)}</strong>
          <span>${escapeHtml(task.status)}${task.detail ? ` - ${escapeHtml(task.detail)}` : ""}</span>
        </article>
      `
    )
    .join("");
}

function render() {
  remoteHostEl.textContent = state.remoteHost || "remote-linux";
  renderMessages();
  renderTasks();
  if (state.apps) {
    apps = state.apps;
    renderApps();
  }
  if (state.youtubeResults) {
    videoResults = state.youtubeResults;
    renderVideoResults();
  }
  if (state.media) renderMedia();
  if (state.screen) remoteScreen.src = state.screen;
  if (state.windows) renderWindows();
  if (state.files) renderFiles();
  if (state.system) renderSystem();
  if (state.audioSinks) renderAudioSinks();
}

async function loadState() {
  const response = await fetch("/api/state");
  state = await response.json();
  render();
}

function appendLocalMessage(content) {
  state.messages.push({ role: "assistant", content });
  renderMessages();
}

async function runAction(action, payload = {}, button = null) {
  if (button) button.disabled = true;
  try {
    const response = await fetch(`/api/remote/${action}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Error desconocido");
    state = data;
    if (data.result?.output && action === "status") {
      state.messages.push({ role: "assistant", content: data.result.output });
    }
    render();
  } catch (error) {
    appendLocalMessage(`No pude ejecutar la accion: ${error.message}`);
  } finally {
    if (button) button.disabled = false;
  }
}

function renderApps() {
  const query = appSearch.value.trim().toLowerCase();
  const visible = apps
    .filter((app) => {
      const haystack = `${app.name} ${app.comment || ""} ${app.id}`.toLowerCase();
      return !query || haystack.includes(query);
    })
    .slice(0, 140);

  if (!visible.length) {
    appsList.innerHTML = `<p class="empty">${apps.length ? "Sin coincidencias." : "Carga la lista para abrir cualquier app instalada."}</p>`;
    return;
  }

  appsList.innerHTML = visible
    .map(
      (app) => `
        <button class="app-item" type="button" data-app-id="${escapeHtml(app.id)}">
          <strong>${escapeHtml(app.name)}</strong>
          <span>${escapeHtml(app.comment || app.id)}</span>
        </button>
      `
    )
    .join("");

  appsList.querySelectorAll("[data-app-id]").forEach((button) => {
    button.addEventListener("click", () => runAction("open-app", { appId: button.dataset.appId }, button));
  });
}

function renderVideoResults() {
  if (!videoResults.length) {
    youtubeResults.innerHTML = `<p class="empty">Busca un video para ver resultados y reproducirlo en Linux remoto.</p>`;
    return;
  }
  youtubeResults.innerHTML = videoResults
    .map(
      (video) => `
        <button class="video-item" type="button" data-url="${escapeHtml(video.url)}">
          <img src="${escapeHtml(video.thumbnail)}" alt="" loading="lazy" />
          <span>
            <strong>${escapeHtml(video.title)}</strong>
            <small>${escapeHtml([video.channel, video.duration].filter(Boolean).join(" - "))}</small>
          </span>
        </button>
      `
    )
    .join("");
  youtubeResults.querySelectorAll("[data-url]").forEach((button) => {
    button.addEventListener("click", () => runAction("open-url", { url: button.dataset.url }, button));
  });
}

function formatMicros(value) {
  const seconds = Math.max(0, Math.floor(Number(value || 0) / 1000000));
  const minutes = Math.floor(seconds / 60);
  const rest = String(seconds % 60).padStart(2, "0");
  return `${minutes}:${rest}`;
}

function renderMedia() {
  const media = state.media || {};
  if (!media.available) {
    mediaTitle.textContent = media.title || "Nada reproduciendose";
    mediaMeta.textContent = media.error || "No hay reproductor activo.";
    mediaCurrent.textContent = "0:00";
    mediaDuration.textContent = "0:00";
    mediaSeek.value = 0;
    mediaSeek.max = 0;
    mediaSeek.disabled = true;
    return;
  }
  mediaTitle.textContent = media.title || "Sin titulo";
  mediaMeta.textContent = [media.artist, media.status].filter(Boolean).join(" - ");
  mediaCurrent.textContent = formatMicros(media.position);
  mediaDuration.textContent = formatMicros(media.length);
  mediaSeek.max = String(media.length || 0);
  mediaSeek.value = String(Math.min(media.position || 0, media.length || media.position || 0));
  mediaSeek.disabled = !media.length;
}

function renderWindows() {
  const windows = state.windows || [];
  windowsList.innerHTML = windows.length
    ? windows.map((win) => `
        <article class="list-row">
          <span><strong>${escapeHtml(win.title)}</strong><small>${escapeHtml(win.class || win.id)}</small></span>
          <button data-window-op="focus" data-window-id="${escapeHtml(win.id)}">Foco</button>
          <button data-window-op="minimize" data-window-id="${escapeHtml(win.id)}">Min</button>
          <button data-window-op="close" data-window-id="${escapeHtml(win.id)}">Cerrar</button>
        </article>
      `).join("")
    : `<p class="empty">Sin ventanas detectadas.</p>`;
  windowsList.querySelectorAll("[data-window-op]").forEach((button) => {
    button.addEventListener("click", () => runAction("window-action", { id: button.dataset.windowId, op: button.dataset.windowOp }, button));
  });
}

function renderFiles() {
  const data = state.files || { path: "~", items: [] };
  filesPath.value = data.path || filesPath.value;
  filesList.innerHTML = data.items?.length
    ? data.items.map((item) => `
        <button class="file-row" type="button" data-file-path="${escapeHtml(item.path)}" data-is-dir="${item.isDir ? "1" : "0"}">
          <strong>${item.isDir ? "[DIR] " : ""}${escapeHtml(item.name)}</strong>
          <small>${item.isDir ? "Carpeta" : `${Math.round((item.size || 0) / 1024)} KB`}</small>
        </button>
      `).join("")
    : `<p class="empty">Sin archivos.</p>`;
  filesList.querySelectorAll("[data-file-path]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.isDir === "1") runAction("files", { path: button.dataset.filePath }, button);
      else runAction("open-file", { path: button.dataset.filePath }, button);
    });
  });
}

function renderSystem() {
  const info = state.system || {};
  systemInfo.innerHTML = Object.entries(info).map(([key, value]) => `
    <article><strong>${escapeHtml(key)}</strong><span>${escapeHtml(value || "-")}</span></article>
  `).join("");
}

function renderAudioSinks() {
  const sinks = state.audioSinks || [];
  audioSinks.innerHTML = sinks.length
    ? sinks.map((sink) => `
        <button class="file-row" type="button" data-sink="${escapeHtml(sink.name)}">
          <strong>${escapeHtml(sink.name)}</strong>
          <small>${escapeHtml(sink.state || sink.id)}</small>
        </button>
      `).join("")
    : "";
  audioSinks.querySelectorAll("[data-sink]").forEach((button) => {
    button.addEventListener("click", () => runAction("set-sink", { sink: button.dataset.sink }, button));
  });
}

document.querySelectorAll("[data-action]").forEach((button) => {
  button.addEventListener("click", () => runAction(button.dataset.action, {}, button));
});

statusButton.addEventListener("click", () => runAction("status", {}, statusButton));
refreshAppsButton.addEventListener("click", () => runAction("apps", {}, refreshAppsButton));
appSearch.addEventListener("input", renderApps);
mediaRefreshButton.addEventListener("click", () => runAction("media-status", {}, mediaRefreshButton));

mediaSeek.addEventListener("change", () => {
  if (mediaSeek.disabled) return;
  runAction("media-seek", { position: mediaSeek.value });
});

urlForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const url = urlInput.value.trim();
  if (!url) return;
  urlInput.value = "";
  runAction("open-url", { url });
});

youtubeSearchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = youtubeSearchInput.value.trim();
  if (!query) return;
  runAction("youtube-search", { query }, youtubeSearchForm.querySelector("button"));
});

screenshotButton.addEventListener("click", () => runAction("screenshot", {}, screenshotButton));

remoteScreen.addEventListener("click", (event) => {
  if (!remoteScreen.naturalWidth || !remoteScreen.naturalHeight) return;
  const rect = remoteScreen.getBoundingClientRect();
  const x = Math.round((event.clientX - rect.left) * (remoteScreen.naturalWidth / rect.width));
  const y = Math.round((event.clientY - rect.top) * (remoteScreen.naturalHeight / rect.height));
  runAction("click", { x, y });
});

typeTextButton.addEventListener("click", () => {
  const text = remoteText.value;
  if (!text) return;
  remoteText.value = "";
  runAction("type-text", { text }, typeTextButton);
});

document.querySelectorAll("[data-shortcut]").forEach((button) => {
  button.addEventListener("click", () => runAction("shortcut", { name: button.dataset.shortcut }, button));
});

filesForm.addEventListener("submit", (event) => {
  event.preventDefault();
  runAction("files", { path: filesPath.value || "~" }, refreshFilesButton);
});

refreshFilesButton.addEventListener("click", () => runAction("files", { path: filesPath.value || "~" }, refreshFilesButton));

commandForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = commandInput.value.trim();
  if (!text) return;
  commandInput.value = "";
  runAction("command", { text }, commandForm.querySelector("button"));
});

copyToRemoteButton.addEventListener("click", () => {
  runAction("copy-to-remote", { source: copySource.value, destination: copyDestination.value }, copyToRemoteButton);
});

copyFromRemoteButton.addEventListener("click", () => {
  runAction("copy-from-remote", { source: copySource.value, destination: copyDestination.value }, copyFromRemoteButton);
});

loadState();
mediaPoll = setInterval(() => runAction("media-status"), 12000);
