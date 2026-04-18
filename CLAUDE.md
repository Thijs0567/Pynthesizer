# CLAUDE.md

## Project
Build a Python software synthesizer. Priorities: correct audio behavior, low latency, clear module boundaries, small diffs, and tests that catch regressions early.

## Operating rules
- Before coding, scan only the files needed for the task.
- Prefer the smallest valid change.
- Do not rewrite unrelated code.
- Ask one concise clarification only if requirements block progress.
- When possible, implement one vertical slice at a time.
- Keep reasoning brief and output concise.

## Token-use rules
- Use this file as the default source of project context.
- Put detailed conventions in focused files under `/docs` or `/guides`.
- Read extra files only when they are directly relevant.
- Summarize findings in 3-5 bullets before editing large areas.
- Avoid repeated explanations across turns.
- Prefer file names, symbols, and line references over long paraphrases.

## Workflow
1. Inspect the minimum set of files needed.
2. State a short plan.
3. Edit only the files required for the task.
4. Run the narrowest useful test or demo.
5. Report what changed, what was verified, and any follow-up risks.

## Architecture conventions
- Keep DSP, UI, MIDI, presets, and persistence separated.
- Put pure signal generation in isolated modules.
- Keep audio-thread code allocation-light and deterministic.
- Avoid hidden globals unless they are truly shared runtime state.
- Prefer explicit data flow over clever abstractions.

## Synth rules
- Preserve sample-rate awareness everywhere.
- Treat note on/off, envelopes, filters, LFOs, and modulation paths as first-class units.
- Keep oscillator, envelope, filter, voice, and mixer logic testable in isolation.
- Any change that affects audio output should include a reproducible check or test.
- If adding a feature, define its signal path first, then its controls, then its UI.

## Performance rules
- Avoid per-sample Python object churn where possible.
- Prefer NumPy or vectorized paths only when they reduce complexity without harming realtime behavior.
- Measure before optimizing.
- Keep the audio callback path short.

## Testing
- Add or update tests near the code you change.
- Prefer deterministic tests for envelopes, filters, tuning, MIDI parsing, voice allocation, and preset loading.
- For audio changes, include a small golden-check or property test when practical.
- If tests are slow, run the smallest targeted subset first.

## File guidance
- `docs/architecture.md`: system structure and module responsibilities.
- `docs/audio-path.md`: signal flow, sample rate, latency, realtime constraints.
- `docs/testing.md`: test strategy and known edge cases.
- `docs/todo.md`: active work, bugs, and future ideas.
- Keep `CLAUDE.md` short; move details out of it.

## Output format
When responding to tasks, use:
- Plan:
- Changes:
- Verification:
- Risks:

## Definition of done
A task is done only when:
- The code is minimal and coherent.
- Relevant tests pass or are listed clearly if not run.
- The change matches the requested behavior.
- No unrelated files were modified.