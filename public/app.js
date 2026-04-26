const messagesEl = document.querySelector("#messages");
const tasksEl = document.querySelector("#tasks");
const taskCountEl = document.querySelector("#taskCount");
const remoteHostEl = document.querySelector("#remoteHost");
const disconnectButton = document.querySelector("#disconnectButton");
const statusButton = document.querySelector("#statusButton");
const connectionGate = document.querySelector("#connectionGate");
const connectionForm = document.querySelector("#connectionForm");
const connectionHost = document.querySelector("#connectionHost");
const connectionUser = document.querySelector("#connectionUser");
const connectionPort = document.querySelector("#connectionPort");
const authMethod = document.querySelector("#authMethod");
const passwordField = document.querySelector("#passwordField");
const keyPathField = document.querySelector("#keyPathField");
const connectionPassword = document.querySelector("#connectionPassword");
const connectionKeyPath = document.querySelector("#connectionKeyPath");
const rememberConnection = document.querySelector("#rememberConnection");
const togglePasswordButton = document.querySelector("#togglePasswordButton");
const connectionTestButton = document.querySelector("#connectionTestButton");
const connectionConnectButton = document.querySelector("#connectionConnectButton");
const connectionFeedback = document.querySelector("#connectionFeedback");
const recentConnections = document.querySelector("#recentConnections");
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
const terminalViewport = document.querySelector("#terminalViewport");
const terminalInput = document.querySelector("#terminalInput");
const terminalOpenButton = document.querySelector("#terminalOpenButton");
const terminalClearButton = document.querySelector("#terminalClearButton");
const terminalCloseButton = document.querySelector("#terminalCloseButton");
const terminalSendButton = document.querySelector("#terminalSendButton");

let state = {
  messages: [],
  tasks: [],
  remoteHost: "remote-linux",
  apps: [],
  youtubeResults: [],
  media: null,
  terminalOpen: false,
  connected: false,
  connectionInfo: { host: "", username: "", port: 22, authMethod: "password", keyPath: "", remember: true },
  recentConnections: [],
};
let apps = [];
let videoResults = [];
let mediaPoll = null;
let terminalPoll = null;
let terminalBuffer = "";

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
  remoteHostEl.textContent = state.connected ? (state.remoteHost || "linux remoto") : "sin conexion";
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
  renderTerminalState();
  renderConnectionGate();
  renderRecentConnections();
}

async function loadState() {
  const response = await fetch("/api/state");
  state = await response.json();
  syncConnectionForm(true);
  setConnectionFeedback("");
  render();
}

function appendLocalMessage(content) {
  state.messages.push({ role: "assistant", content });
  renderMessages();
}

function connectionPayload() {
  return {
    host: connectionHost.value.trim(),
    username: connectionUser.value.trim(),
    port: Number(connectionPort.value || 22),
    authMethod: authMethod.value,
    password: connectionPassword.value,
    keyPath: connectionKeyPath.value.trim(),
    remember: rememberConnection.checked,
  };
}

function setConnectionFeedback(text, isError = false) {
  connectionFeedback.textContent = text || "";
  connectionFeedback.dataset.error = isError ? "1" : "0";
}

function syncConnectionForm(force = false) {
  const info = state.connectionInfo || {};
  if (force || !connectionHost.value.trim()) connectionHost.value = info.host || "";
  if (force || !connectionUser.value.trim()) connectionUser.value = info.username || "";
  if (force || !connectionPort.value) connectionPort.value = String(info.port || 22);
  authMethod.value = info.authMethod || "password";
  if (force || !connectionKeyPath.value.trim()) connectionKeyPath.value = info.keyPath || "";
  rememberConnection.checked = info.remember !== false;
  toggleAuthFields();
}

function renderConnectionGate() {
  connectionGate.dataset.connected = state.connected ? "1" : "0";
  disconnectButton.hidden = !state.connected;
  if (!state.connected) {
    syncConnectionForm();
  }
}

function renderRecentConnections() {
  const items = state.recentConnections || [];
  if (!items.length) {
    recentConnections.innerHTML = `<p class="empty">Todavia no hay equipos guardados.</p>`;
    return;
  }
  recentConnections.innerHTML = items
    .map(
      (item, index) => `
        <button class="recent-item" type="button" data-recent-index="${index}">
          <strong>${escapeHtml(item.username)}@${escapeHtml(item.host)}</strong>
          <small>Puerto ${escapeHtml(String(item.port || 22))} - ${escapeHtml(item.authMethod === "key" ? "Llave SSH" : "Contrasena")}</small>
        </button>
      `
    )
    .join("");
  recentConnections.querySelectorAll("[data-recent-index]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = state.recentConnections[Number(button.dataset.recentIndex)];
      if (!item) return;
      connectionHost.value = item.host || "";
      connectionUser.value = item.username || "";
      connectionPort.value = String(item.port || 22);
      authMethod.value = item.authMethod || "password";
      connectionKeyPath.value = item.keyPath || "";
      rememberConnection.checked = item.remember !== false;
      connectionPassword.value = "";
      setConnectionFeedback("");
      toggleAuthFields();
    });
  });
}

function toggleAuthFields() {
  const isPassword = authMethod.value === "password";
  passwordField.classList.toggle("hidden", !isPassword);
  keyPathField.classList.toggle("hidden", isPassword);
}

function normalizeTerminal(text) {
  return String(text || "")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .replace(/\u001b\][^\u0007]*(\u0007|\u001b\\)/g, "")
    .replace(/\u001b\[[0-9;?]*[A-Za-z]/g, "")
    .replace(/\u001b./g, "")
    .replace(/\u0008/g, "");
}

function appendTerminalOutput(text) {
  const clean = normalizeTerminal(text);
  if (!clean) return;
  terminalBuffer = `${terminalBuffer}${clean}`.slice(-60000);
  terminalViewport.textContent = terminalBuffer;
  terminalViewport.scrollTop = terminalViewport.scrollHeight;
}

function renderTerminalState() {
  terminalViewport.dataset.open = state.terminalOpen ? "1" : "0";
  terminalInput.disabled = !state.terminalOpen;
  terminalSendButton.disabled = !state.terminalOpen;
  terminalCloseButton.disabled = !state.terminalOpen;
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

async function terminalAction(action, payload = {}, button = null) {
  if (button) button.disabled = true;
  try {
    const response = await fetch(`/api/remote/${action}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Error desconocido");
    state = { ...state, ...data };
    if (data.terminal?.output) appendTerminalOutput(data.terminal.output);
    if (typeof data.terminal?.open === "boolean") state.terminalOpen = data.terminal.open;
    render();
  } catch (error) {
    appendLocalMessage(`No pude usar la terminal remota: ${error.message}`);
  } finally {
    if (button) button.disabled = false;
  }
}

async function connectionAction(action, payload = {}, button = null) {
  if (button) button.disabled = true;
  try {
    const response = await fetch(`/api/remote/${action}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Error desconocido");
    state = { ...state, ...data };
    setConnectionFeedback(data.result?.reply || "");
    if (action === "connection-connect") {
      connectionPassword.value = "";
    }
    if (action === "connection-disconnect") {
      terminalBuffer = "";
      terminalViewport.textContent = "";
      connectionPassword.value = "";
    }
    render();
  } catch (error) {
    setConnectionFeedback(error.message, true);
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

authMethod.addEventListener("change", toggleAuthFields);

togglePasswordButton.addEventListener("click", () => {
  const visible = connectionPassword.type === "text";
  connectionPassword.type = visible ? "password" : "text";
  togglePasswordButton.textContent = visible ? "Mostrar" : "Ocultar";
});

connectionTestButton.addEventListener("click", () => {
  setConnectionFeedback("");
  connectionAction("connection-test", connectionPayload(), connectionTestButton);
});

connectionForm.addEventListener("submit", (event) => {
  event.preventDefault();
  setConnectionFeedback("");
  connectionAction("connection-connect", connectionPayload(), connectionConnectButton);
});

disconnectButton.addEventListener("click", () => {
  connectionAction("connection-disconnect", {}, disconnectButton);
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

function terminalRows() {
  return Math.max(12, Math.floor(terminalViewport.clientHeight / 19));
}

function terminalCols() {
  return Math.max(40, Math.floor(terminalViewport.clientWidth / 8.8));
}

async function pollTerminal() {
  if (!state.connected || !state.terminalOpen) return;
  await terminalAction("terminal-read");
}

async function sendTerminalText(text, clearInput = false) {
  if (!text) return;
  await terminalAction("terminal-write", { text });
  if (clearInput) terminalInput.value = "";
}

terminalOpenButton.addEventListener("click", async () => {
  terminalViewport.focus();
  await terminalAction("terminal-open", { cols: terminalCols(), rows: terminalRows() }, terminalOpenButton);
});

terminalClearButton.addEventListener("click", () => {
  terminalBuffer = "";
  terminalViewport.textContent = "";
  terminalViewport.focus();
});

terminalCloseButton.addEventListener("click", async () => {
  await terminalAction("terminal-close", {}, terminalCloseButton);
});

terminalSendButton.addEventListener("click", () => sendTerminalText(`${terminalInput.value}\n`, true));

terminalInput.addEventListener("keydown", async (event) => {
  if (!state.terminalOpen) return;
  if (event.key === "Enter") {
    event.preventDefault();
    await sendTerminalText(`${terminalInput.value}\n`, true);
    return;
  }
  if (event.key === "ArrowUp") {
    event.preventDefault();
    await sendTerminalText("\u001b[A");
    return;
  }
  if (event.key === "ArrowDown") {
    event.preventDefault();
    await sendTerminalText("\u001b[B");
    return;
  }
  if (event.key === "Tab") {
    event.preventDefault();
    await sendTerminalText("\t");
    return;
  }
  if (event.ctrlKey && event.key.toLowerCase() === "c") {
    event.preventDefault();
    await sendTerminalText("\u0003");
    return;
  }
  if (event.ctrlKey && event.key.toLowerCase() === "l") {
    event.preventDefault();
    terminalBuffer = "";
    terminalViewport.textContent = "";
    await sendTerminalText("\u000c");
  }
});

terminalViewport.addEventListener("click", () => terminalInput.focus());

terminalViewport.addEventListener("keydown", async (event) => {
  if (!state.terminalOpen) return;
  if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
    event.preventDefault();
    await sendTerminalText(event.key);
    return;
  }
  if (event.key === "Enter") {
    event.preventDefault();
    await sendTerminalText("\n");
    return;
  }
  if (event.key === "Backspace") {
    event.preventDefault();
    await sendTerminalText("\u007f");
    return;
  }
  if (event.key === "Tab") {
    event.preventDefault();
    await sendTerminalText("\t");
    return;
  }
  if (event.key === "ArrowUp") {
    event.preventDefault();
    await sendTerminalText("\u001b[A");
    return;
  }
  if (event.key === "ArrowDown") {
    event.preventDefault();
    await sendTerminalText("\u001b[B");
    return;
  }
  if (event.key === "ArrowLeft") {
    event.preventDefault();
    await sendTerminalText("\u001b[D");
    return;
  }
  if (event.key === "ArrowRight") {
    event.preventDefault();
    await sendTerminalText("\u001b[C");
    return;
  }
  if (event.ctrlKey && event.key.toLowerCase() === "c") {
    event.preventDefault();
    await sendTerminalText("\u0003");
    return;
  }
  if (event.ctrlKey && event.key.toLowerCase() === "l") {
    event.preventDefault();
    terminalBuffer = "";
    terminalViewport.textContent = "";
    await sendTerminalText("\u000c");
  }
});

document.querySelectorAll("[data-terminal-seq]").forEach((button) => {
  button.addEventListener("click", () => sendTerminalText(button.dataset.terminalSeq));
});

window.addEventListener("resize", () => {
  if (!state.terminalOpen) return;
  terminalAction("terminal-resize", { cols: terminalCols(), rows: terminalRows() });
});

loadState();
mediaPoll = setInterval(() => {
  if (!state.connected) return;
  runAction("media-status");
}, 12000);
terminalPoll = setInterval(pollTerminal, 900);
