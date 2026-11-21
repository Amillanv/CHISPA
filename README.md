# CHISPA

CHISPA merges fire detections from different sources into one alert for each fire.
Then it measures how good those alerts are.

## Status

**There are no results for the test year 2024.**

What works at this time:

- A public bucket holds the raw files of each source in the table below.
- `chispa build` gets the raw files from the bucket and makes a SQLite store: 4.1 million detections and the mapped fires of 2023 and 2024.
- `chispa fuse` groups the detections of one year into events with a confidence level. Its thresholds are a first proposal.
- `chispa evaluate` compares one fused year with the mapped fires and writes [results/SUMMARY.md](results/SUMMARY.md).
- `chispa fetch` gets raw files from the sources. `chispa check` does a check of the bucket, the key and the login.

**The numbers in `results/` are for the development year 2023 and are not conclusions.**
Two known limits are open:

- Only isolated fires give a delay. In 2023 that is a small sample.
- One event is not always one fire. The results give the purity and the completeness of the events.

[docs/method.md](docs/method.md) section 13 gives each assumption, its reason and its pitfall.
The weather, the smoke level, the agent and the dashboard do not exist yet.

## The problem

A brigade gets fire data from many places.
Polar-orbit satellites see small fires, but only a few times each day.
Geostationary satellites look every 10 minutes, but with large pixels.
Cameras and people see a fire quickly, but only near them.
The same fire can show as many records, and some records are not fires.

## The hypothesis

A merged alert finds the same mapped fires earlier than one source alone.
It does this without a larger share of alerts that have no mapped fire.

We do not know if this is true. The project exists to find out.
We will publish the result if it is positive or negative.

## What we measure

The evaluation uses recorded data from the Brazilian Pantanal. We tune on 2023 and score on 2024.
The truth is a map of burn scars. We group the scars into fires with a map of burn days.

| Measure | Meaning |
|---|---|
| Fire recall | The share of mapped fires that got a minimum of one detection. |
| Relative delay | The time from the first detection by all sources to the first detection of one configuration. |
| Unmatched share | The share of detections with no mapped fire. Precision against the map is 1 minus this share. |

We report each measure by source, by sensor family, by confidence level and by fire size.

### What we cannot measure yet

The true goal has two measures:

- The minutes from first detection to brigade acknowledgment.
- The share of alerts that brigades say were worth action.

These measures need a live system and brigades that use it.
Recorded data cannot give them. We will not report them until we have them.

## Limits you must know

- The first evaluation uses satellite sources only. We have no recorded camera data or community reports for 2024.
- The ground truth gives the day of a burn, with an uncertainty of some days. Thus we measure delay between sources, not delay from the true start of a fire.
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

INPE gives no named licence for its files. It publishes them as open data for public use.
Our copy of the INPE files is not an official INPE service.

## How the data moves

```
sources  --fetch-->  data/raw/  --push-->  public bucket
                                               |
public bucket  --build-->  data/raw/  --build-->  data/chispa.sqlite
```

- The raw files are the files that the sources gave, with no change.
- The bucket `gs://chispa_raw` is a public copy of the raw files. It holds no code, no store and no key.
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

The command `build` does two things:

1. It downloads each raw file that is absent from `data/raw/`. The first run gets approximately 1.8 GB.
2. It makes `data/chispa.sqlite` from the raw files. This needs approximately 5.5 GB of memory and 3 minutes.

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
- Live operation with delivery by SMS, radio or an offline app.
- Camera detections and community reports.
- Burn scar maps from Ai2 OlmoEarth on Sentinel-2 imagery, for areas that MapBiomas does not map.
- Other regions.

## Language and licence

All text is written to the ASD-STE100 Simplified Technical English writing rules. We do not claim certified compliance.
The licence is not decided.
