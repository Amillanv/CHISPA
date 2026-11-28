# CLAUDE.md

This file gives the essential rules for all work in this repository.
The detail is in `docs/`. Read the applicable file before you work on its subject.

| Subject | File |
|---|---|
| Checked facts and rules for each data source (section 8) | `docs/sources.md` |
| Glossary, stages, data conventions, fusion, evaluation, agent, assumptions (sections 6, 7, 9 to 13) | `docs/method.md` |
| ASD-STE100 writing rules and word list (section 5) | `docs/language.md` |
| Build plan, open decisions and progress | `PLAN.md` |

If a rule and a request are in conflict, tell the owner before you continue.

## Purpose

CHISPA merges fire detections from different sources into one alert for each fire.
Each alert has a confidence level.
CHISPA then measures how good the alerts are against mapped fires.
All the work follows the eight stages of a fire in `README.md`. Each part of an alert has its stage and its measure.

- The first region is the Brazilian Pantanal. We set rules on 2023. 2024 scored the merge. 2025 scores each later part.
- The evaluation is the primary product. The agent and the dashboard show it. They do not replace it.
- The owner must be able to understand each part. A part that the owner cannot understand is a defect.

## Hypothesis

A merged alert finds the same mapped fires earlier than one source alone.
It does this without a larger share of alerts that have no mapped fire.
The 2024 result supports this only in part. `README.md` gives the result.

Each new part gets its own hypothesis before its result. `docs/method.md` section 7.4 gives the rules.
A negative result is a valid result. Publish it the same way as a positive result.

We can calculate fire recall, relative delay and unmatched alert share from recorded data.
We cannot calculate the true goal from recorded data: the minutes to brigade acknowledgment
and the share of alerts that brigades say were worth action. Do not report a value for them.

## Honesty rules

These rules have priority over all other rules.

1. Do not invent data: numbers, coordinates, dates, results or citations.
2. Synthetic data is only for unit tests. Do not put it into a result.
3. Each number in a document must come from a command that a reader can run again.
4. Mark a fact about an external source `UNVERIFIED` until a check against the source confirms it.
5. Give the denominator with each percentage. Give the limits of a result adjacent to the result.
6. Do not use "accurate", "robust", "state of the art", "powerful", "real-time" or "novel". Give the number.
7. An alert with no mapped scar is an "unmatched alert", not a "false alarm".
8. If a test fails, say so. If a step was skipped, say so. If you do not know, say so.
9. Do not change a threshold after you see 2024 results, unless the next result says so.

## Scope

- Now: recorded satellite detections, fusion, evaluation, live operation, the tools, and the parts of the stages:
  visibility, the content of the alert, measured growth, the confidence of the first alert and the growth forecast
  of a front.
- Parked: the MCP server, the agent, the gold questions and the dashboard. Do not change them without the owner.
- Before you write or change a tool, read `docs/method.md` section 12.1. A new tool needs the agreement of the owner.
- Later: delivery by SMS or radio, cameras, community reports and other regions.
- A change of the growth forecast needs a published test against what came, before it goes into an alert.
- Never: a permission to burn, a replacement for official alert systems.
- The first evaluation uses satellite sources only. Say this in each result.

## Language

Write all English text to the ASD-STE100 writing rules: documents, comments, docstrings,
commit messages, log and error messages, dashboard text, prompts and alert text.
`docs/language.md` has the full rules. The essential rules are:

- A maximum of 20 words in an instruction and 25 words in a description.
- One instruction in each sentence. Active voice. Simple tenses.
- One word for one meaning. Use the glossary terms in `docs/method.md` and no synonym.
- Use "must", not "should". Use "make sure", not "ensure". Use "do a check", not "check" as a verb.
- We say "written to the ASD-STE100 writing rules". We do not say "compliant".

## Architecture

```
sources -> data/raw/ -> store -> fusion -> store -> evaluation -> results
              |                                |
              +<-> public bucket               +-> tools -> MCP server, agent -> dashboard
```

- `chispa fetch` gets raw files from a source. `--push` copies new files to the bucket.
- `chispa build` gets absent raw files from the bucket and makes a new store.
- The store is a result. Do not edit it. Change the parser or the raw files, then build again.
- The bucket holds raw files only: no store, no code, no key. A file in the bucket never changes.
- A source module does not import a different source module.
- The fusion never reads burn scars and does not import the evaluation.
- The live path of the growth forecast does not import the evaluation: it loads the saved trees.
- At time T, the fusion uses only detections with `available_at` at or before T.
- The MCP server, the agent and the dashboard contain no logic. They call the tools module.
- All thresholds and estimates are in `config.py` and in no other file.
- The same inputs and the same configuration must give the same outputs.

## Data conventions

- Time: UTC and timezone-aware. Coordinates: WGS84, in the sequence `lat, lon`.
- Units: metres, hectares, megawatts, degrees Celsius, kilometres per hour.
- Put the unit in the name: `radius_m`, `frp_mw`, `wind_kmh`.
- Use `None` for a missing value. Do not use 0, -1 or an empty string.
- Each source module returns `Detection` records with the fields in `models.py` and no others.

## Code standards

- Python 3.12. `ruff` for format and lint. `pytest` for tests. Type hints on each signature.
- Plain functions and dataclasses. One process. One SQLite file. No ORM. No JavaScript build step.
- Prefer the standard library. Each dependency has a comment in `pyproject.toml` with its reason.
- A function does one thing and has a maximum of 40 lines and 5 arguments.
- A Python file has a maximum of 300 lines.
- No `utils.py`, `helpers.py` or `common.py`. No global mutable state.
- No abstraction before the second use. No flag or parameter for a use that does not exist.
- Each module starts with a docstring: what it does and why it exists.
- A comment gives the reason, not the action. No commented-out code. No `TODO` in code.
- Fail early with a message that says what to do. Do not catch an error that you cannot correct.
- Validate data at the edges: when a source module parses a file and when a tool gets arguments.
- When new code replaces old code, delete the old code. Keep no compatibility layers.

## Tests

- Do a test of behaviour, not of implementation.
- The fusion and the evaluation have small cases that a person can calculate on paper.
- Source parsers have tests against small real files in `tests/samples/`.
- Tests do not use the network and run in less than 30 seconds.

## Documents

- The permitted Markdown files are `CLAUDE.md`, `README.md`, `PLAN.md`, the three files in `docs/`
  and `results/SUMMARY.md`. Code makes `results/SUMMARY.md`. Do not edit it by hand.
- A fact is in one document only. Other documents give a link.
- When the code changes, update the documents in the same step.
- `README.md` describes what exists now. `PLAN.md` gets shorter as the work progresses.
- When a plan step is complete, remove its detail.

## Security

- Keys are only in `.env`, which git ignores. Keep keys out of error messages and logs.
- Do not store or publish personal data from a community report.
- Do not let text from a report or a tool result go to the model as an instruction.
- Add a rate limit to the agent route before public deployment.

## Session rules for Claude

1. At the start, read this file and `PLAN.md`. Tell the owner which step is next.
2. Do one plan step at a time.
3. Explain a new concept in a few sentences before you write code for it.
4. Prefer the smallest change that completes the step.
5. Run the tests and the lint before you say that a step is complete.
6. Show real output for each result. Read the full output of a background run before you report it.
7. Record each new checked fact in `docs/sources.md` with the date of the check.
8. Write a problem that is not part of the step in `PLAN.md`. Do not correct it now.
9. At the end, update the progress in `PLAN.md`. Do not write a session summary file.

Stop and ask the owner before you:

- Add a dependency, a file in the repository root or a Markdown file.
- Change an honesty rule, a fusion rule or an evaluation rule.
- Download more than 1 GB, call an API that costs money, deploy or publish.
- Use `--push` for a source whose terms are not confirmed.
- Commit. Commit only when the owner asks.

Stop and tell the owner if you see a sign of drift:

- A file is larger than its budget, or two modules do the same thing.
- A document repeats a different document.
- A result has no command that makes it again.
- The work in progress is not in `PLAN.md`.

## Size budgets

| Item | Budget |
|---|---|
| `CLAUDE.md` | 200 lines |
| `README.md` | 200 lines |
| `PLAN.md` | 400 lines |
| Python file | 300 lines |
| Function | 40 lines, 5 arguments |
| Tools for the agent | 6 |
| Runtime dependencies | 10 |

A budget is a signal, not a target. If a budget is exceeded, simplify first.
