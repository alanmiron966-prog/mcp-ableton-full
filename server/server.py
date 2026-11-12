"""MCP server: puente entre Claude y el Remote Script AbletonClaude (socket local 127.0.0.1:9877)."""
import asyncio
import json
import os
import re
import time
from typing import Any, Literal

import analysis
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

HOST = "127.0.0.1"
PORT = int(os.environ.get("ABLETON_CLAUDE_PORT", "9877"))
HOME = os.environ.get("ABLETON_CLAUDE_HOME", os.path.join(os.path.expanduser("~"), ".ableton-mcp"))
PROFILE = os.path.join(HOME, "perfil.json")
PRESETS = os.environ.get("ABLETON_CLAUDE_PRESETS",
                         r"C:\Users\HP_Store\Desktop\samples alan droops\User Library\Claude Presets")
AUDIO_EXT = (".wav", ".mp3", ".flac", ".aif", ".aiff", ".m4a", ".ogg")

mcp = MCPServer(
    "ableton_mcp",
    instructions=(
        "Controla Ableton Live abierto. Pistas: indice 0.., 'r0' para retornos, 'master'. "
        "Antes de tocar un plugin, mira sus parametros con ableton_device_params. "
        "Para valores reales usa display (ej. '250 Hz', '-3 dB'); el servidor convierte. "
        "Al empezar llama a ableton_get_profile: si configurado es false, haz el onboarding preguntando "
        "nombre, generos y 1-3 temas de referencia (ruta de un archivo de audio) y guardalos con "
        "ableton_set_profile y ableton_add_reference. Para mezclar usa solo plugins de 'plugins_listos'. "
        "get_profile tambien trae el resumen de samples y librerias (escaneadas al conectar): para elegir sonidos "
        "usa ableton_find_samples con tipo (kick, clap, hat_closed...) antes que palabras sueltas."
    ),
)

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
ADD = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

Track = int | str
Source = Literal["plugins", "audio_effects", "instruments", "midi_effects", "drums", "sounds", "user_library", "packs", "all"]


async def call_live(type_: str, **params: Any) -> Any:
    # shortcut: una conexion por comando; si se vuelve lento con muchas llamadas, mantener la conexion abierta.
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(HOST, PORT), 3)
    except (OSError, asyncio.TimeoutError):
        raise ToolError(
            "No conecto con Ableton. Abre Live y en Preferencias > Link, Tempo & MIDI elige "
            "'AbletonClaude' como Control Surface."
        )
    try:
        clean = {k: v for k, v in params.items() if v is not None}
        writer.write((json.dumps({"type": type_, "params": clean}) + "\n").encode())
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), 20)
    finally:
        writer.close()
    if not line:
        raise ToolError("Ableton cerro la conexion sin responder.")
    resp = json.loads(line)
    if not resp.get("ok"):
        raise ToolError(resp.get("error", "Error desconocido en Ableton"))
    return resp["result"]


@mcp.tool(annotations=READ)
async def ableton_status() -> dict:
    """Tempo, si esta sonando, compas y numero de pistas del proyecto abierto."""
    return await call_live("status")


@mcp.tool(annotations=READ)
async def ableton_list_tracks() -> list:
    """Todas las pistas (normales, retornos 'rN' y 'master') con volumen, pan, envios, mute/solo y dispositivos."""
    return await call_live("list_tracks")


@mcp.tool(annotations=READ)
async def ableton_meters(seconds: float = 1.0) -> dict:
    """Pico de salida de cada pista (0..1, ~0.92 = 0 dBFS) durante `seconds`. Live debe estar reproduciendo."""
    peaks: dict[str, float] = {}
    for _ in range(max(1, int(seconds * 10))):
        for k, v in (await call_live("meters")).items():
            peaks[k] = max(peaks.get(k, 0.0), v)
        await asyncio.sleep(0.1)
    return peaks


@mcp.tool(annotations=WRITE)
async def ableton_set_mixer(
    track: Track,
    volume_db: float | None = None,
    pan: float | None = None,
    send: int | None = None,
    send_db: float | None = None,
    mute: bool | None = None,
    solo: bool | None = None,
) -> dict:
    """Ajusta el mixer de una pista. volume_db en dB (ej. -6). pan de -1 (izq) a 1 (der).
    send = indice del envio (0 = A) junto con send_db."""
    return await call_live("set_mixer", track=track, volume_db=volume_db, pan=pan,
                         send=send, send_db=send_db, mute=mute, solo=solo)


@mcp.tool(annotations=READ)
async def ableton_list_browser(source: Source = "plugins", query: str = "", limit: int = 200) -> list:
    """Busca en el Browser de Live. source='plugins' lista VST/AU instalados (FabFilter, etc.)."""
    return await call_live("list_browser", source=source, query=query, limit=limit)


@mcp.tool(annotations=ADD)
async def ableton_load_device(track: Track, name: str, source: Source = "plugins") -> dict:
    """Carga un plugin o dispositivo en la pista (al final de su cadena). name admite parte del nombre: 'Pro-Q 4'."""
    if os.path.exists(os.path.join(PRESETS, _safe(name) + ".adg")):
        source = "user_library"  # el Rack de Claude Presets trae los parametros expuestos
    return await call_live("load_device", track=track, name=name, source=source)


@mcp.tool(annotations=ADD)
async def ableton_create_track(kind: Literal["audio", "midi"] = "audio", name: str | None = None) -> dict:
    """Crea una pista nueva al final del proyecto."""
    return await call_live("create_track", kind=kind, name=name)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False,
                                      openWorldHint=False))
async def ableton_delete_track(track: int) -> dict:
    """Borra una pista (se puede deshacer con Ctrl+Z en Live). Confirma con el usuario antes."""
    return await call_live("delete_track", track=track)


@mcp.tool(annotations=READ)
async def ableton_device_params(track: Track, device: int | str) -> dict:
    """Parametros de un dispositivo (indice o parte del nombre) con su valor visible ('250 Hz')."""
    return await call_live("device_params", track=track, device=device)


@mcp.tool(annotations=WRITE)
async def ableton_set_device_param(
    track: Track, device: int | str, param: int | str, value: float | None = None, display: str | None = None
) -> dict:
    """Cambia un parametro. Usa display con unidades reales ('250 Hz', '-3 dB', '2.5 kHz') o value interno."""
    return await call_live("set_device_param", track=track, device=device, param=param, value=value, display=display)


# ---------- produccion: cancion, clips y notas ----------
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


@mcp.tool(annotations=WRITE)
async def ableton_set_song(tempo: float | None = None, numerator: int | None = None, denominator: int | None = None,
                           key: str | None = None, scale: str | None = None) -> dict:
    """Tempo (BPM), compas y tonalidad del proyecto. key: 'C'..'B' con '#' (ej. 'F#').
    scale: nombre de escala de Live ('Major', 'Minor', 'Dorian'...)."""
    root = None
    if key is not None:
        k = key.strip().upper()
        if k not in NOTE_NAMES:  # shortcut: solo sostenidos; anadir bemoles si Claude los pide
            raise ToolError("key debe ser una de %s" % ", ".join(NOTE_NAMES))
        root = NOTE_NAMES.index(k)
    r = await call_live("set_song", tempo=tempo, numerator=numerator, denominator=denominator,
                        root_note=root, scale_name=scale)
    r["key"] = NOTE_NAMES[r["root_note"] % 12]
    return r


@mcp.tool(annotations=ADD)
async def ableton_create_clip(track: int, slot: int = 0, bars: float = 4, name: str | None = None,
                              replace: bool = False) -> dict:
    """Crea un clip MIDI vacio en una pista MIDI (hueco = escena, 0..). bars en compases de 4/4.
    replace=True borra el clip que haya en ese hueco: confirma con el usuario si no lo creaste tu."""
    return await call_live("create_clip", track=track, slot=slot, length=bars * 4, name=name, replace=replace)


@mcp.tool(annotations=ADD)
async def ableton_add_notes(track: int, slot: int, notes: list[dict], clear: bool = False) -> dict:
    """Escribe notas en un clip MIDI. notes: [{pitch, start, duration, velocity}] con tiempos en beats
    (1 = negra, 0.25 = semicorchea). pitch MIDI en Drum Rack: 36 kick, 38 snare, 39 clap, 42 hat cerrado,
    46 hat abierto. clear=True borra antes las notas del clip."""
    return await call_live("add_notes", track=track, slot=slot, notes=notes, clear=clear)


@mcp.tool(annotations=READ)
async def ableton_get_notes(track: int, slot: int) -> dict:
    """Notas de un clip MIDI (pitch, start, duration, velocity), su duracion y zona de loop en beats."""
    return await call_live("get_notes", track=track, slot=slot)


@mcp.tool(annotations=WRITE)
async def ableton_clip_props(track: int, slot: int, name: str | None = None, bars: float | None = None) -> dict:
    """Renombra un clip o cambia su duracion de loop (bars en compases de 4/4)."""
    return await call_live("clip_props", track=track, slot=slot, name=name,
                           length=None if bars is None else bars * 4)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True,
                                      openWorldHint=False))
async def ableton_delete_clip(track: int, slot: int) -> dict:
    """Borra un clip (Ctrl+Z en Live lo recupera). Confirma con el usuario si no lo creaste tu."""
    return await call_live("delete_clip", track=track, slot=slot)


@mcp.tool(annotations=WRITE)
async def ableton_play(track: int | None = None, slot: int | None = None, stop: bool = False,
                       from_bar: float | None = None) -> dict:
    """Reproduce: con track y slot lanza ese clip de Session; from_bar (1 = inicio) para los clips de Session
    y toca el Arrangement desde ese compas; sin nada arranca el transporte. stop=True para todo."""
    pos = None if from_bar is None else (from_bar - 1) * 4
    return await call_live("play", track=track, slot=slot, stop=stop, arrangement=pos)


# ---------- arrangement (linea de tiempo) ----------
@mcp.tool(annotations=WRITE)
async def ableton_arrange_clip(track: int, bar: float, bars: float, notes: list[dict], name: str | None = None) -> dict:
    """Dibuja un clip MIDI en el Arrangement desde el compas `bar` (1 = inicio) con `bars` compases de 4/4.
    notes como en ableton_add_notes, con start en beats relativo al inicio del clip (puede pasar de 16).
    Borra los clips del Arrangement que pise ese tramo en esa pista."""
    return await call_live("arrange_clip", track=track, start=(bar - 1) * 4, length=bars * 4, notes=notes, name=name)


@mcp.tool(annotations=WRITE)
async def ableton_arrange_automation(track: int | str, device: str | int, param: str | int,
                                     points: list[dict]) -> dict:
    """Graba automatizacion en el Arrangement. Live la graba en tiempo real: reproduce desde un compas
    antes del primer punto hasta el ultimo, asi que tarda lo que dure el tramo (recording_seconds); no
    lances otra hasta que termine. device: indice o nombre, o "mixer" con param "volume", "pan", "send 0".
    points: [{"bar": compas (1 = inicio, admite decimales), "display": "-12 dB" | "800 Hz"} o {"bar", "value"}];
    rampa lineal entre puntos. Mira los parametros antes con ableton_device_params."""
    pts = [{**{k: v for k, v in x.items() if k != "bar"}, "beat": (x["bar"] - 1) * 4} for x in points]
    return await call_live("arrange_automation", track=track, device=device, param=param, points=pts)


@mcp.tool(annotations=READ)
async def ableton_arrange_list(track: int | str) -> list:
    """Clips del Arrangement de una pista: nombre, start y end en beats (compas = beats/4 + 1)."""
    return await call_live("arrange_list", track=track)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True,
                                      openWorldHint=False))
async def ableton_arrange_clear(track: int | str, from_bar: float | None = None, to_bar: float | None = None) -> dict:
    """Borra clips del Arrangement de una pista (todos, o los que toquen el tramo de compases). Ctrl+Z los recupera.
    Confirma con el usuario si no los creaste tu."""
    return await call_live("arrange_clear", track=track,
                           start=None if from_bar is None else (from_bar - 1) * 4,
                           end=None if to_bar is None else (to_bar - 1) * 4)


# ---------- sonidos: samples de las carpetas del usuario ----------
def _user_folders() -> dict:
    """{ruta: nombre en Places} desde el Library.cfg mas reciente de Live."""
    base = os.path.join(os.environ.get("APPDATA", ""), "Ableton")
    cfgs = [os.path.join(base, d, "Preferences", "Library.cfg") for d in (os.listdir(base) if os.path.isdir(base) else [])]
    cfgs = sorted((c for c in cfgs if os.path.isfile(c)), key=os.path.getmtime)
    if not cfgs:
        return {}
    txt = open(cfgs[-1], encoding="utf-8", errors="replace").read()
    return {os.path.normpath(p): n for p, n in re.findall(r'<UserFolderInfo Id="\d+" Path="([^"]+)" DisplayName="([^"]*)"', txt)}


# orden = prioridad dentro de un mismo nombre: "vocal_shot_wrd_kick" es vocal, "synth_bass" es bass
TIPOS = [
    ("vocal", {"vocal", "vocals", "vox", "voc", "acapella", "wrd", "phrs", "chant", "laugh", "laughs", "spoken"}),
    ("fx", {"fx", "sfx", "riser", "risers", "impact", "impacts", "sweep", "uplifter", "downlifter", "noise", "fxs", "efx", "efxlp",
            "buildup"}),
    ("kick", {"kick", "kicks", "kik", "bd"}),
    ("clap", {"clap", "claps", "snap", "snaps"}),
    ("snare", {"snare", "snares", "snr", "rim", "rimshot"}),
    ("hat", {"hat", "hats", "hihat", "hihats", "hh", "chh", "ohh", "openhat"}),
    ("cymbal", {"crash", "ride", "cymbal"}),
    ("perc", {"perc", "percs", "percussion", "tom", "toms", "shaker", "conga", "bongo", "tambourine", "cowbell", "top",
              "tops", "prc", "prclp"}),
    ("bass", {"bass", "sub", "808", "reese"}),
    ("synth", {"synth", "chord", "chords", "pad", "pads", "lead", "piano", "keys", "stab", "stabs", "arp", "pluck",
               "melody", "melodic", "hook", "hooks", "guitar", "syn", "synlp", "brass", "organ",
               "melodies", "music"}),
    ("drums", {"drum", "drums", "drm", "drmlp", "drumloop", "drumloops", "break", "breaks", "fill", "fills"}),
]
_KEY = re.compile(r"^([a-g][#b]?)(m|min|minor|maj|major)?$")
_index: list | None = None


def _classify(rel: str) -> dict:
    """Tipo, loop, bpm y tonalidad a partir de la ruta relativa (nombre primero, luego carpetas de dentro afuera)."""
    levels = [[t.rstrip("0123456789") or t for t in re.findall(r"[a-z0-9#]+", p)] for p in os.path.splitext(rel.lower())[0].split(os.sep)]
    tipo = "otro"
    for toks in reversed(levels):
        tipo = next((t for t, kw in TIPOS if kw & set(toks)), None)
        if tipo:
            if tipo == "hat":
                tipo = "hat_open" if {"open", "oh", "ohh", "openhat"} & set(toks) else "hat_closed"
            break
    tipo = tipo or "otro"
    name = levels[-1]
    loop = any("loop" in t or t in {"lp", "lps", "fill", "fills"} for toks in levels for t in toks)
    bpm = next((int(m.group(1)) for m in [re.match(r"^(\d{2,3})(bpm)?$", t) for t in name] if m and 60 <= int(m.group(1)) <= 200), None)
    key = next((m.group(1).upper() + ("m" if m.group(2) in ("m", "min", "minor") else "") for m in map(_KEY.match, name) if m), None)
    return {"tipo": tipo, "loop": loop, "bpm": bpm, "key": key}


def _sample_index(force: bool = False) -> list:
    """Escanea una vez por sesion todas las carpetas de Places y clasifica cada sample."""
    global _index
    if _index is None or force:
        idx = []  # se asigna al final: una llamada a mitad de escaneo no ve la lista a medias
        for root in _user_folders():
            for dirpath, _, files in os.walk(root):
                for f in files:
                    if f.lower().endswith(AUDIO_EXT):
                        path = os.path.join(dirpath, f)
                        rel = os.path.relpath(path, root)
                        lib = rel.split(os.sep)[0] if os.sep in rel else os.path.basename(root)
                        idx.append({"ruta": path, "libreria": lib, **_classify(rel)})
        _index = idx
    return _index


def _library_summary() -> dict:
    idx = _sample_index()
    por_tipo, libs = {}, {}
    for s in idx:
        k = s["tipo"] + ("_loop" if s["loop"] else "")
        por_tipo[k] = por_tipo.get(k, 0) + 1
        libs[s["libreria"]] = libs.get(s["libreria"], 0) + 1
    return {"total": len(idx), "por_tipo": dict(sorted(por_tipo.items())),
            "librerias": dict(sorted(libs.items(), key=lambda kv: -kv[1]))}


@mcp.tool(annotations=READ)
async def ableton_scan_samples() -> dict:
    """Reescanea las carpetas de Places (si el usuario anadio librerias) y devuelve el resumen por tipo y libreria."""
    _sample_index(force=True)
    return _library_summary()


@mcp.tool(annotations=READ)
async def ableton_find_samples(query: str = "", tipo: str | None = None, loops: bool = False,
                               bpm: int | None = None, limit: int = 30) -> list:
    """Busca samples ya clasificados. tipo: kick, clap, snare, hat_closed, hat_open, cymbal, perc, bass, synth,
    vocal, fx, drums (loops/fills de bateria completa), otro. query filtra por palabras en la ruta ('tech house', 'toolroom'). loops=False solo one-shots,
    True solo loops. bpm filtra loops a +-2. Prioriza los generos del perfil."""
    words = query.lower().split()
    generos = [g.lower() for g in _load(PROFILE, {}).get("generos", [])]
    hits = [s for s in _sample_index()
            if (tipo is None or s["tipo"] == tipo) and s["loop"] == loops
            and (bpm is None or (s["bpm"] and abs(s["bpm"] - bpm) <= 2))
            and all(w in s["ruta"].lower() for w in words)]
    hits.sort(key=lambda s: -sum(g in s["ruta"].lower() for g in generos))
    return [{k: v for k, v in s.items() if v is not None} for s in hits[:limit]]


@mcp.tool(annotations=ADD)
async def ableton_load_sample(track: int, ruta: str, pad: int | None = None) -> dict:
    """Carga un sample en una pista MIDI. Sin pad: crea un Simpler (toca la nota 60). Con pad (36 kick,
    39 clap, 42 hat cerrado, 46 hat abierto): lo pone en ese pad de un Drum Rack, creandolo si falta."""
    ruta = os.path.normpath(ruta)
    for root, name in _user_folders().items():
        if ruta.lower().startswith(root.lower() + os.sep):
            parts = os.path.relpath(ruta, root).split(os.sep)
            try:
                return await call_live("load_sample", track=track, root=name, parts=parts, pad=pad)
            except ToolError as e:
                if pad is None or "No hay Drum Rack" not in str(e):
                    raise
                await call_live("load_device", track=track, name="Drum Rack", source="instruments")
                return await call_live("load_sample", track=track, root=name, parts=parts, pad=pad)
    raise ToolError("El sample tiene que estar en una carpeta de Places de Live: %s" % list(_user_folders()))


# ---------- perfil y onboarding ----------
def _safe(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip(" .")  # igual que batch_presets.safe_name


def _load(path: str, default: Any) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save_profile(p: dict) -> None:
    os.makedirs(HOME, exist_ok=True)
    tmp = PROFILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PROFILE)  # atomico: un corte no deja el perfil a medias


def _inventory() -> dict:
    """Plugins con Rack generado y probado en Live, por categoria VST3; el resto en no_usar."""
    tests = _load(os.path.join(HOME, "rack_tests.json"), {})
    ready: dict[str, list] = {}
    bad = []
    for row in _load(os.path.join(HOME, "plugins.json"), []):
        if row.get("status") != "ok":
            continue
        st = tests.get(_safe(row["name"]), {}).get("status", "sin probar")
        if st == "ok" or st == "sin parametro movible":  # los medidores no tienen nada que mover
            cat = row.get("sub", "").replace("Fx|", "").replace("Fx", "") or "Otros"
            ready.setdefault(cat, []).append(row["name"])
        else:
            bad.append({"plugin": row["name"], "estado": st})
    return {"plugins_listos": ready, "no_usar": bad}


@mcp.tool(annotations=READ)
async def ableton_get_profile() -> dict:
    """Perfil del usuario (nombre, generos, referencias) y los plugins listos para usar, por categoria."""
    p = _load(PROFILE, {})
    falta = [k for k in ("nombre", "generos", "referencias") if not p.get(k)]
    return {"configurado": not falta, "falta": falta, "perfil": p, **_inventory(), "samples": _library_summary()}


@mcp.tool(annotations=WRITE)
async def ableton_set_profile(nombre: str | None = None, generos: list[str] | None = None,
                              notas: str | None = None) -> dict:
    """Guarda datos del perfil. Solo cambia lo que se pasa."""
    p = _load(PROFILE, {})
    for k, v in (("nombre", nombre), ("generos", generos), ("notas", notas)):
        if v is not None:
            p[k] = v
    p.setdefault("creado", time.strftime("%Y-%m-%d"))
    _save_profile(p)
    return p


@mcp.tool(annotations=ADD)
async def ableton_add_reference(ruta: str, nota: str = "") -> dict:
    """Anade un tema de referencia (archivo de audio local) al perfil. nota: que te gusta de su mezcla."""
    ruta = os.path.abspath(os.path.expanduser(ruta))
    if not os.path.isfile(ruta):
        raise ToolError("No existe el archivo: %s" % ruta)
    if not ruta.lower().endswith(AUDIO_EXT):
        raise ToolError("No es un archivo de audio (%s)" % ", ".join(AUDIO_EXT))
    p = _load(PROFILE, {})
    refs = [r for r in p.get("referencias", []) if r["ruta"].lower() != ruta.lower()]
    refs.append({"ruta": ruta, "nota": nota})
    p["referencias"] = refs
    p.setdefault("creado", time.strftime("%Y-%m-%d"))
    _save_profile(p)
    return {"referencias": refs}


# ---------- medicion ----------
def _measure(ruta: str) -> dict:
    try:
        return analysis.analyze(os.path.abspath(os.path.expanduser(ruta)))
    except FileNotFoundError:
        raise ToolError("No existe el archivo: %s" % ruta)
    except Exception as e:
        raise ToolError("No pude medir %s: %s" % (ruta, e))


@mcp.tool(annotations=READ)
async def ableton_analyze_audio(ruta: str) -> dict:
    """Mide un archivo de audio: LUFS integrado, LRA, true peak (dBTP), PLR, balance por bandas
    (dB respecto al total: sub, bajo, medios_bajos, medios, presencia, aire), correlacion L/R y ancho (side-mid dB)."""
    return await asyncio.to_thread(_measure, ruta)


@mcp.tool(annotations=READ)
async def ableton_compare_reference(ruta: str, referencia: int = 0) -> dict:
    """Mide una mezcla (archivo exportado) y la compara con una referencia del perfil (indice, 0 = la primera).
    Devuelve las dos mediciones, las diferencias (positivo = la mezcla tiene mas) y notas de que corregir."""
    refs = _load(PROFILE, {}).get("referencias", [])
    if not refs:
        raise ToolError("El perfil no tiene referencias. Anade una con ableton_add_reference.")
    if not 0 <= referencia < len(refs):
        raise ToolError("Solo hay %d referencias (indices 0..%d)" % (len(refs), len(refs) - 1))
    mix, ref = await asyncio.gather(asyncio.to_thread(_measure, ruta),
                                    asyncio.to_thread(_measure, refs[referencia]["ruta"]))
    return {"mezcla": mix, "referencia": ref, "diferencia": analysis.compare(mix, ref)}


if __name__ == "__main__":
    import threading
    threading.Thread(target=_sample_index, daemon=True).start()  # escanea samples al conectar sin frenar el arranque
    mcp.run()
