# CHISPA

CHISPA merges fire detections from different sources into one alert for each fire.
It measures how good those alerts are, and it publishes the result: good or bad.
Each part of an alert must say how we know it.

## The problem

A brigade gets fire data from many places.
Polar-orbit satellites see small fires, but only a few times each day.
Geostationary satellites look every 10 minutes, but with large pixels.
The same fire can show as many records, and some records are not fires.
A brigade must also know how much to trust an alert, and what the satellites could not see.

## The stages of a fire

All the work follows eight stages. Each stage gives one part of the alert, and each part has its own measure.
[docs/method.md](docs/method.md) section 7 gives the rules.

| Stage | What occurs | What drives it | Part of the alert | Measure | State |
|---|---|---|---|---|---|
| 1. Ignition | The fire starts. No source records this. | Nothing | The earliest possible start | Not possible directly. Visibility can give a limit. | Not built |
| 2. Observation | A sensor sees heat on the ground. | The VIIRS, MODIS, ABI and AVHRR satellites | Position, time and fire power | Fire recall of each sensor family | Built |
| 3. Publication | A source publishes the detection. | FIRMS, NOAA and INPE. `sources/`, `live.py` | The age of the data | Source delay, from the live poller | Built. Measured only live. |
| 4. Alert | CHISPA puts the detection into an event with a confidence level. | `fusion.py` | The event and its level | Fire recall, unmatched share, purity, completeness | Built. Scored on 2024. |
| 5. Growth | The fire gets larger. | VIIRS passes. `growth.py` | New pixels, advance and direction at each pass | Short against long times between passes. No reference. | Built. Not in the alert. |
| 6. Confirmation | More passes see the event. The level can go up. | `fusion.py` | The change of the level | Matched share of each level, delay to each level | Built. Scored on 2024. |
| 7. End | The fire stops. | Not built | "No detection", with the visibility | Not decided | Not built |
| 8. Mapping | Months later, a map shows the burned ground. | MapBiomas and MCD64A1. `fires.py`, `evaluation/` | The track record of the alerts | It is the reference for the other stages. | Built |

- Stages 2 to 6 repeat for each new observation. Visibility is part of each stage: could a sensor examine this place? It is built for GOES and for mapped fires. It is not in the alert.
- We cannot make stages 1 to 3 quicker. We read each source by its quickest route, at intervals of 5 minutes.
- Our work is stage 4 and the stages after it: what the alert says, and how we know it.

## The first hypothesis: the merge

A merged alert finds the same mapped fires earlier than one source alone.
It does this without a larger share of alerts that have no mapped fire.

We measured it against fires that a different satellite mapped after the season.
We set the rules on 2023. Then we ran 2024 one time, on the frozen configuration `e03804b1c89a`.
The 2024 result, with satellite sources only, supports the hypothesis only in part:

- The merge finds more fires than each sensor family alone. The gain on GOES, the best family, is small: almost all of it is fires smaller than 100 hectares.
- The merge is not earlier for the typical fire. It is earlier for some fires: where GOES was late, a polar-orbit satellite was first.
- The unmatched share of the merge is between the shares of the single families.
- A higher confidence level matches a mapped fire more frequently: 80 percent of 1582 HIGH events, and 52 percent of 2914 LOW events.
- A second satellite examined the HIGH events with no mapped fire. They are between a fire and no fire: Sentinel-2 showed a burn at 94 of 209 such events, at 82 of 97 events with a mapped fire, and at 22 of 98 boxes with no fire. The rule of this check is weak: read the three numbers together.

We also found an error that is easy to make. A simple comparison showed GOES hours before VIIRS. That lead came from the large GOES pixel, which reaches the fires adjacent to its fire. With a clear match, the two are equal for the typical fire.
[results/SUMMARY.md](results/SUMMARY.md) has each number, adjacent to its limits.

## The next hypothesis: the first alert

The first alert of an event is LOW, and it is the quickest alert that we can make.
HIGH needs a second sensor family. On 93 isolated fires of 2024, it came a median of 2.8 hours later.
The hypothesis: data that exists at the first detection can say which first alerts will match a mapped fire.
It is not measured. We will learn on 2023, tune on 2024 and do the test one time on 2025.

Each other new part gets its hypothesis in the same way, before its result. We do not report a value that we did not measure.

## Status

- `chispa build` gets the raw files from a public bucket and makes a SQLite store: 4.1 million detections and the mapped fires of 2023 and 2024.
- `chispa fuse` groups the detections of one year into events with a confidence level. `chispa evaluate` compares them with the mapped fires.
- `chispa poll` does one pass of the live poller: it records each new detection with the time of the pass, then updates the store and the events. It needs a FIRMS key.
- `tools.py` answers three questions for a given time: the alerts near a position, the detail of one event, and the measured quality of the alerts.
- `chispa burn` asks Sentinel-2 if the ground at each unmatched HIGH event burned. `chispa images` lets a person check a sample. The check by a person is not complete.
- [docs/method.md](docs/method.md) section 13 gives each assumption, its reason and its pitfall.
- Not built: the parts that the stage table marks, the live delay report, the MCP server, the agent and the dashboard.

## Limits you must know

- The evaluation uses satellite sources only, in the Brazilian part of the Pantanal.
- The reference gives the day of a burn, with an uncertainty of some days. Thus we measure delay between sources, not delay from ignition.
- Only isolated fires give a delay: a small sample. One event is not always one fire: the results give the purity.
- An alert with no mapped fire is not always a false alarm. The map does not show each small fire.
- A place with no detection is not a place with no fire. Cloud, smoke and a small fire hide it.
- We give no burned area for an event: a VIIRS pixel is as large as a small fire. Less than half of the steps of 6 to 18 hours show an advance that is larger than the error of the positions.
- We cannot measure the true goal yet: the minutes to brigade acknowledgment, and the share of alerts that brigades say were worth action.

## Data sources

| Source | Content | Access |
|---|---|---|
| [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/) | VIIRS and MODIS hotspots | Free key |
| [GOES-16 and GOES-19](https://registry.opendata.aws/noaa-goes/) | Fire product at intervals of 10 minutes | Open |
| [INPE Queimadas](https://terrabrasilis.dpi.inpe.br/queimadas/portal/) | Hotspot database for Brazil | Open |
| [MapBiomas Fogo](https://brasil.mapbiomas.org/) | Burn scar maps: where a fire burned | Open |
| [MODIS MCD64A1](https://doi.org/10.5067/MODIS/MCD64A1.061) | Burn days: when a fire burned | Open |
| [IBGE](https://www.ibge.gov.br/) | Border of the Pantanal biome | Open |
| [Sentinel-2](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED) | Images of 10 m to 20 m, for the burn check of events | Open |

Each source owns its data. The public bucket has a file `README.txt` with the terms of each source.

- FIRMS: we acknowledge the use of data from NASA's Fire Information for Resource Management System (FIRMS) (https://earthdata.nasa.gov/firms), part of NASA's Earth Science Data and Information System (ESDIS).
- GOES: NOAA GOES-16 ABI Level 2 Fire/Hot Spot Characterization, from the NOAA Open Data Dissemination Program.
- INPE: INPE. Banco de Dados de queimadas. Disponível em: http://www.inpe.br/queimadas/bdqueimadas. Acesso em: 20 nov. 2026.
- MapBiomas Fogo: CC BY 4.0. Alencar et al. 2022, Remote Sensing 14(11), 2510.
- Burn days: NASA MODIS MCD64A1 Version 6.1. https://doi.org/10.5067/MODIS/MCD64A1.061
- IBGE: Biomas e Sistema Costeiro-Marinho do Brasil, 1:250 000. Rio de Janeiro: IBGE, 2019.

INPE gives no named licence for its files: it publishes them as open data. Our copy is not an official INPE service.

## How the data moves

```
sources  --fetch-->  data/raw/  --push-->  public bucket
                                               |
public bucket  --build-->  data/raw/  --build-->  data/chispa.sqlite
```

- The bucket `gs://chispa_raw` is a public copy of the raw files, with no change. It holds no code, no store and no key.
- The store is a result. The command `build` makes it again from the raw files each time.
- A file in the bucket never changes. An upload of a file that exists fails.

## Quickstart

Python 3.12 or later is necessary. You do not need a key or an account for these steps.

```
python3 -m venv venv
venv/bin/pip install -e ".[dev]"
venv/bin/pytest
venv/bin/chispa build
venv/bin/chispa fuse --year 2023
venv/bin/chispa evaluate --year 2023
```

The command `build` downloads each raw file that is absent from `data/raw/`. The first run gets approximately 1.8 GB. With `--offline` it uses only the local raw files.
Then it makes `data/chispa.sqlite`. This needs approximately 5.5 GB of memory and 3 minutes.

## For maintainers: get new raw files

Only a maintainer does these steps. They need a FIRMS key and a Google login.

### 1. Get a FIRMS key

1. Request a free key at https://firms.modaps.eosdis.nasa.gov/api/map_key/.
2. Copy the file `.env.example` to `.env`.
3. Write the key after `FIRMS_API_KEY=`.

Git ignores the file `.env`. Do not put a key in a different file.

### 2. Set up the Google login

One Google login does two jobs: it reads the burn scar maps from Google Earth Engine, and it writes to the bucket.

1. Register a Cloud project for Earth Engine at https://code.earthengine.google.com. The use without payment is for non-commercial work.
2. Write the project ID in `.env` after `EE_PROJECT=`.
3. Install the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install).
4. Log in. This command opens a browser and saves the login outside the repository:

```
gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

To write to the bucket, the login must also have write access to the bucket.
There is no other key for the bucket: the Google permission is the lock.

### 3. Do a check of the access

```
venv/bin/chispa check
```

The correct output has three lines: one for the bucket, one for FIRMS and one for Earth Engine.
If the Earth Engine line fails after some weeks, run the `gcloud` login command again.

### 4. Get raw files and copy them to the bucket

```
venv/bin/chispa fetch firms --year 2024 --push
venv/bin/chispa fetch goes --year 2024 --push
venv/bin/chispa fetch inpe --year 2024 --push
venv/bin/chispa fetch scars --year 2024 --push
venv/bin/chispa fetch burnday --year 2024 --push
venv/bin/chispa fetch border --push
```

- `fetch` saves raw files in `data/raw/`. It does not download a file that is there, and it does not change the store.
- `--push` copies the new files of that source to the bucket.
- `fetch goes` fills a gap of 50 days in the FIRMS record of GOES-16. It reads approximately 11 GB of raw files.
- `fetch inpe` downloads approximately 1.4 GB for the two years. The INPE server is slow.
- `fetch scars` and `fetch burnday` read from Earth Engine.

Then run `venv/bin/chispa build` to make the store again.

## Later work

- A dashboard, an MCP server and a small agent. The agent will not say that a burn is safe.
- Delivery of alerts by SMS, radio or an offline app. Camera detections and community reports.
- A growth forecast, only after a test against measured growth.
- Other regions.

## Language and licence

All text is written to the ASD-STE100 Simplified Technical English writing rules. We do not claim certified compliance.
The licence is not decided.
