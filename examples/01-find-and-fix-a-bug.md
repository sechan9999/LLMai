# Example 1 — Find and fix a bug

**Time:** ~2 minutes · **Layers needed:** none (core only)

## Prompt

> The `validate_email` function in `auth/validators.py` accepts
> `user@` as valid. Find why, fix it, and add a test.

## What the agent does

1. **`list_files`** under `auth/` to locate `validators.py` (auto-approved)
2. **`read_file`** on `validators.py` — discovers the regex is missing
   the domain part
3. **Asks for permission** to call `edit_file` — you approve
4. **`edit_file`** replaces the regex with one requiring `@<domain>.<tld>`
5. **`read_file`** on `tests/test_validators.py` to see existing test style
6. **Asks for permission** to call `edit_file` again — you approve
7. **`edit_file`** adds a new test case `test_rejects_empty_domain`
8. **Asks for permission** to call `run_command pytest tests/test_validators.py`
9. **`run_command`** runs the test, observes it passes
10. Summarizes what changed

## Success signal

```
✓ Edited auth/validators.py: 1 replacement applied
✓ Edited tests/test_validators.py: added test_rejects_empty_domain
✓ pytest passed (5 tests in 0.04s)
```

## What you learn

- The 8-tool core loop is enough for most bug fixes
- Every state-mutating step asks permission — you stay in control
- The agent reads existing code before writing similar code, so style stays consistent

## Variations

- Add `"don't run tests yet"` to the prompt to stop the agent before step 8
- Add `"check git blame to see when this regex was added"` to bring `run_command` into the read phase
