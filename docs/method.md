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
| Alert with a new fire | An alert that had the first detection that matches a counted fire (section 11.21). |
| Alert on a known fire | An alert whose detections match a counted fire that a different alert saw first (section 11.21). |
| Large alert | An alert whose fire ends with a limit of hectares or more. It is the label of the growth risk (section 11.21). |
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
| Growth | `growth`: the newest step. `growth_steps`: each step, the oldest first (section 11.13). `forecast`: the growth forecast of each front of the event, for each window that is open (section 11.29) | A burned area (section 11.12). A distance and a speed of the growth to come |
| Confirmation | `level_changes`, the pass that made each change (`passes`), `absorbed` | |
| End | `goes_view`: what GOES said for the place in its newest saved scan and in each scan after the newest detection, with the last clear look. `viirs_passes_after_last_detection` | A cause of the end. A statement that a fire is out |
| Mapping | The track record of the level (`evaluation_summary`) | |

`severity` has the number, the points of each part and the facts (section 11.14).

- A field with no value is `None`. Do not fill it with an estimate. `notes` says why a part is absent.
- `forecast` is `None` when no forecast file has a front of the event with an open window. A front of 1 or 2
  pixels has its chances and no sectors: the forecast has no direction for it (section 11.30).
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
  `after_last_detection` counts them in each group.
  `runs_after_last_detection` gives the same scans in time sequence. The scans of one answer in a row are one run:
  fire, possible fire, no fire, or "not_seen" (cloud, no background, blocked, water, not processed). A run gives its first
  and last scan, its number of scans and the number in each group.
  `last_clear_look` is the newest scan after the newest detection with an answer, whatever the answer. A scan with fire at one
  pixel and cloud at a different pixel saw fire. If no scan has an answer, the last clear look is the newest detection:
  a detection is a look that saw fire. `kind` is `goes_scan` or `last_detection`. `scans_after` and `groups_after` give
  the saved scans after the last clear look. None of them has an answer.
  The recorded masks have one scan of each hour, the live masks each scan.
  It is the place of the newest pass only. It does not say that a fire is out: GOES can miss a small fire.
- The level and the confidence rank put the events in a sequence by their evidence for a match with a mapped fire.
  They do not decide that a fire is real: a burn can be absent from the map. `goes_view`, `growth` and the passes after
  the last detection say what the sensors see now. Do not use one for the other.

### 7.4 Rules for a new part

These rules are for each part that we add to a stage, with a trained model or without.

1. Write the hypothesis of the part before its result. Give the baseline: the rule that the part must be better than.
2. Train on 2023. Tune on 2024, which we know now. Do the test one time on 2025.
   The growth risk has a different form, which the owner agreed to on 2026-11-25: a cross-validation by year
   on 2019 to 2025, and a test on 2026 (section 11.21).
   The growth forecast also has its form, which the owner agreed to on 2026-11-26: the rules come from 2019 to 2024,
   with one year left out in turn, and 2025 and 2026 score them one time (section 11.26).
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

From 2026-11-26 the match also has the year: a detection matches only a fire of the map of the year of its
observation. Before that day, a detection of 31 December that became available in the next year matched a fire by its
month and its day only. The owner decided the change on 2026-11-23, for the first run on 2026 (section 11.25).
We made the tables of `chispa evaluate` again on 2026-11-26 with the rule of now, for 2023, 2024 and 2025.
One detection of 2024 is now unmatched: three counts of unmatched detections in the table `configurations` of
2024 are larger by 1. No other value of a table changed.

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
- Each table is a CSV file in `results/`. The file `stamps.csv` of a year gives the stamp of each of its tables:
  the configuration hash and the day of the run. Thus a new run changes only the rows with a new value.
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
- `front_steps`: the answers of the fronts at 12 and at 24 hours (section 11.26). `front_flames`: those answers against
  the flames in Sentinel-2 images (section 11.27).
- `severity_inputs`, `severity` and `severity_rank`: the severity of the events against the mapped area (section 11.14).
- `confidence` and `confidence_weights`: the probability of a match at two moments, against the level (section 11.15).
- The tables with a name that starts with `risk`: the growth risk. Sections 11.21 to 11.25 name each table.

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
- The speed has no reference. It is a defined measure, not a checked one. Section 11.27 has a source for the position
  of the flames at a known time, for one day in five.
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

### 11.21 The growth risk

Question: at an alert, how probable is it that its fire becomes large?
The severity of section 11.14 is not a forecast of the burned area. This part gives a value for that question at the
two moments of section 11.15: 30 minutes and 24 hours after the first detection of an alert.
`chispa risk` makes the tables of each year in one run. Sections 11.22 to 11.25 give the inputs, the percentage and
the test. The owner agreed to each rule on the day that the rule names.
The tables in `results/` are for the models of now. The numbers of the models before them are in the commits
`b23ae63` (the inputs of the confidence) and `5ccd4f9` (before the ground that burned).

The words are the standard words of machine learning:

- Large: the fire of an alert ends with the limit of hectares or more. It is the label.
- Base rate: the share of the alerts that became large.
- AUC: the area below the ROC curve. It is the probability that an alert that became large has a larger value than an
  alert that did not. 0.5 is chance, and 1 is a correct sequence. Section 11.15 calls it the separation.
- Top tenth: the tenth of the alerts of a year with the largest values.
- Observed to expected: the large alerts that came, divided by the sum of the values. It is the level of the values:
  1 is correct, and more than 1 says that the values are too low.
- Brier skill score: 1 minus the mean square error of the values, divided by that of one constant. The constant is
  the base rate of the training years. More than 0 is better than that constant.
- Cross-validation by year: each year gets its numbers from models that the other years trained.
- Split in time sequence: each year gets its numbers from models that only the years before it trained.

The size and the alerts:

1. The size of a fire is its area in the store (section 11.3). It is the final area in the map, and not the area at
   the time of the alert. The map has each burn that it sees: a wildfire and a planned burn are the same to it.
2. The limits are 10, 100 and 1000 hectares (`config.RISK_CLASS_LIMITS_HA`). A fire of 10 hectares is the smallest
   counted fire: that model asks if the alert has a new fire. The tables of this section and the rule of section
   11.22 have the limits 100 and 1000 hectares. A limit of 10 000 hectares has no model: a year has 2 to 27 such fires.
3. An alert is the event as it was at the moment (`evaluation/moments.py`). It is in one of three groups.
   New fire: the alert had the first detection that matches a counted fire, and its size is the largest such fire.
   No mapped fire: its size is 0. Known fire: its detections match a counted fire that a different alert saw first.
4. An alert on a known fire is left out: the question has no meaning for it. Thus one fire gives its area to a
   maximum of one alert. The table `risk_alerts` counts each group.

The model is the logistic regression of section 11.15: one model for each moment and each limit, thus six models.
Section 11.22 gives the inputs. The baselines are the probability of the confidence model, the number of detections,
and at 24 hours the persistence rule: the advance of the newest step (section 11.13).

The years:

- The cross-validation by year chooses the inputs, by the AUC. The split in time sequence measures the level: it is
  the form of the live use. The owner decided this on 2026-11-25.
- The unit of a split is a year. The alerts of one season are not independent, and a random split is too good.
- These numbers choose inputs and rules. Thus they are validation numbers. The test year is 2026 (section 11.25).

The tables: `risk` (each value against the label), `risk_alerts`, `risk_weights`, `risk_all_alerts` (all alerts, with
no group left out: which fires the top tenth reaches), `risk_calibration` and, with the split in time sequence,
`risk_earlier`, `risk_calibration_earlier` and `risk_level_sources`.

The hypotheses for the test year, written on 2026-11-24 and 2026-11-25 before the first runs, for 100 and 1000 hectares:

1. At 30 minutes, the AUC of the growth risk is larger than that of the confidence and that of the number of detections.
2. At 24 hours, the AUC of the growth risk is larger than that of each of the three baselines.
3. For the alerts with a new fire only, the AUC of the growth risk is larger than that of each baseline.
4. With all alerts in the sequence, the top tenth of the growth risk reaches more different fires of the limit or
   more than that of each baseline.

If hypothesis 1 or 2 is false for a limit at a moment, we give no growth risk as a sequence there.
If hypothesis 3 is false, the growth risk finds the alerts with a fire and does not put the sizes in a sequence.
If hypothesis 4 is false, the gain is only for an alert with a new fire. We say each of these.
A model with less than 30 large alerts in the test year has no answer: too few (owner, 2026-11-25).

The percentage. A percentage in an alert is correct only if the values are calibrated. A model can give one if
these three conditions are true, with the split in time sequence (owner, 2026-11-25):

1. The Brier skill score is more than 0 in each scored year.
2. For the scored years together, observed to expected is from 0.8 to 1.25.
3. In each scored year, observed to expected is from 0.5 to 2.

A year is scored if its models have two training years or more: 2021 to 2025 (owner, 2026-11-26, after the first
results). The values get a recalibration first (section 11.24). If a condition is false, an alert gets a rank.

The result with the cross-validation by year (tables `risk` and `risk_all_alerts` of 2019 to 2025, 2026-11-26):

| Model | Alerts | Large alerts | AUC, growth risk | AUC, confidence | AUC, number of detections | Large alerts in the top tenth |
|---|---|---|---|---|---|---|
| 30 minutes, 100 hectares | 30 879 | 1286 | 0.8237 | 0.6975 | 0.6293 | 536 of 1286 |
| 30 minutes, 1000 hectares | 30 879 | 388 | 0.8594 | 0.7157 | 0.6306 | 190 of 388 |
| 24 hours, 100 hectares | 28 772 | 1059 | 0.9020 | 0.8287 | 0.8170 | 674 of 1059 |
| 24 hours, 1000 hectares | 28 772 | 311 | 0.9192 | 0.8662 | 0.8436 | 210 of 311 |

- An AUC is the mean of the seven years. The AUC of the growth risk is larger than that of each baseline in each of
  the 7 years, for each model. The persistence rule has 0.5697 and 0.5839 at 24 hours.
- For the alerts with a new fire only, the mean AUC of the growth risk is 0.6424, 0.6948, 0.7411 and 0.7661.
  The sequence of the sizes is the weak part of each value.
- All alerts, with no group left out. The different fires that the top tenth reaches, for the growth risk and for
  the number of detections: 1304 and 1267 of 2588, 437 and 439 of 660, 1945 and 1954 of 2642, and 587 and 589 of 659.
  Thus with these numbers hypothesis 4 is false: the gain of the growth risk is for a fire with no alert before it.

- Limits: the label is the final size of a fire, and we have no area at the time of an alert (section 11.12).
  The value is not a growth forecast (section 7.4, rule 6). The label has the errors of the map (section 11.5).
  The burn day of a fire is uncertain by some days: an alert that started a fire can have no match at its time.
  A GOES detection matches each counted fire near it. The top tenth is that of all the year: a brigade decides with
  the alerts of one day. The years before August 2022 have no GOES row from FIRMS. The detections before the live
  logs have an estimate of `available_at`. The confidence baseline has the weights of 2023.

### 11.22 The inputs of the growth risk

`evaluation/risk_inputs.py` makes the inputs. The table `risk_inputs` of each year compares sets of inputs, and the
table `risk_input_rule`, with the tables of the newest year, gives the rule for each set and each model.

The rule. We add or remove inputs in groups: a group has one reason, and its hypothesis comes before its run.
For each of the four models with 100 and 1000 hectares, a group passes if these three conditions are true:

1. The mean AUC of the seven years is larger with the group, with the cross-validation by year.
2. The AUC is larger with the group in 5 or more of the 7 years.
3. The level is not worse after the recalibration, for the scored years. For those years together, observed to
   expected is not farther from 1 by more than a margin of 0.05, and not more years are out of the range from 0.5 to 2.

A group stays if it passes for 3 or 4 of the 4 models. To remove a group, the rule is the same in the other
sequence. Each choice makes the validation numbers a little too good: the test of 2026 has no part in a choice.
The owner changed condition 3 two times after results, and we say so: the margin on 2026-11-25, and the level
after the recalibration in the place of the level before it on 2026-11-26.

The inputs of the models. Each uses what an alert has at the moment, with one exception. The ground that burned
reads the map of the year before. An alert of the first months of a year does not have that map (the limits below).

- The inputs of the confidence (section 11.15), without the calendar and without the fire power and its mark.
- The first hours, six inputs: the hour of the first detection as the two inputs of a circle, the number of GOES
  scans of 10 minutes with a detection, the same for the scans from 18:00 to 06:00, the number of passes of the
  polar-orbit satellites, and the hours from the first detection to the last. The counts and the hours are logarithms.
- The weather, six inputs from ERA5-Land (`docs/sources.md` section 8.21), at the mean position of the detections:
  the rain of 7, 30 and 90 days, the days from the last day with 1 mm of rain, and the mean of the largest wind
  speed and of the largest dryness of the air of 3 days. A day is in the product approximately 6 days after it.
  Thus each input ends 7 days before the day of the moment: an alert can have it.
- The ground that burned before, four inputs from the maps of the 10 years before the year of the alert
  (`chispa fetch burned`): the years from the last burn of the cell of the alert, the number of those years with a
  burn, and the burned share of the square of approximately 10 km around the cell, in the year before and in the
  3 years before. A cell burned in a year if half of its pixels or more burned. For the 3 years, a cell counts
  with its largest share of one year. Our files have a share for each year: they cannot give the union.

- Limits: the map of a year comes in April to July of the next year (`docs/sources.md` section 8.5). Each
  alert reads the map of the year before it. Thus an alert before that day has inputs that it cannot have at its
  time. A check outside the repository gave the alerts before 1 July no map of the year before. The mean AUC
  stays above that of the models without the group, and the same five models have the three conditions
  (`PLAN.md` has the numbers). A live alert needs the Monitor map for that year: not built. The map covers Brazil only. The weather grid is coarse, and its newest day is
  7 days old: it is the weather of the season.

Each group against the models of now (table `risk_input_rule`, 2026-11-26). The four numbers of a mean AUC are for
30 minutes with 100 and with 1000 hectares, then for 24 hours with 100 and with 1000 hectares.
With the models of now the mean AUC is 0.8237, 0.8594, 0.902 and 0.9192.

| Group | Models passed | Mean AUC without it, or with it | In the models |
|---|---|---|---|
| First hours | 4 of 4 | without: 0.8167, 0.8539, 0.8959 and 0.9149 | yes |
| Weather | 3 of 4 | without: 0.7998, 0.8153, 0.8956 and 0.905 | yes |
| People and protected land | 4 of 4 | without: 0.8095, 0.8438, 0.8948 and 0.9116 | yes |
| Ground that burned before | 3 of 4 | without: 0.801, 0.8443, 0.8833 and 0.9068 | yes, from 2026-11-26 |
| Weather to 1 day before, in the place of 7 days | 3 of 4 | with: 0.8267, 0.8613, 0.9023 and 0.9173 | no: an alert cannot have it |
| Weather of the 3 days after an alert | 2 of 4 | with: 0.8263, 0.8631, 0.9018 and 0.9186 | no: an alert cannot have it |
| Calendar: the day of the year | 0 of 4 | with: 0.8238, 0.8615, 0.9018 and 0.9187 | no |
| Fire power and its mark | 0 of 4 | with: 0.8307, 0.8623, 0.903 and 0.9194 | no |
| Dryness fields of INPE | 0 of 4 | with: 0.8199, 0.8578, 0.9006 and 0.9176 | no |
| River level at Ladário | 0 of 4 | with: 0.8285, 0.8692, 0.9032 and 0.9241 | no |

- The weather to 1 day before passes the rule with the models of now, by a small amount. ERA5-Land does not have
  those days at the time of an alert. Open-Meteo has them from a different weather model, with a different level
  of the rain and of the wind (`docs/sources.md` section 8.4). A check outside the repository used the test
  alerts of 2026 (`PLAN.md`). The weather to 1 day before gave no larger AUC, from the one source or from the other.
  The weights of the weather are in the rain of 30 and 90 days, which changes little in 6 days. Not built.
- The weather after an alert is the rain, the largest wind speed and the largest dryness of the air of 3 days, from
  the record of the weather: a forecast of those three values with no error. It does not pass. This is a result for
  those daily values on a grid of 11 km only. It says nothing about a forecast with the wind direction or with hours.
- The fire power: no GOES row of INPE has a fire power in 2019 to 2021, and each GOES row has one from 2023
  (`docs/sources.md` section 8.3). Thus the input does not say the same thing in each year, and the level is
  0.86 to 0.94 with it.
- The dryness fields are the days with no rain, the rain and the fire risk that INPE adds to its archive rows.
  The river level is that of the Paraguay River from ANA (`docs/sources.md` section 8.22): one value for all alerts
  of a day. With it the level is 0.82 to 0.89.

The hypotheses of the groups, each written before its run:

| Date | Hypothesis | Result |
|---|---|---|
| 2026-11-25 | The dryness fields pass | False: 0 of 4 |
| 2026-11-25 | The first hours pass | False with no margin (1 of 4), true with the margin |
| 2026-11-25 | The people and the land pass | False with no margin, true with the margin |
| 2026-11-25 | The weather to 1 day before passes | True: 3 of 4 |
| 2026-11-25 | The weather after is better than the weather before, for each model | False: for 2 of 4 |
| 2026-11-25 | The weather to 1 day before does not pass against the weather to 7 days before | True then (2 of 4). False with the models of now (3 of 4) |
| 2026-11-25 | The fire power and its mark pass | False: 0 of 4 |
| 2026-11-25 | The ground that burned before passes | False with the level before the recalibration (0 of 4) |
| 2026-11-25 | Its part "last burn" passes, and its part "burn frequency" does not | False (0 of 4), and true (2 of 4) |
| 2026-11-25 | The river level does not pass | True |
| 2026-11-26 | With the level after the recalibration, the ground that burned before passes | True: 3 of 4. Not a hypothesis in the sense of section 7.4: a check outside the repository came first |
| 2026-11-26 | With that rule, the three groups in the models pass, and no other set passes | True for the three groups. False for the two parts of the ground that burned before: they pass |

Where the level changes with the year (tables `risk_alerts` and `risk_level_sources`, 2026-11-26):

- Of the alerts with a new fire at 30 minutes, the share that became large for 100 hectares is almost the same in
  each year: from 34.6 percent (362 of 1047 in 2019) to 44.8 percent (187 of 417 in 2024).
- The share of the alerts that have a new fire is not the same: 1047 of 6074 in 2019 (17.2 percent), and 245 of 5630
  in 2023 (4.4 percent). Thus the level of a year is wrong in the question "does this alert have a mapped fire".
- 2023 has two causes. The first is a source. From October 2023 to February 2024, INPE has 0.47 to 1.22 GOES rows
  for each GOES row of FIRMS. In each other month of the comparison it has 0.03 to 0.46 (`docs/sources.md` section
  8.3). 2765 alerts of 2023 have only GOES rows of INPE at 30 minutes. For 100 hectares the models of the earlier
  years expected 167.7 large alerts from them, and 14 came: 153.7 too many.
- The second cause is the size of the fire season. For each other alert of 2023 the models expected 174.3, and 72
  came: 102.3 too many. Thus the alerts with only GOES rows of INPE have approximately 6 of 10 parts of the
  excess, and the other alerts 4. These are totals of two groups of alerts, not of two causes: the season is in
  the two groups.
- We do not know what those GOES rows of INPE are. 14 of the 2765 alerts became large for 100 hectares: those
  have a mapped fire. An alert of the group with no mapped fire is an unmatched alert, not a false alarm (section 11.5).

### 11.23 The alerts with a new fire only

Question: if an alert has a new fire, how probable is it that this fire becomes large?
This is the second question of section 11.22, where the level does not change with the year. The owner chose this
form on 2026-11-25, and said after its result that one model has little value for a brigade. It stays a result.

- The models have the form and the inputs of the growth risk. They get their weights from the alerts with a new
  fire only, and the tables measure them on those alerts: `risk_fire` (cross-validation by year) and
  `risk_fire_calibration` (split in time sequence, 2020 to 2025, with no recalibration).
- The value is a conditional probability. Its condition is: the alert is the first alert on a mapped fire of
  10 hectares or more. A later alert on that fire has no part in the models or in the tables.
- This part has no hypothesis in the sense of section 7.4: a check outside the repository gave its result before we
  wrote what we expected. Thus it is an exploratory result, and the years of its numbers cannot test it.
- With the models of now (2026-11-26), the three conditions are true for the two models at 24 hours. For 100
  hectares: 773 large alerts for 784.6 expected, 0.711 to 1.2977 in each year, and a mean AUC of 0.7513.
  For 1000 hectares: 238 for 261.0, 0.5271 to 1.1055, and 0.7719. At 30 minutes the Brier skill score is less
  than 0 in 2020 or in 2023: -0.032 and -0.0566 for 100 hectares, and -0.0154 for 1000 hectares.
- No alert gives this value: the percentage of an alert is that of section 11.24. It has no test on new alerts:
  such a test needs a hypothesis and a baseline first.

### 11.24 The recalibration and the percentage

The share of the alerts with a mapped fire changes with the size of the fire season (section 11.22), and no input
has it. A recalibration corrects the level of the values with the outcomes that are known at the time of an alert.
It does not change the models. Two alerts with the same factor keep their sequence. The factor changes with the
time of an alert, thus the sequence of the alerts of a year can change. The owner agreed to it on 2026-11-25.
`evaluation/risk_recalibration.py` makes it, in the run of `chispa risk`.

The rule:

1. The alerts are those of section 11.21, without the alerts with only GOES rows of INPE at the moment.
   Such an alert gets a rank and no percentage (owner, 2026-11-25). When a row of a different source or sensor
   family joins the alert, it gets a percentage at the next moment.
2. The value of an alert comes from the models of the earlier years: the split in time sequence.
3. At the time T of the moment of an alert, an outcome is known if its alert had its moment 60 days or more before T.
   The known outcomes of the 365 days before T count. The factor is the large alerts that came plus 10, divided by
   the large alerts that the values expected plus 10. The values are those of that time, with no recalibration.
4. The odds of the value are multiplied by the factor. Each model has its own factor.
5. The classes of an alert come from its three values: no fire of 10 hectares, 10 to 100, 100 to 1000, and 1000
   hectares or more. If a value for a larger limit is larger than the value for the limit before it, the alert has
   a wrong sequence: it gets the smaller of the two, and the class between gets 0.

The tables, for each scored year: `risk_recalibrated` (the level, the Brier skill score and the AUC after and before the
recalibration, for all alerts and for each tenth, with the factor and the alerts with a rank only), `risk_classes`,
and `risk_percentage` with the newest year: the three conditions of each model, as code.

- Limits: the outcome of an alert is its label of the annual map, as if a map gave it 60 days after the alert.
  That label is the final size. A fire can burn, or join a different fire, after those 60 days: then the factor
  has an outcome that no person had at that time. We did not measure how frequently this occurs.
  A live alert needs the Monitor map for this: section 11.25 has a replay of the test year with the maps of the
  time. The scored years have no replay: the first day of a Monitor month before October 2025 is not known.
  The models of a year start on 1 January with the map of the year before it, which comes in April to July.
  A check outside the repository gave the alerts before 1 July the weights of the years to 2 years before.
  The same five models have the three conditions for 2022 to 2025 (`PLAN.md`).
  The group of an alert comes from the map of the year: new fire, no mapped fire or known fire. A live alert does
  not have that map. Thus no rule says at the time of an alert that it is on a known fire. The percentage has
  no check for such an alert. Not built.
  The 60 days, the 365 days and the 10 came from a check outside the repository, which gave the same
  result for 12 settings (30 to 120 days, and 5 to 20). The recalibration, the scored years and the rank for the
  alerts with only GOES rows of INPE came after results: the numbers are validation numbers.

What we wrote before each first run. Two statements of 2026-11-25 came after a check outside the repository: the
three conditions are true for 100 hectares at 30 minutes and for the two models at 24 hours, and condition 1 is false
for 1000 hectares at 30 minutes. They are not hypotheses in the sense of section 7.4: only the test of section 11.25
can confirm them. Three hypotheses had no check before them. On 2026-11-25: at 24 hours the class from 100 to 1000
hectares is in the range of one year, and less than 1 of 100 alerts has a wrong sequence. On 2026-11-26: the three
conditions are true for 10 hectares at the two moments, and the class from 10 to 100 hectares is in the range of one
year. Each statement was true for the models of its day, and each is true for the models of now.

The result for the scored years, 2021 to 2025 (tables `risk_percentage` and `risk_recalibrated`, 2026-11-26):

| Model | Large alerts, and expected | Observed to expected, all years | In one year | Smallest Brier skill score | Percentage |
|---|---|---|---|---|---|
| 30 minutes, 10 hectares | 1239 for 1309.3 | 0.9463 | 0.7344 to 1.2991 | 0.0548 | yes |
| 30 minutes, 100 hectares | 445 for 464.3 | 0.9584 | 0.6328 to 1.4383 | 0.0192 | yes |
| 30 minutes, 1000 hectares | 151 for 156.4 | 0.9655 | 0.6651 to 1.3691 | -0.0148 | no: a rank |
| 24 hours, 10 hectares | 1231 for 1334.2 | 0.9227 | 0.7714 to 1.2633 | 0.1749 | yes |
| 24 hours, 100 hectares | 463 for 516.1 | 0.8971 | 0.679 to 1.4355 | 0.1354 | yes |
| 24 hours, 1000 hectares | 154 for 158.4 | 0.9722 | 0.5807 to 1.4929 | 0.0911 | yes |

- Before the recalibration no model has the three conditions: observed to expected is 0.6358 to 0.7481 for the
  five years together, and 0.3765 to 0.5379 in the year with the smallest value.
- The factor of 2023 has a median of 0.4527 to 0.6084. In 2024 it is 0.5619 to 0.6566: the small season of 2023 is
  in the known outcomes of 2024. Thus the values of 2024 are too low (1.2633 to 1.4929), and in the range.
- The tenth of the alerts with the largest values, for the five years together: 198 of 1323 alerts became large for
  100 hectares at 30 minutes (15.0 percent), 314 of 1319 at 24 hours (23.8 percent), and 109 of 1319 for 1000
  hectares at 24 hours (8.3 percent). The values expected 217.3, 354.0 and 118.0.
- The classes between two limits are in the range of one year at each moment: 0.6187 to 1.4899.
  19 of 13 259 alerts have a wrong sequence at 30 minutes, and 69 of 13 207 at 24 hours.
- The alerts with a rank only, at 30 minutes: 644, 372, 2765, 943 and 22.
- The recalibration makes the sequence of a year a little worse (columns `auc_before` and `auc`). The mean AUC of
  the five years, before and after: 0.7918 and 0.789, 0.8384 and 0.8306, and 0.8864 and 0.8694 at 30 minutes for
  10, 100 and 1000 hectares; 0.8497 and 0.8492, 0.9097 and 0.9083, and 0.9423 and 0.9357 at 24 hours.
  The largest change of one year is -0.0428 (1000 hectares at 30 minutes, 2021). Thus the value before the
  recalibration is the better value for a sequence, and the value after it is the percentage.

### 11.25 The test of the growth risk on 2026

`chispa risk --test-run` makes the tables of the test year, in `results/2026`. With no `--test-run`, the command reads
no outcome of 2026. `evaluation/risk_test.py` makes the fires and the rows of the test year.
We wrote the rules on 2026-11-26, before the first run on 2026.

The rules:

1. The models are the six models of section 11.24. They get their weights from each year with an annual map: 2019
   to 2025. No rule and no input changes for the test.
2. The fires of 2026 come from the Monitor map (`docs/sources.md` section 8.18): `chispa fetch monitor --year` saves
   the first month with a burn of each pixel. The rule for a fire is that of the annual map (section 11.3), with the
   burn days of the months that the burn day product has.
3. The match rule has the year (section 11.4).
4. Only an alert with a known outcome is in the test: its moment is 60 days or more before the end of the last month
   of the map. The map had the months to October 2026. Thus the test has the alerts with a moment before
   2026-09-02 00:00 UTC: 1 January to 1 September, and not the months with the most fires.
5. The groups of the alerts, the alerts with a rank only and the recalibration are those of sections 11.21 and
   11.24. The known outcomes of 2025 are those of the annual map, and those of 2026 are those of the Monitor map.

The answer of a model (table `risk_test`). A model holds its percentage in the test if it has 30 large alerts or more,
a Brier skill score of more than 0, and an observed to expected from 0.5 to 2. With less than 30 large alerts it has
no answer. The table `risk` of the test year has the baselines, for hypotheses 1 to 3 of section 11.21.
Hypothesis 4 has no table for the test year: not built.

The runs. The owner decided on 2026-11-26 to run the test on that day, for a part of the year.

- A rehearsal came first, with no outcome of 2026: the same code with 2025 as the test year and its fires from the
  Monitor map. 2025 has the two maps. The percentage held for 10 and 100 hectares. A check outside the repository.
- The first run scored the models before the ground that burned. Its tables are in the commit `5ccd4f9`.
  The percentage held for 10 and 100 hectares at the two moments. Hypothesis 2 was false for 100 hectares at
  24 hours: an AUC of 0.9116, against 0.9144 for the number of detections.
- The inputs then changed by the rule of section 11.22, which uses 2019 to 2025 only. The second run scored the
  models of now one time, on the same alerts. Thus these alerts have two looks, and the numbers below are the second.
  The second run is a second analysis, not a test of the models of now. Hypothesis 2 was false in the first run:
  a result on alerts that we saw cannot change that. The alerts from 2 September are the test.

The result of the second run (tables `risk_test`, `risk_recalibrated`, `risk_classes` and `risk` of 2026, 2026-11-26).
The test has satellite sources only. It has 763 alerts at 30 minutes and 746 at 24 hours, without the alerts on a
known fire and without the 7 and the 2 alerts with a rank only.

| Model | Large alerts, and expected | Observed to expected | Brier skill score | AUC | Answer |
|---|---|---|---|---|---|
| 30 minutes, 10 hectares | 108 for 79.3 | 1.362 | 0.1969 | 0.8449 | the percentage holds |
| 30 minutes, 100 hectares | 43 for 29.2 | 1.4709 | 0.1287 | 0.8723 | the percentage holds |
| 30 minutes, 1000 hectares | 14 for 9.3 | 1.5121 | 0.0672 | 0.9231 | no answer: too few |
| 24 hours, 10 hectares | 96 for 78.1 | 1.2295 | 0.368 | 0.9014 | the percentage holds |
| 24 hours, 100 hectares | 38 for 31.0 | 1.2244 | 0.4244 | 0.9326 | the percentage holds |
| 24 hours, 1000 hectares | 13 for 10.0 | 1.3026 | 0.4022 | 0.9702 | no answer: too few |

- In each model more alerts became large than the values expected: the values are too low, and in the range.
- The recalibration made the level worse in this test. Before it, observed to expected of the four models with an
  answer was 1.1921, 1.2333, 1.1111 and 1.1048, and the Brier skill score 0.213, 0.1475, 0.3804 and 0.4404.
  The median factor was 0.7826 to 0.8372. The values with no recalibration also hold in this test.
- The classes between two limits: 1.2984 and 1.4519 at 30 minutes, and 1.2329 and 1.1875 at 24 hours.
- The hypotheses, for 100 hectares. The first run is their test (the tables of the commit `5ccd4f9`). The numbers
  of the second run are a second analysis of the same alerts: an exploratory result.
- Hypothesis 1 is true in the test. At 30 minutes the AUC of the growth risk was 0.8519, that of the confidence
  0.8326 and that of the number of detections 0.714. In the second run it is 0.8807, and the top tenth has 23 of
  the 45 large alerts, against 18 and 15.
- Hypothesis 2 is false in the test. At 24 hours the AUC of the growth risk was 0.9116, against 0.9144 for the
  number of detections. In the second run it is 0.9338, against 0.9095, 0.9144 and 0.61 for the confidence, the
  number of detections and the persistence rule. The alerts from 2 September decide.
- Hypothesis 3 is true at 30 minutes and false at 24 hours, in the two runs. In the test: 0.6212 against 0.564 and
  0.6133, and 0.7777 against 0.8085 for the number of detections. In the second run: 0.6633 and 0.7917.
  At 24 hours the growth risk does not put the sizes in a better sequence.
- For 1000 hectares the test has 15 and 13 large alerts: no answer. The growth risk has the largest AUC at
  30 minutes (0.9317), and the number of detections at 24 hours (0.9754 against 0.9718).

The decisions of the owner after the first run (2026-11-26). An alert gives the percentage for 100 hectares at
24 hours, as for the other models with an answer: the rule of section 11.21 gave no growth risk as a sequence there,
and this is a change after a result. For 1000 hectares an alert gives a rank at 30 minutes, and at 24 hours the
percentage with the mark "not tested". The field of the event record is parked.

The replay with the maps of the time (table `risk_replay`, asked by the owner on 2026-11-26 after a review).
In the runs above, the factor of a test alert reads the outcomes of the older alerts from the map to October 2026.
For the alerts of 2025 it reads the annual map. No person had those maps at the time of the alert.
The replay changes only this:

1. `chispa fetch monitor` saves the time of the last change of each month image (`docs/sources.md` section 8.18).
   For a month from October 2025, that time is 9 to 15 days after the end of the month. An image can have an older
   version that was different. The replay has each image as it is now, from the time of its last change.
2. T is the time of a test alert. The outcome and the group of each older alert of 2025 and of 2026 come from
   the Monitor map as it was at T: only the months that it had. Its burn days are those of the months before the
   last month.
3. The models, the values, the 60 days, the 365 days and the scored alerts with their outcomes do not change.

The hypothesis, written on 2026-11-26 before the run: a fire is not complete in the map of the time T. Thus fewer
older alerts are large, and the factor is smaller. Observed to expected is larger than in the second run for each
of the four models with an answer. The percentage holds for those four models.

The result of the replay (table `risk_replay` of 2026, 2026-11-26). The hypothesis is true.

| Model | Large alerts, and expected | Observed to expected | In the second run | Brier skill score | Answer |
|---|---|---|---|---|---|
| 30 minutes, 10 hectares | 108 for 74.4 | 1.4517 | 1.362 | 0.1868 | the percentage holds |
| 30 minutes, 100 hectares | 43 for 28.0 | 1.5378 | 1.4709 | 0.1238 | the percentage holds |
| 30 minutes, 1000 hectares | 14 for 10.2 | 1.3736 | 1.5121 | 0.0704 | no answer: too few |
| 24 hours, 10 hectares | 96 for 74.5 | 1.2888 | 1.2295 | 0.3606 | the percentage holds |
| 24 hours, 100 hectares | 38 for 29.9 | 1.2705 | 1.2244 | 0.4178 | the percentage holds |
| 24 hours, 1000 hectares | 13 for 10.8 | 1.2078 | 1.3026 | 0.4102 | no answer: too few |

- With the maps of the time, the four models with an answer expected 3.5 to 6.2 percent fewer large alerts.
  The median factor is 0.7507 to 0.7961 for them, against 0.7826 to 0.8372 in the second run.
- The replay is a third look at the same alerts.

The rule for the next run. The owner decided it on 2026-11-26. That was after the replay, and before a look at an
alert from 2 September 2026. In the run on those alerts, the answer of a model is that of the replay (table
`risk_replay`). The conditions of the answer do not change. The table `risk_test` stays as a second number.

- Limits: the fires of the test come from a different map than the fires that gave the weights. The Monitor map
  of the Pantanal has almost no burned pixel far from a detection: more than 5.5 km from each detection of its
  month and of the month before. In the annual map, approximately 1 of 9 burned pixels is that far
  (`docs/sources.md` section 8.18 has the counts). The method document of the map says that the Pantanal has
  no hotspot rule. `UNVERIFIED`: the rule that made the asset.
  We use the map as a reference that is not independent of our sources. The ground of each alert is near a
  hotspot, and this test scores alerts only. We do not use the map to score the fires with no detection.
  `PLAN.md` has a comparison of the two maps on the alerts of 2025. In the replay, the weights and the ground that
  burned read the annual map with 2025, which came in April 2026. A check outside the repository changed the two
  for the alerts before 1 July: the four answers stayed (`PLAN.md`). The burn days of the replay are those that the
  product has now, and the product changes its older months. A fire that burned after October 2026 has the size
  that it had in October. The test is a part of one year, with 38 to 108 large alerts for a model with an answer:
  we did not measure how much its numbers change by chance. The detections of 2026 before 2026-11-20 have an
  estimate of `available_at`. The alerts from 2 September 2026 are not read: they give a clean test when the
  Monitor map has them. The annual map of 2026 then gives a test of the full year.

### 11.26 Fronts and their answers

The step of section 11.13 is one direction for one event. An event can hold many fires, and the step reads only the
first satellite of a group of passes. A forecast needs a smaller unit, and an answer for it. `fronts.py` makes the
fronts, and `evaluation/fronts.py` gives each front its answers. The command `chispa fronts --year` makes the table
`front_steps`. The owner agreed to this part on 2026-11-26.

1. Only the VIIRS detections of FIRMS count. INPE gives the same passes from a second processor.
2. A look is the detections of the box with no gap in time longer than the look gap (`config.py`): the passes of
   all VIIRS satellites of one afternoon or of one night.
3. A front is the pixels of one look that a chain of pixels links, with no step longer than the link distance.
   A front has the minimum number of pixels or more, and its centre is in the biome border. It has no event.
4. The known pixels of a look are its pixels and the pixels of each look before it in the year.
5. A later pixel is a new pixel if it is farther than the floor of section 11.13 from each known pixel, and not
   farther than the reach from a pixel of the look. It belongs to the front of the nearest pixel of the look.
6. A front has one answer for each window: 12 and 24 hours. The window of 12 hours holds the next look, and the
   window of 24 hours holds two looks.
   - New ground: the front has a new pixel in the window.
   - The front again: no new pixel, and a later pixel that is not farther than the floor from the front.
   - Clear, no fire: no later pixel at the front, and GOES examined its place.
   - Not visible: no later pixel at the front, and GOES did not examine its place.
7. GOES examined a pixel if its mask has a fire class or "no fire" (section 11.11). The scan of a pixel is the
   nearest to 12 or to 24 hours after the middle of the look. It is not farther than the limit, and it is not in
   the block-out zone of the sun. A front was not visible at a time if half or more of its pixels have no such scan,
   or cloud in it. For 24 hours, a front must be visible at the two times, or have new ground.
8. A new pixel has a sector: the direction of its line from the nearest pixel of the front, in 8 equal sectors.
   The distance of a front is a high percentile of the lengths of those lines (section 11.13, rule 4).
9. A front counts only if its longest window ends in the year of its look: the later pixels are those of that
   year. A year in progress has an earlier end (`config.py`). On the day of the test of section 11.28, 2026 had its
   weather to 2026-11-20, and its masks and its later looks to 2026-11-22. Thus that end is 2026-11-21 00:00 UTC.
10. The table `front_alerts` counts the first alerts of a year in the biome that have a front. A first alert is an
    event as we issued it: the moment when its first detection was available, at the mean position of the detections
    of that moment. An event that a later merge absorbed had its own first alert, and it counts.
    At each delay after the alert (`config.py`), the event has a front if the newest look of its VIIRS pixels has a
    group of the minimum size. Only the pixels that the event had at that moment count: the pixels of its issued
    ids of that moment (`issued.py`) that were available. An alert counts only if its longest delay ends in the year.
11. A look is complete when its last pixel was available. A front counts only if its look was complete before its
    first window starts. Thus the answer of a front is not older than a forecast from its complete look.
12. `examined` says if GOES examined the place of a front at each time of a window, with no use of a later pixel.
    The table gives the fronts with new ground, or with the front again, at a place that GOES did not examine.
    Those fronts have an answer only because a later pixel came.

- "Not visible" is not an answer about the fire. A forecast does not learn from such a front, and it gets no score on it.
- A front has no speed. Its distance is the distance of approximately 12 or 24 hours, with the error of section 11.13.
- A day look and a night look are not the same. Each table gives the two apart.
- The mask of GOES has pixels of 2 km or more, and our files have one scan of each hour. Cloud can hide a place
  in the minutes of a VIIRS pass and not in the scan, and the reverse.
- The answers do not read the pass lists. We assume that a VIIRS satellite passes over each place in each look.
- The values in `config.py` are first values. A probe on 2019 to 2023 used them before this section (`PLAN.md`).
  No result set them. 2019 to 2022 have two VIIRS satellites, and the later years have three.
- The answers have satellite sources only.

The result (table `front_steps` of each year, 2026-11-27, with the rules 9, 11 and 12 from the review of pull request 45).
The table has the fronts of 3 pixels or more. `front_steps_small` has the fronts of 1 or 2 pixels (section 11.30, rule 2).

| Year | Hours | Fronts | New ground | The front again | Clear, no fire | Not visible | New ground, not examined | The front again, not examined |
|---|---|---|---|---|---|---|---|---|
| 2019 | 12 | 9674 | 1968 | 2313 | 3603 | 1790 | 190 | 239 |
| 2019 | 24 | 9674 | 3462 | 1954 | 1880 | 2378 | 886 | 187 |
| 2020 | 12 | 21 068 | 4211 | 8851 | 6121 | 1885 | 282 | 631 |
| 2020 | 24 | 21 068 | 7360 | 7934 | 2792 | 2982 | 1250 | 734 |
| 2021 | 12 | 6653 | 1673 | 2031 | 1927 | 1022 | 168 | 207 |
| 2021 | 24 | 6653 | 2613 | 1571 | 862 | 1607 | 656 | 185 |
| 2022 | 12 | 1904 | 250 | 607 | 655 | 392 | 32 | 68 |
| 2022 | 24 | 1904 | 456 | 510 | 344 | 594 | 155 | 61 |
| 2023 | 12 | 5843 | 1366 | 1982 | 1431 | 1064 | 213 | 379 |
| 2023 | 24 | 5843 | 2267 | 1487 | 628 | 1461 | 882 | 358 |
| 2024 | 12 | 11 506 | 2677 | 4805 | 2718 | 1306 | 245 | 492 |
| 2024 | 24 | 11 506 | 4217 | 3936 | 1273 | 2080 | 989 | 521 |
| 2025 | 12 | 890 | 116 | 223 | 335 | 216 | 15 | 29 |
| 2025 | 24 | 890 | 207 | 184 | 185 | 314 | 80 | 18 |
| 2026 | 12 | 755 | 153 | 161 | 299 | 142 | 24 | 29 |
| 2026 | 24 | 755 | 249 | 117 | 167 | 222 | 87 | 26 |

- 2025 and 2026 are the test years of section 11.28. 2026 ends on 2026-11-20 (rule 9).
- The six years of 2019 to 2024 have 56 648 fronts. 49 189 were visible at 12 hours, and 12 145 of those had new ground.
- A day look and a night look are not the same. 5860 of the 30 936 visible fronts of a day look had new ground
  in 12 hours, and 6285 of the 18 253 visible fronts of a night look.
- Of the 23 914 fronts with no later pixel in 12 hours, 7459 were not visible. Thus "no detection" is frequently "no view".
- The group with an answer depends on the answer (rule 12). At 24 hours, 4818 of the 20 375 fronts with new ground
  were at a place that GOES did not examine. In the group that GOES examined, 15 557 of 38 682 fronts had new
  ground. With the other fronts it is 20 375 of 45 546. At 12 hours: 11 015 of 46 043, against 12 145 of 49 189.
- A look was complete a median of 4.7 hours after its start. This uses the delay estimate of 3 hours for a VIIRS
  pixel (`config.py`). The first window starts at 6 hours.
- The years are not the same size: 2020 has 21 068 fronts and 2022 has 1904.

The first alerts with a front of 3 pixels or more (table `front_alerts` of each year, 2026-11-27, rule 10).
The column `with_any_front` of that table counts a front of 1 pixel or more (section 11.30):

| Year | First alerts in the biome | With a front at 0.5 hours | At 6 hours | At 24 hours | Alerts that only GOES started | Of them with a front at 0.5 hours |
|---|---|---|---|---|---|---|
| 2019 | 9665 | 1769 | 3544 | 3787 | 846 | 90 |
| 2020 | 15 141 | 2127 | 4299 | 5076 | 3092 | 191 |
| 2021 | 6050 | 959 | 1891 | 2114 | 1293 | 137 |
| 2022 | 3410 | 240 | 620 | 782 | 1002 | 11 |
| 2023 | 8053 | 585 | 1259 | 1498 | 5824 | 165 |
| 2024 | 7617 | 851 | 1688 | 1966 | 3917 | 91 |
| 2025 | 1747 | 158 | 345 | 399 | 699 | 4 |
| 2026 | 1305 | 84 | 273 | 332 | 512 | 10 |

- In 2023 to 2026, 1678 of 18 722 first alerts had a front 0.5 hours after the alert, and 4195 had one at 24 hours.
  Thus the growth forecast has nothing to say for most first alerts, and for many it never has.
- An alert that only GOES started rarely has a front at 0.5 hours: 270 of 10 952 in 2023 to 2026. It has one when
  a merge puts it into an event with a front in that time. The VIIRS pixels of a pass come some hours after the pass.
- The years before 2023 have fewer GOES detections in the store (`docs/sources.md` section 8.1). Their alerts are
  not those of live operation: more of them start with VIIRS.
- Only the newest look counts. Thus a number at 48 hours can be smaller than at 24 hours.
- The table has satellite sources only.

### 11.27 The fronts against the flames of Sentinel-2

A front needs a check that is not VIIRS. Flames are bright in the short-wave band of Sentinel-2 (B12, pixels of
20 m), and an image of the Pantanal is near 14 UTC (`docs/sources.md` section 8.11). That is approximately 9 hours
after a night look, and 3 hours before the afternoon look of that day. `evaluation/flames.py` compares the answer
of a front with the flames in the image of its window. The command `chispa flames --year` makes the table `front_flames`.

1. The image of a front is the first image in its window of 12 hours that holds the box of the front. With no such
   image, it is the first image in the window of 24 hours. The image is the check of the answer of that window.
   Thus a night look gets a check of 12 hours, and a day look gets a check of 24 hours.
2. The box of a front is the box of its pixels, with the reach of the window around it.
3. A hot pixel has a B12 of the limit or more, and the factor times B8A or more (`config.py`).
   It is a simple rule of this check, not a published rule.
4. The image gets the rule of a new pixel (section 11.26, rule 5), with its hot pixels as the later pixels.
   Flames on new ground: the front has the minimum number of new hot pixels or more.
   No flames on new ground: the front has no new hot pixel, and the box has the minimum clear share.
5. The table compares the two answers, and the two directions for the fronts with new ground in the two.

The hypothesis, written on 2026-11-26 before the first run, for the fronts of 2023:

1. More than half of the fronts with flames on new ground have the answer "new ground".
2. That share is two times or more the share for the fronts with no flames on new ground.
3. For the fronts with new ground in the two, the two directions agree in 45 degrees for more than half.
   Chance is 25 percent.

If statement 1 or 2 is false, the answer of a front does not show what the fire did, and a forecast has no label.

- An image shows the flames of one moment. A fire that moved and then stopped before the image has no flames in it.
- The image is 3 hours before the last look of the window. A fire that starts to move after the image is new ground
  for VIIRS only.
- Thick smoke can have the scene class of cloud. Such a box gets no answer "no flames on new ground".
- The check has a part of the fronts: one day in five, and only a box that one image holds.

The result of the first run (table `front_flames` of 2023, 2026-11-26): the three statements are true.
The numbers are of the run of 2026-11-27, with rule 9 of section 11.26: it took out 8 fronts, none with flames.
1129 of the 5843 fronts had an image. The image was approximately 10 hours after a night look, and 21 hours after a day look.

| Check | Fronts with flames on new ground | Of them "new ground" | Fronts with no flames, clear box | Of those "new ground" | Directions in 45 degrees |
|---|---|---|---|---|---|
| 12 hours, 495 fronts of night looks | 54 | 51 | 166 | 42 | 39 of 51 |
| 24 hours, 634 fronts of day looks | 132 | 127 | 208 | 30 | 111 of 127 |

- Statement 1: 51 of 54 and 127 of 132 fronts with flames on new ground have the answer "new ground". Of the other 8,
  5 were not visible for VIIRS.
- Statement 2: the share is 0.9444 against 0.253 for 12 hours, and 0.9621 against 0.1442 for 24 hours.
- Statement 3: the two directions agree for 39 of 51 and 111 of 127 fronts.
- 42 of 166 and 30 of 208 fronts had "new ground" with no flames on new ground in a clear image. The image does not say
  which is wrong: the fire can move after the image, or stop before it, and a VIIRS pixel can have a wrong position.
  This is a count of two answers that are not the same. It is not a limit of the error of the answer "new ground".
- The median distance was 2339 m for VIIRS and 1362 m for the flames at 12 hours, and 2100 m and 1494 m at 24 hours.
  The image is earlier than the last look, and a VIIRS pixel is wide. This supports the rule that a front has no speed.
- 22 and 36 fronts had 1 to 9 new hot pixels: they are in no group. 253 and 258 had no new hot pixel in a box with cloud.
- This is one year, with the largest fires of November.

The second year is 2024. Its hypothesis is the same three statements for the fronts of 2024, written on 2026-11-26
before its run. No rule and no value changed after the result of 2023.

The result of the second year (table `front_flames` of 2024, 2026-11-26): the three statements are true.
The numbers are of the run of 2026-11-27: rule 9 took out 2 fronts. 2249 of the 11 506 fronts had an image.

| Check | Fronts with flames on new ground | Of them "new ground" | Fronts with no flames, clear box | Of those "new ground" | Directions in 45 degrees |
|---|---|---|---|---|---|
| 12 hours, 937 fronts of night looks | 104 | 84 | 537 | 134 | 75 of 84 |
| 24 hours, 1312 fronts of day looks | 256 | 235 | 585 | 98 | 218 of 235 |

- Statement 2: the share is 0.8077 against 0.2495 for 12 hours, and 0.918 against 0.1675 for 24 hours.
- 20 and 21 fronts with flames on new ground had a different answer. 10 and 7 of them were not visible for VIIRS.
- 6 and 7 of them had the answer "clear, no fire": GOES examined the place, and VIIRS gave no pixel. In 2023 this
  was 0 and 1 fronts. Thus an answer "clear, no fire" can be wrong. `results/2024/front_flames/fronts.csv` has each front.
- The median distance was 2101 m for VIIRS and 1438 m for the flames at 12 hours, and 2124 m and 1789 m at 24 hours.

### 11.28 The growth forecast

A forecast for a front says, at the time of its look, what the next 12 and 24 hours bring: new ground or not,
large growth or not, and in which sectors. `front_inputs.py` makes the inputs, `forecast_model.py` has the trees,
and `evaluation/forecast.py` makes the rows with their answers and the tables. The command `chispa forecast` makes
the tables of 2019 to 2024.
With `--test-run` it also makes those of 2025 and 2026.

The rules:

1. A row is a front with an answer that is not "not visible" (section 11.26). For the sector question, a row is
   one sector of such a front. A front with no weather on disk, or with no pixel with a fire power, is not a row.
2. The questions, each for 12 and for 24 hours: new ground; large growth, which is the minimum number of new pixels
   or more (`config.py`); and a new pixel in the sector.
3. An input uses only what we know at the look. It has no weather after the look: we have no recorded forecast.
   - The front: its number of pixels, its fire power, its extent, its hot side, and day or night.
   - How it came: its pixels on new ground at this look with their direction, and the fire of the look before.
   - The ground that burned this season around the front, for each sector. A fire does not burn the same ground again.
   - The land cover on the front and ahead of it in each sector, and the ground that burned in the three years before.
   - The weather before the look: the dryness of the air, the temperature, the wind and the rain of the days before,
     and the wind of the 12 hours before with its direction.
4. The model is gradient-boosted trees, from scikit-learn. The owner agreed to that dependency on 2026-11-26.
   The trees get their number and their size from one training year that they do not train on: the training year
   with the second-largest number of rows.
5. The baselines. Persistence: the pixels of the front on new ground at this look, and their sectors. The wind:
   how much of the wind before the look goes to a sector. The logistic regression of section 11.15, with the same inputs.
6. The years (section 7.4). A year of 2019 to 2024 gets the models of the five other years. 2025 and 2026 get the
   models of 2019 to 2024, one time. 2026 has the fronts to 2026-11-20 (section 11.26, rule 9, written before the test).
7. The direction of a forecast is the mean of the sector directions, with the probability of each sector as its weight.
   It is compared with the direction of the new pixels of a front (section 11.26, rule 8), for a front with the
   minimum number of new pixels or more.
8. Three tables say in counts what a forecast is worth. They are measures of the same run, not statements of the
   hypothesis. A dry run outside the repository gave their numbers on 2026-11-26, before the tables.
   - `forecast_chances`: for each band of the stated chance (`config.py`), the rows, their mean stated chance, and
     how many had the answer yes.
   - `forecast_sectors`: for the fronts of rule 7, how many of the new pixels are in the 1, 2 and 3 most likely sectors.
   - `forecast_first_look`: the scores for the first look of a fire, and for the other fronts. A front is a first
     look if each of its pixels is farther than the largest reach from each pixel that we knew before.
   - `forecast_examined`: the scores for the fronts at a place that GOES examined, and for the others
     (section 11.26, rule 12). Only the first group does not depend on the answer.

The hypothesis, written on 2026-11-26 before the first run of this code. A probe on 2019 to 2023 came before it, with
a first form of the answers and more inputs (`PLAN.md`). Thus the numbers of those years are not new to us.
2024, 2025 and 2026 were not in the probe.

1. New ground and large growth: the trees have a higher AUC than persistence in each year, at 12 and at 24 hours.
2. The direction of the trees is in 45 degrees of the direction of the new pixels for a larger share of the fronts
   than the direction of persistence and than the direction of the wind, in each year. Chance is 25 percent.
3. The probability holds: in each test year, the Brier skill score against the share of the training years is more
   than 0 for the three questions.
4. The trees have a higher mean AUC than the logistic regression for each question.

The forecast gives no distance and no speed. In the probe, no model was better than the median distance of the
training years by 4 percent.

- A front that was not visible is not in a result. The forecast has no score for the fires under cloud.
- The answers come from VIIRS, with the limits of sections 11.26 and 11.27.
- The maps of the year before are inputs. Early in a year, a live forecast does not have the annual map of the
  year before, and the live command stops (section 11.29). The scores have the fronts of those months, with that
  map. A check outside the repository (2026-11-27): 601 of the 2675 rows of 2025 and 2026 at 12 hours are before
  1 May, and 8704 of the 81 947 rows of 2019 to 2024. Section 11.31 has the rule for those months, and the
  scores with a calendar rule for the maps.
- A Brier skill score of more than 0 says that the chances are better than one number for all fronts. It does not
  say that the level of the chances is correct. The bands of rule 8 and the counts of section 11.30 measure the level.
- The weather is ERA5-Land, which is 6 days late. A live forecast must read the weather before the look from a second source.
- Many fronts are one fire at different looks. The rows of one year are not independent: thus a model never gets a row of the year that it scores.
- The forecast has satellite sources only.

The numbers of this section are of the run of 2026-11-27, with the rules 9, 11 and 12 of section 11.26 and rule 1
of this section, from the review of pull request 45. The commit `4717599` has the tables of that run: the tables of
now have the rows and the models of section 11.30. The first run was on 2026-11-26, and the commit `adff491` has
its numbers. The corrections took out the fronts of the last 30 hours of a year. No statement changed. The largest
change of an AUC or of a Brier skill score in the 48 rows of the table `forecast` was 0.0072.

The result of the development years (tables `forecast`, `forecast_direction` and `forecast_inputs` of 2019 to 2024).
Each year has the models of the five other years. The statements are true for these years.
Each AUC is the lowest and the highest of the six years.

| Question | Hours | Rows | With the answer yes | AUC of persistence | AUC of the regression | AUC of the trees |
|---|---|---|---|---|---|---|
| New ground | 12 | 49 189 | 12 145 | 0.6614 to 0.7375 | 0.7933 to 0.8263 | 0.8114 to 0.8434 |
| Large growth | 12 | 49 189 | 4659 | 0.7069 to 0.7862 | 0.8231 to 0.8634 | 0.8360 to 0.8756 |
| Sector | 12 | 393 512 | 27 960 | 0.6052 to 0.6446 | 0.8202 to 0.8566 | 0.8488 to 0.8769 |
| New ground | 24 | 45 546 | 20 375 | 0.6471 to 0.7199 | 0.7661 to 0.8217 | 0.7811 to 0.8358 |
| Large growth | 24 | 45 546 | 9900 | 0.7007 to 0.7580 | 0.7901 to 0.8366 | 0.7981 to 0.8485 |
| Sector | 24 | 364 368 | 54 212 | 0.5967 to 0.6341 | 0.7832 to 0.8452 | 0.7987 to 0.8556 |

The direction, as the sum of the six years. "In 45 degrees" is of the fronts with the minimum number of new pixels.
Persistence has a direction for a part of them.

| Hours | Fronts | Trees in 45 degrees | Regression | Wind | Fronts with persistence | Persistence in 45 degrees | Trees for those fronts |
|---|---|---|---|---|---|---|---|
| 12 | 8404 | 4987 | 4502 | 2815 | 5807 | 2547 | 3373 |
| 24 | 15 584 | 8793 | 8539 | 4557 | 9838 | 4761 | 5521 |

- Statement 1: the trees have the higher AUC in 24 of 24 cells of year, question and hours.
- Statement 2: the trees have the larger share in 12 of 12 cells against the wind, and in 12 of 12 against persistence.
- Statement 3, for these years only: the Brier skill score is 0.1523 to 0.3357 in the 36 cells.
- Statement 4: the mean AUC of the trees is higher for each question, by 0.007 to 0.024. The trees are higher in
  35 of 36 cells. The other cell is large growth at 24 hours in 2022: 0.8194 against 0.8202.
- The gain of the trees on the regression is small. For the direction at 24 hours it is 8793 against 8539 of 15 584.
- The AUC of the sector question also counts the fronts with no new ground. The direction table is the measure of direction.
- The wind before the look is in 45 degrees for 2815 of 8404 fronts at 12 hours. Chance is 25 percent.
- The extent of the front and day or night are in the first three inputs for 35 of the 36 lists of year, question
  and hours. The ground that burned this season at the front is in 32. No wind input is in a list.
- 2022 is small: 150 fronts have a direction at 12 hours, and the trees are in 45 degrees for 78 of them.
- The probe saw 2019 to 2023. 2024 was not in it. Its AUC for new ground at 12 hours is 0.8434.
  The direction of the trees is in 45 degrees for 1176 of its 1996 fronts.

The result of the test (the same tables of 2025 and 2026): the four statements are true.
The models are those of 2019 to 2024. Each cell has the value of 2025, then the value of 2026.

| Question | Hours | Rows | With the answer yes | AUC of persistence | AUC of the regression | AUC of the trees |
|---|---|---|---|---|---|---|
| New ground | 12 | 674, 613 | 116, 153 | 0.7155, 0.6630 | 0.8679, 0.7861 | 0.8778, 0.8072 |
| Large growth | 12 | 674, 613 | 48, 55 | 0.7435, 0.6839 | 0.8561, 0.8098 | 0.8665, 0.8165 |
| Sector | 12 | 5392, 4904 | 258, 332 | 0.5710, 0.5935 | 0.8596, 0.8131 | 0.8755, 0.8413 |
| New ground | 24 | 576, 533 | 207, 249 | 0.7175, 0.6523 | 0.8252, 0.7551 | 0.8508, 0.7674 |
| Large growth | 24 | 576, 533 | 97, 113 | 0.7440, 0.6777 | 0.8359, 0.8007 | 0.8490, 0.7983 |
| Sector | 24 | 4608, 4264 | 525, 618 | 0.5901, 0.5728 | 0.8098, 0.7760 | 0.8228, 0.7935 |

| Year | Hours | Fronts | Trees in 45 degrees | Regression | Wind | Fronts with persistence | Persistence in 45 degrees | Trees for those fronts |
|---|---|---|---|---|---|---|---|---|
| 2025 | 12 | 80 | 40 | 34 | 36 | 53 | 21 | 27 |
| 2025 | 24 | 162 | 78 | 76 | 57 | 105 | 39 | 49 |
| 2026 | 12 | 102 | 54 | 53 | 36 | 78 | 26 | 40 |
| 2026 | 24 | 187 | 89 | 96 | 40 | 124 | 48 | 60 |

- Statement 1: the trees have the higher AUC in 8 of 8 cells of year, question and hours.
- Statement 2: the trees have the larger share in 4 of 4 cells against the wind, and in 4 of 4 against persistence.
  In 2025 at 12 hours, the difference to the wind is 4 fronts of 80.
- Statement 3: the Brier skill score is 0.1009 to 0.3574 in the 12 cells.
- Statement 4: the mean AUC of the trees for the two years is higher for each question and hours.
  The regression is higher in 1 of 12 cells: large growth at 24 hours in 2026.
- The direction is weaker than in the development years. The trees are in 45 degrees for 94 of 182 fronts at
  12 hours, and for 167 of 349 at 24 hours. In the development years: 4987 of 8404, and 8793 of 15 584.
- For the direction, the trees are not better than the regression in these years: 94 against 87 of 182 fronts,
  and 167 against 172 of 349.
- The test years are small: 890 and 755 fronts. A development year has 1904 to 21 068. 2022, the smallest of
  those, also has a weak direction: 78 of 150 fronts at 12 hours.
- For new ground, 2026 has the lowest AUC of the eight years, and 2025 has the highest.
- 2026 is not a complete year (section 11.26, rule 9). Its detections from September are the live product of FIRMS
  (`docs/sources.md` section 8.1). S-NPP stops on 2026-11-02 (section 8.10): the later looks have two satellites.
- A second model on these years is a second look at them. The owner agreed to one on 2026-11-27, for the weather
  after the look as an input. It gets its hypothesis before its run (`PLAN.md`).

What the forecast says, in counts (tables `forecast_chances`, `forecast_sectors`, `forecast_first_look` and
`forecast_examined` of each year, rule 8). A cell has how many had the answer yes, of the rows of the band, at 12 hours.

| Stated chance | New ground, 2019 to 2024 | New ground, 2025 and 2026 | A sector, 2019 to 2024 | A sector, 2025 and 2026 |
|---|---|---|---|---|
| Less than 0.05 | 171 of 6874 | 4 of 252 | 4019 of 263 314 | 67 of 6700 |
| 0.05 to 0.1 | 714 of 10 594 | 10 of 264 | 3781 of 50 797 | 96 of 1430 |
| 0.1 to 0.2 | 1359 of 10 050 | 30 of 219 | 5664 of 38 920 | 155 of 1230 |
| 0.2 to 0.35 | 2164 of 7933 | 48 of 206 | 6175 of 23 157 | 142 of 606 |
| 0.35 to 0.5 | 2334 of 5549 | 54 of 141 | 4268 of 10 542 | 82 of 224 |
| 0.5 to 0.7 | 3107 of 5370 | 86 of 152 | 3164 of 5623 | 47 of 99 |
| 0.7 or more | 2296 of 2819 | 37 of 53 | 889 of 1159 | 1 of 7 |

- For all rows together, the stated chances of new ground at 12 hours expect 12 323 fronts, and 12 145 had it.
  In the test years they expect 305, and 269 had it. At 24 hours: 20 510 and 20 375, then 508 and 456.
- A stated chance at 24 hours is too high for the group that does not depend on the answer (section 11.26,
  rule 12). For the fronts that GOES examined, the chances expect 16 764 fronts with new ground at 24 hours, and
  15 557 had it. In the test years: 379 and 289. At 12 hours: 11 333 and 11 015, then 270 and 230.
  The other group has the reverse: 3746 expected and 4818 at 24 hours. The trees learned from the two groups together.
- In the test years, a high chance for a sector was too high: 48 of the 106 sectors with 0.5 or more got a new pixel.
- Most sectors have a small chance: 263 314 of the 393 512 sector rows of 2019 to 2024 are below 0.05.
- For the fronts of rule 7, the three most likely sectors had 162 443 of 222 514 new pixels, and 2658 of 3890 in the
  test years. The most likely sector got a new pixel for 5637 of 8404 fronts, and for 108 of 182.
  A sector at random got one for 23 679 of 67 232, and for 486 of 1456: a front that grows has new pixels in 3 sectors.
- The first look of a fire is 543 of the 49 189 rows, and 94 of 1287 in the test years. 83 and 19 of them got new
  ground. Their AUC is 0.74 to 0.91 in a year of 2019 to 2024, and 0.79 and 0.82 in the test years.
- The direction of a first look at 24 hours is weak: in 45 degrees for 49 of 111 fronts, and for 10 of 26 in the test
  years. For the other fronts it is 8744 of 15 473.

### 11.29 The live growth forecast

`forecast_live.py` makes the forecast of section 11.28 for the fronts that burn now. The command
`chispa forecast --live` gives it, and `chispa update` makes it for each new look. The event record has it
(section 7.3): the owner agreed to that field on 2026-11-27.
The modules of this path (`fronts.py`, `front_inputs.py`, `forecast_model.py`, `forecast_live.py` and
`forecast_files.py`) import no module of the evaluation: a test does a check of that. They load the saved
trees, as the event record loads the model of the confidence.

1. The fronts are those of the looks that started in the last hours (`config.py`), with the minimum size and their
   centre in the biome (section 11.26, rules 1 to 3). A year in progress has no end here. Only the pixels
   that were available at the time of the run count.
2. The trees are those of section 11.31, from the rows of all development years. The command
   `chispa forecast --trees` fits them and saves them in a file (`evaluation/forecast_trees.py`): some minutes.
   A live forecast loads the file, and it fits no trees. It uses the trees only if they are for the inputs of
   now: the first part of `config.py`, the code of the fronts, of the inputs and of the model, and the version of
   scikit-learn. If not, it gives no forecast and says which command to run.
   The file also has a mark of its fit, with a hash of the detections of the development years in the store.
   After a change of those detections, or of the code of the answers, a person runs the command again.
3. The inputs are those of section 11.28, rule 3, with the maps of section 11.31. The weather comes from
   ERA5-Land to its last day on disk.
   The later days come from Open-Meteo, with the model IFS, for the weather cell of each front.
4. The answer of the command is JSON: one object for each look, with the time of the look, the time to which it
   has pixels (`pixels_to`), the minimum of a large growth on that day, the mark of the trees that made it
   (`trees`), and each front.
   A front has its centre, its number of pixels, and the ids of the events of its pixels as we
   issued them: an alert is for an event, and this list joins a front to its alerts. An issued id does not change
   when two events merge. For each window, a front has the limits of the window as
   UTC times, and the chance of new ground, of large growth, and of a new pixel in each of the 8 sectors. It has no
   distance and no speed. A window that ended before the run gets no forecast. A front with no weather before
   its look, or with no pixel with a fire power, has its windows with no chance, and the reason: the trees have
   no row and no score for it.
5. Each look gets its object as a file in `data/forecasts` (`forecast_files.py`). A file has `made_at`: the time
   when it was complete, which is later than `pixels_to`. Its name has the time of the look and that time, and a
   file does not change. A look gets a second file when a forecast has more pixels, because a second satellite
   came, or more fronts with a chance, or other trees. The first forecast stays as we gave it.
   `chispa update` makes a new file only for more pixels: after a new fit, `chispa forecast --live` makes it.
6. `chispa update` makes the file of each new look as its last step, in each update. It does not fit the trees:
   if the saved trees are not those of now, it says so, and `chispa forecast --live` fits them.
   If a layer or the weather is absent, it says so, and the next update does the step again.
7. The field `forecast` of the event record is the forecast of the newest look that has a front of the event. It
   comes from the newest file of that look that was complete at or before the as-of time. A front is a front of
   the event if one of its ids is an issued id of the event at that time (`issued.py`). The field has only the
   windows that are open at the as-of time, and the minimum of a large growth that the file has.
   A front of 1 or 2 pixels has no sectors (section 11.30, statement 5).

- A live forecast has no answer at its time. The files of rule 5 are data that no model has read:
  `chispa forecast --score` scores them against what came (section 11.32).
- IFS is not ERA5-Land. On the fronts of September 2024, the two gave almost the same forecast (`docs/sources.md`
  section 8.4). A month with much rain is not checked.
- The store has only the pixels that were available at the time of the run. A forecast from one satellite of a
  look is not the forecast of the complete look.
- An alert with no front gets no forecast. In 2025 and 2026, 1690 of 3052 first alerts had a front of 1 pixel
  or more 0.5 hours after the alert (section 11.30).
- For a front of 1 or 2 pixels, the sectors are not a direction: they were not better than the wind in the test
  (section 11.30). The answer gives the number of pixels of each front.
- In the first months of a year, the annual map of the burned ground of the year before is not on disk: a front
  has no value for its inputs from that map, and it gets its forecast (section 11.31). On 1 January the
  command reads the looks of the two years. December can be a month in progress in the weather.
- A window can start before the run: the 12 hours window starts 6 hours after the look. The answer gives its
  limits. The test scored each forecast as made before its windows (section 11.26, rule 11).
- The trees have rows and scores only for the fronts at a place that GOES examined later (section 11.30, rule 1).
  A live chance comes before that is known. In 2025 and 2026, 1045 of the 3720 fronts were not rows at 12 hours,
  and 1706 at 24 hours (tables `front_steps`, `front_steps_small` and `forecast`).
- The files come from the computer that has the store and runs `chispa update`. The server only records the
  logs. The dashboard does not show the field, and no text goes to a person with it.
- The forecast has satellite sources only.

### 11.30 The second model: the examined fronts, the weather after the look, and the small fronts

Three things asked for a second model. The review of pull request 45 found that the rows of section 11.28 depend
on the answer (section 11.26, rule 12). The owner asked for a forecast of the weather as an input. Most first
alerts have no front of 3 pixels (section 11.26, table `front_alerts`). The owner agreed on 2026-11-27 to the
three changes together, and to one more score of 2025 and 2026. `chispa forecast` makes the tables of `trees`.

The weather after the look gave no gain, and the owner decided on 2026-11-27 to remove its code. The commit
`39b6a49` has that code, and the tables with the columns of `ahead` and `forecast`: the numbers of the two in this
section are from those tables. The tables of now have the same rows, and the same numbers for each other model.

1. A row is a front at a place that GOES examined at each time of the window. It has the weather before its look
   and after it on disk, and a pixel with a fire power. A front at a place that GOES did not examine is not a row,
   with a later pixel or with none. The weather after the look took out no row in the eight years: the code of
   now does not ask for it.
2. A front has 1 pixel or more (`config.py`). A small front has 1 or 2 pixels. The trees learn from all fronts.
   Each table gives the fronts of 3 pixels or more and the small fronts apart.
3. Two sets of trees learn from the same rows. `trees` has the inputs of section 11.28, rule 3. `ahead` has them
   and the weather after the look.
4. The weather after the look is in blocks of 6 hours, from the block after that of the start of the look. For 12
   and for 24 hours: how much of the wind goes to each sector, its mean speed and its largest speed. For the UTC day
   of the first block, and for the day after it: the largest wind, dryness and temperature, and the rain.
5. `ahead` gets the recorded weather (ERA5-Land), which the trees learned from. `forecast` is
   the same trees with a forecast in the place of the recorded weather: the value that the IFS model predicted
   24 hours before each hour, and 48 hours before for the day after, from Open-Meteo (`docs/sources.md` section 8.4,
   `evaluation/forecast_weather.py` of that commit). The lead is from each hour of the weather, not from the look.
   Only the test years have `forecast`. An hour with no value in the forecast stays with no value: the measure of
   its day is absent, and the trees read an absent value. We wrote this on 2026-11-27 before a score: a first run
   stopped on such an hour (`docs/sources.md` section 8.4).
6. The years are those of section 11.28, rule 6. The test years get the trees of 2019 to 2024, one time.
7. The model that stays, written before the run on the test years. If the statements 1 and 2 of the hypothesis are
   true, `ahead` replaces `trees`, and the live forecast gives it a forecast of the weather. If one is false,
   `trees` stays, with the rows and the fronts of the rules 1 and 2. A negative result is a valid result.

The result of the development years (tables `forecast` and `forecast_direction` of 2019 to 2024, 2026-11-27).
Each year has the models of the five other years. Each AUC is the mean of the six years.

| Fronts | Question | Hours | Rows | With the answer yes | Persistence | Regression | `trees` | `ahead` |
|---|---|---|---|---|---|---|---|---|
| 3 or more | New ground | 12 | 46 043 | 11 015 | 0.6905 | 0.8059 | 0.8278 | 0.8304 |
| 3 or more | New ground | 24 | 38 682 | 15 557 | 0.6828 | 0.7864 | 0.8075 | 0.8106 |
| 3 or more | Sector | 12 | 368 344 | 25 664 | 0.6217 | 0.8394 | 0.8654 | 0.8715 |
| 3 or more | Sector | 24 | 309 456 | 42 616 | 0.6191 | 0.8263 | 0.8403 | 0.8455 |
| 1 or 2 | New ground | 12 | 35 904 | 2733 | 0.5274 | 0.8010 | 0.8273 | 0.8291 |
| 1 or 2 | New ground | 24 | 29 627 | 4770 | 0.5317 | 0.7106 | 0.7471 | 0.7526 |

| Fronts | Hours | Fronts with a direction | `trees` in 45 degrees | `ahead` | Wind before the look |
|---|---|---|---|---|---|
| 3 or more | 12 | 7698 | 4581 | 4864 | 2615 |
| 3 or more | 24 | 12 160 | 6929 | 7252 | 3575 |
| 1 or 2 | 12 | 1525 | 725 | 757 | 512 |
| 1 or 2 | 24 | 2877 | 1222 | 1272 | 850 |

- With the recorded weather after the look, the direction is better in 6 of 6 years for the fronts of 3 pixels or
  more, at 12 and at 24 hours. The gain in the AUC of new ground is 0.003.
- The stated chances of `trees` now hold at 24 hours. For the fronts of 3 pixels or more they expect 15 696 fronts
  with new ground, and 15 557 had it. At 12 hours: 11 157 and 11 015. For one year, observed to expected is 0.89 to 1.08.
- A small front has new ground less frequently: 2733 of 35 904 at 12 hours. The AUC of `trees` for it is 0.79 to
  0.85 in a year at 12 hours, and 0.69 to 0.80 at 24 hours. The chances expect 2792 and 4900 fronts with new ground,
  and 2733 and 4770 had it. For one year, observed to expected is 0.76 to 1.21.
- A small front has a direction less frequently, and a weaker one: `trees` is in 45 degrees for 725 of 1525.
- With a front of 1 pixel or more, 5676 of 15 670 first alerts of 2023 and 2024 have a front at 0.5 hours.
  With 3 pixels or more it is 1436. Of the alerts that only GOES started, 411 have one.

The hypothesis, written on 2026-11-27 before the run on 2025 and 2026. The numbers of 2019 to 2024 above were known.
For the fronts of 3 pixels or more, with the two test years together:

1. The direction of `forecast` is in 45 degrees for more fronts than the direction of `trees`, at 12 and at 24 hours.
2. For new ground, the mean AUC of `forecast` of the two years is not lower than that of `trees` by more than 0.01,
   at 12 and at 24 hours.
3. The stated chances of new ground hold: observed to expected is from 0.8 to 1.25 for `trees` and for `forecast`,
   at 12 and at 24 hours.

For the small fronts, which no model has read:

4. For new ground, `trees` has a higher AUC than persistence in each test year, at 12 and at 24 hours. Its Brier
   skill score is more than 0 in each cell.
5. The direction of `trees` is in 45 degrees for more fronts than the wind before the look, at 12 and at 24 hours,
   with the two years together. Chance is 25 percent.

- This is a second score of the fronts of 3 pixels or more of 2025 and 2026. The first test read their answers.
  The three changes came from the review, from the owner and from 2019 to 2024. One number of the test years was
  known before the change of rule 1: 289 fronts with new ground for 379 expected at 24 hours (section 11.28).
- No number of the small fronts of the test years was known.
- The forecast is of the IFS model with cells of 0.25 degrees. A live forecast can use the model of 9 km, which
  has no forecast of the past before 2026. The two are not the same model run.
- The review of 2026-11-27 corrected two claims that this section had before the run. `ahead` is not an upper
  limit: ERA5-Land is a model value for a cell, not the weather at the front. And the weather of `forecast` is not
  always older than a forecast that we can get at a look: the lead is from each hour. For most looks, the last
  1 or 2 hours of the window of 24 hours have a value from a time after the start of the look. For a look that
  starts at 18:00 UTC or later it is more hours: 1 of the 3720 fronts of 2025 and 2026 has such a start (a check
  outside the repository). We did not select the weather by the time when a run was published.
  A later run is nearer the weather that came, as a mean: thus we expect that this error helps `forecast`.
  For one front it can do the reverse. We did not measure it.
- The limits of sections 11.26 to 11.28 apply. The forecast has satellite sources only.

The result of the test (the same tables of 2025 and 2026, 2026-11-27): the statements 2, 3 and 4 are true, and the
statements 1 and 5 are false. By rule 7, `trees` stays: the forecast does not get the weather after the look.
The models are those of 2019 to 2024. Each cell of the first table has the value of 2025, then the value of 2026.

| Fronts | Hours | Rows | With new ground | Persistence | Regression | `trees` | `ahead` | `forecast` |
|---|---|---|---|---|---|---|---|---|
| 3 or more | 12 | 630, 560 | 101, 129 | 0.7069, 0.6528 | 0.8603, 0.7823 | 0.8705, 0.8189 | 0.8642, 0.8228 | 0.8576, 0.8250 |
| 3 or more | 24 | 478, 420 | 127, 162 | 0.7159, 0.6422 | 0.7945, 0.7372 | 0.8166, 0.7665 | 0.8152, 0.7750 | 0.8036, 0.7709 |
| 1 or 2 | 12 | 801, 684 | 44, 46 | 0.5081, 0.4915 | 0.7797, 0.7937 | 0.8106, 0.8112 | 0.8130, 0.8255 | 0.8009, 0.8254 |
| 1 or 2 | 24 | 590, 526 | 55, 72 | 0.4477, 0.4501 | 0.6867, 0.6753 | 0.7478, 0.7435 | 0.7547, 0.7609 | 0.7505, 0.7412 |

The direction, as the sum of the two years:

| Fronts | Hours | Fronts with a direction | `trees` in 45 degrees | `ahead` | `forecast` | Regression | Wind before the look |
|---|---|---|---|---|---|---|---|
| 3 or more | 12 | 157 | 80 | 80 | 78 | 77 | 66 |
| 3 or more | 24 | 226 | 97 | 104 | 102 | 111 | 62 |
| 1 or 2 | 12 | 52 | 25 | 26 | 24 | 18 | 26 |
| 1 or 2 | 24 | 81 | 27 | 29 | 30 | 22 | 32 |

- Statement 1 is false. At 12 hours `forecast` is in 45 degrees for 78 of 157 fronts, and `trees` for 80.
  At 24 hours it is 102 against 97 of 226.
- The recorded weather gave no gain at 12 hours: `ahead` has 80 of 157. In the development years it had 4864
  against 4581 of 7698.
- Statement 2 is true: the mean AUC of `forecast` is lower than that of `trees` by 0.003 at 12 hours, and by 0.004
  at 24 hours.
- Statement 3 is true. `trees` expected 265.5 fronts with new ground at 12 hours, and 230 had it. At 24 hours:
  347.3 and 289. `forecast` expected 262.5 and 348.1. Observed to expected is 0.83 to 0.88.
- The stated chances were too high in 2025. For `trees`, 126.6 fronts were expected at 12 hours and 101 had new
  ground. At 24 hours: 170.2 and 127.
- Statement 4 is true. For a small front, the Brier skill score of `trees` is 0.0970 to 0.1323 in the four cells.
  The chances expected 92.0 fronts with new ground at 12 hours, and 90 had it. At 24 hours: 159.9 and 127, which
  is too high.
- Statement 5 is false. For a small front, `trees` is in 45 degrees for 25 of 52 fronts at 12 hours, and the wind
  for 26. At 24 hours: 27 and 32 of 81. Thus the forecast has no direction for a small front.
- For the fronts of 3 pixels or more at 24 hours, the regression has the best direction: 111 of 226 fronts.
- For the three questions, `trees` has a higher AUC than the regression and than persistence in 24 of 24 cells of
  year, question, hours and size. Its Brier skill score is 0.0563 to 0.3160 in those cells.
- The fronts of 3 pixels or more by stated chance (table `forecast_chances`): at 12 hours, 34 of the 46 fronts with
  0.7 or more had new ground, and 6 of the 306 fronts below 0.05. At 24 hours: 103 of 144, and 3 of 112 below 0.1.
- The three most likely sectors had 2324 of the 3409 new pixels at 12 hours (table `forecast_sectors`).
- With a front of 1 pixel or more, 1690 of the 3052 first alerts of 2025 and 2026 have a front at 0.5 hours.
  With 3 pixels or more it is 242. Of the 1211 alerts that only GOES started, 31 have one.
- The test years are small. The difference between `forecast` and `trees` is 2 fronts of 157, and 5 of 226.
  The result does not show that the weather after the look has no use. It shows no gain that supports a second
  source of weather in the live forecast.
- 17 fronts of 2026 have no dryness of the first day in `forecast` (rule 5, `docs/sources.md` section 8.4).
- The run of that commit needs the 585 answers of Open-Meteo in `data/raw/openmeteo_previous`. The bucket has them.
- The result has satellite sources only.

Why the weather after the look gave no gain. This is a check outside the repository on 2026-11-27, with the fronts
of 3 pixels or more of 2019 to 2024 and the recorded weather:

- The error of the forecast is not the cause. `ahead` has the recorded weather, and it gave no gain at 12 hours.
  The wind of the forecast is in 45 degrees of the recorded wind for 3278 of the 3719 fronts of 2025 and 2026.
- The wind after a look is near the wind before it: in 45 degrees for 6009 of the 7698 fronts with a direction at
  12 hours. `trees` has the wind before the look. Thus the wind after the look is not much new data.
- The recorded wind of the next 12 hours is a weak sign of the direction. It is in 45 degrees of the direction of
  the new pixels for 3132 of 7698 fronts. The wind before the look has 2615, and `trees` has 4581.
- A faster wind is a better sign, and it stays a weak sign: 927 of 2566 fronts in the third with the slowest
  wind, 1122 of 2567 in the middle third, and 1083 of 2565 in the third with the fastest wind.
  The mean wind after a look is 8.9 km/h.
- A front with a direction has new pixels in 2.84 of the 8 sectors as a mean. Its growth is not one line.
- The gain of the development years is 283 of 7698 fronts at 12 hours, and 323 of 12 160 at 24 hours. For the
  fronts of the test years, that is approximately 6 fronts at each time. The test cannot show a gain of that size.
- We do not know the cause of the weak sign. The wind is a model value for a cell of 9 km or more, as the mean
  of 6 hours. A wind with more detail is a different part, with its own hypothesis.

### 11.31 The inputs of the time

The test of section 11.28 gave each front the annual map of the burned ground of the year before, also in the
months when that map did not exist (section 11.28, limits). The live command stopped in those months.
The owner agreed on 2026-11-27 to a forecast for those months, and to new trees that learn from the inputs that a
look can have. `chispa forecast` makes the tables.

1. A look before 1 July (`config.py`) has no value for the two inputs from the annual map of the year before: the
   burned share on the front, and ahead of it in each sector. The map of a year comes in April to July of the next
   year (`docs/sources.md` section 8.5). From 1 July a look has those inputs. For a live forecast the map can
   be absent from the disk: then they have no value. The rows of a test must have the map on disk.
2. A front gets the land cover of two years before, or of the last year that the map has (`config.py`) if that
   is older. We have no checked day for the land cover map of a year. `UNVERIFIED`: we assume that the map of two
   years before exists at each look.
3. The rules 1 and 2 are for each row: the rows that the trees learn from, the rows of a test, and a live
   forecast. The trees read an absent value as absent. The regression gets the mean of the training rows.
4. A live forecast reads the looks of two years when its last hours have 1 January. A look has the known pixels
   of its year only (section 11.26, rule 4).
5. The table `forecast_periods` gives, for the fronts of 3 pixels or more, the fronts before 1 July and the
   other fronts apart, with persistence and the wind for the same fronts. The calendar makes the two groups,
   not the map on disk.

Two probes outside the repository came first (2026-11-27), on 2019 to 2024 with the trees of section 11.30.
They gave the two rules: no value before 1 July had no cost that we could measure, and the land cover of two
years before had a small cost. Their numbers are not in this document: no command of the repository makes them.
The tables below have the cost of the two rules together, as "Trees" against "Trees before".

The result of the development years (tables `forecast`, `forecast_direction` and `forecast_periods` of 2019 to
2024, 2026-11-27). Each year has the trees of the five other years. Each AUC is the mean of the six years.
"Trees before" has the value of section 11.30, with the complete maps.

| Fronts | Question | Hours | Rows | With the answer yes | Persistence | Regression | Trees | Trees before |
|---|---|---|---|---|---|---|---|---|
| 3 or more | New ground | 12 | 46 043 | 11 015 | 0.6905 | 0.8044 | 0.8264 | 0.8278 |
| 3 or more | New ground | 24 | 38 682 | 15 557 | 0.6828 | 0.7831 | 0.8062 | 0.8075 |
| 3 or more | Sector | 12 | 368 344 | 25 664 | 0.6217 | 0.8390 | 0.8646 | 0.8654 |
| 3 or more | Sector | 24 | 309 456 | 42 616 | 0.6191 | 0.8256 | 0.8401 | 0.8403 |
| 1 or 2 | New ground | 12 | 35 904 | 2733 | 0.5274 | 0.7996 | 0.8260 | 0.8273 |
| 1 or 2 | New ground | 24 | 29 627 | 4770 | 0.5317 | 0.7059 | 0.7445 | 0.7471 |

| Fronts | Hours | Fronts with a direction | Trees in 45 degrees | Trees before | Regression | Wind before the look |
|---|---|---|---|---|---|---|
| 3 or more | 12 | 7698 | 4577 | 4581 | 4113 | 2615 |
| 3 or more | 24 | 12 160 | 6947 | 6929 | 6729 | 3575 |
| 1 or 2 | 12 | 1525 | 715 | 725 | 667 | 512 |
| 1 or 2 | 24 | 2877 | 1210 | 1222 | 1180 | 850 |

The fronts of 3 pixels or more before 1 July, and the other fronts (table `forecast_periods`):

| Hours | Fronts | Rows | With new ground | Expected | AUC of the trees | AUC of persistence | Trees in 45 degrees | Wind |
|---|---|---|---|---|---|---|---|---|
| 12 | Before 1 July | 7818 | 1347 | 1282.2 | 0.7784 | 0.6330 | 490 of 857 | 299 |
| 12 | From 1 July | 38 225 | 9668 | 9816.1 | 0.8245 | 0.6918 | 4087 of 6841 | 2316 |
| 24 | Before 1 July | 6382 | 1996 | 1917.8 | 0.7487 | 0.6166 | 744 of 1451 | 414 |
| 24 | From 1 July | 32 300 | 13 561 | 13 611.2 | 0.8057 | 0.6895 | 6203 of 10 709 | 3161 |

- The new trees are near the trees of section 11.30. The mean AUC of new ground is lower by 0.0014 at 12 hours
  and by 0.0013 at 24 hours. The counts of the direction are near: 4577 against 4581, and 6947 against 6929.
- The trees have a higher AUC than persistence and than the regression in each year, for each row of the first
  table. Their Brier skill score is more than 0 in each cell of year, question, hours and size.
- The sum of the stated chances is near the count, for the six years together. For the fronts of 3 pixels or
  more the chances expect 11 098.4 fronts with new ground at 12 hours, and 11 015 had it. At 24 hours: 15 528.9
  and 15 557. A sum does not show each band of the chance: the table `forecast_chances` has the bands.
  For one year, observed to expected is 0.88 to 1.12 at 12 hours, and 0.86 to 1.10 at 24 hours. For the small
  fronts it is 0.74 to 1.20, and 0.73 to 1.19.
- Before 1 July the mean AUC is lower than in the other months: 0.7784 against 0.8245 at 12 hours. It is not
  lower in each year: in 2019 it is 0.8368 against 0.8160. The two groups have different fires and different
  inputs, thus the table does not say why. The trees are above persistence in 6 of 6 years. The lowest year
  is 2021: 0.6688 at 12 hours, with 34 fronts with new ground of 517.

The hypothesis, written on 2026-11-27 before the run on 2025 and 2026. The numbers above were known.
The test years get the trees of 2019 to 2024, one time.

1. For the fronts of 3 pixels or more before 1 July, the mean AUC of the trees for new ground of the two years is
   higher than that of persistence, at 12 and at 24 hours.
2. For all fronts of 3 pixels or more, the mean AUC of the trees for new ground of the two years is not lower than
   that of section 11.30 by more than 0.01. Those means are 0.8447 at 12 hours and 0.79155 at 24 hours.
3. For the fronts of 3 pixels or more, with the two years together, the direction of the trees is in 45 degrees for
   more fronts than the wind before the look, at 12 and at 24 hours.
4. For the fronts of 3 pixels or more, with the two years together, observed to expected for new ground is from 0.8
   to 1.25, at 12 and at 24 hours. In section 11.30 it was 0.87 and 0.83.
5. For the small fronts, the trees have a higher AUC for new ground than persistence in each test year, at 12 and
   at 24 hours.

The rules 1 to 4 stay with each result: they are what a live forecast has. The result says how good the forecast
is with them. A negative result is a valid result.

- This is a third score of the fronts of 3 pixels or more of 2025 and 2026, and a second score of their small
  fronts. The trees are new, and the answers were read before. Thus statement 2 compares two analyses of the
  same fronts: it is not an independent test of the limit of 0.01.
- 1 July is one day for each year. The map of 2025 was in Earth Engine on 2026-04-09, and that of 2024 on
  2025-05-21 or before (`docs/sources.md` section 8.5).
- We have no checked day for the land cover map. `UNVERIFIED`: a year comes in the second half of the next year.
- Each map is that of the collection that we read in 2026. A look of the past had an older collection of the
  same year, which can have other values. We did not measure that difference.
- The fronts of 2019 need the land cover of 2017: `chispa fetch landcover --year 2017`. It is not in the bucket.
- The limits of sections 11.26 to 11.30 apply. The forecast has satellite sources only.

The result of the test (the same tables of 2025 and 2026, 2026-11-27): the statements 2, 3, 4 and 5 are true.
Statement 1 is true at 12 hours and false at 24 hours. Each cell has the value of 2025, then the value of 2026.

| Fronts | Hours | Rows | With new ground | Persistence | Regression | Trees | Trees of section 11.30 |
|---|---|---|---|---|---|---|---|
| 3 or more | 12 | 630, 560 | 101, 129 | 0.7069, 0.6528 | 0.8599, 0.7827 | 0.8706, 0.8179 | 0.8705, 0.8189 |
| 3 or more | 24 | 478, 420 | 127, 162 | 0.7159, 0.6422 | 0.7890, 0.7357 | 0.8111, 0.7675 | 0.8166, 0.7665 |
| 1 or 2 | 12 | 801, 684 | 44, 46 | 0.5081, 0.4915 | 0.7830, 0.7995 | 0.8060, 0.8034 | 0.8106, 0.8112 |
| 1 or 2 | 24 | 590, 526 | 55, 72 | 0.4477, 0.4501 | 0.6815, 0.6784 | 0.7328, 0.7462 | 0.7478, 0.7435 |

The fronts of 3 pixels or more before 1 July (table `forecast_periods`):

| Hours | Year | Rows | With new ground | Expected | AUC of the trees | AUC of persistence | Trees in 45 degrees | Wind |
|---|---|---|---|---|---|---|---|---|
| 12 | 2025 | 100 | 4 | 8.7 | 0.8672 | 0.8893 | 1 of 1 | 1 |
| 12 | 2026 | 211 | 58 | 48.7 | 0.8639 | 0.7180 | 21 of 38 | 16 |
| 24 | 2025 | 64 | 6 | 11.4 | 0.7098 | 0.8448 | 1 of 4 | 0 |
| 24 | 2026 | 161 | 61 | 58.5 | 0.8361 | 0.7025 | 24 of 49 | 13 |

- Statement 1: at 12 hours the mean AUC of the trees before 1 July is 0.8656, and that of persistence is 0.8036.
  At 24 hours it is 0.77295 against 0.77365: false by 0.0007.
- The two years are not the same. 2025 has 4 and 6 fronts with new ground before 1 July, and persistence is
  higher there. 2026 has 58 and 61, and the trees are higher by 0.1459 and by 0.1336.
  The mean of the two years gives a year with 6 such fronts the weight of a year with 61.
- Statement 2: the mean AUC for all fronts of 3 pixels or more is lower than that of section 11.30 by 0.0005 at
  12 hours, and by 0.0023 at 24 hours. For the small fronts it is lower by 0.0062 at 12 and at 24 hours.
  One cell of year, question, hours and size changed by -0.0085 to +0.0051 for the fronts of 3 pixels or
  more, and by -0.0150 to +0.0233 for the small fronts.
- Statement 3: the trees are in 45 degrees for 79 of 157 fronts at 12 hours, and the wind for 66. At 24 hours: 97
  and 62 of 226. The regression has 77 and 110: at 24 hours it is ahead of the trees, as in section 11.30.
- Statement 4: the trees expected 267.3 fronts with new ground at 12 hours, and 230 had it: 0.86. At 24 hours:
  348.3 and 289, 0.83. The stated chances were too high in 2025: 128.9 and 101, then 172.6 and 127.
- Statement 5: for a small front, the trees are above persistence in each year. The direction of a small front
  is in 45 degrees for 27 of 52 fronts at 12 hours, and the wind for 26. At 24 hours: 24 and 32 of 81.
  Thus the forecast has no direction for a small front, as in section 11.30.
- For the three questions, the trees have a higher AUC than persistence in 24 of 24 cells of year, question, hours
  and size, and than the regression in 23. The other cell is large growth at 12 hours for the small fronts of 2026.
  The Brier skill score of the trees is 0.0258 to 0.3191.
- By stated chance, for the fronts of 3 pixels or more at 12 hours: 35 of the 48 fronts with 0.7 or more had new
  ground, and 6 of the 275 fronts below 0.05. The three most likely sectors had 2281 of the 3409 new pixels.
- The forecast of the months before 1 July has a test on one year with many fronts with new ground, 2026.
  2025 has too few for an answer.
- The rules stay: the calendar does not stop a live forecast now. A front must have its other inputs
  (section 11.29, rule 4). The trees of now are those of this section. The numbers of sections 11.28 and 11.30
  are those of their runs.
- A live forecast from 1 July with no map of the year before on disk has inputs that no test had: each row of a
  test from 1 July has that map.
- The next independent test is the saved files of the live forecast (section 11.32), and the fronts after
  2026-11-20.
- The result has satellite sources only.

### 11.32 The score of the saved live forecasts

A file of section 11.29 is a forecast that we gave before its answer existed. The command
`chispa forecast --score` gives each front of those files its answer, and it scores the stated chances
(`evaluation/forecast_score.py`). No model has read these fronts: each look is after the end of the test of
section 11.31. The owner asked for this command on 2026-11-27.

1. The forecast of a look is its newest file that was complete before the first window starts. A look with only
   later files has no score. The longest window must end in the year of the look (section 11.26, rule 9).
2. The command makes the look again as the file saw it, with the pixels that were available at `pixels_to`.
   The later pixels are those of the store of now, from the start of the first window.
3. A look has a score only if the store of now has the same look: the same pixels, and no more. If a pixel of
   the look came after the file, the look was not complete before its first window (section 11.26, rule 11).
   The table counts the fronts of the looks that are the same (`same_look`).
4. A window has an answer 6 hours after its end: the hours in which a look must be complete (`config.py`).
   The pixels of the last pass of a window come some hours after the pass.
5. The answer of a front comes from the rules 5 to 8 of section 11.26. The masks are those of the live poller:
   each scan that it recorded.
6. A front has a score if it has a chance, and if GOES examined its place at each time of the window
   (section 11.30, rule 1).
7. The table `forecast_live` has one row for each window and each size of front: the looks, the fronts, the
   fronts with a score, those with new ground, the sum of the stated chances, the AUC of the trees and of
   persistence, and the direction of the fronts with 3 new pixels or more. An AUC needs a front with new ground
   and a front with none. The file `results/<year>/forecast_live/fronts.csv` has one row for each front and
   each window, with the mark of its trees.
8. Each run makes the table of a year again from all files of that year. A run with no answer makes no table.

The hypothesis, written on 2026-11-27 before a window of a saved forecast had an answer. The first files are of
the look of 2026-11-27 16:41 UTC. The statements are for the table of a year, at the first run in which 100 or
more fronts of 3 pixels or more have a score at 12 hours. Before that count, the table is a count in progress:
it does not answer the hypothesis.

1. For the fronts of 3 pixels or more, the AUC of the trees for new ground is higher than that of persistence,
   at 12 and at 24 hours.
2. For the fronts of 3 pixels or more, observed to expected for new ground is from 0.8 to 1.25, at 12 and at
   24 hours.

A negative result is a valid result.

- 100 fronts are few. In the test of section 11.31, 230 of the 1190 fronts of 3 pixels or more had new ground
  at 12 hours. At that share, 100 fronts give approximately 19 with new ground: statement 2 can be false by
  chance.
- A look has a file only if the computer with the store ran `chispa update` before the first window. A look
  with no file has no score, and the table does not count it.
- The masks of the poller have each scan, and the test had one scan of each hour (section 11.26). The limit in
  time from a scan to its moment is the same.
- One table can have the files of trees with different marks. The file of the fronts has the mark of each row.
- The table has no wind: the count of the direction has no baseline.
- The wait of rule 4 is not a measured delay. The delay report of the live logs is not made (`PLAN.md`).
- The limits of sections 11.26 to 11.31 apply. The score has satellite sources only.

### 11.33 The fronts in Brazil outside the biome

The store has the detections of the whole box, and an alert can be outside the biome border. Its fronts have no
forecast: the trees learn from the fronts of the biome, and each score is for those fronts (section 11.26,
rule 3). The owner asked on 2026-11-27 for a test of the trees on the fronts in Brazil outside the biome.
`chispa forecast --outside` makes the tables `forecast_outside` and `forecast_direction_outside`
(`evaluation/forecast_outside.py`).

1. A front is in Brazil if its centre is in a cell with a land cover class: the land cover map has Brazil only
   (`docs/sources.md` section 8.14). A front in a different country has no maps: it is not in this test.
2. The fronts of this section are in Brazil, and their centre is not in the biome border. Each other rule of the
   fronts, of their answers and of their inputs is that of sections 11.26 to 11.31.
3. The trees are those of section 11.31: a year gets the trees of the biome fronts of the other development
   years. No tree reads a front outside the biome. The regression and the baselines also come from the biome.

The result of the development years (tables `forecast_outside` and `forecast_direction_outside` of 2019 to 2024,
2026-11-27). Each AUC is the mean of the six years. "Expected" is the sum of the stated chances of the trees.

| Fronts | Question | Hours | Rows | With the answer yes | Expected | Persistence | Regression | Trees | Trees in the biome |
|---|---|---|---|---|---|---|---|---|---|
| 3 or more | New ground | 12 | 18 867 | 3531 | 3670.9 | 0.6399 | 0.7542 | 0.7768 | 0.8264 |
| 3 or more | New ground | 24 | 15 996 | 5382 | 5646.3 | 0.6095 | 0.7304 | 0.7620 | 0.8062 |
| 3 or more | Large growth | 12 | 18 867 | 1065 | 1249.5 | 0.7159 | 0.8302 | 0.8384 | 0.8651 |
| 3 or more | Large growth | 24 | 15 996 | 2252 | 2447.3 | 0.6634 | 0.8171 | 0.8387 | 0.8406 |
| 1 or 2 | New ground | 12 | 26 949 | 1260 | 1729.2 | 0.4691 | 0.7058 | 0.7325 | 0.8260 |
| 1 or 2 | New ground | 24 | 22 034 | 2835 | 3344.5 | 0.4834 | 0.6286 | 0.6783 | 0.7445 |

| Fronts | Hours | Fronts with a direction | Trees in 45 degrees | Regression | Wind before the look |
|---|---|---|---|---|---|
| 3 or more | 12 | 2199 | 1237 | 1169 | 805 |
| 3 or more | 24 | 3862 | 2029 | 2024 | 1209 |
| 1 or 2 | 12 | 549 | 245 | 230 | 189 |
| 1 or 2 | 24 | 1328 | 505 | 517 | 397 |

- For new ground and for the sectors, the trees have a higher AUC than persistence and than the regression in
  6 of 6 years, for each size and each window.
- The AUC is lower than in the biome: by 0.0496 at 12 hours and by 0.0442 at 24 hours, for the fronts of
  3 pixels or more. The lowest year is 2022: 0.7156 and 0.6668.
- The stated chances are near the count for the six years together, and not for each year. For the fronts of
  3 pixels or more, observed to expected for new ground is 0.54 to 1.04 for one year at 12 hours, and 0.55 to
  1.00 at 24 hours. In 2022 the trees expected 146.9 fronts with new ground at 12 hours, and 80 had it. In 2023:
  334.5 and 247. In the biome, one year had 0.88 to 1.12 (section 11.31).
- For the small fronts the stated chances are too high: observed to expected is 0.73 at 12 hours and 0.85 at
  24 hours, and 0.53 to 0.86 for one year at 12 hours.
- The chance of a large growth is too high: for the fronts of 3 pixels or more, observed to expected for one
  year is 0.11 to 1.19 at 12 hours. For the small fronts, 180 had a large growth of 355.1 expected.

The hypothesis, written on 2026-11-27 before the run on 2025 and 2026. The numbers above were known. No command
read an answer of a front outside the biome of those two years. The test years get the trees of 2019 to 2024,
one time.

1. For the fronts of 3 pixels or more, the trees have a higher AUC for new ground than persistence in each test
   year, at 12 and at 24 hours.
2. For the fronts of 3 pixels or more, the mean AUC of the trees for new ground of the two years is not lower
   than that of the biome fronts by more than 0.10. Those means are 0.84425 at 12 hours and 0.7893 at 24 hours
   (section 11.31).
3. For the fronts of 3 pixels or more, with the two years together, observed to expected for new ground is from
   0.8 to 1.25, at 12 and at 24 hours.
4. For the fronts of 3 pixels or more, with the two years together, the direction of the trees is in 45 degrees
   for more fronts than the wind before the look, at 12 and at 24 hours.
5. For the small fronts, the trees have a higher AUC for new ground than persistence in each test year, at 12
   and at 24 hours.

What follows from the result, written before it. If the statements 1 to 4 are true, a live forecast can give a
front of 3 pixels or more outside the biome its chance of new ground and its sectors, with a mark that it is
outside the biome. A small front outside the biome gets a chance only if statement 5 is true and its observed to
expected for new ground is in the range of statement 3: in the development years it was not, at 12 hours.
No statement is for the chance of a large growth: an alert must not give it for a front outside the biome.
A negative result is a valid result.

- The limit of 0.10 in statement 2 comes from the development years: no two of them have a larger mean
  difference. It is a choice.
- The maps end at the border of Brazil. For a front near that border, the ground ahead in a different country has
  no land cover group and no burned ground in the inputs. A front of the biome near the border has the same limit.
- The Brier skill score in the table `forecast_outside` compares the trees with the share of the biome fronts
  of the training years, not with a share of the fronts outside.
- The limits of sections 11.26 to 11.31 apply. The result has satellite sources only.

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
6. Give measured growth as measured growth: do not call it a forecast. Give a growth forecast only from the field
   `forecast` of the event record (section 11.29). Give its chance with the times of its window. Give no direction
   for a front of 1 or 2 pixels. Give no distance and no speed of the growth to come.
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
8. The clock sets one time zone for the page: Pantanal time (the zone in `config.py`) or UTC. Each time on the page is in
   that zone, with its name. The detections of each day stay UTC days. Data, tools and results stay in UTC.
9. A time to CHISPA that includes a stop of the poller (`poller_stop_h`) has a mark with the most that the stop added.
   The last clear look gives the newest look at the place of the last detection and what it saw (section 7.3).
   After the last detection, the timeline has one row for each run of GOES scans with one answer. Folded, it keeps each
   run of fire or possible fire and the newest runs.
   The page does not say that a fire is out.
10. At an as-of time before the first alert of the selected event, CHISPA had no detection of it: the page says "No alert yet".
   It gives the time of the first detection and of the first alert from a record of the event at a later time, and it says
   that CHISPA did not know these times at the as-of time. The event lane of the history band starts at the first detection.

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
