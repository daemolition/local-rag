# Audit-Checkliste: Open Knowledge UI (Selbstauskunft)

> Jede Zeile mit Fundstelle. Status: ✅ vorhanden · ⚠️ teilweise · ❌ fehlt. Stand: 2026-10-12, Version 0.1.3. Vor Wiederverwendung gegen den Code prüfen. Orientierung, keine Zertifizierung, keine Rechtsberatung.

## Security

| Prüfpunkt | Status | Fundstelle/Beleg | Kommentar |
|---|---|---|---|
| Passwort-Hashing | ✅ | `app/users.py` (`generate_password_hash`/`check_password_hash`, Werkzeug) | Konstante Laufzeit bei unbekanntem Konto über `_DUMMY_HASH` (`app/users.py:54`) |
| Sitzung / Secret Key | ⚠️ | `app/__init__.py:306-312` | Schlüssel wird zufällig erzeugt und in der DB gespeichert (`SECRET_KEY` sensibel). Keine Rotation, Cookie-Flags (`Secure`, `SameSite`) nicht gesetzt (nur Flask-Standard) |
| Stilles Klartext-Fallback | ⚠️ | `app/connections.py:140-176` | Zugangsdaten (API-Keys, LDAP-Bind-Passwort, OIDC-Secret, Quellen-Keys) liegen **unverschlüsselt** in der Datenbank; sie werden nie ausgeliefert (`has_key`), aber nicht at rest verschlüsselt |
| Feldverschlüsselung / Key-Rotation | ❌ | - | Lücke, siehe `docs/data-mapping.md` |
| Secrets nie im Repo | ✅ | `env.example`, `.gitignore`; Standardpasswort nur als Startwert | `admin`/`admin` beim ersten Start muss geändert werden (`README.md`, `SECURITY.md`) |
| Rollen / RBAC | ✅ | `app/auth.py` (`require_role`), `app/access.py` (Gruppen, Grants) | Rollen user/editor/admin, Knowledge und Modelle pro Gruppe freigebbar |
| Rollen aus Fremdgruppen | ✅ | `app/auth_external.py:sync_groups` | Externe Gruppen vergeben nie Rollen und legen keine Gruppen an |
| Injection-Schutz (LDAP/SQL) | ✅ | `app/auth_ldap.py` (`escape_filter_chars`), SQLAlchemy ORM; Test `tests/test_external_auth.py` | `run_pandas` mit Blockliste (`SECURITY.md`) |
| OIDC-Prüfung | ✅ | `app/auth_oidc.py` (PKCE, `state`, `nonce`, Signatur über JWKS, `iss`, `aud`, `exp`) | Konto-Verknüpfung nur über `sub`, nie über den Namen (Test `test_oidc_never_links_an_existing_account_by_name_only`) |
| CSRF | ❌ | - | Keine Token; Schutz nur durch Session-Cookie (SameSite nicht explizit). Lücke |
| CORS | ✅ | kein CORS-Header gesetzt (gleiche Herkunft) | |
| Rate-Limiting | ⚠️ | `app/users.py:40-48` (5 Fehlversuche je Konto, 20 je IP, 300 s) | Zähler **im Prozessspeicher**: nicht geteilt zwischen Prozessen, weg nach Neustart. Nur Login |
| MFA | ❌ | - | Nur über OIDC-Anbieter (dessen MFA) möglich |
| Security-Header | ❌ | kein `after_request` | CSP, HSTS, X-Frame-Options, X-Content-Type-Options fehlen; beim Reverse Proxy setzen |
| Sicherheitsrelevante Tests | ✅ | `tests/test_users.py`, `tests/test_access.py`, `tests/test_external_auth.py`, `tests/test_external_sources.py` | SSRF-/Link-Local-Sperre in `app/llm/registry.py:_reject_link_local` |
| Disclosure-Prozess | ✅ | `SECURITY.md` | Antwort innerhalb 72 h zugesagt |
| Container nicht als root | ❌ | `Dockerfile` (kein `USER`) | Lücke |
| DB/Qdrant nicht öffentlich | ⚠️ | `docker-compose.yml:112` (Postgres-Port auskommentiert) | Qdrant-Port und App-Port siehe Compose; `QDRANT_API_KEY` optional (`docker-compose.yml:17`) |
| Endpunkte mit Geheimnissen nur für Admins | ✅ | `/api/admin/*` mit `@require_role("admin")`; Geheimnisse nur als `has_*` | |
| Protokollierung sicherheitsrelevanter Ereignisse | ⚠️ | `logger.warning` bei LDAP-/Login-Fehlern (`app/users.py`) | Kein Audit-Log in der DB (wer hat wann was geändert/gelöscht) |

## Datenschutz / DSGVO

| Prüfpunkt | Status | Fundstelle/Beleg | Kommentar |
|---|---|---|---|
| Datenflussdiagramm / VVT-Start | ✅ | `docs/data-mapping.md` | |
| Art.-32-Maßnahmen | ⚠️ | `SECURITY.md`, diese Liste | Verschlüsselung at rest fehlt (App-Ebene) |
| Pseudonymisierung | ⚠️ | `app/utils/pii_filter_client.py`, `docs/sanitizer-api.md` | Herstellerneutrale Schnittstelle. Nutzereingaben werden vor dem LLM maskiert, wenn ein Filter eingerichtet ist; bei Filterfehler bricht der Chat mit Fehlermeldung ab (fail-closed), der ganze Kontext inkl. Verlauf und Compaction wird maskiert, die Antwort live zurückübersetzt (`app/pii_session.py`). Lücke: Dokument-Treffer gehen unmaskiert ans Modell. Websuche bricht bei Filterfehler ab und läuft ohne Filter nur nach ausdrücklicher Freigabe |
| Datenminimierung | ⚠️ | Chat-Anhänge werden mit dem Chat gelöscht (`app/attachments.py:cleanup_session_attachments`) | Keine automatische Aufbewahrungsfrist für Chats |
| Berichtigung | ✅ | Anzeigename/Passwort (`app/user_routes.py`, `app/user_admin.py`) | |
| Löschung | ✅ | Chat (`app/routes.py:delete_session_route`), eigene Dokumente (`delete_my_document`), Benutzer samt Chats (`app/user_admin.py:delete_user`) | Benutzer löschen entfernt Chats, Mitgliedschaften, Freigaben; Uploads/Ablagen des Benutzers nicht ausdrücklich (siehe Data Mapping, Lücke 5). Backups nicht betroffen |
| Auskunft / Übertragbarkeit | ❌ | - | Kein Export der eigenen Daten; Lücke |
| Widerspruch | ⚠️ | Betreiberprozess | |
| TLS zu externen Endpunkten | ⚠️ | LDAP prüft Zertifikate (`app/auth_ldap.py`); LLM-/Quellen-URLs vom Admin wählbar | `http://` ist erlaubt, Betreiber verantwortlich |
| Auftragsverarbeiter dokumentiert | ⚠️ | `docs/data-mapping.md` ("Externe Stellen") | Hängt von der Konfiguration ab |
| Aufbewahrungsfristen | ❌ | - | Keine automatische Löschung; Betreiber legt fest |
| Bekannte Lücken benannt | ✅ | `docs/data-mapping.md` | |

## Lizenz / Compliance

| Prüfpunkt | Status | Fundstelle/Beleg | Kommentar |
|---|---|---|---|
| `LICENSE` vollständig | ✅ | `LICENSE` (AGPL-3.0) | |
| Copyright konsistent | ✅ | Dateiköpfe "Copyright (C) 2026 Christopher Abanilla" | Ältere Dateien nicht einzeln geprüft |
| SPDX-Header | ❌ | - | Nur ausgeschriebener Lizenzkopf, kein `SPDX-License-Identifier` |
| `AUTHORS` / `THIRD_PARTY_NOTICES` | ❌ | - | |
| Lockfiles | ✅ | `uv.lock`, `frontend/package-lock.json` | CI nutzt `uv sync --frozen` |
| Automatische Lizenzprüfung / `reuse lint` | ❌ | - | |
| SBOM pro Image | ❌ | - | |

## Projekt-Health / Governance

| Prüfpunkt | Status | Fundstelle/Beleg | Kommentar |
|---|---|---|---|
| CI/CD | ✅ | `.github/workflows/ci.yml`, `release.yml` | Actions auf SHAs gepinnt |
| Dependabot | ⚠️ | `.github/dependabot.yml` | Nur GitHub-Actions; **nicht** `pip`/`npm`/`docker` |
| Lint in CI | ⚠️ | `ci.yml` | Ruff nur Information (`--exit-zero`) |
| CONTRIBUTING / CODE_OF_CONDUCT / SECURITY | ✅ | `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md` | |
| CHANGELOG | ✅ | `CHANGELOG.md` (Keep a Changelog) | |
| Issue-/PR-Vorlagen | ✅ | `.github/ISSUE_TEMPLATE/`, `.github/pull_request_template.md` | |
| Versionierung und Tags | ✅ | `scripts/release.py`, Tags v0.1.0 bis v0.1.3 | Releases ungesigniert |
| Testabdeckung | ⚠️ | Backend: 449 Tests (Lauf 2026-10-12, SQLite und Postgres) | Frontend: keine Tests, nur Typprüfung und Build |
| Bus-Faktor | ❌ | ein Maintainer | |
| Health-Endpunkt | ✅ | `app/routes.py:217` (`/health`) | |
| Reproduzierbare Builds | ⚠️ | Lockfiles; Basis-Images nicht auf Digest gepinnt | |

## Zusammenfassung

**Stärken:** saubere Rollen- und Gruppenprüfung, Geheimnisse werden nie ausgeliefert, Login-Härtung inkl. OIDC/LDAP mit Tests, SSRF-Sperre, Disclosure-Prozess, CI mit gepinnten Actions, Löschwege für Chats, Dokumente und Benutzer.

**Lücken (Reihenfolge nach Wirkung):**
1. Kein **Audit-Log** und keine Aufbewahrungsregeln.
2. Zugangsdaten **unverschlüsselt in der DB**, keine Schlüsselrotation.
3. Keine **CSRF-Token**, keine **Security-Header**, Cookie-Flags nicht gesetzt.
4. Login-Sperre nur **im Prozessspeicher**; keine MFA lokal.
5. Container läuft als **root**; Abhängigkeiten (pip/npm/docker) ohne Dependabot; keine SBOM, keine signierten Releases.
6. Kein **Datenexport** für Auskunft/Übertragbarkeit.
