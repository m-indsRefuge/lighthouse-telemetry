# Lighthouse V1 CLI Smoke Checklist

This checklist is for local Operator validation after safety-critical CLI or
engine changes. It complements PyTest. It does not replace PyTest.

## Preconditions

```powershell
cd C:\Users\nolan\AIProjects\lighthouse
git checkout main
git pull origin main
python -m pytest tests
```

## Start CLI

```powershell
python lighthouse.py
```

## Core read-only commands

```text
health
windows
cim
events
```

Expected result: reports render without crashing. No OS-changing action is taken.

## Deterministic operator flow

```text
talk why is my laptop slow
talkrun why is my laptop slow
```

Expected result:
- `talk` recommends a safe route but does not execute it.
- `talkrun` only auto-runs safe read-only diagnostic routes through the
  Operator Autorun Gate.

## LLM preview flow

```text
llm preview why is chrome eating memory
llm talk why is chrome eating memory
llm previews
llm preview feedback labels
```

Expected result:
- LLM preview and LLM talk are preview-only.
- They do not execute commands.
- They do not pass model output into `talk` or `talkrun`.
- They record preview journal IDs when journaling succeeds.

## Feedback and dataset flow

Use a real preview id from `llm previews`:

```text
llm preview feedback <preview_id> useful live smoke test looked correct
dataset llm preview
dataset operator
```

Expected result:
- feedback is recorded
- dataset export succeeds
- no route is executed by dataset commands

## Exit

```text
quit
```
