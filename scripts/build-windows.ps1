# Bygg MatchIQ för Windows (.exe-installerare + .msi) på en Windows-dator.
#
#   powershell -ExecutionPolicy Bypass -File scripts\build-windows.ps1
#
# Kräver: Python 3.11+ (python i PATH), Node.js 20+ (npm i PATH).
# Resultat: apps\desktop\release\MatchIQ-<version>-win-x64.exe och .msi
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$Root = Get-Location

function Say($t) { Write-Host "`n==> $t" -ForegroundColor Cyan }

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) { throw "Python 3.11 eller senare krävs" }

Say "1/5 Python-miljö för backend"
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip | Out-Null
pip install -r backend\requirements.txt -r backend\requirements-dev.txt

Say "2/5 Backend-tester"
Push-Location backend
$env:MATCHIQ_SECRETS = "memory"; $env:PYTHONPATH = "."
python -m unittest discover -s tests -p "test_*.py"
if ($LASTEXITCODE -ne 0) { throw "Backend-testerna misslyckades" }
Remove-Item Env:MATCHIQ_SECRETS; Remove-Item Env:PYTHONPATH

Say "3/5 Paketera backend (PyInstaller)"
pyinstaller --noconfirm matchiq-backend.spec
Pop-Location

Say "4/5 Bygg gränssnittet"
npm install
npm --workspace apps/web run build

Say "5/5 Bygg Windows-installerare"
Push-Location apps\desktop
npm run build
if (-not $env:CSC_LINK) { $env:CSC_IDENTITY_AUTO_DISCOVERY = "false" }
npx electron-builder --win --x64 --publish never
Pop-Location

Say "Klart"
Get-ChildItem "$Root\apps\desktop\release\*.exe", "$Root\apps\desktop\release\*.msi" | Select-Object Name, Length
