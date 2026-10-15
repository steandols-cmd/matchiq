# PyInstaller-spec för backend-sidecaren (onedir => snabb start). Körs: pyinstaller matchiq-backend.spec
from PyInstaller.utils.hooks import collect_submodules

hidden = collect_submodules("uvicorn") + collect_submodules("keyring.backends") + ["tzdata"]
a = Analysis(
    ["run_backend.py"],
    pathex=["."],
    datas=[("matchiq/migrations/*.sql", "matchiq/migrations"),
           ("matchiq/assets/fonts/*", "matchiq/assets/fonts")],
    hiddenimports=hidden,
    excludes=["tkinter", "matplotlib", "pandas", "scipy", "IPython", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="matchiq-backend", console=True,
          codesign_identity=None, entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.datas, name="matchiq-backend")
