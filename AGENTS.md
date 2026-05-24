# AGENTS.md

## Projektüberblick

Codex OpenAI Bridge ist ein kleiner Python-HTTP-Server, der lokale Codex-CLI-Läufe als OpenAI-kompatiblen Provider für OpenWebUI verfügbar macht. Der primäre OpenWebUI-Pfad ist `/v1/responses`; `/v1/chat/completions` bleibt als Fallback erhalten.

## Arbeitsregeln

- Antworte in diesem Repository standardmäßig auf Deutsch.
- Erhalte bestehende Endpunkte, Umgebungsvariablen, CLI-Flags, Modell-IDs und Standardwerte, sofern der Nutzer keine Änderung ausdrücklich verlangt.
- Ändere Laufzeitverhalten nicht für reine Dokumentations- oder Repository-Hygiene-Aufgaben.
- Halte Diffs klein und projektbezogen.
- Keine Secrets, Tokens, API-Keys, privaten Logs oder Codex-Login-Daten ausgeben, erzeugen oder committen.
- Keine produktiven Deployments ausführen.
- Docker- oder OpenWebUI-Live-Änderungen nur ausführen, wenn der Nutzer das ausdrücklich verlangt.

## Wichtige Dateien

- `src/codex_openai_bridge.py`: Bridge-Server, Event-Mapping, Redaction, Streaming, Auth
- `scripts/configure_openwebui_provider.py`: OpenWebUI-Provider-Registrierung
- `install.sh`: interaktiver lokaler Installer
- `docker-compose.yml`: Standard-Compose-Setup
- `examples/openwebui_stack.override.yml`: Integrationsvorlage für bestehende OpenWebUI-Stacks
- `tests/test_bridge_payloads.py`: Unit-Tests für Payloads, Streaming und Redaction

## Entwicklungsbefehle

```bash
python -m py_compile src/codex_openai_bridge.py scripts/configure_openwebui_provider.py
python -m unittest discover -s tests
bash -n install.sh
```

Wenn Docker verfügbar ist:

```bash
CODEX_BRIDGE_SECRET_FILE=/dev/null docker compose config
docker build -t codex-openai-bridge:dev .
```

## Dokumentationsregeln

- README-Inhalte nicht entfernen, wenn sie Installations-, Sicherheits-, OpenWebUI- oder Konfigurationswissen enthalten.
- Neue Aussagen müssen aus Code, Compose-Dateien, Tests oder vorhandener Dokumentation ableitbar sein.
- Keine Lizenz, Releases, Registry-Veröffentlichung, Roadmap-Zusagen oder Sicherheitsgarantien erfinden.
- Lokale Links relativ halten, wenn möglich.
- Keine externen Badges ergänzen, die nicht zum ermittelten GitHub-Repository gehören.

## Sicherheitsgrenzen

- `CODEX_BRIDGE_API_KEY`, OpenWebUI-Admin-Token und Codex-Login-Daten sind Secrets.
- Prompt- und Antwortinhalte dürfen nicht unnötig in Logs oder Dokumente übernommen werden.
- `CODEX_BRIDGE_BYPASS_SANDBOX=true` nur als bewusstes Container-Sicherheitsmodell dokumentieren oder nutzen.
- Der Dienst führt `codex exec` aus und darf nicht als öffentlich gehärteter Internetdienst beschrieben werden.
