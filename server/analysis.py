"""Mide un archivo de audio con un solo pase de ffmpeg: LUFS integrado, rango (LRA), true peak,
balance tonal por bandas (dB relativos al total) y estereo (correlacion y ancho side/mid)."""
import math
import os
import re
import subprocess

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
# bandas pensadas para musica electronica: (nombre, desde Hz, hasta Hz)
BANDS = [("sub", 20, 60), ("bajo", 60, 150), ("medios_bajos", 150, 500), ("medios", 500, 2000),
         ("presencia", 2000, 6000), ("aire", 6000, 20000)]


def _graph():
    n = len(BANDS) + 4
    parts = ["[0:a]aformat=channel_layouts=stereo,asplit=%d%s" % (n, "".join("[s%d]" % i for i in range(n)))]
    stats = "astats@{0}=measure_perchannel=none:measure_overall=RMS_level+Peak_level,anullsink"
    parts.append("[s0]ebur128=peak=true[out]")
    parts.append("[s1]pan=mono|c0=0.5*c0+0.5*c1," + stats.format("full"))
    for i, (name, lo, hi) in enumerate(BANDS, 2):
        # dos filtros de 2 polos en cada lado = pendiente de 24 dB/oct, bandas separadas sin mucho solape
        parts.append("[s%d]pan=mono|c0=0.5*c0+0.5*c1,highpass=f=%d,highpass=f=%d,lowpass=f=%d,lowpass=f=%d,%s"
                     % (i, lo, lo, hi, hi, stats.format(name)))
    parts.append("[s%d]pan=mono|c0=0.5*c0+0.5*c1,%s" % (n - 2, stats.format("mid")))
    parts.append("[s%d]pan=mono|c0=0.5*c0-0.5*c1,%s" % (n - 1, stats.format("side")))
    return ";".join(parts)


def _num(s):
    return float("-inf") if "inf" in s else float(s)


def parse(log):
    """Saca los valores del log de ffmpeg. Separado de analyze() para poder probarlo sin audio."""
    # con measure_perchannel=none cada astats solo imprime su linea Overall de RMS
    rms = {n: _num(v) for n, v in re.findall(r"\[astats@(\w+) @ [^\]]+\] RMS level dB: (\S+)", log)}
    summary = log[log.rfind("Summary:"):]
    get = lambda pat: _num(re.search(pat, summary, re.S).group(1))  # noqa: E731
    out = {"lufs": get(r"Integrated loudness:.*?I:\s+(\S+) LUFS"),
           "lra": get(r"Loudness range:.*?LRA:\s+(\S+) LU"),
           "true_peak_dbtp": get(r"True peak:.*?Peak:\s+(\S+) dBFS"),
           "rms_db": round(rms["full"], 2)}
    out["plr"] = round(out["true_peak_dbtp"] - out["lufs"], 2)  # peak to loudness: cuanto aplastado esta
    out["bandas_db"] = {n: round(rms[n] - rms["full"], 2) for n, _, _ in BANDS}
    m2, s2 = 10 ** (rms["mid"] / 10), 10 ** (rms["side"] / 10)
    # con M=(L+R)/2 y S=(L-R)/2: correlacion L/R = (M^2-S^2)/(M^2+S^2)
    out["correlacion"] = round((m2 - s2) / (m2 + s2), 3) if m2 + s2 else 0.0
    out["ancho_db"] = round(rms["side"] - rms["mid"], 2) if s2 else float("-inf")  # side respecto a mid
    return out


def analyze(path):
    if not re.match(r"https?://", path) and not os.path.isfile(path):  # ffmpeg tambien lee streams http
        raise FileNotFoundError(path)
    r = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", path, "-filter_complex", _graph(), "-map", "[out]", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0:
        raise RuntimeError((r.stderr.strip().splitlines() or ["ffmpeg fallo"])[-1])
    res = parse(r.stderr)
    res["archivo"] = os.path.basename(path)
    return res


def compare(mix, ref):
    """Diferencias mezcla - referencia y que significan. Positivo = la mezcla tiene mas."""
    d = {"lufs": round(mix["lufs"] - ref["lufs"], 2), "true_peak": round(mix["true_peak_dbtp"] - ref["true_peak_dbtp"], 2),
         "plr": round(mix["plr"] - ref["plr"], 2), "lra": round(mix["lra"] - ref["lra"], 2),
         "correlacion": round(mix["correlacion"] - ref["correlacion"], 3),
         "ancho_db": round(mix["ancho_db"] - ref["ancho_db"], 2) if math.isfinite(mix["ancho_db"] - ref["ancho_db"]) else None,
         "bandas_db": {k: round(mix["bandas_db"][k] - ref["bandas_db"][k], 2) for k in ref["bandas_db"]}}
    notas = []
    if abs(d["lufs"]) >= 1:
        notas.append("%.1f LU %s que la referencia" % (abs(d["lufs"]), "mas fuerte" if d["lufs"] > 0 else "mas baja"))
    if mix["true_peak_dbtp"] > -0.5:
        notas.append("true peak %.2f dBTP: riesgo de clipping al convertir a mp3/streaming" % mix["true_peak_dbtp"])
    if d["plr"] <= -2:
        notas.append("mas comprimida/limitada que la referencia (PLR %.1f dB menos)" % -d["plr"])
    elif d["plr"] >= 2:
        notas.append("mas dinamica que la referencia (PLR %.1f dB mas)" % d["plr"])
    for k, v in d["bandas_db"].items():
        if abs(v) >= 2:  # shortcut: umbral fijo de 2 dB; ajustarlo por banda si da falsos avisos
            notas.append("%s: %+.1f dB respecto a la referencia" % (k, v))
    if mix["correlacion"] < 0.2:
        notas.append("correlacion %.2f: problemas de fase/mono probables" % mix["correlacion"])
    if d["ancho_db"] is not None and abs(d["ancho_db"]) >= 3:
        notas.append("imagen estereo %s que la referencia" % ("mas ancha" if d["ancho_db"] > 0 else "mas estrecha"))
    d["notas"] = notas or ["muy parecida a la referencia en todo lo medido"]
    return d
