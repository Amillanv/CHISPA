# Data sources

This file gives the checked facts and the rules for each external data source.
The section numbers are fixed. Other files refer to them.

## 8. Data sources

Each fact here that is marked `UNVERIFIED` comes from memory, not from a check.
Do a check against the source documentation before you write code that uses the fact.
When you complete the check, remove the mark and correct the fact.
A fact with the mark "Checked" gives the date of a check against the live source.

### 8.1 NASA FIRMS

Checked 2026-11-19 with live requests.

- Content: hotspots from VIIRS (375 m) and MODIS (1 km) on polar-orbit satellites.
- Access: a CSV API with a free key. The key name in our environment is `FIRMS_API_KEY`.
- Request form: `/api/area/csv/{key}/{product}/{west,south,east,north}/{days}/{start_date}`.
- Products for 2023 and 2024: `VIIRS_SNPP_SP`, `VIIRS_NOAA20_SP`, `VIIRS_NOAA21_SP` (from 2023-03-01) and `MODIS_SP`.
- The near-real-time products hold only the last few months. Do not use them for 2023 or 2024.
- One request gives a maximum of 5 days. For `GOES_NRT` the maximum is 2 days.
- The limit is 5000 transactions in 10 minutes.
- The time field `acq_time` is UTC as a number with no leading zeros: `513` is 05:13.
- VIIRS confidence is `l`, `n` or `h`. MODIS confidence is a percentage, 0 to 100.
- The limits that make MODIS classes (30 and 80) come from memory of the MODIS user guide. `UNVERIFIED`
- The pixel size is in the fields `scan` and `track`, in kilometres. We use it for the footprint.
- The archive products are a substitute for the live products. The live detections can be a little different.
- The archive has a field `type` that marks static heat sources. The live products do not have it. Do not use it.
- FIRMS does not give the publication time. `config.py` holds a delay estimate for each sensor family.
- An empty result is a file with only the header line. A bad key gives HTTP 400.
- Each satellite passes approximately two times each day. Thus the gap between observations is hours.

### 8.2 GOES fire product

Checked 2026-11-19 with live requests and one raw file.

- Content: the ABI Fire Detection and Characterization product, full disk, at intervals of 10 minutes.
- GOES-16 has files for 2023 and 2024. GOES-19 has files for 2025. GOES-16 has no files for August 2025.
- The pixel is 2.0 km at the point below the satellite. It is larger over the Pantanal.
- Raw files: bucket `noaa-goes16`, prefix `ABI-L2-FDCF/{year}/{day_of_year}/{hour}/`. No key is necessary.
- One raw file is approximately 1.6 MB. One year is approximately 86 GB.
- One raw file was available 10 minutes after the start of its scan. This is one sample, not a rule.
- FIRMS gives the same detections as CSV rows in the product `GOES_NRT`, from 2022-08-09.
- We get GOES detections from FIRMS, not from raw files. This prevents an 86 GB download.
- In `GOES_NRT`, the `satellite` field has three values. Use only `G16`.
  - `G16`: the NOAA product. The `confidence` field holds the mask class.
  - `G16FRP`: a different algorithm on the same instrument. Its origin is `UNVERIFIED`. Do not use it until we know.
  - `Met10`: Meteosat, at a very oblique angle over the Pantanal. Do not use it.
- FIRMS keeps only the mask classes 10, 11, 30 and 31: good and saturated fire pixels.
- FIRMS drops the cloud-contaminated and probability classes (12 to 15 and 32 to 35).
- Check for one scan (2024-08-15 15:00 UTC, Pantanal box): 99 of 99 FIRMS rows agree with a raw pixel. FIRMS dropped 18 raw pixels of the other classes.
- Thus our GOES data has no low-probability detections. Say this limit in the results.
- FIRMS has no `G16` rows from 2024-09-28 15:00 to 2024-11-16 23:40 UTC. Found 2026-11-20.
- The module `sources/goes.py` fills this gap from the raw NOAA files, with the same four mask classes.
- Check for one hour outside the gap (2024-08-15 15:00 to 15:50): 692 of 692 pixels agree with FIRMS in position, class and FRP.
- The raw record has holes too. The largest are 2024-09-28 15:00 to 2024-09-29 02:20 and 2024-10-02 11:10 to 15:50.
- The scan of 2024-09-28 15:00 exists, but each pixel in it has the class "unprocessed".
- The gap fill gave 150 680 detections from 4859 scans.
- Some days in November 2024 have shorter holes. Each 2024 result must say that GOES has holes in this period.
- A scan with no fire pixel gives no row. Thus we cannot find a hole in the FIRMS record from the row counts.
- Some scans have two raw files. We read the newest file.
- We do not keep the raw GOES files, because the gap is approximately 11 GB. We keep one CSV file of fire pixels for each day.
- The `source` value of these detections is `noaa`.

### 8.3 INPE Queimadas

Checked 2026-11-19 with live requests.

- Content: the Brazilian national hotspot database.
- Access: open CSV files at `dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/`. No key is necessary.
- Use the monthly files in `mensal/Brasil/`. They are `.zip` for 2023 and `.csv` for 2024.
- The monthly files for 2024 are 1.2 GB together. The largest is 389 MB. The 2023 files are 185 MB together.
- The server is slow. A download with a short timeout gives a file that is not complete.
- The satellite counts in this section came from such a file. They show which satellites exist, not how many rows.
- Fields: `id`, `lat`, `lon`, `data_hora_gmt`, `satelite`, `bioma`, `frp`, `numero_dias_sem_chuva`, `precipitacao`, `risco_fogo` and place names.
- The `bioma` field lets us select the Pantanal with no border file.
- Satellites: NOAA-21, NOAA-20, GOES-16, NPP-375, NPP-375D, AQUA, TERRA, METOP-B, METOP-C, NOAA-18, NOAA-19, MSG-03.
- The meaning of the suffix `D` and of `M-M` and `M-T` is `UNVERIFIED`. We use only the satellite name.
- We do not use MSG-03. It is a Meteosat satellite.
- Some rows have no `frp` field.
- METOP, NOAA-18 and NOAA-19 carry the AVHRR sensor. FIRMS does not give it. It is a sensor family that only INPE adds.
- INPE uses its own detection method on GOES-16. Its GOES counts are not the FIRMS counts.
- INPE gives a GOES time approximately 7 minutes after the start of the scan. FIRMS gives the start of the scan.
- For the polar-orbit satellites, the INPE time and the FIRMS time of one pass differ by one or two minutes.
- The store has 1 135 655 INPE detections for the Pantanal box in 2023 and 2024.
- Some rows have positions with only two decimal places.
- An INPE hotspot and a FIRMS hotspot from the same satellite pass are one observation, not two.

Terms, from a check of the INPE pages on 2026-11-20:

- INPE calls the files "open data for public use", free of charge, for any user.
- INPE gives no named licence for these files. No page permits or prohibits a public copy.
- The CC BY-SA 4.0 licence on the TerraBrasilis site is for a different INPE programme. Do not use it for these files.
- Citation that INPE asks for: `INPE. Banco de Dados de queimadas. Disponível em: http://www.inpe.br/queimadas/bdqueimadas. Acesso em: <date>.`
- The owner decided on 2026-11-20 to put the INPE files in the public bucket, with the citation and a note that the copy is not official.
- The owner asks INPE for a written answer (cienciasdaterra@inpe.br). If INPE objects, remove the files from the bucket.

### 8.4 Open-Meteo

Checked 2026-11-19 with live requests.

- Content: recorded weather, weather forecasts and air quality.
- Access: a JSON API. No key is necessary. The free API is for non-commercial use.
- Use the archive API for 2023 and 2024. Use the forecast API for burn conditions.
- The air quality API gives hourly `aerosol_optical_depth` for 2022, 2023 and 2024 in the Pantanal.
- The weather grid is coarse. A value is for a grid cell, not for a point.
- The grid size of the AOD data is `UNVERIFIED`.

### 8.5 MapBiomas Fogo

Checked 2026-11-19 against the MapBiomas pages, the method document for Collection 5.1 and Alencar et al. 2022.

- Content: maps of burned area in Brazil from Landsat imagery at 30 m. This is our ground truth.
- Use Collection 5.1. It has the years 1985 to 2025, thus 2023 and 2024.
- Use the layer `burned_monthly_{year}`. Each pixel value is the month of the burn, 1 to 12.
- The month is the month of the Landsat image with the lowest burn index. It is not the month of ignition.
- Thus the month can be later than the true burn, and a pixel has only one month in a year.
- There is no layer with the day of the burn.
- The files are for all of Brazil. We must clip them to the Pantanal.
- The published GeoTIFF addresses gave HTTP 403 to a request with no login on 2026-11-19.
- Access is through Google Earth Engine. Checked 2026-11-20: the asset has the bands for 2023 and 2024 at 30 m.
- Asset: `projects/mapbiomas-public/assets/brazil/fire/collection5_1/mapbiomas_fire_collection51_monthly_burned_v1`.
- The Cloud project ID is in the environment variable `EE_PROJECT`.
- Earth Engine uses the Google login of `gcloud` on the computer. The command `earthengine authenticate` was blocked for the owner account.
- Licence: CC BY 4.0. Cite Alencar et al. 2022, Remote Sensing 14(11), 2510.

What we store, from the download of 2026-11-20:

- `fetch scars` reads the layer on its own 30 m grid, with no resampling, as 130 tiles for each year. The tiles for two years are 8 MB.
- The Pantanal box is a grid of 25 975 rows and 18 554 columns.
- `build` keeps the pixels in the biome border and groups pixels that touch and have the same month into scars.
- 2023: 66 349 scars, 627 508 hectares. 2024: 703 889 scars, 2 212 767 hectares.
- Most scars are very small. In 2024, 631 033 scars are smaller than 1 hectare. Together they hold 6 percent of the burned area.
- A cause is the month split: one burned area with two image dates becomes pieces with different months.
- Thus the evaluation must report by scar size and by area, and must use a minimum scar size.
- `build` needs approximately 5.5 GB of memory for the scar step.

### 8.8 IBGE biome border

Checked 2026-11-20 with a live request.

- Content: the border of the six biomes of Brazil at the scale 1:250 000, from the IBGE map service (layer `CREN:lm_bioma_250`).
- The Pantanal has the code 6 and an area of 150 961 km2. Our grid mask of the border has 150 761 km2.
- The file is GeoJSON in the datum SIRGAS 2000, which is less than one metre from WGS84.
- The terms of IBGE for a public copy are `UNVERIFIED`. The owner decided on 2026-11-20 to put the border file in the bucket with attribution.
- The citation in the bucket file is from memory. `UNVERIFIED`

Independence from hotspots:

- The model uses only four spectral bands. It does not use hotspots as an input.
- The authors used hotspots and MODIS burned area to select which Landsat scenes to sample for training.
- A hotspot filter removes some scars, but only in Amazon forest. It does not apply to the Pantanal.
- Thus the ground truth for the Pantanal is almost independent of our detections. Say "almost", and give the reason.
- Do not use the product "Monitor do Fogo" as ground truth without a new check. In other biomes it maps only near INPE hotspots.

Known errors of the ground truth:

- The only published accuracy is for Collection 1: more omission than commission. `UNVERIFIED` for the exact numbers and for the Pantanal.
- The authors report commission errors in wetlands and dry lagoons. This is important for the Pantanal.
- The method removes burned areas of 1.4 hectares or smaller. A fire of that size cannot have a scar.

### 8.6 Cameras and community reports

- No recorded data at this time.
- The data model accepts these sensor families from the start.
- Do not write an adapter until real data exists.

### 8.7 Rules for all sources

1. Read keys from environment variables. Do not write a key in a file that git tracks.
2. Save each raw download in `data/raw/` before you parse it. Do not change raw files. The raw GOES files are the only exception (section 8.2).
3. Do not download a file again if the raw file exists.
4. Obey the rate limits of each source. Add a delay between requests.
5. The bucket records the upload time of each raw file. The store does not record files.
6. Keep the attribution text that each source requires in `README.md`.
7. `data/` is not in git. A reader must be able to make it again with the command `chispa build`.
8. A network error must stop the run with a clear message. Do not continue with partial data in silence.
9. The bucket `gs://chispa_raw` holds raw files only. Never put the store, code or a key in it.
10. A file in the bucket never changes. To correct a raw file, give the new file a new name.
11. The code reads the bucket with plain HTTPS and no login. Only the function `push` uses a Google login.
12. Do not use `--push` for a new source until the owner agrees. The owner agreed for FIRMS, GOES and INPE.
14. The file `README.txt` in the bucket gives the terms of each source. Update it when a source is added.
13. The store is a result. Do not edit it by hand. Change the parser or the raw files, then build again.

### 8.9 Burn day products

Checked 2026-11-20 with live requests, and against the user guides and Giglio et al. 2018 and 2025.
We use MCD64A1: `fetch burnday` saves one file for each month on a grid of 0.004 degrees. We do not use VNP64A1.

Access:

- The FIRMS products `BA_MODIS` and `BA_VIIRS` give no rows through the area CSV API. Do not use them.
- Earth Engine has `MODIS/061/MCD64A1` and `NASA/VIIRS/002/VNP64A1`: one image for each month, pixels of 463 m.
- Each has 12 images for 2023 and for 2024.
- Terms: open with no restriction (CC0). NASA asks for a citation. MCD64A1: https://doi.org/10.5067/MODIS/MCD64A1.061

Method, from the documents:

- The burn day comes only from the change in the surface reflectance. It does not come from a hotspot.
- The decision that a pixel burned does use hotspots: they give the training samples and the prior probability.
- Thus the burn day is "reasonably independent" of hotspots (the words of the authors), but the set of burned pixels is not.
- The uncertainty band is the number of days between the last clear view before the burn and the first clear view after it.
- Published check for 2023: 46 percent of MCD64A1 burn days are the day of a MODIS hotspot, and 72 percent are not more than 2 days from it.
- Global validation: approximately 72 percent omission and 34 to 40 percent commission. The products do not find most small burns.
- VNP64A1 uses only the Suomi NPP satellite, with pixels of 750 m. Suomi NPP data stopped on 2026-11-02.
- The MODIS orbits drift. The authors say the effect became larger in late 2024 and that they examine it. The size of the effect on MCD64A1 is not published.

Our comparison in the Pantanal biome, 2023, on a grid of 0.004 degrees:

| | MCD64A1 | VNP64A1 |
|---|---|---|
| MapBiomas burned area that has a burn day | 0.891 | 0.836 |
| Product burned area that MapBiomas also maps | 0.469 | 0.473 |
| Uncertainty in days, median and 90th percentile | 3 and 7 | 4 and 11 |

- With one or the other product, 0.913 of the MapBiomas burned area has a burn day.
- The two products agree on the burn day to 1 day for 48 percent of cells, to 3 days for 77 percent and to 7 days for 95 percent.
- MapBiomas gives the same month as the burn day for 37 percent of the area, one month later for 60 percent, two months later for 1.5 percent. It almost never gives an earlier month. The two products give the same numbers.
- Thus the month margin of the evaluation must be on one side: the detection is in the scar month or the month before.
