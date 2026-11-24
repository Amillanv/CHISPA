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

Checked 2026-11-23 with live requests, for the 2025 data:

- The archive products `VIIRS_SNPP_SP`, `VIIRS_NOAA20_SP`, `VIIRS_NOAA21_SP` and `MODIS_SP` have data to 2026-08-31.
- In `GOES_NRT`, the `satellite` field changed in 2025. On 2025-03-15 it had `G16`. On 2025-04-10, 2025-08-15 and 2025-12-15 it had `G19`.
  The rows of `G19` have the mask class in the `confidence` field, as the rows of `G16`. We use `G19` with the platform name `GOES19`.
- The same days also had `G19FRP`, `Met10` and a new value `Met12`. We do not use them, as before.
- April 2025 has GOES detections on 14 days. Each other month has them on 26 days or more. Checked 2026-11-23:
  - FIRMS gives `G16` to 2025-04-07 and `G19` from 2025-04-06. The two are in the rows of 6 and 7 April.
  - FIRMS has no `G19` row in the Pantanal box on 13 to 18 April and on 22 to 30 April.
  - The NOAA bucket `noaa-goes19` has all 144 files for 11, 16, 23 and 27 April. The bucket `noaa-goes16` has none for those days.
  - In 12 scans of each of those days, the window of the box had 3, 0, 1 and 0 fire pixels. The sensor examined
    84, 51, 24 and 17 percent of the window: the days with no row had much cloud.
  - Thus we found no hole in April 2025: the raw files exist, and they have almost no fire pixels. We read one scan of each two hours, not all.
- Not checked: holes in the `G19` record of the other months of 2025. A hole in 2024 was seven weeks long.
- The 2025 store has 200 140 detections, 17 146 fires and 589 counted fires: a year with few fires.
- The burn scar asset has the band `burned_monthly_2025`. The burn day product has one image for each month of 2025.

Checked 2026-11-23 with live requests, for the data of 2026 before the live logs:

- The archive products (`_SP`) have data to 2026-08-31. FIRMS gives the last day of each product at `/api/data_availability/csv/{key}/ALL`.
- The live products `VIIRS_SNPP_NRT`, `VIIRS_NOAA20_NRT` and `MODIS_NRT` have data from 2026-09-01. `VIIRS_NOAA21_NRT` has data from 2024-01-17.
- A request for an archive product after its last day gives no row and no error. Thus `fetch firms` asks FIRMS for the last day,
  and it gets the live product of the same satellite for the later days.
- A request on 2026-10-10 for 2 days gave no row for each of the four live products. Not checked: if this is a hole or two days with no fire.
- The rows of a live product from the archive have no time of the first view. Their `available_at` is an estimate, as for 2023 to 2025.
- INPE has the monthly files of 2026 to November. The file of a month in progress changes each day: we get the months to October.
  INPE also has a file for each day (`focos/csv/diario/`). We do not read it. Thus 1 to 19 November 2026 has no INPE detection.

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
- Some scans have two raw files. The read of the archive takes the newest file. The live poller takes the file that came first: a pass cannot wait for a second file.
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
- The AOD grid has cells of approximately 0.4 degrees (44 km). Checked 2026-11-21: five points on one latitude gave three different series.
- One request accepts a list of positions.

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
- Then `build` groups the scars into fires. `docs/method.md` section 11.3 gives the rule. The store holds the fires, not the scars.
- 2023: 66 349 scars, 29 210 fires, 627 508 hectares. 2024: 703 889 scars, 380 530 fires, 2 212 767 hectares.
- Most scars are very small. A cause is the month split: one burned area with two image dates becomes pieces with different months.
- Thus the evaluation uses fires, reports by fire size and by area, and uses a minimum fire size.
- `build` needs approximately 5.5 GB of memory for the scar step.

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
12. Do not use `--push` for a new source until the owner agrees. The owner agreed for each source that is in the bucket now.
13. The store is a result. Do not edit it by hand. Change the parser or the raw files, then build again.
14. The file `README.txt` in the bucket gives the terms of each source. Update it when a source is added.

### 8.8 IBGE biome border

Checked 2026-11-20 with a live request.

- Content: the border of the six biomes of Brazil at the scale 1:250 000, from the IBGE map service (layer `CREN:lm_bioma_250`).
- The Pantanal has the code 6 and an area of 150 961 km2. Our grid mask of the border has 150 761 km2.
- The file is GeoJSON in the datum SIRGAS 2000, which is less than one metre from WGS84.
- The terms of IBGE for a public copy are `UNVERIFIED`. The owner decided on 2026-11-20 to put the border file in the bucket with attribution.
- The citation in the bucket file is from memory. `UNVERIFIED`

### 8.9 Burn day products

Checked 2026-11-20 with live requests, and against the user guides and Giglio et al. 2018 and 2025.
We use MCD64A1: `fetch burnday` saves one file for each month on a grid of 0.004 degrees. We do not use VNP64A1.
`build` uses the burn days to group the scars into fires.

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

### 8.10 Live products

Checked 2026-11-21 at 20:13 UTC with live requests. The command `chispa poll` reads raw GOES-19, the three FIRMS products and the INPE files of 10 minutes.

- FIRMS has the near-real-time products `VIIRS_NOAA20_NRT`, `VIIRS_NOAA21_NRT`, `MODIS_NRT` and `GOES_NRT` to the present day.
- `VIIRS_SNPP_NRT` stops on 2026-11-02. Suomi NPP is not a live source.
- In `GOES_NRT`, the `satellite` field now has `G19`, `G19FRP`, `Met12` and `Met10`. GOES-19 replaced GOES-16.
- The near-real-time rows have the same fields as the archive rows, and no publication time.
- The newest row of each FIRMS product for the Pantanal box was 3 to 15 hours old. This says little: it depends on the passes and on the fires of that day.
- Raw GOES-19 files: bucket `noaa-goes19`, same prefix as GOES-16. The bucket `noaa-goes16` has no new files.
- For 12 of 12 scans in two hours, the raw GOES-19 file was in the bucket 10 minutes after the start of its scan. The bucket gives this time for each file.
- INPE has one CSV file for each 10 minutes in `focos/csv/10min/`. The file of 20:10 UTC was on the server at 20:10 UTC.
- An INPE file of 10 minutes has only the fields `lat`, `lon`, `satelite` and `data` (the observation time, UTC). It has no FRP. It is for all of South America.
- In 40 files, the satellites were NOAA-21, NOAA-20, GOES-19, AQUA, TERRA and MSG-03. The server keeps approximately 4 days of files.
- The answer to a file request gives the publication time (`Last-Modified`). One sample: INPE published a NOAA-21 pass of 16:56 UTC at 20:20 UTC.
- Thus two sources give a publication time that we can measure: raw GOES and the INPE files of 10 minutes. FIRMS gives none: we must record when we first see a row.
- A raw GOES-19 file is approximately 2.1 MB. One day of scans is approximately 300 MB. The poller reads the files and does not keep them.
- In 21 scans from 17:00 to 20:20 UTC on 2026-11-21, the Pantanal box had no fire pixel of the four classes.
- In the scan of 20:20, the mask had the class "processed, no fire" for only 3 percent of the pixels near the box. 43 percent were cloud, and 51 percent had no background value. Thus "no detection" was not "no fire".

Checked 2026-11-24 from 20:15 to 21:00 UTC with live requests.

- The bucket `noaa-goes19` had 701 files with a scan start from 2026-11-20 00:00 to 2026-11-24 20:30 UTC: one file for each of 701 scan starts. 700 starts are the times at a multiple of 10 minutes, and one more scan started at 10:45 on 23 November. The file of a scan was in the bucket a median of 10.2 minutes after the scan start. The 90th percentile was 10.9 minutes, and the maximum was 12.1.
- For 2026-11-23, FIRMS `GOES_NRT` gave 28 rows with the satellite `G19` in the box. The poller read 28 fire pixels from the raw files. The 28 had the same time, the same position to 2 decimals and the same class (25 of class 30, 3 of class 10). Thus the raw files gave the rows of the FIRMS product for that day.
- A FIRMS request with a start date and 5 days gives the rows of past days for the three live products. A live request for 2 days does not give a row of the day before yesterday.
- At 20:15 UTC the oldest INPE file of 10 minutes on the server was that of 2026-11-21 00:00. A file of 10 minutes was 1 kB to 77 kB.
- The rules of the poller from 2026-11-24. A pass asks FIRMS for 5 days. It reads each GOES scan and each INPE file of the last 4 days that no pass read (`config.LIVE_LOOKBACK`). It keeps each INPE file in full in `live/inpe_files/`, with its publication time: the logs have only the rows in the Pantanal box. What a stop of the poller can lose is different for each source. GOES: a pass reads back to the newest scan that a pass read, and the bucket keeps each file. Thus a stop of each length gets its scans. The exception is a file that comes to the bucket out of sequence before a stop of more than 4 days. FIRMS: a live request has no start date, and it asks for the day of the request and the 4 days before it. Thus after a stop of 3 days or less, a request still asks for each day of the stop. We did not check that FIRMS then gives each row of those days. INPE: the oldest file was 3.8 days old, thus a stop of more than 3 days can lose files. The option `--since` of `chispa poll` changes the read-back of GOES and INPE, not the FIRMS request. A pass does not read back to before `config.LIVE_START`. The last row of a pass in the poll log says that the pass read each source: a pass with no such row stopped in the middle. The first pass with a last row started at 22:46 UTC on 2026-11-24. Each of the 10 passes from 22:06 to 22:45 UTC of that day, which wrote their rows one at a time with no last row, has its three FIRMS rows and ended. A pass reads FIRMS, then INPE, then GOES: INPE removes its files, and the bucket keeps each scan.
- The memory of one pass, as `/usr/bin/time -l venv/bin/chispa poll` gives it (maximum resident set size): 0.1 GB for a pass that read 3 scans, with the fixed window of the box. With a search of the window in the full grid it was 3.4 GB.

### 8.11 Sentinel-2 images

Checked 2026-11-22 with live requests to Earth Engine.

- Asset: `COPERNICUS/S2_SR_HARMONIZED`. The same Google login as for the burn scars reads it.
- One point in the Pantanal had 12 images from 2024-07-15 to 2024-09-15: one image each 5 days.
- The bands B12, B8 and B4 show a new burn as a dark red area. The pixels are 10 m (B4, B8) and 20 m (B12).
- `CLOUDY_PIXEL_PERCENTAGE` is for the full image tile, not for a small box in it.
- A search must have a filter on the position first. A search with no such filter took approximately one minute.
- The band `SCL` gives a class for each pixel: cloud, cloud shadow, water and others. The burn check uses it to keep clear pixels.
- A band name in a request cannot have a point.
- One measure of the burn check for one box took approximately 2 seconds, and 6 seconds for a box of 50 km.
- The 152 pictures of the 2024 image check are 181 MB. They are in `data/images/`, not in the bucket.
- For the 90 events of the 2024 sample, 69 have a picture before and a picture after. 13 have no picture before, and 15 have no picture after.
- Checked 2026-11-23: the scene classes of the pixels of a box give its share with no cloud for each image, in one request
  of less than 1 second for 18 images. With a minimum share of 0.8, 80 of the same 90 events have the two pictures.
  For the 150 chips of the second look, the picture after came 5 days or less after the last detection for 64 chips,
  10 days or less for 113, and 30 days or less for 142. The 422 pictures are 471 MB.
- `UNVERIFIED`: the terms. We believe that Copernicus Sentinel data is free and open with an attribution. Do a check before we publish a picture.

### 8.12 GOES mask and polar-orbit pass times

Checked 2026-11-22 with live requests.

GOES mask:

- Each raw GOES fire file has the variable `Mask`: one class for each pixel. The file gives the name of each of its 45 classes (`flag_meanings`).
- `sources/goes.py` puts the classes in groups: fire (10, 11, 30, 31), possible fire (12 to 15, 32 to 35), no fire (100), cloud (200 to 245),
  no background (170), water (150 to 153), blocked (40, 50, 60) and not processed (all others).
- Checked 2026-11-23 in the GOES-19 file of the scan 2026-11-22 14:00 UTC (`flag_meanings`): 30 is `temporally_filtered_good_fire_pixel`,
  33 is `temporally_filtered_high_probability_fire_pixel`, 100 is `processed_no_fire_pixel`, 170 is `no_background_value_could_be_computed`,
  200 is `cloud_pixel_detected_by_11.19um_threshold_test` and 60 is `SZA_or_glint_angle_block_out_zone`.
- The Pantanal box is 356 rows by 285 columns of the GOES-16 grid.
- In the scan of 2024-08-15 15:00 UTC, 100 741 of the 101 460 pixels of this window had the class "no fire". 162 had a fire class, and 557 were water.
- `chispa fetch goes_mask` reads one scan of each hour and keeps only the mask of the window. One day of January 2024 is approximately 0.2 MB, and takes approximately 25 seconds.
- The file reader (HDF5) is not safe in threads. Only the downloads can run in threads.

Polar-orbit pass times:

- The NASA Common Metadata Repository (CMR) gives each granule of a product for a box and a time range. No key is necessary.
  Request: `https://cmr.earthdata.nasa.gov/search/granules.json` with `short_name`, `bounding_box` and `temporal`.
- A granule has its start time, its end time, a day or night flag and the outline of its swath.
- The fire products are `VNP14IMG` (SNPP), `VJ114IMG` (NOAA-20), `VJ214IMG` (NOAA-21), `MOD14` (Terra) and `MYD14` (Aqua).
- For 2024-08-15 and the Pantanal box: 2, 4, 2, 3 and 3 granules. A VIIRS granule has 6 minutes. A MODIS granule has 5 minutes.
- The start times agree with our detections of that day. Example: SNPP granules start at 05:12 and 17:42, and our SNPP detections are at 05:13 to 05:15 and 17:43 to 17:45.
- For 2026-11-20 the three VIIRS products gave no granule. `MOD14` and `MYD14` gave granules, some of them two times.
- The near-real-time products `VJ114IMG_NRT` and `VJ214IMG_NRT` gave granules for 2026-11-21, changed 2 to 6 hours after the pass. `VNP14IMG_NRT` gave none: SNPP has no live data now (section 8.10).
- A granule says that the satellite passed. It does not say if cloud hid a place. The granule file has a mask for that. It needs an Earthdata login: not checked.
- `chispa fetch passes` saves the granule list of the three VIIRS products for one year: one request for each product. One year of one product has approximately 1400 granules.
- We do not read the MODIS granules, and we do not read the cloud of a pass.

### 8.13 NASA FEDS, a method for fire growth

Read 2026-11-22: Chen et al. 2022, "California wildfire spread derived using VIIRS satellite observations and an
object-based tracking system", Scientific Data. Open copy: Europe PMC, `PMC9151742`. We read parts of the text, not all of it.

- Input: VIIRS active fire pixels of 375 m with nominal or high confidence, at steps of 12 hours.
- At each step the pixels go into groups by distance. A group joins a fire if it is in the outline of that fire plus a buffer:
  5 km for a forest fire, 1 km for other fire types. If not, it starts a new fire. Fires that come near merge.
- The outline of a fire is an alpha shape of all its pixels. The authors compared alpha from 500 m to 10 km with mapped
  perimeters of California and chose 1 km. A large alpha gave too much area. A small alpha cut a large fire into parts.
- A fire stays active if it had a pixel in the last 5 days.
- The fire type comes from the main land cover in the outline. The authors also record a fuel moisture value,
  because prescribed fires had wetter fuel on average than wildfires.
- The active fire line comes from the outline and the new pixels of the step.
- Against the mapped perimeters, precision, recall, overlap and F1 for each fire were between 0.71 and 0.93.
- We use the ideas, not the code: the outline from all pixels with a set distance, and the new pixels as the active part.

### 8.14 Layers for the severity: land cover, protected land, people

Checked 2026-11-22 with live requests to Earth Engine. The same Google login as for the burn scars reads each layer.
`earthengine.py` reads an image in tiles of 512 pixels: one request for the full grid went over the memory limit.
The layer grid has cells of 10 scar pixels (approximately 298 m): 1856 columns and 2598 rows.
The last column and the last row go past the scar grid, thus each scar pixel is in a cell.

Land cover, MapBiomas:

- Asset: `projects/mapbiomas-public/assets/brazil/lulc/collection10/mapbiomas_brazil_collection10_integration_v2`.
  One band for each year from 1985 to 2024: `classification_{year}`. Pixels of 30 m.
- We save the most frequent class of each layer cell. For 2023, that class is the class at the cell centre for 89 percent of the cells.
- 29 percent of the cells of the Pantanal box have no class: they are not in Brazil.
- The class names come from the legend file of MapBiomas for collection 11, read on 2026-11-22:
  `legend_code_mapbiomas_brazil_collection_11.csv` on brasil.mapbiomas.org. We did not find a legend file for collection 10.
  The classes in the box are 3 Forest Formation, 4 Savanna Formation, 6 Floodable Forest, 9 Forest Plantation, 11 Wetland,
  12 Grassland Formation, 15 Pasture, 20 Sugar cane, 21 Mosaic of Uses, 24 Urban Area, 25 Other non Vegetated Areas,
  29 Rocky Outcrop, 30 Mining, 31 Aquaculture, 33 River, Lake and Ocean, 39 Soybean, 40 Rice and 41 Other Temporary Crops.
- The folder also has `collection10_1` and `collection11`. Not examined.

Protected land and indigenous land, World Database on Protected Areas (WDPA):

- Asset: `WCMC/WDPA/current/polygons`. 166 areas touch the Pantanal box. The identifier field is `SITE_ID`, not `WDPAID`.
- The field `DESIG_ENG` gives the designation, and `DESIG_TYPE` says if it is national or international.
- The asset is the current list. It has no list for a past year.

People, Global Human Settlement Layer (GHSL):

- Asset: `JRC/GHSL/P2023A/GHS_POP/2020`: the number of people in each cell of 100 m, in an equal-area projection.
  The asset also has 2025 and 2030: those years are a projection, and we do not use them.
- A cell with no data has the value -200. We use 0 for it. Found 2026-11-23: the mean of cells with -200 gave cells with less than zero people.
- The Pantanal box has 3 507 496 people in this layer, with 0 for the cells with no data. Our grid has 3 473 304.
- A sum of the cells on our grid gave 6 499 476: wrong. Use the mean of the cells, then the area of our cell.

`UNVERIFIED`: the terms of the three layers. Do a check before we publish a copy of a layer.

### 8.15 MapTiler base map

Checked 2026-11-23 (UTC) with requests from this computer and the key of the owner. The dashboard reads the base map. No result uses it.

- The tile sets `satellite-v2`, `terrain-rgb-v2` and `v3`, and the style `outdoor`, answered with status 200.
- `satellite-v2` gives JPEG tiles for zoom 0 to 22. `v3` has the vector layers `water`, `waterway`, `transportation` and `place`, and others.
- The dashboard shows the town names of the `place` layer: OpenStreetMap data. Not checked against a second source.
- UNVERIFIED: the dates of the satellite mosaic for the Pantanal. Thus the page says that the image is not of the as-of time.
- UNVERIFIED: the terms of the free plan for a public page. The map has an attribution control for each tile set.
  From 2026-11-23 a style rule of the owner hides the corner of the map that holds this control: the attribution is not
  on the page. The page is only on the computer of the owner. Show the attribution again before a public page.

### 8.16 Time zone of the Pantanal

Checked 2026-11-23 with the IANA time zone database (Python `zoneinfo`, the copy of this computer).
The dashboard shows Pantanal time. No result uses it.

- The biome is in Mato Grosso do Sul (`America/Campo_Grande`) and Mato Grosso (`America/Cuiaba`).
- Each of the two zones had UTC-4 at each hour from 2020-01-01 to 2026-12-31 (UTC): 61 368 hours with one offset.
- From 2019-01-01, the only change of each zone was on 2019-02-17 at 03:00 UTC: from UTC-3 to UTC-4, the end of summer time.
- The page uses the copy of the database in the browser. A very old browser can have different rules. Not checked.

### 8.17 Sentinel-1 radar, and how frequently Sentinel-2 views a place

Checked 2026-11-23 with live requests to Earth Engine, at three points of the Pantanal box: centre, north and south.
The command `chispa candidates` reads Sentinel-1, as a candidate for the burned ground (`docs/method.md` section 11.16).

- Asset: `COPERNICUS/S1_GRD`. One orbit views the three points: descending, relative orbit 141, mode IW, bands VV and VH.
- Sentinel-1 gives one view each 12 days. 2023 and 2024 had 28 or 29 days with a scene at each point, all from Sentinel-1A.
  The largest time between two views was 24 days in 2023 and 2024, and 36 days in 2025 at two of the points.
- The south point also had Sentinel-1C in 2025. In 2026 each point had two satellites, and still one view each 12 days.
- Sentinel-2 at the centre point: one view each 5 days, and 74, 86 and 77 days with an image in 2024, 2025 and 2026
  (2026 to 16 November). The largest time between two views was 5 days in 2024 and 2026, and 10 days in 2025.
- Thus radar is not quicker than Sentinel-2 at these points. Its possible value is a view through cloud.
- Checked 2026-11-23 with `chispa candidates --year 2023`: 139 of the 624 boxes had no scene before their event or no scene
  after it. Two boxes near longitude -55.7 and -55.1 had no scene in all of 2023: the asset does not have all of the Pantanal box.
- For the 90 events of the 2024 image check, the first image with little cloud (section 8.11) came 5 days or less
  after the last detection for 30 events, 10 days or less for 57, and 30 days or less for 75. A check outside the repository.
- `UNVERIFIED`: the terms of Sentinel-1 data, the time from a scan to its file in Earth Engine, and how well the
  backscatter shows a burn on grass or on wetland.

### 8.18 Candidates for the burned ground

The command `chispa candidates` reads the Monitor do Fogo asset (`docs/method.md` section 11.16). No command reads the other sources.

Checked 2026-11-23 with live requests to Earth Engine:

- MapBiomas Monitor do Fogo: the asset `projects/mapbiomas-public/assets/brazil/fire/monitor/mapbiomas_fire_monthly_burned_v1`
  is a collection of 94 images, one for each month from January 2019 to October 2026. The band is `FireMonth`.
  The properties say collection 2 and source IPAM. The first image has pixels of 30 m. The asset changed last on 2026-11-09.
- Thus a map of the burned ground of a month exists some weeks after that month, also for 2026.
- A first look outside the repository, in the boxes of the 63 chips of 2024 with a clear answer of the person:
  the asset had 1 hectare or more for 22 of the 30 chips that the person called burned, and for 9 of the 33 others.
  For the 44 unmatched HIGH events it had 1 hectare or more for 13.

Read 2026-11-23 by a research agent, on the pages of each owner. `UNVERIFIED`: no second read confirmed these facts.
A web search on 2026-11-24 found the method document of collection 1 of the Monitor map, and no document for the
collection of the asset that we read.

- Monitor do Fogo: the method document of its collection 1 gives monthly Sentinel-2 mosaics, a deep learning model, and
  only the ground not farther than 5 km from an INPE hotspot. Licence CC BY 4.0. Thus it cannot show a fire with no hotspot.
- OlmoEarth (Ai2): an encoder for Sentinel-2 L2A, Sentinel-1 and Landsat. It gives embeddings. The agent found no model,
  weights or benchmark for burned area. A use needs our labels and a head for two dates. The weights have the
  "OlmoEarth Artifact License": it prohibits military and extractive uses. The package `olmoearth-pretrain-minimal`
  has 5 dependencies, with torch. No speed on a laptop is published.
- Prithvi-EO-2.0 (NASA and IBM): weights for burn scars exist, with Apache-2.0. The input is one date of 6 HLS bands at 30 m.
  The training fires are in the United States, from MTBS: fires of approximately 200 hectares or more.
- Sentinel-1: Belenguer-Plomer et al. 2019 (DOI 10.1016/j.rse.2019.111345) give grassland as the worst class for
  backscatter change (Dice 0.28), with errors from soil moisture and floods.
- ALARMES (LASA-UFRJ): burned area from VIIRS each day, at 500 m. The data comes by request.
