# Natural-Language Rules to Safe Python for Column-Level Synthetic Data Generation in an MMD-VAE Tool

## Executive summary

A practical way to let users define natural-language (NL) “generation rules” for dataset columns—while keeping execution safe and scalable—is to have a **large language model (LLM) translate NL into a constrained intermediate representation (IR)/DSL first**, then **compile that DSL into a validated Python AST**, and finally **execute inside a defense-in-depth sandbox** with strict resource and capability limits. This mirrors a core lesson from NL2Code research: constraining the output space with syntax/structure (e.g., AST-aware generation) improves reliability and correctness compared to unconstrained text-to-code.

For integration with an MMD-VAE (InfoVAE family) synthetic-data tool, the most robust pattern is a **hybrid generator**:

- Use **MMD-VAE** to generate unconstrained columns (or latent codes), leveraging its stability and objective variants that include Maximum Mean Discrepancy regularization.

- Use the **Rules Engine** to generate:
  - derived columns (deterministic functions of other columns),
  - constraint-heavy columns (IDs, checksums, referential integrity, timestamps ordering),
  - columns specialized by **Faker** for realistic text-like values with reproducible seeding.

Security should assume rules are untrusted code. In-process restrictions (e.g., RestrictedPython) can help but are not a complete sandbox; robust isolation typically requires OS/hypervisor-level boundaries (containers + syscall filtering, user-space kernels, or microVMs), plus strict CPU/memory/time/network controls.

A 12-week implementation is feasible for an initial production-grade slice if scope is disciplined: start with a small but expressive grammar, strong validation, a safe execution environment, preview UX, and a test/metrics harness that includes both fidelity and privacy risk auditing (e.g., membership inference).

## Requirements and problem framing

The feature goal is: **users write NL rules for one or more dataset columns**, which the system translates into **safe Python code** (optionally using Faker) to generate values within an **MMD‑VAE-based synthetic tabular data tool**. Key functional requirements implied by the prompt include:

- **Column rule coverage**: arithmetic across columns, conditional logic, randomness + seeding, regex/pattern strings, timestamps, uniqueness, aggregations over generated rows, referential integrity, and cross-column constraints.
- **Safety**: rules cannot become arbitrary code execution; must prevent injection, data exfiltration, hostile resource use, or sandbox escape; must include audit/logging. RestrictedPython explicitly positions itself as a “safe subset” helper but “not a sandbox system or a secured environment,” so stronger isolation is needed.
- **Reproducibility**: users should be able to re-run generation to get identical outputs given the same seed/config (including Faker version behavior). Faker documents explicit seeding and notes that the same seed yields the same results when using the same methods and version.
- **Evaluation**: include metrics for fidelity/utility/privacy; privacy auditing should acknowledge that synthetic data can leak membership information via overfitting and that realistic MIAs exist even when only synthetic samples are released.

Assumptions (per prompt): no specific constraint on user skill level, hosting environment, or deployment model. That pushes the design toward **safe defaults**, progressive disclosure of complexity, and a clean API surface.

## Architecture and system design

### Component model

A production architecture typically benefits from separating (a) rule authoring and translation, (b) compilation/validation, (c) execution, and (d) model-based generation. A minimal component set:

1. **Rule Authoring API**
   - API: CRUD for rules, compilation endpoint, and generation jobs.

2. **NL Understanding Layer**
   - LLM-based translator that extracts intents/entities/constraints and produces a structured semantic frame plus DSL candidate.

3. **Rule IR/DSL + Compiler**
   - A constrained DSL that can represent all supported constructs.
   - Compiler that transforms DSL → Python AST (never string concatenation), validates allowed nodes, then compiles to a code object using the standard `compile()` pipeline.

4. **Safe Execution Service**
   - Runs compiled rules on generated rows under strict sandbox controls.
   - Implements per-rule resource limits, determinism controls (seed), and I/O/network lockdown.

5. **MMD‑VAE Model Service**
   - Already implemented. Acts as a client for rules generation service. Provides initial synthetic dataset for rules to apply.

6. **Job Orchestrator + Storage**
   - Async task execution (e.g., Celery) for generation workloads, consistent with task-queue semantics (producers enqueue tasks; workers consume).
   - Metadata DB (rules, versions, runs, audit logs) via an ORM (SQLAlchemy supports CPython ≥3.11).
   - Generated datasets storead on a local file system and available for download using API endpoints.

### Data flow and ordering

A robust data flow for a single-table dataset:

1. **Schema ingest**: columns, types, nullability, constraints (if any), plus user rules.
2. **Column planning**:
   - classify columns as:
     - *Model-generated* (from MMD‑VAE),
     - *Rule-generated* (from DSL → safe Python),
     - *Hybrid* (MMD‑VAE base + rule postprocess).
3. **Dependency graph**:
   - edges represent “column A depends on column B.”
   - compute topological ordering; detect cycles; provide actionable errors.
4. **Base generation (already implemented)**:
   - generate N rows for model-generated columns via MMD‑VAE.
5. **Rule execution**:
   - execute row-wise rules in dependency order.
   - execute aggregate/group rules in one or more passes (see runtime section).
6. **Validation + metrics**:
   - schema checks, constraint checks, and fidelity/privacy evaluation.
7. **Artifacts**:
   - output dataset + run report + audit logs.

### Interfaces and APIs

A clean API surface (illustrative):

- `POST /rules/parse` → returns semantic frame (intents/entities/constraints) with confidence.
- `POST /rules/compile` → returns DSL + compiled artifact ID + explainability trace.
- `POST /datasets/{id}/generate` → starts async generation job; returns job ID.
- `GET /jobs/{id}` → status/progress, partial preview samples.
- `GET /runs/{id}/report` → quality + privacy metrics report and execution logs.

If implemented in FastAPI, its design emphasizes building APIs with standard Python type hints and supports async path operations, which is useful for job submission and preview endpoints.

### Sandboxing and dependency management

Execution of user-derived code must be treated as hostile. Containerization alone is not a complete sandbox; for example, Linux syscall filtering (seccomp) reduces kernel attack surface but “isn’t a sandbox” by itself and must be combined with other hardening and policy enforcement.

A defensible dependency strategy should include:

- **Pinned versions + hash checking** for reproducible, tamper-resistant installs (`pip --require-hashes`).
- **Vulnerability scanning** (pip-audit scans environments against known advisories).
- **SBOM generation** (CycloneDX tools generate SBOMs for Python projects; CPython also publishes SBOMs).
- **Project health scoring** (OpenSSF Scorecard provides automated checks across supply-chain risk areas).

### Integration with MMD‑VAE

The InfoVAE framework describes objective variants (including MMD-based regularization) intended to improve latent usage and posterior quality issues in VAEs. A rule layer can integrate with an MMD‑VAE tool in three main patterns:

- **Post-generation derivation (recommended baseline)**: train/generate with MMD‑VAE on all columns; compute rule-driven columns afterward. This yields exact constraints for derived columns.

A key design point is to make the **column planner explicit**: every column is assigned a source of truth (model vs rule) and a consistency policy.

## Rule language and semantics

### Why a DSL (even if the output is “Python code”)

Unconstrained NL→Python is brittle. NL2Code research and surveys consistently show that structure-aware generation (AST constraints, intermediate representations) improves correctness and controllability. TRANX, for example, emphasizes using target syntax to constrain output space and improve accuracy/generalization. A broad survey of NL2Code highlights diverse approaches and the practical challenges of reliability and evaluation across settings.

Therefore:

- The **user-facing language** can be NL, but the **system’s internal contract** should be a typed DSL/IR.
- The DSL provides:
  - restricted constructs,
  - explicit typing and null handling,
  - deterministic compilation,
  - explainability (“we understood your NL as this DSL”).

### Core constructs to support

Below is a compact semantics catalog aligned to the prompt.

**Row expressions**
- Literals: numbers, strings, booleans, null
- Column references: `col("other_col")`
- Arithmetic: `+ - * / // %`, min/max, clamp
- String ops: concat, lower/upper, substring
- Regex/pattern: `regex("^[A-Z]{3}-\\d{4}$")` (generation) and `match(...)` (validation)
- Dates/times: `now()`, `date_add`, `date_diff`, `between()`
- Conditionals: `if(cond, a, b)`; comparisons; boolean ops
- Random: `randint(a,b)`, `choice([...], weights=[...])`, `normal(mu, sigma)` with seeded RNG
- Faker calls (whitelisted providers): `faker("name")`, `faker("email")`, etc., with locale support. Faker documents locale configuration and seeding.

**Table / group expressions**
- Aggregations over produced rows:
  - `row_number(order_by=..., partition_by=...)`
  - `group_sum(key="order_id", value="line_amount")`
  - `group_count_distinct(...)`
- Constraints and referential integrity:
  - `unique()` constraint declaration
  - `foreign_key("customers.customer_id")` semantics with generation ordering

### Example EBNF-style sketch

This is a design sketch (not a standard) that is intentionally small enough to implement safely:

```ebnf
rule         := "set" column "=" expr [ "where" predicate ] ;
expr         := literal
              | "col" "(" string ")"
              | expr binop expr
              | unop expr
              | "if" "(" predicate "," expr "," expr ")"
              | "faker" "(" string ["," "locale" "=" string] ")"
              | "randint" "(" number "," number ")"
              | "choice" "(" list ["," "weights" "=" list] ")"
              | "regex" "(" string ")"
              | "date_between" "(" date_expr "," date_expr ")"
              | "row_number" "(" [partition] [order] ")"
              | "group_sum" "(" "key" "=" string "," "value" "=" string ")"
              ;
predicate    := expr cmpop expr | predicate boolop predicate | "not" predicate ;
```

The important architectural point is that **every node maps to a known-safe AST fragment**; anything else is rejected before compilation.

## NL-to-code translation approach

### Processing pipeline

A defensible NL-to-code pipeline for this feature:

1. **NL normalization**
   - tokenize, lowercasing where appropriate, normalize column names, parse numbers/dates, detect units.

2. **Intent + entity extraction**
   - classify intent: faker value, arithmetic derivation, conditional rule, timestamp rule, regex format, aggregation, ID generation, referential integrity, etc.

3. **Fill a typed semantic frame**
   - Example frame fields: `target_column`, `dependencies`, `distribution`, `constraints`, `null_policy`, `seed_policy`.

4. **Generate DSL**
   - deterministic canonical DSL rendering from the LLM-produced semantic frame.

5. **Compile DSL → Python AST**
   - build AST nodes, validate allowed node types, compile with `compile()` from the standard library.

6. **Static safety validation**
   - enforce “no import,” “no attribute access outside whitelist,” no `exec/eval`, no file/network primitives, no dunder access, bounded loops (ideally no loops at all), and size limits.

7. **Explainability trace**
   - show users: “NL → semantic frame → DSL → (safe) Python snippet.”

8. **Execution inside sandbox**
   - run with restricted globals and resource limits plus OS-level isolation, and optionally Python runtime auditing hooks for visibility. PEP 578 introduces runtime audit hooks for monitoring security-sensitive runtime actions.

### DSL vs direct Python generation

Even if the system “outputs Python,” direct NL→Python text synthesis is risky and hard to validate. NL2Code literature emphasizes the usefulness of structure-aware generation and constrained decoding/outputs. A DSL-first approach makes validation tractable and supports strong safety guarantees.

### NL-to-code approaches compared

| Approach | How it works | Strengths | Weaknesses | Fit for this feature |
|---|---|---|---|---|
| Template-based | Match NL patterns to predefined templates that emit DSL/Python | Highly deterministic, easy to validate, predictable explainability | Limited coverage; brittle wording variants; needs many templates | Useful as a fallback or guardrail for narrow intents |
| ML-based (semantic parsing / LLM) | Model maps NL → code/DSL (possibly AST-constrained) | Broad coverage; handles paraphrases; can learn complex mappings | Non-determinism, hallucinations, harder to constrain; evaluation burden is high per NL2Code survey discussions | Useful as an assistant, but risky as the sole compiler |
| LLM-first with DSL gate (recommended) | LLM maps NL to a typed semantic frame and DSL candidate; deterministic validators and optional templates gate, repair, or reject the output before compilation | Broad NL coverage, good paraphrase handling, strong safety boundary at the DSL validator | Requires prompt/eval discipline, model monitoring, and fallback handling | Recommended if NL authoring is a primary user interface |

Recommendation: **LLM-first with a DSL gate**. Let an LLM propose the semantic frame and DSL, but never allow it to emit executable Python directly and never trust its output until the DSL validator accepts it. Deterministic templates can still serve as fallback handling for especially narrow or high-confidence intents. This aligns with structure-constrained approaches like TRANX and addresses reliability concerns highlighted in NL2Code evaluations.

### Concrete NL → Python examples

Each example shows a **safe function** signature:

- `row`: dict-like access to previously generated columns
- `ctx`: sandbox-provided context with:
  - `faker`: initialized Faker instance (seeded, locale-configured)
  - `rng`: a `random.Random`-like RNG (seeded)
  - helper utilities, e.g., `null_with_prob(p)`, `slugify()`, `clamp()`

#### Example rule for Faker-generated names

**NL rule:** “`full_name` should be a realistic US full name.”

```python
def gen_full_name(row, ctx):
    return ctx.faker.name()
```

Edge cases: locale selection and reproducibility. Faker supports locales and explicit seeding for repeatable outputs.

#### Example rule for regex/pattern-formatted IDs

**NL rule:** “`device_code` must look like `ABC-1234` (3 uppercase letters, hyphen, 4 digits).”

```python
def gen_device_code(row, ctx):
    letters = "".join(ctx.rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(3))
    digits = "".join(ctx.rng.choice("0123456789") for _ in range(4))
    return f"{letters}-{digits}"
```

Edge cases: uniqueness (if required) should be enforced by a uniqueness constraint layer rather than hoping randomness avoids collisions; the engine should detect collisions and retry with a cap.

#### Example rule for arithmetic across columns with null handling

**NL rule:** “`total_comp` = `base_salary` + `bonus`; if `bonus` is null, treat it as 0.”

```python
def gen_total_comp(row, ctx):
    base = row.get("base_salary")
    bonus = row.get("bonus")
    if base is None:
        return None
    return float(base) + float(bonus or 0.0)
```

Edge cases: type coercion (string to float), missing `base_salary`, and defaulting `bonus`. Null policies should be explicit in the DSL (e.g., `coalesce(col("bonus"), 0)`).

#### Example rule for conditional logic referencing another column

**NL rule:** “If `job_level` ≥ 5, `bonus` is 10% of `base_salary`, else 0.”

```python
def gen_bonus(row, ctx):
    base = row.get("base_salary")
    level = row.get("job_level")
    if base is None or level is None:
        return None
    return 0.10 * float(base) if int(level) >= 5 else 0.0
```

Edge cases: missing level/base, non-integer levels, rounding rules (bankers rounding vs floor) should be configurable.

#### Example rule for timestamps with ordering constraint

**NL rule:** “`created_at` is a random timestamp in the last 90 days; `updated_at` is after `created_at` by 0–30 days.”

```python
from datetime import timedelta

def gen_created_at(row, ctx):
    # ctx.now is an anchored datetime (fixed per run) for reproducibility
    start = ctx.now - timedelta(days=90)
    seconds = ctx.rng.randint(0, 90 * 24 * 3600)
    return start + timedelta(seconds=seconds)

def gen_updated_at(row, ctx):
    created = row.get("created_at")
    if created is None:
        return None
    delta_days = ctx.rng.randint(0, 30)
    return created + timedelta(days=delta_days)
```

Edge cases: timezone handling; define `ctx.now` as a fixed “run anchor time” (not wall clock) to keep replays deterministic; validate `updated_at >= created_at`.

#### Example rule for randomness and per-column seeding

**NL rule:** “`churned` is True with probability 7%.”

```python
def gen_churned(row, ctx):
    return ctx.rng.random() < 0.07
```

Edge cases: deterministic randomness should come from a seeded RNG (and ideally split per column for reproducibility across schema changes). Faker also supports seeding.

#### Example rule for aggregation over generated rows

**NL rule:** “For each `order_id`, set `order_total` to the sum of `line_amount` across all rows with that `order_id`.”

This is not a pure row-local rule; it requires a group pass:

```python
def compute_order_totals(table, ctx):
    # table is a list[dict] or a DataFrame-like abstraction provided by the engine
    totals = {}
    for r in table:
        oid = r.get("order_id")
        amt = r.get("line_amount") or 0.0
        if oid is None:
            continue
        totals[oid] = totals.get(oid, 0.0) + float(amt)
    for r in table:
        oid = r.get("order_id")
        r["order_total"] = totals.get(oid)
    return table
```

Edge cases: missing `order_id`, null `line_amount`, floating-point stability, and whether orders must have at least one line. This motivates modeling **multi-pass rules** in the DSL: “row rules” vs “group/table rules.”

#### Example rule for referential integrity across tables

**NL rule:** “`customer_id` in `orders` must reference an existing `customer_id` from the `customers` table.”

```python
def gen_orders_customer_id(row, ctx):
    # ctx.ref("customers.customer_id") returns a precomputed list of valid keys
    keys = ctx.ref("customers.customer_id")
    return ctx.rng.choice(keys) if keys else None
```

Edge cases: empty parent table, distribution matching (uniform vs weighted by customer frequency), and generation ordering (customers must be generated before orders). Referential integrity should be enforced structurally by the planner.

#### Example rule for cross-column consistency constraint

**NL rule:** “`age` must match `date_of_birth` (rounded down), and must be between 18 and 75.”

```python
from datetime import date

def gen_age(row, ctx):
    dob = row.get("date_of_birth")
    if dob is None:
        return None
    # dob can be a date or datetime; normalize
    dob_date = dob.date() if hasattr(dob, "date") else dob
    today = ctx.now.date() if hasattr(ctx.now, "date") else date.today()
    age = today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))
    return max(18, min(75, age))
```

Edge cases: leap days, timezone shifts if using datetimes, and whether clamping is acceptable vs resampling DOB to satisfy bounds. A good DSL supports either policy.

## Runtime execution and scalability

### Batch vs streaming generation

Two execution modes map to typical synthetic data usage:

- **Batch mode**: generate a full dataset of size N, run multi-pass rules, then compute evaluation metrics and output artifacts. This is the natural fit for offline generation pipelines and for computing table-level aggregates.
- **Streaming mode**: generate rows incrementally (useful for previews and very large datasets). Streaming complicates cross-row aggregates and referential constraints; the engine should either:
  - restrict streaming previews to row-local rules, or
  - allow partial aggregates with a “finalize” step.

### Dependency resolution and ordering

The engine should build a dependency DAG between columns:

- Row-based dependencies (A uses B) are resolved by topological ordering.
- Cycles should be diagnosed with human-readable explanations and suggested fixes (e.g., compute A from B, or B from A, but not both).

Aggregations introduce *global dependencies*:
- A group aggregate column depends on the entire set of rows (or a partition), so the planner should mark it as “requires pass after base rows exist.”

### Handling missing/nullable values

Null handling should be explicit and systematic:

- **null policy**: `strict` (propagate null), `coalesce` (default), `resample` (retry generation), `error`.
- For Faker-like generators, allow `optional(p)` style null introduction (probability p) with deterministic seeding; seeding is a primary mechanism for repeatable results.

### Performance and scalability techniques

- **Compilation caching**: compile DSL→AST→code objects once per rule version and cache artifacts.
- **Vectorization**: where possible, compile some DSL nodes into vectorized operations (NumPy/pandas), which are designed for high-performance table operations (NumPy provides efficient ndarray operations; pandas is built for table-like data structures).
- **Task offloading**: use a distributed task queue for large jobs; Celery’s model describes workers consuming tasks via a broker, enabling horizontal scaling.
- **Resource limits**: container-level CPU/memory limits (Docker documents runtime resource constraints) mitigate runaway generation workloads.

## Validation, quality, and testing strategy

### Testing layers

A rigorous test plan should include:

- **Unit tests** for:
  - NL parsing into semantic frames,
  - DSL rendering and round-tripping,
  - AST validation rules (reject forbidden constructs),
  - deterministic seeding behavior.

- **Integration tests**:
  - end-to-end generation: schema → MMD‑VAE base → rule application → output dataset,
  - multi-pass aggregate correctness,
  - referential integrity across multi-table datasets.

- **Property-based tests**:
  - Use Hypothesis to generate random schemas/rules within supported grammar and validate invariants (e.g., `updated_at >= created_at`, uniqueness, bounds). Hypothesis is specifically designed to test properties over broad input spaces and shrink failing examples.

### Validation datasets and scenarios

Build a “rule conformance suite” with:

- small toy datasets (fast execution),
- medium datasets for performance regression,
- schemas with common enterprise patterns: IDs, timestamps, monetary amounts, categorical codes, nested dependencies.

### Fidelity and utility metrics

For tabular synthetic data, evaluate:

- **distribution similarity**: marginals, pairwise correlations, and higher-order checks.
- **model utility**: Train-on-Synthetic Test-on-Real (TSTR) is a known evaluation protocol used in synthetic data literature to test downstream utility; early uses appear in time-series GAN evaluation contexts.
- **model-agnostic evaluation suites**: SDMetrics provides quality and privacy metric tooling for tabular synthetic data evaluation.

### Privacy risk auditing

Synthetic data is not automatically private. Membership inference attacks against generative models have been demonstrated, and more recent work proposes practical MIAs against synthetic data via overfitting detection (e.g., DOMIAS).

Recommended privacy checks:

- **Nearest-neighbor / distance-to-closest-record (already implemented)** metrics and disclosure checks (available in SDV/SDMetrics privacy evaluation guidance).
- **Membership inference score** (e.g., run a representative MIA evaluation against released synthetic tables).
- **Policy gating**: block export if privacy risk exceeds thresholds; require explicit override + audit reason.

Regulatory guidance and PET framing can inform governance; the UK ICO publishes PETs guidance and AI/data protection guidance that can be used to structure risk assessment, although it is not synthetic-data-specific “implementation advice.”

## Safety, security, UX, and deployment roadmap

### Sandboxing options and security checklist

#### Sandboxing options compared

| Option | Isolation boundary | Pros | Cons | When to use | Key sources |
|---|---|---|---|---|---|
| In-process subset (RestrictedPython) | Same process | Fast; helps define a restricted language subset | Not a complete sandbox; still needs external hardening | As an *additional* layer, never the only boundary | RestrictedPython docs and PyPI warning  |
| Containers with hardening | OS namespaces/cgroups + LSM | Mature tooling; easy deployment; can apply AppArmor/SELinux | Containers “by default secure” is not equivalent to “safe for untrusted code”; needs defense-in-depth | Good baseline when combined with seccomp, no network, non-root | Docker security docs  |
| seccomp profiles | Syscall filtering | Reduces kernel attack surface; widely used in orchestration | Not a sandbox alone (“isn’t a sandbox”) | Pair with containers/microVMs | Kernel + Kubernetes docs  |
| User-space kernel (entity["organization","gVisor","userspace kernel sandbox"]) | Intercepts syscalls in user space | Stronger isolation than vanilla containers; used in managed offerings | Operational complexity; compatibility/perf tradeoffs | Multi-tenant untrusted execution | gVisor docs  |
| MicroVMs (entity["organization","Firecracker","microvm vmm"] / Kata) | Hardware virtualization | Strong isolation; designed for multi-tenant workloads | More operational overhead than containers | Highest-risk untrusted execution | Firecracker docs  |
| WebAssembly runtime (Pyodide) | Wasm sandbox (browser/edge) | Strong capability limits by design; convenient for “run locally in browser” execution | Package compatibility, performance limits; not all server contexts | Client-side previews; restricted execution environments | Pyodide docs + Cloudflare Pyodide writeup |

#### Security checklist

Execution sandbox (must-have):
- Run as non-root; prefer rootless container mode in Docker where feasible.
- Enforce CPU/memory/time limits (Docker documents resource constraint controls).
- Disable outbound network by default; allow none unless explicitly needed.
- Apply syscall filtering (seccomp) and OS hardening; note seccomp alone is insufficient.

Language-level safety (must-have):
- Compile from DSL → AST; validate AST; reject any unknown nodes; compile via standard mechanisms.
- No imports; no filesystem or subprocess APIs; whitelist only safe helpers and Faker providers.
- Limit recursion/loops; prefer expression-only rules.
- Audit runtime events: use Python audit hooks (PEP 578) to log security-sensitive actions where possible.

Supply-chain security (must-have):
- Pin dependencies; enable hash-checking installs (`pip --require-hashes`).
- Scan dependencies with pip-audit.
- Generate SBOMs (CycloneDX tooling) and store them per release.
- Track dependency/project posture with OpenSSF Scorecard where relevant.

### Tech stack recommendations

Given “no specific constraint,” a conservative production stack in Python:

- Python: target modern CPython where audit hooks exist (introduced in 3.8 per PEP 578 discussion in “What’s New”), and to benefit from newer `ast`/runtime improvements.
- API service: FastAPI for typed endpoints and async.
- Async jobs: Celery for distributed task processing pattern.
- Data handling: pandas + NumPy for tabular operations and performance where safe.
- ORM: SQLAlchemy for rule/run metadata persistence.
- Faker: for realistic text generators, seeded for reproducibility and locale support.
- Sandboxing: defense-in-depth:
  - AST validation + restricted globals
  - plus container/microVM isolation (Docker hardening; consider gVisor or Firecracker for higher-risk tiers).
- Supply chain: pip hash-checking installs + pip-audit + SBOM generation (CycloneDX).

### Deployment considerations

- **Isolation tiering**: run previews in a lighter sandbox; run full jobs in the strongest available isolation (microVMs where feasible). Firecracker is explicitly positioned as enabling workloads in lightweight VMs with enhanced isolation over traditional VMs while retaining container-like speed/efficiency.
- **Monitoring**: track job duration, rule compile failures, sandbox terminations, memory/CPU throttling, and privacy metric alerts.
- **Rollback**: immutable rule versions + run-level linkage enables rollback by selecting prior rule versions; apply standard blue/green or canary for rule engine changes.
- **Secure builds**: enforce hash-checking installs and SBOM publication; use automated dependency vulnerability detection (pip-audit) in CI gates.
