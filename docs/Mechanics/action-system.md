> [← CLAUDE.md](../../CLAUDE.md)

# Action System

`build_action_library()` returns `dict[str, ActionDefinition]` keyed by action key. **Critical**: always use `loop._action_library[key]`, never call `build_action_library()` independently — `ActionDefinition.id` is a fresh `uuid4()` each call, and `ActionInstance` UUIDs must match the loop's library or they will be silently skipped.

`ActionInstance` fields: `action_definition_id`, `target_type`, `target_id`, `proxius_id`, `intent` (typed union `ActionIntent`).

## Adding a New Action

1. Define the intent class in `core/action_core.py`
2. Add it to the `ActionIntent` union
3. Add an `ActionDefinition` in `build_action_library()`
4. Handle it in `logic/tick_logic._resolve_intent_mutations()`
5. Add to `_validate_and_filter_queue` if needed
6. Add UI prompting in `GameScreen._build_intent()` and/or `_build_intent_params()` in `ui/ui.py`
