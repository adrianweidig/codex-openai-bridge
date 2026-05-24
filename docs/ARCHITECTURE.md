# Architektur

Codex OpenAI Bridge ist eine kleine HTTP-Brücke zwischen OpenWebUI und der Codex CLI. Der Server nimmt OpenAI-kompatible Requests entgegen, baut daraus einen Codex-Prompt, startet `codex exec --json` und übersetzt die Codex-JSONL-Ereignisse in sichtbare HTTP- oder SSE-Antworten.

## Hauptkomponenten

| Komponente | Datei | Aufgabe |
| --- | --- | --- |
| HTTP-Server | `src/codex_openai_bridge.py` | Endpunkte, Auth-Prüfung, JSON-Parsing, SSE-Ausgabe |
| Codex Runner | `src/codex_openai_bridge.py` | Startet Codex CLI, liest stdout/stderr, behandelt Timeout und Client-Abbruch |
| Event Mapping | `src/codex_openai_bridge.py` | Übersetzt Codex-JSONL-Events in sichere sichtbare Deltas |
| OpenWebUI-Konfiguration | `scripts/configure_openwebui_provider.py` | Registriert oder ersetzt den Bridge-Provider in OpenWebUI |
| Installer | `install.sh` | Erzeugt lokale Konfiguration, Secret-Datei und Compose-Datei |
| Container | `Dockerfile`, `docker-compose.yml` | Liefert Codex CLI, Python, Node.js, Playwright und Hilfswerkzeuge |

## Request-Flow

1. OpenWebUI sendet einen Request an `/v1/responses` oder als Fallback an `/v1/chat/completions`.
2. Die Bridge prüft optional den Bearer-Token aus `CODEX_BRIDGE_API_KEY` oder `CODEX_BRIDGE_API_KEY_FILE`.
3. Aus `instructions`, `input` oder `messages` wird ein textbasierter Prompt aufgebaut.
4. Die Bridge startet `codex exec --json` im konfigurierten `CODEX_BRIDGE_WORKDIR`.
5. Codex-JSONL-Ereignisse werden gelesen, redigiert und in sichtbare Status- oder Assistant-Deltas übersetzt.
6. Bei `stream=true` werden SSE-Events sofort an den Client gesendet.
7. Die finale Antwort wird als Responses-Objekt oder Chat-Completion-Objekt zurückgegeben.

## Streaming

Die Bridge sendet Responses-API-Lifecycle-Events wie `response.created`, `response.output_item.added`, `response.output_text.done` und `response.completed`.

Wenn `CODEX_BRIDGE_OPENWEBUI_CHAT_COMPAT_STREAM=true` gesetzt ist, werden sichtbare Deltas zusätzlich als `chat.completion.chunk`-Events gespiegelt. Dieser Modus ist für OpenWebUI-Instanzen gedacht, deren Chat-Oberfläche Responses-Provider intern über den Chat-Completion-Renderer ausgibt.

## Sicherheitsgrenzen

- Prompt- und Antwortinhalte werden nicht in Container-Logs geschrieben.
- Tokenartige Werte und sensitive Pfade werden für sichtbare Statusmeldungen redigiert.
- Versteckte Modellgedanken werden nicht offengelegt.
- Der Service führt `codex exec` aus und sollte nicht ungeschützt im öffentlichen Netz laufen.
- `CODEX_BRIDGE_BYPASS_SANDBOX=true` ist nur sinnvoll, wenn der Container selbst die Sicherheitsgrenze bildet.

## Persistenz

Die Bridge ist stateless. Sie speichert keine Chat-Historie und implementiert keine serverseitige Verkettung über `previous_response_id`.

Persistente Daten liegen außerhalb der Anwendung:

- Codex-Login im Docker-Volume `codex_home` oder in einem explizit gemounteten `CODEX_HOME`
- optionale lokale Secret-Datei unter `secrets/codex_bridge_api_key`
- optionaler Arbeitsbereich unter `workspace/`

## Erweiterungspunkte

- weitere Codex-Eventtypen in `map_codex_json_event`
- zusätzliche Modellaliasse in `MODEL_ALIASES`
- andere Provider-Registrierungslogik in `scripts/configure_openwebui_provider.py`
- alternative Container-/Portainer-Topologien über Compose-Dateien
