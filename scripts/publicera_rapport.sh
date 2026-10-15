#!/usr/bin/env bash
# Publicera en rapportmapp på grenen "datarapport" (används av GitHub Actions).
#   bash scripts/publicera_rapport.sh MAPP "Meddelande"
# Endast rapportfiler (räknade siffror) – aldrig rådata från licensierade källor.
set -euo pipefail
SRC="$1"
MSG="${2:-Datarapport}"
TMP=$(mktemp -d)
cp -r "$SRC"/. "$TMP"/
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
WT=$(mktemp -d)
if git fetch --depth 1 origin datarapport 2>/dev/null; then
  git worktree add "$WT" FETCH_HEAD
  (cd "$WT" && git checkout -B datarapport)
else
  git worktree add --detach "$WT"
  (cd "$WT" && git checkout --orphan datarapport && git rm -rfq . )
fi
mkdir -p "$WT/rapport"
cp -r "$TMP"/. "$WT/rapport/"
cd "$WT"
git add rapport
if git diff --cached --quiet; then
  echo "Inga ändringar i rapporten"
  exit 0
fi
git commit -qm "$MSG $(date -u +%Y-%m-%dT%H:%M:%SZ) [skip ci]"
for i in 1 2 3; do
  if git push origin datarapport; then exit 0; fi
  git fetch --depth 1 origin datarapport && git rebase FETCH_HEAD || true
  sleep 5
done
exit 1
