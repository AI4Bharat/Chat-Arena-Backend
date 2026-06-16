# Chat Arena — LLM Arena Design Document

> **Scope.** This document covers the **LLM (text/chat) arena**: anonymous side-by-side
> model comparison, voting, and the leaderboards that result. The TTS, ASR, and OCR arenas
> share the same foundations (sessions → messages → feedback → metrics) and are out of scope
> here.
>
> **Companion:** see [`LLM-Arena-Architecture.md`](./LLM-Arena-Architecture.md) for diagrams.

---

## 1. Purpose & Goals

Chat Arena is a **crowd-sourced LLM evaluation platform** (a LMSYS-Chatbot-Arena-style
system) tuned for **Indic languages** via AI4Bharat. Users chat with two anonymized models
side by side and vote on which response is better; aggregated votes produce ELO-ranked
leaderboards.

**Primary goals**
1. Let anyone (including guests) run a blind A/B battle between two LLMs and vote.
2. Stream both model responses concurrently with low perceived latency.
3. Turn votes into trustworthy ELO rankings, sliced by language and organization.
4. Support multiple deployments (tenants) and multiple modalities on one codebase.

**Non-goals**
- Not a production chat assistant (no long-term agentic memory, tools, or RAG).
- Not a model-hosting platform — all inference is proxied to external providers.

---

## 2. Key Concepts

| Term | Meaning |
|------|---------|
| **Mode** | `direct` (one model), `compare` (user-chosen pair), `random` (server-picked anonymized pair), `academic` (curated benchmark prompts). The arena's signal comes from `compare`/`random`. |
| **Participant** | In a battle, each assistant message is tagged `a` or `b` — the left/right model. |
| **Battle / Turn** | One user prompt → two streamed assistant responses → one optional vote. |
| **Vote / Preference** | A `Feedback` row of type `preference`: Left better, Both good (tie), Both bad, or Right better. |
| **Tenant** | An isolated deployment addressed by a URL slug (`/:tenant/...`), backed by its own database. |
| **Thinking model** | Reasoning models (e.g. o-series) flagged `is_thinking_model` for distinct UI handling. |

---

## 3. Requirements

### Functional
- **FR1** Create a session in any mode; `compare`/`random` anonymize models until after voting context.
- **FR2** Send a prompt (optionally with image/audio/doc attachment and a target Indic language).
- **FR3** Stream both models' responses concurrently into a side-by-side view.
- **FR4** Cast exactly one preference per battle turn; preference is immutable once cast.
- **FR5** Branch / regenerate responses; navigate the message tree.
- **FR6** Persist session history, rename/pin/share/export/duplicate sessions.
- **FR7** Show ELO leaderboards filtered by language and organization, plus top contributors.
- **FR8** Support guest usage with caps, upgradable to a full account without losing history.

### Non-functional
- **NFR1 Latency** — first token visible ASAP; client buffers chunks at ~75 ms to balance smoothness vs. render cost.
- **NFR2 Concurrency** — two providers stream in parallel per turn; one slow/failing model must not block the other.
- **NFR3 Integrity** — votes must map unambiguously to a `(model_a, model_b)` pair and resist double-voting (unique constraint).
- **NFR4 Abuse resistance** — per-tier throttles + hard daily message cap; anonymous expiry.
- **NFR5 Isolation** — tenant data must not leak across databases.
- **NFR6 Resilience** — token refresh, WS reconnect, and stream retry must degrade gracefully.

---

## 4. Architecture Overview

A **React 19 SPA** talks to a **Django + Channels** backend over three channels:

1. **REST (axios)** — sessions, messages, feedback, models, leaderboards.
2. **HTTP text stream (fetch reader)** — the dual-model completion stream.
3. **WebSocket (Channels)** — per-session state sync, typing, broadcasts.

Backend state lives in **PostgreSQL** (per-tenant DBs via a router), with **Redis** for cache,
the Celery broker, and the Channels group layer. **Celery Beat** runs ELO updates and metric
snapshots. Inference is proxied to external **LLM providers**. **Firebase** handles identity;
the backend verifies tokens and also issues anonymous tokens.

See the architecture doc for C4, ER, and sequence diagrams.

---

## 5. Detailed Design

### 5.1 Session & message model

- A `ChatSession` carries `mode`, `model_a`, `model_b`, `session_type=LLM`, sharing fields, and an `expires_at` for guest GC.
- `Message` is a **DAG**: `parent_message_ids` / `child_ids` (GIN-indexed UUID arrays) enable branching and regeneration; `position` orders a thread.
- A battle turn produces **one** user message and **two** assistant messages (`participant a`/`b`), each `status: pending → streaming → success/failed`, with `latency_ms` and token metadata.

### 5.2 The streaming protocol (core design decision)

The completion stream uses a **custom line protocol** over
`StreamingHttpResponse(content_type='text/plain')` rather than classic SSE:

```
a0:"Hello"          ← model A delta (JSON-escaped)
b0:"Bonjour"        ← model B delta
a0:" there"
ad:{"finishReason":"stop"}   ← model A done
bd:{"finishReason":"stop"}   ← model B done
```

**Server side** (`message/views.py::stream`): `stream_model_a()` and `stream_model_b()` run in
**separate threads**, each consuming its provider's streaming generator from
`ai_model/llm_interactions.py` and pushing tagged chunks `('a'|'b', line)` into a shared
`chunk_queue`. The response generator drains the queue, so A and B deltas **interleave** in a
single HTTP response. A failure in one model emits an error `ad`/`bd` payload without aborting
the other.

**Client side** (`useStreamingMessagesCompare.js`): reads `response.body.getReader()`, splits on
`\n`, dispatches `a0`/`b0` into `streamingMessages[sessionId][messageId]`, and flushes to React on
a ~75 ms timer (NFR1). `ad`/`bd` finalize each side and move content into the committed
`messages` array.

> **Why a line protocol instead of SSE?** It is a Vercel-AI-SDK-compatible framing that cleanly
> multiplexes **two** streams over one connection with per-model done/error markers, and avoids
> SSE's `data:`/event overhead per chunk. The SSE `StreamingManager` and WS `message_update`
> broadcasts remain for single-model and state-sync paths.

### 5.3 Provider abstraction

`ai_model/llm_interactions.py` dispatches on model code to per-provider handlers
(`get_gpt4_output`, `get_gemini_output`, `get_sarvam_output`, …), each returning a generator of
text chunks. `AIModel.config` holds endpoints/params; `supports_streaming`, `is_thinking_model`,
and `random_only` drive behavior. New providers are added by registering a handler + an `AIModel`
row — no schema change.

### 5.4 Voting → ELO pipeline

1. Client POSTs `/feedback/` with `feedback_type=preference`, `preferred_model_ids`, and
   `tracking_data` (turn timestamps: prompt sent, each response completed, vote submitted).
2. Feedback is stored once per `(user, session, message, feedback_type)` (unique constraint →
   double-vote protection, NFR3) and mirrored onto `Message.feedback` for fast render.
3. **Celery (every 10 min)** `update_model_elo_ratings` reads unprocessed preferences, resolves
   `a_wins | b_wins | tie`, applies `EloRatingCalculator`, and marks each processed.
4. **Daily/weekly** `calculate_model_metrics` snapshots wins/losses/ties + average rating into
   `ModelMetric` per category/period.
5. Leaderboards are served two ways: **live** (`ModelMetricsService.get_leaderboard`, ranked +
   cached 1 h) and **published** (`Leaderboard.leaderboard_json` snapshots filtered by
   `arena_type=llm`, language, organization), the latter being what the UI table renders.

### 5.5 Auth & guest model

- Firebase (Google popup, Phone OTP) yields an idToken exchanged at `/auth/{google,phone}/` for
  app JWTs; sending the `X-Anonymous-Token` header **merges** prior guest history into the new
  account.
- Guests bootstrap via `/auth/anonymous/`; identity (token + `message_count`/`session_count`)
  lives in `User.preferences`. Limits enforced client-side (`useGuestLimitations`) and
  server-side (daily cap via `select_for_update`); guests expire after 30 days.
- `FirebaseAuthentication` validates JWT + active + non-expired; `AnonymousTokenAuthentication`
  is the header fallback.

### 5.6 Multi-tenancy

`TenantMiddleware` reads the leading URL slug → thread-local context → `db_router` selects the
tenant DB (NFR5). The SPA mirrors this with `TenantRoute` and an axios request interceptor that
auto-prefixes every call, so the same components serve global and tenant-scoped routes.

### 5.7 Real-time channel

`ChatSessionConsumer` (`ws/chat/session/{id}/`) authenticates via query-string token, verifies
ownership (or public share), joins group `session_{id}`, and relays `message_update`,
`session_update`, `typing_indicator`, and `ping/pong`. Reconnect uses exponential backoff
(max 5 attempts), with a single token-refresh attempt on auth-close codes (NFR6).

---

## 6. Key Data Flows (summary)

| Flow | Path |
|------|------|
| Start battle | `POST /sessions/` → (random: server picks pair) → open WS → `POST /messages/stream/` |
| Stream | threads → `chunk_queue` → `a0/b0/ad/bd` lines → Redux `streamingMessages` → UI (75 ms) |
| Vote | `POST /feedback/` (preference + tracking_data) → mirror on message → session vote counts |
| Rank | Celery ELO (10 min) + metric snapshots (daily) → `ModelMetric` / published `Leaderboard` |
| Leaderboard view | `GET /leaderboard/llm/?org&language` → React Query cache → table |

---

## 7. Design Decisions & Trade-offs

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Custom `a0/b0` line protocol over text/plain | Multiplex two streams + per-model done/error in one connection; AI-SDK compatible | Non-standard; bespoke client parser instead of `EventSource` |
| Threads + shared queue for dual streaming | True parallel inference; one model's stall can't block the other | Thread-per-request cost; relies on Daphne worker capacity |
| Redux for stream state, React Query for read caches | Hot streaming buffer needs fine-grained local updates; leaderboards/models are cacheable reads | Two state systems to reason about |
| Anonymous identity in `User.preferences` | Guests need no extra tables; one-shot merge on sign-up | Preferences JSON becomes load-bearing |
| ELO via periodic Celery batch (10 min) | Decouples voting latency from ranking compute; idempotent via processed flag | Rankings lag votes by up to ~10 min |
| Two leaderboard surfaces (live + published) | Live for freshness, published JSON for curated, language/org-sliced presentation | Possible divergence; must keep snapshots fresh |
| HashRouter + URL-slug tenancy | Multi-tenant without server-side route config; static-host friendly | `#` URLs; tenant parsing duplicated client+server |
| Message DAG (parent/child arrays) | Branching + regeneration without a separate edges table for the common case | Array integrity maintained in app code; `MessageRelation` exists for explicit edges |

---

## 8. Failure Modes & Mitigations

| Failure | Mitigation |
|---------|-----------|
| One provider errors/times out mid-battle | Per-model `ad`/`bd` error payload; other model continues; message marked `failed` with `failure_reason` |
| Access token expires mid-session | axios 401 interceptor refreshes via `/auth/refresh/`, queues concurrent requests; anon users re-bootstrap |
| WebSocket drops | Exponential-backoff reconnect (≤5), state re-sync via `request_state` / `session_state` |
| Vote double-submit | DB unique `(user, session, message, feedback_type)`; UI locks after first vote |
| Guest abuse / cost runaway | DRF throttles + atomic daily message cap + 30-day anon expiry |
| Broken model in registry | `validate_all_models` (6 h) deactivates failing models so they leave rotation |
| Frontend error visibility | Redacted envelopes to `/logs/frontend-error/`, localStorage-queued when offline |

---

## 9. Security & Privacy

- API CSRF-exempt by design (token auth); CSRF enforced only on `/admin/`, `/accounts/`.
- Sensitive fields (passwords, tokens, api keys) redacted before error logging.
- Contributor leaderboard masks user emails.
- First-message privacy consent gate, persisted client + server side.
- Per-tenant DB isolation via router; relations restricted to same database.

---

## 10. Future / Open Considerations

- **Ranking freshness** — optionally stream ELO deltas instead of 10-min batches for live boards.
- **Provider resilience** — circuit-breaker per provider beyond the 6-hourly health check.
- **Stream backpressure** — the thread+queue model could adopt async generators end-to-end to reduce worker pressure under load.
- **Vote quality** — spam/Sybil detection on preferences before they enter ELO.
- **Snapshot drift** — reconcile published `Leaderboard` JSON against live `ModelMetric` on a schedule.
