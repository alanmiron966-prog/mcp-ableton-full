"""Instala el Remote Script AbletonClaude en la User Library de Live y registra el servidor en Claude Code.
Uso: python install.py   (con Live cerrado; despues abre Live y elige AbletonClaude en Control Surface)."""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "server"))
import livepaths  # noqa: E402

lib = livepaths.user_library()
if not lib:
    sys.exit("No encuentro la User Library: abre Live una vez para que cree sus preferencias y vuelve a probar.")
dst = os.path.join(lib, "Remote Scripts", "AbletonClaude")
os.makedirs(dst, exist_ok=True)
shutil.copy2(os.path.join(ROOT, "remote_script", "AbletonClaude", "__init__.py"), dst)
print("Remote Script copiado a", dst)

for tool in ("uv", "ffmpeg", "claude"):
    if not shutil.which(tool):
        print("AVISO: falta '%s' en el PATH" % tool)
if shutil.which("claude"):
    cmd = ["claude", "mcp", "add", "--scope", "user", "ableton", "--", "uv", "run", "--directory",
           os.path.join(ROOT, "server"), "python", "server.py"]
    r = subprocess.run(cmd, capture_output=True, text=True, shell=os.name == "nt")
    print((r.stdout or r.stderr).strip() or "servidor 'ableton' registrado en Claude Code")
print("Ahora: abre Live > Preferencias > Link, Tempo & MIDI > Control Surface: AbletonClaude (reinicia Live si ya estaba).")
