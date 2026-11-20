# Method

This file gives the glossary, the data conventions and the rules for the fusion, the evaluation and the agent.
The section numbers are fixed. Other files refer to them.

## 6. Glossary

Use each term only with this meaning.

| Term | Meaning |
|---|---|
| Detection | One observation of a possible fire from one sensor at one time. |
| Hotspot | A detection from a satellite thermal sensor. |
| Source | A provider of detections, for example FIRMS or INPE. |
| Sensor family | One type of instrument: VIIRS, MODIS, ABI, AVHRR, camera or person. |
| Event | A group of detections that Chispa assigns to one fire. |
| Alert | The message that Chispa makes for an event. One event has one alert. |
| Confidence level | LOW, MEDIUM or HIGH. Section 10.3 gives the rules. |
| Burn scar | A connected area that MapBiomas Fogo maps as burned in one month. |
| Matched alert | An alert that agrees in space and time with a burn scar. |
| Unmatched alert | An alert with no burn scar that agrees. |
| Scar recall | Scars with a minimum of one matched alert, divided by all scars. |
| Relative delay | First alert time minus first detection time from all sources. |
| Footprint | The ground area that one detection can represent, as a radius in metres. |
| FRP | Fire radiative power, in megawatts. A measure of fire intensity. |
| AOD | Aerosol optical depth. We use it as the measure of smoke level. |
| Smoke level | A class of AOD: CLEAR, MODERATE or HEAVY. |
| Development period | 2023. We set thresholds on this period. |
| Test period | 2024. We report results on this period. |
| Replay | A run that gives recorded detections to the fusion in time sequence. |
| As-of time | The time that a replay or a question uses as "now". |
| Gold question | A question for the agent with a known correct answer. |
| Brigade | A team that fights fires on the ground. |
| Acknowledgment | The signal from a brigade that it received an alert. |
| Burn conditions | The weather-based class for a planned burn: LOW, ELEVATED or EXTREME risk. |

## 9. Data conventions

### 9.1 Units and formats

- Time: UTC, timezone-aware, ISO 8601 in text. Convert to local time only in the display.
- Coordinates: WGS84 decimal degrees.
- Coordinate sequence: `lat, lon` in function arguments and in text. Write a comment where a library uses `lon, lat`.
- Distance: metres in code. Kilometres are permitted in the display.
- Area: hectares.
- FRP: megawatts.
- Temperature: degrees Celsius. Wind speed: kilometres per hour. Relative humidity: percent.
- Put the unit in the name of each variable that has a unit: `radius_m`, `frp_mw`, `wind_kmh`.

### 9.2 The detection record

Each source module returns records with these fields and no others.

| Field | Type | Meaning |
|---|---|---|
| `source` | text | Provider name: `firms`, `noaa`, `inpe`. |
| `sensor_family` | text | `viirs`, `modis`, `abi`, `avhrr`, `camera`, `person`. |
| `platform` | text | The satellite or device name. |
| `observed_at` | time | The time of the observation. |
| `available_at` | time | The time when the source published the detection. |
| `lat`, `lon` | number | The centre of the detection. |
| `footprint_m` | number | The radius of position uncertainty. |
| `frp_mw` | number or none | Fire radiative power. |
| `source_confidence` | text | `low`, `nominal` or `high`, mapped from the source value. |

`available_at` is important.
A satellite observation is not available at the moment of the observation.
If a source does not give the publication time, use a fixed delay from `config.py` and say so in the results.

### 9.3 Missing values

- Use `None` for a missing value. Do not use 0, -1 or an empty string.
- Do not fill a missing value with an estimate, unless the function name says that it makes an estimate.

## 10. Fusion rules

### 10.1 Principles

- The fusion is deterministic. It has no random step and no trained model in the first version.
- The fusion is causal. At time T it uses only detections with `available_at` at or before T.
- A person must be able to explain each alert from its detections and the rules.

### 10.2 Deduplication

1. Two detections with the same platform, the same `observed_at` and almost the same position are one observation. Keep one.
2. A detection joins an event if it is near in space and near in time to the event.
3. "Near in space" uses the footprints of the two detections plus a margin from `config.py`.
4. "Near in time" uses a time window from `config.py`.
5. If a detection is near to two events, the two events merge. Keep the older identifier.
6. If a detection is near to no event, it starts a new event.

### 10.3 Confidence level

The first version uses rules, not a model.

- Count independent evidence by sensor family and by observation time, not by source.
- The same satellite pass from two sources is one item of evidence.
- LOW: one item of evidence with low or nominal source confidence.
- MEDIUM: a high source confidence, or a second observation from the same sensor family.
- HIGH: observations from two or more sensor families.

These rules are a first proposal. Tune them only on the development period.
A confidence level is useful only if HIGH alerts match scars more frequently than LOW alerts.
The evaluation must report the matched share for each level.

### 10.4 Alert content

An alert contains:

- An identifier.
- The centre and the radius of the event.
- The time of the first detection and of the last detection.
- The confidence level and the evidence that gave that level.
- The largest FRP, if available.
- The list of detection identifiers.

The short alert text must be plain ASCII and must fit in 160 characters.
This lets the same text go through SMS and voice radio.

## 11. Evaluation rules

### 11.1 No look-ahead

- The fusion never reads burn scars.
- The evaluation runs after the fusion completes.
- The replay gives detections in `available_at` sequence.

### 11.2 Development period and test period

- Set all thresholds on 2023.
- Freeze the configuration. Record its hash.
- Run the 2024 evaluation one time for each frozen configuration.
- Record each 2024 run in `results/`, with the configuration hash and the date.
- If you change a threshold after a 2024 run, the next result must say so.

### 11.3 Burn scar units

- A burn scar is a connected group of burned pixels in one month.
- Ignore scars smaller than the minimum area in `config.py`. Report how many scars this removes.
- Report results by scar size class, by count and by area.

### 11.4 Match rule

An alert matches a burn scar if these two conditions are true:

- The alert centre is in the scar, or nearer than the alert radius to the scar.
- The first detection of the alert is in the scar month, plus or minus the margin in `config.py`.

One scar can match many alerts. One alert can match many scars.
Count a scar one time in scar recall. Count an alert one time in the unmatched share.

### 11.5 Why "unmatched" is not "false"

An alert with no mapped scar can be a real fire.
Possible causes are:

- The fire was too small for a 30 m map.
- Clouds or smoke hid the scar from Landsat.
- The fire was stopped quickly.
- MapBiomas did not map the scar.
- The detection was an industrial heat source or sun glint. Only this cause is a true false alarm.

Report the unmatched share. Do not call it the false alarm rate.

### 11.6 Delay

- MapBiomas gives the month, not the minute.
- Thus the reference time for an event is the first detection from all sources.
- Relative delay for a configuration is its first alert time minus the reference time.
- Calculate the delay two times: one time with `observed_at` and one time with `available_at`.
- The `available_at` number is the honest number for operations.

### 11.7 Baselines

Each result table must contain these rows:

- Each source alone.
- Each sensor family alone.
- All sources merged.

The merged row has value only in comparison with the best single row.

### 11.8 Smoke level

- Get AOD for the event position and time.
- Assign CLEAR, MODERATE or HEAVY with the limits in `config.py`.
- Report each measure by smoke level.
- AOD comes from a coarse model. It is an estimate of smoke, not a measurement at the fire.

### 11.9 Result format

- One command makes all result tables.
- Each table is a CSV file in `results/` with a header that gives the configuration hash.
- `results/SUMMARY.md` is generated by code. Do not edit it by hand.
- Give counts adjacent to shares. Give the median and the 90th percentile for delays.

## 12. Agent and MCP rules

### 12.1 Tools

- Keep the number of tools small. The target is six or fewer.
- Each tool is one function in `tools.py` with typed arguments and a typed return value.
- Each tool returns data with units, times and source names.
- The MCP server and the agent expose the same functions. Do not write a tool two times.

### 12.2 Answers

The agent must:

1. Answer only from tool results.
2. Give the time and the source of each number.
3. Say when the data is old. Give the age of the newest detection.
4. Say "no detection" and not "no fire". A satellite does not see through thick cloud.
5. Give intensity as FRP in megawatts, with the sensor name.
6. Give growth as the change in event radius between two times. Call it "measured growth", not "spread rate forecast".
7. Refuse to estimate a value that no tool gives.

### 12.3 Burn questions

"Is it safe to burn tomorrow?" is a question with risk to life.

- Do not answer "safe" or "yes".
- Give the burn conditions class and the weather values that gave it.
- Give the active alerts near the position.
- Say that the answer is not an authorization, and that local law can prohibit burns.
- If the forecast is not available, say so and give no class.

### 12.4 Model

- The model name is a value in `config.py`.
- The system prompt is one file. It is written to the STE writing rules.
- Do not put instructions for the model in tool results.

### 12.5 Gold questions

- Each gold question has an as-of time. The answer comes from the recorded store, thus it does not change.
- Each gold question lists the tool calls that are necessary and the facts that the answer must contain.
- Each gold question can list text that the answer must not contain.
- Grade with code first. Use a model as a judge only where code cannot grade, and report the two scores separately.
- Include questions where the correct answer is "I do not know" or a refusal.
