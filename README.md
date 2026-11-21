# CHISPA

CHISPA merges fire detections from different sources into one alert for each fire.
Then it measures how good those alerts are, and it publishes the result: good or bad.

## The problem

A brigade gets fire data from many places.
Polar-orbit satellites see small fires, but only a few times each day.
Geostationary satellites look every 10 minutes, but with large pixels.
Cameras and people see a fire quickly, but only near them.
The same fire can show as many records, and some records are not fires.

## The hypothesis

A merged alert finds the same mapped fires earlier than one source alone.
It does this without a larger share of alerts that have no mapped fire.

## The result

We did not assume that the merge helps. We measured it against fires that a different satellite mapped after the season.
We set the rules on 2023. Then we ran 2024 one time, on the frozen configuration `e03804b1c89a`.
The 2024 result, with satellite sources only, supports the hypothesis only in part:

- The merge finds more fires than each sensor family alone. The gain on GOES, the best family, is small: almost all of it is fires smaller than 100 hectares.
- The merge is not earlier for the typical fire. It is earlier for some fires: where GOES was late, a polar-orbit satellite was first.
- The unmatched share of the merge is between the shares of the single families.
- A higher confidence level matches a mapped fire more frequently.

We also found an error that is easy to make. A simple comparison showed GOES hours before VIIRS.
That lead came from the large GOES pixel, which reaches the fires adjacent to its fire. With a clear match, the two are equal for the typical fire.
[results/SUMMARY.md](results/SUMMARY.md) has each number, adjacent to its limits.

## Why we build the live system

The gain of the merge alone is not the reason. The result gives three better reasons:

1. **No one sensor is sufficient.** GOES is quick and finds the large fires. The polar-orbit satellites find small fires that GOES does not find, and they are first when GOES is late.
2. **The confidence level has a measured meaning.** In 2024, 80 percent of 1582 HIGH events matched a mapped fire, and 52 percent of 2914 LOW events. A brigade with few people can go to the HIGH alerts first.
3. **Recorded data cannot answer the two most important questions.** How many minutes go by from a satellite scan to an alert? Does a brigade say that the alert was worth action?

Only a live system can measure these. Thus we build one that measures itself from the first day.
We will not ask a brigade to trust a number that we did not measure.

## Status

- `chispa build` gets the raw files from a public bucket and makes a SQLite store: 4.1 million detections and the mapped fires of 2023 and 2024.
- `chispa fuse` groups the detections of one year into events with a confidence level. `chispa evaluate` compares them with the mapped fires.
- `chispa poll` does one pass of the live poller: it records each new detection with the time of the pass, then updates the store and the events. It needs a FIRMS key.
- `tools.py` answers three questions for a given time: the alerts near a position, the detail of one event, and the measured quality of the alerts.
- [docs/method.md](docs/method.md) section 13 gives each assumption, its reason and its pitfall.
- Not built yet: the live delay report, the weather, the MCP server, the agent and the dashboard.

## What we measure

The evaluation uses recorded data from the Brazilian Pantanal.
The truth is a map of burn scars. We group the scars into fires with a map of burn days.

| Measure | Meaning |
|---|---|
| Fire recall | The share of mapped fires that got a minimum of one detection. |
| Relative delay | The time from the first detection by all sources to the first detection of one configuration. |
| Unmatched share | The share of detections with no mapped fire. Precision against the map is 1 minus this share. |

We report each measure by source, by sensor family, by confidence level and by fire size.
We cannot measure the true goal yet: the minutes to brigade acknowledgment, and the share of alerts that brigades say were worth action.
We will not report these two measures until brigades use a live system.

## Limits you must know

- The first evaluation uses satellite sources only. We have no recorded camera data or community reports for 2024.
- The ground truth gives the day of a burn, with an uncertainty of some days. Thus we measure delay between sources, not delay from the true start of a fire.
- Only isolated fires give a delay: a small sample. One event is not always one fire: the results give the purity.
- An alert with no mapped fire is not always a false alarm. The fire can be too small for the map.
- Some sources use the same satellites. We count one satellite pass as one observation.

## Data sources

| Source | Content | Access |
|---|---|---|
| [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/) | VIIRS and MODIS hotspots | Free key |
| [GOES-16 and GOES-19](https://registry.opendata.aws/noaa-goes/) | Fire product at intervals of 10 minutes | Open |
| [INPE Queimadas](https://terrabrasilis.dpi.inpe.br/queimadas/portal/) | Hotspot database for Brazil | Open |
| [Open-Meteo](https://open-meteo.com/) | Weather and air quality. Not built yet. | Open, non-commercial |
| [MapBiomas Fogo](https://brasil.mapbiomas.org/) | Burn scar maps: where a fire burned | Open |
| [MODIS MCD64A1](https://doi.org/10.5067/MODIS/MCD64A1.061) | Burn days: when a fire burned | Open |
| [IBGE](https://www.ibge.gov.br/) | Border of the Pantanal biome | Open |

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

The command `build` downloads each raw file that is absent from `data/raw/`. The first run gets approximately 1.8 GB.
Then it makes `data/chispa.sqlite`. This needs approximately 5.5 GB of memory and 3 minutes.

Use `venv/bin/chispa build --offline` to make the store from the local raw files only.

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

Google blocked the usual command `earthengine authenticate` for one of our accounts. The `gcloud` login worked.

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

- An MCP server with a small agent, gold questions and a Flask dashboard. The agent will not say that a burn is safe.
- Delivery of alerts by SMS, radio or an offline app.
- Camera detections and community reports.
- Burn scar maps from Ai2 OlmoEarth on Sentinel-2 imagery, for areas that MapBiomas does not map.
- Other regions.

## Language and licence

All text is written to the ASD-STE100 Simplified Technical English writing rules. We do not claim certified compliance.
The licence is not decided.
