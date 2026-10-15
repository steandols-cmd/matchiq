"""API-nycklar lagras i operativsystemets nyckelförråd – aldrig i källkod, databas eller loggar.

* macOS: Nyckelringen (Keychain) via ``keyring`` eller kommandot ``security``.
* Windows: Autentiseringshanteraren (Credential Manager) via ``keyring`` eller Win32 CredWrite/CredRead.
* Linux: Secret Service via ``keyring`` eller ``secret-tool``.

Miljövariabeln ``MATCHIQ_SECRETS=memory`` ger ett minnesbaserat förråd för tester.
"""
from __future__ import annotations

import os
import subprocess
import sys

SERVICE = "MatchIQ"
KNOWN_KEYS = {
    "api_football": "API-Football (API-Sports) – nyckel",
    "football_data_org": "football-data.org – X-Auth-Token",
    "the_odds_api": "The Odds API – apiKey",
    "github_token": "GitHub-token (valfri, höjer anropsgränsen för OpenFootball/StatsBomb)",
}
_memory: dict[str, str] = {}


def _backend() -> str:
    if os.environ.get("MATCHIQ_SECRETS") == "memory":
        return "memory"
    try:
        import keyring  # noqa: F401
        return "keyring"
    except Exception:  # noqa: BLE001
        pass
    if sys.platform == "darwin":
        return "macos-security"
    if sys.platform.startswith("win"):
        return "win-cred"
    return "secret-tool"


def backend_name() -> str:
    return {"memory": "Minne (test)", "keyring": "Systemets nyckelförråd (keyring)",
            "macos-security": "macOS Nyckelring", "win-cred": "Windows Autentiseringshanteraren",
            "secret-tool": "Secret Service (secret-tool)"}[_backend()]


def set_secret(name: str, value: str) -> None:
    if name not in KNOWN_KEYS:
        raise KeyError(name)
    value = value.strip()
    if not value:
        raise ValueError("Tom nyckel")
    b = _backend()
    if b == "memory":
        _memory[name] = value
    elif b == "keyring":
        import keyring
        keyring.set_password(SERVICE, name, value)
    elif b == "macos-security":
        # -U uppdaterar befintlig post. Värdet skickas via stdin-läget (-w utan värde stöds ej icke-interaktivt),
        # därför används keyring-paketet i paketerade byggen; detta är en reserv.
        subprocess.run(["security", "add-generic-password", "-U", "-a", name, "-s", SERVICE, "-w", value],
                       check=True, capture_output=True)
    elif b == "win-cred":
        _win_write(f"{SERVICE}:{name}", value)
    else:
        subprocess.run(["secret-tool", "store", "--label", f"{SERVICE} {name}", "service", SERVICE, "account", name],
                       input=value.encode(), check=True, capture_output=True)


def get_secret(name: str) -> str | None:
    b = _backend()
    try:
        if b == "memory":
            return _memory.get(name)
        if b == "keyring":
            import keyring
            return keyring.get_password(SERVICE, name)
        if b == "macos-security":
            r = subprocess.run(["security", "find-generic-password", "-a", name, "-s", SERVICE, "-w"],
                               capture_output=True, text=True)
            return r.stdout.strip() or None if r.returncode == 0 else None
        if b == "win-cred":
            return _win_read(f"{SERVICE}:{name}")
        r = subprocess.run(["secret-tool", "lookup", "service", SERVICE, "account", name],
                           capture_output=True, text=True)
        return r.stdout.strip() or None if r.returncode == 0 else None
    except Exception:  # noqa: BLE001 - saknat förråd ska inte krascha appen
        return None


def delete_secret(name: str) -> None:
    b = _backend()
    if b == "memory":
        _memory.pop(name, None)
    elif b == "keyring":
        import keyring
        try:
            keyring.delete_password(SERVICE, name)
        except Exception:  # noqa: BLE001
            pass
    elif b == "macos-security":
        subprocess.run(["security", "delete-generic-password", "-a", name, "-s", SERVICE], capture_output=True)
    elif b == "win-cred":
        _win_delete(f"{SERVICE}:{name}")
    else:
        subprocess.run(["secret-tool", "clear", "service", SERVICE, "account", name], capture_output=True)


def status() -> dict:
    return {"backend": backend_name(),
            "keys": [{"name": k, "label": v, "configured": bool(get_secret(k))} for k, v in KNOWN_KEYS.items()]}


# ---------------------------------------------------------------- Windows (ctypes, utan beroenden)
def _win_api():
    import ctypes
    from ctypes import wintypes

    class CREDENTIAL(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                    ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
                    ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
                    ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                    ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]
    return ctypes, wintypes, CREDENTIAL, ctypes.windll.advapi32  # type: ignore[attr-defined]


def _win_write(target: str, secret: str) -> None:
    ctypes, wintypes, CREDENTIAL, advapi = _win_api()
    blob = secret.encode("utf-16-le")
    cred = CREDENTIAL()
    cred.Type = 1  # CRED_TYPE_GENERIC
    cred.TargetName = target
    cred.CredentialBlobSize = len(blob)
    cred.CredentialBlob = ctypes.cast(ctypes.create_string_buffer(blob, len(blob)), ctypes.POINTER(ctypes.c_char))
    cred.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE
    cred.UserName = "MatchIQ"
    if not advapi.CredWriteW(ctypes.byref(cred), 0):
        raise OSError("CredWriteW misslyckades")


def _win_read(target: str) -> str | None:
    ctypes, wintypes, CREDENTIAL, advapi = _win_api()
    pcred = ctypes.POINTER(CREDENTIAL)()
    if not advapi.CredReadW(target, 1, 0, ctypes.byref(pcred)):
        return None
    try:
        c = pcred.contents
        return ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize).decode("utf-16-le")
    finally:
        advapi.CredFree(pcred)


def _win_delete(target: str) -> None:
    ctypes, wintypes, CREDENTIAL, advapi = _win_api()
    advapi.CredDeleteW(target, 1, 0)
