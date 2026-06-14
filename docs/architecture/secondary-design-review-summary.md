# Secondary Design Review Summary

This note records the accepted project-context summary from the Lighthouse Telemetry secondary research/design thread.

## Relationship to the main build path

The main build path remains the source of truth for implementation, code changes, tests, errors, and milestones.

The secondary thread is used for research, architecture discussion, tool design, model choices, future features, and parking-lot ideas.

Any decision made in the secondary thread must be summarized clearly before being carried back into the main build path.

## Architecture direction

Lighthouse should follow an Observe -> Mediate -> Act architecture.

### Observe

Read-only telemetry collectors gather system state.

Examples:

- System snapshot
- CPU usage
- Memory usage
- Disk usage
- Process state
- Windows event signals
- Crash and stability indicators

### Mediate

The planner, tool registry, memory context, and policy rules classify intent, select valid tools, identify risk, and decide whether an action is allowed.

The model is the reasoning and conversation layer, not the authority layer.

### Act

Only approved tools may touch the operating system.

Any mutating action must require explicit Operator confirmation before execution and must write to an audit/action journal afterward.

## Confirmed architectural rules

1. Lighthouse must not receive raw terminal or unrestricted OS access.
2. The model is the reasoning/conversation layer, not the authority layer.
3. The Tool Registry is the only approved path to OS action.
4. Read-only telemetry can run freely.
5. Mutating tools require structured confirmation previews.
6. Destructive or ambiguous requests should default to safe inspection first.
7. Memory supports context and case recall, but it is not an authority source.
8. The Operator remains in command.

## Accepted future improvements

- Add structured confirmation preview objects for mutating tools.
- Add action journal/audit logging for tool execution.
- Add memory schema hardening and log rotation before adding vector search.
- Defer async/background telemetry until the backend engine is stable.
- Defer WinUI/native dashboard until CLI, tool registry, and safety gates are reliable.

## Preferred framing

Lighthouse is an Operator-controlled, permission-gated local OS assistant.

## Avoided framing

Lighthouse should not be described as an autonomous OS agent with independent authority over the computer.

## Lead-engineer conclusion

The useful value of the secondary review is not to add more technology immediately. Its value is to confirm the core foundation:

- Deterministic telemetry
- Strict mediation
- Permission-gated action
- Operator authority
- Auditable execution

This direction should remain central as Lighthouse moves from read-only diagnostics toward safe maintenance tooling.
