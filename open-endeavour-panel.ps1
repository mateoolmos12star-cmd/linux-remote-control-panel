$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$HostName = if ($env:REMOTE_SSH_HOST) { $env:REMOTE_SSH_HOST } elseif ($env:ENDEAVOUR_SSH_HOST) { $env:ENDEAVOUR_SSH_HOST } else { "endeavour" }
$Port = if ($env:REMOTE_PANEL_PORT) { $env:REMOTE_PANEL_PORT } elseif ($env:ENDEAVOUR_PANEL_PORT) { $env:ENDEAVOUR_PANEL_PORT } elseif ($env:CODEX_COMPANION_PORT) { $env:CODEX_COMPANION_PORT } else { "8787" }

$env:REMOTE_SSH_HOST = $HostName
$env:ENDEAVOUR_SSH_HOST = $HostName
$env:ENDEAVOUR_SSH_CONTROL_PATH = ""
$env:REMOTE_PANEL_PORT = $Port
$env:ENDEAVOUR_PANEL_PORT = $Port
$env:CODEX_COMPANION_PORT = $Port

& "$Root\start-companion.ps1"
