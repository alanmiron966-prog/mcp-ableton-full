"""MCP server: puente entre Claude y el Remote Script AbletonClaude (socket local 127.0.0.1:9877)."""
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from typing import Any, Literal

import analysis
import livepaths
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

HOST = "127.0.0.1"
PORT = int(os.environ.get("ABLETON_CLAUDE_PORT", "9877"))
HOME = os.environ.get("ABLETON_CLAUDE_HOME", os.path.join(os.path.expanduser("~"), ".ableton-mcp"))
PROFILE = os.path.join(HOME, "perfil.json")
PRESETS = os.environ.get("ABLETON_CLAUDE_PRESETS", os.path.join(livepaths.user_library() or HOME, "Claude Presets"))
AUDIO_EXT = (".wav", ".mp3", ".flac", ".aif", ".aiff", ".m4a", ".ogg")

mcp = MCPServer(
    "ableton_mcp",
    instructions=(
        "Controla Ableton Live abierto. Pistas: indice 0.., 'r0' para retornos, 'master'. "
        "Antes de tocar un plugin, mira sus parametros con ableton_device_params. "
        "Para valores reales usa display (ej. '250 Hz', '-3 dB'); el servidor convierte. "
        "Al empezar llama a ableton_status: si trae 'aviso', diselo al usuario antes de seguir. "
        "Al producir, marca las secciones (intro, break, drop, outro) con ableton_locators. "
        "Luego llama a ableton_get_profile. Si plugins_pendientes es true (instalacion nueva o plugins sin "
        "probar), lo primero, antes del onboarding: avisa que vas a analizar sus plugins (unos minutos, con un set "
        "vacio abierto) y llama a ableton_scan_plugins; si Live se cierra con un plugin, que lo abra y vuelve a "
        "llamarla. Despues, si configurado es false, haz el onboarding preguntando solo lo que "
        "este en 'falta', una pregunta cada vez y en este orden: nombre artistico; generos; bpm (recomienda tu un rango "
        "tipico del genero, ej. UK garage 130-138, tech house 124-128, techno 130-140, y que elija); 3 artistas de "
        "referencia (para entender su sonido); 1-3 temas de referencia (enlace de YouTube o ruta de un archivo de audio) "
        "y que le gusta de cada uno. Guardalos con ableton_set_profile y ableton_add_reference. Para mezclar usa solo plugins de 'plugins_listos'. "
        "get_profile tambien trae el resumen de samples y librerias (escaneadas al conectar): para elegir sonidos "
        "usa ableton_find_samples con tipo (kick, clap, hat_closed...) antes que palabras sueltas. "
        "El master se hace en el mismo proyecto de la produccion y la mezcla (cadena en el Main, medir con "
        "ableton_record_master), sin exportar la mezcla ni preguntarlo; solo masteriza aparte si el usuario lo pide. "
        "Si perfil.proyectos tiene alguno, al empezar pregunta antes de nada: seguir con el ultimo (di su nombre, "
        "cuando fue y lo pendiente) o empezar uno nuevo; si sigue y set_abierto es otro, pidele que abra ese set. "
        "Al acabar cada tarea y cuando el usuario se despida, apunta el avance con ableton_save_project. "
        "Al producir: cada sonido en su propia pista MIDI con su Simpler (kick, clap, hat cerrado, hat abierto, "
        "perc... por separado, nunca juntos en un Drum Rack) para procesarlos aparte. Kick y bajo tambien "
        "en pistas separadas, sin agrupar ni enrutar a un bus. Produce siempre en el Arrangement: dibuja los MIDI "
        "con ableton_arrange_clip, nunca clips de Session (create_clip/add_notes solo si el usuario lo pide). "
        "Cuando pidan una cancion, entrega el proyecto terminado sin parar entre fases: 1) produccion de la "
        "cancion entera (intro, breaks sin kick, drops, outro), 2) mezcla (EQ, sidechain, reverb/delay, paneo, "
        "niveles), 3) master en el Main medido contra la referencia con ableton_record_master y "
        "ableton_compare_reference. Como medir exige el set guardado, al empezar pide que lo guarde con nombre "
        "(Ctrl+S) si set_abierto es null. Al final resume que se hizo y que no se pudo comprobar."
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
        err = resp.get("error", "Error desconocido en Ableton")
        if err.startswith("Comando desconocido"):
            err += ". Live tiene cargado un Remote Script viejo: reinicia Live."
        raise ToolError(err)
    return resp["result"]


REPO_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "remote_script", "AbletonClaude",
                           "__init__.py")


def _script_aviso(status: dict) -> str | None:
    """Aviso si el Remote Script que tiene Live no es el del repo (se copio uno nuevo y Live no se reinicio)."""
    try:
        with open(REPO_SCRIPT, "rb") as f:
            repo = hashlib.sha1(f.read().replace(b"\r\n", b"\n")).hexdigest()[:12]
    except OSError:
        return None  # instalado sin el repo: nada con que comparar
    if status.get("script") != repo:
        return "Live tiene cargada otra version del Remote Script: copia la nueva (python install.py) y reinicia Live."
    return None


@mcp.tool(annotations=READ)
async def ableton_status() -> dict:
    """Tempo, si esta sonando, compas, posicion del cabezal (bar) y numero de pistas del proyecto abierto.
    Trae 'aviso' si Live tiene cargado un Remote Script distinto del instalado."""
    st = await call_live("status")
    aviso = _script_aviso(st)
    return {**st, "aviso": aviso} if aviso else st


@mcp.tool(annotations=ADD)
async def ableton_locators(add: list[dict] | None = None, remove: list[float] | None = None) -> list:
    """Marcadores del Arrangement. add=[{"name": "Drop 1", "bar": 49}, ...] crea o renombra (compas 1 = inicio);
    remove=[49, ...] borra los de esos compases. Sin nada solo los lista. Marca cada seccion al producir."""
    if not add and not remove:
        return await call_live("locators")
    back = (await call_live("status"))["bar"]
    for _ in range(2 * (len(add or []) + len(remove or [])) + 1):  # como mucho un ciclo de cabezal por marcador
        r = await call_live("locators", add=add, remove=remove)
        if not (isinstance(r, dict) and "pendiente" in r):
            break
    else:
        raise ToolError("Live no movio el cabezal al compas %s" % r["pendiente"])
    await call_live("locators", seek_bar=back)
    return r


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
async def ableton_device_params(track: Track, device: int | str, match: str | None = None) -> dict:
    """Parametros de un dispositivo (indice o parte del nombre) con su valor visible ('250 Hz').
    match filtra por parte del nombre del parametro (ej. 'Band 1') para no listar cientos."""
    return await call_live("device_params", track=track, device=device, match=match)


@mcp.tool(annotations=WRITE)
async def ableton_set_device_param(
    track: Track, device: int | str, param: int | str, value: float | None = None, display: str | None = None
) -> dict:
    """Cambia un parametro. Usa display con unidades reales ('250 Hz', '-3 dB', '2.5 kHz', '100 ms'),
    el texto de una opcion de lista ('Low Cut', 'Opto') o value interno."""
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
    """Crea un clip MIDI vacio en la vista Session (hueco = escena, 0..). Solo si el usuario pide Session:
    para producir usa ableton_arrange_clip. bars en compases de 4/4.
    replace=True borra el clip que haya en ese hueco: confirma con el usuario si no lo creaste tu."""
    return await call_live("create_clip", track=track, slot=slot, length=bars * 4, name=name, replace=replace)


@mcp.tool(annotations=ADD)
async def ableton_add_notes(track: int, slot: int, notes: list[dict], clear: bool = False) -> dict:
    """Escribe notas en un clip MIDI. notes: [{pitch, start, duration, velocity}] con tiempos en beats
    (1 = negra, 0.25 = semicorchea). Pista con Simpler (un sonido por pista): pitch 60 = sample a su tono.
    En un Drum Rack: 36 kick, 38 snare, 39 clap, 42 hat cerrado, 46 hat abierto. clear=True borra antes las notas."""
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
    """Clips del Arrangement de una pista: nombre, start y end en beats (compas = beats/4 + 1); file en los de audio."""
    return await call_live("arrange_list", track=track)


async def _song_end() -> float:
    """Beat donde acaba el ultimo clip del Arrangement en pistas sin mute (la referencia y Master Rec quedan fuera)."""
    ends = [c["end"] for t in await call_live("list_tracks") if isinstance(t["ref"], int) and not t["mute"]
            for c in await call_live("arrange_list", track=t["ref"])]
    return max(ends, default=0.0)


@mcp.tool(annotations=WRITE)
async def ableton_record_master(from_bar: float = 1, bars: float | None = None) -> dict:
    """Graba la salida del master (con su cadena: limitador incluido) en la pista de audio 'Master Rec' del
    Arrangement, por la entrada Resampling, sin exportar. Live graba en tiempo real: tarda recording_seconds;
    no lances otra grabacion hasta que acabe. Despues ableton_arrange_list(index devuelto) da el
    file del clip: pasalo a ableton_analyze_audio (LUFS, true peak) o ableton_compare_reference.
    Live bloquea el wav hasta cerrar el set (guardar no basta): despues llama a ableton_reload_set antes de medir.
    Al acabar la pista queda muteada para que la toma no se sume al master.
    Sin bars graba hasta el final del ultimo clip (cancion entera con from_bar=1)."""
    start = (from_bar - 1) * 4
    end = start + bars * 4 if bars else await _song_end()
    if end <= start:
        raise ToolError("No hay clips en el Arrangement despues del compas %s" % from_bar)
    return await call_live("record_master", start=start, end=end)


# Guarda (Ctrl+S hasta que el titulo pierda el '*'), cierra Live y reabre el set. Probado a mano el 2026-11-12.
RELOAD_PS = r'''
$ErrorActionPreference = 'Stop'
$dir = $args[0]
$p = Get-Process 'Ableton Live 1*' -ErrorAction SilentlyContinue | Where-Object MainWindowTitle | Select-Object -First 1
if (-not $p) { throw 'Live no esta abierto' }
$name = ($p.MainWindowTitle -split ' - Ableton Live')[0].TrimEnd('*')
$als = Join-Path $dir "$name.als"
if (-not (Test-Path -LiteralPath $als)) { throw "No encuentro $als : guarda el set con nombre en esa carpeta" }
$sh = New-Object -ComObject WScript.Shell
for ($i = 0; $i -lt 6; $i++) {
  $p.Refresh(); if ($p.MainWindowTitle -notmatch '\*') { break }
  [void]$sh.AppActivate($p.Id); Start-Sleep -Milliseconds 500; $sh.SendKeys('^s'); Start-Sleep 2
}
$p.Refresh(); if ($p.MainWindowTitle -match '\*') { throw 'No pude guardar el set: el titulo sigue con *' }
[void]$p.CloseMainWindow()
if (-not $p.WaitForExit(90000)) { throw 'Live no se cerro en 90 s (hay un dialogo abierto?)' }
Start-Process -FilePath $als
Write-Output $als
'''


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True,
                                      openWorldHint=False))
async def ableton_reload_set() -> dict:
    """Guarda el set, cierra Live y lo reabre para que suelte los wav recien grabados (Live los bloquea
    hasta cerrar el set; guardar no basta). Usalo despues de ableton_record_master y antes de medir.
    Tarda 30-120 s y Live desaparece un momento: avisa al usuario. Devuelve la ultima toma lista para medir."""
    if os.name != "nt":
        raise ToolError("ableton_reload_set solo funciona en Windows")
    rec = next((t for t in await call_live("list_tracks") if t["name"] == "Master Rec"), None)
    files = [c["file"] for c in await call_live("arrange_list", track=rec["ref"])] if rec else []
    files = [f for f in files if os.path.isfile(f)]
    if not files:
        raise ToolError("No hay tomas en 'Master Rec': graba antes con ableton_record_master")
    take = max(files, key=os.path.getmtime)
    project = os.path.dirname(os.path.dirname(os.path.dirname(take)))  # <proyecto>\Samples\Recorded\toma.wav
    proc = await asyncio.create_subprocess_exec(
        "powershell", "-NoProfile", "-NonInteractive", "-Command",
        "& {%s} '%s'" % (RELOAD_PS, project.replace("'", "''")),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await asyncio.wait_for(proc.communicate(), 150)
    if proc.returncode:
        raise ToolError("No pude reabrir Live: %s" % err.decode(errors="replace").strip().splitlines()[0])
    for _ in range(90):  # Live tarda en cargar el set y el Remote Script
        await asyncio.sleep(2)
        try:
            await call_live("ping")
            break
        except ToolError:
            pass
    else:
        raise ToolError("Live se reabrio pero AbletonClaude no responde despues de 3 minutos")
    return {"set": out.decode(errors="replace").strip(), "toma": take}


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
    txt = livepaths.library_cfg()
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


_secs: dict = {}
SHOT_MAX = 3.0  # un golpe de kick/bajo/perc mas largo es casi seguro un loop sin "loop" en el nombre
LONG_OK = {"vocal", "fx", "cymbal", "otro"}


def _wav_seconds(path: str) -> float | None:
    """Duracion leyendo solo la cabecera RIFF (byte rate y tamano de 'data'). None si no es wav legible."""
    if path not in _secs:
        d = None
        try:
            with open(path, "rb") as f:
                if f.read(12)[8:] == b"WAVE":
                    rate = None
                    while (h := f.read(8)) and len(h) == 8:
                        cid, size = h[:4], int.from_bytes(h[4:], "little")
                        if cid == b"fmt ":
                            rate = int.from_bytes(f.read(size)[8:12], "little")
                        elif cid == b"data":
                            d = size / rate if rate else None
                            break
                        else:
                            f.seek(size + (size & 1), 1)
        except OSError:
            pass
        _secs[path] = d
    return _secs[path]


def _is_loop(s: dict) -> bool:
    if s["loop"] or s["tipo"] in LONG_OK:
        return s["loop"]
    d = _wav_seconds(s["ruta"])
    return d is not None and d > SHOT_MAX


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
    True solo loops (un golpe de mas de 3 s cuenta como loop). seg = duracion. bpm filtra loops a +-2. Prioriza los generos del perfil."""
    words = query.lower().split()
    generos = [g.lower() for g in _load(PROFILE, {}).get("generos", [])]
    hits = [s for s in _sample_index()
            if (tipo is None or s["tipo"] == tipo)
            and (bpm is None or (s["bpm"] and abs(s["bpm"] - bpm) <= 2))
            and all(w in s["ruta"].lower() for w in words) and _is_loop(s) == loops]
    hits.sort(key=lambda s: -sum(g in s["ruta"].lower() for g in generos))
    out = []
    for s in hits[:limit]:
        d = _wav_seconds(s["ruta"])
        out.append({**{k: v for k, v in s.items() if v is not None}, "loop": loops,
                    **({"seg": round(d, 2)} if d else {})})
    return out


@mcp.tool(annotations=ADD)
async def ableton_load_sample(track: int, ruta: str, pad: int | None = None) -> dict:
    """Carga un sample en una pista MIDI. Sin pad (lo normal: un sonido por pista): crea un Simpler (toca la
    nota 60). Con pad (36 kick, 39 clap, 42 hat cerrado, 46 hat abierto): lo pone en ese pad de un Drum Rack,
    creandolo si falta; solo si el usuario pide un Drum Rack."""
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


TESTS = os.path.join(HOME, "rack_tests.json")
SKIP_PARAMS = ("device on", "bypass")


async def _test_rack(name: str) -> dict:
    """Carga el Rack en una pista temporal, mueve un parametro y mira si el valor visible cambia."""
    t = (await call_live("create_track", kind="audio", name="Claude test"))["index"]
    try:
        await call_live("load_device", track=t, name=name, source="user_library")
        for _ in range(40):  # load_item es asincrono en Live
            if (await call_live("list_tracks"))[t]["devices"]:
                break
            await asyncio.sleep(0.5)
        else:
            return {"status": "no carga"}
        d = await call_live("device_params", track=t, device=0)
        ps = [p for p in d["params"] if p["name"].lower() not in SKIP_PARAMS and p["max"] > p["min"]]
        p = next((p for p in ps if not p["quantized"]), ps[0] if ps else None)
        if p is None:
            return {"device": d["device"], "class": d["class"], "status": "sin parametro movible"}
        v = p["min"] + (p["max"] - p["min"]) * (0.25 if p["value"] > (p["min"] + p["max"]) / 2 else 0.75)
        await call_live("set_device_param", track=t, device=0, param=p["index"], value=v)
        after = (await call_live("device_params", track=t, device=0))["params"][p["index"]]["display"]
        return {"device": d["device"], "class": d["class"], "params": len(d["params"]), "param": p["name"],
                "antes": p["display"], "despues": after,
                "status": "ok" if after != p["display"] else "el parametro no se mueve"}
    finally:
        if (await call_live("list_tracks"))[t]["name"] == "Claude test":  # no borrar una pista del usuario
            await call_live("delete_track", track=t)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True,
                                      openWorldHint=False))
async def ableton_scan_plugins(reescanear: bool = False) -> dict:
    """Primer paso de una instalacion nueva: escanea los VST3, genera su Rack en Claude Presets y prueba cada uno
    en Live (pista temporal 'Claude test' que se borra). Tarda minutos; usa un set vacio. Si Live se cierra con un
    plugin, vuelve a llamarla: ese plugin queda en no_usar y sigue con el resto. reescanear=True rehace el escaneo."""
    if reescanear or not os.path.exists(os.path.join(HOME, "plugins.json")):
        proc = await asyncio.create_subprocess_exec(sys.executable, os.path.join(os.path.dirname(__file__),
                                                                                 "batch_presets.py"),
                                                    stdout=asyncio.subprocess.DEVNULL)
        await proc.wait()
    tests = _load(TESTS, {})
    for k, v in tests.items():
        if v.get("status") == "probando":  # la ultima vez Live se cerro con este plugin
            tests[k] = {"status": "cierra Live"}
    names = [_safe(r["name"]) for r in _load(os.path.join(HOME, "plugins.json"), []) if r.get("status") == "ok"]
    for name in names:
        if name in tests and not reescanear:
            continue
        familia = " ".join(name.split()[:2])
        if any(" ".join(k.split()[:2]) == familia and v["status"].startswith("cierra Live") for k, v in tests.items()):
            tests[name] = {"status": "cierra Live (misma familia)"}  # no tumbar Live una vez por cada Ozone
            continue
        tests[name] = {"status": "probando"}
        _save_json(TESTS, tests)  # si Live se cae aqui, la marca dice que plugin fue
        t0 = time.time()
        try:
            tests[name] = dict(await _test_rack(name), s=round(time.time() - t0, 1))
        except ToolError as e:
            if "No conecto" in str(e) or "cerro la conexion" in str(e):
                tests[name] = {"status": "cierra Live"}
                _save_json(TESTS, tests)
                raise ToolError("Live se cerro al cargar '%s'. Abre Live y vuelve a llamar a ableton_scan_plugins: "
                                "sigue donde quedo." % name)
            tests[name] = {"status": "error: %s" % e}
        _save_json(TESTS, tests)
    _save_json(TESTS, tests)  # tambien las marcas de familia y de 'probando'
    return _inventory()


def _save_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(path + ".tmp", path)


@mcp.tool(annotations=READ)
async def ableton_get_profile() -> dict:
    """Perfil del usuario (nombre, generos, bpm, artistas, referencias) y los plugins listos para usar, por categoria."""
    p = _load(PROFILE, {})
    falta = [k for k in ("nombre", "generos", "bpm", "artistas", "referencias") if not p.get(k)]
    inv = _inventory()
    sin_probar = sum(1 for x in inv["no_usar"] if x["estado"] in ("sin probar", "probando"))
    return {"plugins_pendientes": not os.path.exists(os.path.join(HOME, "plugins.json")) or sin_probar > 0,
            "configurado": not falta, "falta": falta, "perfil": p, "set_abierto": await asyncio.to_thread(_set_name),
            **inv, "samples": _library_summary()}


def _set_name() -> str | None:
    """Nombre del set abierto, del titulo de la ventana de Live ('Nombre* - Ableton Live 12 Suite').
    None si Live esta cerrado, no es Windows o el set no tiene nombre todavia."""
    if os.name != "nt":
        return None  # shortcut: solo Windows lee el titulo; en Mac pasar nombre a mano
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        "[Console]::OutputEncoding=[Text.Encoding]::UTF8; (Get-Process 'Ableton Live 1*' "
                        "-ErrorAction SilentlyContinue | ? MainWindowTitle | select -First 1).MainWindowTitle"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    name = r.stdout.strip().split(" - Ableton Live")[0].rstrip("*").strip()
    return None if name.lower() in ("", "untitled", "sin título", "sin titulo") else name


@mcp.tool(annotations=WRITE)
async def ableton_save_project(resumen: str, pendiente: str = "", nombre: str | None = None) -> dict:
    """Apunta en que va un proyecto para retomarlo otro dia. resumen: que se hizo (genero, bpm, tonalidad, que
    suena ya). pendiente: el siguiente paso. nombre: por defecto el del set abierto en Live; si el set no tiene
    nombre, pide al usuario que lo guarde (Ctrl+S) o pasa uno. Reemplaza la nota anterior del mismo proyecto."""
    nombre = nombre or await asyncio.to_thread(_set_name)
    if not nombre:
        raise ToolError("El set no tiene nombre: pide al usuario que lo guarde con Ctrl+S o pasa nombre")
    p = _load(PROFILE, {})
    projs = [x for x in p.get("proyectos", []) if x["nombre"].lower() != nombre.lower()]
    projs.append({"nombre": nombre, "fecha": time.strftime("%Y-%m-%d %H:%M"), "resumen": resumen, "pendiente": pendiente})
    p["proyectos"] = projs[-10:]  # el ultimo es el mas reciente
    _save_profile(p)
    return projs[-1]


@mcp.tool(annotations=WRITE)
async def ableton_set_profile(nombre: str | None = None, generos: list[str] | None = None,
                              bpm: str | None = None, artistas: list[str] | None = None,
                              notas: str | None = None) -> dict:
    """Guarda datos del perfil. Solo cambia lo que se pasa. bpm: el que eligio o un rango ('132' o '130-134').
    artistas: artistas de referencia de su sonido."""
    p = _load(PROFILE, {})
    for k, v in (("nombre", nombre), ("generos", generos), ("bpm", bpm), ("artistas", artistas), ("notas", notas)):
        if v is not None:
            p[k] = v
    p.setdefault("creado", time.strftime("%Y-%m-%d"))
    _save_profile(p)
    return p


@mcp.tool(annotations=ADD)
async def ableton_add_reference(ruta: str, nota: str = "") -> dict:
    """Anade un tema de referencia al perfil: enlace (YouTube, SoundCloud...) o archivo de audio local.
    Un enlace se mide al momento leyendo el stream, sin guardar el audio. nota: que te gusta de su mezcla."""
    ref = {"ruta": ruta, "nota": nota}
    if re.match(r"https?://", ruta):
        ref["titulo"], ref["medicion"] = await asyncio.to_thread(_measure_url, ruta)
    else:
        ruta = ref["ruta"] = os.path.abspath(os.path.expanduser(ruta))
        if not os.path.isfile(ruta):
            raise ToolError("No existe el archivo: %s" % ruta)
        if not ruta.lower().endswith(AUDIO_EXT):
            raise ToolError("No es un archivo de audio (%s)" % ", ".join(AUDIO_EXT))
    p = _load(PROFILE, {})
    refs = [r for r in p.get("referencias", []) if r["ruta"].lower() != ruta.lower()]
    refs.append(ref)
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


def _measure_url(url: str) -> tuple[str, dict]:
    """Pide a yt-dlp la URL directa del audio y ffmpeg la mide en streaming: no queda archivo en disco.
    La URL directa caduca, por eso la medicion se guarda en el perfil."""
    r = subprocess.run([sys.executable, "-m", "yt_dlp", "-f", "bestaudio/best", "--no-playlist",
                        "--print", "title", "--print", "urls", url],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    lines = r.stdout.strip().splitlines()
    if r.returncode or len(lines) < 2:
        raise ToolError("No pude abrir el enlace: %s" % ((r.stderr.strip().splitlines() or ["yt-dlp fallo"])[-1]))
    try:
        return lines[0], {**analysis.analyze(lines[1]), "archivo": url}
    except Exception as e:
        raise ToolError("No pude medir el audio del enlace: %s" % e)


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
    r = refs[referencia]
    mix, ref = await asyncio.gather(asyncio.to_thread(_measure, ruta),
                                    asyncio.to_thread(lambda: r.get("medicion") or _measure(r["ruta"])))
    return {"mezcla": mix, "referencia": ref, "diferencia": analysis.compare(mix, ref)}


if __name__ == "__main__":
    import threading
    threading.Thread(target=_sample_index, daemon=True).start()  # escanea samples al conectar sin frenar el arranque
    mcp.run()
