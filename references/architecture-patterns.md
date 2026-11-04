# Architecture pattern catalog

A fixed, curated list of system-design and code-level patterns. Agents PICK from
this catalog; they never name a pattern outside it. Sources: Azure Cloud Design
Patterns, microservices.io, Fowler (PoEAA, bliki), GoF, Cockburn.

## Rules
- Entry format: `### <id> — <Name>: <what it solves>`, then seven bullets in order:
  Signals, Not when, Cost, Pairs with, Conflicts with, Overuse smell, Simpler
  alternative. Ids are stable — designs and ADRs cite them; never rename one.
- "Not when" and "Simpler alternative" are BINDING: a pick that hits a Not when
  line is rejected, and its Simpler alternative must be tried first.
- When no Signals line matches, pick nothing — a design with no pattern is
  valid. `Simpler alternative: none` means the cheaper option is not using the
  pattern at all.
- Conflicts with: alternatives for the same concern at the same boundary — never
  apply both to one boundary.
- Each pick cites the user-sourced NFR or symptom that matched its Signals line,
  and why its Simpler alternative lost.
- At most 5 picks; zero is valid.
- Project-local additions live in the project's
  `docs/architecture/catalog-additions.md`, in this same format.
- If no entry fits, say so and draft a new entry in this format for the user to
  approve. Never use an unapproved pattern.
- Briefing an architect: give the full index (`grep '^### '` of this catalog and
  of the project's catalog-additions.md), plus the full text of the candidates —
  entries whose Signals match an NFR or symptom in the criteria or research — and
  of each candidate's Simpler-alternative ids, and this Rules section. The
  architect may cite any index id; the orchestrator checks a cited id it did not
  expand against the full entry (Signals, Not when) before it reaches the options
  table.

## Structure

### layered — Layered architecture: separates presentation, domain and data access
- Signals: a single deployable app with one team; the code mixes UI, rules and SQL in the same functions.
- Not when: the domain is a thin CRUD wrapper where layers only forward calls.
- Cost: pass-through code between layers; changes to one field touch every layer.
- Pairs with: `service-layer`, `repository`
- Conflicts with: `microservices`
- Overuse smell: layers that only delegate, adding files without adding rules.
- Simpler alternative: none

### modular-monolith — Modular monolith: one deployable split into modules with enforced boundaries
- Signals: 2-3 teams in one codebase stepping on each other; boundaries are known but independent scaling is not needed.
- Not when: one small team and a small domain — plain `layered` is enough.
- Cost: boundary enforcement (lint rules, module APIs); one shared deploy and database.
- Pairs with: `hexagonal`, `anti-corruption-layer`, `strangler-fig`
- Conflicts with: `microservices`
- Overuse smell: modules that call each other's internals or share tables freely.
- Simpler alternative: `layered`

### hexagonal — Hexagonal (ports & adapters): isolates the domain from frameworks and I/O
- Signals: the domain must run against 2+ production adapters per port (DB, queue, UI; test doubles don't count); vendor swap is a stated NFR.
- Not when: a single adapter per port with no planned swap; CRUD with little domain logic.
- Cost: an interface per port and mapping code at every boundary.
- Pairs with: `adapter`, `dependency-injection`, `repository`
- Conflicts with: none
- Overuse smell: ports with exactly one adapter and no test double using them.
- Simpler alternative: `layered`

### microservices — Microservices: independently deployable services per business capability
- Signals: ≥ 3 teams needing independent deploys; components with measurably different scaling or availability needs.
- Not when: fewer than ~3 teams; no independent scaling need; domain boundaries still unclear; no ops capacity for distributed tracing and CI per service.
- Cost: network calls, distributed data consistency, per-service CI/CD, observability, and on-call burden.
- Pairs with: `database-per-service`, `api-gateway`, `saga`, `circuit-breaker`
- Conflicts with: `layered`, `modular-monolith`
- Overuse smell: services that must deploy together, or one request fanning out to many services synchronously.
- Simpler alternative: `modular-monolith`

### backends-for-frontends — Backends for frontends: one backend per client type
- Signals: 2+ client types (web, mobile, partner) with diverging payloads or release cadence; one client's needs keep breaking another's.
- Not when: a single client, or clients that consume the same shapes.
- Cost: one more service per client; duplicated logic across BFFs.
- Pairs with: `api-gateway`, `microservices`
- Conflicts with: none
- Overuse smell: BFFs holding business rules instead of shaping responses.
- Simpler alternative: `api-gateway`

### api-gateway — API gateway: single entry point for routing, aggregation and offloading (auth, TLS, rate limits)
- Signals: clients call ≥ 3 backend services directly; cross-cutting concerns (auth, TLS, throttling) duplicated per service.
- Not when: one backend service; a reverse proxy already covers routing.
- Cost: an extra hop and a component that is a single point of failure if not made highly available.
- Pairs with: `microservices`, `rate-limiting`, `federated-identity`
- Conflicts with: none
- Overuse smell: business logic and orchestration living in the gateway.
- Simpler alternative: none

## Data

### database-per-service — Database per service (vs shared database): each service owns its data
- Signals: services must deploy and change schema independently; one service's load degrades others via the shared DB.
- Not when: a monolith or modular monolith; queries need cross-entity ACID transactions that cannot be split.
- Cost: no cross-service joins or transactions; data duplication and eventual consistency.
- Pairs with: `microservices`, `saga`, `transactional-outbox`, `materialized-view`
- Conflicts with: none
- Overuse smell: services reading each other's databases "just this once".
- Simpler alternative: `modular-monolith`

### cache-aside — Cache-aside: load data into a cache on demand
- Signals: p95 read latency over budget AND read:write > 10:1 on the same keys; a hot data store under read load.
- Not when: data must be strongly consistent on every read; writes dominate; latency already within budget.
- Cost: a cache cluster to run; stale reads; invalidation logic on every write path.
- Pairs with: `static-content-cdn`, `repository`
- Conflicts with: none
- Overuse smell: caching values that are cheap to compute or rarely re-read.
- Simpler alternative: none

### materialized-view — Materialized view: precompute a read-optimised projection
- Signals: a query joins or aggregates across many records/stores and misses its latency budget; the read shape differs from the write shape.
- Not when: the source data changes faster than the view can be refreshed; a DB index fixes the query.
- Cost: refresh jobs or event handlers; stale data between refreshes; storage.
- Pairs with: `cqrs`, `event-sourcing`, `database-per-service`
- Conflicts with: none
- Overuse smell: a view per screen, each refreshed separately.
- Simpler alternative: `cache-aside`

### cqrs — CQRS: separate models for writes (commands) and reads (queries)
- Signals: read and write loads differ by > 10× and need separate scaling; read models need shapes the write model cannot serve.
- Not when: simple CRUD; one team, one model that serves both sides acceptably.
- Cost: two models to keep in sync; eventual consistency visible to users.
- Pairs with: `event-sourcing`, `materialized-view`
- Conflicts with: none
- Overuse smell: CQRS across a whole system instead of the one bounded context that needs it.
- Simpler alternative: `materialized-view`

### event-sourcing — Event sourcing: store state as an append-only log of events
- Signals: a full audit trail of every change is a stated requirement; state must be rebuilt as of any past point in time.
- Not when: no audit or temporal-query need; an audit/history table meets the need; the team lacks experience with event versioning; simple CRUD.
- Cost: event schema versioning, replay tooling, snapshots; reads need projections.
- Pairs with: `cqrs`, `materialized-view`, `publish-subscribe`
- Conflicts with: none
- Overuse smell: events named after CRUD ops (`RowUpdated`) rather than domain facts.
- Simpler alternative: none

### sharding — Sharding: split a data store horizontally by a partition key
- Signals: a single node's storage or write throughput is measured near its ceiling after vertical scaling and indexing.
- Not when: data fits one node with headroom; queries routinely span all partitions.
- Cost: shard routing, rebalancing, cross-shard queries and transactions lost.
- Pairs with: `database-per-service`
- Conflicts with: none
- Overuse smell: sharding before trying read replicas, indexes or a bigger instance.
- Simpler alternative: none

### transactional-outbox — Transactional outbox: write the event in the same DB transaction as the state change
- Signals: a state change must reliably publish a message; lost or phantom events have been observed (dual write).
- Not when: no message broker in the flow; losing an occasional notification is acceptable.
- Cost: an outbox table and a relay process; at-least-once delivery downstream.
- Pairs with: `idempotent-consumer`, `publish-subscribe`, `saga`
- Conflicts with: none
- Overuse smell: outbox for messages nobody needs reliably.
- Simpler alternative: none

### idempotent-consumer — Idempotent consumer: process a duplicated message safely
- Signals: delivery is at-least-once (most brokers, retries, outbox); duplicate side effects observed or unacceptable.
- Not when: the handler is naturally idempotent (pure upsert by key).
- Cost: a processed-message store or dedup key; storage cleanup.
- Pairs with: `transactional-outbox`, `retry-with-backoff`, `queue-load-leveling`
- Conflicts with: none
- Overuse smell: a dedup table in front of an operation that is already an upsert.
- Simpler alternative: none

## Messaging

### publish-subscribe — Publish-subscribe: broadcast events to any number of subscribers
- Signals: one event must trigger work in ≥ 2 independent consumers; the producer must not know its consumers.
- Not when: exactly one consumer that needs an answer; strict ordering across consumers is required.
- Cost: a broker to run; harder tracing; eventual consistency.
- Pairs with: `transactional-outbox`, `idempotent-consumer`, `observer`
- Conflicts with: none
- Overuse smell: events used as hidden remote procedure calls awaiting replies.
- Simpler alternative: `observer`

### queue-load-leveling — Queue-based load leveling (+ competing consumers): buffer bursts through a queue
- Signals: traffic bursts exceed the downstream's measured capacity; work can finish later than the request.
- Not when: the caller needs the result synchronously within its latency budget.
- Cost: a queue to run; delayed results; backlog monitoring and dead-letter handling.
- Pairs with: `idempotent-consumer`, `async-request-reply`, `rate-limiting`
- Conflicts with: none
- Overuse smell: a queue between two in-process components.
- Simpler alternative: `rate-limiting`

### async-request-reply — Asynchronous request-reply: accept now, deliver the result later via polling or callback
- Signals: an operation takes longer than the client or gateway timeout (e.g. > 30 s); clients can poll or receive a callback.
- Not when: the work completes within the latency budget synchronously.
- Cost: a status endpoint, job storage, and client polling logic.
- Pairs with: `queue-load-leveling`
- Conflicts with: none
- Overuse smell: async endpoints for calls that return in milliseconds.
- Simpler alternative: none

### saga — Saga (orchestration vs choreography): a cross-service transaction as local steps with compensations
- Signals: one business transaction spans ≥ 2 services with their own databases; partial failure must be undone.
- Not when: all data lives in one database — use a local transaction (`unit-of-work`).
- Cost: compensating actions per step; intermediate states visible; orchestrator or event-flow debugging.
- Pairs with: `database-per-service`, `transactional-outbox`, `idempotent-consumer`
- Conflicts with: none
- Overuse smell: choreography chains so long nobody can tell the flow; compensations that cannot actually undo.
- Simpler alternative: `unit-of-work`

### anti-corruption-layer — Anti-corruption layer: translate between your model and a legacy or foreign one
- Signals: integrating a legacy or third-party system whose model would leak into yours; migrating off that system.
- Not when: the external model already matches yours; a one-field mapping.
- Cost: a translation layer to maintain and test; added latency if a separate service.
- Pairs with: `strangler-fig`, `adapter`, `facade`
- Conflicts with: none
- Overuse smell: an ACL between two of your own modules that share a model.
- Simpler alternative: `adapter`

## Resilience

### retry-with-backoff — Retry with backoff: timeout + exponential backoff + jitter for transient faults
- Signals: a remote call fails transiently (timeouts, 503, throttling) at a measurable rate; the operation is idempotent.
- Not when: the operation is not idempotent; the failure is permanent (4xx other than 408/429); the downstream is already overloaded.
- Cost: added latency on failure; retry storms without jitter and a cap.
- Pairs with: `circuit-breaker`, `idempotent-consumer`
- Conflicts with: none
- Overuse smell: retries stacked at every layer, multiplying load.
- Simpler alternative: none

### circuit-breaker — Circuit breaker: stop calling a failing dependency for a while
- Signals: downstream timeouts or error rate spike and callers pile up threads/connections waiting on it.
- Not when: a single in-process call; the dependency is local and fails fast already.
- Cost: state per dependency; tuning thresholds; a fallback behaviour to define.
- Pairs with: `retry-with-backoff`, `bulkhead`, `health-endpoint`
- Conflicts with: none
- Overuse smell: breakers with untested fallbacks, or thresholds nobody tuned.
- Simpler alternative: none

### bulkhead — Bulkhead: isolate resources per dependency or tenant
- Signals: one slow dependency or noisy tenant exhausts a shared pool and takes down unrelated features.
- Not when: one dependency; the shared pool has never saturated.
- Cost: pools sized per partition; idle capacity.
- Pairs with: `circuit-breaker`, `rate-limiting`
- Conflicts with: none
- Overuse smell: a pool per call site, each too small to absorb normal bursts.
- Simpler alternative: `circuit-breaker`

### rate-limiting — Rate limiting (throttling): cap request rate per client or overall
- Signals: abusive or bursty clients degrade service for others; a downstream quota must be respected.
- Not when: traffic is internal and well-behaved with capacity headroom.
- Cost: limit state (often a shared store); rejected requests clients must handle.
- Pairs with: `api-gateway`, `queue-load-leveling`, `bulkhead`
- Conflicts with: none
- Overuse smell: limits so low that legitimate traffic gets 429s.
- Simpler alternative: none

### health-endpoint — Health endpoint monitoring: expose liveness/readiness for orchestrators and monitors
- Signals: an orchestrator or load balancer routes traffic to instances; failures need detecting without user reports.
- Not when: a CLI or batch job with no long-running process.
- Cost: an endpoint and its checks; deep checks can cascade failures.
- Pairs with: `circuit-breaker`
- Conflicts with: none
- Overuse smell: a readiness check that fails when any downstream blips.
- Simpler alternative: none

## Edge & security

### static-content-cdn — Static content hosting + CDN: serve static assets from storage and edge caches
- Signals: static assets are a large share of bandwidth or latency for distant users.
- Not when: content is per-user or changes on every request.
- Cost: cache invalidation on deploy; another vendor.
- Pairs with: `cache-aside`, `valet-key`
- Conflicts with: none
- Overuse smell: putting authenticated per-user responses behind the CDN.
- Simpler alternative: none

### valet-key — Valet key (presigned URLs): let clients access storage directly with a scoped token
- Signals: large uploads/downloads proxied through app servers consume their bandwidth or memory.
- Not when: files are small and rare; every access needs app-side inspection.
- Cost: token scoping and expiry; upload validation moves to post-processing.
- Pairs with: `static-content-cdn`, `federated-identity`
- Conflicts with: none
- Overuse smell: long-lived or over-scoped presigned URLs.
- Simpler alternative: none

### federated-identity — Federated identity: delegate authentication to an identity provider
- Signals: SSO across apps is required; enterprise customers bring their own IdP; storing passwords is unwanted.
- Not when: a single internal tool with no auth requirement beyond the platform's.
- Cost: IdP dependency and integration (OIDC/SAML); token validation and key rotation.
- Pairs with: `api-gateway`, `valet-key`
- Conflicts with: none
- Overuse smell: custom token formats layered on top of the IdP's.
- Simpler alternative: none

## Migration

### strangler-fig — Strangler fig: replace a legacy system piece by piece behind a routing facade
- Signals: a legacy system must be replaced while it keeps serving traffic; a big-bang rewrite is too risky.
- Not when: the system is small enough to replace in one release; requests cannot be intercepted.
- Cost: running old and new side by side; routing and data sync during the migration.
- Pairs with: `anti-corruption-layer`, `feature-toggles`, `facade`
- Conflicts with: none
- Overuse smell: a migration with no end date where both systems live forever.
- Simpler alternative: `branch-by-abstraction`

### parallel-change — Parallel change (expand-contract): change an interface or schema in backward-compatible steps
- Signals: a schema or API change with consumers that cannot deploy in lockstep; zero-downtime deploys required.
- Not when: the only consumer deploys in the same release.
- Cost: dual writes/reads during transition; a cleanup step that must not be forgotten.
- Pairs with: `feature-toggles`
- Conflicts with: none
- Overuse smell: expand steps that never get their contract step.
- Simpler alternative: none

### feature-toggles — Feature toggles: ship code dark and switch behaviour at runtime
- Signals: unfinished work must merge to trunk; a rollout must be gradual or instantly reversible.
- Not when: the change is small and ships complete; nobody owns toggle cleanup.
- Cost: combinatorial test paths; toggle debt; a toggle store.
- Pairs with: `parallel-change`, `branch-by-abstraction`, `strangler-fig`
- Conflicts with: none
- Overuse smell: toggles older than a few releases, or toggles nested in toggles.
- Simpler alternative: none

### branch-by-abstraction — Branch by abstraction: swap an implementation behind an interface on trunk
- Signals: a large internal component must be replaced over many commits without a long-lived branch.
- Not when: the replacement fits in one small change.
- Cost: a temporary abstraction and two implementations during the swap.
- Pairs with: `feature-toggles`, `strategy`, `dependency-injection`
- Conflicts with: none
- Overuse smell: the abstraction outliving the migration with one implementation.
- Simpler alternative: none

## Code — creational

### factory-method — Factory method: defer which concrete class to create to a subclass or function
- Signals: creation logic picks among ≥ 2 concrete types by input, and that choice is duplicated at call sites.
- Not when: one concrete type; a plain constructor call is clear.
- Cost: an extra indirection to read.
- Pairs with: `strategy`, `dependency-injection`
- Conflicts with: none
- Overuse smell: factories that only call one constructor.
- Simpler alternative: none

### builder — Builder: construct a complex object step by step
- Signals: a constructor takes many optional parameters, or construction needs validation across fields.
- Not when: ≤ 3 parameters; the language has named/default arguments that cover it.
- Cost: a parallel builder class to maintain.
- Pairs with: `factory-method`
- Conflicts with: none
- Overuse smell: builders for value objects with two fields.
- Simpler alternative: none

### dependency-injection — Dependency injection: pass collaborators in instead of creating them inside
- Signals: a class must be tested without its real I/O; collaborators vary by environment.
- Not when: a pure function with no collaborators.
- Cost: wiring code or a container; indirection when reading.
- Pairs with: `hexagonal`, `repository`, `strategy`
- Conflicts with: none
- Overuse smell: a DI container for a script; Singletons used as service locators.
- Simpler alternative: none

## Code — structural

### adapter — Adapter: make an existing interface fit the one your code expects
- Signals: a third-party or legacy API's shape differs from the interface your code depends on.
- Not when: you own both sides and can change one to match.
- Cost: a thin wrapper to maintain as the wrapped API changes.
- Pairs with: `hexagonal`, `anti-corruption-layer`
- Conflicts with: none
- Overuse smell: adapters that rename methods and nothing else, for code you own.
- Simpler alternative: none

### facade — Facade: one simple interface over a complex subsystem
- Signals: callers repeat the same multi-step sequence against a subsystem.
- Not when: callers need the subsystem's full flexibility.
- Cost: a layer that can grow into a god object.
- Pairs with: `service-layer`, `strangler-fig`
- Conflicts with: none
- Overuse smell: a facade that exposes every method of what it hides.
- Simpler alternative: none

### decorator — Decorator: add behaviour to an object by wrapping it
- Signals: cross-cutting behaviour (caching, logging, retry) must be combined per instance without subclass explosion.
- Not when: one fixed combination — put it in the class.
- Cost: deep wrapper stacks are hard to debug.
- Pairs with: `chain-of-responsibility`, `retry-with-backoff`
- Conflicts with: none
- Overuse smell: wrappers whose order matters but is not documented.
- Simpler alternative: none

## Code — behavioral

### strategy — Strategy: choose an algorithm at runtime behind one interface
- Signals: the same switch/if-chain on a type or mode appears in ≥ 2 places; algorithms vary by config or input.
- Not when: two branches in one place that rarely change.
- Cost: one class or function per variant.
- Pairs with: `factory-method`, `dependency-injection`
- Conflicts with: none
- Overuse smell: a strategy interface with one implementation.
- Simpler alternative: none

### observer — Observer: notify in-process subscribers when state changes
- Signals: one change must trigger ≥ 2 independent in-process reactions the source should not know about.
- Not when: one fixed reaction — call it directly.
- Cost: hidden control flow; leaks from unremoved subscribers.
- Pairs with: `publish-subscribe`
- Conflicts with: none
- Overuse smell: chains of observers triggering observers.
- Simpler alternative: none

### command — Command: represent a request as an object
- Signals: operations must be queued, logged, undone or retried as values.
- Not when: a direct call with no queue, undo or audit need.
- Cost: a class per operation.
- Pairs with: `queue-load-leveling`, `cqrs`
- Conflicts with: none
- Overuse smell: commands that are only renamed method calls.
- Simpler alternative: none

### state — State: move state-dependent behaviour into one object per state
- Signals: an entity has ≥ 3 states with transition rules, and switches on its status are spread across methods.
- Not when: two states or a simple flag.
- Cost: a class per state; transitions spread across classes.
- Pairs with: `strategy`
- Conflicts with: none
- Overuse smell: state classes that all share the same behaviour.
- Simpler alternative: none

### chain-of-responsibility — Chain of responsibility (middleware): pass a request along a chain of handlers
- Signals: a request needs an ordered, configurable pipeline of independent steps (auth, validation, logging).
- Not when: a fixed sequence of two steps.
- Cost: order-dependent behaviour; harder tracing of who handled what.
- Pairs with: `decorator`
- Conflicts with: none
- Overuse smell: handlers that depend on each other's side effects.
- Simpler alternative: none

## Code — application

### repository — Repository: collection-like interface over persistence for domain objects
- Signals: domain logic must be tested without the database; query logic is duplicated across services.
- Not when: an ORM already provides it and you would only wrap it one-to-one.
- Cost: an interface and an implementation per aggregate.
- Pairs with: `unit-of-work`, `service-layer`, `hexagonal`
- Conflicts with: none
- Overuse smell: generic `Repository<T>` that re-exposes the ORM.
- Simpler alternative: none

### unit-of-work — Unit of work: track changes and commit them in one transaction
- Signals: one business operation writes several aggregates that must commit or roll back together.
- Not when: each operation writes a single row; data spans services (use `saga`).
- Cost: change tracking; long transactions if scoped badly.
- Pairs with: `repository`, `service-layer`
- Conflicts with: none
- Overuse smell: hand-rolled unit of work on top of an ORM session that already is one.
- Simpler alternative: none

### service-layer — Service layer: application operations as one boundary over the domain
- Signals: the same use case is invoked from ≥ 2 entry points (HTTP, CLI, jobs) and its orchestration is duplicated.
- Not when: one entry point with trivial logic.
- Cost: a layer that can become anemic pass-through.
- Pairs with: `repository`, `unit-of-work`, `layered`
- Conflicts with: none
- Overuse smell: service methods that only call one repository method.
- Simpler alternative: none

### active-record-vs-data-mapper — Active record vs data mapper: objects persist themselves, or a mapper persists them
- Signals: choosing how domain objects reach the DB; active record when the domain mirrors tables, data mapper when it does not or when the design uses `hexagonal`, `cqrs` or `event-sourcing`.
- Not when: no persistence decision is open — keep the framework's default.
- Cost: active record couples domain to schema; data mapper adds mapping code.
- Pairs with: `repository`, `unit-of-work`
- Conflicts with: none
- Overuse smell: active record objects carrying complex domain rules across tables.
- Simpler alternative: none
