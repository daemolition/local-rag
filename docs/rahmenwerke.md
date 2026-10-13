# Rahmenwerke: Einordnung für SOC 2 und NIS2 (und Nachbarn)

> Stand 2026-10-12, Version 0.1.3. **Orientierung, keine Zertifizierung, keine Rechtsberatung.** Belegquelle: [`audit-checklist-open-knowledge-ui.md`](./audit-checklist-open-knowledge-ui.md); Datenflüsse: [`data-mapping.md`](./data-mapping.md). Es wird nirgends Konformität behauptet, nur "liefert Nachweise für" oder "Lücke".

## SOC 2 (AICPA Trust Services Criteria)

**Was es prüft:** Ein unabhängiger Wirtschaftsprüfer testet die Kontrollen eines **Dienstleisters** gegen die Kriterien Security (Pflicht, "Common Criteria"), optional Availability, Confidentiality, Processing Integrity und Privacy. **Typ I** bewertet den Entwurf der Kontrollen zu einem Stichtag, **Typ II** ihre Wirksamkeit über einen Zeitraum (meist 3 bis 12 Monate). Zertifiziert wird eine Organisation, kein Code.

**Projekt-Bezug:** Als Open-Source-Software ohne Betreiber gibt es nichts zu auditieren; ein SOC 2 gilt erst für **dich als Betreiber** (gehostetes Angebot) oder für deine Firma. Das Projekt liefert Nachweise für folgende Kontrollbereiche und nennt Lücken:

| Kriterium | Belegbar | Lücke |
|---|---|---|
| CC6.1-6.3 Zugriff | Rollen und Gruppen (`app/access.py`), SSO/LDAP, Passwort-Hashing | MFA lokal, Zugriffsüberprüfungen (Review-Prozess) |
| CC6.6-6.7 Datenübertragung | TLS über Proxy möglich, Link-Local-Sperre | Security-Header, TLS-Pflicht nicht erzwungen |
| CC7.1-7.3 Überwachung, Vorfälle | `/health`, Logs | **kein Audit-Log**, kein Alarmwesen, kein Incident-Prozess |
| CC8.1 Änderungsmanagement | Git, CI, Changelog, Release-Skript, PR-Vorlage | Branch-Schutz, Pflicht-Review, signierte Releases |
| CC9.2 Lieferanten | Lockfiles, Dependabot für Actions | Dependabot/SBOM für pip/npm/docker, Lieferantenbewertung |
| A1 Verfügbarkeit | Postgres, Compose | Backup-/Restore-Nachweis, Wiederanlauftest |
| C1 Vertraulichkeit | Geheimnisse nie ausgeliefert | Verschlüsselung at rest, Aufbewahrung/Löschung automatisch |
| P Privacy | Löschwege, Datenfluss-Doku | Export, Einwilligungs-/Hinweistexte |

## NIS2 (EU-Richtlinie 2022/2555, in Deutschland NIS2UmsuCG)

**Was es prüft:** Pflichten für "besonders wichtige" und "wichtige" Einrichtungen (u. a. Energie, Gesundheit, digitale Infrastruktur, IT-Dienste für Unternehmen, Hersteller): Risikomanagement-Maßnahmen (Art. 21: u. a. Richtlinien, Vorfallbewältigung, Business Continuity, **Lieferkettensicherheit**, sichere Entwicklung, Schwachstellenmanagement, Wirksamkeitsprüfung, Kryptografie, Zugriffskontrolle, MFA), Meldepflichten (Frühwarnung 24 h, Meldung 72 h, Abschlussbericht 1 Monat) und Leitungsverantwortung samt Schulung.

**Projekt-Bezug:** Das Projekt ist nicht selbst reguliert. Für eine betroffene Einrichtung, die es betreibt, ist es **Teil der Lieferkette und der eigenen IT** und muss in deren Risikomanagement erscheinen. Was das Projekt dafür liefert:

| Art. 21 Maßnahme | Belegbar | Lücke |
|---|---|---|
| Zugriffskontrolle / MFA | Rollen, Gruppen, SSO via OIDC (MFA beim Anbieter) | lokale MFA fehlt |
| Kryptografie | Passwort-Hashing, LDAP/OIDC mit Zertifikatsprüfung | keine Verschlüsselung at rest |
| Schwachstellenmanagement | `SECURITY.md` (Meldeweg, 72 h), Dependabot für Actions | Dependabot für pip/npm/docker, keine SBOM, kein Support-Zeitraum |
| Sichere Entwicklung | Tests (449), PR-Vorlage, SSRF-/Injection-Tests | Pflicht-Review nicht erzwungen, Frontend ohne Tests |
| Vorfallbewältigung | - | **kein Audit-Log**, kein Meldeprozess (24 h/72 h) beim Betreiber |
| Business Continuity | Postgres, Compose | Backup-/Restore-Konzept nicht dokumentiert |
| Lieferkette | `uv.lock`, `package-lock.json`, gepinnte Actions | SBOM, Lizenz-/Herkunftsprüfung, Basis-Images nicht auf Digest gepinnt |

Betreiberpflichten, die **nicht** im Projekt lösbar sind: Registrierung beim BSI, Meldeprozess, Schulung der Leitung, Notfallplan, Bewertung der LLM-Anbieter als Lieferanten.

## Nachbarn kurz

- **ISO/IEC 27001:** ISMS einer Organisation, kein Produktzertifikat. Wirkt wie SOC 2 als Rahmen für Richtlinien, Risikoanalyse und Maßnahmen (Annex A); die Tabellen oben decken sich weitgehend.
- **EU CRA:** gilt für Produkte mit digitalen Elementen **im Rahmen einer kommerziellen Tätigkeit**; rein nicht-kommerzielle Open-Source-Software ist ausgenommen. Wird das Projekt kostenpflichtig angeboten oder an Kunden ausgeliefert, ändert sich das. Typische Lücken dann: SBOM, signierte Releases, Support-Zeitraum, Meldepflichten. **Rechtsprüfung empfohlen.**
- **DSGVO/BDSG:** Art. 32 und Art. 30 siehe Audit-Checkliste und Data Mapping; Auftragsverarbeitung (Art. 28) für jeden eingetragenen Cloud-Endpunkt.
- **EU AI Act:** Das Projekt ist ein Werkzeug mit Allzweck-LLMs; Transparenz- und Aufsichtspflichten hängen vom Einsatzzweck des Betreibers ab. Prüfung im Einzelfall.

## Kernbotschaft

Belegt sind Rollen- und Gruppenzugriff, Login-Härtung mit SSO/LDAP, SSRF-Schutz, Löschwege, CI, Tests und ein Meldeweg für Schwachstellen. Offen sind vor allem **Audit-Log**, **Verschlüsselung der Zugangsdaten**, **CSRF/Security-Header/Container-Härtung**, **Lieferketten-Nachweise (SBOM, Dependabot für alle Ökosysteme, signierte Releases)** und **Betriebsprozesse** (Backup, Vorfallmeldung). Ein Zertifikat gibt es nur für eine Organisation mit gelebten Prozessen; vor einem kommerziellen Angebot oder einem regulierten Einsatz sind CRA, NIS2-Betroffenheit und Verträge rechtlich zu klären.

## Nachtrag: SQL-Datenbanken als Knowledge

Zugriff auf Fremdsysteme folgt Least Privilege: lesender Datenbank-Benutzer, Tabellen-/Spaltenfreigaben, Read-only-Sitzung, SQL-Prüfung und getrennter Worker ohne Zugriff auf App-Daten (siehe `docs/sql-knowledge.md`). Offene Punkte: kein Zeilenfilter pro Nutzer, keine Protokollierung der einzelnen Abfragen im Produkt (nur Log des Workers), Passwort unverschlüsselt in der App-Datenbank.
