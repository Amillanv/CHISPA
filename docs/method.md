# Method

This file gives the glossary, the data conventions and the rules for the fusion, the evaluation and the agent.
Section 13 gives the assumptions behind the rules, with the reason and the pitfall of each.
The section numbers are fixed. Other files refer to them.

## 6. Glossary

Use each term only with this meaning.

| Term | Meaning |
|---|---|
| Detection | One observation of a possible fire from one sensor at one time. |
| Hotspot | A detection from a satellite thermal sensor. |
| Source | A provider of detections, for example FIRMS or INPE. |
| Sensor family | One type of instrument: VIIRS, MODIS, ABI, AVHRR, camera or person. |
| Event | A group of detections that CHISPA assigns to one fire. |
| Alert | The message that CHISPA makes for an event. One event has one alert. |
| Confidence level | LOW, MEDIUM or HIGH. Section 10.3 gives the rules. |
| Burn scar | A connected area that MapBiomas Fogo maps as burned in one month. |
| Fire | A group of burned cells that touch and burned in near days. Section 11.3 gives the rule. |
| Counted fire | A fire of the minimum area in `config.py` or more. |
| Isolated fire | A counted fire that shares no detection with a different counted fire. |
| Match | A detection matches a fire if it agrees with the fire in space and time (section 11.4). |
| Unmatched alert | An alert with no detection that matches a fire. |
| Unmatched share | The detections that match no fire, divided by all detections of a configuration. |
| Fire recall | The counted fires with a minimum of one match, divided by all counted fires. |
| Relative delay | The first match of a configuration minus the first match from all sources, for one fire. |
| Purity | The share of the matches of an event that are on its main fire. A low value shows that the fusion merged fires. |
| Completeness | The share of the matches of a fire that are in its main event. A low value shows that the fusion split a fire. |
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

### 10.2 Deduplication and events

The fusion uses a grid of cells of approximately 550 m.

1. A detection occupies the cells of a square: its footprint plus a margin, on each side of its centre.
2. A cell remembers the event that occupied it last, and the observation time.
3. A detection joins an event if it occupies a cell of that event, and the two observation times are in the time window.
4. If a detection joins two or more events, the events merge. The oldest identifier stays.
5. If a detection joins no event, it starts a new event.
6. The grid makes the join distance approximate by up to one cell.

The fusion does not delete a detection that two sources give. It counts the two as one pass (section 10.3).
The cell size, the margin and the time window are in `config.py`.

Known limit, found on 2023: large fires chain into very large events.
The largest 2023 event has 275 200 of 1 000 362 detections, lasts 25 days and spans 112 km by 169 km.
Thus "one event" is not always "one fire". The evaluation must use the position of each detection, not the event centre.

### 10.3 Confidence level

The first version uses rules, not a model.

- An item of evidence is one pass of one platform over the event.
- Detections of one platform are one pass if their times are not farther apart than the pass gap in `config.py`.
- For GOES, a pass is one scan. We move each GOES time back to the start of its 10 minute scan.
- Thus the same pass from FIRMS and from INPE is one item of evidence.
- LOW: one pass with low or nominal source confidence.
- MEDIUM: a high source confidence, or two or more passes of one sensor family.
- HIGH: passes from two or more sensor families.

These rules are a first proposal. Tune them only on the development period.
A confidence level is useful only if HIGH alerts match fires more frequently than LOW alerts.
The evaluation must report the matched share for each level.

### 10.4 Fusion output

The command `chispa fuse --year` writes three tables.

- `events`: one row for each event at the end of the year: times, number of detections, mean position, bounding box, largest FRP, level, sensor families and number of passes.
- `alerts`: one row for each change of the level of an event, with the time when the change became available.
- `memberships`: one row for each detection: its event, and the level of the event immediately after that detection.

The `memberships` table lets the evaluation ask: "When did an alert of a given level first have a detection at this place?"

The short alert text is not built. It must be plain ASCII and must fit in 160 characters.
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
- The table `merge_gain` came after the first 2024 run of 2026-11-21. It changed no threshold and no number of the other tables.

### 11.3 Fires

A burn scar is a connected group of burned pixels with one map month.
The map cuts one fire into many scars, because it splits a burn by the month of the image.
Thus the unit of the evaluation is the fire, not the scar. The command `build` makes the fires:

1. Each burned pixel gets the burn day of its cell of approximately 445 m (MCD64A1). `build` reads the day of the map month, or of the month before.
2. Two cells that touch, also at a corner, are one fire if their first burn days are not more than the day margin apart.
3. A pixel with no burn day goes to the fire that holds most of the dated pixels of its scar.
4. A scar with no dated pixel is one fire. That fire has only the map month.

- The burn scar map stays the truth for where. The burn day product says only when.
- Count only fires of the minimum area in `config.py` or more. Report how many fires that is.
- Report results by fire size class, by count and by area.
- In 2023 the 66 349 scars make 29 210 fires. 969 fires have 10 hectares or more, and 382 of those have burn days.

### 11.4 Match rule

The match is between a detection and a fire, not between an event and a fire.
An event can be very large, thus its centre says little.

A detection matches a fire if these two conditions are true:

- Space: a pixel of the fire is in the square of the detection footprint plus the margin in `config.py`.
- Time: the fire burned near the time of the detection.

The time condition has two forms:

- A fire with burn days: the day of the detection is from the first burn day of the fire minus the day margin, to the last burn day plus the day margin.
- A fire with no burn day: the detection is in the map month or in the month before it. It is not in the month after it.

One fire can match many detections. One detection can match many fires.
Only detections in the biome border count. Only fires in the biome border exist in the store.
A merged row uses the level of the event immediately after each detection (table `memberships`).

### 11.5 Why "unmatched" is not "false"

An alert with no mapped scar can be a real fire.
Possible causes are:

- The fire was too small for a 30 m map.
- Clouds or smoke hid the scar from Landsat.
- The fire was stopped quickly.
- MapBiomas did not map the scar.
- The detection was an industrial heat source or sun glint. Only this cause is a true false alarm.

Report the unmatched share. Do not call it the false alarm rate.
The precision against the map is 1 minus the unmatched share. It is a lower limit of the true precision.

### 11.6 Delay

- No source gives the start time of a fire. The burn day is uncertain by some days.
- Thus the reference time for a fire is the first detection from all sources that matches the fire.
- Relative delay for a configuration is its first matched detection time minus the reference time.
- Calculate the delay two times: one time with `observed_at` and one time with `available_at`.
- The `available_at` number is the honest number for operations. It depends on the delay estimates in `config.py`.

Only isolated fires give a delay.
A sensor with a large footprint reaches the fires near its fire. Then it seems to see each of them early.
For an isolated fire, each detection that matches it matches no other counted fire, for each footprint size.
Each result row gives the number of isolated fires that it used (`delay_fires`). The sample is small.

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

The tables are:

- `configurations`: fire recall, area recall, unmatched share and delay for each source, sensor family and merged level.
- `fire_sizes`: fire recall for each configuration and fire size class.
- `fire_events`: for each fire size class, into how many events the fusion split a fire, and the completeness.
- `events`: for each final level, the share of events that match a fire, how many counted fires one event holds, and the purity.
- `merge_gain`: for each sensor family and fire size class, the fires that only the merge finds, and the isolated fires that the family finds later than the merge.

Purity and completeness count matches with counted fires. A detection that matches two fires counts two times.

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

## 13. Assumptions and decisions

Each row gives one choice, its reason and its pitfall. The values are in `config.py`.
The numbers behind the reasons are in the sections that the rows name. This section does not repeat them.
When a choice changes, change its row in the same step.

### 13.1 Ground truth

| Choice | Reason | Pitfall |
|---|---|---|
| The MapBiomas map says where a fire burned. | It is a published map of 30 m from Landsat. Its model does not use hotspots (section 8.5). | It does not map small burns. It has commission errors in wetlands and dry lagoons. |
| The MCD64A1 product says when a pixel burned. | It is the only source of a burn day. The day comes from reflectance, not from a hotspot (section 8.9). | Its pixels are 463 m. The day is uncertain by some days. Small scars frequently have no burn day. |
| The unit is a fire: burned cells that touch and have burn days not more than 7 days apart. | A scar is not a fire: the month split cuts one fire into many scars. | Fires that burn into each other are one fire. A fire can be very large and counts one time. |
| The limit between two fires is the day margin of the match. | We cannot divide in time what we cannot match in time. | A different limit gives a different number of fires. |
| A scar with no burn day stays a fire with only a month. | We have no day to group it. | These fires are small and many. By count they weigh as much as a very large fire. |
| The day margin is 7 days. | Two burn day products agree to 7 days for 95 percent of cells (section 8.9). | A detection of a different fire, near in space and in these days, can match. |
| A fire matches from its first burn day to its last burn day. | One time range for each fire is simple. | A fire that burned for many days matches a detection in each of those days, at each place. |
| A fire with no burn day uses its month and the month before. | The map month is almost never before the burn, and frequently one month after it (section 8.9). | A burn two months before the map month does not match. A January fire loses its December detections. |
| Fire recall counts fires of 10 hectares or more. | Most smaller fires are scars with no burn day: pieces from the month split. | The results say nothing about small fires. |
| Only the biome border in Brazil counts. | MapBiomas Fogo for Brazil does not map Bolivia and Paraguay. | The results are not for the full Pantanal. |
| We tune on 2023 and score on 2024. | A threshold that saw the test data gives a result that is too good. | The two years are different: 2024 has more than three times the burned area (section 8.5). |

### 13.2 Detections

| Choice | Reason | Pitfall |
|---|---|---|
| Satellites are the only sources. | We have no recorded camera data or community reports. | The results do not show what the other sensor families add. |
| `available_at` is `observed_at` plus a fixed delay for each sensor family. | No source gives its publication time. | The delays are estimates. Each result that uses `available_at` depends on them. |
| The archive files stand for the live files. | The live files of 2023 and 2024 do not exist now (section 8.1). | A live detection can be different or absent. |
| GOES has only the mask classes 10, 11, 30 and 31, all as "nominal". | FIRMS gives only these classes (section 8.2). | A live system can read the low-probability classes. We cannot measure their effect. |
| The footprint of GOES and of each INPE sensor is one fixed radius. | The sources give no pixel size for these detections. | A real pixel changes with the view angle. The radius changes the fusion and the match. |
| One pass that FIRMS and INPE give is one item of evidence. | The two sources read the same instrument at the same time. | Two sensor families are not fully independent: a hot surface can deceive the two. |

### 13.3 Fusion

| Choice | Reason | Pitfall |
|---|---|---|
| The replay uses the `available_at` sequence. | An alert must use only what a brigade could know at that time. | See the `available_at` row in section 13.2. |
| A detection occupies a square: its footprint plus a margin, on cells of approximately 550 m. | It is simple and quick, and a person can calculate it. | The join distance is approximate. A sensor with a large footprint joins more. |
| The time window is 24 hours. | A polar-orbit satellite sees a fire that continues a minimum of one time in 24 hours. | A large fire that continues becomes one very large event (section 10.2). |
| The level counts passes and sensor families. | It needs no trained model, and a person can explain each alert. | An event that lasts long becomes HIGH. HIGH does not mean a large or dangerous fire. |
| The cell size, the margin and the time window stay at their first values. | On 2023, smaller cells, smaller margins and shorter windows did not increase the purity. To do this check again, change a value in `config.py`, then run `fuse` and `evaluate`. | One event is not always one fire. The tables `events` and `fire_events` give the purity and the completeness. |
| A detection with a large footprint joins and merges events as each other detection. | A test outside the repository gave it a small core and no permission to merge. Purity increased a little, completeness decreased more, and the number of events doubled. | The test is not a repository command. Hotspots that are continuous in space and time cannot divide fires that burn near each other. |
| One event has one alert. | It is the first, simple design. | A very large event lasts for weeks. An alert for new ground in an event is not built. |

### 13.4 Evaluation

| Choice | Reason | Pitfall |
|---|---|---|
| We grade against mapped fires, not against active fires. | No independent record of active fires exists. Hotspots are the data that we grade. | The truth is exact in space and coarse in time. A fire with no mapped scar is invisible. |
| The match is between a detection and a fire. | An event can be very large, thus its centre says little. | The tables count detections. A table of alerts for each fire is not built. |
| The match reach is the footprint plus a margin. | A detection can be anywhere in its pixel. | A sensor with a large footprint reaches more fires. Its recall looks better. |
| Recall, unmatched share and delay all use the fire. | One unit for all measures. The pieces of a large fire counted many times in the scar recall. | The fire recall is lower than the scar recall of earlier runs. The two are not comparable. |
| Delay is relative to the first detection from all sources. | No source gives the start time of a fire. | We cannot give the time from ignition to alert. |
| Delay counts only isolated fires. | Only there each detection belongs to one fire, for each footprint size (section 11.6). | The sample is small and holds a small share of the burned area. Isolated fires can differ from other fires. |
| A merged row and a single-source row use the same detections. | Then the rows differ only in the selection. | A single-source row is not a separate fusion run of that source. |
| An unmatched detection is not a false alarm. | Section 11.5 gives the causes. | The unmatched share alone rewards a system that sends few alerts. Read it with fire recall. |
