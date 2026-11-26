"""Rutas de Live del usuario leidas de su Library.cfg (el de la version de Live usada mas recientemente)."""
import os
import re
import sys

# carpeta de preferencias de Live: %APPDATA%\Ableton en Windows, ~/Library/Preferences/Ableton en Mac
PREFS = (os.path.expanduser("~/Library/Preferences/Ableton") if sys.platform == "darwin"
         else os.path.join(os.environ.get("APPDATA", ""), "Ableton"))


def library_cfg() -> str:
    cfgs = [os.path.join(PREFS, d, "Preferences", "Library.cfg") for d in (os.listdir(PREFS) if os.path.isdir(PREFS) else [])]
    cfgs = sorted((c for c in cfgs if os.path.isfile(c)), key=os.path.getmtime)
    return open(cfgs[-1], encoding="utf-8", errors="replace").read() if cfgs else ""


def user_library() -> str | None:
    """Carpeta 'User Library' de Live, o None si no hay Library.cfg."""
    m = re.search(r'<UserLibrary>.*?<ProjectName Value="([^"]*)" />\s*<ProjectPath Value="([^"]*)" />',
                  library_cfg(), re.S)
    return os.path.normpath(os.path.join(m.group(2), m.group(1))) if m else None
