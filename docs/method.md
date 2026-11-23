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
- Live: each pass of the poller saves the number of pixels of each group for each scan, in the log `live/goes_mask/`.
- Polar-orbit sensors: a NASA service gives the time of each pass (section 8.12). We do not read it yet.
  A pass time does not say if cloud hid a place.
- An answer from the visibility must name the sensor and the time. "Examined, no fire" from GOES says nothing about a small fire.

### 7.3 The event record

The event record is the one object that an alert, a tool and a report read.
It holds, for one event at an as-of time, what we know at each stage and how we know it.

| Stage | Field today (`tools.py`) | Field not built |
|---|---|---|
| Ignition | | The limits of the start time |
| Observation | `first_observed_at`, `last_observed_at`, `max_frp_mw`, `detections` | The land cover at the event |
| Publication | `newest_available_at`, `newest_observation_age_h` | |
| Alert | `level`, `sensor_families` | The probability of a match at the first alert |
| Growth | | The area at each pass |
| Confirmation | `alert_changes` | |
| End | | The visibility after the last detection |
| Mapping | The track record of the level (`evaluation_summary`) | |

- A field with no value is `None`. Do not fill it with an estimate.
- Add a field only with its measure: how do we know that the field is correct, and on which data?
- A fire has no "type" in the record. No source gives a label for a controlled burn.

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

`available_at` is important.
A satellite observation is not available at the moment of the observation.
For a recorded detection it is an estimate: `observed_at` plus a fixed delay from `config.py`. Say so in the results.
For a live detection it is a measurement: the time of the pass of the poller that first saw it.

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
- Freeze the configuration. Record its hash. The hash covers the first part of `config.py`: the values that can change a result.
- Run the evaluation of the test period one time for each frozen configuration.
- Record each run in `results/`, with the configuration hash and the date.
- If you change a threshold after a run on the test period, the next result must say so.

The test period of the merge hypothesis was 2024. We ran it on 2026-11-21, thus 2024 is not new data now.
The table `merge_gain` came after that first run. It changed no threshold and no number of the other tables.
Each later part uses 2024 only to tune, and 2025 as its test period (section 7.4).
Each command that makes a result stops for 2024 and for 2025, unless it has the flag `--test-run`.
Do not use the flag for 2025 before the rules of a part are frozen. The store can hold the 2025 data before that time.

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

- `configurations`: fire recall, area recall, unmatched share and delay for each source, sensor family and merged level.
- `fire_sizes`: fire recall for each configuration and fire size class.
- `fire_events`: for each fire size class, into how many events the fusion split a fire, and the completeness.
- `events`: for each final level, the share of events that match a fire, how many counted fires one event holds, and the purity.
- `merge_gain`: for each sensor family and fire size class, the fires that only the merge finds, and the isolated fires that the family finds later than the merge.
- `burn_check`, `burn_rule`, `image_check` and `image_agreement`: the burn check of HIGH events and its check by a person (section 11.10).
- `visibility`: how frequently GOES examined the place of a fire (section 11.11).
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
- More than half of the steps with 6 to 18 hours came after an empty pass: a satellite passed and gave no detection of the event.

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
- The check uses the events as they are at the end of the year. Two events that were separate at the evaluation time and
  merged later are one event in the check. A brigade did not have that grouping at that time. A correct check needs
  a replay that stops at the evaluation time: not built.
- The list of protected land is the list of today (section 8.14). An area that got its status after an event still
  gives points to that event. A new download can give a different list.

The result (tables `severity` and `severity_rank`, 2026-11-22): the hypothesis is true on 2023 and false on 2024.

- Rank correlation with the outcome, for all events: the severity 0.2749 and the number of detections 0.2547 in 2023 (5890 events).
  In 2024 the severity 0.2685 and the number of detections 0.2857 (6260 events). The two are almost equal, and the sequence changes.
- Thus the severity does not say more about the final burned area than a count of detections.
- For the events with a match only, each rank correlation is near zero. Many small events match one very large fire,
  thus the outcome of an event says little about that event. Thus the rank correlation for all events shows mostly
  one thing: an event with many detections matches a fire more frequently. It does not show a ranking of the burned area.
- The severity does separate the events that match a mapped fire. In 2024 the matched share was 1078 of 3285 events with a
  severity below 25, 1347 of 2602 from 25 to 50, 309 of 357 from 50 to 75, and 15 of 16 from 75.
  This was not the hypothesis. It is a property of a confidence, not of a severity (PLAN.md, C4).
- The number of detections separates these events as well as the severity: the match separation in the table
  `severity_rank` is 0.6615 for the severity and 0.6612 for the number of detections in 2024, and 0.692 and 0.688 in 2023.
- The time after the evaluation time. Of the 324 matched events with a severity of 50 or more in 2024, 224 had a detection
  after the evaluation time: 211 of 309 from 50 to 75, for a median of 2.2 more days, and 13 of 15 from 75, for a median of 6.23.
  Below 25, 95 of 1078 matched events had one. In 2023: 117 of 208 from 50, and 38 of 362 below 25.
  Thus more of the events with a high value at 24 hours have a later detection, and fewer of the events with a low value.
  A later detection does not say that the same fire burns, and it gives no time for a brigade to act.
  No later detection does not say that a fire is out: the sensors do not see each fire.
  This is a description of two years, found after the first run. It is not a tested forecast.
- The check was weak in one way: people, land and land cover have no relation to the burned area by design.
  They are the priorities of the owner. Only the fire parts can agree with the outcome.

The rule of the hypothesis says: with a false result, the facts stay with no number.
The owner decides if the number stays as a statement of priorities. It must not be called a forecast of the burned area.

### 11.15 Confidence at two moments

The confidence level of section 10.3 counts passes and sensor families. At the first detection it is almost always LOW.
This part gives a probability that an event will match a mapped fire, at two moments. `confidence.py` makes it.
The command `chispa confidence --year` makes the tables.

- Moment 0: the first alert. It uses the detections that were available not later than one pass gap (section 10.3)
  after the first detection of the event: the same pass from two sources has times that differ by some minutes.
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
- Top tenth: of the tenth of the events with the largest values, how many match. A brigade goes to these first.
  `top_tenth_fires` is the number of different counted fires that those events match. Many events can match one
  large fire, thus a count of events alone can look better than it is.

What 2023 and 2024 show (2026-11-23). This is tuning, not the test. The weights are from 2023:

- The first model had no input for the fire activity near an event. On 2024 its match separation was 0.8131 at moment 0.
- We examined the inputs on 2024, outside the repository. No group of inputs alone gave more than 0.74. Each group that we
  removed decreased the separation by 0.04 or less. The activity of all the region did not help.
- We made one change: the input "activity near the event". Fires come in groups in space and time, and the input
  uses only the days before the first alert. We made no other change, and the penalty stays at its first value.
- With this input, on 2024: the match separation is 0.8579 at moment 0 and 0.8712 at moment 24. That of the level is 0.5625 and 0.6333.
  The Brier skill is 0.3693 and 0.3886. That of the level is 0.0114 and 0.0728 (6260 events, 2749 with a match).
- Top tenth at moment 0: 575 of 626 events match. For the level: 291 of 626.
- The probability is too low on 2024: in the middle fifth of the events the mean probability was 0.1534, and the matched
  share was 0.4305. The matched share of all events was 0.207 in 2023 and 0.439 in 2024. The model has the rate of 2023.
  No data at the time of an alert gives the rate of its year: the map comes the next year. Thus we expect hypothesis 3 to be false.
- The largest weights at moment 0: the fire power and the activity near the event (more is a match), the season,
  and the distance to indigenous land and to protected land (near is a match).
- The model is frozen at this state.

A caution for the input "activity near the event": an event near a large fire can match that fire, because the match
rule has a reach in space and in time. Then the input and the label agree for a reason that is not the event.

The table `confidence_calibration`: we put the events in sequence by their probability and make five equal groups.
`probability_mean` is what the model said for a group. `matched_share` is what came. `observed_to_predicted` is the
second divided by the first: 1 is a correct probability, and more than 1 says that the probability is too low.

The result of the test (tables `confidence` and `confidence_calibration` of 2025). The owner ran it one time on 2026-11-23,
with the frozen model. A second run on the same day added the column `observed_to_predicted`. It changed no other number.
2025 has 1726 events in the biome, and 327 of them match a mapped fire.

- Hypothesis 1 is true. At moment 0 the match separation of the probability is 0.8245. That of the level is 0.6012.
- Hypothesis 2 is true. At moment 24 it is 0.8405 for the probability and 0.6814 for the level.
- Hypothesis 3 is false at moment 0 and true at moment 24. At moment 0 the fourth group had a mean probability of 0.0966
  and a matched share of 0.2232, and the fifth group 0.3995 and 0.513. At moment 24 each group is in 0.1.
  In each group of the two moments the probability is too low: the matched share is 1.2 to 4.3 times the probability.
- The Brier skill of the probability is 0.21 at moment 0 and 0.2748 at moment 24. That of the level is 0.0281 and 0.0869.
- Top tenth at moment 0: 114 of 172 events match. For the level: 31 of 172.
  Those events match 145 different counted fires. For the level: 47. Thus the model does not only put many alerts
  of one large fire at the top. A review of the pull request asked for this number. A third run on 2025 added it,
  and changed no other number.
- Thus the model puts the events in a better sequence than the level, at the first alert and one day later, in a year
  that it did not see. Its number is not a correct probability. By the rule above, we give a rank and not a probability.
- The values of 2025 are lower than those of 2024 and near those of 2023. 2025 is a small year: 327 events with a match.
  We give no range for the values: a different year can give a different result.

- Limits: the events are the events of the end of the year (section 11.14). The GOES detections of 2025 are from GOES-19,
  and those of 2023 and 2024 from GOES-16. The year 2025 can have holes in its GOES record that we did not find.
  2025 had few fires: 589 counted fires, and 4246 in 2024. Thus the test has fewer events with a match.
  The layers have the limits of section 11.14.

## 12. Agent and MCP rules

### 12.1 Tools

- Keep the number of tools small. The target is six or fewer. Three exist: `alerts_near`, `event_detail` and `evaluation_summary`.
- Each tool that reads events has an as-of time. It uses only detections with `available_at` at or before that time.
- Known limit: if two events merged after the as-of time, the tool shows them as one event.
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
