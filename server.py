from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import json
import os
import re
import shlex
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

import paramiko


ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
CONNECTIONS_FILE = ROOT / "connections.json"
PORT = int(os.environ.get("REMOTE_PANEL_PORT") or os.environ.get("ENDEAVOUR_PANEL_PORT") or "8787")
REMOTE_HOST = os.environ.get("REMOTE_SSH_HOST") or os.environ.get("ENDEAVOUR_SSH_HOST") or "endeavour"
REMOTE_DISPLAY = os.environ.get("REMOTE_DISPLAY", ":0")
REMOTE_XAUTHORITY = os.environ.get("REMOTE_XAUTHORITY", "/tmp/xauth_OvomTp")
REMOTE_XDG_RUNTIME_DIR = os.environ.get("REMOTE_XDG_RUNTIME_DIR", "/run/user/1000")
REMOTE_DBUS_SESSION_BUS_ADDRESS = os.environ.get(
    "REMOTE_DBUS_SESSION_BUS_ADDRESS",
    f"unix:path={REMOTE_XDG_RUNTIME_DIR}/bus",
)
SSH_CONTROL_PATH = os.environ.get("ENDEAVOUR_SSH_CONTROL_PATH", "")
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def hidden_startupinfo():
    if os.name != "nt":
        return None
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return startupinfo


def ssh_config_for(host):
    host = (host or "").strip()
    if not host:
        return {}
    config_path = Path.home() / ".ssh" / "config"
    if not config_path.exists():
        return {"hostname": host, "user": os.environ.get("USERNAME")}
    config = paramiko.SSHConfig()
    with config_path.open("r", encoding="utf-8") as handle:
        config.parse(handle)
    data = config.lookup(host)
    data.setdefault("hostname", host)
    return data


def default_connection():
    data = ssh_config_for(REMOTE_HOST)
    identity_files = data.get("identityfile") or []
    key_path = str(Path(os.path.expanduser(identity_files[0]))) if identity_files else ""
    return {
        "host": REMOTE_HOST,
        "username": data.get("user") or "",
        "port": int(data.get("port", 22) or 22),
        "authMethod": "key" if key_path else "password",
        "keyPath": key_path,
        "remember": True,
        "connected": False,
        "password": "",
    }


def sanitize_connection(connection):
    connection = connection or {}
    return {
        "host": str(connection.get("host", "")).strip(),
        "username": str(connection.get("username", "")).strip(),
        "port": int(connection.get("port", 22) or 22),
        "authMethod": str(connection.get("authMethod", "password")),
        "keyPath": str(connection.get("keyPath", "")).strip(),
        "remember": bool(connection.get("remember", True)),
        "connected": bool(connection.get("connected", False)),
    }


def load_recent_connections():
    if not CONNECTIONS_FILE.exists():
        return []
    try:
        data = json.loads(CONNECTIONS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    recent = []
    for item in data[:8]:
        if not isinstance(item, dict):
            continue
        safe = sanitize_connection(item)
        safe["connected"] = False
        recent.append(safe)
    return recent


def save_recent_connections():
    payload = []
    for item in recent_connections[:8]:
        safe = sanitize_connection(item)
        safe["connected"] = False
        payload.append(safe)
    CONNECTIONS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def remember_connection(connection):
    safe = sanitize_connection(connection)
    safe["connected"] = False
    recent_connections[:] = [
        item
        for item in recent_connections
        if not (
            item.get("host", "").lower() == safe["host"].lower()
            and item.get("username", "").lower() == safe["username"].lower()
            and int(item.get("port", 22)) == safe["port"]
        )
    ]
    recent_connections.insert(0, safe)
    del recent_connections[8:]
    save_recent_connections()


def resolve_connection(connection):
    safe = sanitize_connection(connection)
    if not safe["host"]:
        raise RuntimeError("Debes escribir una IP o hostname.")
    if not safe["username"]:
        raise RuntimeError("Debes escribir el usuario SSH.")
    data = ssh_config_for(safe["host"])
    hostname = data.get("hostname", safe["host"])
    port = safe["port"] or int(data.get("port", 22) or 22)
    key_path = safe["keyPath"]
    if not key_path:
        identity_files = data.get("identityfile") or []
        if identity_files:
            key_path = str(Path(os.path.expanduser(identity_files[0])))
    password = str(connection.get("password", "") or "")
    return {
        "host": safe["host"],
        "hostname": hostname,
        "username": safe["username"],
        "port": int(port),
        "authMethod": safe["authMethod"],
        "keyPath": key_path,
        "remember": safe["remember"],
        "connected": safe["connected"],
        "password": password,
    }


def connection_key(connection=None):
    safe = sanitize_connection(connection or current_connection)
    return f"{safe['username']}@{safe['host']}:{safe['port']}"


def paramiko_client(connection=None):
    resolved = resolve_connection(connection or current_connection)
    key_filename = [resolved["keyPath"]] if resolved["keyPath"] else None
    use_key = resolved["authMethod"] == "key"
    password = resolved["password"] if resolved["authMethod"] == "password" else None
    if resolved["authMethod"] == "password" and not password:
        raise RuntimeError("Debes escribir la contrasena SSH.")
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=resolved["hostname"],
        port=resolved["port"],
        username=resolved["username"],
        password=password or None,
        key_filename=key_filename or None,
        look_for_keys=use_key,
        allow_agent=use_key,
        timeout=8,
        banner_timeout=8,
        auth_timeout=8,
    )
    return client


messages = [
    {
        "role": "assistant",
        "content": "Panel listo para controlar la computadora Linux remota.",
    }
]
tasks = []
terminal_sessions = {}
terminal_sessions_lock = threading.Lock()
current_connection = default_connection()
recent_connections = load_recent_connections()


def now():
    return datetime.now(timezone.utc).isoformat()


def json_response(handler, status, payload):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json; charset=utf-8")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler):
    length = int(handler.headers.get("content-length", "0"))
    body = handler.rfile.read(length).decode("utf-8") if length else "{}"
    return json.loads(body or "{}")


def add_task(title, task_type):
    task = {
        "id": str(uuid.uuid4()),
        "title": title,
        "type": task_type,
        "status": "running",
        "createdAt": now(),
        "finishedAt": None,
        "detail": "",
    }
    tasks.insert(0, task)
    return task


def state_payload(extra=None):
    payload = {
        "messages": messages,
        "tasks": tasks,
        "remoteHost": current_connection.get("host", "") or "sin conexion",
        "terminalOpen": False,
        "connected": bool(current_connection.get("connected", False)),
        "connectionInfo": sanitize_connection(current_connection),
        "recentConnections": recent_connections,
    }
    with terminal_sessions_lock:
        key = connection_key()
        payload["terminalOpen"] = payload["connected"] and key in terminal_sessions and terminal_sessions[key].alive
    if extra:
        payload.update(extra)
    return payload


def ssh_raw(command, input_text=None, timeout=15, batch=True):
    if not current_connection.get("connected"):
        return subprocess.CompletedProcess(command, 255, "", "No hay conexion SSH activa.")
    try:
        with paramiko_client() as client:
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            if input_text is not None:
                stdin.write(input_text)
                stdin.channel.shutdown_write()
            exit_status = stdout.channel.recv_exit_status()
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            return subprocess.CompletedProcess(command, exit_status, out, err)
    except Exception as exc:
        return subprocess.CompletedProcess(command, 255, "", str(exc))


def ssh(command, input_text=None, timeout=15):
    completed = ssh_raw(command, input_text=input_text, timeout=timeout, batch=True)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "SSH remoto fallo").strip())
    return completed.stdout.strip()


def shell_export(name, value):
    return f"export {name}={shlex.quote(str(value))}; "


def gui_prefix(command):
    return (
        shell_export("DISPLAY", REMOTE_DISPLAY)
        + shell_export("XAUTHORITY", REMOTE_XAUTHORITY)
        + shell_export("XDG_RUNTIME_DIR", REMOTE_XDG_RUNTIME_DIR)
        + shell_export("DBUS_SESSION_BUS_ADDRESS", REMOTE_DBUS_SESSION_BUS_ADDRESS)
        + f"{command}"
    )


def remote_session_env():
    return {
        "XDG_RUNTIME_DIR": REMOTE_XDG_RUNTIME_DIR,
        "DBUS_SESSION_BUS_ADDRESS": REMOTE_DBUS_SESSION_BUS_ADDRESS,
    }


def desktop_shortcut():
    if os.name != "nt":
        raise RuntimeError("La creacion del acceso directo desde el panel esta disponible solo en Windows.")
    desktop = Path.home() / "Desktop"
    shortcut = desktop / "Linux Remote Control Panel.lnk"
    target = ROOT / "launch-endeavour-panel.vbs"
    icon = ROOT / "tux.ico"
    if not target.exists():
        raise RuntimeError("No encontre el lanzador del panel para crear el acceso directo.")
    powershell = f"""
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut({str(shortcut)!r})
$shortcut.TargetPath = {str(target)!r}
$shortcut.WorkingDirectory = {str(ROOT)!r}
$shortcut.Description = 'Abrir Linux Remote Control Panel'
if (Test-Path -LiteralPath {str(icon)!r}) {{
  $shortcut.IconLocation = {f'{icon},0'!r}
}}
$shortcut.Save()
"""
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            powershell,
        ],
        capture_output=True,
        text=True,
        timeout=15,
        startupinfo=hidden_startupinfo(),
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "No pude crear el acceso directo.").strip())
    return state_payload({"result": {"reply": f"Acceso directo creado en {shortcut}"}})


def close_terminal_sessions():
    with terminal_sessions_lock:
        sessions = list(terminal_sessions.values())
        terminal_sessions.clear()
    for session in sessions:
        try:
            session.close()
        except Exception:
            pass


def connect_payload(body):
    body = body or {}
    connection = {
        "host": str(body.get("host", "")).strip(),
        "username": str(body.get("username", "")).strip(),
        "port": int(str(body.get("port", "22") or "22")),
        "authMethod": str(body.get("authMethod", "password")).strip().lower(),
        "keyPath": str(body.get("keyPath", "")).strip(),
        "remember": bool(body.get("remember", True)),
        "password": str(body.get("password", "")),
        "connected": False,
    }
    if connection["authMethod"] not in {"password", "key"}:
        raise RuntimeError("Metodo de acceso no soportado.")
    return connection


def test_connection(connection):
    resolved = resolve_connection(connection)
    with paramiko_client(resolved) as client:
        stdin, stdout, stderr = client.exec_command("hostname", timeout=8)
        hostname = stdout.read().decode("utf-8", errors="replace").strip() or resolved["hostname"]
        error_text = stderr.read().decode("utf-8", errors="replace").strip()
        if error_text and not hostname:
            raise RuntimeError(error_text)
    return hostname


def connection_test(body):
    connection = connect_payload(body)
    hostname = test_connection(connection)
    return state_payload(
        {
            "result": {
                "reply": f"Conexion correcta con {hostname}.",
                "connectionHost": hostname,
            }
        }
    )


def connection_connect(body):
    global current_connection
    connection = connect_payload(body)
    hostname = test_connection(connection)
    close_terminal_sessions()
    connection["connected"] = True
    current_connection = connection
    if connection.get("remember"):
        remember_connection(connection)
    messages.append(
        {
            "role": "assistant",
            "content": f"Conexion SSH activa con {connection['host']} ({hostname}).",
        }
    )
    return state_payload({"result": {"reply": f"Conectado a {connection['host']}."}})


def connection_disconnect():
    global current_connection
    close_terminal_sessions()
    remembered = sanitize_connection(current_connection)
    remembered["connected"] = False
    remembered["password"] = ""
    current_connection = remembered
    messages.append({"role": "assistant", "content": "Conexion SSH cerrada."})
    return state_payload({"terminal": {"open": False, "output": ""}, "result": {"reply": "Conexion cerrada."}})


class TerminalSession:
    def __init__(self, connection):
        self.connection = sanitize_connection(connection)
        self.client = paramiko_client()
        self.channel = self.client.invoke_shell(term="xterm-256color", width=120, height=34)
        self.channel.settimeout(0.0)
        self.buffer = ""
        self.lock = threading.Lock()
        self.alive = True
        self.last_used_at = time.time()
        time.sleep(0.15)
        self._pump()

    def _pump(self):
        if not self.alive:
            return ""
        chunks = []
        while self.channel.recv_ready():
            data = self.channel.recv(4096)
            if not data:
                self.alive = False
                break
            chunks.append(data.decode("utf-8", errors="replace"))
        if self.channel.closed or self.channel.exit_status_ready():
            self.alive = False
        if chunks:
            text = "".join(chunks)
            self.buffer += text
            self.last_used_at = time.time()
            return text
        return ""

    def read(self):
        with self.lock:
            self._pump()
            text = self.buffer
            self.buffer = ""
            return text

    def write(self, text):
        with self.lock:
            if not self.alive:
                raise RuntimeError("La terminal remota ya no esta activa.")
            self.channel.send(text)
            self.last_used_at = time.time()
            return self._pump()

    def resize(self, cols, rows):
        with self.lock:
            if not self.alive:
                return
            self.channel.resize_pty(width=max(40, int(cols)), height=max(12, int(rows)))
            self.last_used_at = time.time()

    def close(self):
        with self.lock:
            if self.alive:
                try:
                    self.channel.close()
                except Exception:
                    pass
                try:
                    self.client.close()
                except Exception:
                    pass
            self.alive = False


def get_terminal_session(create=False):
    if not current_connection.get("connected"):
        return None
    key = connection_key()
    with terminal_sessions_lock:
        session = terminal_sessions.get(key)
        if session and not session.alive:
            session.close()
            terminal_sessions.pop(key, None)
            session = None
        if not session and create:
            session = TerminalSession(current_connection)
            terminal_sessions[key] = session
        return session


def terminal_open(cols=120, rows=34):
    session = get_terminal_session(create=True)
    if not session:
        raise RuntimeError("No hay conexion SSH activa.")
    session.resize(cols, rows)
    output = session.read()
    return state_payload({"terminal": {"open": True, "output": output}})


def terminal_read():
    session = get_terminal_session(create=False)
    if not session:
        return state_payload({"terminal": {"open": False, "output": ""}})
    return state_payload({"terminal": {"open": session.alive, "output": session.read()}})


def terminal_write(text):
    session = get_terminal_session(create=True)
    if not session:
        raise RuntimeError("No hay conexion SSH activa.")
    output = session.write(text)
    return state_payload({"terminal": {"open": session.alive, "output": output}})


def terminal_resize(cols, rows):
    session = get_terminal_session(create=False)
    if session:
        session.resize(cols, rows)
    return state_payload({"terminal": {"open": bool(session and session.alive), "output": ""}})


def terminal_close():
    with terminal_sessions_lock:
        session = terminal_sessions.pop(REMOTE_HOST, None)
    if session:
        session.close()
    return state_payload({"terminal": {"open": False, "output": ""}, "result": {"reply": "Terminal remota cerrada."}})


def firefox_open_command(url):
    quoted_url = shlex.quote(url)
    return gui_prefix(
        "pkill -x firefox || true; "
        "sleep 1; "
        f"nohup firefox {quoted_url} >/tmp/codex-firefox-url.log 2>&1 &"
    )


def screenshot():
    command = gui_prefix(
        "xfce4-screenshooter -f -s /tmp/codex-screen.jpg >/tmp/codex-shot.log 2>&1 && "
        "base64 -w 0 /tmp/codex-screen.jpg"
    )
    image = ssh(command, timeout=20)
    return state_payload({"screen": f"data:image/jpeg;base64,{image}", "result": {"reply": "Captura actualizada."}})


def x11_pointer_script(x, y, click=False):
    return f"""
import ctypes
import time
x11 = ctypes.CDLL("libX11.so.6")
xtst = ctypes.CDLL("libXtst.so.6")
x11.XOpenDisplay.restype = ctypes.c_void_p
x11.XDefaultScreen.argtypes = [ctypes.c_void_p]
x11.XDefaultScreen.restype = ctypes.c_int
x11.XFlush.argtypes = [ctypes.c_void_p]
xtst.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
xtst.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
display = x11.XOpenDisplay(None)
if not display:
    raise SystemExit("No pude abrir DISPLAY")
screen = x11.XDefaultScreen(display)
xtst.XTestFakeMotionEvent(display, screen, int({x}), int({y}), 0)
x11.XFlush(display)
time.sleep(0.08)
if {str(bool(click))}:
    xtst.XTestFakeButtonEvent(display, 1, 1, 0)
    xtst.XTestFakeButtonEvent(display, 1, 0, 0)
    x11.XFlush(display)
print("pointer-ok")
"""


def click_remote(x, y):
    script = x11_pointer_script(int(x), int(y), click=True)
    return state_payload({"result": run_task("Click remoto", "remote_pointer", gui_prefix("cat > /tmp/codex_pointer.py && python /tmp/codex_pointer.py"), input_text=script, timeout=12)})


def type_text(text):
    script = f"""
import ctypes
import time
x11 = ctypes.CDLL("libX11.so.6")
xtst = ctypes.CDLL("libXtst.so.6")
x11.XOpenDisplay.restype = ctypes.c_void_p
x11.XStringToKeysym.argtypes = [ctypes.c_char_p]
x11.XStringToKeysym.restype = ctypes.c_ulong
x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
x11.XKeysymToKeycode.restype = ctypes.c_uint
x11.XFlush.argtypes = [ctypes.c_void_p]
xtst.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
display = x11.XOpenDisplay(None)
if not display:
    raise SystemExit("No pude abrir DISPLAY")
shift = x11.XKeysymToKeycode(display, 0xFFE1)
special = {{
    "\\n": "Return", "\\t": "Tab", " ": "space", ".": "period", ",": "comma",
    "/": "slash", "-": "minus", "_": "underscore", ":": "colon", ";": "semicolon",
    "@": "at", "#": "numbersign", "&": "ampersand", "?": "question", "!": "exclam",
    "(": "parenleft", ")": "parenright", "'": "apostrophe", '"': "quotedbl",
}}
text = {json.dumps(text[:800])}
for char in text:
    name = special.get(char, char)
    keysym = x11.XStringToKeysym(name.encode())
    if not keysym:
        continue
    keycode = x11.XKeysymToKeycode(display, keysym)
    needs_shift = char.isupper() or char in "_:?!)@#&\\\""
    if needs_shift:
        xtst.XTestFakeKeyEvent(display, shift, 1, 0)
    xtst.XTestFakeKeyEvent(display, keycode, 1, 0)
    xtst.XTestFakeKeyEvent(display, keycode, 0, 0)
    if needs_shift:
        xtst.XTestFakeKeyEvent(display, shift, 0, 0)
    x11.XFlush(display)
    time.sleep(0.015)
print("typed")
"""
    return state_payload({"result": run_task("Escribir texto remoto", "remote_keyboard", gui_prefix("cat > /tmp/codex_type.py && python /tmp/codex_type.py"), input_text=script, timeout=15)})


def list_windows():
    script = r"""
import json
import re
import subprocess

def run(args):
    return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL).strip()
root = run(["xprop", "-root", "_NET_CLIENT_LIST"])
ids = re.findall(r"0x[0-9a-fA-F]+", root)
windows = []
for wid in ids:
    try:
        props = run(["xprop", "-id", wid, "_NET_WM_NAME", "WM_NAME", "WM_CLASS"])
    except Exception:
        continue
    title = ""
    wm_name = re.search(r'_NET_WM_NAME\(UTF8_STRING\) = "(.*?)"', props)
    if not wm_name:
        wm_name = re.search(r'WM_NAME\(\w+\) = "(.*?)"', props)
    if wm_name:
        title = wm_name.group(1)
    klass = ""
    match = re.search(r'WM_CLASS\(\w+\) = (.*)', props)
    if match:
        klass = match.group(1).replace('"', '')
    if title:
        windows.append({"id": wid, "title": title, "class": klass})
print(json.dumps(windows))
"""
    output = ssh(gui_prefix("cat > /tmp/codex_windows.py && python /tmp/codex_windows.py"), input_text=script, timeout=12)
    return json.loads(output or "[]")


def window_op_script(window_id, op):
    return f"""
import ctypes
x11 = ctypes.CDLL("libX11.so.6")
x11.XOpenDisplay.restype = ctypes.c_void_p
x11.XRaiseWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
x11.XSetInputFocus.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
x11.XIconifyWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int]
x11.XKillClient.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
x11.XDefaultScreen.argtypes = [ctypes.c_void_p]
x11.XDefaultScreen.restype = ctypes.c_int
x11.XFlush.argtypes = [ctypes.c_void_p]
display = x11.XOpenDisplay(None)
if not display:
    raise SystemExit("No pude abrir DISPLAY")
window = int("{window_id}", 16)
screen = x11.XDefaultScreen(display)
op = {json.dumps(op)}
if op == "focus":
    x11.XRaiseWindow(display, window)
    x11.XSetInputFocus(display, window, 1, 0)
elif op == "minimize":
    x11.XIconifyWindow(display, window, screen)
elif op == "close":
    x11.XKillClient(display, window)
x11.XFlush(display)
print("window-ok")
"""


def window_action(window_id, op):
    if not re.match(r"^0x[0-9a-fA-F]+$", window_id):
        raise RuntimeError("ID de ventana invalido")
    if op not in {"focus", "minimize", "close"}:
        raise RuntimeError("Operacion de ventana no soportada")
    script = window_op_script(window_id, op)
    return state_payload({"result": run_task(f"Ventana {op}", "remote_window", gui_prefix("cat > /tmp/codex_window_op.py && python /tmp/codex_window_op.py"), input_text=script, timeout=12)})


def list_files(remote_path):
    path = remote_path.strip() or "~"
    command = "python - <<'PY'\n" + f"path={json.dumps(path)}\n" + r"""
import json
from pathlib import Path
p = Path(path).expanduser()
items = []
for child in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.casefold()))[:250]:
    items.append({"name": child.name, "path": str(child), "isDir": child.is_dir(), "size": child.stat().st_size if child.is_file() else 0})
print(json.dumps({"path": str(p), "items": items}))
""" + "\nPY"
    output = ssh(command, timeout=12)
    return json.loads(output or "{}")


def open_file(remote_path):
    if not remote_path.strip():
        raise RuntimeError("Ruta vacia")
    quoted = shlex.quote(remote_path)
    return state_payload({"result": run_task(f"Abrir archivo {remote_path}", "remote_file", gui_prefix(f"nohup xdg-open {quoted} >/tmp/codex-open-file.log 2>&1 &"), timeout=10)})


def copy_file(direction, source, destination):
    source = source.strip()
    destination = destination.strip()
    if not source or not destination:
        raise RuntimeError("Origen y destino son obligatorios")
    task = add_task("Copiar archivo", "file_transfer")
    try:
        with paramiko_client() as client:
            sftp = client.open_sftp()
            try:
                if direction == "to-remote":
                    sftp.put(source, destination)
                elif direction == "from-remote":
                    sftp.get(source, destination)
                else:
                    raise RuntimeError("Direccion de copia no soportada")
            finally:
                sftp.close()
        task["status"] = "done"
        task["detail"] = "copiado"
        reply = "Listo: archivo copiado."
        messages.append({"role": "assistant", "content": reply})
        return state_payload({"result": {"reply": reply, "task": task}})
    except Exception as exc:
        task["status"] = "error"
        task["detail"] = str(exc)
        raise
    finally:
        task["finishedAt"] = now()


def universal_command(text):
    text = text.strip()
    lower = text.lower()
    if not text:
        raise RuntimeError("Comando vacio")
    if lower in {"estado", "status", "sistema"}:
        return state_payload({"system": system_info(), "result": {"reply": "Sistema actualizado."}})
    if lower in {"captura", "pantalla", "screenshot"}:
        return screenshot()
    if lower.startswith(("youtube ", "busca ", "buscar ")):
        query = re.sub(r"^(youtube|busca|buscar)\s+", "", text, flags=re.I).strip()
        results = youtube_search(query)
        return state_payload({"youtubeResults": results, "result": {"reply": f"{len(results)} videos encontrados."}})
    if lower.startswith(("abre ", "abrir ", "open ")):
        target = re.sub(r"^(abre|abrir|open)\s+", "", text, flags=re.I).strip()
        apps = list_remote_apps()
        match = next((app for app in apps if app["name"].lower() == target.lower()), None)
        if not match:
            match = next((app for app in apps if target.lower() in app["name"].lower()), None)
        if match:
            return open_remote_app(match["id"])
        if "." in target and " " not in target:
            if not target.lower().startswith(("http://", "https://")):
                target = "https://" + target
            return state_payload({"result": run_task(f"Abrir {target}", "remote_browser", firefox_open_command(target), timeout=12)})
        raise RuntimeError("No encontre una app o URL para abrir")
    raise RuntimeError("Comando no reconocido. Prueba: 'abre Firefox', 'youtube Eminem', 'captura' o 'estado'.")


def system_info():
    script = r"""
import json, os, subprocess
def out(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""
print(json.dumps({
  "hostname": out("hostname"),
  "uptime": out("uptime -p"),
  "load": out("cat /proc/loadavg"),
  "memory": out("free -h | awk '/Mem:/ {print $3 \" / \" $2}'"),
  "disk": out("df -h / | awk 'NR==2 {print $3 \" / \" $2 \" (\" $5 \")\"}'"),
  "tailscale": out("tailscale ip -4 2>/dev/null"),
  "volume": out("pactl get-sink-volume @DEFAULT_SINK@ | head -1"),
  "mute": out("pactl get-sink-mute @DEFAULT_SINK@")
}))
"""
    output = ssh("cat > /tmp/codex_system.py && python /tmp/codex_system.py", input_text=script, timeout=12)
    return json.loads(output or "{}")


def list_audio():
    script = r"""
import json, subprocess
rows = subprocess.check_output("pactl list short sinks", shell=True, text=True).strip().splitlines()
sinks = []
for row in rows:
    parts = row.split("\t")
    if len(parts) >= 2:
        sinks.append({"id": parts[0], "name": parts[1], "state": parts[4] if len(parts) > 4 else ""})
print(json.dumps(sinks))
"""
    output = ssh("cat > /tmp/codex_audio.py && python /tmp/codex_audio.py", input_text=script, timeout=12)
    return json.loads(output or "[]")


def obs_action(action):
    if action == "status":
        output = ssh("if pgrep -x obs >/dev/null; then echo running; else echo stopped; fi", timeout=8)
        return state_payload({"obs": {"status": output}, "result": {"reply": f"OBS: {output}"}})
    if action == "record":
        command = gui_prefix("nohup flatpak run com.obsproject.Studio --startrecording >/tmp/codex-obs-record.log 2>&1 &")
        return state_payload({"result": run_task("Abrir OBS grabando", "remote_obs", command, timeout=12)})
    if action == "stream":
        command = gui_prefix("nohup flatpak run com.obsproject.Studio --startstreaming >/tmp/codex-obs-stream.log 2>&1 &")
        return state_payload({"result": run_task("Abrir OBS transmitiendo", "remote_obs", command, timeout=12)})
    raise RuntimeError("Accion OBS no soportada")


def run_task(title, task_type, command, input_text=None, timeout=15):
    task = add_task(title, task_type)
    try:
        output = ssh(command, input_text=input_text, timeout=timeout)
        task["status"] = "done"
        task["detail"] = output[-400:] if output else "ok"
        reply = f"Listo: {title}."
        messages.append({"role": "assistant", "content": reply})
        return {"reply": reply, "task": task, "output": output}
    except Exception as exc:
        task["status"] = "error"
        task["detail"] = str(exc)
        raise
    finally:
        task["finishedAt"] = now()


def status():
    output = ssh(
        "printf 'host='; hostname; printf '\\n'; "
        "printf 'firefox='; if pgrep -x firefox >/dev/null; then echo running; else echo stopped; fi; "
        "printf 'obs='; if pgrep -x obs >/dev/null; then echo running; else echo stopped; fi; "
        "printf 'session='; loginctl list-sessions --no-legend 2>/dev/null | awk 'NR==1{print $0}' || true",
        timeout=10,
    )
    return state_payload({"result": {"reply": "Estado actualizado.", "output": output}})


def remote_key_script(keys):
    return f"""
import ctypes
import time

x11 = ctypes.CDLL("libX11.so.6")
xtst = ctypes.CDLL("libXtst.so.6")
x11.XOpenDisplay.restype = ctypes.c_void_p
x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
x11.XKeysymToKeycode.restype = ctypes.c_uint
x11.XFlush.argtypes = [ctypes.c_void_p]
xtst.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
display = x11.XOpenDisplay(None)
if not display:
    raise SystemExit("No pude abrir DISPLAY")
keys = {json.dumps(keys)}
for keysym in keys:
    keycode = x11.XKeysymToKeycode(display, int(keysym, 16))
    xtst.XTestFakeKeyEvent(display, keycode, 1, 0)
    x11.XFlush(display)
    time.sleep(0.04)
for keysym in reversed(keys):
    keycode = x11.XKeysymToKeycode(display, int(keysym, 16))
    xtst.XTestFakeKeyEvent(display, keycode, 0, 0)
    x11.XFlush(display)
    time.sleep(0.04)
print("sent keys")
"""


def list_remote_apps():
    script = r"""
import configparser
import json
from pathlib import Path

dirs = [
    Path.home() / ".local/share/applications",
    Path("/usr/local/share/applications"),
    Path("/usr/share/applications"),
]
apps = {}
for directory in dirs:
    if not directory.exists():
        continue
    for desktop in directory.glob("*.desktop"):
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        parser.optionxform = str
        try:
            parser.read(desktop, encoding="utf-8")
            entry = parser["Desktop Entry"]
        except Exception:
            continue
        if entry.get("Type", "Application") != "Application":
            continue
        if entry.get("Hidden", "false").lower() == "true":
            continue
        if entry.get("NoDisplay", "false").lower() == "true":
            continue
        name = entry.get("Name", "").strip()
        exec_value = entry.get("Exec", "").strip()
        if not name or not exec_value:
            continue
        app_id = desktop.name
        apps[app_id] = {
            "id": app_id,
            "name": name,
            "comment": entry.get("Comment", "").strip(),
            "terminal": entry.get("Terminal", "false").lower() == "true",
        }

print(json.dumps(sorted(apps.values(), key=lambda item: item["name"].casefold())))
"""
    output = ssh("cat > /tmp/codex_list_apps.py && python /tmp/codex_list_apps.py", input_text=script, timeout=15)
    return json.loads(output or "[]")


def open_remote_app(app_id):
    if not re.match(r"^[A-Za-z0-9_.@+-]+\.desktop$", app_id):
        raise RuntimeError("Identificador de app no valido")
    quoted_id = shlex.quote(app_id)
    return state_payload(
        {
            "result": run_task(
                f"Abrir {app_id}",
                "remote_app",
                gui_prefix(f"gtk-launch {quoted_id} >/tmp/codex-open-app.log 2>&1 || gio launch /usr/share/applications/{quoted_id} >/tmp/codex-open-app.log 2>&1"),
                timeout=12,
            )
        }
    )


def text_from_runs(value):
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    if value.get("simpleText"):
        return value["simpleText"]
    runs = value.get("runs", [])
    return "".join(run.get("text", "") for run in runs if isinstance(run, dict)).strip()


def walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def youtube_search(query):
    query = query.strip()
    if not query:
        raise RuntimeError("Busqueda vacia")
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "es-CO,es;q=0.9,en;q=0.6",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        html = response.read().decode("utf-8", errors="replace")

    match = re.search(r"ytInitialData\s*=\s*(\{.*?\});\s*</script>", html)
    if not match:
        raise RuntimeError("No pude leer los resultados de YouTube.")

    data = json.loads(match.group(1))
    results = []
    seen = set()
    for node in walk_json(data):
        renderer = node.get("videoRenderer") if isinstance(node, dict) else None
        if not renderer:
            continue
        video_id = renderer.get("videoId")
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        thumbs = renderer.get("thumbnail", {}).get("thumbnails", [])
        thumb = thumbs[-1].get("url", "") if thumbs else f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        channel = ""
        owner = renderer.get("ownerText") or renderer.get("shortBylineText") or {}
        channel = text_from_runs(owner)
        results.append(
            {
                "id": video_id,
                "title": text_from_runs(renderer.get("title", {})) or "Video sin titulo",
                "channel": channel,
                "duration": text_from_runs(renderer.get("lengthText", {})),
                "thumbnail": thumb,
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }
        )
        if len(results) >= 12:
            break
    if not results:
        raise RuntimeError("No encontre videos para esa busqueda.")
    return results


def media_status():
    script = r"""
import json
import subprocess

env = __REMOTE_SESSION_ENV__

def run(args):
    return subprocess.check_output(args, text=True, env=env).strip()

def bus_json(args):
    return json.loads(run(["busctl", "--user", "--json=short"] + args))

try:
    names = bus_json(["list"])
    players = [item["name"] for item in names if item.get("name", "").startswith("org.mpris.MediaPlayer2.")]
    if not players:
        print(json.dumps({"available": False, "title": "Nada reproduciendose"}))
        raise SystemExit
    player = next((name for name in players if "firefox" in name.lower()), players[0])
    status = bus_json(["get-property", player, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player", "PlaybackStatus"])["data"]
    metadata = bus_json(["get-property", player, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player", "Metadata"])["data"]
    position = int(bus_json(["get-property", player, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player", "Position"])["data"])
    artists = metadata.get("xesam:artist", {}).get("data", [])
    print(json.dumps({
        "available": True,
        "player": player,
        "status": status,
        "title": metadata.get("xesam:title", {}).get("data", "Sin titulo"),
        "artist": ", ".join(artists) if isinstance(artists, list) else str(artists or ""),
        "url": metadata.get("xesam:url", {}).get("data", ""),
        "artUrl": metadata.get("mpris:artUrl", {}).get("data", ""),
        "trackId": metadata.get("mpris:trackid", {}).get("data", "/org/mpris/MediaPlayer2/firefox"),
        "position": position,
        "length": int(metadata.get("mpris:length", {}).get("data", 0) or 0),
    }))
except Exception as error:
    print(json.dumps({"available": False, "title": "Sin datos de reproduccion", "error": str(error)}))
""".replace("__REMOTE_SESSION_ENV__", repr(remote_session_env()))
    output = ssh("cat > /tmp/codex_media_status.py && python /tmp/codex_media_status.py", input_text=script, timeout=12)
    return json.loads(output or "{}")


def media_method(method):
    script = f"""
import json
import subprocess

env = {repr(remote_session_env())}
names = json.loads(subprocess.check_output(["busctl", "--user", "--json=short", "list"], text=True, env=env))
players = [item["name"] for item in names if item.get("name", "").startswith("org.mpris.MediaPlayer2.")]
if not players:
    raise SystemExit("No hay reproductor MPRIS activo")
player = next((name for name in players if "firefox" in name.lower()), players[0])
subprocess.check_call(["busctl", "--user", "call", player, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player", "{method}"], env=env)
print(player)
"""
    return run_task(f"Media {method}", "remote_media", "cat > /tmp/codex_media_method.py && python /tmp/codex_media_method.py", input_text=script, timeout=12)


def media_seek(position):
    try:
        microseconds = int(float(position))
    except ValueError as exc:
        raise RuntimeError("Posicion invalida") from exc
    if microseconds < 0:
        microseconds = 0
    script = f"""
import json
import subprocess

env = {repr(remote_session_env())}
def bus_json(args):
    return json.loads(subprocess.check_output(["busctl", "--user", "--json=short"] + args, text=True, env=env))
names = bus_json(["list"])
players = [item["name"] for item in names if item.get("name", "").startswith("org.mpris.MediaPlayer2.")]
if not players:
    raise SystemExit("No hay reproductor MPRIS activo")
player = next((name for name in players if "firefox" in name.lower()), players[0])
metadata = bus_json(["get-property", player, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player", "Metadata"])["data"]
track_id = metadata.get("mpris:trackid", {{}}).get("data", "/org/mpris/MediaPlayer2/firefox")
subprocess.check_call(["busctl", "--user", "call", player, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player", "SetPosition", "ox", track_id, "{microseconds}"], env=env)
print(player)
"""
    return run_task("Mover posicion de reproduccion", "remote_media", "cat > /tmp/codex_media_seek.py && python /tmp/codex_media_seek.py", input_text=script, timeout=12)


def send_keys(title, keys):
    script = remote_key_script(keys)
    command = gui_prefix("cat > /tmp/codex_remote_keys.py && python /tmp/codex_remote_keys.py")
    return run_task(title, "remote_key", command, input_text=script, timeout=12)


def remote_action(action, body=None):
    body = body or {}
    if action == "connection-test":
        return connection_test(body)
    if action == "connection-connect":
        return connection_connect(body)
    if action == "connection-disconnect":
        return connection_disconnect()
    if action == "desktop-shortcut":
        return desktop_shortcut()
    if action == "terminal-open":
        return terminal_open(body.get("cols", 120), body.get("rows", 34))
    if action == "terminal-read":
        return terminal_read()
    if action == "terminal-write":
        return terminal_write(str(body.get("text", "")))
    if action == "terminal-resize":
        return terminal_resize(body.get("cols", 120), body.get("rows", 34))
    if action == "terminal-close":
        return terminal_close()
    if action == "screenshot":
        return screenshot()
    if action == "click":
        return click_remote(body.get("x", 0), body.get("y", 0))
    if action == "type-text":
        return type_text(str(body.get("text", "")))
    if action == "shortcut":
        shortcuts = {
            "enter": ["0xFF0D"], "esc": ["0xFF1B"], "tab": ["0xFF09"],
            "ctrl-l": ["0xFFE3", "0x006C"], "alt-tab": ["0xFFE9", "0xFF09"],
            "ctrl-w": ["0xFFE3", "0x0077"], "ctrl-r": ["0xFFE3", "0x0072"],
        }
        keys = shortcuts.get(str(body.get("name", "")))
        if not keys:
            raise RuntimeError("Atajo no soportado")
        return state_payload({"result": send_keys(f"Atajo {body.get('name')}", keys)})
    if action == "windows":
        return state_payload({"windows": list_windows(), "result": {"reply": "Ventanas actualizadas."}})
    if action == "window-action":
        return window_action(str(body.get("id", "")), str(body.get("op", "")))
    if action == "files":
        return state_payload({"files": list_files(str(body.get("path", "~"))), "result": {"reply": "Archivos actualizados."}})
    if action == "open-file":
        return open_file(str(body.get("path", "")))
    if action == "copy-to-remote":
        return copy_file("to-remote", str(body.get("source", "")), str(body.get("destination", "")))
    if action == "copy-from-remote":
        return copy_file("from-remote", str(body.get("source", "")), str(body.get("destination", "")))
    if action == "command":
        return universal_command(str(body.get("text", "")))
    if action == "system":
        return state_payload({"system": system_info(), "audioSinks": list_audio(), "result": {"reply": "Sistema actualizado."}})
    if action == "audio-sinks":
        return state_payload({"audioSinks": list_audio(), "result": {"reply": "Audio actualizado."}})
    if action == "set-sink":
        sink = str(body.get("sink", ""))
        if not re.match(r"^[A-Za-z0-9_.:-]+$", sink):
            raise RuntimeError("Sink invalido")
        return state_payload({"result": run_task("Cambiar salida de audio", "remote_audio", f"pactl set-default-sink {shlex.quote(sink)}", timeout=10)})
    if action == "obs-status":
        return obs_action("status")
    if action == "obs-record":
        return obs_action("record")
    if action == "obs-stream":
        return obs_action("stream")
    if action == "status":
        return status()
    if action == "apps":
        apps = list_remote_apps()
        return state_payload({"apps": apps, "result": {"reply": f"{len(apps)} apps encontradas."}})
    if action == "open-app":
        return open_remote_app(str(body.get("appId", "")).strip())
    if action == "open-firefox":
        return state_payload({"result": run_task("Abrir Firefox", "remote_app", gui_prefix("nohup firefox >/tmp/codex-firefox.log 2>&1 &"), timeout=10)})
    if action == "close-firefox":
        return state_payload({"result": run_task("Cerrar Firefox", "remote_app", "pkill -x firefox || true", timeout=10)})
    if action == "open-youtube":
        url = "https://www.youtube.com"
        return state_payload({"result": run_task("Abrir YouTube", "remote_browser", firefox_open_command(url), timeout=12)})
    if action == "youtube-search":
        query = str(body.get("query", "")).strip()
        results = youtube_search(query)
        return state_payload({"youtubeResults": results, "result": {"reply": f"{len(results)} videos encontrados."}})
    if action == "media-status":
        return state_payload({"media": media_status(), "result": {"reply": "Estado de reproduccion actualizado."}})
    if action == "media-play-pause":
        try:
            result = media_method("PlayPause")
        except Exception:
            result = send_keys("Play/Pausa en navegador remoto", ["0x0020"])
        return state_payload({"result": result, "media": media_status()})
    if action == "media-next":
        try:
            result = media_method("Next")
        except Exception:
            result = send_keys("Siguiente cancion en YouTube", ["0xFFE1", "0x006E"])
        return state_payload({"result": result, "media": media_status()})
    if action == "media-prev":
        try:
            result = media_method("Previous")
        except Exception:
            result = send_keys("Cancion anterior en YouTube", ["0xFFE1", "0x0070"])
        return state_payload({"result": result, "media": media_status()})
    if action == "media-seek":
        result = media_seek(body.get("position", 0))
        return state_payload({"result": result, "media": media_status()})
    if action == "open-eminem":
        url = "https://www.youtube.com/watch?v=_Yhyp-_hX2s&list=RD_Yhyp-_hX2s&start_radio=1&autoplay=1"
        return state_payload({"result": run_task("Abrir playlist Eminem", "remote_browser", firefox_open_command(url), timeout=12)})
    if action == "open-url":
        url = str(body.get("url", "")).strip()
        if not url:
            raise RuntimeError("URL vacia")
        if not url.lower().startswith(("http://", "https://")):
            url = "https://" + url
        return state_payload({"result": run_task(f"Abrir {url}", "remote_browser", firefox_open_command(url), timeout=12)})
    if action == "open-obs":
        return state_payload({"result": run_task("Abrir OBS", "remote_app", gui_prefix("nohup flatpak run com.obsproject.Studio >/tmp/codex-obs.log 2>&1 &"), timeout=12)})
    if action == "close-obs":
        return state_payload({"result": run_task("Cerrar OBS", "remote_app", "pkill -x obs || true", timeout=10)})
    if action == "play-pause":
        return state_payload({"result": send_keys("Play/Pausa en navegador remoto", ["0x0020"])})
    if action == "youtube-next":
        return state_payload({"result": send_keys("Siguiente cancion en YouTube", ["0xFFE1", "0x006E"])})
    if action == "youtube-prev":
        return state_payload({"result": send_keys("Cancion anterior en YouTube", ["0xFFE1", "0x0070"])})
    if action == "volume-up":
        return state_payload({"result": run_task("Subir volumen", "remote_audio", "pactl set-sink-volume @DEFAULT_SINK@ +5%", timeout=10)})
    if action == "volume-down":
        return state_payload({"result": run_task("Bajar volumen", "remote_audio", "pactl set-sink-volume @DEFAULT_SINK@ -5%", timeout=10)})
    if action == "mute":
        return state_payload({"result": run_task("Silenciar/activar sonido", "remote_audio", "pactl set-sink-mute @DEFAULT_SINK@ toggle", timeout=10)})
    raise RuntimeError(f"Accion remota no soportada: {action}")


class PanelHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC), **kwargs)

    def log_message(self, format, *args):
        return

    def do_GET(self):
        if self.path == "/api/state":
            json_response(self, 200, state_payload())
            return
        super().do_GET()

    def do_POST(self):
        try:
            if self.path.startswith("/api/remote/"):
                action = self.path.rsplit("/", 1)[-1]
                body = read_json(self)
                json_response(self, 200, remote_action(action, body))
                return
            json_response(self, 404, {"error": "Not found"})
        except Exception as exc:
            json_response(self, 500, {"error": str(exc)})


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), PanelHandler)
    server.serve_forever()
