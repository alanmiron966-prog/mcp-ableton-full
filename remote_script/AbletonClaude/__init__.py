# AbletonClaude Remote Script: recibe comandos JSON por socket local y los ejecuta en el hilo principal de Live.
from __future__ import absolute_import, print_function, unicode_literals

import json
import queue
import re
import socket
import threading
import traceback

import Live
from _Framework.ControlSurface import ControlSurface

HOST = "127.0.0.1"  # solo local: nadie de la red puede controlar Live
PORT = 9877


def create_instance(c_instance):
    return AbletonClaude(c_instance)


def _parse_display(text):
    """'2.50 kHz' -> 2500.0, '-6.0 dB' -> -6.0, '-inf dB' -> -inf. None si no hay numero."""
    s = str(text).strip().lower()
    if "inf" in s:
        return float("-inf") if s.startswith("-") else float("inf")
    m = re.search(r"-?\d+(?:[.,]\d+)?", s)
    if not m:
        return None
    v = float(m.group(0).replace(",", "."))
    rest = s[m.end():].strip()
    if rest.startswith("k"):
        v *= 1000.0
    elif rest.startswith("ms"):  # tiempos en segundos: '200.0 ms' y '1.000 sec' se comparan igual
        v /= 1000.0
    return v


class AbletonClaude(ControlSurface):
    def __init__(self, c_instance):
        ControlSurface.__init__(self, c_instance)
        self._running = True
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._server.bind((HOST, PORT))
            self._server.listen(4)
            self._server.settimeout(1.0)
            threading.Thread(target=self._accept_loop, daemon=True).start()
            self.show_message("AbletonClaude escuchando en puerto %d" % PORT)
        except Exception as e:
            self.log_message("AbletonClaude: no pude abrir el puerto: %s" % e)
            self.show_message("AbletonClaude: error de puerto %s" % e)

    def disconnect(self):
        self._running = False
        try:
            self._server.close()
        except Exception:
            pass
        ControlSurface.disconnect(self)

    # ---------- red ----------
    def _accept_loop(self):
        while self._running:
            try:
                client, _ = self._server.accept()
            except socket.timeout:
                continue
            except Exception:
                break
            threading.Thread(target=self._handle, args=(client,), daemon=True).start()

    def _handle(self, client):
        buf = b""
        try:
            while self._running:
                chunk = client.recv(65536)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if line.strip():
                        resp = self._run_on_main(json.loads(line.decode("utf-8")))
                        client.sendall((json.dumps(resp) + "\n").encode("utf-8"))
        except Exception as e:
            self.log_message("AbletonClaude cliente: %s" % e)
        finally:
            client.close()

    def _run_on_main(self, cmd):
        # La Live API no es thread-safe: todo se ejecuta en el hilo principal.
        out = queue.Queue()

        def task():
            try:
                fn = getattr(self, "cmd_" + cmd.get("type", ""), None)
                if fn is None:
                    raise ValueError("Comando desconocido: %s" % cmd.get("type"))
                out.put({"ok": True, "result": fn(**cmd.get("params", {}))})
            except Exception as e:
                self.log_message(traceback.format_exc())
                out.put({"ok": False, "error": str(e)})

        self.schedule_message(0, task)
        try:
            return out.get(timeout=15)
        except queue.Empty:
            return {"ok": False, "error": "Live no respondio en 15 s (dialogo abierto o proyecto cargando?)"}

    # ---------- utilidades ----------
    def _track(self, ref):
        """ref: indice (0..), 'master', o 'r0','r1'... para pistas de retorno."""
        song = self.song()
        r = str(ref).lower()
        if r == "master":
            return song.master_track
        if r.startswith("r"):
            return song.return_tracks[int(r[1:])]
        return song.tracks[int(ref)]

    @staticmethod
    def _unwrap(d):
        # los presets de Claude son un Rack de 1 cadena con 1 plugin: se trabaja con el plugin
        chains = list(d.chains) if getattr(d, "can_have_chains", False) else []
        if len(chains) == 1 and len(chains[0].devices) == 1:
            return chains[0].devices[0]
        return d

    def _device(self, track_ref, device):
        devs = list(self._track(track_ref).devices)
        if isinstance(device, int) or str(device).isdigit():
            return self._unwrap(devs[int(device)])
        for d in devs:
            if str(device).lower() in d.name.lower():
                return self._unwrap(d)
        raise ValueError("No hay dispositivo '%s'. Hay: %s" % (device, [d.name for d in devs]))

    @staticmethod
    def _param_info(i, p):
        return {"index": i, "name": p.name, "value": round(p.value, 4), "min": p.min, "max": p.max,
                "display": p.str_for_value(p.value), "quantized": p.is_quantized}

    @staticmethod
    def _to_value(p, display):
        """Valor interno de Live para un valor como se ve ('250 Hz', '-3 dB'): se busca por biseccion."""
        target = _parse_display(display)
        if target is None:
            return AbletonClaude._text_value(p, display)
        lo, hi = p.min, p.max
        asc = (_parse_display(p.str_for_value(hi)) or 0) >= (_parse_display(p.str_for_value(lo)) or 0)
        for _ in range(40):
            mid = (lo + hi) / 2.0
            cur = _parse_display(p.str_for_value(mid))
            if cur is None:
                raise ValueError("El parametro '%s' no muestra un numero" % p.name)
            if (cur < target) == asc:
                lo = mid
            else:
                hi = mid
        return min((lo, hi), key=lambda v: abs((_parse_display(p.str_for_value(v)) or 0) - target))

    @staticmethod
    def _text_value(p, text):
        """Opcion de lista por su texto ('Low Cut', 'Opto'): recorre el rango y toma el centro del tramo."""
        t = str(text).strip().lower()
        vals = [p.min + (p.max - p.min) * i / 1000.0 for i in range(1001)]
        shown = [p.str_for_value(v) for v in vals]
        hits = [v for v, d in zip(vals, shown) if d.strip().lower() == t]
        if not hits:
            opts = sorted(set(shown), key=shown.index)[:30]
            raise ValueError("'%s' no es una opcion de '%s'. Opciones: %s" % (text, p.name, ", ".join(opts)))
        v = hits[len(hits) // 2]
        return round(v) if p.is_quantized else v

    @staticmethod
    def _set_param(p, value=None, display=None):
        """value = valor interno de Live. display = valor como se ve ('250 Hz', '-3 dB')."""
        if display is not None:
            value = AbletonClaude._to_value(p, display)
        if value is None:
            raise ValueError("Falta value o display")
        if not p.is_enabled:
            raise ValueError("El parametro '%s' esta bloqueado (automatizado o mapeado)" % p.name)
        p.value = max(p.min, min(p.max, float(value)))
        return {"name": p.name, "display": p.str_for_value(p.value)}

    def _track_info(self, ref, t):
        m = t.mixer_device
        info = {"ref": ref, "name": t.name,
                "volume": m.volume.str_for_value(m.volume.value),
                "pan": m.panning.str_for_value(m.panning.value),
                "devices": [d.name for d in t.devices]}
        if ref != "master":
            info.update(mute=t.mute, solo=t.solo,
                        sends=[s.str_for_value(s.value) for s in m.sends])
        if hasattr(t, "has_midi_input"):
            info["kind"] = "midi" if t.has_midi_input else "audio"
        return info

    def _all_tracks(self):
        song = self.song()
        items = [(i, t) for i, t in enumerate(song.tracks)]
        items += [("r%d" % i, t) for i, t in enumerate(song.return_tracks)]
        items.append(("master", song.master_track))
        return items

    # ---------- comandos ----------
    def cmd_ping(self):
        return "pong"

    def cmd_status(self):
        s = self.song()
        return {"tempo": s.tempo, "playing": s.is_playing, "tracks": len(s.tracks),
                "returns": len(s.return_tracks), "time_signature": "%d/%d" % (s.signature_numerator, s.signature_denominator),
                # compas del cabezal (1 = inicio); current_song_time va en negras
                "bar": round(s.current_song_time / (s.signature_numerator * 4.0 / s.signature_denominator) + 1, 2)}

    def cmd_list_tracks(self):
        return [self._track_info(r, t) for r, t in self._all_tracks()]

    def cmd_meters(self):
        # pistas MIDI sin instrumento tienen salida MIDI y no tienen medidor
        return {str(r): round(max(t.output_meter_left, t.output_meter_right), 4)
                for r, t in self._all_tracks() if getattr(t, "has_audio_output", True)}

    def cmd_set_mixer(self, track, volume_db=None, pan=None, send=None, send_db=None, mute=None, solo=None):
        t = self._track(track)
        m = t.mixer_device
        done = {}
        if volume_db is not None:
            done["volume"] = self._set_param(m.volume, display=str(volume_db))["display"]
        if pan is not None:  # -1 izquierda .. 1 derecha
            done["pan"] = self._set_param(m.panning, value=pan)["display"]
        if send is not None and send_db is not None:
            done["send"] = self._set_param(m.sends[int(send)], display=str(send_db))["display"]
        if mute is not None:
            t.mute = bool(mute)
            done["mute"] = t.mute
        if solo is not None:
            t.solo = bool(solo)
            done["solo"] = t.solo
        return done

    def _browser_roots(self, source):
        b = Live.Application.get_application().browser
        names = ["plugins", "audio_effects", "instruments", "midi_effects", "drums", "sounds", "user_library", "packs"]
        if source != "all":
            names = [source]
        return [(n, getattr(b, n)) for n in names if hasattr(b, n)]

    def _walk(self, item, depth=0, max_depth=6):
        for child in item.children:
            if child.is_loadable:
                yield child
            if child.is_folder and depth < max_depth:
                for x in self._walk(child, depth + 1, max_depth):
                    yield x

    def cmd_list_browser(self, source="plugins", query="", limit=200):
        q = query.lower()
        found = []
        for root_name, root in self._browser_roots(source):
            for it in self._walk(root):
                if q in it.name.lower():
                    found.append({"name": it.name, "source": root_name})
                    if len(found) >= limit:
                        return found
        return found

    def cmd_load_device(self, track, name, source="all"):
        t = self._track(track)
        q = name.lower()
        hits = [it for _, root in self._browser_roots(source) for it in self._walk(root) if q in it.name.lower()]
        # exacto primero: 'Pro-Q 4' (VST3) no debe cargar 'FabFilter Pro-Q 4' (VST2)
        hits.sort(key=lambda it: it.name.lower() != q)
        if hits:
            self.song().view.selected_track = t
            Live.Application.get_application().browser.load_item(hits[0])
            return {"loaded": hits[0].name, "track": t.name}
        raise ValueError("No encontre '%s' en el browser (%s). Usa list_browser para ver nombres." % (name, source))

    def _file_item(self, root, parts):
        """Baja por Places (user_folders) hasta el archivo: mucho mas rapido que recorrer todo el browser."""
        b = Live.Application.get_application().browser
        cur = next((f for f in b.user_folders if f.name == root), None)
        for i, p in enumerate(parts):
            if cur is None:
                break
            names = (p,) if i < len(parts) - 1 else (p, p.rsplit(".", 1)[0])  # Live puede ocultar la extension
            cur = next((c for c in cur.children if c.name in names), None)
        if cur is None or not cur.is_loadable:
            raise ValueError("No encontre %s/%s en Places de Live" % (root, "/".join(parts)))
        return cur

    def cmd_load_sample(self, track, root, parts, pad=None):
        t = self._track(track)
        if not t.has_midi_input:
            raise ValueError("'%s' no es una pista MIDI" % t.name)
        item = self._file_item(root, parts)
        s, b = self.song(), Live.Application.get_application().browser
        s.view.selected_track = t
        if pad is None:
            b.load_item(item)
            return {"loaded": item.name, "track": t.name, "device": "Simpler"}
        rack = next((d for d in t.devices if d.can_have_drum_pads), None)
        if rack is None:
            raise ValueError("No hay Drum Rack en '%s': cargalo antes con load_device('Drum Rack', 'instruments')" % t.name)
        dp = rack.drum_pads[int(pad)]
        rack.view.selected_drum_pad = dp
        s.view.select_device(rack)
        b.load_item(item)
        return {"loaded": item.name, "track": t.name, "pad": int(pad), "pad_name": dp.name}

    def cmd_create_track(self, kind="audio", name=None):
        s = self.song()
        (s.create_midi_track if kind == "midi" else s.create_audio_track)(-1)  # -1 = al final
        t = s.tracks[len(s.tracks) - 1]
        if name:
            t.name = name
        return {"index": len(s.tracks) - 1, "name": t.name}

    def cmd_delete_track(self, track):
        s = self.song()
        i = int(track)
        name = s.tracks[i].name
        s.delete_track(i)
        return {"deleted": name}

    # ---------- produccion: cancion, clips y notas ----------
    def cmd_set_song(self, tempo=None, numerator=None, denominator=None, root_note=None, scale_name=None):
        s = self.song()
        if tempo is not None:
            s.tempo = float(tempo)
        if numerator is not None:
            s.signature_numerator = int(numerator)
        if denominator is not None:
            s.signature_denominator = int(denominator)
        if root_note is not None:  # 0 = C .. 11 = B
            s.root_note = int(root_note)
        if scale_name is not None:
            s.scale_name = str(scale_name)
        return {"tempo": s.tempo, "signature": "%d/%d" % (s.signature_numerator, s.signature_denominator),
                "root_note": s.root_note, "scale_name": s.scale_name}

    def _slot(self, track, slot):
        t = self._track(track)
        slots = list(t.clip_slots)
        s = self.song()
        while int(slot) >= len(slots):  # crea escenas hasta que exista el hueco
            s.create_scene(-1)
            slots = list(t.clip_slots)
        return t, slots[int(slot)]

    def _clip(self, track, slot):
        t, cs = self._slot(track, slot)
        if not cs.has_clip:
            raise ValueError("No hay clip en la pista '%s', hueco %s" % (t.name, slot))
        return cs.clip

    def cmd_create_clip(self, track, slot=0, length=4.0, name=None, replace=False):
        """length en beats (negras): 16 = 4 compases en 4/4."""
        t, cs = self._slot(track, slot)
        if not t.has_midi_input:
            raise ValueError("'%s' no es una pista MIDI" % t.name)
        if cs.has_clip:
            if not replace:
                raise ValueError("Ya hay un clip en el hueco %s de '%s' (usa replace)" % (slot, t.name))
            cs.delete_clip()
        cs.create_clip(float(length))
        if name:
            cs.clip.name = name
        return {"track": t.name, "slot": int(slot), "length": cs.clip.length, "name": cs.clip.name}

    @staticmethod
    def _note_info(n):
        return {"pitch": n.pitch, "start": round(n.start_time, 4), "duration": round(n.duration, 4),
                "velocity": round(n.velocity, 1), "mute": n.mute}

    def cmd_add_notes(self, track, slot, notes, clear=False):
        """notes: [{pitch, start, duration, velocity?, mute?}] con tiempos en beats."""
        return self._write_notes(self._clip(track, slot), notes, clear)

    @staticmethod
    def _write_notes(c, notes, clear=False):
        if clear:
            c.remove_notes_extended(0, 128, 0.0, max(c.length, 1.0) * 4)
        specs = []
        for n in notes:
            p = int(n["pitch"])
            if not 0 <= p <= 127:
                raise ValueError("pitch fuera de 0..127: %s" % p)
            specs.append(Live.Clip.MidiNoteSpecification(
                pitch=p, start_time=float(n["start"]), duration=max(float(n.get("duration", 0.25)), 0.001),
                velocity=float(max(1, min(127, n.get("velocity", 100)))), mute=bool(n.get("mute", False))))
        c.add_new_notes(tuple(specs))
        return {"added": len(specs), "total": len(c.get_notes_extended(0, 128, 0.0, c.length * 4))}

    # ---------- arrangement ----------
    def _midi_track(self, track):
        t = self._track(track)
        if not getattr(t, "has_midi_input", False):
            raise ValueError("'%s' no es una pista MIDI" % t.name)
        return t

    def cmd_arrange_clip(self, track, start, length, notes, name=None):
        """Clip MIDI en el Arrangement. start y length en beats; notas relativas al inicio del clip."""
        t = self._midi_track(track)
        start, length = float(start), float(length)
        for c in list(t.arrangement_clips):  # quita lo que pise ese tramo
            if c.start_time < start + length and c.end_time > start:
                t.delete_clip(c)
        c = t.create_midi_clip(start, length)
        if name:
            c.name = name
        res = self._write_notes(c, notes)
        res.update(track=t.name, start=c.start_time, end=c.end_time, name=c.name)
        return res

    def cmd_arrange_list(self, track):
        t = self._track(track)
        return [{"name": c.name, "start": c.start_time, "end": c.end_time,
                 **({"file": c.file_path} if getattr(c, "is_audio_clip", False) else {})} for c in t.arrangement_clips]

    def cmd_arrange_clear(self, track, start=None, end=None):
        t = self._track(track)
        n = 0
        for c in list(t.arrangement_clips):
            if (start is None or c.end_time > float(start)) and (end is None or c.start_time < float(end)):
                t.delete_clip(c)
                n += 1
        return {"track": t.name, "deleted": n}

    def cmd_get_notes(self, track, slot):
        c = self._clip(track, slot)
        notes = sorted(c.get_notes_extended(0, 128, 0.0, c.length * 4), key=lambda n: (n.start_time, n.pitch))
        return {"name": c.name, "length": c.length, "loop": [c.loop_start, c.loop_end],
                "notes": [self._note_info(n) for n in notes]}

    def cmd_clip_props(self, track, slot, name=None, length=None, loop_start=None):
        c = self._clip(track, slot)
        if name is not None:
            c.name = name
        if loop_start is not None:
            c.loop_start = float(loop_start)
        if length is not None:  # cambia la zona de loop: el clip suena esa duracion
            c.loop_end = c.loop_start + float(length)
            c.end_marker = c.loop_end
        return {"name": c.name, "length": c.length, "loop": [c.loop_start, c.loop_end]}

    def cmd_delete_clip(self, track, slot):
        t, cs = self._slot(track, slot)
        if cs.has_clip:
            cs.delete_clip()
        return {"track": t.name, "slot": int(slot), "deleted": True}

    def cmd_play(self, track=None, slot=None, stop=False, arrangement=None):
        s = self.song()
        if stop:
            s.stop_all_clips()
            s.stop_playing()
            return {"playing": False}
        if arrangement is not None:  # vuelve al Arrangement y toca desde esa posicion (beats)
            s.stop_all_clips()
            s.back_to_arranger = False
            # con Live parado la posicion se ignora: arrancar y saltar en el siguiente ciclo (probado en 12.4.6)
            s.continue_playing()
            self.schedule_message(1, lambda: setattr(s, "current_song_time", float(arrangement)))
            return {"playing": True, "from": float(arrangement)}  # current_song_time se aplica despues, no releerlo
        if track is not None and slot is not None:
            self._slot(track, slot)[1].fire()
        else:
            s.start_playing()
        return {"playing": True}

    def cmd_device_params(self, track, device, match=None):
        d = self._device(track, device)
        m = (match or "").lower()
        return {"device": d.name, "class": d.class_name,
                "params": [self._param_info(i, p) for i, p in enumerate(d.parameters) if m in p.name.lower()]}

    def cmd_set_device_param(self, track, device, param, value=None, display=None):
        return self._set_param(self._find_param(self._device(track, device), param), value=value, display=display)

    @staticmethod
    def _find_param(d, param):
        params = list(d.parameters)
        if isinstance(param, int) or str(param).isdigit():
            return params[int(param)]
        matches = [x for x in params if x.name.lower() == str(param).lower()] or \
                  [x for x in params if str(param).lower() in x.name.lower()]
        if not matches:
            raise ValueError("'%s' no tiene parametro '%s'. Usa device_params." % (d.name, param))
        return matches[0]

    def _auto_param(self, track, device, param):
        if str(device).lower() == "mixer":  # param: volume, pan, send N
            m = self._track(track).mixer_device
            key = str(param).lower()
            if key.startswith("vol"):
                return m.volume
            if key.startswith("pan"):
                return m.panning
            if key.startswith("send"):
                return m.sends[int(key.split()[-1])]
            raise ValueError("mixer: usa volume, pan o 'send N'")
        return self._find_param(self._device(track, device), param)

    def cmd_arrange_automation(self, track, device, param, points):
        """Graba automatizacion en el Arrangement en tiempo real (la API no deja escribirla directo).
        points: [{beat (absoluto), value o display}], rampa lineal. Vuelve enseguida; la grabacion dura lo que el tramo."""
        s = self.song()
        p = self._auto_param(track, device, param)
        pts = sorted((float(x["beat"]), self._to_value(p, x["display"]) if "display" in x else float(x["value"]))
                     for x in points)
        if len(pts) < 2:
            raise ValueError("Hacen falta al menos dos puntos")
        if getattr(self, "_rec", None):
            raise ValueError("Ya hay una grabacion de automatizacion en curso")
        start, end = pts[0][0], pts[-1][0]

        def at(t):
            for (b0, v0), (b1, v1) in zip(pts, pts[1:]):
                if t <= b1:
                    return v0 + (v1 - v0) * max(0.0, t - b0) / ((b1 - b0) or 1)
            return pts[-1][1]

        armed = [t for t in s.tracks if t.can_be_armed and t.arm]
        for t in armed:  # sin pistas armadas solo se graba automatizacion
            t.arm = False
        self._rec = {"armed": armed, "auto_arm": s.session_automation_record}
        s.session_automation_record = True  # boton Automation Arm: sin el no se graba automatizacion
        s.re_enable_automation()  # si el parametro esta en override, Live no graba encima

        def finish():
            s.re_enable_automation()  # mover el parametro sin grabar lo deja en override
            self._end_rec()

        secs = self._roll(start, end, lambda t: setattr(p, "value", max(p.min, min(p.max, at(t)))), finish)
        return {"param": p.name, "automation_state": p.automation_state, "recording_seconds": secs,
                "from": p.str_for_value(pts[0][1]), "to": p.str_for_value(pts[-1][1])}

    def _end_rec(self):
        s = self.song()
        s.session_automation_record = self._rec["auto_arm"]
        for t in self._rec["armed"]:
            t.arm = True
        self._rec = None

    def _roll(self, start, end, step, finish):
        """Toca el Arrangement desde un compas antes de start; entre start y end activa record_mode y llama
        step(t) en cada tick. Al acabar apaga record_mode y llama finish(). Devuelve los segundos que tarda."""
        s = self.song()
        s.stop_all_clips()
        s.back_to_arranger = False
        loop = s.loop
        s.loop = False  # con el loop del Arrangement puesto nunca llega a end y graba encima en bucle
        s.continue_playing()
        self.schedule_message(1, lambda: setattr(s, "current_song_time", max(0.0, start - 4)))  # 1 compas de preroll

        def tick(waited=[0], rolled=[False]):
            t = s.current_song_time
            waited[0] += 1
            # play y salto al preroll son asincronos: hasta ver ambos, is_playing y t son los viejos
            rolled[0] = rolled[0] or (s.is_playing and t <= start)
            if waited[0] > 6000 or (rolled[0] and (not s.is_playing or t >= end + 0.5)):  # +0.5: graba el valor final
                s.record_mode = False
                s.loop = loop
                return finish()
            if rolled[0] and t >= start:
                if not s.record_mode:
                    s.record_mode = True
                step(t)
            self.schedule_message(1, tick)

        self.schedule_message(3, tick)
        return round((end - max(0.0, start - 4)) * 60.0 / s.tempo, 1)

    def cmd_record_master(self, start, end, name="Master Rec"):
        """Graba la salida del master (entrada Resampling) en una pista de audio del Arrangement, en tiempo real."""
        s = self.song()
        start, end = float(start), float(end)
        if getattr(self, "_rec", None):
            raise ValueError("Ya hay una grabacion en curso")
        t = next((x for x in s.tracks if x.name == name), None)
        if t is None:
            s.create_audio_track(-1)
            t = s.tracks[len(s.tracks) - 1]
            t.name = name
        rs = [r for r in t.available_input_routing_types if r.display_name.lower() == "resampling"]
        if not rs:
            raise ValueError("Live no ofrece la entrada Resampling en '%s'" % name)
        t.input_routing_type = rs[0]
        t.current_monitoring_state = 2  # Off: monitorizar el master en su propia entrada lo realimenta
        armed = [x for x in s.tracks if x.can_be_armed and x.arm]
        for x in armed:
            x.arm = False
        self._rec = {"armed": armed, "auto_arm": s.session_automation_record}
        s.session_automation_record = False  # que no se grabe automatizacion de paso
        t.arm = True

        def finish():
            t.arm = False
            s.stop_playing()
            self._end_rec()

        return {"track": t.name, "index": list(s.tracks).index(t), "recording_seconds": self._roll(start, end, lambda _t: None, finish)}
