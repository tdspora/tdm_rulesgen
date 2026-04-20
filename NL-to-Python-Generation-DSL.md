# A Minimal PoC DSL for Natural-Language Column Generation Rules

## Executive summary

A low-effort, PoC-friendly DSL for user-authored generation rules can be implemented most quickly by **reusing Python’s own expression parser** (`ast.parse(..., mode="eval")`) as the “syntax layer,” while enforcing safety and determinism via a **strict AST whitelist + a small, explicitly whitelisted runtime function set** (e.g., `col()`, `coalesce()`, `faker()`, `randint()`, `pattern()`, `fk()`, `group_sum()`). The Python standard library supports parsing and walking ASTs (`ast`), transforming trees (`NodeTransformer`), and compiling AST objects into executable code (`compile()` accepts AST inputs).

This approach is exceptionally PoC-efficient because it avoids implementing a full lexer/parser while still yielding a robust internal representation. However, it must be paired with **hard limits on input size/complexity** and **defensive execution**: Python’s AST compiler can be crashed by sufficiently complex inputs, and related “safe-looking” helpers like `ast.literal_eval` are explicitly not recommended on untrusted inputs due to denial-of-service risks.

For NL→DSL, the preferred direction is an **LLM-based translator** that maps user phrasing into a typed semantic frame and DSL candidate for a small set of intents (faker-like, arithmetic, conditional, pattern, timestamp, referential integrity, aggregate). The generated output must still pass deterministic schema checks, AST validation, and runtime whitelisting before execution. Deterministic matchers or templates can remain as fallback paths for especially narrow intents or high-confidence repairs.

A PoC DSL should explicitly cover: row expressions, column references, arithmetic, conditionals, pattern generation, timestamps, seeded randomness, whitelisted Faker calls (including uniqueness helpers), referential integrity hooks, and a minimal set of group operations, while keeping semantics simple and predictable. Faker provides documented seeding and unique-value generation facilities, which can be incorporated into determinism and uniqueness guarantees.

## Survey of candidate libraries and tools

### Parsing and DSL toolkits

The following table summarizes common Python parsing/DSL approaches relevant to a PoC. The “recommended choice” is evaluated with PoC constraints: minimal engineering, fast iteration, and controllable safety.

| Option | Parsing model | Strengths for PoC | Friction / risks | When it’s the right choice |
|---|---|---|---|---|
| **Python `ast.parse` as the DSL parser (recommended for PoC)** | Python expression grammar | No external dependency; direct AST output; easy to validate with `NodeVisitor`/`NodeTransformer`; can compile AST with `compile()`  | Must constrain syntax and validate strictly; complex inputs can crash interpreter (DoS) so you need size/complexity limits  | When the DSL can be a “Python-expression subset” and you want the fastest path |
| **Lark** | Earley + LALR(1) + CYK; EBNF-like grammars | Strong grammar authoring; LALR(1) efficiency; supports Earley for broad grammars; provides automatic tree construction and line counting  | Adds dependency and a grammar+transformer layer; still need compiler/validator to safe runtime | When you want a custom syntax (not Python-like) and better parse errors/locations |
| **Parsimonious** | PEG parser | Lightweight; pure Python; PEG-based EBNF-like grammars  | PEG greediness/backtracking gotchas; you write visitors manually; less ergonomic than Lark for many  | When you want a minimal PEG grammar and can live with PEG tradeoffs |
| **textX** | Meta-language for DSLs; builds parser + metamodel | Produces a metamodel/object graph from grammar; purpose-built for DSLs  | Bigger conceptual overhead for a PoC; often used when you want a full modeling layer, scoping, etc.  | When your DSL needs model-driven tooling beyond expression evaluation |
| **ANTLR4** | LL(*) / adaptive LL(*) | Industrial-grade parsing; generates parser + listener/visitor from grammar; multi-language targets; widely used  | Heavyweight for PoC; external toolchain; Java requirement is common in ANTLR 4 workflows (repo indicates Java 11+)  | When you need long-term, multi-language grammar ecosystem and can afford toolchain setup |

**PoC recommendation:** start with a **Python-expression-subset DSL** parsed by `ast.parse(mode="eval")`, because it collapses the parser+AST layer into one. Use Lark later if you need a non-Python surface syntax or richer error recovery.

### AST manipulation and codegen libraries

For your PoC, you primarily need to **build/validate Python AST** and optionally **pretty-print/explain** it.

- **Python `ast`**: core module for processing Python abstract syntax trees; includes tree walking and transformation utilities and `ast.unparse` to regenerate source code from AST (added in Python 3.9).
- **AST compilation**: `compile()` can take an AST object and produce a code object executable via `eval()`/`exec()`.
- **LibCST**: lossless concrete syntax tree preserving whitespace/comments; best for refactoring/codemods, not required for a DSL evaluator but useful if you later evolve toward “editable code artifacts.”
- **RedBaron/Baron (FST)**: provides full syntax trees preserving formatting; oriented to refactoring tasks, not needed for a minimal rules DSL.
- **astor**: designed for manipulating Python source via AST and converting node trees back into Python source (`to_source`).
- **gast**: compatibility layer that abstracts AST differences across Python versions; useful mainly if you must support multiple Python versions’ AST shapes.
- **typed_ast**: historically used to parse type comments independent of runtime Python version; it explicitly does not support Python 3.8+ syntax and recommends stdlib `ast` for 3.8+.

**PoC recommendation:** use **stdlib `ast` + `ast.unparse`** for debug/explainability; avoid codegen libraries unless you need cross-version printing quirks or older Python support.

### Data modeling helpers for the DSL AST/IR

- **`dataclasses`**: standard library decorator/module for boilerplate-free data containers (good for defining DSL node types).
- **Pydantic**: strong validation and error messages for structured data models; includes `model_validate`/`ValidationError` workflows that can make DSL IR validation cleaner.

**PoC recommendation:** `dataclasses` for node types + handwritten validation is usually lowest friction; add Pydantic only if you want richer validation/errors early.

### NL-to-DSL helpers

- **LLM translation layer**: prompt an LLM to produce a typed semantic frame and DSL candidate, then reject or repair anything that fails schema and AST checks. This provides the main NL coverage path while preserving a strict validation boundary.
- **Deterministic repair/fallback layer**: token-based rules such as spaCy `Matcher` / `EntityRuler` or narrow templates can still help normalize column mentions, repair obvious slot errors, or provide fallback behavior for well-known intents.

**PoC recommendation:** make the LLM translator the primary NL-to-DSL path, but keep deterministic repair and fallback rules around it so every candidate still goes through a predictable validation gate.

## Rule-DSL precedents and what to borrow

A PoC DSL benefits enormously from borrowing “good defaults” from existing rule languages.

### SQL-like expression idioms

SQL’s conditional and null-handling constructs are familiar to many users and provide clear semantics:

- `COALESCE(...)` returns the first non-NULL argument (SQLite documents this explicitly).
- SQL `CASE`/conditional constructs short-circuit at the first match; PostgreSQL docs note evaluation properties similar to `CASE` and `COALESCE` semantics.

**Borrow for PoC:** adopt explicit `coalesce(x, y)` and a simple conditional expression (`if(cond, a, b)` or Python’s `a if cond else b`). This helps define null semantics consistently and predictably.

### Jinja templates

Jinja is a Python templating engine with control-flow features; it also includes a documented sandbox mode (`SandboxedEnvironment`) for rendering untrusted templates in restricted contexts.

**Borrow for PoC:** treat “template-like” string generation as a first-class use case (e.g., `template("{first}.{last}@example.com")`), but keep it *very constrained*; Jinja’s sandbox exists, yet template-injection history shows sandboxing is non-trivial and must be treated carefully for untrusted inputs.

### JsonLogic-style rules

JsonLogic is a JSON-based logic format designed to be portable and secure; it explicitly emphasizes not using `eval()` and that rules operate only on provided data (read-only).

**Borrow for PoC:** a small stable core of operators and “data access” (`var`/`col`) plus combinators. Even if you don’t adopt JSON as the surface syntax, the **operator-as-data** mindset helps keep the rule engine auditable.

## Proposed minimal PoC DSL specification

This section proposes a compact specification optimized for a **4-week PoC**. The goal is to be expressive enough for synthetic column generation while keeping parsing/compilation effort minimal.

### Design goals

- **Low-effort parsing**: reuse Python expression parsing (`ast.parse(mode="eval")`) and restrict to an allowed subset.
- **Safety**: users never write full Python statements; the validator disallows attribute access, imports, comprehensions, lambdas, subscripting, etc. (details below). Restricted subsets are a known security approach, but must be paired with other controls; RestrictedPython documents it is *not* a full sandbox.
- **Determinism**: seeded RNG and seeded Faker. Faker documents `Faker.seed()` and also per-instance seeding via `seed_instance` / `seed_locale`, plus a `.unique` proxy for uniqueness.
- **Predictable null semantics**: build in `coalesce`, `optional(p, expr)`, and consistent propagation rules inspired by SQL-like semantics.
- **Minimal multi-pass semantics**: presence of group ops triggers a second pass over the generated table.

### Surface syntax (PoC)

For PoC simplicity, define the DSL as:

- A **rule file** = one rule per line:
  `COLUMN_NAME = EXPR`
- `EXPR` = a restricted Python expression subset.

Example:

```text
total_comp = col("base_salary") + coalesce(col("bonus"), 0)
email = unique(lower(faker("first_name")) + "." + lower(faker("last_name")) + "@example.com")
customer_id = fk("customers.customer_id")
order_total = group_sum(key=col("order_id"), value=col("line_amount"))
```

This “Python-expression DSL” is intentionally boring: it makes the PoC translator and evaluator straightforward.

### Allowed tokens and lexical conventions

Because you parse with Python’s own parser, lexing/tokenization follows Python rules for identifiers, numbers, and string literals. The key PoC conventions are:

- **Column references must use `col("...")`** (string-literal column name).
- **External hooks** must be string-literal references, e.g., `fk("table.column")`.
- **String literals** must be Python-string literals (recommend double quotes for user docs); this directly leverages Python’s robust string escape handling.

### Minimal EBNF (conceptual)

You do not need to fully re-implement Python’s grammar; this conceptual EBNF defines the subset you accept and validate after parsing:

```ebnf
rule_file      := { rule_line } ;
rule_line      := IDENT "=" expr ;

expr           := literal
               | call
               | col_ref
               | "(" expr ")"
               | expr binop expr
               | unop expr
               | expr cmpop expr
               | expr boolop expr
               | cond_expr ;

cond_expr      := expr "if" expr "else" expr ;  (* optional; can omit for PoC *)

col_ref        := "col" "(" STRING ")" ;

call           := IDENT "(" [ args ] ")" ;
args           := arg { "," arg } ;
arg            := expr | IDENT "=" expr ;

literal        := NUMBER | STRING | "None" | "True" | "False" ;
binop          := "+" | "-" | "*" | "/" ;
unop           := "+" | "-" | "not" ;
cmpop          := "==" | "!=" | "<" | "<=" | ">" | ">=" ;
boolop         := "and" | "or" ;
```

### DSL IR (AST node types)

Even though parsing yields Python AST, maintain a small internal IR for clarity and future evolution. Use `dataclasses` for nodes. A minimal set:

- `Rule(target_col: str, expr: PyAstExpr, location: (line, col))`
- `ExprKind` categories (optional): `RowExpr | GroupExpr | ConstraintExpr`
- `FunctionCall(name, args, kwargs)` (optional) if you normalize calls

In a pure PoC, you can skip a separate IR and keep “validated Python AST” as the IR. That is acceptable if (a) validation is strict and (b) runtime call targets are whitelisted.

### Typing and null semantics (PoC rules)

Define a small type universe and predictable coercions:

- Types: `Null`, `Bool`, `Int`, `Float`, `Str`, `DateTime`, `Date`, `Any`.
- **Null propagation**:
  - Arithmetic ops: if any operand is null → result null (unless wrapped by `coalesce`).
  - Comparisons/predicates: if any operand is null → predicate evaluates to false (PoC default; SQL uses “unknown,” but PoC can choose false to minimize surprises). This behavior mirrors typical defensive programming and avoids tri-valued logic in v1 while still allowing explicit predicates like `is_null(x)`. (SQL documents “unknown” behavior in some implementations; note this differs and should be documented.)
- `coalesce(a, b, ...)`: returns first non-null, mirroring SQL `coalesce`.
- `optional(p, expr)`: returns null with probability `p`, else `expr` (requires deterministic RNG seeding; see below).

### Error model

Emit structured errors that can drive a UI:

- `DSLParseError`: syntax error from `ast.parse`; include line/offset. `ast.parse` warns that producing an AST doesn’t guarantee the code is compilable; compilation can still raise `SyntaxError` for context-sensitive constraints.
- `DSLSafetyError`: forbidden node/call/identifier.
- `DSLTypeError`: obvious type mismatches detected statically in simple cases (optional).
- `DSLUnknownColumnError`: `col("x")` refers to missing schema column.
- `DSLExecutionError`: runtime exception (should be wrapped with rule name + row index).
- `DSLAggregationPhaseError`: aggregate used in row phase or vice versa.

### Supported functions (PoC whitelist)

**Row-phase functions**

- `col(name: str)` → value from current row
- `coalesce(*args)` → first non-null
- `optional(p, expr)` → probabilistic null
- `randint(a, b)`, `choice(seq, weights=None)` → RNG-based values (seeded)
- String helpers: `lower`, `upper`, `concat`, `substr`, `len` (or forbid `len` if you avoid Python builtins)
- `faker(provider: str, **kwargs)` → whitelisted Faker provider call
- `unique(expr)` → unique constraint wrapper (implemented by maintaining a “seen set” and retrying)
- `pattern(fmt: str)` and/or `regex(rx: str)` → **limited generator** supporting a safe subset (see examples)

**Referential integrity hooks**

- `fk("table.column")` → sample from a precomputed keyset (optionally weighted)

**Group-phase functions**

- `group_sum(key=..., value=...)`
- `group_count(key=...)`
- `row_number(partition_by=..., order_by=...)` (optional)

For PoC minimalism, implement `group_sum` and `group_count` first.

### Deterministic seeding strategy

Determinism should not rely on accidental global RNG state. Python’s `random` module documents that reusing a seed reproduces sequences, but also notes algorithms and seeding behavior may change across Python versions; thus you should pin versions if cross-version determinism is required.

A practical PoC strategy:

- Accept a single `run_seed` (int).
- Derive per-column seeds deterministically:
  - `col_seed = stable_hash64(run_seed, rule_id, column_name)`
- Create per-column RNGs:
  - `py_rng = random.Random(col_seed)`
  - `np_rng = np.random.default_rng(col_seed)` for vectorized draws; NumPy documents seeding and reproducible outputs for `default_rng(seed=...)`.
- Seed Faker:
  - Use `fake.seed_instance(col_seed)` for per-instance RNG isolation, or `Faker.seed(col_seed)` for global seeding; Faker documents both class seeding and per-instance seeding, including `seed_instance` and `.unique`.

This setup makes rules stable even if unrelated columns are added/removed, because each column uses its own RNG stream.

## NL-to-DSL-to-AST examples

Below are **12 concrete examples** showing NL rule → DSL → safe Python AST snippet. These examples assume:

- `col("x")` reads from the current row.
- Runtime provides a `faker()` function (whitelisted providers only).
- Runtime provides an RNG-backed `randint()` and `choice()` that are deterministic under the seeding policy.
- Aggregations run in a second pass.

The AST snippets are illustrative Python `ast` constructions; in the PoC you may parse DSL text into AST and then validate/normalize it instead of constructing it manually. The `ast` module provides `NodeVisitor`/`NodeTransformer` for walking/rewriting nodes and `ast.unparse` for explainability.

```mermaid
flowchart LR
  NL["Natural language rule"] --> IE["LLM semantic frame + DSL candidate"]
  IE --> DSL["DSL expression string"]
  DSL --> P["ast.parse(mode='eval')"]
  P --> V["AST validator + normalizer"]
  V --> C["compile(AST, ..., 'eval')"]
  C --> E["Execute in sandboxed runtime"]
  E --> OUT["Column values / diagnostics"]
```

### Example set

1) **Faker name**

- NL: “full_name should be a realistic name.”
- DSL: `faker("name")`
- Safe AST snippet:
```python
import ast
expr = ast.Expression(
    body=ast.Call(
        func=ast.Name(id="faker", ctx=ast.Load()),
        args=[ast.Constant(value="name")],
        keywords=[],
    )
)
```
- Edge cases: locale selection and uniqueness. Faker supports per-instance seeding and `.unique` for uniqueness within an instance lifetime.

2) **Email derived from faker first/last with normalization and uniqueness**

- NL: “email is lower(first.last)@example.com and must be unique.”
- DSL: `unique(lower(faker("first_name")) + "." + lower(faker("last_name")) + "@example.com")`
- Safe AST snippet:
```python
import ast
expr = ast.Expression(
    body=ast.Call(
        func=ast.Name(id="unique", ctx=ast.Load()),
        args=[
            ast.BinOp(
                left=ast.BinOp(
                    left=ast.BinOp(
                        left=ast.Call(ast.Name("lower", ast.Load()),
                                      [ast.Call(ast.Name("faker", ast.Load()),
                                                [ast.Constant("first_name")], [])], []),
                        op=ast.Add(),
                        right=ast.Constant("."),
                    ),
                    op=ast.Add(),
                    right=ast.Call(ast.Name("lower", ast.Load()),
                                   [ast.Call(ast.Name("faker", ast.Load()),
                                             [ast.Constant("last_name")], [])], []),
                ),
                op=ast.Add(),
                right=ast.Constant("@example.com"),
            )
        ],
        keywords=[],
    )
)
```
- Edge cases: collisions; implement `unique(expr)` as “retry up to K times, then error,” and expose collisions meaningfully in UI logs. Faker’s `.unique` can help, but your wrapper is more general.

3) **Arithmetic across columns with null default**

- NL: “total_comp = base_salary + bonus; treat null bonus as 0.”
- DSL: `col("base_salary") + coalesce(col("bonus"), 0)`
- Safe AST snippet:
```python
import ast
expr = ast.Expression(
    body=ast.BinOp(
        left=ast.Call(ast.Name("col", ast.Load()), [ast.Constant("base_salary")], []),
        op=ast.Add(),
        right=ast.Call(
            ast.Name("coalesce", ast.Load()),
            [
                ast.Call(ast.Name("col", ast.Load()), [ast.Constant("bonus")], []),
                ast.Constant(0),
            ],
            [],
        ),
    )
)
```
- Edge cases: if base_salary is null, propagate null (document); this is consistent with SQL-like dependence on `coalesce` for null handling.

4) **Conditional logic**

- NL: “If job_level ≥ 5 then bonus is 10% of base_salary else 0.”
- DSL: `0.10 * col("base_salary") if col("job_level") >= 5 else 0`
- Safe AST snippet:
```python
import ast
expr = ast.Expression(
    body=ast.IfExp(
        test=ast.Compare(
            left=ast.Call(ast.Name("col", ast.Load()), [ast.Constant("job_level")], []),
            ops=[ast.GtE()],
            comparators=[ast.Constant(5)],
        ),
        body=ast.BinOp(
            left=ast.Constant(0.10),
            op=ast.Mult(),
            right=ast.Call(ast.Name("col", ast.Load()), [ast.Constant("base_salary")], []),
        ),
        orelse=ast.Constant(0),
    )
)
```
- Edge cases: null `job_level` or `base_salary`; PoC rule: null in predicate → false, so falls to else. Document this divergence from SQL “unknown” semantics.

5) **Optional nulls with probability**

- NL: “middle_name is missing for ~40% of rows, otherwise a faker first name.”
- DSL: `optional(0.40, faker("first_name"))`
- Safe AST snippet:
```python
import ast
expr = ast.Expression(
    body=ast.Call(
        ast.Name("optional", ast.Load()),
        [ast.Constant(0.40), ast.Call(ast.Name("faker", ast.Load()), [ast.Constant("first_name")], [])],
        []
    )
)
```
- Edge cases: determinism depends on seeded RNG stream. Python `random` documents reproducibility with a reused seed (with caveats across versions/threads).

6) **Pattern generation (format-string subset)**

- NL: “device_code must look like ABC-1234.”
- DSL: `pattern("AAA-####")`
- Safe AST snippet:
```python
import ast
expr = ast.Expression(
    body=ast.Call(ast.Name("pattern", ast.Load()), [ast.Constant("AAA-####")], [])
)
```
- Edge cases: ensure `pattern()` supports only a safe mini-language:
  - `A` = uppercase letter, `a` = lowercase, `#` = digit, other chars literal.
  - Reject large repeats or nested constructs to avoid DoS; Python AST tooling warns complex inputs can crash the interpreter, reinforcing the need for strict complexity bounds across the pipeline.

7) **Regex-like generation (restricted regex subset)**

- NL: “policy_id matches ^POL-[0-9]{8}$.”
- DSL: `regex("^POL-[0-9]{8}$")`
- Safe AST snippet:
```python
import ast
expr = ast.Expression(
    body=ast.Call(ast.Name("regex", ast.Load()), [ast.Constant(r"^POL-[0-9]{8}$")], [])
)
```
- Edge cases: full regex generation is hard; PoC should implement a limited subset (character classes + fixed quantifiers) and reject advanced constructs. This keeps runtime predictable and prevents pathological regex expansions.

8) **Timestamp in a range**

- NL: “created_at is a random timestamp in the last 90 days.”
- DSL: `ts_between(now_minus(days=90), now())`
- Safe AST snippet:
```python
import ast
expr = ast.Expression(
    body=ast.Call(
        ast.Name("ts_between", ast.Load()),
        [
            ast.Call(ast.Name("now_minus", ast.Load()), [], [ast.keyword(arg="days", value=ast.Constant(90))]),
            ast.Call(ast.Name("now", ast.Load()), [], []),
        ],
        []
    )
)
```
- Edge cases: use a fixed `run_now` anchored at job start for determinism; ensure timezone policy is explicit.

9) **Timestamp ordering constraint**

- NL: “updated_at is after created_at by 0–30 days.”
- DSL: `ts_add(col("created_at"), days=randint(0, 30))`
- Safe AST snippet:
```python
import ast
expr = ast.Expression(
    body=ast.Call(
        ast.Name("ts_add", ast.Load()),
        [ast.Call(ast.Name("col", ast.Load()), [ast.Constant("created_at")], [])],
        [ast.keyword(arg="days", value=ast.Call(ast.Name("randint", ast.Load()),
                                               [ast.Constant(0), ast.Constant(30)], []))]
    )
)
```
- Edge cases: if `created_at` is null, return null (propagate). Determinism again depends on seeded RNG.

10) **Referential integrity**

- NL: “customer_id must reference an existing customers.customer_id.”
- DSL: `fk("customers.customer_id")`
- Safe AST snippet:
```python
import ast
expr = ast.Expression(
    body=ast.Call(ast.Name("fk", ast.Load()), [ast.Constant("customers.customer_id")], [])
)
```
- Edge cases: if keyset empty, decide policy: return null vs error; PoC should default to error with actionable messaging.

11) **Group aggregate: sum over rows**

- NL: “order_total is sum(line_amount) per order_id.”
- DSL: `group_sum(key=col("order_id"), value=col("line_amount"))`
- Safe AST snippet:
```python
import ast
expr = ast.Expression(
    body=ast.Call(
        ast.Name("group_sum", ast.Load()),
        [],
        [
            ast.keyword(arg="key", value=ast.Call(ast.Name("col", ast.Load()), [ast.Constant("order_id")], [])),
            ast.keyword(arg="value", value=ast.Call(ast.Name("col", ast.Load()), [ast.Constant("line_amount")], [])),
        ],
    )
)
```
- Edge cases: multi-pass execution. The engine must detect `group_sum` and schedule it in the aggregate phase, after row values exist.

12) **Cross-column constraint with clamping**

- NL: “age derived from date_of_birth, clamped to [18, 75].”
- DSL: `clamp(age_from_dob(col("date_of_birth")), 18, 75)`
- Safe AST snippet:
```python
import ast
expr = ast.Expression(
    body=ast.Call(
        ast.Name("clamp", ast.Load()),
        [
            ast.Call(ast.Name("age_from_dob", ast.Load()),
                     [ast.Call(ast.Name("col", ast.Load()), [ast.Constant("date_of_birth")], [])],
                     []),
            ast.Constant(18),
            ast.Constant(75),
        ],
        []
    )
)
```
- Edge cases: leap days and timezone behavior should be encapsulated in `age_from_dob()` with a clearly documented policy.

## PoC implementation plan, sandboxing, testing, and milestones

### Recommended minimal translator and runtime architecture

A PoC-optimized architecture keeps layers thin and testable:

1) **NL translator (LLM + validation gate)**
- Implement a small intent set: `{faker_value, arithmetic, conditional, pattern, timestamp, fk, aggregate, unique, optional}`.
- Use the schema column dictionary in the prompt and post-validation to ground column mentions.
- Optionally use **spaCy Matcher + EntityRuler** or narrow templates as a repair/fallback layer when the LLM output is incomplete or misses obvious slots.

2) **DSL builder**
- Emit DSL expression strings in the restricted Python-expression subset.

3) **DSL parser**
- `ast.parse(expr, mode="eval")` to obtain AST.
- Enforce input limits:
  - max characters per expression (e.g., 2–5k)
  - max AST node count / depth
  - reject deeply nested expressions (to avoid compiler stack-depth issues documented by `ast`).

4) **AST validator + normalizer**
- Use `ast.NodeVisitor` to ensure:
  - Only allowed node classes appear (e.g., `Expression`, `Constant`, `Name`, `Call`, `BinOp`, `BoolOp`, `Compare`, `IfExp`, `UnaryOp`).
  - `Call.func` must be `ast.Name` and the name must be in a whitelist (`col`, `coalesce`, `faker`, etc.).
  - Disallow `Attribute`, `Subscript`, `Lambda`, comprehensions, `Dict`, `List` literals if you want minimal complexity (or allow small `List` for `choice([...])`).
- Optionally normalize:
  - Rewrite `None` to `null()` or keep as `Constant(None)`.

5) **Compilation**
- Use `compile(validated_ast, filename, mode="eval")`; Python docs state `compile()` can compile an AST object into a code object executable by `eval()`/`exec()`.
- Cache compiled code objects by `(rule_id, version, python_version, dependency_versions)`.

6) **Execution engine (two-phase)**
- **Row phase:** evaluate row expressions per row.
- **Group phase:** evaluate aggregate expressions with access to the full table (or partition index structures).
- Provide runtime context:
  - seeded RNG streams
  - Faker instance(s) seeded via documented mechanisms (`Faker.seed`, `seed_instance`, `.unique`).

### Validation steps (minimal but essential)

Even in a PoC, the following steps are high leverage:

- **Unknown column detection**: any `col("x")` must resolve to schema.
- **Forbidden nodes**: fail with `DSLSafetyError` and a user-readable explanation.
- **Forbidden calls**: only whitelisted function names; no attribute access.
- **Complexity bounds**: reject or truncate large expressions; `ast` warns about interpreter crashes on complex inputs.

### RestrictedPython in the PoC?

RestrictedPython defines a “safe subset” and can restrict language features, but it explicitly states it is **not a sandbox system or a secured environment**; it helps define a trusted environment for executing untrusted code.

**PoC guidance:**
- If you **never accept raw Python** and only compile ASTs you constructed/validated, RestrictedPython may add limited value.
- If you decide to allow “advanced mode” where users type slightly more Python-like snippets, RestrictedPython can provide a second layer—still not a replacement for process isolation.

### Sandboxing options for a PoC

Use OpenSandbox for running generated Python scripts.

### Suggested test cases

A PoC succeeds if it is demonstrably correct and fails safely. Use pytest for unit tests and Hypothesis for property-based tests.

**Core unit tests (translator + validator)**
- Parse success/failure:
  - malformed input, unexpected tokens, unmatched quotes
- Safety:
  - reject `__import__`, `open`, attribute access (`x.__class__`), subscripting, comprehensions
- Column resolution:
  - unknown `col("missing")` should fail clearly
- Whitelist calls:
  - allow only explicit list: `col`, `coalesce`, `faker`, `randint`, `choice`, `pattern`, `regex`, `fk`, `group_sum`, etc.

**Runtime unit tests**
- Determinism:
  - fixed seed results match exactly across runs (within pinned versions)
- Null semantics:
  - propagation and `coalesce` behavior
- Uniqueness:
  - `unique(expr)` produces no duplicates for reasonable N; collision handling triggers retry
- Aggregation:
  - `group_sum` produces correct totals; missing keys handled per policy

**Property-based tests (Hypothesis)**
Hypothesis is designed to generate edge cases you didn’t think of and shrink failures to minimal reproductions.
- Generate random small schemas + random safe DSL expressions; assert:
  - validator never allows forbidden nodes
  - evaluation never raises unexpected exceptions (only expected `DSLExecutionError`)
  - determinism holds for a given seed
- Generate random “pattern strings” for `pattern()` within supported alphabet and assert that output matches constraints.

### Performance and caching recommendations for a PoC

- **Cache compiled expressions**: since `compile()` returns code objects, cache by `(dsl_string, schema_signature, runtime_version)`; `compile()` explicitly produces code objects executable by `eval()`/`exec()`.
- **Avoid per-row parser work**: parse+compile once, then evaluate for all rows.
- **Precompute FK keysets and group indexes**: keep dictionaries `{key -> aggregate}` for `group_sum` and reuse across columns in the same phase.
- **Use vectorization only if trivial**: NumPy’s `default_rng(seed)` supports reproducible generation and can speed up generation, but integrating vectorization with `col()` dependencies can complicate the PoC.
