"""Startskript för den paketerade backend-sidecaren (PyInstaller)."""
import multiprocessing

from matchiq.server import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
