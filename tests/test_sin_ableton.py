"""Prueba sin Ableton: stubs de Live, conversion de valores y viaje MCP -> socket -> Remote Script."""
import asyncio
import math
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- stubs de los modulos que solo existen dentro de Live ---
fw = types.ModuleType("_Framework")
cs = types.ModuleType("_Framework.ControlSurface")


class ControlSurface:
    def __init__(self, c): pass
    def show_message(self, m): pass
    def log_message(self, m): pass
    def disconnect(self): pass
    def schedule_message(self, delay, fn): fn()  # en la prueba, ejecutar al momento


cs.ControlSurface = ControlSurface
sys.modules.update({"_Framework": fw, "_Framework.ControlSurface": cs, "Live": types.ModuleType("Live")})
sys.path.insert(0, os.path.join(ROOT, "remote_script"))
sys.path.insert(0, os.path.join(ROOT, "server"))
import AbletonClaude as rs  # noqa: E402


class Param:
    """Imita un parametro de Live: valor interno 0..1, display segun funcion."""
    def __init__(self, name, fmt):
        self.name, self.min, self.max, self.value = name, 0.0, 1.0, 0.5
        self.is_quantized, self.is_enabled, self._fmt = False, True, fmt
    def str_for_value(self, v): return self._fmt(v)


def vol_fmt(v):  # curva tipo Live: 0 -> -inf, 0.85 -> 0 dB, 1 -> +6 dB
    if v <= 0: return "-inf dB"
    db = 6 * (v - 0.85) / 0.15 if v >= 0.85 else 40 * math.log10(v / 0.85)
    return "%.1f dB" % db


def freq_fmt(v):  # 10 Hz .. 30 kHz logaritmico, como un EQ
    f = 10 * (3000 ** v)
    return "%.2f kHz" % (f / 1000) if f >= 1000 else "%.1f Hz" % f


# 1. parseo
assert rs._parse_display("2.50 kHz") == 2500.0
assert rs._parse_display("-6.0 dB") == -6.0
assert rs._parse_display("-inf dB") == float("-inf")
assert rs._parse_display("C") is None

# 2. biseccion por valor visible
p = Param("Volume", vol_fmt)
assert rs.AbletonClaude._set_param(p, display="-6")["display"] == "-6.0 dB"
q = Param("Band 1 Frequency", freq_fmt)
assert rs.AbletonClaude._set_param(q, display="250 Hz")["display"] == "250.0 Hz"
assert rs.AbletonClaude._set_param(q, display="2.5 kHz")["display"] == "2.50 kHz"
q.is_enabled = False
try:
    rs.AbletonClaude._set_param(q, value=0.3); raise SystemExit("deberia fallar con parametro bloqueado")
except ValueError:
    pass


# 3. viaje completo con una cancion falsa
class Obj:
    def __init__(self, **kw): self.__dict__.update(kw)


class Clip:
    def __init__(self, length):
        self.name, self.length, self.loop_start, self.loop_end, self.end_marker, self.notes = "", length, 0.0, length, length, []
    def add_new_notes(self, specs): self.notes += [Obj(**s.__dict__) for s in specs]
    def get_notes_extended(self, p, ps, t, ts): return [n for n in self.notes if t <= n.start_time < t + ts]
    def remove_notes_extended(self, p, ps, t, ts): self.notes = []


class Slot:
    clip = None
    has_clip = property(lambda self: self.clip is not None)
    def create_clip(self, length): self.clip = Clip(length)
    def delete_clip(self): self.clip = None
    def fire(self): pass


sys.modules["Live"].Clip = Obj(MidiNoteSpecification=lambda **kw: Obj(**kw))


def track(name):
    mixer = Obj(volume=Param("Volume", vol_fmt), panning=Param("Pan", lambda v: "C"), sends=[])
    return Obj(name=name, mixer_device=mixer, devices=[], mute=False, solo=False, has_midi_input=True,
               output_meter_left=0.5, output_meter_right=0.7, clip_slots=[Slot()], arrangement_clips=[])


def _arr_clip(t, start, length):
    c = Clip(length); c.start_time, c.end_time = start, start + length
    t.arrangement_clips.append(c); return c


song = Obj(tempo=126.0, is_playing=False, tracks=[track("Kick"), track("Bass")], return_tracks=[],
           master_track=track("Master"), signature_numerator=4, signature_denominator=4, view=Obj(),
           root_note=0, scale_name="Major")
for _t in song.tracks:
    _t.create_midi_clip = lambda st, ln, t=_t: _arr_clip(t, st, ln)
    _t.delete_clip = lambda c, t=_t: t.arrangement_clips.remove(c)
song.create_scene = lambda i: [t.clip_slots.append(Slot()) for t in song.tracks]
rs.PORT = 9988
os.environ["ABLETON_CLAUDE_PORT"] = "9988"
rs.HOST = "127.0.0.1"
rs.AbletonClaude.song = lambda self: song
surface = rs.AbletonClaude(None)
import json, tempfile  # noqa: E402,E401
TMP = tempfile.mkdtemp()
os.environ["ABLETON_CLAUDE_HOME"] = TMP
with open(os.path.join(TMP, "plugins.json"), "w") as f:
    json.dump([{"name": "Pro-Q 4", "sub": "Fx|EQ", "status": "ok"}, {"name": "Ozone 11 Imager", "sub": "Fx", "status": "ok"},
               {"name": "Serum", "sub": "Instrument", "status": "saltado: no es efecto"}], f)
with open(os.path.join(TMP, "rack_tests.json"), "w") as f:
    json.dump({"Pro-Q 4": {"status": "ok"}, "Ozone 11 Imager": {"status": "cierra Live"}}, f)
import server  # noqa: E402

# libreria de samples falsa: la clasificacion sale del nombre y de las carpetas
LIB = os.path.join(TMP, "LIB")
for rel in ["Pack/Words/hhvt_c_vocal_shot_wrd_kick.wav", "Pack/Kicks/Kick 01.wav",
            "Pack/Hats_Open/OH_02.wav", "Pack/Bass_Loops/synth_bass_loop_125_Fm.wav", "Pack/notas.txt"]:
    rel = os.path.normpath(rel)
    os.makedirs(os.path.dirname(os.path.join(LIB, rel)), exist_ok=True)
    open(os.path.join(LIB, rel), "wb").close()
server._user_folders = lambda: {LIB: "LIB"}


async def main():
    assert (await server.ableton_status())["tempo"] == 126.0
    assert (await server.ableton_set_mixer(track=1, volume_db=-3))["volume"] == "-3.0 dB"
    tracks = await server.ableton_list_tracks()
    assert [t["name"] for t in tracks] == ["Kick", "Bass", "Master"] and tracks[1]["volume"] == "-3.0 dB"
    assert (await server.ableton_meters(seconds=0.1))["0"] == 0.7
    try:
        await server.ableton_device_params(track=0, device="Pro-Q")
        raise SystemExit("deberia fallar: no hay dispositivos")
    except Exception as e:
        assert "No hay dispositivo" in str(e), e
    # onboarding: perfil vacio -> pide datos; plugins que cierran Live no se ofrecen
    prof = await server.ableton_get_profile()
    assert not prof["configurado"] and prof["falta"] == ["nombre", "generos", "referencias"]
    assert prof["samples"]["total"] == 4 and prof["samples"]["por_tipo"]["vocal"] == 1, prof["samples"]
    assert [os.path.basename(x["ruta"]) for x in await server.ableton_find_samples(tipo="kick")] == ["Kick 01.wav"]
    assert (await server.ableton_find_samples(tipo="hat_open"))[0]["libreria"] == "Pack"
    b = await server.ableton_find_samples(tipo="bass", loops=True, bpm=126)
    assert (b[0]["bpm"], b[0]["key"]) == (125, "Fm") and not await server.ableton_find_samples(tipo="bass", bpm=126)
    assert prof["plugins_listos"] == {"EQ": ["Pro-Q 4"]} and prof["no_usar"][0]["plugin"] == "Ozone 11 Imager"
    await server.ableton_set_profile(nombre="Alan", generos=["techno"])
    ref = os.path.join(TMP, "ref.wav")
    open(ref, "wb").close()
    await server.ableton_add_reference(ref, nota="graves")
    await server.ableton_add_reference(ref, nota="graves y voz")  # misma ruta: se reemplaza, no se duplica
    for bad in (os.path.join(TMP, "no.wav"), os.path.join(TMP, "plugins.json")):
        try:
            await server.ableton_add_reference(bad); raise SystemExit("deberia rechazar %s" % bad)
        except Exception as e:
            assert "No " in str(e), e
    prof = await server.ableton_get_profile()
    assert prof["configurado"] and prof["perfil"]["referencias"] == [{"ruta": ref, "nota": "graves y voz"}]
    # produccion: tempo/tonalidad, clip en un hueco que aun no existe (crea escena), notas, no pisar clips
    s = await server.ableton_set_song(tempo=126, key="f#", scale="Minor")
    assert (s["tempo"], s["key"], s["scale_name"]) == (126.0, "F#", "Minor")
    c = await server.ableton_create_clip(track=0, slot=2, bars=1, name="Kick 4x4")
    assert c["length"] == 4.0 and len(song.tracks[1].clip_slots) == 3
    kick = [{"pitch": 36, "start": b, "duration": 0.25, "velocity": 127} for b in range(4)]
    assert (await server.ableton_add_notes(track=0, slot=2, notes=kick))["total"] == 4
    assert (await server.ableton_add_notes(track=0, slot=2, notes=kick[:1], clear=True))["total"] == 1
    assert (await server.ableton_get_notes(track=0, slot=2))["notes"][0]["pitch"] == 36
    for bad in (lambda: server.ableton_create_clip(track=0, slot=2), lambda: server.ableton_set_song(key="H"),
                lambda: server.ableton_add_notes(track=0, slot=2, notes=[{"pitch": 200, "start": 0}])):
        try:
            await bad(); raise SystemExit("deberia fallar")
        except Exception as e:
            assert "deberia" not in str(e), e
    assert (await server.ableton_clip_props(track=0, slot=2, bars=2))["loop"] == [0.0, 8.0]
    await server.ableton_delete_clip(track=0, slot=2)
    a = await server.ableton_arrange_clip(track=0, bar=1, bars=8, notes=kick + [{"pitch": 36, "start": 20}], name="Intro")
    assert (a["start"], a["end"], a["total"]) == (0.0, 32.0, 5)
    await server.ableton_arrange_clip(track=0, bar=9, bars=8, notes=kick)
    await server.ableton_arrange_clip(track=0, bar=5, bars=2, notes=kick)  # pisa el primero: lo reemplaza
    assert [c["start"] for c in await server.ableton_arrange_list(track=0)] == [32.0, 16.0]
    assert (await server.ableton_arrange_clear(track=0, from_bar=9))["deleted"] == 1
    assert (await server.ableton_arrange_clear(track=0))["deleted"] == 1
    assert not song.tracks[0].clip_slots[2].has_clip

asyncio.run(main())
surface.disconnect()

# generador de presets: plugin dentro del Rack, con estado, parametros elegidos e Ids unicos
import preset_gen  # noqa: E402

fake = {"name": "Fake EQ", "cid": "00000000-0000-0000-0000-000000000001", "cid_hex": "00" * 15 + "01",
        "processor_state": "AB" * 100, "controller_state": "",
        "params": [{"id": i, "name": "Band 1 Gain" if i else "Bypass", "flags": 1, "default": 0.0, "min": -30.0,
                    "max": 30.0} for i in range(3)]}
rack = preset_gen.build_rack(fake)
v = rack.find(".//AudioEffectBranchPreset/DevicePresets/Vst3Preset")
ps = v.find("ParameterSettings")
assert [e.find("ParameterId").get("Value") for e in ps] == ["0", "1", "2"]
assert [e.get("Id") for e in ps] == ["0", "1", "2"]
assert v.find("ProcessorState").text.replace("\n", "") == "AB" * 100 and v.find("ControllerState").text is None
assert v.find("Uid/Fields.3").get("Value") == "1"
# con el Pro-Q 4 real, el Uid debe salir igual que el que escribio Live
assert preset_gen.uid_fields("72bd57ed605c7e46a64dd2f400758b6f") == [-313016974, 1549813374, -1504849164, 7703407]
# medicion: lectura del log de ffmpeg y comparacion con referencia
import analysis  # noqa: E402
log = "".join("[astats@%s @ 0000] Overall\n[astats@%s @ 0000] RMS level dB: %s\n" % (n, n, v) for n, v in
              [("full", -10), ("mid", -10), ("side", -20), ("sub", -18), ("bajo", -16), ("medios_bajos", -22),
               ("medios", -23), ("presencia", -25), ("aire", -27)])
log += ("[Parsed_ebur128_2 @ 0] Summary:\n  Integrated loudness:\n    I:   -8.6 LUFS\n  Loudness range:\n"
        "    LRA:   6.0 LU\n  True peak:\n    Peak:   0.7 dBFS\n")
m = analysis.parse(log)
assert (m["lufs"], m["lra"], m["true_peak_dbtp"], m["plr"]) == (-8.6, 6.0, 0.7, 9.3)
assert m["bandas_db"]["sub"] == -8 and m["ancho_db"] == -10 and m["correlacion"] == round(0.9 / 1.1, 3)
quiet = dict(m, lufs=-12.6, plr=13.3, bandas_db=dict(m["bandas_db"], sub=-11))
d = analysis.compare(quiet, m)
assert d["lufs"] == -4 and d["bandas_db"]["sub"] == -3 and len(d["notas"]) == 4, d
assert analysis.compare(m, m)["notas"] == ["true peak 0.70 dBTP: riesgo de clipping al convertir a mp3/streaming"]
print("OK: todas las pruebas pasaron")
