# Chat Arena — LLM Arena Architecture

> Scope: the **LLM (text/chat) arena** only. TTS, ASR, and OCR arenas are intentionally
> excluded. They reuse the same scaffolding (sessions, messages, feedback, leaderboards)
> but with modality-specific providers and UI.

---

## 1. System Context (C4 — Level 1)

```mermaid
graph TB
    subgraph Users
        U1[Registered User<br/>Google / Phone]
        U2[Guest / Anonymous User]
    end

    FE[React 19 SPA<br/>Chat-Arena-Frontend]

    subgraph Backend["Django + Channels Backend"]
        API[REST API<br/>Daphne / ASGI]
        WS[WebSocket Layer<br/>Channels]
        CEL[Celery Workers + Beat]
    end

    subgraph Data
        PG[(PostgreSQL<br/>default + tenant DBs)]
        RD[(Redis<br/>cache · broker · channel layer)]
        GCS[(Google Cloud Storage<br/>uploads + error logs)]
    end

    subgraph External
        FB[Firebase Auth]
        OAI[OpenAI / Azure]
        GEM[Google Gemini]
        ANT[Anthropic Claude]
        SAR[Sarvam / AI4Bharat]
        OTH[Meta · Mistral · DeepSeek · Qwen ...]
    end

    U1 --> FE
    U2 --> FE
    FE -->|Firebase SDK| FB
    FE -->|HTTPS REST + text stream| API
    FE -->|WSS session channel| WS

    API --> PG
    API --> RD
    API --> GCS
    API -->|verify JWT| FB
    API -->|stream completions| OAI & GEM & ANT & SAR & OTH

    WS --> RD
    CEL --> PG
    CEL --> RD
    CEL -->|provider health checks| OAI & GEM & ANT
```

**Roles**
- **Frontend** — single-page React app; renders the side-by-side arena, streams responses, collects votes.
- **REST API** — session/message/feedback/model/leaderboard endpoints; also proxies and streams LLM completions.
- **WebSocket layer** — per-session real-time channel (state sync, typing, broadcast); streaming itself goes over HTTP.
- **Celery** — async ELO updates, daily/weekly metric snapshots, model health checks, cleanup.
- **Redis** — Django cache, Celery broker/result backend, and Channels group layer.
- **PostgreSQL** — primary data store with a per-tenant database router.

---

## 2. Container / Module View (C4 — Level 2)

```mermaid
graph LR
    subgraph FE["Frontend (src/)"]
        direction TB
        ROUTER[router.jsx<br/>HashRouter + TenantRoute]
        STORE[Redux store<br/>auth · chat · models]
        RQ[React Query<br/>leaderboard/model cache]
        APICLI[api/client.js<br/>axios + interceptors]
        HOOKS[hooks<br/>useStreamingMessagesCompare<br/>useWebSocket]
        CHATUI[chat/components<br/>CompareView · MessageInput<br/>ModelSelector · FeedbackSelector]
        LBUI[leaderboard/components]
    end

    subgraph BE["Backend (Django apps)"]
        direction TB
        USER[user<br/>Firebase + anon auth]
        TEN[tenants<br/>middleware · db_router]
        SESS[chat_session<br/>ViewSet + consumer]
        MSG[message<br/>ViewSet + stream]
        AIM[ai_model<br/>llm_interactions]
        FB2[feedback<br/>votes]
        MM[model_metrics<br/>ELO + aggregators]
        LB[leaderboards<br/>published JSON]
        AP[academic_prompts]
    end

    CHATUI --> STORE
    CHATUI --> HOOKS
    LBUI --> RQ
    STORE --> APICLI
    RQ --> APICLI
    HOOKS -->|fetch text stream| MSG
    HOOKS -->|WSS| SESS
    APICLI --> USER & SESS & MSG & FB2 & AIM & LB

    USER --> TEN
    SESS --> TEN
    MSG --> AIM
    MSG --> SESS
    FB2 --> MM
    MM --> LB
    SESS --> AP
```

### Backend apps

| App | Responsibility | Key files |
|-----|----------------|-----------|
| `user` | Firebase JWT + anonymous-token auth, guest expiry/limits | `authentication.py`, `models.py` |
| `tenants` | URL-slug tenant detection, thread-local context, DB routing | `middleware.py`, `db_router.py`, `context.py` |
| `chat_session` | Session lifecycle (modes, share, duplicate, export), WS consumer | `views.py`, `services.py`, `consumers.py` |
| `message` | Messages, branching tree, **dual-model streaming** | `views.py` (`stream` action), `services.py` |
| `ai_model` | Model registry + provider dispatch + streaming generators | `models.py`, `llm_interactions.py`, `services.py` |
| `feedback` | Preference / rating / report votes | `models.py`, `views.py` |
| `model_metrics` | ELO ratings, win/loss aggregation, snapshots | `calculators.py`, `aggregators.py`, `services.py` |
| `leaderboards` | Published leaderboard JSON per arena/lang/org, contributors | `models.py`, `services.py` |
| `academic_prompts` | Curated benchmark prompts (used by random/academic modes) | `models.py` |

### Frontend layers

| Layer | Responsibility |
|-------|----------------|
| Routing | `app/router.jsx` — HashRouter; `TenantRoute` extracts `/:tenant/...` and sets `TenantContext`. |
| Global state (Redux) | `auth`, `chat` (sessions, messages, **streamingMessages**, turn timestamps), `models`. |
| Server cache (React Query) | Leaderboard tables, model lists — `staleTime 5m`. |
| API client | `shared/api/client.js` — axios with tenant-prefix, token injection, 401 refresh queue, fire-and-forget error logging. |
| Streaming hooks | `useStreamingMessagesCompare` (dual model), `useStreamingMessage` (direct), `useWebSocket` (session channel). |

---

## 3. Domain Model (ER)

```mermaid
erDiagram
    USER ||--o{ CHAT_SESSION : owns
    USER ||--o{ FEEDBACK : casts
    AI_MODEL ||--o{ CHAT_SESSION : "model_a / model_b"
    AI_MODEL ||--o{ MESSAGE : generates
    AI_MODEL ||--o{ MODEL_METRIC : rated_by
    CHAT_SESSION ||--o{ MESSAGE : contains
    CHAT_SESSION ||--o{ FEEDBACK : about
    MESSAGE ||--o{ FEEDBACK : "optional target"
    MESSAGE ||--o{ MESSAGE : "parent/child tree"

    USER {
        uuid id PK
        string email
        string phone_number
        string auth_provider "google|phone|anonymous"
        string firebase_uid
        bool is_anonymous
        datetime anonymous_expires_at
        json preferences "message_count, session_count, anonymous_token"
    }
    AI_MODEL {
        uuid id PK
        string provider "openai|google|anthropic|sarvam|..."
        string model_code UK
        string model_type "LLM"
        bool supports_streaming
        bool is_thinking_model
        bool random_only
        bool is_active
        json config "endpoints + params"
    }
    CHAT_SESSION {
        uuid id PK
        uuid user_id FK
        string mode "direct|compare|random|academic"
        uuid model_a_id FK
        uuid model_b_id FK
        string session_type "LLM"
        bool is_public
        string share_token
        datetime expires_at
    }
    MESSAGE {
        uuid id PK
        uuid session_id FK
        string role "user|assistant|system"
        text content
        uuid model_id FK
        uuid[] parent_message_ids
        uuid[] child_ids
        int position
        string participant "a|b (compare)"
        string status "pending|streaming|success|failed"
        string feedback
        float latency_ms
    }
    FEEDBACK {
        uuid id PK
        uuid user_id FK
        uuid session_id FK
        uuid message_id FK
        string feedback_type "preference|rating|report"
        uuid[] preferred_model_ids
        int rating
        string input_modality
        json tracking_data "turn timestamps"
    }
    MODEL_METRIC {
        uuid id PK
        uuid model_id FK
        string category "overall|text|code|reasoning|..."
        int wins
        int losses
        int ties
        int elo_rating
        string period "daily|weekly|monthly|all_time"
        datetime calculated_at
    }
```

**Notable design points**
- `Message` is a **DAG** via `parent_message_ids` / `child_ids` (GIN-indexed arrays) → supports branching and regeneration.
- In `compare`/`random` modes a single user turn fans out to **two assistant messages** distinguished by `participant ∈ {a, b}`.
- A `preference` vote is stored on `Feedback` (with `preferred_model_ids` + per-turn `tracking_data` timestamps) and **mirrored** onto the user `Message.feedback` field for quick render.
- Anonymous identity lives entirely in `User.preferences` (token + counters), so guests need no separate table.

---

## 4. The Arena Flow — Side-by-Side Compare

End-to-end sequence for one battle turn (`compare`/`random` mode):

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant FE as React SPA
    participant API as Django REST
    participant TH as Stream threads<br/>(model_a / model_b)
    participant P as LLM Providers
    participant WS as WS Consumer
    participant CEL as Celery
    participant DB as PostgreSQL

    Note over FE: guest-limit + privacy-consent checks
    U->>FE: type prompt, submit
    FE->>API: POST /sessions/ {mode, model_a, model_b, type:LLM}
    API->>DB: create ChatSession (+pick random models if mode=random)
    API-->>FE: session {model_a, model_b}
    FE->>WS: open WSS /ws/chat/session/{id}/

    FE->>API: POST /messages/stream/ {session, user+aiA+aiB msgs}
    API->>DB: persist user message + 2 pending assistant msgs
    par Model A
        API->>TH: stream_model_a()
        TH->>P: provider A completion (stream)
        P-->>TH: text deltas
    and Model B
        API->>TH: stream_model_b()
        TH->>P: provider B completion (stream)
        P-->>TH: text deltas
    end
    TH-->>API: shared chunk_queue (interleaved)
    API-->>FE: a0:"..."  b0:"..."  (text/plain stream)
    Note over FE: parse a0/b0 → updateStreamingMessage (75ms buffer)
    API-->>FE: ad:{finishReason} / bd:{finishReason}
    API->>DB: finalize messages (status, latency_ms, tokens)

    U->>FE: vote (Left / Both good / Both bad / Right)
    FE->>API: POST /feedback/ {preference, tracking_data}
    API->>DB: Feedback + mirror Message.feedback
    API-->>FE: session_update (vote counts)

    loop every 10 min
        CEL->>DB: unprocessed preference feedback
        CEL->>CEL: EloRatingCalculator → update ratings
        CEL->>DB: write ModelMetric
    end
```

### Streaming protocol (the important detail)

The arena does **not** use classic `data: {...}` SSE for completions. The `message.stream`
action returns a `StreamingHttpResponse(content_type='text/plain')` carrying a
**Vercel-AI-SDK-style line protocol**:

| Line prefix | Meaning |
|-------------|---------|
| `a0:"<text>"` | Model **A** content delta (JSON-escaped string) |
| `b0:"<text>"` | Model **B** content delta |
| `ad:{...}` | Model **A** done — `{"finishReason":"stop"}` or error payload |
| `bd:{...}` | Model **B** done |

Both models run **concurrently in background threads** (`stream_model_a`, `stream_model_b`)
that push tagged chunks into a shared `chunk_queue`; the response generator drains the queue
so A and B deltas interleave in one HTTP response. The client
(`useStreamingMessagesCompare.js`) reads `response.body.getReader()`, splits on newlines,
and routes each prefix into Redux `streamingMessages[sessionId][messageId]`, flushing to the
UI on a ~75 ms cadence to avoid render thrash.

The native `data:` SSE path in `message/streaming.py::StreamingManager` and the WebSocket
`message_update` broadcasts exist for **state sync / single-model** paths; the dual-model
battle uses the line protocol above.

---

## 5. Auth & Multi-Tenancy

```mermaid
flowchart TD
    A[App load] --> B{tokens in localStorage?}
    B -- yes --> C[GET /users/me/]
    C -- ok --> D[Authenticated / Anonymous session]
    C -- fail --> E[clear tokens]
    B -- no --> E
    E --> F[POST /auth/anonymous/<br/>→ anonymous_token + JWT]
    F --> D

    D --> G{user signs in}
    G -->|Google popup / Phone OTP| H[Firebase idToken]
    H --> I[POST /auth/google|phone/<br/>X-Anonymous-Token merges guest data]
    I --> D
```

- **Auth backends** (`user/authentication.py`): `FirebaseAuthentication` (JWT carrying Firebase `user_id`, checks active + anon expiry) and `AnonymousTokenAuthentication` (`X-Anonymous-Token` header).
- **Guest limits**: 30-day expiry; capped messages/sessions tracked in `User.preferences`; enforced client-side (`useGuestLimitations`) and server-side (daily message limit via `select_for_update`).
- **Token lifecycle**: axios response interceptor refreshes on 401 via `/auth/refresh/`, queuing concurrent requests; anonymous users (no refresh token) are re-bootstrapped.
- **Tenancy**: `TenantMiddleware` parses the leading `/:slug/` from the path → thread-local context → `db_router` selects that tenant's database. The frontend mirrors this: `TenantRoute` + the axios request interceptor auto-prefix every API call with the active tenant.

---

## 6. Leaderboard & Metrics Pipeline

```mermaid
graph LR
    F[Feedback<br/>preference votes] -->|every 10 min| ELO[update_model_elo_ratings<br/>EloRatingCalculator]
    F -->|daily / weekly| AGG[calculate_model_metrics<br/>wins/losses/ties + avg rating]
    ELO --> MM[(ModelMetric)]
    AGG --> MM
    MM -->|ranked, cached 1h| SVC[ModelMetricsService.get_leaderboard]
    MM -->|published snapshot| LBJSON[(Leaderboard.leaderboard_json<br/>per arena/lang/org)]
    SVC --> EP1[GET /leaderboard/ live]
    LBJSON --> EP2[GET /leaderboard/llm/?org&language]
    EP2 --> UI[Leaderboard UI<br/>rank · score · CI · votes]
```

Two leaderboard surfaces coexist:
- **Live metrics** (`model_metrics`) — ELO + win-rate computed from raw feedback, ranked and cached on read.
- **Published leaderboards** (`leaderboards`) — curated `leaderboard_json` snapshots filtered by `arena_type=llm`, `language`, and `organization` (AI4Bharat / Aquarium), plus a **top-contributors** view (vote counts by user, emails masked). This is what the frontend leaderboard table renders.

---

## 7. Async Jobs (Celery Beat)

| Schedule | Task | Purpose |
|----------|------|---------|
| every 10 min | `update_model_elo_ratings` | Convert new preference votes → ELO deltas |
| daily 00:00 | `calculate_model_metrics(daily)` | Win/loss/tie + avg-rating snapshot |
| Mondays | `calculate_model_metrics(weekly)` | Weekly snapshot |
| daily 02:00 | `cleanup_expired_anonymous_users` | GC expired guests |
| every 6 h | `validate_all_models` | Provider health check, deactivate broken models |
| monthly | `cleanup_old_metrics` | Archive stale metric rows |
| (on demand) | `generate_session_titles`, `export_session_batch` | Auto-title, bulk export |

---

## 8. Cross-Cutting Concerns

- **Rate limiting** (DRF throttles): anon 60/min, user 200/min, AI generation 30/min, auth 10/min; plus a hard per-user daily message cap enforced atomically.
- **Error logging**: frontend posts redacted error envelopes to `/logs/frontend-error/` (fire-and-forget, localStorage-queued offline); backend logs provider errors to GCS.
- **Privacy/consent**: first-message gate (`usePrivacyConsent`) recorded in localStorage + `User.preferences`.
- **Resilience**: WS reconnect with exponential backoff (max 5); stream retry wrapper; 401 refresh queue prevents thundering-herd refreshes.
- **CSRF**: API paths exempted (`ApiCsrfExemptMiddleware`); only `/admin/` and `/accounts/` enforce it.

---

## 9. Tech Stack Summary

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Redux Toolkit, React Query, React Router 7 (Hash), MUI + Tailwind, Framer Motion, Firebase SDK |
| Transport | Axios (REST), Fetch reader (text/plain line stream), native WebSocket (Channels) |
| Backend | Django + DRF, Django Channels (Daphne/ASGI), Celery + Beat |
| Data | PostgreSQL (multi-DB tenant router), Redis (cache/broker/channel layer), Google Cloud Storage |
| Auth | Firebase Auth (Google + Phone) + JWT (simplejwt) + anonymous tokens |
| LLM providers | OpenAI/Azure, Google Gemini, Anthropic, Sarvam/AI4Bharat, Meta, Mistral, DeepSeek, Qwen, … |
