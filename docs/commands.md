\
    # Lighthouse Command Reference

    Start Lighthouse from the repository root:

    ```powershell
    python lighthouse.py
    ```

    Then enter commands inside the Lighthouse CLI.

    ## Core telemetry

    ```text
    snapshot
    ```

    Runs a full system telemetry report.

    ```text
    health
    ```

    Shows a compact health summary.

    ```text
    cpu
    memory
    disk
    processes
    ```

    Shows focused telemetry reports.

    ```text
    events
    crash
    ```

    Shows recent crash-relevant Windows event evidence.

    ```text
    windows
    ```

    Shows aggregated Windows-native evidence and deterministic findings.

    ```text
    cim
    ```

    Shows Windows CIM hardware and OS evidence.

    ## Deterministic diagnosis

    ```text
    diagnose
    slow
    ```

    Explains likely causes of slowness from available telemetry.

    ```text
    insight
    explain
    ```

    Shows a plain-English Lighthouse assessment.

    ```text
    plan <text>
    ```

    Builds a conservative tool plan. It does not execute tools.

    Example:

    ```text
    plan close Chrome because it is using memory
    ```

    ```text
    runplan <text>
    ```

    Runs the request through Lighthouse Engine V1. The engine may execute safe
    read-only tools, but it does not execute OS-changing tools.

    Example:

    ```text
    runplan why is my laptop slow
    ```

    ## Operator routing

    ```text
    talk <text>
    ```

    Interprets natural input and suggests a deterministic safe route. It does not
    execute the route.

    Example:

    ```text
    talk why is chrome eating memory
    ```

    ```text
    talkrun <text>
    ```

    Interprets natural input and auto-runs only safe read-only diagnostic routes
    through the Operator Autorun Gate.

    Example:

    ```text
    talkrun why is my laptop slow
    ```

    Unsafe requests are refused for autorun.

    ```text
    routes
    ```

    Shows the Operator route registry and policy health.

    ```text
    interactions
    ```

    Shows recent Operator interaction traces.

    ```text
    feedback labels
    feedback <trace_id> <label> [note]
    ```

    Lists feedback labels and records feedback against an Operator trace.

    ## LLM preview boundary

    ```text
    ask <question>
    ```

    Asks Lighthouse a plain-English question. If Ollama is disabled or unavailable,
    Lighthouse uses deterministic fallback behavior.

    ```text
    model
    model test
    ```

    Shows local Ollama status or sends a small safe model test prompt.

    ```text
    llm preview <text>
    ```

    Asks the model for a route proposal and validates it through LLM Contract V0.
    This is preview-only and executes nothing.

    ```text
    llm talk <text>
    ```

    Shows a side-by-side deterministic route interpretation and LLM route preview.
    This is preview-only and executes nothing.

    ```text
    llm previews
    ```

    Shows recent LLM route preview journal entries.

    ```text
    llm preview feedback labels
    llm preview feedback <preview_id> <label> [note]
    ```

    Lists LLM preview feedback labels and records feedback for a preview.


## Conversational turns

```text
turn <text>
turns
turn feedback labels
turn feedback <turn_id> <label> [note]
turn feedback latest <label> [note]
```

`turn <text>` builds a preview-only conversational engine turn and records it
to the append-only turn journal. It does not execute tools.

`turns` reviews recent conversational engine turns.

`turn feedback <turn_id> <label> [note]` records append-only Operator feedback
against a specific turn id.

`turn feedback latest <label> [note]` records feedback against the most recent
turn, avoiding manual copy/paste of the turn id during quick smoke tests.

Turn feedback is observational. It does not rewrite turn records, execute tools,
call a model, mutate the operating system, or override deterministic route,
tool, or autorun authority.

    ## Dataset export

    ```text
    dataset operator
    ```

    Exports Operator route interaction examples.

    ```text
    dataset llm preview
    ```

    Exports LLM preview examples with feedback when available.

    Dataset export does not execute routes.

### Conversational turn dataset

```text
dataset turns
conversation turn dataset
```

Exports conversational engine turn examples from `memory/conversation_turns.jsonl`
to `memory/datasets/conversational_turn_dataset.jsonl`.

This is a dataset-export command only. It does not execute routes, call the
model, mutate the operating system, or change the turn journal.

    ## Local history and audit

    ```text
    save
    history
    last
    ```

    Saves and reads local telemetry snapshots.

    ```text
    journal
    ```

    Shows recent Lighthouse action journal entries.

    ## Session commands

    ```text
    help
    quit
    ```

## Conversational turn feedback review

```text
turn feedback labels
turn feedbacks
turn feedback journal
turn feedback <turn_id> <label> [note]
conversation turn feedback <turn_id> <label> [note]
conversational turn feedback <turn_id> <label> [note]
```

Lists conversational turn feedback labels, reviews recent turn feedback records,
and records feedback for a full conversational engine turn. Feedback is appended
as a later human judgment and is joined into `dataset turns`.

The review commands show the append-only feedback journal without changing it.

## Conversational turn dataset review

```text
dataset turns review
dataset turns rows
dataset turns review <limit>
conversation turn dataset review
conversational turn dataset review
```

Reviews rows from the current exported conversational turn dataset artifact.
This does not regenerate the dataset, call a model, execute tools, mutate the
operating system, or rewrite journals. Run `dataset turns` first when the export
is missing or stale.

## Conversational turn dataset review filters

```text
dataset turns review included
dataset turns review excluded
dataset turns review feedback
dataset turns review corrections
dataset turns review review-needed
dataset turns review category <category>
```

Filters rows from the current exported conversational turn dataset artifact.
These commands do not regenerate the dataset, rewrite journals, delete memory,
call a model, execute tools, or mutate the operating system.

