"""Lee de un .vst3 su class id y la lista de parametros (ParamID VST3, nombre) via COM, sin host completo.
Uso: python vst3_scan.py <ruta.vst3>  -> JSON. Pensado para correr en un subproceso (un plugin roto no tumba al MCP)."""
import ctypes
import glob
import json
import os
import sys
import uuid

HRESULT = ctypes.c_int32


def _iid(l1, l2, l3, l4):
    # INLINE_UID con COM_COMPATIBLE (Windows): mismo orden de bytes que un GUID
    return (l1.to_bytes(4, "little") + (l2 >> 16).to_bytes(2, "little") + (l2 & 0xFFFF).to_bytes(2, "little")
            + l3.to_bytes(4, "big") + l4.to_bytes(4, "big"))


IID_COMPONENT = _iid(0xE831FF31, 0xF2D54301, 0x928EBBEE, 0x25697802)
IID_CONTROLLER = _iid(0xDCD7BBE3, 0x7742448D, 0xA874AACC, 0x979C759E)


class PClassInfo(ctypes.Structure):
    _fields_ = [("cid", ctypes.c_ubyte * 16), ("cardinality", ctypes.c_int32),
                ("category", ctypes.c_char * 32), ("name", ctypes.c_char * 64)]


class PClassInfo2(ctypes.Structure):
    _fields_ = [("cid", ctypes.c_ubyte * 16), ("cardinality", ctypes.c_int32), ("category", ctypes.c_char * 32),
                ("name", ctypes.c_char * 64), ("classFlags", ctypes.c_uint32), ("subCategories", ctypes.c_char * 128),
                ("vendor", ctypes.c_char * 64), ("version", ctypes.c_char * 64), ("sdkVersion", ctypes.c_char * 64)]


IID_FACTORY2 = _iid(0x0007B650, 0xF24B4C0B, 0xA464EDB9, 0xF00B2ABB)


class ParameterInfo(ctypes.Structure):
    _fields_ = [("id", ctypes.c_uint32), ("title", ctypes.c_wchar * 128), ("shortTitle", ctypes.c_wchar * 128),
                ("units", ctypes.c_wchar * 128), ("stepCount", ctypes.c_int32), ("default", ctypes.c_double),
                ("unitId", ctypes.c_int32), ("flags", ctypes.c_int32)]


def _call(obj, idx, restype, *args):
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    fn = ctypes.CFUNCTYPE(restype, ctypes.c_void_p, *[type(a) if hasattr(type(a), 'from_param') else ctypes.c_void_p for a in args])(vtbl[idx])
    return fn(obj, *args)


IID_CONNECTION = _iid(0x70A4156F, 0x6E6E4026, 0x989148BF, 0xAA60D8D1)
IID_FUNKNOWN = _iid(0, 0, 0xC0000000, 0x46)
IID_HOSTAPP = _iid(0x58E595CC, 0xDB2D4969, 0x8B6AAF8C, 0x36A664E5)
_QI = ctypes.CFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
_REF = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p)
_NAME = ctypes.CFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_void_p)
_CREATE = ctypes.CFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))


IID_MESSAGE = _iid(0x936F033B, 0xC6C047DB, 0xBB0882F8, 0x13C1E613)
IID_ATTRLIST = _iid(0x1E5F0AEB, 0xCC7F4533, 0xA2544011, 0x38AD5EE4)
_LIVE = []  # objetos COM creados para el plugin: viven hasta que acaba el subproceso
_P = ctypes.c_void_p
_ID = ctypes.c_char_p


def _com(iid, methods):
    """Objeto COM en Python: FUnknown + methods [(CFUNCTYPE, fn)]. Devuelve el puntero al objeto."""
    def qi(this, req, out):
        if ctypes.string_at(req, 16) in (IID_FUNKNOWN, iid):
            out[0] = this
            return 0
        out[0] = None
        return -2147467262
    fns = [_QI(qi), _REF(lambda t: 1), _REF(lambda t: 1)] + [t(f) for t, f in methods]
    vtbl = (ctypes.c_void_p * len(fns))(*[ctypes.cast(f, ctypes.c_void_p) for f in fns])
    holder = ctypes.c_void_p(ctypes.addressof(vtbl))
    _LIVE.append((fns, vtbl, holder))
    return ctypes.addressof(holder)


def _attr_list():
    d = {}

    def put(this, k, v):
        d[k] = v
        return 0

    def get(this, k, out):
        if k not in d:
            return 1  # kResultFalse
        out[0] = d[k]
        return 0

    def set_str(this, k, src):
        d[k] = ctypes.wstring_at(src)
        return 0

    def get_str(this, k, dst, size):
        if k not in d:
            return 1
        b = d[k].encode("utf-16-le")[:max(0, size - 2)] + b"\0\0"
        ctypes.memmove(dst, b, len(b))
        return 0

    def set_bin(this, k, src, n):
        d[k] = ctypes.create_string_buffer(ctypes.string_at(src, n), n)
        return 0

    def get_bin(this, k, out, n):
        if k not in d:
            return 1
        out[0], n[0] = ctypes.addressof(d[k]), len(d[k])
        return 0

    I64, F64 = ctypes.c_int64, ctypes.c_double
    return _com(IID_ATTRLIST, [
        (ctypes.CFUNCTYPE(HRESULT, _P, _ID, I64), put), (ctypes.CFUNCTYPE(HRESULT, _P, _ID, ctypes.POINTER(I64)), get),
        (ctypes.CFUNCTYPE(HRESULT, _P, _ID, F64), put), (ctypes.CFUNCTYPE(HRESULT, _P, _ID, ctypes.POINTER(F64)), get),
        (ctypes.CFUNCTYPE(HRESULT, _P, _ID, _P), set_str), (ctypes.CFUNCTYPE(HRESULT, _P, _ID, _P, ctypes.c_uint32), get_str),
        (ctypes.CFUNCTYPE(HRESULT, _P, _ID, _P, ctypes.c_uint32), set_bin),
        (ctypes.CFUNCTYPE(HRESULT, _P, _ID, ctypes.POINTER(_P), ctypes.POINTER(ctypes.c_uint32)), get_bin)])


def _message():
    attrs, mid = _attr_list(), [ctypes.create_string_buffer(b"")]

    def set_id(this, s):
        mid[0] = ctypes.create_string_buffer(ctypes.string_at(s) if s else b"")
        return None

    return _com(IID_MESSAGE, [(ctypes.CFUNCTYPE(_P, _P), lambda t: ctypes.addressof(mid[0])),
                              (ctypes.CFUNCTYPE(None, _P, _P), set_id),
                              (ctypes.CFUNCTYPE(_P, _P), lambda t: attrs)])


def _create_instance(this, cid, iid, out):
    """IHostApplication::createInstance: iZotope y otros crean aqui los IMessage que se envian al conectar."""
    want = ctypes.string_at(iid, 16)
    if want == IID_MESSAGE:
        out[0] = _message()
        return 0
    if want == IID_ATTRLIST:
        out[0] = _attr_list()
        return 0
    out[0] = None
    return -2147467262


def _make_host():
    """IHostApplication minimo: algunos plugins no crean sus parametros si initialize() recibe null."""
    host = ctypes.c_void_p()

    def qi(this, iid, obj):
        if ctypes.string_at(iid, 16) in (IID_FUNKNOWN, IID_HOSTAPP):
            obj[0] = this
            return 0
        obj[0] = None
        return -2147467262  # kNoInterface

    def name(this, buf):
        ctypes.memmove(buf, "Ableton Live".encode("utf-16-le") + b"\0\0", 26)
        return 0

    fns = [_QI(qi), _REF(lambda t: 1), _REF(lambda t: 1), _NAME(name), _CREATE(_create_instance)]
    vtbl = (ctypes.c_void_p * len(fns))(*[ctypes.cast(f, ctypes.c_void_p) for f in fns])
    holder = ctypes.c_void_p(ctypes.addressof(vtbl))
    host.value = ctypes.addressof(holder)
    host._keep = (fns, vtbl, holder)  # que el GC no libere los callbacks
    return host


HOST = None
IID_BSTREAM = _iid(0xC3BF6EA2, 0x30994752, 0x9B6BF990, 0x1EE33E9B)
_RW = ctypes.CFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32, ctypes.POINTER(ctypes.c_int32))
_SEEK = ctypes.CFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_int64, ctypes.c_int32, ctypes.POINTER(ctypes.c_int64))
_TELL = ctypes.CFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int64))


def _get_state(obj, idx):
    """Llama getState(IBStream*) (vtable idx) con un IBStream en memoria y devuelve los bytes."""
    buf, pos = bytearray(), [0]

    def qi(this, iid, out):
        if ctypes.string_at(iid, 16) in (IID_FUNKNOWN, IID_BSTREAM):
            out[0] = this
            return 0
        out[0] = None
        return -2147467262

    def read(this, dst, n, done):
        chunk = bytes(buf[pos[0]:pos[0] + n])
        ctypes.memmove(dst, chunk, len(chunk))
        pos[0] += len(chunk)
        if done:
            done[0] = len(chunk)
        return 0

    def write(this, src, n, done):
        buf[pos[0]:pos[0] + n] = ctypes.string_at(src, n)
        pos[0] += n
        if done:
            done[0] = n
        return 0

    def seek(this, off, mode, res):
        pos[0] = max(0, [0, pos[0], len(buf)][mode] + off)
        if res:
            res[0] = pos[0]
        return 0

    def tell(this, res):
        if res:
            res[0] = pos[0]
        return 0

    fns = [_QI(qi), _REF(lambda t: 1), _REF(lambda t: 1), _RW(read), _RW(write), _SEEK(seek), _TELL(tell)]
    vtbl = (ctypes.c_void_p * len(fns))(*[ctypes.cast(f, ctypes.c_void_p) for f in fns])
    holder = ctypes.c_void_p(ctypes.addressof(vtbl))
    ok = _call(obj, idx, HRESULT, ctypes.c_void_p(ctypes.addressof(holder))) == 0
    return bytes(buf) if ok else b""


def _qi(obj, iid):
    out = ctypes.c_void_p()
    ok = _call(obj, 0, HRESULT, ctypes.c_char_p(iid), ctypes.byref(out)) == 0
    return out if ok and out.value else None


def dll_path(path):
    if os.path.isdir(path):  # bundle: X.vst3/Contents/x86_64-win/X.vst3
        hits = glob.glob(os.path.join(path, "Contents", "x86_64-win", "*.vst3"))
        if not hits:
            raise FileNotFoundError("bundle sin binario x64: %s" % path)
        return hits[0]
    return path


def scan(path):
    global HOST
    HOST = HOST or _make_host()
    lib = ctypes.WinDLL(dll_path(path))
    if hasattr(lib, "InitDll"):
        lib.InitDll()
    get_factory = lib.GetPluginFactory
    get_factory.restype = ctypes.c_void_p
    factory = ctypes.c_void_p(get_factory())
    f2 = _qi(factory, IID_FACTORY2)
    out = []
    for i in range(_call(factory, 4, ctypes.c_int32)):
        info = PClassInfo()
        _call(factory, 5, HRESULT, ctypes.c_int32(i), ctypes.byref(info))
        if info.category != b"Audio Module Class":
            continue
        cid = bytes(info.cid)
        sub = ""  # "Fx|EQ", "Instrument|Synth"... decide que tipo de Rack lo envuelve
        if f2 is not None:
            info2 = PClassInfo2()
            if _call(f2, 7, HRESULT, ctypes.c_int32(i), ctypes.byref(info2)) == 0:
                sub = info2.subCategories.decode("utf-8", "replace")
        comp = ctypes.c_void_p()
        if _call(factory, 6, HRESULT, ctypes.c_char_p(cid), ctypes.c_char_p(IID_COMPONENT), ctypes.byref(comp)) != 0:
            continue
        _call(comp, 3, HRESULT, HOST)
        ctrl = _qi(comp, IID_CONTROLLER)
        if ctrl is None:  # controller separado
            ccid = (ctypes.c_ubyte * 16)()
            _call(comp, 5, HRESULT, ctypes.byref(ccid))
            ctrl = ctypes.c_void_p()
            if _call(factory, 6, HRESULT, ctypes.c_char_p(bytes(ccid)), ctypes.c_char_p(IID_CONTROLLER),
                     ctypes.byref(ctrl)) != 0:
                ctrl = None
            else:
                _call(ctrl, 3, HRESULT, HOST)
                a, b = _qi(comp, IID_CONNECTION), _qi(ctrl, IID_CONNECTION)
                if a and b:  # como hace un host real: une componente y controlador
                    try:
                        _call(a, 3, HRESULT, b)
                        _call(b, 3, HRESULT, a)
                    except OSError:
                        # shortcut: iZotope pide host->createInstance(IMessage) al conectar y no lo tenemos;
                        # se sigue sin conexion. Si faltan parametros, implementar IMessage/IAttributeList.
                        pass
        params = []
        if ctrl is not None:
            for j in range(_call(ctrl, 8, ctypes.c_int32)):
                p = ParameterInfo()
                _call(ctrl, 9, HRESULT, ctypes.c_int32(j), ctypes.byref(p))
                plain = [_call(ctrl, 12, ctypes.c_double, ctypes.c_uint32(p.id), ctypes.c_double(v))
                         for v in (0.0, 1.0, p.default)]  # normalizedParamToPlain
                params.append({"id": p.id, "name": p.title, "units": p.units, "steps": p.stepCount,
                               "flags": p.flags, "default_norm": p.default,
                               "min": plain[0], "max": plain[1], "default": plain[2]})
        out.append({"name": info.name.decode("utf-8", "replace"), "cid": str(uuid.UUID(bytes_le=cid)),
                    "cid_hex": cid.hex(), "sub": sub, "params": params,
                    # estado por defecto que el propio plugin genera: Live lo guarda tal cual en hex
                    "processor_state": _get_state(comp, 13).hex().upper(),
                    "controller_state": _get_state(ctrl, 7).hex().upper() if ctrl is not None else ""})
    return out


if __name__ == "__main__":
    # el codigo nativo de algunos plugins escribe en stdout: se manda a stderr y el JSON sale por el fd original
    out = os.fdopen(os.dup(1), "w", encoding="utf-8")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    out.write(json.dumps(scan(sys.argv[1]), ensure_ascii=False))
    out.close()
