\
    # Lighthouse

    Lighthouse is a local Windows telemetry and diagnostic assistant.

    It is built around a simple safety spine:

    ```text
    Observe -> Mediate -> Act
    ```

    In V1, Lighthouse is focused on observation, diagnosis, safe planning, explicit
    route mediation, journaling, and auditability. It is not an autonomous OS
    controller.

    ## Current status

    Lighthouse is currently in late V0 / early V1 stabilization.

    The current V1 spine includes:

    - read-only telemetry collection
    - Windows-native evidence collection
    - deterministic diagnostic findings
    - a conservative tool registry
    - a read-only tool executor
    - Lighthouse Engine V1 orchestration
    - Operator route registry and autorun gate
    - local memory context retrieval
    - operator interaction journaling
    - LLM Contract V0 route validation
    - LLM preview-only route proposal flow
    - feedback capture and dataset export
    - Windows GitHub Actions PyTest workflow

    ## Safety model

    Lighthouse follows these rules:

    ```text
    The model is not authority.
    The route registry is authority for routing.
    The tool registry is authority for tools.
    The autorun gate is authority for safe auto-run.
    The Operator remains in command.
    ```

    The model may explain or propose a route through a strict contract, but it may
    not execute commands, authorize actions, provide shell commands, bypass the
    route registry, bypass the tool registry, or bypass the autorun gate.

    Lighthouse V1 does not:

    - run arbitrary shell commands
    - mutate the operating system automatically
    - close processes automatically
    - delete files automatically
    - edit the registry
    - change Windows settings
    - treat model output as permission
    - treat memory as authority

    See:

    - [Safety Model](docs/safety_model.md)
    - [V1 Contract Shapes](docs/v1_contract_shapes.md)
- [Memory Layer Architecture](docs/memory_layer_architecture.md)

    ## Requirements

    Lighthouse currently targets:

    - Windows
    - Python 3.12
    - PowerShell
    - local repository execution

    Install dependencies from:

    ```powershell
    python -m pip install -r requirements.txt
    ```

    Ollama support is optional and disabled by default. To enable local Ollama
    usage for supported model paths:

    ```powershell
    $env:LIGHTHOUSE_USE_OLLAMA="1"
    ```

    To choose a model:

    ```powershell
    $env:LIGHTHOUSE_OLLAMA_MODEL="qwen2.5:3b"
    ```

    ## Quick start

    From the repository root:

    ```powershell
    cd C:\Users\nolan\AIProjects\lighthouse
    python lighthouse.py
    ```

    Inside the CLI:

    ```text
    help
    health
    windows
    talk why is my laptop slow
    llm talk why is chrome eating memory
    quit
    ```

    ## Command documentation

    Main command groups:

    ```text
    Core telemetry:
      snapshot
      health
      cpu
      memory
      disk
      processes
      events
      windows
      cim

    Deterministic diagnosis:
      diagnose
      insight
      plan <text>
      runplan <text>

    Operator routing:
      talk <text>
      talkrun <text>
      routes
      interactions
      feedback labels
      feedback <trace_id> <label> [note]

    LLM preview boundary:
      ask <question>
      model
      model test
      llm preview <text>
      llm talk <text>
      turn <text>
      llm previews
      llm preview feedback labels
      llm preview feedback <preview_id> <label> [note]

    Dataset export:
      dataset operator
      dataset llm preview
      dataset turns

    Local history:
      save
      history
      last
      journal

    Session:
      help
      quit
    ```

    See:

    - [Command Reference](docs/commands.md)

    ## Testing

    Run the full local test suite:

    ```powershell
    python -m pytest tests
    ```

    Run the local V1 smoke checklist after safety-sensitive CLI or engine changes:

    ```text
    docs/v1_cli_smoke_checklist.md
    ```

    CI currently uses a minimal Windows GitHub Actions workflow:

    ```text
    .github/workflows/windows-pytest.yml
    ```

    The CI goal is intentionally narrow:

    ```text
    Can GitHub reliably run the deterministic unit tests?
    ```

    Live Windows behavior remains validated locally by the Operator.

    ## V1 scope

    In scope for V1:

    - local read-only telemetry
    - deterministic interpretation and planning
    - explicit route policy
    - read-only tool execution
    - confirmation previews for unsafe requests
    - journals, datasets, feedback, audit trails, and memory-layer documentation
    - local optional LLM explanation and route-preview paths
    - contract-shape stability
    - safe CLI operation

    Out of scope until after V1:

    - semantic memory
    - Lighthouse Navigator
    - OS search/open tools
    - UI layer
    - autonomous OS actions
    - custom protocol transport
    - model-directed execution

    ## Development workflow

    Preferred workflow:

    ```text
    feature branch
    -> local tests
    -> pull request
    -> review
    -> merge only when clean
    -> local sync
    -> full PyTest suite
    ```

    Before pushing:

    ```powershell
    git status --short
    python -m pytest tests
    ```

    After merging:

    ```powershell
    git checkout main
    git pull origin main
    python -m pytest tests
    ```
