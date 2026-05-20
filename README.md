# Codex OpenAI Bridge

Minimaler OpenAI-kompatibler Bridge-Server für lokale OpenWebUI-Tests mit Codex CLI. Der Server stellt die Codex-Modelle über `/v1/models` und `/v1/responses` bereit. `/v1/chat/completions` bleibt als Fallback vorhanden, sollte für OpenWebUI aber nicht der primäre Pfad sein.

Das Repository ist für Portainer-/Docker-Compose-Setups gedacht. Es enthält keine Secrets und speichert keine OpenAI- oder Codex-Schlüssel im Image.

## Enthalten

- `src/codex_openai_bridge.py`: HTTP-Bridge mit Responses API, Streaming-Events und optionaler Bearer-Token-Prüfung.
- `Dockerfile`: Container mit Python, Node.js und installierter Codex CLI.
- `docker-compose.yml`: eigenständig startbarer Bridge-Service.
- `examples/openwebui_stack.override.yml`: Compose-Snippet für die Integration in eine bestehende OpenWebUI-Portainer-Stack-Datei.
- `install.sh`: interaktiver Installer, der `.env`, `docker-compose.generated.yml`, Image-Build, Start und OpenWebUI-Provider-Registrierung erledigt.
- `scripts/configure_openwebui_provider.py`: registriert den Bridge-Service in OpenWebUI als `api_type=responses`.
- `docs/freund-installation.md`: knappe Weitergabe-Anleitung für andere Nutzer.
- `tests/`: kleine Payload-/Schema-Tests.

## Schnellstart

Für eine neue Umgebung ist der interaktive Installer der empfohlene Weg:

```bash
bash install.sh
```

Der Installer fragt alle notwendigen Werte ab, erzeugt `.env` und `docker-compose.generated.yml`, baut das Image, startet den Container auf Wunsch und registriert den Provider optional direkt in OpenWebUI.

Für manuelle Nutzung kann weiterhin `.env.example` nach `.env` kopiert und Compose direkt gestartet werden:

```bash
docker compose up -d --build
```

Codex im Container authentifizieren, falls noch kein `CODEX_HOME`-Volume mit gültiger Anmeldung vorhanden ist:

```bash
docker compose run --rm --entrypoint codex codex-openai-bridge login
docker compose restart codex-openai-bridge
```

Healthcheck prüfen:

```bash
curl http://localhost:4010/health
```

Modelle prüfen:

```bash
curl -H "Authorization: Bearer $CODEX_BRIDGE_API_KEY" http://localhost:4010/v1/models
```

## OpenWebUI-Konfiguration

Wenn der Bridge-Container im selben Docker-Netz wie OpenWebUI läuft, ist die interne Provider-URL:

```text
http://codex-openai-bridge:4010/v1
```

In OpenWebUI muss der Provider als OpenAI-kompatibler Anbieter mit `api_type=responses` registriert werden. Das kann per Skript erfolgen:

```bash
export OPENWEBUI_ADMIN_TOKEN="sk-..."
export CODEX_BRIDGE_API_KEY="dein-lokaler-bridge-token"
python scripts/configure_openwebui_provider.py \
  --openwebui-url http://localhost:3000 \
  --bridge-url http://codex-openai-bridge:4010/v1
```

Für die bestehende `openwebui_stack`-Compose-Datei kann `examples/openwebui_stack.override.yml` als Vorlage genutzt werden. Wichtig ist, dass der Service im gleichen Netzwerk wie `open-webui` hängt.

Für Weitergabe an andere Nutzer siehe [docs/freund-installation.md](docs/freund-installation.md).

## Verfügbare Modelle

Standardmäßig werden diese Modell-IDs angeboten:

```text
coder,codex,gpt-5.5,gpt-5.4,gpt-5.4-mini,gpt-5.3-codex,gpt-5.3-codex-spark
```

`coder` und `codex` werden intern auf `gpt-5.5` abgebildet, damit vorhandene OpenWebUI-Custom-Modelle mit `base_model_id: coder` ohne weitere Anpassung gegen Codex laufen können.

Die Liste kann über `CODEX_BRIDGE_MODELS` überschrieben werden.

## Sicherheit

- Keine Secrets in Git schreiben.
- `CODEX_BRIDGE_API_KEY` ist optional, sollte im OpenWebUI-Netz aber gesetzt werden.
- Das Codex-Login liegt im Docker-Volume `codex_home` oder in einem explizit gemounteten `CODEX_HOME`.
- Der Service führt `codex exec` aus. Das ist für lokale Tests gedacht und sollte nicht ungeschützt ins öffentliche Netz gestellt werden.

## Entwicklung

```bash
python -m py_compile src/codex_openai_bridge.py scripts/configure_openwebui_provider.py
python -m unittest discover -s tests
docker compose config
docker build -t codex-openai-bridge:dev .
bash -n install.sh
```
