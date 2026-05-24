# Maintainer-Checkliste

Diese Liste hält GitHub- und Maintainer-Aufgaben fest, die nicht allein aus Repository-Dateien ableitbar sind. Erledigte Punkte beschreiben den zuletzt gesetzten Zustand.

## GitHub Repository Settings

- Erledigt: Repository ist öffentlich.
- Erledigt: Beschreibung ist gesetzt: `OpenAI-compatible bridge that exposes local Codex CLI runs to OpenWebUI`.
- Erledigt: Topics sind gesetzt: `openwebui`, `codex`, `openai-compatible`, `responses-api`, `docker-compose`, `python`, `portainer`.
- Erledigt: Issues sind aktiviert.
- Erledigt: Discussions sind aktiviert.
- Erledigt: Wiki ist deaktiviert; die Projektdokumentation liegt im Repository.

## Social Preview

- `docs/assets/social-preview.svg` ist als Vorlage vorhanden.
- Offen: GitHub Social Preview muss über die GitHub-Weboberfläche hochgeladen werden; für den Upload gibt es keinen stabilen `gh`-/REST-Workflow.

## Branch Protection

- Erledigt: Branch Protection für `main` ist eingerichtet.
- Erledigt: Required Status Checks sind aktiviert:
  - `Python checks`
  - `CodeQL`
- Erledigt: Pull Requests vor Merge sind verlangt.
- Erledigt: direkte Force-Pushes und Branch-Löschungen sind blockiert.

## Security

- Erledigt: Private Vulnerability Reporting ist aktiviert.
- Erledigt: Dependabot Security Updates sind aktiviert.
- Erledigt: Secret Scanning und Push Protection sind aktiviert.
- Erledigt: CodeQL-Workflow ist vorhanden; Code Scanning läuft nach GitHub Actions.
- Offen: Einen privaten Sicherheitskontakt ergänzen, falls GitHub Security Advisories nicht ausreichen.

## Lizenz

- Erledigt: MIT-Lizenzdatei und README-Badge sind im Repository vorhanden.
- Falls später Paketmetadaten entstehen, SPDX-Lizenz `MIT` konsistent eintragen.

## Releases

- Erledigt: erstes Release ist als `v0.1.0` vorgesehen.
- Versionierungsmodell: SemVer über GitHub Release Tags.
- Erledigt: `CHANGELOG.md` enthält den Abschnitt `0.1.0 - 2026-05-24`.
- Offen: GitHub Release nach Push des aktuellen Commits erstellen, falls noch nicht vorhanden.

## Paket- oder Image-Verteilung

- Nur dann Registry-Badges ergänzen, wenn ein Paket oder Image tatsächlich veröffentlicht ist.
- Falls Docker Images veröffentlicht werden sollen, Ziel-Registry, Tagging und Build-Prozess dokumentieren.
