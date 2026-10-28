# Agent Development Guide

Repository-wide programming guidance for StudySpot. Explicit user instructions override this file.

## Working Approach

- Read the relevant code and existing patterns before editing.
- Prefer the smallest correct change that fulfills the request. Keep changes focused and reviewable.
- Evaluate code in this order: correctness, clarity, local conventions, useful deduplication, and meaningful tests.
- Challenge assumptions when evidence warrants it; do not require a ceremonial design or approval checkpoint for ordinary work.
- Clarify material ambiguity, but resolve routine implementation choices using the codebase and the user's intent.
- Preserve observable contracts: response shapes, errors, ordering, defaults, and persisted values matter as much as signatures.
- Avoid speculative abstractions, unrelated refactors, new dependencies without a concrete need, and opportunistic upgrades.
- Follow `CONTRIBUTING.md`, the `justfile`, and package configuration for project workflow and commands.

## Python with Rust and OCaml Discipline

Use Rust's explicit ownership and error handling and OCaml's precise data modeling and functional composition while remaining idiomatic Python. Do not recreate their runtimes, borrow checkers, or entire type systems.

### Precise Types and Boundary Parsing

- Parse external input once into meaningful domain values or reject it with a specific error. Preserve the validated facts in the returned representation.
- Make illegal states hard to represent. Prefer enums, small value objects, and unions of distinct variants over magic strings, ambiguous booleans, and bags of optional fields.
- Use frozen dataclasses for immutable internal records where useful. Remember that `frozen=True` does not freeze nested lists or dictionaries.
- Use discriminated unions and `match` when they clarify genuinely different cases. Use `assert_never` for exhaustiveness where supported by the type checker; never silently turn an impossible state into a valid default.
- Use `None` only for meaningful absence. Do not conflate missing, empty, invalid, and failed values.
- Prefer precise annotations, `TypedDict` for structured mappings, and `Protocol` for behavioral contracts over `Any` and `dict[str, Any]`.
- Use existing Django models and DRF serializers at their established boundaries. Add internal value types only when they preserve useful invariants; do not duplicate every model or introduce another validation library by default.
- Static annotations do not validate runtime input. Keep explicit parsing at untrusted boundaries rather than repeating defensive checks throughout trusted code.

### Functional Core and Explicit Effects

- Prefer small, deterministic functions that transform explicit inputs into explicit outputs.
- Keep I/O and mutation visible at the edges of computation. Separate pure rules from database, filesystem, clock, and network access when it makes the code simpler to reason about.
- Prefer immutable values and returning new results over mutating caller-owned inputs. Use local mutation when it is clearer or materially more efficient.
- Make ownership and aliasing explicit: document intentional in-place mutation and avoid surprising callers through shared mutable objects.
- Pass dependencies explicitly when needed; avoid hidden global state and elaborate dependency-injection frameworks.
- Prefer composition over inheritance, except for real subtype relationships and established Django/DRF extension points.
- Use Python's protocols, iterators, generators, and built-ins instead of inventing parallel interfaces.

### Explicit Errors and Resource Lifetimes

- Use specific exceptions with descriptive messages for failures. Catch errors only where they can be handled or translated meaningfully.
- Preserve causes with `raise ... from exc` when translating exceptions.
- Model expected alternatives as typed values when callers must branch on them. Do not introduce a generic `Result`/`Option` framework just to imitate another language.
- Avoid broad `except Exception`, swallowed errors, and silent fallback values that hide failure.
- Do not use production `assert` for input validation or authorization; assertions can be disabled.
- Acquire and release resources with context managers and `try/finally` where needed.
- Make partial mutation on failure explicit; prefer leaving inputs unchanged when an operation fails.
- For concurrent code, make shared-state ownership, synchronization, cancellation, and resource bounds clear. Do not add async or parallelism without a concrete benefit.

## Clarity and Python Idioms

- Keep functions and classes cohesive. Extract helpers when they reduce complexity, not just to shorten a function.
- Prefer deep modules with small interfaces and descriptive names. Keep behavior near the data when that improves the model.
- Document public contracts and non-obvious invariants. Comments explain why; avoid docstrings that merely repeat the function name.
- Keep imports at the top except for justified lazy imports, circular-import avoidance, or `TYPE_CHECKING` guards.
- Prefer `collections.abc` abstractions in parameter annotations when callers need not supply a particular concrete container.
- Use direct iteration, `enumerate`, `zip`, and `dict.items` instead of unnecessary indexing.
- Use comprehensions, `all`, and `any` when clearer than a loop; avoid dense nested expressions.
- Prefer f-strings for ordinary formatting and named constants for repeated meaningful values.
- Choose tuples for fixed immutable sequences, lists for mutable sequences, and named records when positional fields become unclear.
- Never use mutable default arguments. Use `is` and `is not` for singleton identity checks such as `None`.
- Be explicit about encodings and text-versus-bytes boundaries.
- Preserve local logging and error conventions. Never log credentials or secrets.
- Keep lint and type checks in the development loop. Use narrow, justified suppressions rather than blanket ignores or unchecked casts.
- Follow the repository's configured Ruff and ty checks; do not impose unrelated mypy settings or a different lint ruleset.

## Performance

- Choose algorithms and data structures based on the workload. Consider complexity, allocations, copies, serialization, and database round trips.
- Avoid repeated queries and unnecessary materialization; use batching, appropriate ORM queries, and iteration when they reduce actual work.
- Measure before making performance-driven rewrites. Document the reason for non-obvious optimizations.
- Keep loops, recursion, retries, and concurrent work bounded by the task or explicit limits.
- Favor clear, predictable code over clever micro-optimizations. Concise code should reduce cognitive load, not compress it into fewer lines.

## Focused Verification

- Test observable behavior and important invariants, not private helpers or implementation structure.
- Add the smallest set of tests that provides confidence in changed behavior: the success path, meaningful failures, and relevant boundary cases.
- Choose unit, integration, or end-to-end tests according to the risk. Do not duplicate the same assertion across every layer or add tests just to inflate coverage.
- Prefer integration tests when the meaningful behavior depends on Django, database constraints, permissions, or transactions. Use the project's real Postgres test setup when those semantics matter.
- Follow nearby test organization and existing tooling. Python uses pytest; frontend tests use the existing Vitest setup.
- Prefer fixtures, direct assertions, parametrization for related cases, and deterministic data. Mock external boundaries rather than the behavior being tested.
- Test a fixed bug with a focused regression case when useful. Exercise concurrency or rollback when the change relies on those guarantees.
- Keep live-network tests opt-in. Do not invent coverage thresholds, test markers, or test infrastructure absent from the project.
- Run relevant checks and the checks required by the contribution workflow. Report what ran, what passed, and anything that could not be verified.

## Documentation and Change Safety

- Update relevant documentation when behavior, public contracts, setup, or commands change.
- Explain user tasks with realistic examples and exact commands. Keep implementation details in code comments unless they affect the user.
- Keep one current source for each fact; remove stale instructions rather than accumulating conflicting guidance.
- Use language markers on fenced code blocks and follow the existing documentation format.
- Preserve unrelated user changes. Do not discard work, amend commits, or run destructive Git commands without explicit authorization.
- Never commit credentials, token files, local secrets, or generated operational state.
- Keep migrations and relevant documentation alongside the code changes that require them.
- Follow this project's branch and pull-request workflow in `CONTRIBUTING.md`; feature work starts from `develop`.
- Summarize completed work concisely with verification results and material limitations. For reviews, lead with actionable findings and file references.
