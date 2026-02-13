# Ticket Intelligence API – Demo Django + Machine Learning

Demo di backend per la gestione di ticket con **Django REST Framework**, **PostgreSQL**, **Docker** e un piccolo modello di **Machine Learning** per:

- classificare automaticamente i ticket per categoria (billing, bug, account, ecc.);
- trovare ticket simili a partire dal testo;
- calcolare semplici metriche di supporto (trend per categoria, MTTR).


---

## Tech stack

- **Linguaggio**
  - Python 3.12

- **Web framework / API**
  - Django 5.x
  - Django REST Framework (DRF)
  - drf-spectacular (generazione schema OpenAPI + Swagger UI)

- **Database**
  - PostgreSQL 16 (in Docker)
  - ORM Django per l’accesso ai dati

- **ML / Analytics**
  - scikit-learn (TF–IDF + Logistic Regression)
  - joblib (salvataggio modello su disco)

- **Container / DevOps**
  - Docker
  - Docker Compose

---

## Prerequisiti

- Docker installato e funzionante.
- Docker Compose disponibile (versione plugin moderna va bene).
- Accesso a una shell (Linux, macOS o WSL2/PowerShell su Windows).

Non è richiesto installare Python né Postgres localmente se si utilizza il percorso con Docker.

---

## Configurazione ambiente (`.env`)

Nella root del progetto, creare un file `.env` contenente almeno le variabili:


DJANGO_SECRET_KEY=<stringa_lunga_e_random>
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost

POSTGRES_DB=<nome_db_es. ticketdb>
POSTGRES_USER=<utente_db_es. ticketuser>
POSTGRES_PASSWORD=<password_db_robusta>

DATABASE_URL=postgres://<utente_db>:<password_db>@db:5432/<nome_db>


Note:

* In sviluppo è accettabile `DJANGO_DEBUG=True`.
* In produzione impostare `DJANGO_DEBUG=False`, usare una `DJANGO_SECRET_KEY` robusta e non esporre il database al di fuori della rete interna.
* Il file `.env` **non** deve essere versionato su Git (`.gitignore`).

---

## Avvio con Docker

1. **Clonare la repository**

   ```bash
   git clone <URL_REPO>
   cd ticket-intelligence-api
   ```

2. **Creare il file `.env`**

   * Utilizzare la struttura mostrata sopra.
   * Scegliere valori robusti per password e secret key.

3. **Avviare i container**

   ```bash
   docker compose up -d
   ```

   Questo comando avvia:

   * un container `db` con PostgreSQL;
   * un container `web` con Django + DRF.

4. **Applicare le migrazioni**

   ```bash
   docker compose exec web python manage.py migrate
   ```

5. **Creare un superuser Django**

   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

   * Durante la creazione scegliere una password robusta.
   * Opzionalmente usare un password manager (es. Bitwarden o simili) per gestire le credenziali.

6. **Generare ticket demo sintetici (opzionale ma consigliato)**

   ```bash
   docker compose exec web python manage.py seed_tickets --n 200
   ```

   Questo comando:

   * crea un utente `demo` (non staff) se non esiste;
   * cancella eventuali ticket esistenti;
   * genera `n` ticket sintetici con:

     * categorie varie (`billing`, `bug`, `account`, `feature`, `other`);
     * stati misti (`OPEN`, `IN_PROGRESS`, `RESOLVED`, `CLOSED`);
     * timestamp coerenti per `created_at` / `resolved_at`.

7. **Allenare il modello di Machine Learning**

   Una volta popolato il database con ticket di esempio, allenare il modello via API:

   * Aprire Swagger UI:
     `http://localhost:8000/api/docs/`
   * Se necessario, effettuare login (in alto a destra) con il superuser creato.
   * Andare alla sezione **ml** → `POST /api/ml/train/`.
   * Premere **Try it out** → **Execute**.

   Se il training va a buon fine, la risposta contiene qualcosa del tipo:

   ```json
   {
     "n_samples": 200,
     "n_classes": 5,
     "classes": ["account", "billing", "bug", "feature", "other"],
     "model_path": "/code/ml/artifacts/ticket_classifier.joblib"
   }
   ```

   Il modello allenato viene salvato in `ml/artifacts/ticket_classifier.joblib`
   all’interno del container.

8. **Accesso a admin e API**

   * Admin Django:
     `http://localhost:8000/admin/`
   * Swagger UI (documentazione + test API):
     `http://localhost:8000/api/docs/`
   * Schema OpenAPI (JSON):
     `http://localhost:8000/api/schema/`

---

## Esecuzione dei test automatici

Per eseguire la suite di test sull’app `tickets`:

```bash
docker compose exec web python manage.py test tickets
```

I test coprono:

* creazione e logica di base dei `Ticket`;
* endpoint API principali (elenco, creazione, assegnazione, transizione);
* training del modello ML e predizione per un ticket;
* calcolo dell’MTTR con dati coerenti.

---

## Architettura e flusso ad alto livello

L’applicazione rappresenta un **backend di ticketing** a cui un frontend (web o mobile) può connettersi via API.

1. **Gestione ticket**

   * I ticket vengono rappresentati come oggetti Django (`Ticket`) e salvati in un database PostgreSQL tramite ORM.
   * Le API REST permettono di:

     * creare nuovi ticket (es. apertura di un problema di billing);
     * leggere liste di ticket (filtrando per stato, assegnatario, ordinamento…);
     * aggiornare stato, priorità, assegnatario;
     * chiudere o risolvere i ticket.

2. **Intelligenza “data-driven”**

   A partire dai ticket storici, il backend:

   * estrae il testo di `title` + `description` per ogni ticket etichettato con una categoria;
   * costruisce una rappresentazione numerica (TF–IDF) del testo;
   * allena un modello di **Logistic Regression** che classifica i ticket in una delle categorie funzionali (billing, bug, account, …);
   * salva il modello su disco per riutilizzarlo senza riaddestrarlo a ogni richiesta.

   Una volta allenato, il modello viene utilizzato per:

   * **suggerire automaticamente una categoria** per un ticket (endpoint `/api/tickets/{id}/ml_predict/`);
   * **trovare ticket simili** in base al testo (endpoint `/api/tickets/{id}/similar/`), usando la stessa rappresentazione TF–IDF e la **cosine similarity**.

3. **Analytics**

   Due endpoint forniscono insight operativi:

   * `/api/analytics/trends/`
     calcola il conteggio dei ticket per categoria in una finestra temporale configurabile (`days`).
   * `/api/analytics/mttr/`
     calcola il **Mean Time To Resolve (MTTR)**, ovvero il tempo medio (in secondi) tra `created_at` e `resolved_at` per i ticket risolti negli ultimi `N` giorni.

   Queste metriche sono tipiche KPI (Key Performance Indicators) per un team di supporto:

   * volume di ticket per area;
   * tempo medio di risoluzione.

4. **Containerizzazione**

   * L’intero stack (Django + Postgres) gira in container Docker definiti in `compose.yaml`.
   * Questo permette di:

     * eseguire la demo su qualsiasi macchina con Docker;
     * avere un ambiente isolato e riproducibile, indipendente dalle installazioni locali.

In un contesto reale, al posto di Swagger UI si potrebbe avere:

* una web app (React, Vue, ecc.) o app mobile;
* una dashboard di monitoraggio che consuma gli endpoint di analytics;
* integrazioni con altri sistemi (es. strumenti di ticketing interni, Slack, ecc.).

---

## Endpoint principali

### Ticket REST API

Base path: `/api/tickets/`

* `GET /api/tickets/`
  Elenco dei ticket, con filtri e ordinamento:

  * `?status=OPEN|IN_PROGRESS|RESOLVED|CLOSED`
  * `?assigned_to=me`
  * `?ordering=created_at` oppure `?ordering=-created_at`

* `POST /api/tickets/`
  Creazione di un nuovo ticket (l’utente autenticato viene usato come `created_by`).

* `GET /api/tickets/{id}/`
  Dettaglio di un singolo ticket.

* `PUT/PATCH /api/tickets/{id}/`
  Aggiornamento di un ticket.

* `DELETE /api/tickets/{id}/`
  Cancellazione (non usata nella demo, ma disponibile).

### Azioni custom su ticket

* `POST /api/tickets/{id}/assign/`
  Assegnare un ticket a un utente:
  body JSON `{"assigned_to": <user_id>}`.

* `POST /api/tickets/{id}/transition/`
  Cambiare lo stato del ticket nel workflow:
  body JSON `{"status": "IN_PROGRESS" | "RESOLVED" | "CLOSED" | ...}`.

* `POST /api/tickets/{id}/ml_predict/`
  Utilizzare il modello ML per suggerire una categoria.
  La categoria suggerita viene anche scritta sul campo `category` del ticket.

* `GET /api/tickets/{id}/similar/?top=5`
  Ottenere i ticket più simili in base al testo, con parametro `top` (1–20).

### Endpoint ML / Analytics

* `POST /api/ml/train/`
  Allenare il modello ML sui ticket attualmente salvati (solo quelli con `category` valorizzata).

* `GET /api/analytics/trends/?days=30`
  Conteggio dei ticket per categoria negli ultimi `days` giorni.

* `GET /api/analytics/mttr/?days=30`
  Calcolo del MTTR (in secondi) per i ticket risolti negli ultimi `days` giorni.

---

## Spiegazione dei file principali

### `config/settings.py`

* Configurare:

  * secret key, debug e allowed hosts (via variabili di ambiente);
  * connessione al database: se `DATABASE_URL` è definita → PostgreSQL; altrimenti fallback a SQLite.
* Registrare le app (`tickets`, `rest_framework`, `drf_spectacular`, …).
* Definire:

  * autenticazione e permessi DRF (autenticazione sessione + basic, `IsAuthenticated` di default);
  * paginazione default per le liste;
  * validatori password e hashers sicuri (Argon2 + PBKDF2).

### `config/urls.py`

* Esporre:

  * `/admin/` → pannello di amministrazione Django.
  * `/api/` → router DRF con le rotte dei ticket.
  * `/api/schema/` → schema OpenAPI generato automaticamente.
  * `/api/docs/` → Swagger UI (interfaccia per esplorare e testare le API).
  * `/api/ml/train/`, `/api/analytics/trends/`, `/api/analytics/mttr/` → endpoint extra standalone.

### `tickets/models.py`

* Definire il modello `Ticket` con:

  * campi testuali (`title`, `description`);
  * stato, priorità, categoria (con scelte limitate e indici per query efficienti);
  * relazioni con utenti (`created_by`, `assigned_to`);
  * timestamp (`created_at`, `updated_at`, `resolved_at`).
* Implementare uno `save()` custom che gestisce in modo coerente `resolved_at` quando lo stato passa a/da `RESOLVED`.

### `tickets/serializers.py`

* `TicketSerializer`:

  * serializzare/deserializzare i ticket verso/da JSON;
  * esporre `created_by` come stringa;
  * permettere di impostare `assigned_to` via ID;
  * impostare automaticamente `created_by` come utente autenticato in `create()`.

### `tickets/views.py`

* `TicketViewSet`:

  * implementare CRUD standard sui ticket;
  * aggiungere logica di filtro (`status`, `assigned_to=me`, `ordering`);
  * definire azioni extra (`assign`, `transition`, `ml_predict`, `similar`).
* `TrainModelView`:

  * gestire l’endpoint `/api/ml/train/` per allenare il modello ML.
* `AnalyticsTrendsView` e `AnalyticsMttrView`:

  * esporre endpoint per trend per categoria e MTTR;
  * usare aggregazioni ORM per calcolare le metriche sul database.

### `tickets/ml_utils.py`

* Definire le funzioni di supporto per il modello ML:

  * raccolta dei dati di training dai `Ticket`;
  * costruzione e training della pipeline TF–IDF + Logistic Regression;
  * salvataggio del modello con joblib;
  * caricamento con semplice cache in memoria;
  * predizione di categoria per un ticket;
  * ricerca di ticket simili tramite cosine similarity sui vettori TF–IDF.

### `tickets/management/commands/seed_tickets.py`

* Implementare il comando custom:

  ```bash
  python manage.py seed_tickets --n 200
  ```

* Generare ticket sintetici:

  * con categorie/stati misti;
  * con timestamp coerenti per il calcolo dell’MTTR;
  * con un utente `demo` come `created_by`.

### `tickets/tests.py`

* Contenere test unitari e di integrazione per:

  * logica del modello `Ticket` (es. `resolved_at` coerente);
  * principali endpoint API;
  * training e predizione del modello ML;
  * calcolo dell’MTTR con dati di esempio.

---

## Note su sicurezza e buone pratiche

* Non versionare:

  * il file `.env`;
  * artefatti del modello (`ml/artifacts/*.joblib`).
* Creare sempre un superuser e password nuove in ogni ambiente.
* In produzione:

  * impostare `DJANGO_DEBUG=False`;
  * configurare `ALLOWED_HOSTS` in modo esplicito;
  * utilizzare TLS/HTTPS e un database gestito adeguatamente.

```
```
