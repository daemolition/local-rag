# SQL-Datenbanken als Knowledge

Ein Admin bindet eine Datenbank an (*Knowledge › SQL-Datenbank*). Im Chat fragt das Modell Schema und Daten **live und nur lesend** ab. Die Daten werden nicht kopiert und nicht indexiert.

Unterstützt: PostgreSQL, MySQL/MariaDB, Microsoft SQL Server (auch benannte Instanz) und SQLite-Dateien.

## Einrichten

1. Lege in der Datenbank einen Benutzer an, der **nur SELECT** darf (Least Privilege). Beispiele:
   - PostgreSQL: `CREATE ROLE ouk_ro LOGIN PASSWORD '…'; GRANT CONNECT ON DATABASE shop TO ouk_ro; GRANT USAGE ON SCHEMA public TO ouk_ro; GRANT SELECT ON ALL TABLES IN SCHEMA public TO ouk_ro;`
   - MySQL/MariaDB: `CREATE USER 'ouk_ro'@'%' IDENTIFIED BY '…'; GRANT SELECT ON shop.* TO 'ouk_ro'@'%';`
   - SQL Server: `CREATE LOGIN ouk_ro WITH PASSWORD='…'; USE shop; CREATE USER ouk_ro FOR LOGIN ouk_ro; ALTER ROLE db_datareader ADD MEMBER ouk_ro;`
2. Erreichbarkeit: Der Dienst `tool-worker-sql` muss die Datenbank erreichen. Läuft sie auf dem Docker-Host, nimm `host.docker.internal` als Host.
3. SQLite: lege die Datei in den Ordner `SQL_SQLITE_DIR` (Standard `./sql-data`, wird nur lesend gemountet) und gib im Dialog den Dateinamen an.
4. Im Dialog **Verbindung testen**: Version, Tabellen, Warnung bei Schreibrechten. Danach Tabellen freigeben und Spalten sperren (Standard: alle Tabellen, keine gesperrten Spalten). **Speichern**.
5. Freigabe an Nutzer/Gruppen wie bei jedem Knowledge (Privat/Öffentlich/Freigaben). Im Chat wählst du die Datenbank als Wissen aus oder hängst sie an ein Modell.

**MSSQL mit benannter Instanz:** trage Host und Instanz getrennt ein (`server` und `SQLEXPRESS`); der Port wird über den SQL Browser (UDP 1434) ermittelt. Ein ausdrücklich abweichender Port wird verwendet.

## Sicherheit

Drei Schichten im Worker (`tool_worker/`), keine davon verlässt sich auf die andere:

1. **Read-only-Sitzung** (PostgreSQL, MySQL/MariaDB, SQLite). **SQL Server hat keine Sitzungsoption dafür**: dort schützen die SQL-Prüfung und der SELECT-only-Benutzer.
2. **SQL-Prüfung** (`sqlglot`): genau ein SELECT, kein `INTO`, kein `FOR UPDATE`, keine Sperrfunktionen (`pg_read_file`, `load_file`, `xp_cmdshell`, `load_extension` …), keine Tabellenfunktionen, nur freigegebene Tabellen, gesperrte Spalten auch über `SELECT *`, Alias und Unterabfragen nicht lesbar.
3. **Grenzen**: Zeilenlimit (Standard 50), Zeitlimit (15 s, serverseitig bei PostgreSQL, MariaDB; SQL Server und SQLite über Treiber), Zellenkürzung.

Der Worker läuft nicht als root, mit schreibgeschütztem Dateisystem und ohne Zugriff auf Postgres, Qdrant oder Daten der App. Er ist der einzige Dienst mit Ausgang zu den Datenbankzielen.

## PII-Filter

- **Mit eingerichtetem Filter**: Ergebnisse werden vor dem Modell maskiert (fail-closed: fällt der Filter aus, bekommt das Modell keine Zeilen). Schreibt das Modell einen Platzhalter in die Bedingung (`WHERE name = '[NAME_1]'`), wird er vor der Ausführung zurückübersetzt. Platzhalter über mehrere Aufrufe bleiben eindeutig. Das **Schema** (Tabellen- und Spaltennamen, Kommentare) wird nicht maskiert.
- **Ohne Filter** bleibt alles unverändert: Ergebnisse gehen im Klartext an das Modell (bewusste Entscheidung des Betreibers, wie bei Dokumenten).

## Grenzen

- Kein Zeilenfilter pro Nutzer: wer die Datenbank nutzen darf, sieht alle freigegebenen Tabellen und Spalten. Trenne bei Bedarf über Datenbank-Benutzer oder Tabellenfreigabe.
- Die Tabellenprüfung vergleicht Namen ohne Schema; gleichnamige Tabellen in mehreren Schemas lassen sich so nicht unterscheiden.
- Das Passwort liegt wie andere Schlüssel unverschlüsselt in der App-Datenbank und geht per internem HTTP an den Worker. Die API gibt es nie zurück.
- Getestet gegen echte Server: PostgreSQL 17, MariaDB 11, SQL Server 2022 (Standardinstanz), SQLite. Eine **benannte** SQL-Server-Instanz wurde nicht gegen einen echten Server geprüft.
