# Linux Remote Control Panel

Local web panel for controlling a Linux desktop over SSH from Windows or another Linux machine.

It runs only on your local computer, connects to the remote machine with SSH, and exposes a browser UI for common desktop tasks: screenshots, remote clicks, keyboard input, app launching, Firefox/YouTube control, media controls, files, windows, audio, system status, and basic OBS launch controls.

## Safety model

This project can click, type, open apps, and run commands on the remote Linux desktop. Treat it like a remote-control tool:

- Run the panel only on a trusted machine.
- Keep the web server bound to `localhost`.
- Use SSH keys or a password you control.
- Do not expose the panel port directly to the internet.
- Use a private VPN such as Tailscale/WireGuard if you need access across different Wi-Fi networks.

## Requirements

Local controller:

- Python 3.10+
- SSH access to the remote Linux machine
- Python packages from `requirements.txt`

Remote Linux desktop:

- OpenSSH server
- Python 3
- An active X11 desktop session
- `xfce4-screenshooter` for screenshots
- `xprop` and X11 libraries for window/click/keyboard control
- `pactl` for audio controls
- `busctl` for MPRIS media controls
- Firefox and OBS are optional, but enabled by the UI

Wayland desktops may need extra configuration or X11/XWayland-compatible tools.

## Quick Start: Windows to Linux

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Create or update your SSH alias in `%USERPROFILE%\.ssh\config`:

```sshconfig
Host remote-linux
    HostName 192.168.1.26
    User your-linux-user
    IdentityFile ~/.ssh/id_ed25519
```

Run the panel:

```powershell
$env:REMOTE_SSH_HOST="remote-linux"
.\scripts\start-windows.ps1
```

The legacy launcher `.\open-endeavour-panel.ps1` still works and defaults to the SSH alias `endeavour`.

## Quick Start: Linux to Linux

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Create an SSH alias in `~/.ssh/config`, then run:

```bash
REMOTE_SSH_HOST=remote-linux ./scripts/start-linux.sh
```

Open `http://localhost:8787` if the browser does not open automatically.

## Remote Setup Examples

Arch/EndeavourOS:

```bash
sudo pacman -S --needed openssh python xfce4-screenshooter xorg-xprop pulseaudio-utils
sudo systemctl enable --now sshd
```

Debian/Ubuntu:

```bash
sudo apt update
sudo apt install openssh-server python3 xfce4-screenshooter x11-utils pulseaudio-utils
sudo systemctl enable --now ssh
```

For access outside your home network, configure a private VPN. With Tailscale, install it on both machines and use the remote machine's Tailscale IP or MagicDNS name in your SSH config.

## Configuration

Environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `REMOTE_SSH_HOST` | `endeavour` | SSH host or alias for the remote Linux machine. |
| `REMOTE_PANEL_PORT` | `8787` | Local web panel port. |
| `REMOTE_DISPLAY` | `:0` | Remote X11 display. |
| `REMOTE_XAUTHORITY` | `/tmp/xauth_OvomTp` | Remote Xauthority file. Change this for other Linux users/sessions. |
| `REMOTE_XDG_RUNTIME_DIR` | `/run/user/1000` | Remote runtime directory. |
| `REMOTE_DBUS_SESSION_BUS_ADDRESS` | `unix:path=/run/user/1000/bus` | Remote DBus session bus. |

The old `ENDEAVOUR_SSH_HOST` and `ENDEAVOUR_PANEL_PORT` names are still supported for backward compatibility.


## License

MIT
