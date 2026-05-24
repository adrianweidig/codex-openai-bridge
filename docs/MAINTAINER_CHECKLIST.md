# Maintainer-Checkliste

Diese Punkte erfordern Maintainer-Rechte, externe Plattformentscheidungen oder rechtliche Entscheidungen und wurden deshalb nicht automatisch umgesetzt.

## GitHub Repository Settings

- Repository-Beschreibung setzen, z. B. `OpenAI-compatible bridge that exposes local Codex CLI runs to OpenWebUI`.
- Topics prüfen und setzen, z. B. `openwebui`, `codex`, `openai-compatible`, `responses-api`, `docker-compose`, `python`.
- Repository-Sichtbarkeit bewusst festlegen. Der lokale Check zeigte das GitHub-Repository zuletzt als `PRIVATE`.
- Issues aktivieren, wenn öffentliche Fehlerberichte erwünscht sind.
- Discussions aktivieren, wenn Support- und Ideen-Austausch getrennt von Issues laufen soll.
- Wiki deaktiviert lassen oder bewusst aktivieren; die Projektdokumentation liegt bereits im Repository.

## Social Preview

- `docs/assets/social-preview.svg` als Vorlage verwenden.
- Optional als PNG im Format 1280 x 640 exportieren und in GitHub unter Settings -> Social preview hochladen.

## Branch Protection

- Branch Protection oder Ruleset für `main` einrichten.
- Required Status Checks aktivieren:
  - `python`
  - `CodeQL`
- Pull Requests vor Merge verlangen.
- Direktes Pushen nach `main` für Kollaborationsbetrieb einschränken.

## Security

- Private Vulnerability Reporting aktivieren, falls für das Repository verfügbar.
- Dependabot Security Updates aktivieren.
- Secret Scanning aktivieren, falls im GitHub-Plan verfügbar.
- Code Scanning Alerts für CodeQL prüfen.
- Einen privaten Sicherheitskontakt festlegen, falls GitHub Security Advisories nicht genutzt werden sollen.

## Lizenz

- Erledigt: MIT-Lizenzdatei und README-Badge sind im Repository vorhanden.
- Falls später Paketmetadaten entstehen, SPDX-Lizenz `MIT` konsistent eintragen.

## Releases

- Erstes Release ist als `v0.1.0` vorgesehen.
- Versionierungsmodell: SemVer über GitHub Release Tags.
- `CHANGELOG.md` aus `Unreleased` in einen Release-Abschnitt überführen.
- Release Notes aus den tatsächlichen Änderungen schreiben.

## Paket- oder Image-Verteilung

- Nur dann Registry-Badges ergänzen, wenn ein Paket oder Image tatsächlich veröffentlicht ist.
- Falls Docker Images veröffentlicht werden sollen, Ziel-Registry, Tagging und Build-Prozess dokumentieren.
