# Release-Prozess

Dieses Repository nutzt GitHub Releases und Tags für veröffentlichte Stände. Der folgende Prozess ist eine Maintainer-Richtschnur und führt keine automatische Veröffentlichung ein.

## Vor einem Release

1. `CHANGELOG.md` im Abschnitt `Unreleased` aktualisieren.
2. Lokale Checks ausführen:

   ```bash
   python -m py_compile src/codex_openai_bridge.py scripts/configure_openwebui_provider.py
   python -m unittest discover -s tests
   bash -n install.sh
   ```

3. Wenn Docker verfügbar ist:

   ```bash
   CODEX_BRIDGE_SECRET_FILE=/dev/null docker compose config
   docker build -t codex-openai-bridge:dev .
   ```

4. README, Installationsanleitung und Beispiele gegen den aktuellen Code prüfen.
5. Sicherstellen, dass keine Secrets oder lokalen `.env`-Dateien im Arbeitsbaum liegen.

## Versionierung

Die Release-Tags verwenden SemVer, zum Beispiel `v0.1.0`. Solange kein Paketmanifest existiert, ist der GitHub-Release die maßgebliche Versionsquelle.

## GitHub Release

1. Release-Branch oder direkten Release-Commit vorbereiten.
2. Changelog-Eintrag aus `Unreleased` in einen datierten Abschnitt verschieben.
3. Tag setzen, zum Beispiel `v0.1.0`, wenn Maintainer die Version festgelegt haben.
4. GitHub Release mit kompakten Release Notes erstellen.
5. Optional Docker-Image-Build und Verteilung separat dokumentieren, falls ein Registry-Ziel festgelegt wird.
