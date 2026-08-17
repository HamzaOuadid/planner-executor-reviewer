# peer-loop — Planner → Executor → Reviewer Multi-Agent Loop

A cyclic multi-agent architecture for coding tasks: a **planner** proposes a
fix, an **executor** applies it and runs the real test suite, and a
**reviewer** checks the actual result against the task before it's allowed
to return — rejecting with a specific reason and sending it back to the
planner if it doesn't hold up, up to a hard iteration cap.

This is built as project 7 of a 20-project portfolio, against the spec
`07-planner-executor-reviewer-multi-agent-loop.md`.

## What's real here, honestly

There are no LLM API keys configured in this environment. So:

- **Fully real and fully tested, end to end:** the orchestration engine —
  the plan → execute → review state machine, revision cycles, the
  max-iteration cap, retry-with-backoff for transient tool failures, timeout
  handling, malformed-LLM-output recovery, structured tracing/logging, and
  SQLite persistence. 112 of 113 tests (1 skipped, see below) drive this through a **deterministic
  fake LLM client** (`FakeLLMClient`) — no network, no API key, fully
  reproducible.
- **Real but untested here (no key to test against):** `RealLLMClient`,
  which calls the Anthropic or OpenAI API. It's wired up, has its own unit
  tests for provider selection and env-var handling, but the actual
  network call path only runs if you supply a real key.
- **The "intelligence"** (what the planner actually proposes, what the
  reviewer actually thinks) is, for the demo/eval/tests, **hand-scripted**
  in `demo_fixtures.py` — canned per-task planner/reviewer responses,
  including deliberately flawed first attempts so the revision loop has
  something real to correct. Swap in `RealLLMClient` and the exact same
  loop, logging, and persistence code runs with a real model's plans and
  reviews instead. This is *more* rigorous for testing orchestration than
  hitting a live, non-deterministic LLM in CI would be.

## Task domain

The executor operates on **small, real Python bugs with real pytest
suites** (`src/peer_loop/task_suite/tasks.py`, 6 tasks). Each task ships a
deliberately buggy `solution.py` and a genuine, comprehensive
`test_solution.py`. This gives "does the reviewer's verdict match reality"
an objective, non-LLM-opinion ground truth: a real `pytest` subprocess run,
not a self-graded judgment call.

| task | bug |
|---|---|
| `is_palindrome` | doesn't ignore case/punctuation/spaces |
| `fibonacci` | wrong base case for n=0 |
| `flatten_list` | only flattens one level of nesting |
| `word_count` | case-sensitive, doesn't strip punctuation |
| `dedupe_preserve_order` | drops every duplicated item entirely instead of keeping the first occurrence |
| `safe_divide` | doesn't catch `ZeroDivisionError` |

## Architecture

```
run_task(task, max_iterations=5)
  │
  ▼
┌─────────────────────────── LoopController ───────────────────────────┐
│  for i in 1..max_iterations:                                         │
│    plan  = Planner.plan(task, prior_feedback)      ──▶ Plan          │
│    result= Executor.execute(task, plan, sandbox)    ──▶ ExecutionResult
│    verdict = Reviewer.review(task, plan, result)     ──▶ ReviewVerdict│
│    log_iteration(...)              # every step, every iteration     │
│    if verdict.accepted: return success                               │
│    prior_feedback = verdict.reason  # sent back to the planner        │
│  return failed  # cap hit — graceful, not an exception                │
└────────────────────────────────────────────────────────────────────┘
```

- **Planner** (`planner.py`) — LLM call → JSON `{rationale, steps[]}`.
  Each step names a tool (`read_file` / `write_file` / `run_tests` /
  `list_files`) and, for `write_file`, the complete new file content.
- **Executor** (`executor.py`) — resets the sandbox to the task's buggy
  baseline, then runs each step for real: real file I/O, a real `pytest`
  subprocess. Wraps each tool call in exponential-backoff retry for
  `TransientToolError`; a `ToolTimeoutError` is never retried and is kept
  distinguishable in the log from "ran fine but the code is wrong."
- **Reviewer** (`reviewer.py`) — LLM call → JSON `{accepted, reason}`,
  given the task, the plan, and the real execution result (including
  actual pytest output). Rejects with an empty or generically-worded
  reason (`"bad"`, `"wrong"`, ...) are themselves treated as malformed
  output — every rejection must cite specifics.
- **LoopController** (`loop_controller.py`) — the state machine above.
  Malformed LLM output at either stage, or an executor crash, is caught
  and turned into a normal rejected iteration (consuming one iteration
  slot) rather than an unhandled exception.
- **LoopLogger** (`logging_utils.py`) — one JSON object per loop event
  (`run_start` / `iteration` / `run_end`) to stdout and/or a JSONL file.
- **Storage** (`storage.py`) — SQLite (no server, no Docker needed),
  schema matches the spec's data model: `agent_runs` /
  `agent_iterations`.
- **LLMClient** (`llm/base.py`) — the provider abstraction. `FakeLLMClient`
  (`llm/fake.py`) is programmed with a queue of canned responses per role;
  `RealLLMClient` (`llm/real.py`) calls Anthropic (preferred) or OpenAI
  based on whichever key is in the environment/`.env`.

### Design tradeoff: each iteration restarts from the buggy baseline

`Executor.execute` resets the sandbox to the task's original starter code
at the top of every call, then applies that iteration's plan on top. The
planner is expected to hand back the *complete* corrected file each
attempt rather than an incremental diff. This keeps iterations fully
independent (no compounding state bugs across rounds, easy to test
deterministically) at the cost of not modeling an agent that incrementally
patches its own previous attempt. Documented here rather than hidden.

## Install

```bash
git clone https://github.com/HamzaOuadid/planner-executor-reviewer.git
cd planner-executor-reviewer
pip install -e ".[dev]"
```

Python 3.10+. No Docker, no Postgres, no API key required for anything
below except the `--real` flag.

## Usage

```bash
# List the task suite
peer-loop list-tasks

# The flagship demo: reviewer catches a real bad plan and corrects it
peer-loop demo

# Run any task through the loop, persisting the trace to SQLite
peer-loop run word_count --db runs.db --trace-file trace.jsonl

# Inspect a past run afterwards (the "debug why it was rejected" workflow)
peer-loop trace 1 --db runs.db

# M4: success rate with the reviewer active vs. stubbed to always-accept
peer-loop eval

# The seeded "reviewer is wrong" case (tracked, not hidden)
peer-loop run dedupe_preserve_order --reviewer-error-demo

# Route through a real LLM instead of the fake fixture (needs a key)
cp .env.example .env   # fill in ANTHROPIC_API_KEY or OPENAI_API_KEY
peer-loop run flatten_list --real
```

### Real demo run — actual output

This is genuine output from `peer-loop demo` (word_count task), captured
from an actual run in this repo, not hand-written. The scripted first
attempt lowercases words but forgets to strip punctuation; the reviewer
catches it, cites the exact failing test and the exact wrong dict it
produced, and rejects. The second attempt fixes it and is accepted.

```
$ peer-loop demo
{"event": "run_start", "run_id": "word_count-1786831140670-0", "task_id": "word_count", "task_text": "Fix word_count(text) in solution.py so it returns a dict of word -> frequency that is case-insensitive and ignores surrounding punctuation."}
{"event": "iteration", "run_id": "word_count-1786831140670-0", "iteration_number": 1, "planner_malformed_output": false, "plan_rationale": "lowercase each word before counting so case differences collapse together", "plan_steps": ["write_file", "run_tests"], "execution_overall_status": "success", "tests_passed": false, "step_statuses": [{"tool": "write_file", "status": "success", "attempts": 1}, {"tool": "run_tests", "status": "success", "attempts": 1}], "review_accepted": false, "review_reason": "test_strips_punctuation failed: word_count('Cat, cat. dog!') returned {'cat,': 1, 'cat.': 1, 'dog!': 1} instead of {'cat': 2, 'dog': 1} -- punctuation attached to words is never stripped", "reviewer_disagreed_with_tests": false, "duration_ms": 1094.0}
{"event": "iteration", "run_id": "word_count-1786831140670-0", "iteration_number": 2, "planner_malformed_output": false, "plan_rationale": "strip surrounding punctuation with str.strip(string.punctuation) in addition to lowercasing, per reviewer feedback", "plan_steps": ["write_file", "run_tests"], "execution_overall_status": "success", "tests_passed": true, "step_statuses": [{"tool": "write_file", "status": "success", "attempts": 1}, {"tool": "run_tests", "status": "success", "attempts": 1}], "review_accepted": true, "review_reason": "all 4 tests passed, including punctuation stripping", "reviewer_disagreed_with_tests": false, "duration_ms": 1000.0}
{"event": "run_end", "run_id": "word_count-1786831140670-0", "status": "success", "iteration_count": 2, "result": "accepted after 2 iteration(s): all 4 tests passed, including punctuation stripping", "total_duration_ms": 2094.0}

FINAL STATUS: success after 2 iteration(s)
accepted after 2 iteration(s): all 4 tests passed, including punctuation stripping
```

This is the acceptance criterion for "As a task submitter" (spec section
4): the reviewer caught a real bad-plan case, corrected it, and it's
logged and shown above.

### Real eval run — the proof metric (spec section 14)

Genuine output from `peer-loop eval`, run across the whole 6-task suite,
with the reviewer active vs. stubbed to always-accept (single-shot
baseline). Success is graded against real pytest ground truth, never
against either reviewer's own verdict — otherwise the always-accept
baseline would trivially show 100%.

```
$ peer-loop eval
task                    with reviewer     iters   baseline          iters
is_palindrome           PASS              1       PASS              1
fibonacci               PASS              1       PASS              1
flatten_list            PASS              2       FAIL              1
word_count              PASS              2       FAIL              1
dedupe_preserve_order   PASS              1       PASS              1
safe_divide             PASS              2       FAIL              1

with reviewer:  6/6 tasks correct (100% success rate)
baseline (no reviewer, single-shot): 3/6 tasks correct (50% success rate)
```

Three of six tasks are scripted with a deliberately flawed first attempt.
With the reviewer active, all three get caught and corrected. Without it
(single-shot baseline), whatever the executor produces first goes out the
door — wrong half the time on this suite.

### The reviewer being wrong — tracked, not hidden (spec section 9 / 13)

The spec is explicit that reviewer accuracy is itself unproven and the
comparison must be honest about cases where the reviewer is wrong. One
case is deliberately seeded (`--reviewer-error-demo`): the executor's
first attempt is actually **correct** (passes all 5 tests), but the
reviewer hallucinates a plausible-sounding but factually wrong rejection
anyway. `LoopController` flags this via
`Iteration.reviewer_disagreed_with_tests` (visible in the log and
persisted to SQLite) instead of silently absorbing it:

```
$ peer-loop run dedupe_preserve_order --reviewer-error-demo
...
{"event": "iteration", "iteration_number": 1, ..., "tests_passed": true, "review_accepted": false, "review_reason": "test_strings failed: dedupe(['b', 'a', 'b', 'c']) returned ['b', 'a', 'c'] but order-preserving dedup should sort remaining items alphabetically, expected ['a', 'b', 'c']", "reviewer_disagreed_with_tests": true, ...}
{"event": "iteration", "iteration_number": 2, ..., "tests_passed": true, "review_accepted": true, "review_reason": "all 5 tests passed; correcting my earlier misreading of the order-preservation requirement -- 'preserve order' means first-occurrence order, not alphabetical", "reviewer_disagreed_with_tests": false, ...}

FINAL STATUS: success after 2 iteration(s)
```

The run still succeeds (the identical correct fix is resubmitted and
accepted on round 2), but it cost a wasted iteration because the reviewer
was wrong — exactly the honest failure mode the spec asks not to hide.

## Testing

```bash
pytest tests/ -v
```

113 tests: 112 passing, 1 skipped (a provider-error assertion in
`test_llm_real.py` that only applies if the optional `anthropic` package
happens to be installed). Everything runs entirely through
`FakeLLMClient` — no network access, no API key, fully deterministic.
Coverage includes:

- **Multi-round revision** — a flawed first attempt gets a specific
  rejection and is corrected on the next attempt (`test_loop_controller.py`)
- **Max-iteration cap** — triggers exactly at the configured cap and fails
  gracefully with a clear status, never an unhandled exception
  (`test_max_iteration_cap_triggers_cleanly_not_an_exception`,
  `test_max_iteration_cap_is_exact_never_one_more_or_less`)
- **Malformed LLM output** at either the planner or reviewer stage is
  recovered from, not fatal (`test_planner_malformed_output_is_recovered_not_fatal`,
  `test_reviewer_malformed_output_is_recovered_not_fatal`)
- **Generic/non-specific rejection reasons** (`"bad"`, `"wrong"`, ...) are
  themselves rejected as malformed reviewer output
  (`test_reviewer.py::test_generic_rejection_reason_raises_malformed`)
- **Retry-with-backoff** for transient tool failures, and retry exhaustion
  reported as a normal failed step, not a crash (`test_executor.py`)
- **Timeout vs. wrong-but-successful** are kept distinguishable in the
  execution result (`test_timeout_is_distinguishable_from_a_wrong_but_successful_result`)
- **Executor crash** is caught by the loop controller and turned into a
  rejection, not a fatal exception (`_CrashingExecutor` in
  `test_loop_controller.py`)
- **Reviewer-disagrees-with-ground-truth** is tracked, not hidden
  (`test_reviewer_disagreement_with_ground_truth_is_tracked_not_hidden`)
- **SQLite persistence round-trip** and **CLI run → trace round-trip**
  (`test_storage.py`, `test_cli.py`)
- **The task suite's ground truth itself** — every starter genuinely fails
  its tests, every reference fix genuinely passes (`test_task_suite.py`)
- **The eval comparison** — with-reviewer strictly beats the baseline
  (`test_eval.py`)

## What's implemented vs. deliberately deferred

**Implemented:**
- Full planner → executor → reviewer loop with revision cycles
- Real tool execution (file I/O + real `pytest` subprocess), not mocked
- Retry-with-backoff for transient tool failures, distinct timeout handling
- Max-iteration cap with graceful failure
- Malformed-LLM-output recovery at both the planner and reviewer stages
- Structured JSONL logging of every loop step + SQLite persistence
  matching the spec's data model
- `FakeLLMClient` (deterministic, scriptable) and `RealLLMClient`
  (Anthropic/OpenAI) behind one `LLMClient` protocol
- 6-task suite with real, verifiable pass/fail ground truth
- M4 eval harness: with-reviewer vs. always-accept-baseline success rate
- The seeded "reviewer is wrong" case, tracked explicitly
- CLI (`peer-loop`): `list-tasks`, `run`, `demo`, `eval`, `trace`

**Deliberately deferred / scope cuts:**
- **MCP tool integration.** The spec suggests reusing MCP servers from
  other projects; this project implements its own small, real, in-process
  tool set (`read_file`/`write_file`/`run_tests`/`list_files`) instead.
  For a 4-tool sandboxed-coding-task suite, wiring a full MCP server would
  have added infrastructure without adding coverage of the loop logic that
  is this spec's actual point.
- **LangGraph.** The spec offers "LangGraph or a hand-rolled state
  machine" (section 12); a hand-rolled state machine was chosen so the
  iteration/rejection/revision logic is fully transparent and testable
  without an extra framework dependency.
- **Incremental (diff-based) revision.** Each iteration restarts from the
  task's buggy baseline rather than building on the previous attempt's
  edited file (see "Design tradeoff" above) — simpler and more testable,
  at the cost of not modeling incremental self-correction within a file.
- **Real-LLM integration tests.** `RealLLMClient`'s network call path
  (`_complete_anthropic` / `_complete_openai`) is not exercised by the test
  suite since no API key is available in this environment; its
  provider-selection and error-handling logic is unit tested, and the
  planner/reviewer/loop code paths it feeds into are fully tested via the
  fake client.
- **A real MCP-based tool timeout/flakiness simulation.** Transient
  failures and timeouts are simulated via an injectable `fault_injector`
  hook in `Executor` rather than actually killing a subprocess mid-flight
  — deterministic and fast for tests, while `run_tests`'s real
  `subprocess.run(..., timeout=...)` path is also covered directly in
  `test_tools.py` with a genuinely slow test file.

## Repository layout

```
src/peer_loop/
  models.py            Pydantic data model (Plan, ExecutionResult, ReviewVerdict, Iteration, RunResult)
  exceptions.py         MalformedResponseError, TransientToolError, ToolTimeoutError, UnknownToolError
  json_utils.py          Tolerant JSON extraction from raw LLM text
  llm/                  LLMClient protocol, FakeLLMClient, RealLLMClient
  tools.py               Real file I/O + real pytest subprocess execution
  task_suite/tasks.py    The 6-task suite with starter/fix/test code
  planner.py / executor.py / reviewer.py / loop_controller.py
  logging_utils.py       Structured JSONL loop tracing
  storage.py              SQLite persistence (agent_runs / agent_iterations)
  demo_fixtures.py        Scripted FakeLLMClient responses per task
  eval.py                  M4 with/without-reviewer success-rate comparison
  cli.py                    peer-loop command-line entry point
tests/                    113 tests (112 passing, 1 skipped), all via FakeLLMClient
.github/workflows/ci.yml  Runs the test suite + eval + demo on every push
```

## License

MIT — see [LICENSE](LICENSE).
