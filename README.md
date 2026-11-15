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
4. En Claude Code, `/mcp` debe mostrar `ableton` conectado. Al primer uso Claude te pregunta nombre, generos
   y temas de referencia.

Opcional: `uv run --directory server python batch_presets.py` genera un Rack por cada VST3 con sus parametros
expuestos, para que Claude pueda moverlos (los que pasan la prueba salen en `plugins_listos`).

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
