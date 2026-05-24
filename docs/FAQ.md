# FAQ

## Warum ist `/v1/responses` der empfohlene Pfad?

OpenWebUI kann die Bridge als OpenAI-kompatiblen Provider mit `api_type=responses` registrieren. Dieser Pfad bildet die Responses-API-Events ab und ist der dokumentierte Hauptpfad des Projekts. `/v1/chat/completions` bleibt als Fallback vorhanden.

## Warum bekomme ich bei `/v1/models` einen `401 Unauthorized`?

Wenn `CODEX_BRIDGE_API_KEY` oder `CODEX_BRIDGE_API_KEY_FILE` gesetzt ist, erwartet die Bridge einen passenden Bearer-Token:

```bash
curl -H "Authorization: Bearer $CODEX_BRIDGE_API_KEY" http://localhost:4010/v1/models
```

`/health` ist weiterhin ohne Auth erreichbar.

## Warum sehe ich in OpenWebUI erst nach einem Reload eine Antwort?

OpenWebUI-Live-Ausgaben im Hauptchat laufen über Socket.IO und benötigen im Browser eine normale OpenWebUI-JWT-Session. API-Key-only REST-Aufrufe können Antworten speichern, erhalten aber keine `user:<id>`-Socket-Events.

## Wann brauche ich `CODEX_BRIDGE_OPENWEBUI_CHAT_COMPAT_STREAM=true`?

Dieser Modus hilft bei OpenWebUI-Instanzen, deren Chatpfad Responses-Provider intern weiter über den Chat-Completion-Renderer ausgibt. Die Bridge bleibt dabei am `/v1/responses`-Endpunkt, spiegelt sichtbare Textdeltas aber zusätzlich als `chat.completion.chunk`.

## Wo liegt der Codex-Login?

Im Docker-Setup liegt der Login im Volume `codex_home`, gemountet nach `/home/codex/.codex`. Alternativ kann ein explizites `CODEX_HOME` gemountet werden.

## Darf ich die Codex-Sandbox im Container umgehen?

Nur bewusst. `CODEX_BRIDGE_BYPASS_SANDBOX=true` ist für Fälle gedacht, in denen Docker die Sicherheitsgrenze bildet und Codex im Container Shell-/Tool-Schritte ausführen soll.

## Welche Dateien dürfen nicht committed werden?

Keine Secrets und keine lokalen Runtime-Daten. `.gitignore` schließt unter anderem `.env`, `secrets/`, `codex-home/`, `workspace/` und `docker-compose.generated.yml` aus.
