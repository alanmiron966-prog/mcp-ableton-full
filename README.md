# Ableton MCP

Controla Ableton Live 12 desde Claude: componer (pistas, clips, notas, samples), arreglar en el Arrangement
(clips y automatizacion), mezclar (mixer, plugins con valores reales como "250 Hz" o "-3 dB") y medir el
master (LUFS, true peak, balance por bandas) comparado con tus temas de referencia. Todo local: Live escucha
solo en 127.0.0.1:9877.

## Requisitos

- Windows, Ableton Live 12
- [uv](https://docs.astral.sh/uv/) (instala Python 3.14 y las dependencias solo)
- ffmpeg en el PATH (para medir audio)
- Claude Code

## Instalacion

1. Cierra Live.
2. `python install.py` copia el Remote Script a tu User Library y registra el servidor `ableton` en Claude Code.
3. Abre Live > Preferencias > Link, Tempo & MIDI > Control Surface: **AbletonClaude**.
4. En Claude Code, `/mcp` debe mostrar `ableton` conectado.

## Primer uso

1. **Plugins** (`ableton_scan_plugins`, unos minutos con un set vacio abierto): escanea tus VST3, genera un
   Rack por plugin con sus parametros expuestos y prueba cada uno en Live. Los que funcionan salen en
   `plugins_listos`; los que cierran Live quedan en `no_usar` (si Live se cierra, abrelo y Claude sigue donde iba).
2. **Perfil**: Claude te pregunta nombre, generos y 1-3 temas de referencia (archivos de audio).

## Que hace

- Pedir una cancion entrega el proyecto completo: produccion en el Arrangement (un sonido por pista, secciones
  marcadas con `ableton_locators`), mezcla y master en el mismo set, medido contra tus referencias.
  Guarda el set con nombre (Ctrl+S) antes de empezar: medir el master lo necesita.
- Samples: escanea tus librerias y las busca por tipo (kick, clap, hat_closed...).
- Si actualizas el Remote Script y no reinicias Live, `ableton_status` lo avisa.

## Medir el master sin exportar

`ableton_record_master` graba la salida del master en la pista "Master Rec". Live bloquea el wav recien
grabado hasta cerrar el set, asi que `ableton_reload_set` guarda, cierra y reabre Live (unos 35 s) y devuelve
la toma para `ableton_analyze_audio` o `ableton_compare_reference`.

## Limites conocidos

- Tras actualizar el Remote Script hay que reiniciar Live: cambiar el Control Surface no recarga el codigo.
- La automatizacion del Arrangement se graba en tiempo real (la API de Live no deja escribirla directa).
- Ozone cuelga Live al cargarlo desde el MCP.

## Pruebas

`uv run --directory server python ../tests/test_sin_ableton.py` (no necesita Live).

## Licencia

MIT. Las ideas de marcadores y aviso de version vienen de
[ahujasid/ableton-mcp](https://github.com/ahujasid/ableton-mcp) (MIT).
