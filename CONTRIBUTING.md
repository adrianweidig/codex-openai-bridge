# Mitwirken

Danke, dass du zu Codex OpenAI Bridge beitragen möchtest. Dieses Projekt ist bewusst klein gehalten: Änderungen sollten nachvollziehbar, testbar und eng am Bridge-/OpenWebUI-Anwendungsfall bleiben.

## Geeignete Beiträge

- reproduzierbare Fehlerberichte
- kleine Bugfixes
- Verbesserungen an Streaming-, Payload- oder Redaktionslogik
- klarere Dokumentation, Beispiele und Installationshinweise
- Tests für bestehendes Verhalten
- Compose-/Portainer-Hinweise, sofern sie keine Secrets enthalten

## Vor dem Start

1. Prüfe offene Issues und Pull Requests, um Doppelarbeit zu vermeiden.
2. Erstelle einen Branch mit beschreibendem Namen, zum Beispiel `fix/streaming-usage` oder `docs/openwebui-setup`.
3. Halte den Diff klein und fokussiert.

## Lokale Checks

Führe vor einem Pull Request die passenden Checks aus:

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

## Code-Stil

- Keine neue Framework-Schicht ohne klaren Nutzen.
- Öffentliche Endpunkte, CLI-Flags, Umgebungsvariablen und Standardwerte nicht unbegründet ändern.
- Secrets, Prompt-Inhalte und Token nicht loggen.
- Neue Statusmeldungen müssen sicher sein und dürfen keine versteckten Modellgedanken offenlegen.
- Tests ergänzen, wenn Payload-Parsing, Streaming, Redaction oder OpenWebUI-Kompatibilität verändert werden.

## Dokumentation

Dokumentationsänderungen sollen konkrete Nutzungsfragen beantworten. Bitte keine Behauptungen über Features, Sicherheit, Releases oder Plattformunterstützung ergänzen, wenn sie nicht im Code oder in vorhandenen Projektdateien belegbar sind.

## Pull Requests

Ein guter Pull Request enthält:

- kurze Beschreibung des Problems
- klare Zusammenfassung der Änderung
- ausgeführte Checks
- Hinweise auf bewusst nicht getestete Teile, zum Beispiel Docker-Build ohne lokale Docker-Verfügbarkeit
- Screenshots oder Logs nur, wenn sie keine Secrets enthalten

## Security

Bitte melde Sicherheitsprobleme nicht öffentlich als Issue. Siehe [SECURITY.md](SECURITY.md).

## Kommunikation

Bleib konkret, respektvoll und lösungsorientiert. Technische Kritik ist willkommen, persönliche Angriffe nicht.
