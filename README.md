# Chispa

Chispa merges fire detections from different sources into one alert for each fire.
Then it measures how good those alerts are.

## Status

**There are no results.**

The project skeleton exists: the detection record, the SQLite store and the command names.
No command gets data yet. This section will change when data and results exist.

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

Each source has its own licence and attribution text.
We will add the necessary attribution text here before the first data release.

## Planned parts

1. **Sources:** one module for each data source.
2. **Fusion:** rules that group detections into events and give a confidence level.
3. **Evaluation:** one command that makes all result tables.
4. **MCP server and agent:** tools that answer questions such as "What is new near this village?"
5. **Gold questions:** a set of questions with known answers, to measure the agent.
6. **Dashboard:** a Flask page with a map, the results and a question box.

The agent gives burn conditions from the weather forecast.
It does not say that a burn is safe, and it does not give authorization to burn.

## How to use it

Install the project and run the tests. Python 3.12 or later is necessary.

```
python3 -m venv venv
venv/bin/pip install -e ".[dev]"
venv/bin/pytest
venv/bin/chispa --help
```

The commands in the help text are not built yet. Each one stops with a message.

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
