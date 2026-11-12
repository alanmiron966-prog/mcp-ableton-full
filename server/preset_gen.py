"""Genera un preset de Ableton que carga un VST3 con sus parametros ya expuestos (lo mismo que 'Configure').
Live no carga un plugin de terceros desde un .adv suelto: va dentro de un Audio Effect Rack (.adg) como <Vst3Preset>.
Entrada: el resultado de vst3_scan.scan(). Plantilla: un Rack con Pro-Q 4 VST3 guardado por Live 12.4."""
import copy
import gzip
import os
import re
import xml.etree.ElementTree as ET

RACK_TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "audio_rack.xml")
# shortcut: tope de 128 = los huecos que vimos guardados en un .als; si Live acepta mas, subirlo.
MAX_PARAMS = 128
CAN_AUTOMATE, READ_ONLY, HIDDEN = 1, 2, 16
# para plugins con cientos de parametros, primero lo que se usa al mezclar
KEYWORDS = ["used", "enabled", "frequency", "freq", "gain", " q", "shape", "slope", "mix", "output", "threshold",
            "ratio", "attack", "release", "knee", "range", "drive", "input", "decay", "size", "width", "time",
            "feedback", "lookahead", "ceiling", "style", "mode"]
BAND_ESSENTIAL = 8  # used, enabled, frequency, freq, gain, " q", shape, slope


def uid_fields(cid_hex):
    """16 bytes de class id -> los 4 int32 con signo que Live escribe en <Uid> (FUID::getLong1..4)."""
    b = bytes.fromhex(cid_hex)
    longs = [int.from_bytes(b[0:4], "little"),
             (b[5] << 24) | (b[4] << 16) | (b[7] << 8) | b[6],
             int.from_bytes(b[8:12], "big"), int.from_bytes(b[12:16], "big")]
    return [x - (1 << 32) if x >= 1 << 31 else x for x in longs]


def pick_params(params, limit=MAX_PARAMS):
    ok = [p for p in params if p["flags"] & CAN_AUTOMATE and not p["flags"] & (READ_ONLY | HIDDEN)
          and p["name"].strip() and "reserved" not in p["name"].lower()]
    if len(ok) <= limit:
        return ok

    def score(p):
        n = " " + p["name"].lower()
        hit = next((i for i, k in enumerate(KEYWORDS) if k in n), len(KEYWORDS))
        band = re.search(r"band (\d+)", n)
        # global con palabra clave, o banda con lo esencial (used..slope) -> primero; luego el resto
        tier = 0 if (hit < (BAND_ESSENTIAL if band else len(KEYWORDS))) else 1
        return (tier, int(band.group(1)) if band else 0, hit)

    chosen = {p["id"] for p in sorted(ok, key=score)[:limit]}
    return [p for p in ok if p["id"] in chosen]  # mantiene el orden del plugin


def build_rack(entry, limit=MAX_PARAMS):
    root = ET.parse(RACK_TEMPLATE).getroot()
    g = root.find("GroupDevicePreset")
    g.find("Device/AudioEffectGroupDevice/UserName").set("Value", entry["name"])
    branch = g.find("BranchPresets/AudioEffectBranchPreset")
    branch.find("Name").set("Value", entry["name"])
    v = branch.find("DevicePresets/Vst3Preset")
    for i, val in enumerate(uid_fields(entry["cid_hex"])):
        v.find("Uid/Fields.%d" % i).set("Value", str(val))
    # sin estado el plugin recibe datos vacios; va en hex en lineas de 80 como lo escribe Live
    for tag, key in (("ProcessorState", "processor_state"), ("ControllerState", "controller_state")):
        h = entry.get(key, "")
        v.find(tag).text = "\n" + "\n".join(h[i:i + 80] for i in range(0, len(h), 80)) + "\n" if h else None
    ps = v.find("ParameterSettings")
    proto = ps[0]
    ps.remove(proto)
    # Live solo escribe PluginFloatParameter (6809 de 6809 vistos), tambien para los de pasos
    for i, p in enumerate(pick_params(entry["params"], limit)):
        e = copy.deepcopy(proto)
        e.set("Id", str(i))
        e.find("Index").set("Value", str(i))
        e.find("VisualIndex").set("Value", str(i))
        e.find("ParameterId").set("Value", str(p["id"]))
        ps.append(e)
    return root


def write_adg(entry, out_path, limit=MAX_PARAMS):
    data = ET.tostring(build_rack(entry, limit), encoding="utf-8", xml_declaration=True)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with gzip.open(out_path, "wb") as f:
        f.write(data)
    return out_path
