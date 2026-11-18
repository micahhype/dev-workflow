# Throwaway UI prototype

Read by `/dev-workflow:feature` Stage 3.

**Prototype only when what the user will SEE is the uncertain part.** For a
new screen or page whose layout nobody has pinned down, build a throwaway
static mock (one HTML file, fake data, in the feature dir — never in the
source tree) and show it before the plan checkpoint. It is a question to the
user, not a first draft: it is deleted once the plan is approved, and no
phase builds on it. Anything else — an endpoint, a job, a refactor — gets no
prototype; `## Structure` on paper is enough.
