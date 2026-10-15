"""Hämtning av filer från publika GitHub-repon via GitHubs dokumenterade REST-API.

* Filträdet hämtas med ett anrop (git/trees, recursive) – ger varje fils blob-SHA, så oförändrade
  filer kan hoppas över utan att laddas ner igen.
* Filinnehåll hämtas från GitHubs värd för rå filer (raw.githubusercontent.com), som inte omfattas av
  API:ts gräns på 60 anrop/timme och saknar robots.txt-begränsningar (kontrolleras i källinventeringen).
  Svarar den med något annat än 200/404 används contents-endpointen med ``Accept: application/vnd.github.raw``.
* Anropsgränsen följs: när GitHub svarar att kvoten är slut avbryts körningen med ett tydligt
  meddelande om när den kan återupptas (``SourceBlocked``). En GitHub-token (Inställningar →
  API-nycklar, eller miljövariabeln GITHUB_TOKEN i CI) höjer gränsen från 60 till 5 000 anrop/timme.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from .. import secrets_store
from .http import FetchResult, HttpClient, SourceBlocked

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"


def github_token() -> str | None:
    return secrets_store.get_secret("github_token") or os.environ.get("MATCHIQ_GITHUB_TOKEN") or None


class GitHubRepo:
    def __init__(self, http: HttpClient, source_id: str, owner: str, repo: str):
        self.http = http
        self.source_id = source_id
        self.owner = owner
        self.repo = repo
        self._branch: str | None = None

    def _headers(self, raw: bool = False) -> dict:
        h = {"Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json",
             "X-GitHub-Api-Version": "2022-11-28"}
        tok = github_token()
        if tok:
            h["Authorization"] = f"Bearer {tok}"
        return h

    def _check_limit(self, res: FetchResult) -> None:
        if res.status in (403, 429) and res.headers.get("X-RateLimit-Remaining") == "0":
            reset = res.headers.get("X-RateLimit-Reset")
            when = (datetime.fromtimestamp(int(reset), timezone.utc).strftime("%H:%M UTC")
                    if reset and reset.isdigit() else "senare")
            raise SourceBlocked(f"GitHubs anropsgräns är nådd – hämtningen återupptas automatiskt efter {when}. "
                                "En GitHub-token under Inställningar → API-nycklar höjer gränsen.")

    def branch(self, job: str) -> str:
        if self._branch is None:
            res = self.http.get(self.source_id, f"{API}/repos/{self.owner}/{self.repo}", job=job,
                                headers=self._headers(), conditional=False)
            self._check_limit(res)
            if res.status != 200:
                raise RuntimeError(f"{self.owner}/{self.repo}: HTTP {res.status}")
            self.http.finish(res.fetch_id, "ok")
            self._branch = (res.json() or {}).get("default_branch") or "master"
        return self._branch

    def tree(self, job: str) -> dict[str, str]:
        """{sökväg: blob-SHA} för alla filer i standardgrenen."""
        br = self.branch(job)
        res = self.http.get(self.source_id, f"{API}/repos/{self.owner}/{self.repo}/git/trees/{br}",
                            job=job, params={"recursive": "1"}, headers=self._headers(), conditional=False)
        self._check_limit(res)
        if res.status != 200:
            raise RuntimeError(f"{self.owner}/{self.repo} filträd: HTTP {res.status}")
        data = res.json() or {}
        self.http.finish(res.fetch_id, "ok", {"inserted": len(data.get("tree", []))})
        return {t["path"]: t["sha"] for t in data.get("tree", []) if t.get("type") == "blob"}

    def file(self, path: str, job: str, *, archive: str = "full", timeout: float = 60) -> FetchResult:
        br = self.branch(job)
        # Inga villkorliga anrop här: oförändrade filer hoppas över via blob-SHA eller redan importerade
        # matcher, och ett 304-svar utan innehåll skulle annars tolkas som en tom fil.
        res = self.http.get(self.source_id, f"{RAW}/{self.owner}/{self.repo}/{br}/{path}", job=job,
                            archive=archive, timeout=timeout, conditional=False)
        if res.status in (200, 404):
            return res
        res = self.http.get(self.source_id, f"{API}/repos/{self.owner}/{self.repo}/contents/{path}", job=job,
                            headers=self._headers(raw=True), archive=archive, timeout=timeout, conditional=False)
        self._check_limit(res)
        return res
