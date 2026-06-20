# SO-101 teleop - Windows 11 install script.
# Creates a Python 3.11 venv (.venv next to the teleop folder) and installs lerobot[feetech].
#
# Usage (in PowerShell, from the repo root):
#   powershell -ExecutionPolicy Bypass -File teleop\install_windows.ps1
#
# If you get "running scripts is disabled", run this once first:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

$ErrorActionPreference = "Stop"

# Repo root = parent of this script's dir.
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$Venv = Join-Path $Root ".venv"

Write-Host "==> Repo root: $Root"

# Find a Python 3.11 interpreter. The Windows 'py' launcher is the most reliable way.
$pyExe = $null
$pyArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    # Confirm 3.11 is installed via the launcher.
    $has311 = (& py -0p) -match "3\.11"
    if ($has311) {
        $pyExe = "py"
        $pyArgs = @("-3.11")
    } else {
        Write-Host "==> Python 3.11 not found via 'py' launcher."
        Write-Host "    Install it from https://www.python.org/downloads/release/python-3119/"
        Write-Host "    (3.10-3.12 are fine; avoid 3.14 - no torch wheels yet.)"
        exit 1
    }
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pyExe = "python"
    Write-Host "==> 'py' launcher not found; using 'python' on PATH. Ensure it is 3.10-3.12."
} else {
    Write-Host "==> No Python found. Install Python 3.11 from python.org and re-run."
    exit 1
}

Write-Host "==> Creating venv at $Venv ..."
& $pyExe @pyArgs -m venv $Venv

$activate = Join-Path $Venv "Scripts\Activate.ps1"
Write-Host "==> Activating venv..."
& $activate

Write-Host "==> Upgrading pip..."
python -m pip install --upgrade pip

Write-Host "==> Installing lerobot[feetech] (this pulls torch and may take a few minutes)..."
pip install "lerobot[feetech]"

Write-Host ""
Write-Host "==> Done. Verify:"
python -c "import lerobot; print('lerobot', lerobot.__version__)"

Write-Host ""
Write-Host "Next (this machine can be EITHER role):"
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  lerobot-find-port          # find your arm's COM port"
Write-Host "  # LEADER  machine -> run leader_client.py"
Write-Host "  # FOLLOWER machine -> run follower_server.py"
Write-Host "  # see teleop\README.md"
