"""Escanea todos los VST3 y genera un Rack (.adg) por efecto en 'Claude Presets' de la User Library.
Cada plugin se escanea en un subproceso con tiempo limite: uno que se cuelga o se rompe no para el resto.
Uso: python batch_presets.py [--fallidos] [carpeta_vst3] [carpeta_salida]. --fallidos: solo reintenta lo que no salio ok. Informe en ~/.ableton-mcp/plugins.json."""
import json
import os
import re
import subprocess
import sys

import livepaths
import preset_gen

VST3_DIR = r"C:\Program Files\Common Files\VST3"
REPORT = os.path.join(os.path.expanduser("~"), ".ableton-mcp", "plugins.json")
OUT_DIR = os.environ.get("ABLETON_CLAUDE_PRESETS",
                         os.path.join(livepaths.user_library() or os.path.dirname(REPORT), "Claude Presets"))
TIMEOUT = 60
SCANNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vst3_scan.py")


def find_plugins(root):
    for dirpath, dirs, files in os.walk(root):
        # un bundle .vst3 es una carpeta: se cuenta entero y no se entra en el
        for d in [d for d in dirs if d.lower().endswith(".vst3")]:
            dirs.remove(d)
            yield os.path.join(dirpath, d)
        for f in files:
            if f.lower().endswith(".vst3"):
                yield os.path.join(dirpath, f)


def safe_name(name):
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip(" .")


def main(vst3_dir=VST3_DIR, out_dir=OUT_DIR, only_failed=False):
    report, paths = [], sorted(find_plugins(vst3_dir))
    if only_failed and os.path.exists(REPORT):
        with open(REPORT, encoding="utf-8") as f:
            old = json.load(f)
        report = [x for x in old if x.get("status") == "ok" or x.get("status", "").startswith("saltado")]
        done = {x["file"] for x in report}
        paths = [p for p in paths if p not in done]
    for n, path in enumerate(paths, 1):
        row = {"file": path}
        try:
            r = subprocess.run([sys.executable, SCANNER, path], capture_output=True, timeout=TIMEOUT,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if r.returncode != 0:
                raise RuntimeError((r.stderr.decode("utf-8", "replace").strip().splitlines() or ["fallo"])[-1])
            entries = json.loads(r.stdout.decode("utf-8", "replace"))
        except subprocess.TimeoutExpired:
            entries, row["status"] = [], "timeout"
        except Exception as e:
            entries, row["status"] = [], "error: %s" % e
        for e in entries:
            item = dict(row, name=e["name"], sub=e["sub"], params=len(e["params"]))
            if "Instrument" in e["sub"] or "Fx" not in e["sub"]:
                item["status"] = "saltado: no es efecto"  # shortcut: instrumentos necesitan Instrument Rack
            elif not e["params"]:
                item["status"] = "saltado: sin parametros"
            else:
                item["preset"] = preset_gen.write_adg(e, os.path.join(out_dir, safe_name(e["name"]) + ".adg"))
                item["status"] = "ok"
            report.append(item)
        if not entries:
            report.append(row)
        print("[%d/%d] %s: %s" % (n, len(paths), os.path.basename(path),
                                  ", ".join(x.get("status", "?") for x in report if x["file"] == path)), flush=True)
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    ok = sum(1 for x in report if x.get("status") == "ok")
    print("Presets generados: %d. Informe: %s" % (ok, REPORT))
    return report


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--fallidos"]
    main(*args[:2], only_failed="--fallidos" in sys.argv)
