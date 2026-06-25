\
    # Lighthouse Safety Model

    Lighthouse is designed as a local Windows telemetry and diagnostic assistant,
    not as an autonomous operating-system controller.

    The safety model is built around deterministic authority boundaries.

    ## Core rule

    ```text
    Model output is never execution authority.
    ```

    The model may explain, summarize, or propose a route through a validated
    contract. It may not execute, approve, authorize, or bypass deterministic
    gates.

    ## Authority layers

    ```text
    Operator
      final human authority

    Route Registry
      determines known intents, safety class, command family, autorun eligibility,
      and manual-review requirements

    LLM Contract V0
      validates model proposals and rejects authority-like fields

    Autorun Gate
      permits only ready, known, read-only diagnostic runplan routes

    Tool Registry
      defines which tools exist, their risk levels, and whether they are read-only,
      implemented, targeted, confirmation-gated, or blocked

    Tool Executor
      executes only safe, registered, implemented, read-only, risk-zero,
      non-targeted, non-confirmation tools

    Memory
      provides read-only context and audit evidence, but never authority
    ```

    ## Observe -> Mediate -> Act

    ### Observe

    Lighthouse collects evidence from local, read-only sources such as:

    - system telemetry
    - CPU state
    - memory state
    - disk state
    - process summaries
    - Windows event evidence
    - Windows CIM evidence
    - Windows performance counters

    Observation should not mutate the operating system.

    ### Mediate

    Lighthouse interprets the request through deterministic services:

    - intent classification
    - route registry
    - tool planner
    - target resolver
    - confirmation preview builder
    - memory context retrieval
    - LLM contract validation when model previews are requested

    Mediation decides what is safe to show, plan, or preview.

    ### Act

    V1 action is intentionally narrow:

    - safe read-only diagnostics may run through the tool executor
    - unsafe or OS-changing actions remain preview-only
    - destructive/data-changing actions are blocked or require future explicit
      confirmation design
    - model output cannot directly cause action

    ## Autorun rule

    `talkrun` may auto-run only when every condition is true:

    ```text
    route_ready == true
    route_known == true
    autorun_allowed == true
    manual_review_required == false
    safety_class == read_only_diagnostic
    command_family == runplan
    engine_request is present
    ```

    All other routes are refused for autorun.

    ## LLM boundary

    LLM Contract V0 allows a model to provide:

    ```text
    schema_version
    proposed_intent
    interpreted_request
    confidence
    reasoning_summary
    safety_notes
    ```

    It rejects authority-like fields such as:

    ```text
    command
    recommended_command
    shell_command
    powershell
    tool_name
    tool_args
    execute
    approved
    autorun
    autorun_allowed
    manual_review_required
    permission_granted
    delete_file
    registry_change
    ```

    The route handoff is built by deterministic code after validation.

    ## Memory boundary

    Memory may help recall previous cases, patterns, and context. It may not:

    - decide truth
    - authorize actions
    - override telemetry
    - override the route registry
    - override the tool registry
    - bypass confirmation
    - bypass the Operator

    ## Post-V1 boundary

    These are intentionally deferred until after V1 stabilization:

    - semantic memory
    - file/project navigation
    - OS search/open tools
    - UI layer
    - autonomous actions
    - custom protocol transport
