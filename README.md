# SpielerPlusPlus 📅

Automatischer Synchronisations-Dienst für **SpielerPlus** direkt in deinen **ownCloud / Nextcloud / CalDAV**-Kalender.

- ☁️ **Direkter CalDAV-Sync:** Synchronisiert Termine direkt in deinen privaten ownCloud/Nextcloud-Kalender – kein statisches Datei-Hosting, keine öffentlichen Feeds, kein Webserver nötig.
- 🔀 **Multi-Team Support:** Führt beliebig viele Teams in einem einzigen Kalender zusammen.
- 🏷️ **Team-Kürzel:** Kennzeichnet Einträge übersichtlich mit konfigurierbaren Präfixen (z. B. `[U15]`, `[U17]`).
- 👍 **Persönlicher Teilnahmestatus als Emoji:** Zeigt direkt im Kalendertitel, ob du zugesagt (`👍`), abgesagt (`👎`), unsicher (`❓`) bist oder noch nicht geantwortet hast (`⏳`).
- ⚡ **Blitzschnell (Future-Events only):** Fragt nur bevorstehende Termine ab (`today - 1` bis `today + 90 Tage`). Vergangene Termine bleiben im ownCloud-Kalender dauerhaft erhalten.
- ⏱️ **Schonendes Rate-Limiting:** Höfliche Abfrageabstände und automatische Wiederholungen bei HTTP 429 / 5xx.
- 🧪 **100% Testabdeckung:** Vollständig offline testbar dank integriertem Mock-Server.
- 📸 **Live-Fixture Recorder:** Werkzeug zum Aktualisieren von Testdaten bei Änderungen der SpielerPlus-Seiten.

---

## ⚠️ Wichtiger Hinweis zu SpielerPlus Premium / Pro

Die offizielle `.ics`-Kalenderfunktion (`Kalender abonnieren` unter `/events/calendar`) wird von SpielerPlus **nicht in allen Accounts angezeigt**. 

Damit der `.ics`-Feedlink (`webcal://.../events/ics?t=...&u=...`) auf der Kalenderseite verfügbar ist, muss entweder:
- das jeweilige Team über **Trainer/Team-Premium** verfügen, oder
- dein eigener SpielerPlus-Account ein **Premium/Pro-Abonnement** besitzen.

Bei reinen Free-Teams ohne Account-Premium blendet SpielerPlus anstelle des Links ein Upgrade-Modal ein.

---

## Funktionsweise

```
+--------------------------------------------------------------+
| 1. SpielerPlus Web-Login & Team-Erkennung                    |
|    - CSRF-Token-Auslesung & Session-Verwaltung               |
+------------------------------+-------------------------------+
                               |
                               v
+--------------------------------------------------------------+
| 2. Offizielle .ics Feeds je Team abrufen                     |
|    - Exakte Start-/Endzeiten mit Zeitzone Europe/Berlin      |
|    - Exakte Hallenadressen & GEO-Koordinaten                 |
+------------------------------+-------------------------------+
                               |
                               v
+--------------------------------------------------------------+
| 3. Statusabgleich für anstehende Termine (nächste 90 Tage)   |
|    - Filtert auf zukünftige Events                           |
|    - Ermittelt persönlichen Status (Zugesagt / Abgesagt)     |
|    - Setzt Präfix: [U15, 👍] Training                        |
+------------------------------+-------------------------------+
                               |
                               v
+--------------------------------------------------------------+
| 4. Direkter ownCloud / CalDAV Sync                           |
|    - Findet oder erstellt Ziel-Kalender                      |
|    - Upsert per UID (erstellen oder aktualisieren)           |
|    - Historische Termine bleiben dauerhaft in ownCloud       |
+--------------------------------------------------------------+
```


---

## Schnellstart (Lokal)

### 1. Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

Für Entwickler / Tests:
```bash
pip install -r requirements-dev.txt
```

### 2. Konfiguration (`.env`)

Kopiere `.env.example` nach `.env`:

```bash
cp .env.example .env
```

Trage deine Zugangsdaten ein:

```env
# SpielerPlus Zugangsdaten
SPIELERPLUS_EMAIL="deine-email@beispiel.de"
SPIELERPLUS_PASSWORD="dein-passwort"

# Format: "TeamID:Kürzel, TeamID:Kürzel"
# Lässt du dies leer, werden automatisch alle Teams deines Accounts synchronisiert.
SPIELERPLUS_TEAMS="12345:U15, 67890:U17"

# Emojis im Titel aktivieren (Standard: true)
SPIELERPLUS_ATTENDANCE_EMOJI=true

# Für wie viele Tage in die Zukunft soll der Status ermittelt werden (Standard: 90)
SPIELERPLUS_ATTENDANCE_DAYS=90

# Zeitzone (Standard: Europe/Berlin)
SPIELERPLUS_TIMEZONE="Europe/Berlin"

# CalDAV Ziel (ownCloud / Nextcloud)
CALDAV_URL="https://cloud.beispiel.de/remote.php/dav"
CALDAV_USERNAME="dein-cloud-benutzername"
CALDAV_PASSWORD="dein-cloud-app-passwort"
CALDAV_CALENDAR="SpielerPlus"
```

### 3. Kalender synchronisieren

Zugangsdaten & Verbindung testen (prüft Login bei SpielerPlus und CalDAV, ohne Daten zu verändern):
```bash
python3 main.py --test-auth
```

Probelauf (Simulation & Statusabfrage ohne CalDAV-Schreibzugriff):
```bash
python3 main.py --dry-run
```

Echte Synchronisation nach ownCloud:
```bash
python3 main.py
```

Einzelnes Team synchronisieren:
```bash
python3 main.py --team 12345
```


---

## Status-Emojis

| Status | Emoji | Beispiel |
| :--- | :---: | :--- |
| Zugesagt | 👍 | `[U15, 👍] Training` |
| Abgesagt | 👎 | `[U15, 👎] Auswärtsspiel` |
| Unsicher | ❓ | `[U15, ❓] Sommerfest` |
| Noch offen | ⏳ | `[U15, ⏳] Training` |
| Nicht nominiert | 🚫 | `[U15, 🚫] Meisterschaftsspiel` |
| Vergangene Termine | - | `[U15] Training` |

---

## Automatisierung mit GitHub Actions (Private Runner)

Um deine persönlichen Daten (Namen, Vereinsnamen, Spielpläne, CalDAV-Serveradresse) privat zu halten, wird die Synchronisation über ein separates, **privates Runner-Repository** (`SpielerPlusPlusRunner`) ausgeführt:

1. **Öffentliches Repo (`SpielerPlusPlus`):** Enthält den Quellcode und die automatisierten Tests (`tests.yml`).
2. **Privates Runner-Repo (`SpielerPlusPlusRunner`):** Enthält ausschließlich den Workflow `.github/workflows/sync.yml` und deine GitHub Secrets. Beim Ausführen lädt der Runner automatisch den aktuellen Code aus diesem Repository herunter.

### Secrets im privaten Runner-Repository konfigurieren:
Unter `Settings > Secrets and variables > Actions > New repository secret`:
- `SPIELERPLUS_EMAIL`: Deine SpielerPlus E-Mail-Adresse
- `SPIELERPLUS_PASSWORD`: Dein SpielerPlus Passwort
- `CALDAV_URL`: URL deines CalDAV-Servers (z. B. `https://cloud.beispiel.de/remote.php/dav`)
- `CALDAV_USERNAME`: Dein Nextcloud/ownCloud Benutzername
- `CALDAV_PASSWORD`: Dein Nextcloud/ownCloud App-Token / Passwort
- `CALDAV_CALENDAR`: Name des Zielkalenders (z. B. `SpielerPlus`)
- `SPIELERPLUS_TEAMS`: (optional) z. B. `12345:U15, 67890:U17`
- `SPIELERPLUS_TIMEZONE`: (optional) Standard: `Europe/Berlin`

---

## Tests & 100% Testabdeckung

Die Testsuite läuft komplett offline gegen einen internen Mock-Server:

```bash
# Alle Tests ausführen
python3 -m unittest discover -s tests

# Testabdeckung prüfen (100% gefordert)
python3 -m coverage run --rcfile=.coveragerc -m unittest discover -s tests
python3 -m coverage report -m --rcfile=.coveragerc --fail-under=100
```

---

## Live-Fixtures aktualisieren (`record_fixtures.py`)

Sollte SpielerPlus in Zukunft Seitenstrukturen verändern, kannst du die echten Server-Antworten mit deinen Zugangsdaten neu aufnehmen:

```bash
python3 record_fixtures.py
```

Dieses Tool lädt die aktuellen Seiten und den `.ics`-Feed herunter, anonymisiert persönliche Daten und speichert sie unter `tests/fixtures/`.

---

## Lizenz

Dieses Projekt ist unter der **Apache License 2.0** lizenziert – siehe die [LICENSE](LICENSE)-Datei für Details.

