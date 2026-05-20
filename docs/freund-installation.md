# Installation für Weitergabe an Freunde

Diese Anleitung ist für jemanden gedacht, der nur Docker, Docker Compose und eine laufende OpenWebUI-Instanz hat.

## Voraussetzungen

- Docker mit `docker compose`
- Git
- Eine laufende OpenWebUI-Instanz
- Ein OpenWebUI-Admin-API-Key
- Ein Codex/OpenAI-Konto für `codex login`

## Installation

Repository klonen:

```bash
git clone https://github.com/adrianweidig/codex-openai-bridge.git
cd codex-openai-bridge
```

Installer starten:

```bash
bash install.sh
```

Der Installer fragt ab:

- OpenWebUI-URL vom Host aus, z. B. `http://localhost:3000`
- Docker-Netz der OpenWebUI-Instanz, z. B. `ai_net`
- interne Bridge-URL aus Sicht von OpenWebUI, meist `http://codex-openai-bridge:4010/v1`
- Host-Port für lokale Tests, standardmäßig `4010`
- Modellliste
- lokalen Bridge-API-Key
- ob Image gebaut und Container gestartet werden sollen
- ob `codex login` im Container ausgeführt werden soll
- ob der Provider automatisch in OpenWebUI registriert werden soll

Der Bridge-API-Key wird in `.env` und als lokale Secret-Datei unter `secrets/codex_bridge_api_key` abgelegt. Der Container bekommt nur `/run/secrets/codex_bridge_api_key` gemountet. Der OpenWebUI-Admin-API-Key wird nur für die Registrierung abgefragt und nicht in `.env` gespeichert.

## Nach der Installation

Status prüfen:

```bash
docker compose --env-file .env -f docker-compose.generated.yml ps
```

Healthcheck:

```bash
curl http://localhost:4010/health
```

Modelle prüfen:

```bash
source .env
curl -H "Authorization: Bearer $CODEX_BRIDGE_API_KEY" http://localhost:4010/v1/models
```

OpenWebUI sollte danach einen Provider mit `api_type=responses` und dieser internen URL haben:

```text
http://codex-openai-bridge:4010/v1
```

## In bestehende OpenWebUI-Compose-Datei integrieren

Wer den Service direkt in seinen OpenWebUI-Stack kopieren will, kann `examples/openwebui_stack.override.yml` als Vorlage nutzen. Wichtig sind:

- gleiches Docker-Netz wie OpenWebUI
- `CODEX_BRIDGE_API_KEY_FILE` als Secret-Dateipfad, z. B. `/run/secrets/codex_bridge_api_key`
- persistentes Volume für `/home/codex/.codex`
- Provider-URL in OpenWebUI: `http://codex-openai-bridge:4010/v1`
- Provider-API-Typ: `responses`

## Betrieb

Container stoppen:

```bash
docker compose --env-file .env -f docker-compose.generated.yml down
```

Container aktualisieren:

```bash
git pull
bash install.sh
```

Wenn Codex nicht mehr authentifiziert ist:

```bash
docker compose --env-file .env -f docker-compose.generated.yml run --rm --entrypoint codex codex-openai-bridge login
docker compose --env-file .env -f docker-compose.generated.yml restart codex-openai-bridge
```
