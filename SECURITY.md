# Security Policy

Codex OpenAI Bridge startet lokale Codex-CLI-Prozesse und ist für kontrollierte lokale Docker-/OpenWebUI-Umgebungen gedacht. Der Dienst sollte nicht ungeschützt im öffentlichen Netz betrieben werden.

## Unterstützte Versionen

Das Repository hat aktuell keine dokumentierten Releases oder Versionstags. Sicherheitskorrekturen beziehen sich daher auf den aktuellen `main`-Branch, bis ein Release-Modell festgelegt ist.

## Sicherheitsprobleme melden

Bitte poste keine sensiblen Schwachstellendetails öffentlich als Issue.

Nutze, sofern für dieses Repository aktiviert:

- GitHub Private Vulnerability Reporting
- GitHub Security Advisories

Wenn kein privater Meldeweg sichtbar ist, öffne ein öffentliches Issue nur mit einer knappen, nicht ausnutzbaren Beschreibung und bitte um einen privaten Kontaktweg. Lege keine Tokens, Logs mit Secrets, privaten URLs oder reproduzierbare Exploit-Details offen.

## Erwarteter Ablauf

1. Eingang der Meldung prüfen.
2. Reproduzierbarkeit und betroffene Konfiguration eingrenzen.
3. Fix oder Mitigation vorbereiten.
4. Tests und Dokumentation aktualisieren.
5. Veröffentlichung oder Advisory nach Maintainer-Entscheidung.

## Projektgrenzen

- Die Bridge speichert keine OpenAI- oder Codex-Schlüssel im Image.
- Runtime-Secrets gehören in `.env`, Docker Secrets oder lokale Secret-Dateien, die nicht committed werden.
- Prompt- und Antwortinhalte sollen nicht in Container-Logs geschrieben werden.
- Die Bridge führt `codex exec` aus; die Umgebung muss entsprechend abgesichert sein.

Diese Policy ist keine Sicherheitsgarantie. Sie beschreibt den vorgesehenen Umgang mit Meldungen und die bekannten Betriebsgrenzen.
