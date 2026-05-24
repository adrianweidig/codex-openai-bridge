# Support

Für normale Nutzungsfragen, Fehlermeldungen und Verbesserungswünsche nutze bitte GitHub Issues.

## Vor einem Issue

Prüfe bitte:

- [README.md](README.md)
- [docs/freund-installation.md](docs/freund-installation.md)
- [docs/FAQ.md](docs/FAQ.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Gute Fehlerberichte

Hilfreich sind:

- verwendeter Startpfad: `install.sh`, `docker compose` oder eigene Compose-Datei
- relevante Umgebungsvariablen ohne Secret-Werte
- erwartetes und tatsächliches Verhalten
- gekürzte Logs ohne Tokens, API-Keys oder private Inhalte
- Ergebnis von `curl http://localhost:4010/health`
- ob `/v1/models` mit Bearer-Token erreichbar ist

## Security

Sicherheitsprobleme bitte nicht öffentlich melden. Siehe [SECURITY.md](SECURITY.md).
