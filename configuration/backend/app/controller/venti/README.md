# Venti Controller README

This document explains the current fan controller code in `configuration/backend/app/controller/venti/`.

## Goal

The controller decides whether the fan should be `on` or `off` based on:

- manual mode
- overheat protection
- stock building
- drying conditions
- interval ventilation
- optional self-learning drying logic

The current implementation supports two drying strategies:

- `classic`: old proven rule behavior
- `self-learning`: same basic drying start rule, plus efficiency evaluation and restart blocking after a bad drying run

At the moment, `self_learning_enabled` is set to `False` in [control_data.py](/home/pi/Projects/venti/configuration/backend/app/services/control_data.py:175), so the system currently runs in `classic` mode.

## Main Files

- [controller.py](/home/pi/Projects/venti/configuration/backend/app/controller/venti/controller.py:1)
  Main control loop. Builds the context, evaluates the decision, sends the command, persists state, and publishes events.
- [context.py](/home/pi/Projects/venti/configuration/backend/app/controller/venti/context.py:1)
  Converts raw control data into a structured `VentiContext`.
- [efficiency/drying_decision_engine.py](/home/pi/Projects/venti/configuration/backend/app/controller/venti/efficiency/drying_decision_engine.py:1)
  Contains the drying decision logic for both `classic` and `self-learning`.
- [efficiency/drying_efficiency_engine.py](/home/pi/Projects/venti/configuration/backend/app/controller/venti/efficiency/drying_efficiency_engine.py:1)
  Calculates drying efficiency over the configured history window.
- [control/state_manager.py](/home/pi/Projects/venti/configuration/backend/app/controller/venti/control/state_manager.py:1)
  Stores controller runtime state, adaptive threshold state, and the last bad drying snapshot.
- [services/control_data.py](/home/pi/Projects/venti/configuration/backend/app/services/control_data.py:1)
  Reads live data from Influx and builds the input dictionary for `VentiContext`.

## High-Level Flow

`venti_control()` in [controller.py](/home/pi/Projects/venti/configuration/backend/app/controller/venti/controller.py:81) does this:

1. Restore the previous controller state from Influx through `state_manager.restore()`.
2. Load all live data with `build_control_data()`.
3. Build a `VentiContext`.
4. Compute efficiency metrics with `DryingEfficiencyEngine`.
5. Ask `DryingDecisionEngine` for the current `Decision`.
6. Send the command with `venti_cmd(decision.command)`.
7. Persist state changes with `state_manager.persist(...)`.
8. Publish logs, transition events, alerts, and summaries.

## Context Inputs

`VentiContext` collects all values the controller needs:

- mode: `auto`, `on`, or other non-auto state
- probe values: `sDefMin`, `tsMin`, `tempMax`, `humMax`
- outdoor values: `sDefOut`
- rule parameters:
  - `sdef_on`
  - `sdefMinThreshold`
  - `sdef_hys_half`
  - `ts_hys_half`
  - `intervall_on`
  - `intervall_time`
  - `intervall_duration`
  - `uschutz_on`
  - `uschutz_hys`
- runtime values:
  - `remainingTimeStock`
  - `remainingTimeInterval`
  - `remainingTimeIntervalOn`
  - `remainingTimeIntervalDiff`
  - `fan_runtime_current`
- self-learning values:
  - `efficiency_window`
  - `base_min_efficiency_threshold`
  - `good_drying_level`
  - `efficiency_learning_up`
  - `efficiency_learning_down`
  - `self_learning_enabled`

Derived flags are also built in [context.py](/home/pi/Projects/venti/configuration/backend/app/controller/venti/context.py:1):

- `overheat`
- `drying_conditions_met`

The current drying start condition is:

- `sDefOut >= sdefMinThreshold + sdef_hys_half`
- `sDefOut >= sdef_on + sdef_hys_half`
- `tsSoll >= tsMin + ts_hys_half`

## Decision Order

The decision order is implemented in [drying_decision_engine.py](/home/pi/Projects/venti/configuration/backend/app/controller/venti/efficiency/drying_decision_engine.py:5).

The global order is:

1. Manual `on` override
2. Other non-auto mode => fan `off`
3. Overheat protection
4. Stock building
5. Drying branch
6. Interval ventilation
7. Auto idle

This matches the old working `if / elif / else` logic closely.

## Classic Mode

Classic mode is used when `ctx.self_learning_enabled == False`.

Classic behavior in [drying_decision_engine.py](/home/pi/Projects/venti/configuration/backend/app/controller/venti/efficiency/drying_decision_engine.py:64):

- If drying conditions are met => `DRYING_ACTIVE`
- Else if interval conditions are met => `INTERVAL_ACTIVE`
- Else if drying is not possible after stock building => `AUTO_IDLE`
- Else => `AUTO_IDLE`

Important point:

- Classic mode does not use efficiency to decide if drying should stop.
- Classic mode still computes efficiency for logging and visibility, but the fan logic stays parameter-driven.

This is the current active behavior.

## Self-Learning Mode

Self-learning mode is used when `ctx.self_learning_enabled == True`.

Self-learning behavior in [drying_decision_engine.py](/home/pi/Projects/venti/configuration/backend/app/controller/venti/efficiency/drying_decision_engine.py:117):

1. Use the same drying start rule as classic mode.
2. Before restarting drying, check whether conditions are better than the last bad drying run.
3. If the fan is newly starting, allow `DRYING_ACTIVE`.
4. While runtime is below `efficiency_window`, keep drying active in `startup_window`.
5. After enough runtime, compare efficiency against `min_efficiency_threshold`.
6. If efficiency is too low => `INEFFICIENT_DRYING`
7. Otherwise => continue `DRYING_ACTIVE`

This means self-learning is not supposed to invent a new start rule. It uses the classic start rule, then adds intelligence later in the drying run.

## Efficiency Model

The efficiency model is in [drying_efficiency_engine.py](/home/pi/Projects/venti/configuration/backend/app/controller/venti/efficiency/drying_efficiency_engine.py:1).

Current formula:

- `sdef_gain = ctx.sDefMin - ctx.sDef_2h_ago`
- `ts_gain = ctx.tsMin - ctx.ts_2h_ago`
- `weighted_gain = sdef_gain + ts_weight * ts_gain`
- `efficiency = weighted_gain / window_hours`

Important detail:

- the model compares probe values with historical probe values
- it does not mix outdoor `sDefOut` with historical probe values

That was a bug before and has already been corrected.

## State Manager

The `ControlStateManager` in [state_manager.py](/home/pi/Projects/venti/configuration/backend/app/controller/venti/control/state_manager.py:6) is responsible for:

- restoring the last persisted controller state
- keeping the last state, command, mode, details, and timestamp
- keeping the adaptive threshold for self-learning
- remembering the last bad drying snapshot
- checking if new retry conditions are better than the last failed drying attempt

### Last Bad Drying Snapshot

When self-learning stops a run as `INEFFICIENT_DRYING`, `evaluate()` in [controller.py](/home/pi/Projects/venti/configuration/backend/app/controller/venti/controller.py:29) calls:

- `state_manager.remember_bad_drying(...)`

That snapshot contains values like:

- `sDefOut`
- `sDefMin`
- `sDefDiff`
- `tsMin`
- `tsSoll`
- `tsDiff`
- `efficiency`
- `sdef_change_2h`
- `ts_change_2h`

Later, before a restart, self-learning calls:

- `state_manager.retry_conditions_improved(ctx)`

This blocks restart until the new situation is better than the previous bad run.

Current comparison logic is:

- `sDefOut` better than before, or
- `sDefDiff` better than before, or
- `tsDiff` better than before

and at the same time:

- `sDefDiff` must not be worse
- `tsDiff` must not be worse

The hysteresis values are used as the minimum improvement step.

## Auto-Off Behavior

The old "disable auto after long off-time and near target TS" behavior is still preserved in [controller.py](/home/pi/Projects/venti/configuration/backend/app/controller/venti/controller.py:41).

If all of these are true:

- mode is `auto`
- decision command is `off`
- stock building is finished
- `remainingTimeInterval >= 7200`
- `tsSoll - tsMin <= 0.5`

then:

- `venti_auto("off", ctx.tsSoll, "0")`

This mirrors the old behavior from `test_old.py`.

## Persistence and Events

The controller stores state changes in Influx using:

- `write_controller_state(...)`

The persisted payload includes:

- `state`
- `command`
- `mode`
- `details_json`

Transition and log messages are then built from this state and sent through the event system.

## Current Defaults

In [control_data.py](/home/pi/Projects/venti/configuration/backend/app/services/control_data.py:170), the important current defaults are:

- `efficiency_window = 2h`
- `self_learning_enabled = False`
- `base_min_efficiency_threshold = 0.25`
- `good_drying_level = 0.35`

## Current Status Summary

Right now the controller is in this state:

- classic mode is the active path
- classic mode should behave close to the old working logic
- self-learning mode exists, but is disabled by default
- self-learning uses the same drying start rule as classic
- self-learning adds:
  - efficiency-based stop detection
  - adaptive threshold handling
  - memory of the last bad drying run
  - restart blocking until conditions improve

## Suggested Next Step

The next practical step would be to make `self_learning_enabled` a real user parameter instead of a hardcoded value in [control_data.py](/home/pi/Projects/venti/configuration/backend/app/services/control_data.py:175). Then you could switch between:

- stable classic mode
- experimental self-learning mode

without editing code.
