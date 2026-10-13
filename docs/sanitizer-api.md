# Sanitizer-API (PII-Filter) v1

Der PII-Filter der App ist ein beliebiger HTTP-Dienst, der Text maskiert. Die App benutzt ihn an zwei Stellen:

1. **Chat:** Der **ganze Kontext** (Zusammenfassung, bisheriger Verlauf, neue Frage) wird maskiert, bevor er an das Sprachmodell geht, in **einem Aufruf** (siehe unten). Die Antwort des Modells wird mit dem **Mapping** schon beim Streamen zurückübersetzt (Demaskierung), der Nutzer sieht die echten Namen.
2. **Websuche:** Die Suchanfrage wird maskiert, bevor sie an SearXNG geht. Dort werden die erkannten Werte aus der Anfrage entfernt.

[EntityGuard](https://github.com/S2A-Open-Technologies/entityguard) ist die Referenzimplementierung, die im `docker-compose.yml` mitläuft. Er antwortet mit `sanitized_text` statt `filtered` (beides wird gelesen, siehe Kompatibilität) und verlangt einen API-Key (ohne Key HTTP 401). Jeder andere Dienst funktioniert, wenn er diese Schnittstelle erfüllt, oder über einen kleinen Adapter (Beispiel unten).

## Anfrage

```
POST <Adresse>
Content-Type: application/json
Authorization: Bearer <Key>        # nur, wenn in der App ein Key eingetragen ist

{"text": "Schreibe Max Mustermann (max@example.com) eine Antwort."}
```

| Feld | Pflicht | Bedeutung |
|---|---|---|
| `text` | ja | Der zu maskierende Text (UTF-8). |
| `language` | nein | Sprachhinweis (z. B. `de`); die App sendet ihn derzeit nicht, ein Dienst darf ihn erwarten oder ignorieren. |
| `reuse_placeholders` | nein | `true`: derselbe Wert bekommt im ganzen Text denselben Platzhalter (ein Eintrag je Wert im Mapping). Der Chat sendet das mit, damit das Modell erkennt, dass `[NAME_1]` immer dieselbe Person ist. Dienste, die das Feld nicht kennen, **müssen unbekannte Felder ignorieren** und dürfen weiter pro Vorkommen nummerieren. |

`<Adresse>` ist der vollständige Endpunkt (z. B. `http://entityguard:9500/api/v1/sanitize`). Er wird in *Administration › Tools › PII-Filter* eingetragen.

## Antwort

```
200 OK
Content-Type: application/json

{
  "filtered": "Schreibe [NAME_1] ([EMAIL_1]) eine Antwort.",
  "mapping": {
    "[NAME_1]": "Max Mustermann",
    "[EMAIL_1]": "max@example.com"
  }
}
```

| Feld | Pflicht | Bedeutung |
|---|---|---|
| `filtered` | ja | Der Text mit Platzhaltern statt der erkannten Werte. Ein leerer String ist erlaubt (der Text bestand nur aus personenbezogenen Daten). |
| `mapping` | empfohlen | Platzhalter → Originalwert. Ohne `mapping` kann die Antwort des Modells **nicht** zurückübersetzt werden. |

### Kompatibilität

Aus Rücksicht auf bestehende Dienste liest die App zusätzlich, in dieser Reihenfolge:

- für den Text: `filtered`, `sanitized_text`, `result`, `text`
- für das Mapping: `mapping`, `entities`, `detected`, `pii_detected`
- das Mapping darf auch eine **Liste** sein: `[{"placeholder": "[NAME_1]", "original": "Max Mustermann"}]`

Neue Dienste sollten `filtered` und ein Objekt `mapping` liefern.

## Regeln

1. **Platzhalter sind eindeutig.** Innerhalb **eines Aufrufs** bekommen verschiedene Werte nie denselben Platzhalter (EntityGuard nummeriert durch: `[NAME_1]`, `[NAME_2]` …; derselbe Wert darf dabei mehrere Platzhalter haben, solange das Mapping stimmt). Ein Platzhalter darf nicht Teil eines anderen sein (`[NAME_1]` und `[NAME_10]` sind problematisch; eckige Klammern mit Zähler sind üblich und sicher).
2. **Reiner Ersatz.** `filtered` entsteht nur durch Ersetzen der erkannten Werte, sonst bleibt der Text unverändert. Das gilt auch für die **Trennmarken** (nächster Abschnitt).
3. **Fehler sind Statuscodes.** Alles außer `200` gilt als Fehler (`401`/`403` = Key falsch). Bei einem Fehler (auch Timeout, nicht erreichbar) **bricht die App ab**: die Websuche wird nicht ausgeführt, und der Chat zeigt eine Fehlermeldung, statt die Nachricht unmaskiert an das Modell zu senden (fail-closed).
4. **Schnell genug.** Die App wartet 5 Sekunden plus 1 Sekunde je 2000 Zeichen, höchstens 60 Sekunden (der Chat schickt den ganzen Kontext).
5. **Nichts speichern.** Der Dienst darf Texte und Mapping nicht dauerhaft ablegen oder protokollieren; das Mapping enthält die Klartextwerte.
6. **Einseitige Dienste** (nur Schwärzen, kein `mapping`) sind erlaubt. Dann arbeitet die Websuche mit dem gefilterten Text, die Antworten des Modells bleiben aber maskiert.

## Ganzer Kontext in einem Aufruf

Damit das Modell auch frühere Nachrichten nie im Klartext sieht (die App speichert sie im Klartext und schickt den Verlauf bei jeder Frage erneut), maskiert der Chat **alle Texte in einem Aufruf**. Die Texte werden mit Trennmarken zu einem Text verbunden:

```
=====#0=====

Zusammenfassung oder erste Nachricht …

=====#1=====

Nächste Nachricht …
```

Der Dienst maskiert den ganzen Text und liefert die Marken **unverändert, genau einmal und in Reihenfolge** zurück; sonst bricht die App ab (fail-closed). Die Marken enthalten bewusst **keine Buchstaben**: Mit einer Buchstabenmarke wie `=====MSG-1=====` hat die deutsche spaCy-NER (EntityGuard) den Teil `MSG-1=====` als Entität erkannt und die Marke zerstört (gemessen mit `de_core_news_lg`); `=====#1=====` übersteht die Erkennung. Dadurch vergibt der Dienst im ganzen Gespräch eindeutige Platzhalter und liefert ein gemeinsames Mapping.

## Prüfen

In der App: *Administration › Tools › PII-Filter › Testen*. Die App schickt einen Beispieltext mit erfundenen Daten (Max Mustermann, max.mustermann@example.com) und meldet, ob der Text maskiert wird, ob ein Mapping erkannt wird und ob die Demaskierung den Originaltext ergibt.

Von Hand:

```bash
curl -s -X POST http://localhost:9500/sanitize \
  -H 'Content-Type: application/json' -H 'Authorization: Bearer geheim' \
  -d '{"text": "Schreibe Max Mustermann (max@example.com) eine Antwort."}'
```

## Eigenen Dienst anbinden (Adapter)

Hast du schon einen Erkenner (Presidio, spaCy, ein internes Gateway), schreibst du einen dünnen Adapter, der diese Schnittstelle spricht. Eine lauffähige Vorlage steht in [`examples/sanitizer_adapter.py`](./examples/sanitizer_adapter.py) (FastAPI, ca. 60 Zeilen, Erkennung per Regeln; im Kopf steht, wie du Presidio einsetzt):

```bash
cd docs/examples
uv run --with fastapi --with uvicorn uvicorn sanitizer_adapter:app --port 9500
# Adresse in der App: http://localhost:9500/sanitize
```

## Hinweise zum Betrieb

- Der Dienst sieht Klartext. Betreibe ihn im eigenen Netz und nutze HTTPS, wenn er nicht auf demselben Host läuft.
- Ohne PII-Filter ist die Websuche nur nach ausdrücklicher Freigabe ("Auch ohne PII-Filter erlauben") möglich; Suchanfragen gehen dann unmaskiert hinaus.
- Die maschinenlesbare Beschreibung steht in [`sanitizer-openapi.yaml`](./sanitizer-openapi.yaml).
