#!/usr/bin/env bash
# Bygg MatchIQ som macOS-app (.dmg + .zip) direkt på din Mac.
#
#   ./scripts/build-mac.sh
#
# Kräver: Python 3.11+ (python3), Node.js 20+ (npm), Xcode Command Line Tools (xcode-select --install).
# Resultat: apps/desktop/release/MatchIQ-<version>-mac-<arkitektur>.dmg
#
# Utan Developer ID-certifikat signeras appen ad hoc. En app som du byggt själv på din egen Mac
# får ingen karantänflagga och startar därför utan Gatekeeper-varning.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

command -v python3 >/dev/null || { echo "python3 saknas – installera Python 3.11+ från python.org"; exit 1; }
command -v npm >/dev/null || { echo "npm saknas – installera Node.js 20+ från nodejs.org"; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || { echo "Python 3.11 eller senare krävs"; exit 1; }

say "1/5 Python-miljö för backend"
python3 -m venv "$ROOT/.venv"
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
pip install --upgrade pip >/dev/null
pip install -r backend/requirements.txt -r backend/requirements-dev.txt

say "2/5 Backend-tester"
(cd backend && MATCHIQ_SECRETS=memory PYTHONPATH=. python -m unittest discover -s tests -p "test_*.py")

say "3/5 Paketera backend (PyInstaller)"
(cd backend && pyinstaller --noconfirm matchiq-backend.spec)

say "4/5 Bygg gränssnittet"
npm install
npm --workspace apps/web run build

say "5/5 Bygg macOS-appen"
cd apps/desktop
npm run build
if [ -z "${CSC_LINK:-}" ] && [ -z "${CSC_NAME:-}" ]; then
  export CSC_IDENTITY_AUTO_DISCOVERY=false
fi
npx electron-builder --mac --publish never
if [ -z "${CSC_LINK:-}" ] && [ -z "${CSC_NAME:-}" ]; then
  APP=$(ls -d release/mac*/MatchIQ.app | head -1)
  codesign --force --deep --sign - "$APP"
  VER=$(node -p "require('./package.json').version")
  ARCH=$(basename "$(dirname "$APP")" | sed 's/^mac-\{0,1\}//'); ARCH=${ARCH:-x64}
  rm -f release/*.dmg release/*.zip
  hdiutil create -volname "MatchIQ $VER" -srcfolder "$APP" -ov -format UDZO "release/MatchIQ-$VER-mac-$ARCH.dmg"
  ditto -c -k --keepParent "$APP" "release/MatchIQ-$VER-mac-$ARCH.zip"
fi

say "Klart"
ls -1 "$ROOT"/apps/desktop/release/*.dmg
echo "Öppna dmg-filen och dra MatchIQ till Program."
