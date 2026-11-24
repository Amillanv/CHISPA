# Method

This file gives the glossary, the stages, the data conventions and the rules for the fusion, the evaluation and the agent.
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
| Stage | One of the eight steps in the life of a fire. `README.md` has the table. Section 7 has the rules. |
| Event | A group of detections that CHISPA assigns to one fire. |
| Event record | All that CHISPA knows about one event at an as-of time, stage by stage (section 7.3). |
| First alert | The alert of an event immediately after its first detection. |
| Visibility | The answer to: could a sensor examine this place at this time? (section 7.2) |
| Measured growth | The change of the area of an event between two passes. It is not a forecast. |
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
| Development period | 2023. We set rules and train on this period. |
| Test period | The year that scores a hypothesis one time: 2024 for the merge, 2025 for each later part (section 11.2). |
| Replay | A run that gives recorded detections to the fusion in time sequence. |
| As-of time | The time that a replay or a question uses as "now". |
| Gold question | A question for the agent with a known correct answer. |
| Brigade | A team that fights fires on the ground. |
| Acknowledgment | The signal from a brigade that it received an alert. |
| Burn conditions | The weather-based class for a planned burn: LOW, ELEVATED or EXTREME risk. |

## 7. Stages and the event record

`README.md` has the table of the eight stages: what drives each stage, its part of the alert, its measure and its state.
This section gives what we can know at each stage, and the rules for the parts that we build on the stages.

### 7.1 What we can know at each stage

1. **Ignition.** No source records it. We know only that it is not after the first `observed_at`.
   Visibility can give a second limit: the last time that a sensor examined the place and saw no fire.
   That limit is true only for a fire that the sensor can detect at its size.
2. **Observation.** A detection says that a pixel had heat at `observed_at`. It does not give the size of the fire.
   A pixel is much larger than a small fire.
3. **Publication.** `available_at` is the time when we can use a detection (section 9.2).
   We cannot make the source quicker. We can only read its quickest route.
4. **Alert.** The first alert goes out at the first detection. Its level is LOW, or MEDIUM for a high source confidence.
   Our delay after the publication is not more than the interval of the poller.
5. **Growth.** We see a fire only at a pass. Measured growth is the change between two passes.
   A polar-orbit pass gives the position. A GOES pixel is too large for the position.
6. **Confirmation.** The level goes up only when a new pass sees the event (section 10.3). We cannot make a pass come earlier.
7. **End.** We do not see the end of a fire. We see "no detection", and that has a meaning only with the visibility.
   Do not give a cause for the end, such as a brigade or rain, without a record of that cause.
8. **Mapping.** The map of a year comes in the next year (section 11.3). Thus it is never an input of a live event.
   Sentinel-2 can show the burned ground some days after a fire: a new image comes each 5 days (section 8.11).
   That is too late for an alert. It can give the burned area for the record of a fire, and it can score a forecast.
   It is not built as a measure of area: the burn check (section 11.10) gives only "burned" or "not burned" for a box.

Stages 2 to 6 repeat for each new observation.

### 7.2 Visibility

Visibility is necessary at each stage: for a fire with no detection, for a place with no alert,
for the earliest possible start and for the end.

- GOES: each scan has a mask with a class for each pixel (section 8.12). The classes are in groups:
  fire, possible fire, no fire, cloud, no background, water, blocked and not processed.
- "Examined" is the groups no fire, fire and possible fire: the sensor made a decision for the pixel.
- Recorded: `chispa fetch goes_mask` saves the mask of the Pantanal box for one scan of each hour.
  Section 11.11 gives the table that uses it.
- Live: each pass of the poller saves, for each scan, the number of pixels of each group and the mask of the window,
  in `live/goes_mask/`. The mask files have the form of the recorded masks.
- Polar-orbit sensors: a NASA service gives the time of each pass (section 8.12). We do not read it yet.
  A pass time does not say if cloud hid a place.
- An answer from the visibility must name the sensor and the time. "Examined, no fire" from GOES says nothing about a small fire.

### 7.3 The event record

The event record is the one object that an alert, a tool and a report read. `record.py` makes it, and the tool
`event_record` gives it. It holds, for one event at an as-of time, what we know at each stage and how we know it.
The event is the event as it was at that time (`issued.py`), not the event of the end of the year.

| Stage | Field of the record | Not in the record |
|---|---|---|
| Ignition | `hours_from_first_detection`: the fire is this old or older | The start time, and its limits |
| Observation | `first_observed_at`, `last_observed_at`, `max_frp_mw`, `detections`, `sensor_families`, `newest_detections`, `timeline`: the detections of each day, the land cover in `severity` | |
| Publication | `newest_available_at`, `newest_observation_age_h`, `passes`: when CHISPA had each pass | The time when a source published a pass |
| Alert | `level`, `confidence`: the rank, its number of reference alerts and the inputs with the largest effect (section 11.15) | |
| Growth | `growth`: the newest step. `growth_steps`: each step, the oldest first (section 11.13) | A burned area (section 11.12) |
| Confirmation | `level_changes`, the pass that made each change (`passes`), `absorbed` | |
| End | `goes_view`: what GOES said for the place in its newest saved scan and in each scan after the newest detection, with the last clear look. `viirs_passes_after_last_detection` | A cause of the end. A statement that a fire is out |
| Mapping | The track record of the level (`evaluation_summary`) | |

`severity` has the number, the points of each part and the facts (section 11.14).

- A field with no value is `None`. Do not fill it with an estimate. `notes` says why a part is absent.
- `hours_from_first_detection` is a minimum of the age of a fire. The fire started before its first detection,
  and we do not know how long before. For a small fire under cloud, that time can be days.
- An event out of the Pantanal biome of Brazil is in the answers of the tools, with a note: the confidence rank,
  the land cover and the track record of the level have no check for that place.
- Add a field only with its measure: how do we know that the field is correct, and on which data?
- A fire has no "type" in the record. No source gives a label for a controlled burn. The land cover is in the facts.
- The confidence rank is the share of the alerts of the development year with a smaller value. It is not a probability.
- The land cover is the map of the year before the first detection of the event, not later than the last year of the map
  (`config.py`). If that file is absent, the record has no severity and no rank, and a note.
- `level_changes` has the changes of the event itself. An alert that the event absorbed had its own levels before the merge.
- `passes` has the newest passes and each pass that raised the level (`config.py`), in the sequence of their observation.
  A pass that a satellite saw first can come to CHISPA last: `available_at` and the times in `alerts` say when.
  `pass_count` is the number of all passes. A pass is the item of evidence of section 10.3. Its `available_at` is the first
  time that CHISPA had it. `alerts` has each level that the pass raised, in sequence, with the time when CHISPA had the
  detection that raised it: one pass can raise LOW and then MEDIUM, and its INPE row can come in a later poll than its FIRMS row.
  `source` is the source of the first detection of the pass that CHISPA had. `estimated` is true if that time is an
  estimate (`available_estimated`, section 9.2): a pass before the live logs, or a live pass that the poller first saw after a stop.
  `poller_stop_h` is the part of the time to CHISPA in which no poll read that source with no failure, if that part is more
  than `config.LIVE_POLL_LATE`. It starts at the observation or at the newest such poll before, the later of the two.
  It is the most that the poller added: the poll log does not say when the source published the pass. Else it is None.
- `absorbed` has each alert that merged into the event up to the as-of time, with the time of the merge.
- `viirs_passes_after_last_detection` counts passes, not granules: the granules of one satellite that are not farther apart
  than the pass gap are one pass.
  The record uses the model of moment 0 in the first 24 hours of an event, and the model of moment 24 after that.
  We examined the model only at those two moments. At a different time, the rank is the best value that we have, not a checked value.
- `goes_view` reads the saved masks: one scan of each hour for the years that `chispa fetch goes_mask` got,
  and each scan that the live poller read. It uses only a scan that we had at the as-of time: a live mask has the time
  when the poller got it, and a recorded mask counts from the delay of a raw file after its scan start (`config.py`).
  A live scan that the poller got after a stop counts from the estimate of section 9.2.
  The place is the GOES pixels of the detections of the newest passes: the place of "last seen". A newest pass has a
  detection at the newest observation time; two platforms can have one. Each detection goes to the pixel with the nearest
  centre, in kilometres. `pixels` gives how many pixels the place has in the grid of the newest scan.
  The event centre can be in a different pixel from the fire.
  In each scan the group of the place is the first group in this sequence that one of its pixels has: fire, possible fire,
  cloud, no background, blocked, water, not processed, no fire (`view.PLACE_GROUPS`).
  Thus `no_fire` says that GOES examined each pixel and found no fire, and `cloud` that it could not examine a pixel (section 7.2).
  `no_background` says that GOES could not compute a background value for a pixel (`docs/sources.md` 8.12). It made no decision.
  `goes_view` gives the group of the place in the newest scan of the as-of day or the day before. If these days have no
  such scan, it is None. `scans_after_last_detection` is the number of saved scans after the newest detection, and
  `after_last_detection` counts them in each group. `newest_no_fire_at` is the newest of them with `no_fire`: the last clear look.
  `runs_after_last_detection` gives the same scans in time sequence. The scans of one answer in a row are one run:
  fire, possible fire, no fire, or "not_seen" (cloud, no background, blocked, water, not processed). A run gives its first
  and last scan, its number of scans and the number in each group.
  The recorded masks have one scan of each hour, the live masks each scan.
  It is the place of the newest pass only. It does not say that a fire is out: GOES can miss a small fire.
- The level and the confidence rank put the events in a sequence by their evidence for a match with a mapped fire.
  They do not decide that a fire is real: a burn can be absent from the map. `goes_view`, `growth` and the passes after
  the last detection say what the sensors see now. Do not use one for the other.

### 7.4 Rules for a new part

These rules are for each part that we add to a stage, with a trained model or without.

1. Write the hypothesis of the part before its result. Give the baseline: the rule that the part must be better than.
2. Train on 2023. Tune on 2024, which we know now. Do the test one time on 2025.
3. The burn scar map can be the label for training. It is never an input at the time of an alert.
4. The label has the errors of the map (section 11.5). Say this adjacent to each result.
5. A person must be able to explain the output. Give the inputs that had the largest effect.
6. A growth forecast is permitted only after a test against measured growth. Publish the test with the forecast.
7. A negative result is a valid result. Then the rule that exists stays.

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
| `available_at` | time | The time when CHISPA can use the detection. |
| `lat`, `lon` | number | The centre of the detection. |
| `footprint_m` | number | The radius of position uncertainty. |
| `frp_mw` | number or none | Fire radiative power. |
| `source_confidence` | text | `low`, `nominal` or `high`, mapped from the source value. |
| `available_estimated` | true or false | True if `available_at` is an estimate, not a measured time. |

`available_at` is important.
A satellite observation is not available at the moment of the observation.
For a recorded detection it is an estimate: `observed_at` plus a fixed delay from `config.py`. Say so in the results.
For a live detection it is a measurement: the time when a pass of the poller first read it.
The live logs start on the day in `config.py`. The detections of 2026 before that day come from the archive, with the estimate.

A live row that the poller first saw after a stop has no measured time: its first view has the time of our stop.
It gets an estimate, and `available_estimated` is true. The owner agreed to this rule on 2026-11-24.

- GOES and INPE give the publication time of each file. If the first view was more than `config.LIVE_POLL_LATE` after
  the publication, `available_at` is the publication time plus `config.LIVE_NORMAL_WAIT`: an estimate of the wait to the next pass.
- FIRMS gives no publication time. If no pass read FIRMS in the time `config.LIVE_POLL_LATE` before the first view,
  `available_at` is `observed_at` plus the fixed delay. It is not before the newest pass before that read FIRMS,
  and not after the first view.
- The live logs keep the measured times of each row: the estimate changes no raw file. A delay report must not count these rows.

### 9.3 Missing values

- Use `None` for a missing value. Do not use 0, -1 or an empty string.
- Do not fill a missing value with an estimate, unless the function name says that it makes an estimate.

## 10. Fusion rules

### 10.1 Principles

- The fusion is deterministic. It has no random step and no trained model. Section 7.4 gives the rules for a change.
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

The first alert of an event goes out at its first detection. A higher level needs a new pass.
A confidence level is useful only if HIGH alerts match fires more frequently than LOW alerts.
The evaluation must report the matched share for each level.

### 10.4 Fusion output

The command `chispa fuse --year` writes three tables.

- `events`: one row for each event at the end of the year: times, number of detections, mean position, bounding box, largest FRP, level, sensor families and number of passes.
- `alerts`: one row for each time that the level of an event goes up, with the time when the change became available.
  A merged event keeps only the first row of each level from the events that it absorbed.
- `memberships`: one row for each detection: its event, the level of the event immediately after that detection,
  and the issued id: the event that the detection joined at its time.
- `merges`: one row for each merge of two events: the time, the event that stops and the event that continues.
  With the issued ids and the merges up to a time, `issued.py` gives the events as they were at that time.

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
- Freeze the configuration. Record its hash. The hash covers the first part of `config.py`: the values that can change a result.
- Run the evaluation of the test period one time for each frozen configuration.
- Record each run in `results/`, with the configuration hash and the date.
- If you change a threshold after a run on the test period, the next result must say so.

The test period of the merge hypothesis was 2024. We ran it on 2026-11-21, thus 2024 is not new data now.
The table `merge_gain` came after that first run. It changed no threshold and no number of the other tables.
Each later part uses 2024 only to tune, and 2025 as its test period (section 7.4).
Each command that makes a result stops for 2024 and for 2025, unless it has the flag `--test-run`.
Do not use the flag for 2025 before the rules of a part are frozen. The store can hold the 2025 data before that time.

The merge has a second year: 2025. No threshold of the fusion or of the match changed after 2023.
We wrote these hypotheses on 2026-11-23, before the 2025 run of `evaluate`. Each is a finding of 2024.
The best sensor family of a year is the family with the largest fire recall.

1. The merged configuration finds more counted fires than the best sensor family (table `configurations`).
   Most of the fires that only the merge finds are smaller than 100 hectares (table `merge_gain`).
2. The merge is not earlier for the typical fire. The best sensor family is later than the merge on less than half
   of the isolated fires that it finds (table `merge_gain`). Thus its median relative delay is 0 hours.
3. The matched share of the events increases with the final level: LOW, then MEDIUM, then HIGH (table `events`).
4. The merged configuration does not have a larger unmatched share than the best sensor family.
   This is a part of the first hypothesis of the project. It was false in 2023 and in 2024, by 0.0191 and 0.0073.

What we knew of 2025 before the run. The table `visibility` of 2025 gave 270 counted fires with a GOES detection,
36 with a detection from a different sensor family only, and 283 with no detection. Thus the first part of
hypothesis 1 is not new. The table `confidence` of 2025 showed that the level separates the alerts with a match.
The delays, the unmatched shares, the size classes and the table `events` were not known.

The result for 2025 (tables `configurations`, `merge_gain` and `events`, 2026-11-23). 2025 has 589 counted fires.

- Hypothesis 1 is true. Its first part was not a new result: the table `visibility` gave it before the run (see above).
  The merge found 306 of the 589 counted fires. The family abi, the best sensor family, found 270.
  Its second part is new: each of the 36 fires that only the merge found is smaller than 100 hectares.
- The source `firms` alone found 302 fires. It has three sensor families. Thus the merge of the sources added 4 fires
  to the best source. In 2023 it added 22 fires to the source `inpe`.
- Hypothesis 2 is true. The family abi was later than the merge on 11 of the 76 isolated fires that it found.
  Its median relative delay is 0 hours.
- Hypothesis 3 is true. 252 of 959 LOW events, 131 of 360 MEDIUM events and 214 of 407 HIGH events matched a mapped fire.
- The matched share of a level changes with the year. For HIGH events it was 0.607 in 2023, 0.8047 in 2024 and 0.5258
  in 2025. Thus the levels have the same sequence in each year, and a level has no fixed matched share.
- Hypothesis 4 is false, as in 2023 and in 2024. The unmatched share of the merged configuration is 0.2255:
  13 744 of 60 952 detections. That of the family abi is 0.1712. In 2024 the merged share was 0.039.
- A correction after a review on 2026-11-23: hypothesis 4 is not a part of the first hypothesis of the project.
  The project hypothesis is on alerts. The unmatched share counts detections, and an alert with many detections
  counts many times. No table compares the alerts of the merge with the alerts of one source: a baseline row is not
  a separate fusion run (section 13.4). Thus that part of the project hypothesis has no test.
- The fire recall of the merge was 0.5195. It was 0.8111 in 2023 and 0.6745 in 2024.
  269 of the 283 fires with no detection are smaller than 100 hectares.
- Limits: 2025 has few fires, and only 98 isolated fires give a delay. FIRMS gives GOES-16 to 7 April and GOES-19 from
  6 April: the rows of those two days have the two satellites (`docs/sources.md` section 8.1).
  The year can have holes in its GOES record that we did not find.

On the same day we made the tables of 2023 and 2024 again, with two corrections of the tables and no change of a threshold.
`fires_isolated` in the table `fire_events` counted the fires with no detection also: now it counts only fires that
the fusion found. The table `configurations` now gives the first and the last day of the detections of each row:
the row `source noaa` of 2024 has only the seven weeks of the GOES gap fill. No other value of the five tables changed.

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

Not built and not planned. The owner decided on 2026-11-21 to skip it.
The AOD grid is approximately 44 km (section 8.4): too coarse to say what hid one event.
Visibility (section 7.2) has this purpose now.

### 11.9 Result format

- One command makes all result tables. The package `evaluation/` has one module for each question.
- Each table is a CSV file in `results/` with a header that gives the configuration hash.
- `results/SUMMARY.md` is generated by code. Do not edit it by hand.
- Give counts adjacent to shares. Give the median and the 90th percentile for delays.

The tables are:

- `configurations`: fire recall, area recall, unmatched share and delay for each source, sensor family and merged level,
  with the first and the last day of its detections. A row with a part of the year is not a full baseline.
- `fire_sizes`: fire recall for each configuration and fire size class.
- `fire_events`: for each fire size class, into how many events the fusion split a fire, and the completeness.
- `events`: for each final level, the share of events that match a fire, how many counted fires one event holds, and the purity.
- `merge_gain`: for each sensor family and fire size class, the fires that only the merge finds, and the isolated fires that the family finds later than the merge.
- `burn_check`, `burn_rule`, `image_check` and `image_agreement`: the burn check of HIGH events and its check by a person (section 11.10).
- `visibility` and `visibility_months`: how frequently GOES examined the place of a fire, and the box in each month (section 11.11).
- `growth_steps`: the advance and the speed of the steps of the events, by the time between passes (section 11.13).
- `severity_inputs`, `severity` and `severity_rank`: the severity of the events against the mapped area (section 11.14).
- `confidence` and `confidence_weights`: the probability of a match at two moments, against the level (section 11.15).

Purity and completeness count matches with counted fires. A detection that matches two fires counts two times.

### 11.10 Burn check and image check

The match gives only a lower limit of the precision (section 11.5). The burn check measures a part of the gap:
it asks a second satellite, Sentinel-2, if the ground at an event burned. The image check lets a person verify it.
`config.py` has each value. The two commands are `chispa burn --year` and `chispa images --year`.

The burn check:

1. A box is the box of the detections of an event plus a margin.
2. The burn ratio of a pixel is NBR = (B8A - B12) / (B8A + B12). Healthy plants give a high value. A burn gives a low value.
3. dNBR is the NBR before minus the NBR after. "Before" is the last clear view of the pixel from a day before the
   first detection. "After" is the first clear view after the last detection. A view with cloud, shadow or water is not clear.
4. The background of a box is its median dNBR. We subtract it: plants that dry change all of the box, and a burn changes a part.
5. A pixel is burned if its dNBR is the chosen step or more, and it is in a patch of the minimum size.
6. The rule says "burned" if the burned pixels of the box are the chosen area or more.
7. A box gives no answer if less than the minimum share of it has a clear view before and after.

A dNBR is not only a burn: a wetland that dries, and plants that die in the dry season, also decrease the NBR.
Thus the rule has two reference groups, and the result of the events has a meaning only adjacent to them:

- Matched: a sample of HIGH events that match a mapped fire. Its burned share says how many burns the rule finds.
- No fire: boxes with the sizes and the times of unmatched events, at random positions in the biome with no mapped fire
  of the year and no detection near the time. Its burned share says how frequently the rule says "burned" with no fire.
- Unmatched: each HIGH event with no match. This is the group that we want to know.

The chosen step and the chosen area come from the development year: the pair with the largest difference between
the burned share of the matched group and that of the no-fire group. If two pairs are equal, the smaller area.
Then the test year uses that pair with no change.
The table `burn_check` of the development year gives the counts for each pair. The chosen pair has a mark.
The table of a different year has only the chosen pair.

An unmatched event can have a mapped fire in its box: a fire of a different time, or outside the reach of the match.
Thus the table has one more row: the unmatched events with no mapped fire of the year in their box.
Compare this row with the no-fire group. The two have the same condition.

The first rule had no background, no water mask and no minimum area. On 2023 it said "burned" for 40 of 99
no-fire boxes at its highest step. We changed the rule on 2023, before the 2024 run.
The rule is weak for one event: read only the share of a group, adjacent to the two reference shares.

The table `burn_rule` gives the quality of the chosen rule on the two reference groups: the recall on the matched
events, the false share on the no-fire boxes, and the precision and the F1 of the two groups together.
The precision and the F1 are true only for this mix: the two groups have almost the same size. Real events do not.
Do not compare these values with a published value for burned pixels. Our unit is a box, and our reference is not exact.

The image check:

1. The sample is the start of the unmatched group and of the matched group of the burn check, in the random sequence of that check.
2. Each event gets a chip number in a new random sequence. The number does not show the group.
3. Each event gets two pictures of its box (bands B12, B8, B4): the last image with little cloud from before the event,
   and the first after it. A yellow line shows the box of the detections.
4. A person writes one answer for each chip in `answers.csv`: `burned`, `not burned` or `cannot tell`.
5. The person does not open `key.csv`, or the measures of the burn check, before all answers are complete.
6. The table `image_check` counts the answers. The table `image_agreement` compares each answer with the rule.

Limits:

- The burn check is not independent of the map in its physics: the two read a burn from reflected light.
  It has a different sensor, smaller pixels and more images.
- The no-fire boxes can have a burn that no satellite detected and the map does not show. Then their burned share is too high.
- A box where more than half of the area burned has a high background. Then the rule can miss the burn.
- The matched fires are larger than the fires that we look for. The rule sees only a burned area of the chosen size or more.
- Large boxes rarely have a position with no fire. Thus the no-fire group has few large boxes.
- The picture of the person is one image. The rule uses the clear pixels of all images. The two can differ.
- One person makes the answers. The two checks have only HIGH events.
- The files are in `results/{year}/burn_check/` and `results/{year}/image_check/`. Only `answers.csv` is made by hand.
- The 2024 burn check came after the 2024 run of 2026-11-21. It changed no threshold of the fusion or of the match.
- The burn check of 2025 (table `burn_check` of 2025, 2026-11-23), with the rule of 2023: "burned" for 93 of 186 unmatched
  HIGH events with a clear view, for 83 of 100 with a match, and for 17 of 100 no-fire boxes. It is the baseline of section 11.16.

The second look (`chispa images --year 2024 --test-run --look 2`, made on 2026-11-23). It makes a better reference
for the next rule. The first look had one pair of pictures, it lost 21 chips to cloud on the image tile, and it had no
place with no fire.

1. The sample is each event of the first look again, and the first no-fire boxes of the burn check (`config.py`).
   A new random sequence gives new chip numbers. The file of the person has no id and no group.
2. A picture needs a minimum share of its box with no cloud. The scene classes of the pixels of the box give that share.
3. Each chip has up to three pictures: the last clear view before the event, the first clear view after it,
   and a later view some days after that. A white square in a corner has the minimum burned area of the rule.
4. The answer of a chip is in `answers.csv`: `burned`, `not burned` or `cannot tell`. For `burned`, the column `area`
   has `small` if all the new burn is smaller than the white square, and `large` if not.
5. The tables are `image_check_2` and `image_agreement_2`. The command makes no table before the first answer.

The rules for the person. Do them in this sequence for each chip:

1. Go from the picture before to the picture after. Look for a new dark red, brown or black area.
   Green is plants. Pink and tan are dry or bare ground. A field has straight edges.
2. If there is no such area, write `not burned`.
3. If there is one, make sure that it is not one of these. A cloud shadow: black, with a white cloud of the same form
   near it. Water: black or dark blue, smooth, in a channel or a low place. A burn of an earlier time: it is in the picture before.
   Only a burn between the picture before and the picture after counts. If a burn of the picture before is larger
   in the picture after, the new part counts: write `burned`, with the area of the new part.
   For each chip with a burn in the picture before, write `old burn` in the column `note`.
4. Look at the later picture. A burn stays at its place, and it can be lighter. A shadow is not there. Water can change its form.
5. If all of the picture changed to dark red or brown, the burn is larger than the picture: write `burned` and `large`.
   If all of the picture only changed from green to yellow or pink, the plants dried: write `not burned`.
6. Orange or yellow points, with or without smoke, are flames: write `burned`.
7. A burn at any place in the pictures counts, not only in the yellow line.
8. If cloud hides the ground in the picture after, use the later picture in its place. Write `later only` in the column `note`.
9. If the picture after shows the ground with no burn, a burn that is only in the later picture is a later fire.
   Write `not burned`, and `burn in later` in the column `note`.
10. Write `cannot tell` only if no picture after the event shows the ground, or if the picture before or the picture after is absent.
    With no picture before, you cannot know that a burn is new: write `cannot tell` for a burn. With no burn in the
    pictures after, `not burned` is correct. Flames are `burned`, with `no before` in the note.
    If you see the ground and you are not sure, write the more probable answer, and `?` in the column `note`.
11. Do not open `key.csv`, the files of the burn check or the answers of the first look. Do not guess the group of a chip.
12. Work for a maximum of 30 minutes at one time. Change an answer only before you say that the file is complete.

Rules 8 and 9, the exception of rule 10 and the last three sentences of rule 3 came on 2026-11-23, after questions of the owner in the work. The later picture can be more than
30 days after the last detection, and the box rule reads only 30 days. Thus the table `burn_candidates_person` does not
use the chips with the note `later only`: its column `later_only` gives their number. The answers of 2024 have no such chip.

Three events have no value for a comparison: the owner saw the opinion of Claude on them (chips 7, 49 and 58 of the
first look, events 20240016701, 20240006447 and 20240008269). They can be examples for the person.

The result of the second look (tables `image_check_2` and `image_agreement_2` of 2024, 2026-11-23). The owner made the answers.

- Before a comparison with the key, a second reader read the chips with a note of doubt and a random set of the others.
  The second reader was a model, with the pictures and the rules only. The owner examined the chips with a different answer
  again, changed some answers, and said that the file was final. That check has no table, thus we give no number for it.
- The three events that the person saw with an opinion are not in the two tables.
- Unmatched HIGH events: the person said "burned" for 22 of the 50 chips with the answer "burned" or "not burned".
- Matched HIGH events: 18 of 25. No-fire boxes: 3 of 57.
- Thus a person says "burned" for few places with no fire, and for approximately half of the unmatched HIGH events.
  The 3 no-fire boxes can be errors of the person, or burns that no source shows.
- The second look gave more answers than the first look, and more burns: it has more pictures of each chip.
- The box rule agrees with the person for 89 of the 131 chips with a clear answer and a clear view for the rule.
  It says "burned" for 29 of the 89 chips that the person called not burned.
- Limits: one person, and a small sample. The events of the second look are those of the first look: the person saw them before.

The result of the first look (tables `image_check` and `image_agreement` of 2024, 2026-11-23). The owner made the answers.

- 69 of the 90 chips had the two pictures and got an answer. The other 21 chips had no pair of pictures.
- Unmatched HIGH events: the person said "burned" for 15 of the 44 chips with the answer "burned" or "not burned".
  5 more chips got "cannot tell", and 11 had no pair of pictures.
- Matched HIGH events: the person said "burned" for 15 of 19 such chips. Thus a person can miss a burn in one pair of pictures.
- 15 of 44 is a count of answers. It is not a limit of the burned share: we do not know how frequently a person
  says "burned" at a place with no fire. The sample has no chip of a no-fire box.
- The person and the rule agree for 46 of the 62 chips with one of the two answers and a clear view for the rule.
  For the other 16, the rule said "burned" for 10 and the person for 6.
- Thus the two checks agree on the direction: a part of the unmatched HIGH events has a burn. They do not agree on one number.
- Limits: one person, one pair of pictures for each event, and a small sample.

### 11.11 Visibility of fires

Question: when a counted fire has no detection, could GOES examine its place?
The hypothesis, written before the first run: GOES examined the place of most such fires in less than half of their scans.
If this is false, cloud is not the main cause, and the fire was too small or too cool for the sensors.

1. The place of a fire is the GOES pixel that holds most of its burned pixels.
2. The scans of a fire are the hourly scans in the days when it burned, by the time rule of the match (section 11.4).
3. For each fire we count its scans in each mask group. Its examined share is its examined scans divided by all its scans.
4. The table `visibility` has three rows: the counted fires with no detection, with a detection but not from GOES,
   and with a GOES detection. The command `chispa visibility --year` makes it.

- Limits: one pixel stands for a fire. One scan of each hour stands for six. The table has only GOES.
  A fire with only a month has scans of two months, and most of them are not at the time of the fire.
- The 2024 table came after the 2024 run of 2026-11-21. It has no threshold that we set on data.

The result for 2024 (table `visibility`, 2026-11-22): the hypothesis is false.

- GOES examined the place of a typical fire with no detection in 76 percent of its scans. Cloud had 21 percent.
- 100 of the 1382 fires with no detection had an examined share below one half. 50 had no examined scan.
- The fires with a GOES detection have almost the same values: 74 percent examined and 23 percent cloud.
- Thus cloud is not the main cause of a fire with no detection. GOES looked and found no fire: these fires were too small,
  too cool or too short for the sensors.
- 116 of the 1382 fires with no detection had a scan with a possible-fire class, which FIRMS does not give.
- The largest limit: most of these fires have only a month. Their scans are from two months, and the fire burned in a part
  of that time. A fire that burned on one day with cloud can have a high examined share.

The same table for 2023 and 2025 (2026-11-23) agrees. The median examined share of the fires with no detection
is 0.67 for 183 fires in 2023 and 0.76 for 283 fires in 2025.

The table `visibility_months` gives, for each month, how much of the mask window GOES examined:
the number of days with no scan, the median examined share and the median cloud share of the days,
and the number of days with an examined share below one quarter.
A day with no scan is a hole in the record. A day with a small examined share is a day of cloud.

- 2023, 2024 and 2025 have no day with no scan in the hourly masks. They have 8741, 8739 and 8717 scans.
- The examined share follows the season: in 2024 it is 0.91 to 0.96 from May to September, and 0.42 to 0.72 in the other months.
- April 2025 has an examined share of 0.63, and 4 days below one quarter. FIRMS had GOES rows on only 14 days of that month.
  The NOAA files exist for each hour of that month. In the scans that we examined on four days, the fire pixels were few (section 8.1).
  Thus we found no sign of a hole. We did not compare each NOAA fire pixel of that month with the FIRMS rows.

### 11.12 Why growth has no area

We do not give the burned area of an event. A VIIRS detection covers its full pixel, and the fire is in a part of it.
One pixel is approximately 14 hectares or more: as large as a small fire.
A test on 2023 made an outline from the pixels of each isolated fire, as the method of FEDS does (section 8.13).
The area of the outline was some times the area of the mapped fire, and no setting corrected it.
The code of that test is not in the repository. `PLAN.md` has its numbers.

- A distance has a smaller error than an area: the position of a pixel is wrong by a part of one pixel,
  and that error does not grow with the fire. Thus section 11.13 gives growth as a distance and a direction.
- A GOES pixel is too large for the two.

### 11.13 Advance, direction and speed

Growth has no area (section 11.12). It has a distance. `growth.py` makes the steps of an event.
The command `chispa growth --year` makes the table `growth_steps`.

1. A pass is the VIIRS detections of one event from one satellite at one time (the pass gap of section 10.3).
2. A step is one pass after the first pass of the event. Its older pixels are the detections of all passes before it.
3. The distance of a pixel is the distance from its centre to the centre of the nearest older pixel.
4. The advance of a step is a high percentile of the distances of its pixels (`config.py`). One far pixel does not set it.
5. A pixel is a new pixel if its distance is more than the floor. A step with no new pixel has "no measured advance", not zero.
6. The direction of a step is the direction of the mean line from the nearest older pixel to each new pixel, in degrees from north.
7. The speed of a step is its advance divided by the time from the pass before it, in metres for each hour.
   A step has a speed only if it has a new pixel, and the time from the pass before is the minimum in `config.py` or more.
8. An empty pass is a pass of a VIIRS satellite over the event, between two steps, with no detection of the event (section 8.12).

The floor comes from the development year. Two VIIRS satellites pass approximately 50 minutes apart.
A fire moves little in that time, thus the advance of such a step is mostly the error of the positions.
The floor is the 90th percentile of the advance of the steps with less than 2 hours from the pass before, to the next 50 m.

The hypothesis, written before the first run: the median advance of the steps with less than 2 hours is less than half
of the median advance of the steps with 6 to 18 hours. If this is false, the advance is mostly error, and we give no speed.

- The speed is a mean of the time between two passes. A fire that moves for two hours and then stops gives a low speed.
- The speed has no reference. No source gives the position of a fire front at a known time. It is a defined measure, not a checked one.
- The fusion joins a new fire near an event to that event. Then the advance is the distance to that fire, not a movement.
- An empty pass does not say "the fire is out". Cloud can hide the fire. The pass list has no cloud data.
- A GOES detection gives no step. Its pixel is too large.
- Only detections in the biome border count, as in the other tables.

The result (table `growth_steps`, 2026-11-22): the hypothesis is false in 2023 and in 2024.

- The median advance of the steps with less than 2 hours was 302 m in 2023 and 293 m in 2024.
  For the steps with 6 to 18 hours it was 580 m and 517 m: less than two times as much.
- Thus the advance of a typical step is not larger than the error of the positions. We give no advance and no speed for it.
- The floor from 2023 is 850 m. In the steps with 6 to 18 hours, 743 of 1769 (2023) and 1736 of 4546 (2024) had a new pixel
  past the floor. In the steps with less than 2 hours, 879 of 4877 and 1691 of 10 697 had one.
- For the steps with 6 to 18 hours and a new pixel, the median speed was 113 m and 118 m for each hour.
  The 90th percentile was 335 m and 354 m. The two years agree.
- A speed for a step with less than 2 hours has no meaning: the error of the positions, divided by a short time, gives a high value.
  Thus a step has a speed only with 6 hours or more from the pass before.
- Some steps came after an empty pass: a satellite passed and gave no detection of the event. In the steps with
  6 to 18 hours that is 610 of 1769 in 2023 and 1309 of 4546 in 2024. A granule that is nearer than the pass gap to one of
  the two passes of a step is a part of that pass, and it is not an empty pass.

The test on 2025. We wrote this on 2026-11-23, before the 2025 run of `growth`. The floor and each other value
stay as 2023 set them. The hypothesis of this section stays with no change: we expect that it is false again.
Two more statements come from 2023 and 2024:

1. Less than half of the steps with 6 to 18 hours have a new pixel past the floor.
2. The share of the steps with a new pixel is larger for 6 to 18 hours than for less than 2 hours.

The result for 2025 (table `growth_steps`, 2026-11-23): the hypothesis is false again, and the two statements are true.

- The median advance was 296 m for the steps with less than 2 hours, and 503 m for the steps with 6 to 18 hours.
- 118 of the 377 steps with 6 to 18 hours had a new pixel past the floor, and 144 of the 1242 steps with less than 2 hours.
- For the steps with 6 to 18 hours and a new pixel, the median speed was 124 m for each hour. The 90th percentile was 316 m.
  The three years agree.
- 2025 has few steps: 377 with 6 to 18 hours. 2024 has 4546.

What a step can say: "new pixels past the floor, this far, in this direction", or "no measured advance".
The first is true for less than half of the steps. "No measured advance" does not say that the fire did not move.
The hypothesis is true only in part: the measure has a meaning for the large steps, not for the typical step.

A check against Sentinel-2 images of large fires, over 5 to 10 days, agreed with the advance and the direction.
It is a study outside the repository (`PLAN.md`), not a result. The speed of one step of 12 hours has no check.

### 11.14 Severity

A brigade with few people must know which alert to go to first. The severity is one number from 0 to 100 for an event
at an as-of time, with the facts that give it. `severity.py` makes it. The command `chispa severity --year` makes the tables.
The severity does not contain the confidence level. Give the level adjacent to it.

The facts, each from data that exists at the as-of time:

- Fire power: the largest FRP of the detections of the event.
- Extent: the longer side of the box of the detections, in kilometres.
- Advance: the advance of the newest step, if that step has a new pixel (section 11.13).
- Land cover: the group that most detections are on, from the map of the year before (section 8.14).
  A cell with no class in the map does not count.
- People: the number of people in a square of approximately 10 km around a detection, the largest value of the event.
- Protected land and indigenous land: the nearest area of each kind, with its name and its distance.

The number is a sum of points. `config.py` has each point value.

| Part | Points | Rule |
|---|---|---|
| Fire power | 0 to 20 | One third of the points for each step that the value reaches |
| Extent | 0 to 15 | The same, with its steps |
| Advance | 0 to 15 | The same, with its steps. No points with no measured advance |
| Land cover | 0 to 20 | A fixed number of points for each group |
| People | 0 to 15 | The same as the fire power, with its steps |
| Protected or indigenous land | 0 to 15 | All points if a detection is in an area. A part if an area is near |

- The steps of the fire power, the extent and the advance come from the development year: the 50th, 75th and 90th percentile
  of the events with a value larger than zero, at the evaluation time. An event at one position has an extent of zero.
  The table `severity_inputs` gives them.
- The points of the land cover, the steps of the people and the points of the land are choices of the owner. They are not measured.
- An alert must give the parts of the number, not only the number.

The check. The evaluation time is a fixed number of hours after the first detection of an event became available.
The outcome is the mapped area of the counted fires that the event matches at the end of the year: 0 for an event with no match.

The hypothesis, written before the first run: the rank correlation of the severity with the outcome is larger than that
of the number of detections at the same time. The number of detections is the baseline: it needs no layer and no rule.
If this is false, the number adds nothing to a count, and the facts stay with no number.

- Limits: the outcome is an area, not damage. The people and the land get points, but no reference says that they matter.
  An event that merges with a second event later has the outcome of the two. The land cover is a year old.
  The population is an estimate for 2020 on a grid of 100 m.
- The outcome of an alert is the outcome of the event that holds it at the end of the year. If the alert merged
  into a large fire later, it has the area of that fire.
- The list of protected land is the list of today (section 8.14). An area that got its status after an event still
  gives points to that event. A new download can give a different list.

The unit of the check is an alert as it was at the evaluation time (`evaluation/moments.py`), not an event of the end
of the year. Two alerts that merged later are two rows. An alert that was a part of an older event at that time gives no row.
The first runs used the events of the end of the year. A review found that error. The steps in `config.py` and each
number below come from the corrected unit, on 2026-11-23.

The result (tables `severity` and `severity_rank`): the hypothesis is true on 2023 and false on 2024.

- Rank correlation with the outcome, for all alerts: the severity 0.2894 and the number of detections 0.2738 in 2023 (6037 alerts).
  In 2024 the severity 0.2838 and the number of detections 0.3155 (6473 alerts). The sequence changes between the years.
- Thus the severity does not say more about the final burned area than a count of detections.
- For the alerts with a match only, each rank correlation is near zero. Many small alerts match one very large fire,
  thus the outcome of an alert says little about that alert. Thus the rank correlation for all alerts shows mostly
  one thing: an alert with many detections matches a fire more frequently. It does not show a ranking of the burned area.
- The severity does separate the alerts that match a mapped fire. In 2024 the matched share was 1131 of 3358 alerts with a
  severity below 25, 1457 of 2711 from 25 to 50, 342 of 388 from 50 to 75, and 15 of 16 from 75.
  This was not the hypothesis. It is a property of a confidence, not of a severity (section 11.15).
- The number of detections separates these alerts as well as the severity: the match separation in the table
  `severity_rank` is 0.6678 for the severity and 0.6742 for the number of detections in 2024, and 0.6973 and 0.6965 in 2023.
- The time after the evaluation time. Of the 357 matched alerts with a severity of 50 or more in 2024, 253 had a detection
  after the evaluation time: 240 of 342 from 50 to 75, for a median of 2.96 more days, and 13 of 15 from 75, for a median of 5.93.
  Below 25, 141 of 1131 matched alerts had one. In 2023: 130 of 220 from 50, and 59 of 389 below 25.
  Thus more of the alerts with a high value at 24 hours have a later detection, and fewer of the alerts with a low value.
  A later detection does not say that the same fire burns, and it gives no time for a brigade to act.
  No later detection does not say that a fire is out: the sensors do not see each fire.
  This is a description of two years, found after the first run. It is not a tested forecast.
- The check was weak in one way: people, land and land cover have no relation to the burned area by design.
  They are the priorities of the owner. Only the fire parts can agree with the outcome.

The rule of the hypothesis says: with a false result, the facts stay with no number.
The owner decides if the number stays as a statement of priorities. It must not be called a forecast of the burned area.

The test on 2025. We wrote this on 2026-11-23, before the 2025 run of `severity`. The steps and the points stay
as they are in `config.py`. The confidence test of 2025 used the same alerts and their matches at 24 hours.
It did not use their severity.

1. The hypothesis of this section, with no change: the rank correlation of the severity with the outcome is larger
   than that of the number of detections.
2. From the description of 2023 and 2024: the matched share increases from the alerts below 25, to those from 25 to 50,
   to those from 50 to 75.
3. From the same description: of the alerts with a match, a larger share has a detection after the evaluation time
   for a severity of 50 or more than for a severity below 25.

Statements 2 and 3 were not hypotheses before 2025. They are about a match: a property of a confidence.

The result of the test (tables `severity` and `severity_rank` of 2025, 2026-11-23).
2025 has 1729 alerts at the evaluation time, and 332 of them match a mapped fire.

- Hypothesis 1 is true on 2025 by its measure. The rank correlation with the outcome is 0.3751 for the severity and
  0.2679 for the number of detections. Thus the hypothesis is true on 2023 and on 2025, and false on 2024.
- That measure mixes two things. An alert with no match has an outcome of 0, thus a value that separates the alerts
  with a match gets a high rank correlation. For the area alone, read the alerts with a match: there the severity
  has 0.3143 and the number of detections 0.3174. Thus the gain of the severity on 2025 is a better separation of
  the alerts with a match (0.7648 against 0.6805). It is not a better sequence of the burned areas.
- Alerts that merged later into one event have one outcome. Thus the 332 alerts with a match are not 332
  different outcomes. A comparison with one row for each event of the end of the year is not built.
- One part alone was as good on 2025: the largest fire power has 0.391. On 2024 it had 0.1324.
  The best single measure changes with the year: the number of detections on 2024, and the fire power on 2025.
- For the alerts with a match only, the rank correlations of 2025 are not near zero: 0.3143 for the severity,
  0.3174 for the number of detections and 0.4551 for the fire power (332 alerts). 2025 had 2 fires of 10 000 hectares
  or more, and 2024 had 25. In 2024 many small alerts matched one very large fire.
- Statement 2 is true. The matched share was 107 of 1196 alerts below 25, 175 of 470 from 25 to 50, and 45 of 57
  from 50 to 75. From 75 it was 5 of 6.
- Statement 3 is true. 30 of the 50 matched alerts with a severity of 50 or more had a detection after the
  evaluation time. Below 25 it was 7 of 107.
- In 2024 the match separation was 0.6678 for the severity and 0.6742 for the number of detections.
  On 2025 the fire power alone had 0.774.
- Thus the description of the first day is true in a year that did not give it. It is one test year, with 63 alerts of 50 or more.
- The number is not better than its parts in each year. It must not be called a forecast of the burned area.
  The owner decides if it stays as a statement of priorities.

### 11.15 Confidence at two moments

The confidence level of section 10.3 counts passes and sensor families. At the first detection it is almost always LOW.
This part gives a probability that an event will match a mapped fire, at two moments. `confidence.py` makes it.
The command `chispa confidence --year` makes the tables.

- Moment 0: one pass gap (30 minutes, section 10.3) after the first detection of an alert. It uses the detections that
  were available up to that time: the same pass from two sources has times that differ by some minutes.
  An alert that merged into an older event in those minutes gives no row. Thus moment 0 is near the first alert, not at it.
- Moment 24: the detections that were available 24 hours after that time (the evaluation time of section 11.14).

The inputs. Each exists at its moment:

- From the detections: their number, the number of passes, the sensor families, the largest fire power,
  and if a source gave a high confidence.
- From the time: the month, and day or night at the place.
- From the layers of section 11.14: the land cover group, the distance to protected land and to indigenous land, and the people.
- From the days before: the number of detections near the first detection (`config.py` gives the days and the cells).
- Only at moment 24: the extent, and the advance of the newest step.

The model is a logistic regression: a sum of the inputs with one weight for each, then a probability.
A person can read each weight. It has no dependency: `confidence.py` contains the calculation.

The label is "the event matches a mapped fire at the end of the year". It has errors (sections 11.5 and 11.10):
an event with no match can be a real fire. Thus the probability is for a match with the map, not for a fire.

The periods: the weights come from 2023. The choice of the inputs and of the penalty comes from 2024.
Then the model is frozen, and 2025 gives the result one time.

The baseline at each moment is the confidence level at that moment, as a number: LOW 0, MEDIUM 1, HIGH 2.

The hypotheses, written before the first run on 2025:

1. At moment 0, the match separation of the probability is larger than that of the level.
2. At moment 24, the match separation of the probability is larger than that of the level.
3. The probability is calibrated: in each fifth of the events by probability, the matched share is not farther
   than 0.1 from the mean probability.

If hypothesis 1 or 2 is false, the level rule stays at that moment. If hypothesis 3 is false, we give a rank and not a probability.

The measures in the table `confidence`, for the probability and for the level:

- Match separation: the probability that an event with a match has a larger value than an event with no match.
- Brier value: the mean square of the probability minus the label. 0 is the best. The probability of a level
  is the matched share of that level in the development year.
- Brier skill: 1 minus the Brier value divided by the Brier value of one constant, the matched share of the development year.
  More than 0 is better than that constant.
- Top tenth: of the tenth of the alerts with the largest values, how many match. A brigade goes to these first.
  `top_tenth_fires` is the number of different counted fires of the events that hold those alerts at the end of the year.
  `top_tenth_own_fires` counts only the fires that the detections of each alert at the moment match.
  Many alerts can match one large fire, thus a count of alerts alone can look better than it is.

The unit is an alert as it was at the moment (`evaluation/moments.py`). The numbers below are for that unit.

What 2023 and 2024 show. This is tuning, not the test. The weights are from 2023:

- The first model had no input for the fire activity near an event. We examined the inputs on 2024, outside the repository:
  each group of inputs alone, and the model with one group removed. No group alone was near the full model, and no
  group was necessary. The activity of all the region did not help. These checks have no table, thus we give no number for them.
- We made one change: the input "activity near the event". Fires come in groups in space and time, and the input
  uses only the days before the first alert. We made no other change, and the penalty stays at its first value.
- On 2024: the match separation is 0.8658 at moment 0 and 0.8752 at moment 24. That of the level is 0.5652 and 0.648.
  The Brier skill is 0.3951 and 0.4025. That of the level is 0.0152 and 0.0882 (7085 alerts at moment 0, 3447 with a match).
- Top tenth at moment 0: 667 of 708 alerts match. For the level: 355 of 708.
- At moment 24, 1326 of 6037 alerts matched in 2023, and 2945 of 6473 in 2024. The model has the rate of 2023.
  No data at the time of an alert gives the rate of its year: the map comes the next year. Thus we expected hypothesis 3 to be false.
- The largest weights at moment 0: the fire power and the activity near the event (more is a match), the season,
  and the distance to indigenous land and to protected land (near is a match).

A caution for the input "activity near the event": an event near a large fire can match that fire, because the match
rule has a reach in space and in time. Then the input and the label agree for a reason that is not the event.

The table `confidence_calibration`: we put the alerts in sequence by their probability and make five equal groups.
`probability_mean` is what the model said for a group. `matched_share` is what came. `observed_to_predicted` is the
second divided by the first: 1 is a correct probability, and more than 1 says that the probability is too low.

The history of the test on 2025, all on 2026-11-23. No run changed an input, the penalty or a hypothesis:

1. The owner ran the test one time with the frozen model. Its unit was the event of the end of the year.
   Hypotheses 1 and 2 were true. Hypothesis 3 was false at moment 0.
2. Two more runs added a column each: `observed_to_predicted` and `top_tenth_fires`. They changed no other number.
3. A review said that the unit was wrong: a brigade gets alerts as they are at that time. We corrected the unit in the code.
   A check outside the repository used the frozen model of run 1 on the alerts as they were issued.
   The probability again separated the alerts better than the level. That check has no table, thus we give no number for it.
4. With the corrected unit, the weights came from 2023 again, and 2025 ran again. The tables have this last run.
   It is a second analysis of 2025, not a new test: we knew the result of run 1 when we made it.
   A new test needs a year that we did not use: 2026, when its map of burn scars exists.

The result of the test (tables `confidence` and `confidence_calibration` of 2025), with the corrected unit.
2025 has 1755 alerts at moment 0, and 354 of them match a mapped fire. At moment 24 it has 1729 and 332.

- Hypothesis 1 is true. At moment 0 the match separation of the probability is 0.839. That of the level is 0.6075.
- Hypothesis 2 is true. At moment 24 it is 0.8415 for the probability and 0.686 for the level.
- Hypothesis 3 is false at moment 0: the fourth group had a mean probability of 0.118 and a matched share of 0.2393.
  At moment 24 each group is in 0.1. But in 9 of the 10 groups the probability is too low: at moment 24 the matched share
  is 1.2 to 4.6 times the probability. The limit of 0.1 was too wide for small probabilities. Thus we give a rank at the two moments.
- The Brier skill of the probability is 0.2651 at moment 0 and 0.2827 at moment 24. That of the level is 0.0338 and 0.0911.
- Top tenth at moment 0: 126 of 175 alerts match. For the level: 35 of 175.
- The different counted fires of those alerts. With the fires of the event of the end of the year (`top_tenth_fires`):
  161 for the probability and 52 for the level. A later merge can add fires to an alert. With only the fires that the
  detections of the alert at the moment match (`top_tenth_own_fires`): 125 and 43.
  Thus in 2025 the model does not only put many alerts of one large fire at the top.
- This is not true in each year. At moment 0 in 2024, the detections of the top tenth matched 437 different fires for the
  probability and 624 for the level. In 2023 they matched 192 and 179. At moment 24 the probability has more in each year.
  Thus at moment 0 the model finds more alerts with a match, but in a year with very large fires those alerts are
  more frequently on the same fires.
- Thus the model puts the alerts in a better sequence than the level, at the first alert and one day later, in a year
  that it did not see. Its number is not a correct probability.
- 2025 is a small year. We give no range for the values: a different year can give a different result.

- Limits: the label of an alert is the match of the event that holds it at the end of the year. The GOES detections of 2025 are from GOES-16
  to 7 April and from GOES-19 from 6 April (`docs/sources.md` section 8.1). Those of 2023 and 2024 are from GOES-16. The year 2025 can have holes in its GOES record that we did not find.
  2025 had few fires: 589 counted fires, and 4246 in 2024. Thus the test has fewer events with a match.
  The layers have the limits of section 11.14.

### 11.16 The burned ground after a time

Question: for an event, did the ground burn, and how much, some days after its first detection?
The box rule of section 11.10 answers the first part, and it is weak. This section compares candidates for a better answer.
`PLAN.md` has the sequence of the work. The command `chispa candidates --year` makes the table `burn_candidates`.

The boxes, the periods, the clear pixels, the background and the minimum patch are those of the burn check (section 11.10).
Each candidate gives the hectares of a box that it calls burned. It says "burned" for a box with a minimum of hectares.

| Candidate | Source | A pixel is burned if |
|---|---|---|
| Box rule | Sentinel-2 | its dNBR minus the background is a step or more. It is the baseline. |
| Dark rule | Sentinel-2 | the same, and its near infrared reflectance after the event is a limit or less. |
| Short-wave rule | Sentinel-2 | its short-wave ratio NBR2 minus the background decreased by a step or more, with the same dark limit. |
| Monitor | MapBiomas Monitor do Fogo | the monthly map gives it as burned, from the month of the first detection to one month after the last. |
| Radar VH, radar VV | Sentinel-1 | its backscatter changed by a step or more, in decibels, from the mean scene before to the mean scene after. |

- The reason for the dark rule: a burn is dark, and bare ground or a dry field is bright. A lower dNBR step finds a burn
  on grass, and the dark limit must stop the changes that are not burns.
- NBR2 is (B11 - B12) / (B11 + B12), from the two short-wave bands. The short-wave rule came on 2026-11-23, after the
  first run of 2024: see the round on small burns below.
- `UNVERIFIED`: the method document of an earlier collection of the Monitor map says that it reads only the ground near
  an INPE hotspot (`docs/sources.md` section 8.18). We did not confirm this for the asset that we read.
  If it is true, the map can answer for an event, and it cannot find a fire with no hotspot.
- Radar has one view each 12 days. Its possible value is an answer where Sentinel-2 has no clear view.

The measures of a candidate, with the reference groups of section 11.10:

- Found share: the matched HIGH events that it calls burned, divided by those with an answer.
- No-fire share: the no-fire boxes that it calls burned, divided by those with an answer.
- Difference: the found share minus the no-fire share. It is the measure that set the box rule.
- Answer share: the boxes with an answer, divided by all boxes.
- From 2024: the agreement with the answers of a person (the second look of section 11.10).

The periods: the settings of each candidate come from 2023, as the setting with the largest difference. 2024 compares the
candidates, with the person. Then the choice is frozen, and 2025 gives the result one time.

The hypothesis, written on 2026-11-23 before the first run of a candidate:
a candidate has a larger difference than the box rule on 2025, by 0.05 or more, and a larger agreement with the person on 2024.
If this is false, the box rule stays. A candidate with a new dependency or with an answer that a person cannot explain
needs a larger margin: the owner sets it. Claude proposed 0.05, and the owner can change it before the run of 2024.

- Limits: a matched event is a larger fire than the fires that we look for. A no-fire box can have a burn that no source shows.
  Thus the difference is a measure to compare candidates. It is not the share of correct answers.

What 2023 shows (table `burn_candidates` of 2023, 2026-11-23). 2023 set the values. It is not the test.
`config.py` has the setting of each candidate.

- The box rule: found share 91 of 99, no-fire share 21 of 99, difference 0.7071.
- The dark rule, with a dNBR step of 0.2, a dark limit of 0.15 and 1 hectare: 92 of 99 and 12 of 99, difference 0.8081.
- The Monitor map, with 1 hectare: 91 of 100 and 4 of 100, difference 0.87. It has an answer for each box.
- Radar: the difference is 0.5785 for VH and 0.4361 for VV. The two are less than that of the box rule.
  Radar has an answer for 485 of the 624 boxes, and Sentinel-2 for 618: a part of the Pantanal box had no radar scene.
  Thus radar gave no better answer and no more answers in 2023. It stays in the table, with no more work on it.
- For the unmatched HIGH events, the box rule says "burned" for 184 of 420, the dark rule for 117 of 420,
  and the Monitor map for 109 of 424.
- Two cautions. The dark rule had 36 settings and the box rule 12: the best of more settings looks better in its own year.
  If the Monitor map reads only the ground near a hotspot (`UNVERIFIED`), its no-fire share is small by its design:
  a no-fire box has no detection near it. The map also comes from the group that makes the reference map.
  Thus the comparison with the answers of a person on 2024 is the fair one.

What 2024 shows, first run (2026-11-23), with the settings of 2023. The tables of that run are in the commit of that day.

- The agreement with the person: 89 of 131 chips for the box rule, 106 of 131 for the dark rule, 109 of 132 for the
  Monitor map, 80 of 109 for radar VV and 64 of 109 for radar VH.
- Thus the second part of the hypothesis was true for the dark rule and for the Monitor map.
- The gain is in the places with no burn. Of the 89 chips that the person called not burned, the box rule said "burned"
  for 29, the dark rule for 6 and the Monitor map for 7.
- No candidate found each burn of the person: 29 of 42 for the box rule, 23 of 42 for the dark rule, 27 of 43 for the Monitor map.
  A look outside the repository said that the burns with no answer were mostly those that the person gave as small.
- Radar on 2024: its difference is 0.6337 for VV and 0.6454 for VH. The two are larger than that of the box rule (0.6209),
  by less than the margin of 0.05. On 2023 the two were much less than that of the box rule.
- Radar VV agrees with the person for 80 of 109 chips (0.7339): more than the box rule, and less than the dark rule and
  the Monitor map. Radar VH agrees for 64 of 109. Radar has an answer for 109 of the 131 chips.
- Thus radar is not the best candidate in a year, and it has fewer answers. We do no more work on it.
- The dark rule and the Monitor map are not two answers to one question. The dark rule gives an answer at each clear
  view, some days after an event. The Monitor map gives one answer for a month, some weeks after that month.

The round on small burns (2026-11-23). It had a limit: one round, and a rule to stop that we wrote before the look.

- A look outside the repository tried two ideas on the chips of 2024: the short-wave ratio NBR2, and a lower step with
  the same answer in a later view.
- The rule to stop: a variant must find 6 or more of the 13 burns that the person gave as small, and it must say "burned"
  for 8 or fewer of the 89 chips that the person called not burned.
- The short-wave ratio with a dark limit passed. The later view changed little, and it makes an answer later: we do not use it.
- Thus the short-wave rule became a candidate with a table. The measures of 2023 and 2024 were made again with it.
  No older value of a measure changed.

The choice for the test of 2025, frozen on 2026-11-23 before a run of a candidate on 2025. `config.py` has the settings.

- The box rule, the Monitor map and radar keep their setting of 2023.
- The dark rule and the short-wave rule have the setting with the largest agreement with the person on 2024.
  Thus their numbers of 2024 are too good: we selected them on those chips. On 2023 the dark rule had its largest
  difference with a different setting (table `burn_candidates` of 2023).
- With these settings on 2024 (tables `burn_candidates` and `burn_candidates_person`): the short-wave rule agrees with
  the person for 114 of 131 chips, the dark rule for 112, the Monitor map for 109 of 132 and the box rule for 89.
  The short-wave rule finds 32 of the 42 burns of the person, and it says "burned" for 7 of the 89 other chips.
  Its difference is 0.8256, that of the dark rule is 0.8458, and that of the box rule is 0.6209.
- On 2023 the short-wave rule has a difference of 0.7475, with 17 of 99 no-fire boxes: more than the dark rule (13 of 99).
  It finds more small burns, and it says "burned" for more places with no fire.
- The first candidate is the short-wave rule. The other candidates are in the table for a comparison.

The hypothesis for 2025, written on 2026-11-23 before the run: the short-wave rule has a larger difference than the
box rule, by 0.05 or more, and a larger agreement with the answers of a person on new chips of 2025, by 0.05 or more.
The person makes those answers before a candidate runs on 2025: 80 chips, with the rules of section 11.10.
If the hypothesis is false, the box rule stays, and we say so.

The result of the test (tables `burn_candidates`, `burn_candidates_person` and `image_check_2` of 2025, 2026-11-24).
The command ran one time, after the 80 answers of the person were complete.

- The person said "burned" for 6 of 23 unmatched HIGH events with a clear answer, for 16 of 18 with a match, and for
  0 of 30 no-fire boxes. No answer of 2025 has the area `small`.
- The difference: 0.66 for the box rule (83 of 100 found, 17 of 100 no-fire boxes), 0.79 for the short-wave rule
  (92 and 13), 0.85 for the dark rule (90 and 5), 0.89 for the Monitor map (89 and 0), 0.3585 for radar VV and 0.4789 for radar VH.
- The agreement with the person, for 71 chips: 58 for the box rule, 57 for the short-wave rule, 64 for the dark rule
  and 61 for the Monitor map. For radar it is 43 and 45 of 64 chips.
- The hypothesis is false. The short-wave rule has the larger difference (0.79 against 0.66). It does not have the larger
  agreement with the person (0.8028 against 0.8169): it said "burned" for 12 of the 49 chips that the person called not burned.
  The box rule said so for 9. Thus the gain of the short-wave rule on 2024 came from the selection of its setting on those chips.
- The dark rule was in the table for a comparison, with a setting that we froze before the run. Its difference is 0.85,
  and it agrees with the person for 64 of 71 chips: more than the box rule by 0.19 and by 0.0845.
  It was not the first candidate. Thus a choice of the dark rule now is a choice after the test, and we say so.
  Its difference was also larger than that of the box rule on 2023 and on 2024, with this setting.
- By the rule of the hypothesis the box rule stays. The owner decides if the dark rule replaces it.
- The owner decided on 2026-11-24: the dark rule gives the burned ground of an event (`config.BURN_RULE`).
  It is a choice after the test. The reasons: its setting was frozen before the run of 2025, and its difference was
  larger than that of the box rule in 2023, 2024 and 2025.
- Radar is far below the box rule on 2025. The Monitor map is near the dark rule: it gives one answer for a month.
- Limits: 71 chips, and one person. The answers of 2025 have no small burn, thus this test says nothing on small burns.
  The no-fire boxes do not use the person: the short-wave rule said "burned" for 13 of 100, and the dark rule for 5.

### 11.17 The burn curve

Question: how much ground of an event burned by a number of days after its first detection?
The selected rule of section 11.16 gives one answer, at the first clear view after the last detection.
The burn curve gives an answer at fixed days after the first detection (`config.CURVE_DAYS`): it is a label
for the confidence, a target for the growth risk, and a reference for a year with no map of burn scars.
`sentinel2.py` makes the curve of a box. The command `chispa curve --year` makes the tables.

1. The box, the view before the event, the clear pixels and the minimum patch are those of the burn check (section 11.10).
2. A day counts from the first detection. The answer of a day uses the images from the day after the last detection
   to the end of that day. An event that still burns at a day has no answer at that day.
3. Each pixel has one view: its oldest clear view in those images. A pixel is burned by the selected rule:
   the dNBR against the view before, minus the background, and the dark limit.
4. Thus a later day adds the pixels that got their first clear view. It does not look at a pixel a second time.
5. The clear share at a day is the share of the box with a view to that day. The curve has an answer at a day
   if that share is the minimum of the burn check or more.

The table `burn_curve` gives, for each group of the burn check and each day, the boxes with an answer, the boxes
that the curve calls burned, and how many boxes have the same answer at that day and at the last day. The table `burn_curve_check` compares the last day of the curve with two slower answers
for the same boxes: the selected rule at its first clear view (table `burn_candidates`), and the Monitor map of the months.

The first definition, and why it stopped (2026-11-24). It joined the burned pixels of each image to a day: a pixel was
burned if a minimum of one image called it burned. We wrote its hypotheses before its run on 2023 to 2025.
One was: for the no-fire boxes, the burned share at day 30 is not more than 0.05 above that of the selected rule.
It was false in each of the three years: each image adds its errors, thus more images give more boxes with a false burn.
The table `burn_curve_joined` gives that result, from a measure that stays in the code only for this table:
at day 30 the first definition called 22 of 98 no-fire boxes burned in 2023, 14 of 99 in 2024 and 16 of 100 in 2025.
The definition above calls 13 of 98, 4 of 98 and 5 of 100. The definition above replaced it.
The first run of the first definition was on 2026-11-24, on the boxes of the three years. Thus the result of the
definition above is a second analysis of the same boxes: it is not an independent test.

The hypotheses of the definition above, written on 2026-11-24 before its first run, for each year from 2023 to 2025.
The curve has no setting of its own: the rule is frozen, and the days are round numbers.

1. The curve has an answer for half of the boxes or more at day 10, and for 9 of 10 boxes or more at day 30.
2. At day 30 the curve and the selected rule give the same answer for 95 of 100 boxes or more, in each group.
3. For the no-fire boxes, the burned share of the curve at each day is not more than 0.05 above that of the selected rule.
4. For the matched HIGH events, the burned share of the curve at day 10 is not more than 0.05 below that of the selected rule.
   Thus an early answer is as good as a late answer.

If hypothesis 3 or 4 is false, we do not use the early answers of the curve as a label.

The result (tables `burn_curve` and `burn_curve_check` of 2023, 2024 and 2025, 2026-11-24): the four hypotheses are true
in each year.

- The answers. At day 5 the curve has an answer for 22 to 39 of 100 boxes of a group. At day 10 it has one for 57 to 79,
  at day 20 for 87 to 96, and at day 30 for 95 to 100. Thus Sentinel-2 gives an answer for approximately one third of the
  events in 5 days, and for approximately 7 of 10 in 10 days.
- At day 30 the curve and the selected rule give the same answer for each box with the two answers.
- The no-fire boxes. The burned share is 0.0 to 0.0811 at day 5 and 0.0253 to 0.0779 at day 10. At day 30 it is that of
  the selected rule: 0.1327 in 2023, 0.0408 in 2024 and 0.05 in 2025.
- The matched HIGH events. The burned share at day 10 is 0.8986, 0.8421 and 0.8636 in the three years. That of the
  selected rule is 0.9192, 0.8866 and 0.9. The largest difference is 0.0445, in 2024.
- A correction after a review (2026-11-24). Hypothesis 4 ends with "an early answer is as good as a late answer".
  The burned share of a different set of boxes does not show that. The table now compares the same boxes: for the
  boxes with an answer at day 10 and at day 30, the two answers are the same for 299 of 305, 222 of 225 and 133 of 135
  unmatched events in the three years, for 68 of 69, 56 of 57 and 65 of 66 matched events, and for 77 of 77, 79 of 79
  and 78 of 79 no-fire boxes. Thus an early answer rarely changes. This does not say that the early answer is correct:
  a check of the answer at day 10 against a person is not built. At day 10 the curve has no answer for 21 to 43 of 100 boxes.
- The burned hectares increase with the day: the median of the matched events with a burn is 24 to 45 hectares at day 5,
  and 60 to 102 at day 30. More pixels get their view, and the larger events get their answer later.
- The unmatched HIGH events with a burn at day 30: 144 of 419 in 2023, 85 of 295 in 2024 and 60 of 186 in 2025.
- The Monitor map of the months gives the same answer as the curve at day 30 for 83 to 89 of 100 matched events,
  for 72 to 78 of 100 unmatched events, and for 87 to 96 of 100 no-fire boxes. The rank correlation of the hectares
  is 0.6835 to 0.7768 for the matched events. The two answers agree in part: no one of them is the reference of the other.
- Thus the curve can be a label at a day, with its answer share: "no answer" is not "not burned".

The curve of each event (`chispa curve --year --events`, table `burn_curve_events`).

1. The events are those of a year with their centre in the biome. The box of an event is the box of its detections at the
   end of the year, with the margin of the burn check. The group of an event is its final level.
2. An event of the year in progress is in the list only when its last day of the curve is some days in the past (`config.py`).
3. The curves are in `data/curves/`, with the events that they measured. The files are large: they are not in the repository.
   The command makes them again. A year needs no map of burn scars: 2026 has curves.
4. The table gives, for each level and each day, the events with an answer and the events that the curve calls burned.
5. For a year with a map, the table `burn_curve_map` compares the answer of the curve at day 30 with the match of each event.

The hypothesis, written on 2026-11-24 before the first result: in each year from 2023 to 2026, the burned share at day 30
increases with the final level: LOW, then MEDIUM, then HIGH. The matched share of the events does this against the map
(section 11.2). The curve uses no map, thus it is a second answer to the same question, and the first one for 2026.
If it is false in a year, the level or the curve says a different thing than the map in that year, and we say so.

The result (tables `burn_curve_events` and `burn_curve_map` of 2023 to 2026, 2026-11-24).

- The events with a curve: 5821 in 2023, 6112 in 2024, 1692 in 2025, and 1085 in 2026, with a first detection from
  1 January to 19 October.
- The hypothesis is true in each of the four years. The burned share at day 30 for LOW, MEDIUM and HIGH events:
  593 of 2693, 714 of 2037 and 704 of 1018 in 2023. 957 of 2814, 798 of 1724 and 1097 of 1410 in 2024.
  179 of 929, 118 of 347 and 229 of 370 in 2025. 114 of 549, 95 of 219 and 235 of 310 in 2026.
- Thus the levels have the same sequence in 2026, a year with no map and with no rule that we set on it.
- The answers at day 10: 61 to 75 of 100 events of a level in 2023 and 2024, 71 to 78 in 2025, and 83 to 87 in 2026.
- The curve against the map, for the events with an answer of the curve. The two give the same answer for 0.831, 0.8816
  and 0.8189 of the HIGH events in 2023, 2024 and 2025, for 0.7354, 0.7146 and 0.6657 of the MEDIUM events, and for
  0.8069, 0.7175 and 0.7374 of the LOW events.
- The two differ in the two directions. In 2025, 47 HIGH events have a burn and no match: a burn that the map does not
  have, or an error of the curve. In 2024, 650 LOW events have a match and no burn: a small burn that the curve does not
  find, or a match with a large fire that is near and not at the place of the event. We cannot separate these causes
  without a person.
- Thus the curve is not a copy of the map, and the map is not a copy of the curve. Give the reference with each result.

- Limits: the box of an event at the end of the year can hold more than one fire, and a very large event has a very
  large box. A level uses the number of passes, thus an event with a HIGH level lasts longer: it has its answer later.
  The curve does not find most small burns (section 11.16), and a LOW event is more frequently a small fire.

- Limits: the boxes are those of the burn check, not each event. We saw the results of the first definition before
  this one: it is a second analysis of the same boxes. The curve does not show the growth in an event: its images start
  after the last detection. The check against the Monitor map compares two answers that are not independent of the detections.
  Section 11.19 has the check against the annual map for each pixel. Section 11.20 has the advance of VIIRS against
  the new burned ground.

### 11.18 The confidence against the burn curve, and the test of 2026

Section 11.15 ended with: a new test of the confidence model needs 2026, when its map of burn scars exists.
The burn curve (section 11.17) gives an outcome for 2026 now. The command `chispa confidence --year` makes the table
`confidence_curve` for a year with curves of its events.

1. The model is the frozen model of section 11.15: its weights are from 2023, with the match with the map as the label.
   Nothing of it changes.
2. The alerts are those of section 11.15, as they were at moment 0 and at moment 24.
3. The outcome of an alert is the answer of the burn curve at day 30 for the event that holds the alert at the end of
   the year: burned or not burned. An alert of an event with no answer of the curve is not in the table.
4. The measure is the burn separation: the probability that an alert with a burn has a larger value than an alert with none.
   The table gives it for the probability of the model and for the level. A year with a map also has the match separation
   for the same alerts.

The hypotheses, written on 2026-11-24 before the first run of the command:

1. In 2026, at moment 0, the burn separation of the probability is larger than that of the level.
2. In 2026, at moment 24, the burn separation of the probability is larger than that of the level.

2026 gave the model no weight, no input and no setting, and it gave the dark rule no setting.
2025 has the same table for a comparison: there the two outcomes exist for the same alerts.
If a hypothesis is false, the rank is not better than the level for the burned ground in 2026, and we say so.

The result of the test (table `confidence_curve` of 2026, 2026-11-24). The command ran one time.
2026 has 1103 alerts at moment 0 with an answer of the curve, and 467 of them have a burn. At moment 24 it has 1078 and 444.

- Hypothesis 1 is true. At moment 0 the burn separation of the probability is 0.8242. That of the level is 0.6097.
- Hypothesis 2 is true. At moment 24 it is 0.8439 for the probability and 0.7481 for the level.
- The top tenth at moment 0: 108 of the 110 alerts with the largest probabilities have a burn. For the level: 59 of 110.
- The same table for 2025, where the alerts have the two outcomes: the burn separation of the probability is 0.7722 at
  moment 0, and its match separation is 0.8339. For the level the two are 0.6161 and 0.6097.
  Thus the model is better than the level against each outcome. It is nearer to the label that it learned.
- Thus the model puts new alerts in a better sequence than the level in 2026 also: a year that gave it nothing,
  against an outcome that is not the map. Its value stays a rank, not a probability (section 11.15).

- Limits: the outcome is the answer of a rule, not a map and not a person. The rule does not find most small burns.
  The model learned the match with the map: a burn is a different label. The events of 2026 are those to 19 October.
  The detections of 2026 before the live logs are from the archive, with an estimate of `available_at`.

### 11.19 The hectares of the rule against the map

The checks of sections 11.16 and 11.17 are for "burned" or "not burned". The burn curve also gives hectares, and the
growth risk needs them as its target. This section compares the burned pixels of the selected rule with the pixels of the
annual map of burn scars. The command `chispa pixels --year` makes the table `burn_pixels`.

1. The boxes are those of the burn check. The rule is the selected rule at its first clear view after the event.
2. The map pixels are those of the annual map with a burn from the month of the first detection to one month after the
   month of the last detection, in the same year (the month rule of section 11.4).
3. Only the pixels with a clear view of the rule count. For each box: the hectares of the rule, the hectares of the map,
   and the hectares that the two have.
4. The table gives, for each group: the sums of the three areas, the share of the map area that the rule finds, the share
   of the rule area that the map has, the rank correlation of the two hectares of a box, and the median of their ratio.
   The ratio is for the boxes where the map has the minimum area of the box rule or more.

The hypotheses, written on 2026-11-24 before the first run, for the matched HIGH events of each year from 2023 to 2025:

1. The rank correlation between the hectares of the rule and the hectares of the map is 0.7 or more.
2. The median ratio of the hectares of the rule to the hectares of the map is from 0.5 to 2.

If hypothesis 1 is true and hypothesis 2 is false, the hectares of the rule give a sequence of the events and not an area.
If hypothesis 1 is false, the hectares are not a target for the growth risk.

The result (table `burn_pixels` of 2023, 2024 and 2025, 2026-11-24): the two hypotheses are false in each year.

- The rank correlation for the matched HIGH events is 0.5214 in 2023, 0.6498 in 2024 and 0.6694 in 2025: less than 0.7.
- The median ratio is 0.4644, 0.2153 and 0.3954: the rule has less than half of the hectares of the map for the typical event.
- The rule finds 0.3685, 0.3392 and 0.4815 of the map area in the boxes. 0.6249, 0.7947 and 0.5563 of the rule area is in the map.
- The no-fire boxes have 325, 64 and 40 hectares of the rule in 100 boxes: the rule calls little ground burned with no fire.
- Thus the selected rule says if the ground of an event burned. It does not give the burned area, and its hectares are
  not a target for the growth risk. The curve stays a label: "burned", "not burned" or "no answer".
- Possible causes, not separated: the rule subtracts the background of a box, its two limits were selected for few false
  burns, and the map pixels of the months of an event can be of a different fire in the same box.
- A look outside the repository, with no table: in the same boxes the hectares of the Monitor map are nearer to those of
  the annual map than the hectares of the rule. The two maps come from one group, thus this is not an independent check.

- Limits: the map is not exact. It does not have each small burn, and its month can be one month late.
  The rule subtracts the background of a box, thus it finds less in a box where most of the ground burned.
  The map has pixels of 30 m, and the rule has pixels of 20 m. An event of December has no month after it in the same year.

### 11.20 The advance of VIIRS against the new burned ground

Section 11.13 gives the advance and the direction of an event from its VIIRS pixels. That measure had no reference in
the repository. This section compares it with the new burned ground between two Sentinel-2 images of the same event.
The command `chispa advance --year` makes the table `advance_check`.

1. The events are the HIGH events of a year with their centre in the biome, with VIIRS detections, and with a time
   from the first detection to the last detection of the minimum in `config.py` or more.
2. View A is the first image after the first detection with the minimum share of the box with no cloud (section 11.10).
   View B is the first such image a minimum number of days after view A, not later than the last detection plus the days of the burn check.
3. In each view, a pixel is burned by the selected rule, against the view before the event. The new burned ground is
   each pixel that is burned in view B and not in view A, with a clear view in the two.
4. The advance of Sentinel-2 is a high percentile of the distance from each new burned pixel to the nearest pixel that
   was burned in view A. Only the pixels in the box count.
5. The advance of VIIRS uses the same percentile as section 11.13, with two groups of detections:
   those to the time of view A, and those from view A to view B.
6. The direction has one definition for the two satellites: from the centre of the older group to the centre of the
   new group. It is not the direction of section 11.13, which uses the line from each new pixel to its nearest older pixel.
7. Two advances agree if the larger is not more than a factor of the smaller. Two directions agree if the angle
   between them is not more than a limit. `config.py` has the two values.
8. An event counts if the two satellites have a value: burned ground in view A, new burned ground, and VIIRS pixels in the two groups.

The hypotheses, written on 2026-11-24 before the first run, for each year from 2023 to 2025. A study outside the
repository on 19 large fires of 2023 gave them (`PLAN.md`):

1. For more than half of the events, the two advances agree to a factor of 2.
2. For more than half of the events with a direction of VIIRS, the two directions agree to 45 degrees.

If a hypothesis is false, the advance or the direction of an alert has no support from the burned ground, and we say so.

The result (table `advance_check` of 2023, 2024 and 2025, 2026-11-24).

- The events with the two advances: 34 of 65 long events in 2023, 80 of 134 in 2024 and 5 of 7 in 2025.
  The other events had no two clear views, no burned ground in a view, or no VIIRS pixel in one of the two groups.
- Hypothesis 1 is true in each year. The two advances agree to a factor of 2 for 23 of 34 events, for 57 of 80 and for
  4 of 5. The median ratio of the advance of VIIRS to that of the burned ground is 0.9526, 1.0782 and 1.0993.
- Hypothesis 2, first run: true in 2023 and in 2024, and false in 2025 (2 of 5 events). That run compared two different
  definitions of a direction: the centres for the burned ground, and the lines of section 11.13 for VIIRS.
- A review asked for one definition (rule 6 above), and for the distance from the burned pixels of the box only.
  The tables have this second run. The two directions agree to 45 degrees for 24 of 34 events in 2023, for 56 of 80
  in 2024 and for 3 of 5 in 2025. Thus hypothesis 2 is true in each year in the second run. 2025 changed from false
  to true by one event of five: it has too few events to support the hypothesis or to reject it.
- The median advance of VIIRS is 2806 m, 3623 m and 5224 m. That of the burned ground is 3721 m, 3047 m and 4400 m.
- Thus, for a fire of some days, the advance and the direction of the VIIRS pixels agree with the new burned ground for
  approximately 2 of 3 events. The measure of section 11.13 has a reference now, for these long events only.

- Limits: the rule does not give a correct burned area (section 11.19): this check uses where its pixels are, not how
  many. An event needs two clear views in its days: these are long events, mostly large fires. The check says nothing
  about one step of 12 hours, or about a small fire. The distance of a pixel has a largest value of approximately 20 km.

## 12. Agent and MCP rules

### 12.1 Tools

Five tools exist: `alerts_near`, `event_record`, `activity`, `live_status` and `evaluation_summary`. The maximum is six.
`activity` gives, for each time step of a window, the events with a new detection by level and the detections
of each sensor family. Its events are the events of the as-of time, the same events that `alerts_near` gives.
`live_status` reads the poll log. It gives the newest pass at or before the as-of time with the result of each source,
the newest pass in which no source failed, and the time from which the data is late. It gives no failure text:
a text can hold a key or an address. A source with no row in a pass read no new item and recorded no failure.
Read these rules before you write or change a tool. A test does a check of the rules that a program can examine.

1. A tool is one function in `tools.py` with typed arguments, a typed return value and a docstring.
2. A tool has no logic. It does a check of its arguments, opens the store and calls a module that has the logic
   and its tests. If a tool needs a new calculation, write it in that module first.
3. Each tool that reads events has an as-of time. It uses only detections with `available_at` at or before that time,
   and the events as they were at that time (`issued.py`). Two tools give the same id for the same event at the same time.
4. A tool returns plain data with units in the names, times as UTC text and source names. A value that is absent is `None`.
5. A tool gives no value that has no measure in `results/SUMMARY.md` or no rule in this document.
6. A new tool, or a new field of the event record, needs the agreement of the owner. Ask before you add one.
7. The MCP server, the agent and the dashboard expose the same functions. Do not write a tool two times.

### 12.2 Answers

The agent must:

1. Answer only from tool results.
2. Give the time and the source of each number.
3. Say when the data is old. Give the age of the newest detection.
4. Say "no detection" and not "no fire". A satellite does not see through thick cloud.
5. Give intensity as FRP in megawatts, with the sensor name.
6. Give growth only as measured growth. Do not call it a forecast.
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

### 12.6 Dashboard

`chispa serve` starts the dashboard. `web/server.py` calls the tools, and the page shows their answers.

1. The page formats values. It calculates no new fact and has no threshold. Each value has its unit and its time.
2. The page has one as-of time. Live: the time of the request, again each few minutes. Replay: a recorded moment.
   The history band counts the steps to the as-of time with the events of the as-of time. In a replay it can also
   show the steps after the as-of time, dark, with the events of the end of the window.
   A swipe moves the window of the band by whole steps, and the as-of time stays. Live, the window ends at the latest
   at the as-of time. A window that ends before the as-of time also counts its steps with the events of the as-of time:
   the steps from its start to the as-of time must fit in one answer of `activity` (`config.TOOL_MAX_STEPS`).
3. The base image is a mosaic. It is not an image of the as-of time. A burn scar in it can be of a different year.
4. The growth matrix shows the steps of the record on a log scale, with the floor as a ring. A ray is a past step, not a forecast.
5. The level, the rank and the severity stay separate. The rank and the level say "no check" for an event out of the biome.
   The matched share of a level is for the level at the end of the year. The rank gives its number of reference alerts
   and the hours of its model after the first detection.
6. The text uses the terms of the glossary: "event", "unmatched", "no detection" and not "no fire".
7. The lag is the time from the newest pass in which no source failed to the as-of time. Live: to the clock of the
   computer, each second. A pass with a failure does not make the data newer. `live_status` gives the time from which
   the data is late; the page compares it with its clock. Before the live logs: "archive". In the live period with
   no such pass: "no pass". The lag is not the delay of a source (`PLAN.md`, live operation).
8. Pantanal time is the time of the zone in `config.py`, with its offset on the page. Data, tools and results stay in UTC.
9. A time to CHISPA that includes a stop of the poller (`poller_stop_h`) has a mark with the most that the stop added.
   The last clear look is the newest GOES scan after the last detection with "examined, no fire".
   After the last detection, the timeline has one row for each run of GOES scans with one answer. Folded, it keeps each
   run of fire or possible fire and the newest runs.
   The page does not say that a fire is out.

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
| For recorded data, `available_at` is `observed_at` plus a fixed delay for each sensor family. | The archive files give no publication time. The live poller measures it (section 8.10). | The delays are estimates. Each result that uses `available_at` depends on them. |
| A live row that the poller first saw after a stop gets an estimate of `available_at` (section 9.2). | A replay must show what a poller with no stop gives. The time of the first view is the time of our stop. | The estimate is not a measurement. For FIRMS it uses the fixed delay. |
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

### 13.5 Stages

| Choice | Reason | Pitfall |
|---|---|---|
| The first alert goes out at the first detection, before a confirmation. | A second sensor family can come hours or days later. | Approximately half of the LOW events of 2024 matched no mapped fire (`results/SUMMARY.md`). |
| The burn scar map can train a rule, but it is never an input of an event. | The map comes the next year. A rule that saw the fires of its test gives a result that is too good. | The labels have the errors of the map. |
| We do not count precision only for large fires. | A detection gives a pixel, not the size of the fire. | The precision stays a lower limit until a check against images (`PLAN.md`). |
| The end of a fire has no cause in the record. | We have no record of brigades. Rain, water and fuel also stop a fire. | We cannot measure the effect of a brigade. |
