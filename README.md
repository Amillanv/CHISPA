# CHISPA

CHISPA merges fire detections from different sources into one alert for each fire.
Then it measures how good those alerts are.

## Status

**There are no results.**

What works at this time:

- A public bucket holds the raw files of FIRMS, of the GOES gap fill and of INPE.
- The command `chispa build` gets the raw files from the bucket and makes a SQLite store of detections. It needs no key.
- The command `chispa fetch` gets raw files from the sources: FIRMS (VIIRS, MODIS, GOES-16), raw GOES files and INPE.
- The command `chispa check` does a check of the bucket, the FIRMS key and the Earth Engine login.

The weather, the burn scars, the fusion, the evaluation, the agent and the dashboard do not exist yet.

## The problem

A brigade gets fire data from many places.
Polar-orbit satellites see small fires, but only a few times each day.
Geostationary satellites look every 10 minutes, but with large pixels.
Cameras and people see a fire quickly, but only near them.
The same fire can show as many records, and some records are not fires.

## The hypothesis

A merged alert finds the same burn scars earlier than one source alone.
It does this without a larger share of alerts that have no mapped burn scar.

We do not know if this is true. The project exists to find out.
We will publish the result if it is positive or negative.

## What we measure

The first evaluation uses recorded data from the Brazilian Pantanal in 2024.

| Measure | Meaning |
|---|---|
| Scar recall | The share of mapped burn scars that got a minimum of one alert. |
| Relative delay | The time from the first detection by all sources to the first alert. |
| Unmatched alert share | The share of alerts with no mapped burn scar. |

We report each measure by source, by burn scar size and by smoke level.

### What we cannot measure yet

The true goal has two measures:

- The minutes from first detection to brigade acknowledgment.
- The share of alerts that brigades say were worth action.

These measures need a live system and brigades that use it.
Recorded data cannot give them. We will not report them until we have them.

## Limits you must know

- The first evaluation uses satellite sources only. We have no recorded camera data or community reports for 2024.
- The ground truth gives the month of a burn, not the minute. Thus we measure delay between sources, not delay from the true start of a fire.
- An alert with no mapped burn scar is not always a false alarm. The fire can be too small for the map.
- Some sources use the same satellites. We count one satellite pass as one observation.
- Smoke level comes from a coarse atmosphere model. It is an estimate.

## Data sources

| Source | Content | Access |
|---|---|---|
| [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/) | VIIRS and MODIS hotspots | Free key |
| [GOES-16 and GOES-19](https://registry.opendata.aws/noaa-goes/) | Fire product at intervals of 10 minutes | Open |
| [INPE Queimadas](https://terrabrasilis.dpi.inpe.br/queimadas/portal/) | Hotspot database for Brazil | Open |
| [Open-Meteo](https://open-meteo.com/) | Weather, forecasts and air quality | Open, non-commercial |
| [MapBiomas Fogo](https://brasil.mapbiomas.org/) | Burn scar maps, used as ground truth | Open |

Each source owns its data. The public bucket has a file `README.txt` with the terms of each source.

- FIRMS: we acknowledge the use of data from NASA's Fire Information for Resource Management System (FIRMS) (https://earthdata.nasa.gov/firms), part of NASA's Earth Science Data and Information System (ESDIS).
- GOES: NOAA GOES-16 ABI Level 2 Fire/Hot Spot Characterization, from the NOAA Open Data Dissemination Program.
- INPE: INPE. Banco de Dados de queimadas. Disponível em: http://www.inpe.br/queimadas/bdqueimadas. Acesso em: 20 nov. 2026.
- MapBiomas Fogo: CC BY 4.0. Alencar et al. 2022, Remote Sensing 14(11), 2510.

INPE gives no named licence for its files. It publishes them as open data for public use.
Our copy of the INPE files is not an official INPE service.

## Planned parts

The fusion, the evaluation, an MCP server with a small agent, a set of gold questions and a Flask dashboard.
The agent gives burn conditions from the weather forecast.
It does not say that a burn is safe, and it does not give authorization to burn.

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
```

The command `build` does two things:

1. It downloads each raw file that is absent from `data/raw/`. The first run gets approximately 1.8 GB.
2. It makes `data/chispa.sqlite` from all the raw files in `data/raw/`.

Use `venv/bin/chispa build --offline` to make the store from the local raw files only.
The other commands in `venv/bin/chispa --help` are not built yet.

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

The usual alternative for Earth Engine is `venv/bin/earthengine authenticate`.
Google blocked that command for one of our accounts with the message "This app is blocked".
The `gcloud` login worked for the same account. We did the check on one computer only.

To write to the bucket, the login must also have write access to the bucket.
There is no other key for the bucket: the Google permission is the lock.

### 3. Do a check of the access

```
venv/bin/chispa check
```

The correct output has three lines:

```
Bucket: public read works. 1004 raw files.
FIRMS: key works. 0 of 5000 transactions used.
Earth Engine: login works. Found burned_monthly_2023, burned_monthly_2024.
```

If the Earth Engine line fails after some weeks, run the `gcloud` login command again.

### 4. Get raw files and copy them to the bucket

```
venv/bin/chispa fetch firms --year 2024 --push
venv/bin/chispa fetch goes --year 2024 --push
venv/bin/chispa fetch inpe --year 2024 --push
```

- `fetch` saves raw files in `data/raw/`. It does not download a file that is there, and it does not change the store.
- `--push` copies the new files of that source to the bucket.
- `fetch firms` makes approximately 475 requests for one year.
- `fetch goes` fills a gap of 50 days in the FIRMS record of GOES-16. It reads approximately 11 GB of raw files and keeps only the fire pixels.
- `fetch inpe` downloads approximately 1.4 GB for the two years. The INPE server is slow.

Then run `venv/bin/chispa build` to make the store again.

## Language

All text in this repository is written to the ASD-STE100 Simplified Technical English writing rules.
We do not claim certified compliance.

## Later work

- Live operation with delivery by SMS, radio or an offline app.
- Camera detections and community reports.
- Burn scar maps from Ai2 OlmoEarth on Sentinel-2 imagery, for areas that MapBiomas does not map.
- Other regions.

## Licence

Not decided.
