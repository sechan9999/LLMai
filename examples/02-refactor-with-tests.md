# Example 2 — Refactor with tests as a safety net

**Time:** ~5–8 minutes · **Layers needed:** none

## Prompt

> Refactor `api/client.py` to split the 400-line `ApiClient` class into
> `RequestBuilder`, `ResponseParser`, and `RetryPolicy` helper classes.
> Keep the public API unchanged and make sure all tests in
> `tests/test_client.py` still pass after each step.

## Why this prompt works

It gives the agent three structural anchors (the three new classes), a
constraint that limits blast radius (public API unchanged), and a
verification loop (existing tests must keep passing). The agent will
plan, refactor in chunks, and re-run tests between steps.

## What the agent does

1. `read_file api/client.py` — sees the 400-line class
2. `read_file tests/test_client.py` — locks in the public API surface
3. `run_command pytest tests/test_client.py` (asks first) — establishes a
   green baseline
4. **Iteration 1:** create `api/_request.py` with `RequestBuilder`,
   edit `client.py` to delegate. Re-run tests. Still green.
5. **Iteration 2:** create `api/_response.py` with `ResponseParser`. Edit,
   re-run. Still green.
6. **Iteration 3:** create `api/_retry.py` with `RetryPolicy`. Edit,
   re-run. Still green.
7. Summarizes the final layout

## Success signal

The agent reports after each iteration:

```
✓ Extracted RequestBuilder → api/_request.py
  pytest: 23 passed, 0 failed
✓ Extracted ResponseParser → api/_response.py
  pytest: 23 passed, 0 failed
✓ Extracted RetryPolicy → api/_retry.py
  pytest: 23 passed, 0 failed
```

If any iteration breaks tests, the agent surfaces the failure and either
retries with a fix or asks you how to proceed.

## What you learn

- Multi-step refactors work as long as you give the agent a verification
  loop (tests). Without one, you're trusting the model's judgment alone
- Permission prompts batch nicely — say "Allow this for the rest of the
  session" if the same write pattern repeats

## Tips

- Always include the test command in the prompt. If you don't, the agent
  often skips verification
- For larger refactors, ask for a written plan first, then approve
  step-by-step
