# Changelog

## [0.28.1] - 2026-03-28
### Neu
- **Dashboard: Request-Inhalt aufklappbar** 📋
  - Jeder Request-Log-Eintrag hat einen ▶ Button zum Aufklappen
  - Zeigt den vollen Request-Text (📨) und die Antwort (📤)
  - Gilt fuer User-Requests und Scheduler-Tasks
  - Prompt (max 500 Zeichen) und Output (max 2000 Zeichen) werden gespeichert

## [0.28.0] - 2026-03-28
### Neu
- **Aktien-Crash-Monitor: Multi-Source mit 4 Datenquellen** 🔍
  - yfinance (unbegrenzt) als Hauptquelle fuer Screening aller ~2.500 Ticker
  - Finnhub (Echtzeit, 60/Min) zur Crash-Verifikation
  - Twelve Data (800/Tag) zur zweiten Verifikation
  - Alpha Vantage (25/Tag) nur bei schweren Crashes >30%
  - Jeder Crash wird cross-verifiziert – weniger Fehlalarme
  - Alerts zeigen Anzahl bestaetigender Quellen an
  - API Keys in .env gespeichert (Finnhub, TwelveData, AlphaVantage)
  - Monitor wieder aktiviert

## [0.27.4] - 2026-03-28
### Geändert
- **Aktien-Crash-Monitor deaktiviert** 📉
  - Task `stock_crash_check` auf `enabled: false` gesetzt
  - Code bleibt erhalten, kann jederzeit wieder aktiviert werden

## [0.27.3] - 2026-03-28
### Verbessert
- **Aktien-Crash-Monitor: Separater Ticker-Update Task entfernt** 🧹
  - Ticker-Liste aktualisiert sich jetzt automatisch wenn >7 Tage alt
  - Kein extra Cron-Task mehr noetig – passiert beim normalen Crash-Check
  - Fallback: Wenn Update fehlschlaegt, wird alte Liste weiterverwendet

## [0.27.2] - 2026-03-28
### Neu
- **Watchdog: Automatische Problemerkennung alle 60 Sekunden** 🐕
  - Erkennt haengende Tasks (>2x Timeout) und raeumt sie auf
  - Chrome/CDP Health-Check bei jedem Zyklus – Auto-Restart bei Ausfall
  - Playwright MCP Server Check – Auto-Restart wenn Prozess tot
  - Sofortige Telegram-Benachrichtigung bei Problemen und Fixes
  - Laueft im Scheduler-Zyklus (alle 60s), kein separater Prozess noetig

## [0.27.1] - 2026-03-28
### Verbessert
- **Timeout-Handling: Zwischenstand statt Totalverlust** ⏱️
  - Timeout von 15 Min auf 60 Min erhoeht (praktisch kein Limit mehr)
  - Streaming-Output: stdout wird zeilenweise gelesen statt am Ende komplett
  - Bei Timeout wird der bisherige Zwischenstand an den User gesendet
  - Kein verlorener Output mehr wenn Claude lange arbeitet

## [0.27.0] - 2026-03-28
### Erweitert
- **Aktien-Crash-Monitor: 20 Indizes weltweit – ~2.546 Aktien** 🌍
  - Von 8 auf 20 Indizes erweitert (alle grossen Boersen abgedeckt)
  - Neue Indizes: CAC 40, IBEX 35, SMI, AEX, OMX Stockholm 30 (Europa)
  - Neue Indizes: KOSPI 200, ASX 200, BSE Sensex, Nifty 50 (Asien-Pazifik)
  - Neue Indizes: S&P 400 MidCap, S&P/TSX Composite (Nordamerika)
  - Neue Indizes: FTSE 250 (UK Mid Caps)
  - 24 Index-Ticker (vorher 8) werden zusaetzlich ueberwacht
  - Generischer Wikipedia-Scraper fuer einfache Erweiterung
  - Agent-Beschreibung im Dashboard aktualisiert

## [0.26.3] - 2026-03-28
### Verbessert
- **Aktien-Crash-Monitor: Echte Firmennamen** 🏷️
  - Fehlende Ticker-Namen (v.a. MDAX) werden via yfinance nachgeschlagen
  - EVD.DE zeigt jetzt "CTS Eventim AG & Co. KGaA" statt nur "EVD"
  - 50 Namen aufgeloest (Delivery Hero, Lufthansa, Carl Zeiss Meditec, etc.)

## [0.26.2] - 2026-03-28
### Verbessert
- **Aktien-Crash-Monitor: Dividenden-Filter** 🛡️
  - Bei erkanntem Crash wird einzeln die Dividenden-Historie geprueft
  - Wenn eine Dividende in den letzten 7 Tagen >= 50% des Kursabfalls erklaert → kein Alert
  - Verhindert Fehlalarme durch Ex-Dividende-Abschlaege
  - Echte Crashes (wie EVD.DE -23% am 27.03.) werden weiterhin korrekt gemeldet

## [0.26.1] - 2026-03-28
### Verbessert
- **Aktien-Crash-Monitor: Quell-Links in Alerts** 📎
  - Jeder Alert enthaelt jetzt klickbare Links zu:
    - Yahoo Finance (Kurs-Chart, Details)
    - Google Finance (alternative Ansicht)
    - Google News (aktuelle Nachrichten zur Aktie, deutsch)
  - Links sind boersenspezifisch: .DE→FRA:, .L→LON:, .T→TYO:, .HK→HKG:

## [0.26.0] - 2026-03-28
### Geändert
- **Aktien-Crash-Monitor: Komplettes Rewrite – ueberwacht jetzt ALLE Aktien** 📉
  - Von 28 handverlesenen Tickern auf **~1.056 Aktien** aus 8 grossen Indizes erweitert
  - Ticker-Listen werden automatisch von Wikipedia gescrapt:
    - S&P 500 (503), NASDAQ-100 (101), DAX 40 (40), MDAX (50)
    - FTSE 100 (100), Euro Stoxx 50 (50), Hang Seng (85), Nikkei 225 (225)
    - Plus 8 Index-Ticker selbst
  - Batch-Verarbeitung: 50 Ticker pro yfinance-Download, ~22 Batches
  - Monatlicher Ticker-Update-Task (1. des Monats, 3 Uhr): `--update`
  - Ticker-Liste in `data/stock_tickers.json` (wird bei fehlen automatisch erstellt)
  - Timeout auf 300s erhoeht (fuer ~1.000 Ticker)
  - Alerts nach Staerke sortiert (groesster Einbruch zuerst)
  - Neue CLI-Optionen: `--update`, `--stats`, `--test`
  - Eigenstaendiger Agent `stock_monitor` mit eigener Dashboard-Karte

## [0.25.5] - 2026-03-28
### Hinzugefügt
- **Automatischer Retouren-Abgleich im Mailcheck** 💰
  - E-Mail-Wächter prüft jetzt nach jedem Check auf Rückerstattungs-E-Mails
  - Erkennt: Rückerstattung, Gutschrift, Erstattung, refund
  - Aktualisiert automatisch ~/gdrive/5_Privat/retouren_tracking.json
  - Setzt status auf "received", refund_date, refund_amount
  - Meldet Rückerstattungen als WICHTIG an André per Telegram

## [0.25.4] - 2026-03-28
### Hinzugefügt
- **Info-Buttons fuer einzelne Tasks im Dashboard** ℹ️
  - Jeder Task hat jetzt einen orangenen "i"-Button neben der Beschreibung
  - Klick zeigt den vollstaendigen Prompt/Befehl des Tasks (monospace, max 500 Zeichen)
  - Tags zeigen Task-Typ (claude/bash), Silent-Modus und Timeout
  - Funktioniert fuer alle Tasks inkl. Aktien-Crash-Monitor, Chrome Health etc.
  - Dashboard-Publisher liefert jetzt task_type, silent, timeout und detail pro Task

## [0.25.3] - 2026-03-28
### Hinzugefügt
- **Warteschlange im Dashboard** ⏳
  - Neuer Bereich "Warteschlange" direkt unter "Aktuell in Arbeit"
  - Zeigt wartende Jobs mit Position (#1, #2, ...), Agent, Titel, Typ und Wartezeit
  - Queue-Zaehler in der Stats-Bar (blau wenn Jobs aktiv, gruen wenn leer)
  - Bot schreibt jetzt auch wartende Jobs in `data/current_jobs.json` (neues Format: running + queued)
  - Scheduler und PipeQueue nutzen dasselbe File mit Source-Trennung

## [0.25.2] - 2026-03-28
### Hinzugefügt
- **Info-Button pro Agent im Dashboard** ℹ️
  - Jeder Agent hat jetzt einen kleinen "i"-Button neben dem Namen
  - Klick oeffnet/schliesst ein Beschreibungs-Panel mit:
    - System-Prompt (Rollenbeschreibung des Agenten)
    - Modell-Badge (z.B. opus) in Lila
    - Tool-Badges (claude, bash, playwright) in Gruen
  - Animiertes Ein-/Ausklappen mit fadeIn-Effekt
  - Button wechselt Farbe bei aktivem Panel

## [0.25.1] - 2026-03-28
### Hinzugefügt
- **"Aktuell in Arbeit" Live-Anzeige im Dashboard** 🔄
  - Neuer prominenter Bereich oben im Dashboard zeigt laufende Jobs in Echtzeit
  - Animierter Scan-Balken und Puls-Badge fuer aktive Jobs
  - Zeigt Agent, Aufgabentitel, Laufzeit, Job-Typ und Quelle (User/Scheduler)
  - Persistente Datei `data/current_jobs.json` wird bei Job-Start/-Ende aktualisiert
  - Sowohl PipeQueue (User-Requests) als auch Scheduler-Tasks werden getrackt
  - Bei Leerlauf: "Alle Agenten im Leerlauf" mit gruenem Idle-Dot
- **Request-Log im Dashboard** 📋
  - Neuer Bereich "Request-Log" ganz unten auf dem Dashboard
  - Zeigt alle Anfragen an Agenten: User-Requests (💬) und Scheduler-Tasks (⏰)
  - Persistentes Log in `data/request_log.json` (letzte 200 Eintraege)
  - Bot-Requests (PipeQueue) werden nach Job-Abschluss geloggt
  - Scheduler-Tasks werden nach Ausfuehrung geloggt
  - Anzeige: Zeitstempel, Agent-Emoji, Job-Typ (text/bash/photo), Titel, Dauer, Status
  - Farbcodierung nach Job-Typ: text (blau), photo (lila), bash (orange)

## [0.25.0] - 2026-03-28
### Behoben
- **Cross-Session-Abgleich fuer Erinnerungen** 🔄
  - Taskprep-Agent prueft jetzt VOR jedem Briefing Andrés Telegram-Nachrichten auf Status-Updates
  - Doctolib-Termine werden live geprueft (nicht aus dem Gedaechtnis)
  - Stornierte/erledigte/gescheiterte Termine werden NICHT mehr erinnert
  - Gilt fuer: Morgen-Briefing, Precheck (alle 3h) und Abend-Review
  - System-Prompt um Cross-Session-Regeln erweitert
  - Verhaltensregeln in MEMORY.md aktualisiert

## [0.24.9] - 2026-03-27
### Hinzugefügt
- **Aktien-Crash-Monitor** 📉
  - Neuer Agent `stock_crash_monitor` prueft alle 30 Min (Mo-Fr 6-22 Uhr) auf Kurseinbrueche
  - Ueberwacht 28 Ticker: 8 Indizes (S&P 500, DAX, NASDAQ, etc.) + 10 Top US-Aktien + 10 Top EU-Aktien
  - Telegram-Alert bei >= 20% Kursverlust gegenueber Vortagesschluss
  - State-Datei `data/stock_state.json` speichert letzte Kurse und Meta-Info
  - Basiert auf `yfinance` fuer Echtzeit-Kursdaten
  - Laeuft als stiller Bash-Task (kein Claude-Aufruf noetig)

## [0.24.8] - 2026-03-27
### Hinzugefügt
- **Sessions-Anzeige im Dashboard** 🧠
  - Neue Sektion "Sessions" auf dem Assistina Dashboard
  - Zeigt alle 8 persistenten Claude-Sessions mit Agent-Name, Emoji und Session-ID
  - Transcript-Groesse in MB mit Farbcodierung (grün < 20MB, blau < 50MB, orange > 50MB)
  - Fortschrittsbalken zeigt relative Groesse der Transcripts
  - Letzte Aktivitaet als relative Zeitangabe
  - Sessions-Zähler in der Stats-Bar
  - Dashboard-Publisher (`lib/dashboard_publisher.py`) um `_build_sessions()` erweitert

## [0.24.7] - 2026-03-26
### Behoben
- **Timeout-Probleme komplett überarbeitet** 🔌
  - **Progress-Ticker**: Alle 60s kommt jetzt eine Chat-Nachricht "⏳ Arbeite noch..." bei langen Aufgaben – kein stilles Warten mehr
  - **Worker-Idle-Timeout**: Von 5 Min auf 30 Min erhöht – Bot stirbt nicht mehr bei kurzer Inaktivität
  - **Claude-Timeout**: Von 10 auf 15 Min erhöht – komplexe Aufgaben brechen nicht mehr ab
  - **TypingLoop robust**: Netzwerk-Fehler im Typing-Indikator werden abgefangen statt zum Crash zu führen
  - **HTTP-Client gestärkt**: `HTTPXRequest` mit höheren Timeouts (read=45s, connect=20s, write=30s) und Connection-Pool (8)
  - **Sauberes Logging**: `NetworkError`/`TimedOut` als WARNING statt ERROR (normal bei Long-Polling)
  - Explizite Timeout-Werte für `run_polling()`: read=30s, connect=15s, pool=10s

## [0.24.6] - 2026-03-25
### Behoben
- **Scheduler: Progress-Updates jetzt zuverlässig** ⏳
  - Bug behoben: Zwischenstand-Updates wurden nur gesendet wenn stdout-Output kam
  - Neuer unabhängiger Timer (`_progress_ticker`) sendet Updates alle `progress_interval` Sekunden, auch wenn Claude "denkt" und nichts ausgibt
  - Nutzt `asyncio.Event` + parallele Tasks statt inline-Check im Readline-Loop

## [0.24.5] - 2026-03-24
### Geändert
- **Social Media Postings: Original-Artikelbilder statt Logo** 📸
  - Google News RSS-URLs werden jetzt zur echten Artikel-URL aufgelöst (via googlenewsdecoder)
  - OG-Images werden von den Original-Artikeln heruntergeladen
  - **Kein Logo-Fallback mehr** – Posts ohne Artikelbild werden übersprungen
  - **Quellenangabe** für Bilder (📷 domain.de) in jedem Post
  - Jeder Post hat immer: Bild + Text + Link
  - Gilt für Twitter/X UND Instagram
  - `download_article_image()` gibt jetzt Tuple (path, source_domain) zurück
  - Neue Dependency: `googlenewsdecoder`

## [0.24.4] - 2026-03-24
### Geändert
- **Scheduler: Streaming-Fortschritt** – Claude-Tasks senden jetzt alle 2 Min einen Zwischenstand in den Chat (letzte 5 Output-Zeilen)
- **Scheduler: Timeout-Meldungen entfernt** – Timeouts werden nur noch geloggt, nicht mehr im Chat angezeigt
- **Timeout erhöht** – daily_news und daily_videos auf 1800s (30 Min) statt 600/900s

## [0.24.3] - 2026-03-23
### Entfernt
- **Worker-Bot Metriken/Telemetrie entfernt** – Alle `log_request`-Aufrufe aus bot.py entfernt, Worker-Bot Import deaktiviert (verursachte Connection-Errors)
- **RAG-Sync-Status aus /status entfernt** – `sync_info` wird nicht mehr im Chat-Status angezeigt

## [0.24.2] - 2026-03-23
### Geaendert
- **Twitter/X Anti-Spam Optimierung** 🐦
  - Bio und Website-URL fuer @fake_defense_ai gesetzt (vorher leer)
  - Tweet-Delay von 5s auf 30s erhoeht (Anti-Spam)
  - Max 3 Tweets pro Batch (statt unbegrenzt)
  - Alle 88 alten unsichtbaren Tweets geloescht (Twitter Spam-Filter hatte sie versteckt)
  - Dashboard: Reddit-Link entfernt (Subreddit existiert nicht)

## [0.24.1] - 2026-03-23
### Hinzugefuegt
- **Dashboard: Content & Kanaele Sektion** 🔗
  - Neue Sektion mit Links zu allen Content-Plattformen der Agenten
  - WordPress Blog, Twitter/X, Instagram, Reddit, GitHub, Dashboard
  - Hover-Effekte und responsive Grid-Layout

## [0.24.0] - 2026-03-22
### Behoben
- **Scheduler Retry-Logik fuer transiente Netzwerkfehler** 🔄
  - Automatischer Retry bei DNS-Fehlern, Connection-Resets und aehnlichen transienten Fehlern
  - 30 Sekunden Wartezeit zwischen Versuchen
  - Konfigurierbar via `"retries": N` in Task-Config (Standard: 1)
  - Behebt naechtliche Ausfaelle durch WLAN-Sleep (DNS resolution failures)
- **Timeout-Erhoehungen fuer langsame Tasks**
  - sync_calendar: 300s → 600s
  - sync_drive: 120s → 300s
  - taskprep_evening: 300s → 600s
- **Retry-Config fuer fehleranfaellige Tasks hinzugefuegt**
  - sync_calendar, sync_contacts, sync_drive, taskprep_morning, taskprep_evening, daily_news, daily_videos
- **Stale Dashboard-Eintraege bereinigt**
  - claude_cpu_monitor Eintrag aus Februar entfernt

## [0.23.0] - 2026-03-22
### Hinzugefuegt
- **Instagram Poster Modul** (`lib/instagram_poster.py`) 📸
  - Caption-Format jetzt IDENTISCH zum Twitter/X-Format
  - Format: ⚠️ Titel (Quelle) + 🔗 URL + 🛡️ CTA + Hashtags
  - Batch-Caption-Generierung: `echo '[articles]' | python -m lib.instagram_poster --batch-captions`
  - Deduplizierung via `data/instagram_posted.json`
  - Bild-Handling mit OG-Image, YouTube-Thumbnails und Fallback-Logo
  - Integration mit `twitter_poster.py` fuer Bild-Download
- **Newsradar & Videoradar Instagram-Sync** 🔄
  - Instagram-Anweisungen in beiden Agenten aktualisiert
  - Captions jetzt exakt im Twitter-Format (statt eigenes Format)
  - Automatische Markierung geposteter Artikel zur Vermeidung von Duplikaten

## [0.22.0] - 2026-03-22
### Hinzugefuegt
- **eufy Security Agent** 🔐
  - Automatische Alarmsteuerung basierend auf Anwesenheit und Tageszeit
  - Anwesenheitserkennung via ARP-Tabelle / Ping / arp-scan (Smartphone MAC)
  - Tageslichterkennung via `astral` (Sonnenstand Berlin) + Open-Meteo Wetter-API
  - eufy Steuerung via `eufy-security-client` (Node.js Bridge)
  - Logik: Abwesend + Tag + hell → Modus "Zuhause", Abwesend + Tag + dunkel → Modus "Abwesend"
  - Nacht → keine Aenderung (Zeitsteuerung/Alarm bleibt aktiv)
  - Schutz vor Fehlalarmen: 2 aufeinanderfolgende Abwesenheits-Checks noetig
  - Scheduled Task alle 5 Minuten (silent, bash-Typ)
  - State-Tracking in `data/eufy_state.json`
  - Module: `lib/eufy_security/` (agent.py, presence.py, daylight.py, eufy_control.js)
  - CLI: `python -m lib.eufy_security.agent [--dry-run] [--status] [--mac MAC]`
  - **Noch nicht aktiviert** – benötigt: EUFY_EMAIL, EUFY_PASSWORD, PHONE_MAC in .env

## [0.21.0] - 2026-03-22
### Hinzugefuegt
- **Assistina Dashboard (GitHub Pages)** 📊
  - Live-Dashboard unter https://rokytnice.github.io/chat_agent/
  - Zeigt alle Agenten mit Status, Tasks, Laufzeiten, Fehler
  - Retouren-Tracking mit Fristen und Betraegen
  - Aktivitaetslog der letzten 50 Task-Ausfuehrungen
  - Auto-Refresh alle 30 Sekunden
  - Dark Theme, responsive fuer Mobile
  - Dashboard Publisher (`lib/dashboard_publisher.py`) generiert Status-JSON
  - Automatische Aktualisierung bei jedem Scheduler State-Change
  - Nur Push bei tatsaechlichen Aenderungen (Hash-Vergleich)
- **Retouren-Tracking System** 📦
  - Automatischer taeglicher Gmail-Scan nach Retoure-E-Mails (9:17 Uhr)
  - Tracking-Datei: `~/gdrive/5_Privat/retouren_tracking.json`
  - Erkennt: Amazon, Gymshark, Kaufland und andere Shops
  - Telegram-Alert bei ueberfaelligen Rueckzahlungen (>14 Tage)
  - Aktuell 3 offene Retouren getrackt

## [0.20.6] - 2026-03-21
### Hinzugefuegt
- **Fake Defense AI: Rueckgabebedingungen-Check (Phase 8)** 🛒
  - Neue Pruefphase im Fakechecker-Agent: Rueckgabebedingungen & Versand-Standort-Analyse
  - Prueft Ruecksendeadresse vs. Impressum vs. WHOIS (Dreiecks-Check)
  - Erkennt Fake-Shops anhand: Ruecksendeadresse in Asien, fehlendes EU-Widerrufsrecht, ueberhöhte Retourenkosten
  - Lieferzeit-Plausibilitaet (>14 Tage = Dropshipping-Verdacht)
  - Neue Output-Tabelle im Pruefbericht

### Entfernt
- **Reddit-Posting aus News Radar Agent entfernt** 🗑️
  - Schritt 6 (Reddit-Post) komplett entfernt
  - Alle Reddit-Referenzen aus Prompt, Copyright-Regeln, Sprach-Abschnitt und Telegram-Template entfernt
  - Workflow: WordPress → Twitter/X → Instagram → Telegram (ohne Reddit)

## [0.20.5] - 2026-03-21
### Hinzugefuegt
- **E-Scooter Versicherungs-Erinnerung (Scheduled Task)** 🛴
  - Jaehrliche Erinnerung am 10. Februar um 9 Uhr
  - Erinnert an Ablauf von Lisas E-Scooter-Versicherungskennzeichen (28.02.)
  - Prueft ob Verlaengerung erfolgt ist und meldet Status per Telegram
  - Versicherer: AdmiralDirekt (CHECK24), Police ESC-55749419
  - Cron: `0 9 10 2 *` (Task-ID: `escooter_versicherung`)

## [0.20.4] - 2026-03-20
### Hinzugefuegt
- **USt-VA Pruefagent (Scheduled Task)** 📊
  - Automatische monatliche Pruefung der Umsatzsteuer-Voranmeldung am 10. jedes Monats um 9 Uhr
  - Loggt sich in Lexware ein und prueft ob die USt-VA des Vormonats uebermittelt wurde
  - Meldet Status (gemeldet/nicht gemeldet), Zahllast und ggf. Warnung per Telegram
  - Prueft nur, uebermittelt NICHT selbst
  - Cron: `0 9 10 * *` (Task-ID: `ustva_check`)

## [0.20.3] - 2026-03-19
### Hinzugefuegt
- **Neuer Agent: Steuer & Buchhaltung 2025** 📊
  - Kummert sich um Einkommensteuererklaerung 2025 und geschaeftliche Buchhaltung
  - Datenquellen: Google Drive privat (6_Steuer/2025/, 5_Privat/2025/), Google Drive Business (rochlitz.consulting/business/2025/), Elster, Lexware Office
  - Referenz-Vorlagen aus Steuererklaerung 2024 (EUeR, ELSTER-Abgabe, Belegnachweis)
  - Aufgabenbereiche: ESt-Erklaerung, UStVA, EUeR, Belegmanagement, Lexware-Abgleich
  - Monatlicher Steuer-Status-Check (Cron: 1. des Monats um 9 Uhr)
  - Ergebnisse werden auf Google Drive abgelegt (nicht /tmp/)

## [0.20.2] - 2026-03-19
### Verbessert
- **Instagram Login-Credentials in Agent-Prompts hinterlegt** 🔑
  - News Radar + Video Radar: Instagram-Login mit andre.rochlitz@gmail.com (Standard-Passwort)
  - Automatischer Login-Flow falls nicht eingeloggt
  - Video Radar: File-Root-Workaround (tmp_upload.jpg) analog zu News Radar ergaenzt

## [0.20.1] - 2026-03-17
### Verbessert
- **TaskPrep-Agent: Automatischer Postausgang-Abgleich** 📧
  - Agent prueft bei jedem Durchlauf (Morning/Precheck/Evening) den Gmail-Postausgang
  - Erkennt automatisch erledigte Aufgaben (z.B. beantwortete Polizei-Anzeigen, Behoerden-Mails)
  - Loescht erledigte Erinnerungen selbststaendig aus `notified_tasks`
  - Erinnert bei offenen Aufgaben (>3 Tage) aktiv an ausstehende Antworten
  - Suchstrategie: Ableitung von Suchbegriffen aus Aufgaben-Kontext (Aktenzeichen, Absender, Betreff)

- **News Radar: Instagram-Posting hinzugefuegt** 📸
  - News Radar postet jetzt auch auf Instagram (analog zu Video Radar)
  - Ein Post pro Artikel mit OG-Image, zweisprachiger Caption und Hashtags
  - Maximal 5 Posts pro Durchlauf (Anti-Spam)
  - 30 Sekunden Pause zwischen Posts
  - Fix: Bilder werden vor Upload ins Projektverzeichnis kopiert (Playwright MCP File-Root-Restriction)
  - Erster Instagram-Test-Post erfolgreich veroeffentlicht (17.03.2026)

### Gefixt
- **Google Drive Mount-Skripte** (`mount_andre_rochlitz.sh`, `mount_rochlitz.sh`)
  - `--allow-other` entfernt (nicht in `/etc/fuse.conf` erlaubt)
  - `--daemon` durch `nohup &` ersetzt (Timeout-Problem behoben)
  - Stale-Mount-Erkennung und automatische Bereinigung hinzugefuegt
  - Verzeichnis-Bereinigung vor Mount (verhindert "not empty" Fehler)
  - Mount-Verifikation mit Erfolgs-/Fehler-Logging

## [0.20.0] - 2026-03-16
### Neu
- **Chrome Browser Architektur: Headed-Modus mit CDP** 🖥️
  - Chrome lauft jetzt im **headed-Modus** (nicht headless!) mit GPU/WebGL-Support
  - Neues Modul `lib/chrome_manager.py` – Chrome-Prozess-Manager:
    - Start/Stop/Restart des echten Chrome-Browsers
    - Persistentes Browser-Profil in `~/.config/chrome-bot-profile/` (ueberlebt Reboots)
    - CDP Health-Checks (Chrome DevTools Protocol auf Port 9222)
    - Auto-Recovery: Erkennt Crashes und startet Chrome automatisch neu
    - `ensure_running()` – stellt sicher, dass Chrome lauft
    - CLI: `python -m lib.chrome_manager [start|stop|restart|status|health]`
  - **MCP Playwright verbindet sich jetzt per `--cdp-endpoint`** zum laufenden Chrome
    - Kein eigener Browser-Start durch MCP mehr
    - Login-Sessions (Google, etc.) bleiben dauerhaft erhalten
    - Kein manueller Chrome-Neustart mehr noetig
  - `start.sh` komplett ueberarbeitet: 3-Schritte-Start (Chrome → MCP → Bot)
  - `lib/browser.py` aktualisiert: `--headless` entfernt, CDP-Endpoint-Anbindung
  - Neuer Scheduled Task `chrome_health` (alle 30 Min) – prueft Chrome und startet bei Bedarf neu
  - Altes Profil `/home/aroc/.cache/ms-playwright/mcp-chrome-c1ca833` wird nicht mehr verwendet

## [0.19.6] - 2026-03-15
### Hinzugefügt
- **Reddit-Posting für News Radar** 🤖
  - Neues Modul `lib/reddit_poster.py` – postet Artikel als Sammelpost auf Reddit
  - Batch-Modus: JSON-Array von Artikeln → formatierter Reddit-Post (Markdown)
  - Zweisprachiger Post (DE/EN) mit Copyright-Disclaimer (§ 51 UrhG)
  - Quellenangabe und Zitat-Formatierung für jeden Artikel
  - Unterstützung für mehrere Subreddits (Standard: r/FakeDefenseAI)
  - Rate-Limiting und Duplikat-Erkennung integriert
  - Newsradar Agent-Prompt um Reddit-Schritt erweitert (Schritt 6)
  - PRAW (Python Reddit API Wrapper) als Dependency hinzugefügt
  - Reddit-Credentials als Platzhalter in .env vorbereitet
  - ⚠️ Noch nicht aktiv – wartet auf Reddit API App-Erstellung durch User

## [0.19.5] - 2026-03-15
### Verbessert
- **Alle Radar-Agenten zweisprachig (DE/EN)** 🌍
  - Twitter/X-Tweets: CTA jetzt "Protect yourself / Schützt euch – Fake Defense AI"
  - Twitter/X-Hashtags: International (#FakeShop #OnlineScam #FakeDefenseAI)
  - Instagram-Captions: Zweisprachig EN/DE mit Quellenangabe (Video Radar)
  - Agent-Prompts: Sprachregel "zweisprachig, bei Platzmangel Englisch bevorzugen"
  - Telegram bleibt Deutsch (nur für André)

## [0.19.4] - 2026-03-15
### Verbessert
- **WordPress-Seiten zweisprachig (DE/EN)** 🌍
  - News Radar: Header, Intro, CTA, Footer und Copyright-Disclaimer jetzt deutsch und englisch
  - Video Radar: Header, Intro, CTA, Footer und Copyright-Disclaimer jetzt deutsch und englisch
  - Artikel-Tags sprachabhängig: "WARNUNG"/"WARNING", "VERBRAUCHERSCHUTZ"/"CONSUMER PROTECTION", "SCAM ALERT"
  - "Artikel lesen →" / "Read article →" je nach Artikelsprache
  - "Auf YouTube ansehen" / "Watch on YouTube" je nach Videosprache
  - CTA-Button: "FREE DOWNLOAD / KOSTENLOS"
  - Copyright-Footer in beiden Sprachen mit korrekten HTML-Entities (keine Emojis)

## [0.19.3] - 2026-03-15
### Behoben
- **Emoji-Encoding auf WordPress gefixt** 🔧
  - Alle Emojis aus dem generierten WordPress-HTML entfernt (📰, 🔍, 📅, 🛡, 📱, ⚖️, 🎬, 📷 etc.)
  - WordPress konnte Emojis nicht korrekt rendern (Mojibake wie ðŸ"°)
  - Ersetzt durch reine Text-/HTML-Alternativen (z.B. "Bild:", HTML-Entities)
  - Betrifft: `news_agent.py` und `video_agent.py` (nur HTML-Output, Telegram behält Emojis)
  - Post-Titel jetzt ohne Emojis

## [0.19.2] - 2026-03-15
### Verbessert
- **Copyright-Schutz für alle Radar-Agenten** ⚖️
  - WordPress News Radar: Quellenangabe (📷 Quelle) auf jedem OG-Image-Vorschaubild
  - WordPress News Radar: Copyright-Disclaimer im Footer (§ 51 UrhG Zitatrecht)
  - WordPress Video Radar: Copyright-Disclaimer im Footer (YouTube-Embed-API ToS)
  - WordPress Video Radar: © Channel-Name bei jedem Video
  - Agent System-Prompts: Neue Copyright-Regeln für newsradar und videoradar
    - Keine Volltexte kopieren, nur Zusammenfassungen
    - Immer Quelle/Kanal nennen (WordPress, Twitter, Instagram)
    - YouTube-Videos nur einbetten, nicht re-uploaden
    - Bei Takedown-Requests sofort entfernen

## [0.19.1] - 2026-03-15
### Verbessert
- **Twitter/X Tweets mit Bildern** 📸
  - Tweets werden jetzt immer mit Bild gepostet (statt nur Text mit Link-Card)
  - News-Tweets: OG-Image (Open Graph) wird automatisch vom Originalartikel heruntergeladen
  - Video-Tweets: YouTube-Thumbnail wird als Bild angehängt
  - Fallback: Fake Defense AI Logo wird verwendet wenn kein anderes Bild verfügbar
  - Neuer Media-Upload über Tweepy v1.1 API (`get_api_v1()`, `upload_media()`)
  - Neue Hilfsfunktionen: `download_article_image()`, `get_youtube_thumbnail()`, `get_fallback_logo()`
  - CLI: Neues `--image PFAD` Flag für Einzeltweets mit Bild
  - Batch-Modus: Unterstützt neue Felder `image_path`, `video_id`, `thumbnail_local` im JSON

- **WordPress-Blogposts mit Artikelbildern** 🖼
  - News Radar: OG-Images der Originalartikel werden automatisch in die WordPress-Blogposts eingebunden
  - Bilder erscheinen oben in jeder Artikel-Card (200px Höhe, object-fit: cover)
  - `onerror` Fallback: Bild-Container wird ausgeblendet wenn Bild nicht laden kann
  - Neue Funktion `fetch_og_image_url()` extrahiert og:image/twitter:image Meta-Tags
  - OG-Image-URL wird auch in der JSON-Ausgabe mitgegeben (Feld `og_image`)

## [0.19.0] - 2026-03-15
### Neu
- **Video Radar Agent** 🎬
  - Neuer Agent `videoradar` sucht täglich nach YouTube-Videos über Fake-Shops, Online-Betrug und Verbraucherschutz
  - Python-Script `lib/video_agent.py` mit 3 Suchquellen: YouTube Direct Search (Hauptquelle), Google News RSS, YouTube RSS
  - YouTube Direct Search scraped Suchergebnisse direkt von youtube.com (kein API-Key nötig)
  - Findet Videos aus DE + EN Suchbegriffen (9 Queries, ~80+ Videos pro Lauf)
  - Generiert WordPress-Blogposts mit eingebetteten YouTube-iframes im Fake Defense AI Design
  - Lädt automatisch Video-Thumbnails herunter für Instagram-Posts
  - Automatische Duplikat-Erkennung über Hash-basiertes State-Management (`data/video_seen.json`)
  - Scheduled Task läuft täglich um 22:00 Uhr (`0 22 * * *`)
  - Workflow: Videos suchen → WordPress-Post → Twitter/X Tweets → Instagram Posts → Telegram mit allen Links
  - CLI-Optionen: `--dry-run`, `--force`, `--lookback N` (Tage)
  - Maximal 10 Videos pro Blogpost

## [0.18.1] - 2026-03-15
### Behoben
- **Encoding-Fix für News Radar** 🔧
  - Umlaute (ä, ö, ü, ß) wurden als Mojibake (Ã¤, Ã¶, etc.) angezeigt
  - Ursache: `feedparser.parse(resp.content)` statt `resp.text` → falsche Encoding-Erkennung
  - Fix: `resp.encoding = resp.apparent_encoding` + `feedparser.parse(resp.text)`
  - Neue `fix_mojibake()` Funktion als Sicherheitsnetz (Latin-1→UTF-8 Reparatur)
  - Bestehender Artikel auf WordPress manuell repariert (29 Stellen korrigiert)

### Verbessert
- **News Radar: Telegram-Nachricht mit Links** 🔗
  - Agent sendet nach dem Publizieren alle Links per Telegram (WordPress-URL + Tweet-URLs)
  - Formatierte Zusammenfassung mit Artikelliste

## [0.18.0] - 2026-03-14
### Neu
- **Fake-Shop News Radar Agent** 📰
  - Neuer Agent `newsradar` sucht täglich nach aktuellen Nachrichten über Fake-Shops, Online-Betrug und Internetkriminalität
  - Python-Script `lib/news_agent.py` fetcht Google News RSS für 7 verschiedene Suchbegriffe
  - Automatische Duplikat-Erkennung über Hash-basiertes State-Management (`data/news_seen.json`)
  - Generiert WordPress-Blogposts im Fake Defense AI Design (dunkles Farbschema)
  - Artikel werden mit farbcodierten Kategorie-Tags versehen (Warnung, Polizei, Verbraucherschutz, Phishing, News)
  - Scheduled Task läuft täglich um 21:00 Uhr (`0 21 * * *`)
  - Workflow: News fetchen → WordPress-Post erstellen → Blog-Übersicht aktualisieren → Twitter/X Post → Telegram-Benachrichtigung
  - **Twitter/X Auto-Post**: Nach jedem neuen Blogbeitrag wird automatisch ein Tweet **pro Artikel** auf @FakeDefenseAI gepostet (Batch-Modus mit 5s Pause zwischen Tweets)
  - `lib/twitter_poster.py`: Neue Funktion `post_article_tweets()` und CLI `--batch` Modus für mehrere Tweets
  - Neue Dependency: `feedparser>=6.0.0`
  - CLI-Optionen: `--dry-run` (Vorschau), `--force` (erneut ausführen), `--lookback N` (letzte N Tage)
  - Deutsche + englische Nachrichtenquellen (13 Suchbegriffe)
  - News-Beiträge werden als Top-Level Pages angelegt (nicht als Blog-Posts)

### Aktualisiert
- **WordPress Fake Defense AI Farbschema vereinheitlicht** 🎨
  - Alle 6 Unterseiten (About, Features, How It Works, Contact, Get Protected, Blog) auf das Homepage-Farbschema umgestellt
  - Farb-Mapping: #1A2332→#0d1137, #2A3444→#151a45, #90A4AE→#8899cc, #E0E0E0→#ffffff, #4FC3F7→#00b4d8
  - Copyright-Jahr auf 2026 aktualisiert
- **Contact-Seite E-Mail aktualisiert** ✉️
  - Alle E-Mail-Adressen auf fake.defense.ai@gmail.com geändert (vorher: Rochlitz.Consulting@gmail.com)

## [0.17.3] - 2026-03-10
### Aktualisiert
- **WordPress-Startseite komplett neu gestaltet** 🌐
  - Modernes Layout mit Header, Skills (3-Spalten), Projekte mit Firmenlogos und Kontakt-Bereich
  - Firmenlogos von Wikimedia Commons eingebunden: Deutsche Bahn, BWI, Mercedes Benz, BMW, Volkswagen, Deutsche Post
  - Text-Labels für Firmen ohne frei verfügbare Logos: KV digital, GEMA, Conrad, 4flow, MyToys
  - Skills-Bereich mit Emoji-Icons in 3 Spalten (Sprachen, Frameworks, Cloud/DevOps, Datenbanken, Messaging, Architektur)
  - Kontakt-Bereich mit 2 Spalten und Status-Info
  - URL: https://andrerochlitz.wordpress.com/

## [0.17.2] - 2026-03-09
### Verbessert
- **Queue: Tabellenansicht mit ID, Titel und Zeitstempel** 📊
  - Jeder Job bekommt eine fortlaufende ID
  - `/queue` zeigt jetzt eine Tabelle: ID | Status | Zeit | Titel
  - Jeder Request eine eigene Zeile (keine Zusammenfassung mehr)
  - Job-History speichert die letzten 50 Jobs
  - Status-Emoji pro Job: ⏳ wartend, 🔄 läuft, ✅ fertig, ❌ Fehler
  - Zusammenfassung am Ende: laufend / wartend / erledigt

## [0.17.1] - 2026-03-06
### Verbessert
- **Queue: Titel für Jobs** 📋
  - Jeder Job in der Warteschlange hat jetzt einen lesbaren Titel
  - `/queue` und `/status` zeigen Titel statt abgeschnittener Prompts
  - Bei Einreihung wird der Titel in der Bestätigung angezeigt
  - Wartende Jobs werden einzeln mit Nummer und Titel aufgelistet
  - Freitext, /claude und Bildanalyse vergeben automatisch passende Titel

## [0.17.0] - 2026-03-04
### Hinzugefügt
- **Warteschlange (Queue) statt Kill** 📋
  - Neue `ClaudeQueue`-Klasse ersetzt das alte Anti-Zombie Kill-System
  - Neue Nachrichten werden **eingereiht** statt den laufenden Prozess abzubrechen
  - Pro-Agent `asyncio.Queue` mit automatischem Worker-Management
  - Worker startet automatisch bei erstem Job, beendet sich nach 5 Min Leerlauf
  - Sequentielle Verarbeitung pro Agent – gleiche Claude-Session wird weiterverwendet
  - User bekommt Feedback: "📋 In Warteschlange (Position X)"
  - Bildanalyse (Photos) nutzt ebenfalls die Queue
  - Job-Statistiken: verarbeitete Jobs pro Agent werden getrackt
- **`/queue` Command** – Warteschlangen-Status anzeigen
  - Zeigt laufende Jobs mit Laufzeit und Prompt-Vorschau
  - Zeigt wartende Jobs pro Agent
  - Zeigt verarbeitete Jobs (Session-Counter)
- **`/status` erweitert** um Queue-Info
### Entfernt
- `_active_claude` Prozess-Tracker (ersetzt durch `ClaudeQueue`)
- `_kill_old_claude()` Funktion (kein Kill mehr nötig)
- `_run_claude_background()` Funktion (ersetzt durch `ClaudeQueue._execute_claude()`)
- `_run_photo_analysis_background()` Funktion (ersetzt durch `ClaudeQueue._execute_photo()`)

## [0.16.0] - 2026-03-04
### Hinzugefügt
- **Anti-Zombie Prozess-Tracker** 🔪
  - `_active_claude` dict trackt alle laufenden Claude-Prozesse pro Agent
  - `_kill_old_claude()` – killt vorherigen Prozess bevor neuer startet
  - Neue Nachricht während Claude arbeitet → alter Prozess wird sauber beendet
  - User bekommt Info: "Vorherige Anfrage abgebrochen, starte neue..."
  - Gilt für `_run_claude_background()` UND `_run_photo_analysis_background()`
- **Auto-Session-Rotation – Verhindert aufgeblähte Konversationen** 🔄
  - Session-Transcript wird bei jedem Claude-Aufruf geprüft
  - Bei > 5 MB automatisch frische Session gestartet (Limit: `MAX_SESSION_SIZE_MB`)
  - Verhindert exponentiell wachsende Antwortzeiten durch riesige Kontexte
  - `_check_session_size()` und `_session_transcript_path()` Hilfsfunktionen
- **Safety-Timeout für Claude-Prozesse (10 Min)** ⏱️
  - `CLAUDE_MAX_RUNTIME = 600` – verhindert Zombie-Prozesse
  - Prozess wird nach Timeout sauber gekillt (`proc.kill()`)
  - User bekommt Timeout-Nachricht mit Tipp für `/newsession`
  - Warnung im Log bei Antwortzeiten > 120s
### Behoben
- **Zombie-Claude-Prozesse** – Alte Prozesse liefen tagelang weiter (PID seit 28.02.)
- **31 MB Session-Transcript** – Assistant-Session auf frische ID zurückgesetzt
- **Leere Antworten (0 Zeichen)** – durch Session-Bloat verursacht, jetzt durch Auto-Rotation verhindert

## [0.15.0] - 2026-03-03
### Hinzugefügt
- **Asynchrone Hintergrund-Tasks – Claude ohne Timeout** ⏳
  - Neue Coroutine `_run_claude_background()` für nicht-blockierende Claude-Aufrufe
  - Handler `/claude`, Freitext (`handle_message`), Bildanalyse (`handle_photo`) nutzen jetzt async Background-Tasks
  - Sofortige Antwort "⏳ Claude läuft..." beim Aufruf
  - Typing-Indikator läuft im Hintergrund bis Ergebnis kommt
  - **KEIN 300s Timeout** mehr – lange Aufgaben (Playwright, Daten-Syncs) blockieren nicht mehr
  - Ergebnis wird automatisch per Reply gesendet wenn fertig
  - Alle Handler können parallel Anfragen verarbeiten (Event-Loop Multiplexing)
  - Bot bleibt während langer Claude-Läufe responsiv (z.B. `/status` funktioniert sofort)

## [0.14.0] - 2026-03-03
### Hinzugefügt
- **Task-Preparation Agent – Intelligente Planung & Erinnerungen** 📋
  - Neuer Agent `taskprep` ("Aufgaben-Vorbereiter")
  - Analysiert synchronisierte Kalender-, E-Mail- und Kontaktdaten
  - **3 Scheduled Tasks**:
    - `taskprep_morning` (täglich 7 Uhr): Morgen-Briefing mit Tagesübersicht, Reiserouten, Aufgaben
    - `taskprep_precheck` (alle 3h, 9-20 Uhr): Kurzcheck auf nahende Termine + Abfahrts-Erinnerungen
    - `taskprep_evening` (täglich 20 Uhr): Rückblick + Morgen-Vorschau
  - **Smart Timing-Regeln**:
    - Termine MIT Ort: 1 Woche, 1 Tag, Morgen, 90 Min vor Abfahrt
    - Termine OHNE Ort: 1 Tag, Morgen, 30 Min vorher
    - Deadlines/Fristen: 1 Woche (Briefing), 3 Tage, 1 Tag, Am Tag
    - E-Mail-Aufgaben: Einmalig bei Erkennung, dann wie Deadlines
  - **Automatische Vorbereitung**:
    - Google Maps Reiserouten via Playwright (ÖPNV-optimiert, Start: Im Achterkastell 1, 10315 Berlin)
    - Kontext sammeln: Passende E-Mails zu Terminen finden
    - Dokumente identifizieren: Hinweise auf relevante Dateien in Google Drive
  - **User-Erinnerungen** (der Bot kann's nicht selbst):
    - Explizite Checklisten für: Dokumente ausdrucken, Unterlagen packen, Bestätigungen senden, Rechnungen bezahlen, Anrufe tätigen, E-Mails beantworten
  - **State-Management**:
    - `data/taskprep_state.json` speichert bereits gemeldete Ereignisse (Event-Hash + Benachrichtigungstypen)
    - Verhindert Duplikat-Erinnerungen (intelligent: 1 Benachrichtigung pro Event-Timing, nicht mehrfach)
    - Automatische Cleanup bei alten Einträgen
  - **Intelligente Output-Filter**:
    - KEINE Nachricht wenn nichts Relevantes ansteht (nicht nervig)
    - Präzise Erinnerungen nur bei Bedarf
    - Übersichtliche Briefing-Formate mit Emoji und Struktur

## [0.12.0] - 2026-02-28
### Hinzugefügt
- **Personal Knowledge Base – Vollständige Datenerfassung & Sync** 🧠
  - `lib/knowledge_sync.py` – Neues Core-Sync-Modul
    - `KnowledgeSync` Klasse mit Delta-Sync (Hash-basierte Deduplizierung, SHA256)
    - Gmail-Sync: E-Mail-Zusammenfassungen → ChromaDB (incremental, Hash pro Absender+Betreff+Datum)
    - Kalender-Sync: Termine → ChromaDB (Replace-All Strategie)
    - Kontakte-Sync: Kontakte → ChromaDB (Diff: neue/geänderte/gelöschte)
    - Google Drive Sync (0 API-Tokens, reiner Dateisystem-Zugriff):
      - Ordnerstruktur (~/gdrive, 3 Ebenen tief)
      - Textdateien (.txt, .md, .csv, .json etc.) – Inhalt der 200 neuesten Dateien
      - PDF-Katalog (nur Name + Pfad + Größe + Datum)
    - Sicherheit: Keepass, .kdbx, security/-Ordner werden NICHT indexiert
    - CLI-Interface: `python -m lib.knowledge_sync [drive|status]`
    - State-Persistenz: `data/sync_state.json` mit known_hashes pro Quelle
  - **`/sync` Telegram-Command**:
    - `/sync status` – Sync-Status aller Quellen anzeigen
    - `/sync drive` – Google Drive Komplett-Sync
    - `/sync gmail` – Gmail-Cache in ChromaDB laden
    - `/sync calendar` – Kalender-Cache laden
    - `/sync contacts` – Kontakte-Cache laden
    - `/sync all` – Alle verfügbaren Quellen synchronisieren
  - **Neuer Agent `datasync`** in agents.json:
    - 4 Scheduled Tasks: Gmail (alle 4h), Kalender (täglich 6 Uhr), Kontakte (wöchentlich), Drive (täglich 4 Uhr)
    - Drive-Task als `type: "bash"` (0 API-Tokens)
  - `/status` zeigt jetzt Knowledge Base Sync-Status an
- **Performance**: ~630 ChromaDB-Einträge nach Komplett-Sync, ~8ms Retrieval-Zeit

## [0.11.0] - 2026-02-28
### Hinzugefügt
- **Proaktives Erinnerungssystem** 🔔
  - `lib/reminders.py` - ReminderManager Klasse
    - Automatische Erkennung von Reminder-Phrasen via Regex ("erinnere mich", "ich muss", "nicht vergessen", "deadline", "frist", "termin am")
    - Datum-Parsing via `dateparser` mit deutscher Sprache und Future-Präferenz
    - Fallback: morgen 9:00 Uhr wenn kein Datum erkannt
    - Speicherung in `data/reminders.json` (einfach, debugbar)
  - **Bot-Integration**: Hook in `handle_message()` erkennt Reminder automatisch
    - Bestätigung: "🔔 Erinnerung gespeichert für DD.MM.YYYY HH:MM"
    - Nachricht wird trotzdem weiter an Claude gesendet (kein Early Return)
  - **Scheduler-Integration**: `_check_reminders()` prüft jede Minute auf fällige Erinnerungen
    - Kostet 0 API-Tokens (kein Claude-Aufruf)
    - Automatische Bereinigung: erledigte Erinnerungen nach 30 Tagen gelöscht
  - `/status` zeigt aktive Erinnerungen an
- **Bash-Task-Typ im Scheduler** ⚙️
  - Neues Feld `type: "bash"` in `scheduled_tasks` (config/agents.json)
  - Führt Shell-Befehle direkt aus OHNE Claude aufzurufen
  - Rückwärtskompatibel: bestehende Tasks (ohne type-Feld) laufen weiter als Claude-Tasks
  - Eigener Header: "⚙️ Typ: Bash-Befehl" statt "Agent: ..."
- **`/cpu` – Claude CPU & Memory Monitor** 📊
  - Neuer Telegram-Befehl `/cpu` – auf Anfrage, kein Cron-Job
  - Zeigt: Claude-Prozesse (PID, CPU%, MEM%), System Load, Memory-Übersicht
  - Nutzt KEIN Claude – reiner Bash-Befehl, direkt an Telegram gesendet
- `dateparser>=1.2.0` Dependency hinzugefügt

## [0.10.2] - 2026-02-27
### Verbessert
- **E-Mail-Check Duplikat-Vermeidung**: Stündlicher E-Mail-Check meldet nur noch wirklich neue E-Mails
  - `data/mailcheck_seen.json` speichert bereits analysierte E-Mails (Absender + Betreff)
  - Beim Check werden bereits gemeldete E-Mails automatisch übersprungen
  - Automatische Bereinigung: Einträge älter als 7 Tage werden entfernt
  - Neues Format-Element: `🔇 [Anzahl] bereits bekannte E-Mails ignoriert.`

## [0.10.1] - 2026-02-27
### Hinzugefügt
- **Neuer Agent: `fakechecker` - Fake-Kanzlei Checker** ⚖️
  - Spezialisierter Agent zur Überprüfung verdächtiger Anwaltskanzleien und juristischer Dienstleister
  - Basiert auf offiziellen **BRAK-Handlungshinweisen (April 2025)** für Betroffene von Fake-Kanzleien
  - Integriertes Wissen über 3 bekannte Betrugsmaschen: Fake-Insolvenzverkäufe, Fake-Forderungseinzüge, Fake-Zahlungsansprüche
  - Erkennt typische Täter-Methoden: Namensabwandlungen, Identitätsdiebstahl echter Kanzleien, gefälschte Gerichtsbeschlüsse, kopierte USt-/HRB-Nummern
  - 7-Phasen-Workflow:
    1. **BRAK Anwaltsverzeichnis-Check** (bravsearch.brak.de) - Ist der Anwalt zugelassen? Namensabwandlung? Kontaktdaten-Abgleich
    2. **Insolvenzbekanntmachungen** (neu.insolvenzbekanntmachungen.de) - Existiert das Verfahren? Ist der Verwalter bestellt?
    3. **Domain & Impressum-Analyse** - WHOIS, Domain-Alter, Impressum, kopierte USt-/HRB-Nr., Web Archive
    4. **Adress- & Kontakt-Verifikation** - Google Maps, Tellows, E-Mail-Domain, beA/eBO/MJP sichere Kanäle
    5. **Handelsregister** - Unternehmensregister, North Data, Insolvenzprüfung
    6. **Reputation & Warnungen** - BRAK-Warnungen, RAK-Warnungen, Google Reviews, Reclabox, Presse
    7. **Bankverbindung** - IBAN-Land-Check, ausländische IBAN = höchste Warnstufe
  - Strukturierter Risikobericht mit Ampel-Bewertung (🟢 SERIÖS / 🟡 VERDÄCHTIG / 🔴 FAKE)
  - Handlungsempfehlungen bei Betrug: Polizei, echte Kanzlei, RAK, DENIC-Löschantrag, Notice-and-Takedown (Art. 6 DSA)
  - Aktivierung via `/agent fakechecker`

## [0.10.0] - 2026-02-27
### Hinzugefügt
- **Zyklischer Task-Scheduler**: Automatische Ausführung wiederkehrender Agenten-Aufgaben
  - `lib/scheduler.py` - Core Scheduler-Modul mit Cron-Parser
    - Läuft als asyncio-Task im Bot-Event-Loop (kein separater Prozess)
    - Prüft alle 60 Sekunden welche Tasks fällig sind
    - Cron-Syntax: Minute, Stunde, Tag, Monat, Wochentag (z.B. `0 7 * * *`)
    - Unterstützt: `*`, Einzelwerte, Step (`*/15`), Bereiche (`9-17`), Listen (`1,5,10`)
    - Hot-Reload: `config/agents.json` wird bei jedem Zyklus neu geladen
    - State-Persistenz: `data/scheduler_state.json` (überlebt Bot-Neustarts)
    - Fehler-Isolation: Ein fehlender Task blockiert keine anderen
    - Timeout pro Task konfigurierbar
  - **Cron-Config direkt in `agents.json`** pro Agent:
    - Jeder Agent kann `scheduled_tasks` Array mit Cron-Jobs haben
    - Felder: `id`, `enabled`, `cron`, `prompt`, `timeout_seconds`, `description`
    - Beispiel-Tasks: System-Health-Check (alle 6h), Morgen-Briefing (7 Uhr), Code-Review (Mo 9 Uhr)
  - **`/scheduler` Telegram-Command**:
    - `/scheduler status` - Alle Tasks mit Status, letztem Lauf, Run-Count anzeigen
    - `/scheduler pause` - Scheduler pausieren
    - `/scheduler resume` - Scheduler fortsetzen
    - `/scheduler run <task_id>` - Task sofort beim nächsten Zyklus ausführen
  - `/status` zeigt jetzt auch Scheduler-Status an
  - Task-Ergebnisse werden automatisch via Telegram gesendet
  - RAG-Kontext wird automatisch bei Scheduler-Tasks angereichert

## [0.9.1] - 2026-02-27
### Behoben
- **Logging-Duplikate**: StreamHandler entfernt - doppelte Log-Einträge durch simultanes Schreiben auf Konsole und Datei behoben
- **Fehlerbehandlung**: Error-Handler für Telegram-API-Fehler (NetworkError) hinzugefügt - "No error handlers are registered" Warnung entfernt

## [0.9.0] - 2026-02-27
### Hinzugefügt
- **RAG Kontextmanagement-System**: Vollständig integriert in bot.py für automatische Prompt-Anreicherung
  - **bot.py RAG-Integration**:
    - Automatische Prompt-Anreicherung: System-Prompts werden mit relevantem semantischem Memory angereichert
    - Automatische Interaktions-Speicherung: Alle User-Queries und Assistant-Responses werden nach jedem API-Call gespeichert
    - Wirkt in allen Claude API-Calls: `/claude`, Freitext, Bildanalyse
    - Performance: ~5-10ms zusätzlich pro Request für RAG-Retrieval
    - Error-Handling: RAG-Fehler sind nicht-kritisch (Fallback zu Original-Prompt)
  - **RAG Kontextmanagement-System**: Retrieval-Augmented Generation mit ChromaDB für semantisches Long-Term Memory
  - `lib/context_manager.py` - Core RAG-Engine mit ChromaDB Persistenz
    - 3 Collections: conversations, knowledge, user_preferences
    - Semantic Search mit Cosine Similarity
    - Embedding-Modell: all-MiniLM-L6-v2 (384-dimensionale Vektoren)
    - Methods: `store_conversation()`, `store_knowledge()`, `store_user_preference()`, `retrieve_relevant_context()`, `enrich_prompt()`
  - `lib/rag_integration.py` - Vereinfachte Bot-Integration
    - Automatische Prompt-Anreicherung für Claude API Calls
    - Interaktions-Tracking und Metadaten-Speicherung
    - Präferenz-Management (`set_user_preference()`, `enrich_user_message()`)
  - `docs/RAG_SYSTEM.md` - Umfassende Dokumentation mit API-Referenz, Integration-Guide, Best Practices
  - `examples/rag_example.py` - 4 vollständige funktionsfähige Beispiele (Basis-Verwendung, RAG-Enrichment, Konversations-Tracking, Memory-Statistiken)
  - Persistenter Storage: `data/chroma_db/` mit automatischem Backup-Export
- **ChromaDB Dependency** hinzugefügt zu requirements.txt (>= 0.4.0)
- **Performance getestet**: ~5-10ms Retrieval für Top-K Results, <1ms bei Hit-Caching
- **Production-ready**: Alle Tests bestanden, Dokumentation komplett, Sicherheit & Datenschutz integriert

## [0.8.1] - 2026-02-25
### Hinzugefügt
- **Persistente Sessions**: Claude-Konversationen überleben Bot-Neustarts
  - Feste Session-ID (UUID) pro Agent, gespeichert in `data/sessions.json`
  - `--continue` ersetzt durch `--session-id <uuid>` für zuverlässige Persistenz
  - `/newsession` - Session zurücksetzen, nächste Nachricht startet frische Konversation
  - Session-Verwaltung: `load_sessions()`, `get_session_id()`, `reset_session()`
  - `data/` Ordner wird beim Start automatisch erstellt
- **Typing-Indikator**: "tippt..." wird alle 4 Sekunden erneuert, solange Claude/Bash arbeitet
  - `TypingLoop`-Klasse sendet periodisch `ChatAction.TYPING`
  - Aktiv in allen Handlern: `/claude`, `/bash`, Freitext, Bildanalyse

## [0.8.0] - 2026-02-25
### Hinzugefügt
- **2FA per E-Mail**: Bot ist beim Start gesperrt, 6-stelliger Code wird per Gmail SMTP gesendet
  - `/2fa` - Neuen Code anfordern (10 Min. Gültigkeit)
  - Code-Eingabe direkt im Chat, alle Handler blockiert bis Verifizierung
  - `lib/auth.py` - TwoFactorAuth-Klasse mit generate, send, check
- **Worker-Bot**: `assistina_workerbot` spiegelt jeden eingehenden Request im selben Chat
  - Formatierte Nachricht mit User, Request-Typ, Inhalt, Agent, Uhrzeit
  - `lib/worker.py` - Async Request-Logger über separaten Bot-Token
- **Ordner-Reorganisation**: Saubere Projektstruktur
  - `lib/` - Python-Module (auth, browser, notifier, worker)
  - `config/` - Konfigurationsdateien (agents.json, mcp_config.json)

### Geändert
- `bot.py`: Pfade auf `config/` umgestellt, 2FA-Guard in allen Handlern, Worker-Calls
- `lib/browser.py`: WORKING_DIR auf parent.parent angepasst
- `lib/notifier.py`: .env-Pfad auf parent.parent angepasst

### Entfernt
- `test_mcp.png` aufgeräumt

## [0.7.0] - 2026-02-25
### Hinzugefügt
- `/vorlesen <text>` - Text-to-Speech: Text als Audio-Nachricht vorlesen (Google TTS, Deutsch)
- Auch als Reply auf eine Nachricht nutzbar: einfach `/vorlesen` auf eine bestehende Nachricht antworten
- gTTS Dependency hinzugefügt

## [0.6.0] - 2026-02-25
### Hinzugefügt
- Neuer Agent: `auditor` - Forensic Corporate Auditor für Corporate Intelligence, Bilanzanalyse und Betrugserkennung
  - 4-Phasen-Workflow: Struktur & Vernetzung, Finanzprüfung, Reputation, Technische Infrastruktur
  - Nutzt North Data, Bundesanzeiger, Unternehmensregister, TÜV, Trusted Shops, ViewDNS, Tellows
  - Strukturierter Risikobericht mit Ampel-Bewertung (GRÜN/GELB/ROT)

## [0.5.0] - 2026-02-25
### Hinzugefügt
- Agenten-System: Konfigurierbare Agenten mit eigenem System-Prompt und Modell
- `agents.json`: Konfigurationsdatei für Agenten (assistant, coder, researcher, writer)
- `/agent <name>` - Agent wechseln
- `/agents` - Verfügbare Agenten auflisten
- Jeder Claude-Aufruf nutzt den aktiven Agenten (System-Prompt, Modell)
- `/status` zeigt aktiven Agenten und MCP-Status

## [0.4.0] - 2026-02-25
### Hinzugefügt
- MCP Playwright Integration: Persistente Browser-Session über `@playwright/mcp` SSE-Server
- `browser.py`: MCP-Client-Modul mit navigate, screenshot, click, type_text, list_tabs, get_snapshot
- `/browse <url>` - Website öffnen mit Screenshot + Accessibility-Snapshot
- `/snap` - Aktuelle Seite als strukturierten Text anzeigen
- `/click <ref>` - Element per Accessibility-Ref anklicken
- `/type <ref> | <text>` - Text in Eingabefeld tippen
- `/tabs` - Offene Browser-Tabs auflisten
- `start.sh` startet jetzt auch MCP Playwright Server (Port 8931, headless, shared context)
- `/status` zeigt MCP Server-Status an

### Geändert
- `/playwright` durch `/browse` ersetzt (nutzt jetzt MCP statt direktem Playwright)
- Browser-Session bleibt persistent zwischen Anfragen (shared-browser-context)

## [0.3.0] - 2026-02-25
### Geändert
- Persistente Claude-Session: Alle Claude-Aufrufe (`/claude`, Freitext, Bildanalyse) verwenden jetzt `--continue`, sodass immer dieselbe Session fortgeführt wird und der Kontext erhalten bleibt

## [0.2.0] - 2026-02-25
### Hinzugefügt
- Foto-Analyse: Bilder über Telegram senden, Claude analysiert sie
- `/restart` Befehl zum Neustarten des Bots
- Logging mit RotatingFileHandler (`logs/bot.log`, 5MB, 3 Backups)
- `start.sh` mit automatischem `tail -f` auf Log
- `.gitignore` für `.idea/`, `venv/`, `.env`, `logs/`

## [0.1.0] - 2026-02-25
### Hinzugefügt
- `bot.py`: Bidirektionaler Telegram-Bot (Claude Code Bridge)
- `/claude` - Nachricht an Claude Code senden
- `/bash` - Shell-Befehl ausführen
- `/playwright` - Screenshot einer Webseite
- `/status` - Bot-Status anzeigen
- Freitext wird direkt an Claude Code weitergeleitet
- `notifier.py`: Standalone-Modul zum Senden von Telegram-Nachrichten
- `start.sh`: Start-Script (beendet alte Instanzen, startet neu)
- Autorisierung: Nur konfigurierte Chat-ID erlaubt
