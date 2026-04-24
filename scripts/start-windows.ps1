$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
if (-not $Python) {
  $Python = (Get-Command pyw -ErrorAction SilentlyContinue).Source
}
if (-not $Python) {
  $Python = (Get-Command py -ErrorAction SilentlyContinue).Source
}
if (-not $Python) {
  $Python = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $Python) {
  throw "Python was not found. Install Python 3 and try again."
}

$Port = if ($env:REMOTE_PANEL_PORT) { $env:REMOTE_PANEL_PORT } elseif ($env:ENDEAVOUR_PANEL_PORT) { $env:ENDEAVOUR_PANEL_PORT } else { "8787" }
$env:REMOTE_PANEL_PORT = $Port

$Url = "http://localhost:$Port"
$ServerAlive = $false
try {
  Invoke-RestMethod -Uri "$Url/api/state" -TimeoutSec 1 | Out-Null
  $ServerAlive = $true
} catch {
  $ServerAlive = $false
}

if (-not $ServerAlive) {
  if ((Split-Path $Python -Leaf) -in @("py.exe", "pyw.exe")) {
    $Args = @("-3", "$Root\server.py")
  } else {
    $Args = @("$Root\server.py")
  }
  Start-Process -FilePath $Python -ArgumentList $Args -WorkingDirectory $Root -WindowStyle Hidden
  Start-Sleep -Milliseconds 700
}

$Edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if (Test-Path $Edge) {
  Start-Process -FilePath $Edge -ArgumentList @("--app=$Url", "--window-size=980,760")
} else {
  Start-Process $Url
}
