# Results

Code makes this file. Do not edit it by hand.

## 2023 (development year)

### configurations

Configuration `e03804b1c89a`, run on 2026-11-21.

| configuration | detections | unmatched_detections | unmatched_share | fires | fires_found | fire_recall | area_recall | delay_fires | delay_observed_h_median | delay_observed_h_p90 | delay_available_h_median | delay_available_h_p90 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| source firms | 382550 | 51586 | 0.1348 | 969 | 743 | 0.7668 | 0.9889 | 117 | 0.0 | 0.51 | 0.0 | 1.73 |
| source inpe | 331133 | 55723 | 0.1683 | 969 | 764 | 0.7884 | 0.9889 | 124 | 0.02 | 5.18 | 0.4 | 6.26 |
| family abi | 375298 | 49258 | 0.1313 | 969 | 760 | 0.7843 | 0.9896 | 116 | 0.0 | 24.35 | 0.0 | 21.85 |
| family avhrr | 13508 | 2432 | 0.18 | 969 | 329 | 0.3395 | 0.9012 | 23 | 48.53 | 215.23 | 51.03 | 217.73 |
| family modis | 31246 | 3554 | 0.1137 | 969 | 567 | 0.5851 | 0.9753 | 70 | 8.7 | 98.53 | 10.43 | 101.03 |
| family viirs | 293631 | 52065 | 0.1773 | 969 | 652 | 0.6729 | 0.9835 | 110 | 0.23 | 24.02 | 2.64 | 25.03 |
| merged, level LOW or higher | 713683 | 107309 | 0.1504 | 969 | 786 | 0.8111 | 0.9908 | 130 | 0.0 | 0.0 | 0.0 | 0.0 |
| merged, level MEDIUM or higher | 700649 | 98621 | 0.1408 | 969 | 768 | 0.7926 | 0.9893 | 120 | 0.17 | 23.32 | 0.17 | 21.98 |
| merged, level HIGH | 657438 | 74103 | 0.1127 | 969 | 724 | 0.7472 | 0.9871 | 105 | 0.52 | 48.79 | 2.68 | 48.79 |

### events

Configuration `e03804b1c89a`, run on 2026-11-21.

| final_level | events | events_matched | matched_share | events_on_counted_fires | events_on_one_fire | fires_per_event_max | purity |
|---|---|---|---|---|---|---|---|
| LOW | 2739 | 619 | 0.226 | 345 | 289 | 7 | 0.8438 |
| MEDIUM | 2072 | 776 | 0.3745 | 405 | 269 | 21 | 0.6886 |
| HIGH | 1079 | 655 | 0.607 | 470 | 232 | 125 | 0.7383 |
| all | 5890 | 2050 | 0.348 | 1220 | 790 | 125 | 0.7378 |

### fire_events

Configuration `e03804b1c89a`, run on 2026-11-21.

| size_class_ha | fires | fires_with_burn_day | fires_isolated | fires_found | fires_in_one_event | events_per_fire_median | events_per_fire_max | completeness |
|---|---|---|---|---|---|---|---|---|
| 10 to 100 | 794 | 223 | 281 | 619 | 242 | 2.0 | 12 | 0.8837 |
| 100 to 1000 | 122 | 106 | 29 | 114 | 28 | 2.0 | 13 | 0.9022 |
| 1000 to 10000 | 44 | 44 | 3 | 44 | 0 | 5.0 | 22 | 0.7883 |
| 10000 to inf | 9 | 9 | 0 | 9 | 0 | 14.0 | 256 | 0.8786 |
| all | 969 | 382 | 313 | 786 | 270 | 2.0 | 256 | 0.8641 |

### fire_sizes

Configuration `e03804b1c89a`, run on 2026-11-21.

| configuration | size_class_ha | fires | fires_found | fire_recall |
|---|---|---|---|---|
| source firms | 10 to 100 | 794 | 577 | 0.7267 |
| source firms | 100 to 1000 | 122 | 113 | 0.9262 |
| source firms | 1000 to 10000 | 44 | 44 | 1.0 |
| source firms | 10000 to inf | 9 | 9 | 1.0 |
| source inpe | 10 to 100 | 794 | 599 | 0.7544 |
| source inpe | 100 to 1000 | 122 | 112 | 0.918 |
| source inpe | 1000 to 10000 | 44 | 44 | 1.0 |
| source inpe | 10000 to inf | 9 | 9 | 1.0 |
| family abi | 10 to 100 | 794 | 593 | 0.7469 |
| family abi | 100 to 1000 | 122 | 114 | 0.9344 |
| family abi | 1000 to 10000 | 44 | 44 | 1.0 |
| family abi | 10000 to inf | 9 | 9 | 1.0 |
| family avhrr | 10 to 100 | 794 | 218 | 0.2746 |
| family avhrr | 100 to 1000 | 122 | 64 | 0.5246 |
| family avhrr | 1000 to 10000 | 44 | 39 | 0.8864 |
| family avhrr | 10000 to inf | 9 | 8 | 0.8889 |
| family modis | 10 to 100 | 794 | 411 | 0.5176 |
| family modis | 100 to 1000 | 122 | 104 | 0.8525 |
| family modis | 1000 to 10000 | 44 | 43 | 0.9773 |
| family modis | 10000 to inf | 9 | 9 | 1.0 |
| family viirs | 10 to 100 | 794 | 491 | 0.6184 |
| family viirs | 100 to 1000 | 122 | 108 | 0.8852 |
| family viirs | 1000 to 10000 | 44 | 44 | 1.0 |
| family viirs | 10000 to inf | 9 | 9 | 1.0 |
| merged, level LOW or higher | 10 to 100 | 794 | 619 | 0.7796 |
| merged, level LOW or higher | 100 to 1000 | 122 | 114 | 0.9344 |
| merged, level LOW or higher | 1000 to 10000 | 44 | 44 | 1.0 |
| merged, level LOW or higher | 10000 to inf | 9 | 9 | 1.0 |
| merged, level MEDIUM or higher | 10 to 100 | 794 | 602 | 0.7582 |
| merged, level MEDIUM or higher | 100 to 1000 | 122 | 113 | 0.9262 |
| merged, level MEDIUM or higher | 1000 to 10000 | 44 | 44 | 1.0 |
| merged, level MEDIUM or higher | 10000 to inf | 9 | 9 | 1.0 |
| merged, level HIGH | 10 to 100 | 794 | 559 | 0.704 |
| merged, level HIGH | 100 to 1000 | 122 | 112 | 0.918 |
| merged, level HIGH | 1000 to 10000 | 44 | 44 | 1.0 |
| merged, level HIGH | 10000 to inf | 9 | 9 | 1.0 |

## 2024 (test year)

### configurations

Configuration `e03804b1c89a`, run on 2026-11-21.

| configuration | detections | unmatched_detections | unmatched_share | fires | fires_found | fire_recall | area_recall | delay_fires | delay_observed_h_median | delay_observed_h_p90 | delay_available_h_median | delay_available_h_p90 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| source firms | 769925 | 28975 | 0.0376 | 4246 | 2187 | 0.5151 | 0.96 | 124 | 0.0 | 19.95 | 0.0 | 21.18 |
| source inpe | 602588 | 27127 | 0.045 | 4246 | 2431 | 0.5725 | 0.9682 | 141 | 0.0 | 1.92 | 0.0 | 4.08 |
| source noaa | 101481 | 1360 | 0.0134 | 4246 | 778 | 0.1832 | 0.5126 | 36 | 0.0 | 86.33 | 0.0 | 83.83 |
| family abi | 609914 | 19363 | 0.0317 | 4246 | 2668 | 0.6284 | 0.9736 | 140 | 0.0 | 40.9 | 0.0 | 38.4 |
| family avhrr | 25753 | 1413 | 0.0549 | 4246 | 1034 | 0.2435 | 0.9061 | 35 | 8.62 | 118.65 | 9.65 | 121.15 |
| family modis | 63544 | 2309 | 0.0363 | 4246 | 1443 | 0.3398 | 0.927 | 64 | 3.91 | 86.58 | 5.93 | 87.0 |
| family viirs | 774783 | 34377 | 0.0444 | 4246 | 1564 | 0.3683 | 0.9407 | 101 | 0.0 | 19.45 | 0.92 | 21.95 |
| merged, level LOW or higher | 1473994 | 57462 | 0.039 | 4246 | 2864 | 0.6745 | 0.9771 | 173 | 0.0 | 0.0 | 0.0 | 0.0 |
| merged, level MEDIUM or higher | 1459439 | 52150 | 0.0357 | 4246 | 2654 | 0.6251 | 0.9724 | 137 | 0.17 | 23.26 | 0.17 | 23.4 |
| merged, level HIGH | 1423724 | 42735 | 0.03 | 4246 | 2287 | 0.5386 | 0.9591 | 93 | 0.67 | 70.36 | 2.8 | 70.5 |

### events

Configuration `e03804b1c89a`, run on 2026-11-21.

| final_level | events | events_matched | matched_share | events_on_counted_fires | events_on_one_fire | fires_per_event_max | purity |
|---|---|---|---|---|---|---|---|
| LOW | 2914 | 1511 | 0.5185 | 953 | 649 | 22 | 0.6798 |
| MEDIUM | 1764 | 1093 | 0.6196 | 734 | 405 | 38 | 0.5059 |
| HIGH | 1582 | 1273 | 0.8047 | 1062 | 379 | 170 | 0.7877 |
| all | 6260 | 3877 | 0.6193 | 2749 | 1433 | 170 | 0.7853 |

### fire_events

Configuration `e03804b1c89a`, run on 2026-11-21.

| size_class_ha | fires | fires_with_burn_day | fires_isolated | fires_found | fires_in_one_event | events_per_fire_median | events_per_fire_max | completeness |
|---|---|---|---|---|---|---|---|---|
| 10 to 100 | 3657 | 310 | 1446 | 2355 | 995 | 2.0 | 14 | 0.8265 |
| 100 to 1000 | 462 | 188 | 102 | 383 | 104 | 3.0 | 68 | 0.7728 |
| 1000 to 10000 | 102 | 86 | 7 | 101 | 5 | 5.0 | 30 | 0.7579 |
| 10000 to inf | 25 | 25 | 0 | 25 | 0 | 24.0 | 191 | 0.6868 |
| all | 4246 | 609 | 1555 | 2864 | 1104 | 2.0 | 191 | 0.7229 |

### fire_sizes

Configuration `e03804b1c89a`, run on 2026-11-21.

| configuration | size_class_ha | fires | fires_found | fire_recall |
|---|---|---|---|---|
| source firms | 10 to 100 | 3657 | 1746 | 0.4774 |
| source firms | 100 to 1000 | 462 | 316 | 0.684 |
| source firms | 1000 to 10000 | 102 | 100 | 0.9804 |
| source firms | 10000 to inf | 25 | 25 | 1.0 |
| source inpe | 10 to 100 | 3657 | 1952 | 0.5338 |
| source inpe | 100 to 1000 | 462 | 353 | 0.7641 |
| source inpe | 1000 to 10000 | 102 | 101 | 0.9902 |
| source inpe | 10000 to inf | 25 | 25 | 1.0 |
| source noaa | 10 to 100 | 3657 | 634 | 0.1734 |
| source noaa | 100 to 1000 | 462 | 103 | 0.2229 |
| source noaa | 1000 to 10000 | 102 | 28 | 0.2745 |
| source noaa | 10000 to inf | 25 | 13 | 0.52 |
| family abi | 10 to 100 | 3657 | 2165 | 0.592 |
| family abi | 100 to 1000 | 462 | 378 | 0.8182 |
| family abi | 1000 to 10000 | 102 | 100 | 0.9804 |
| family abi | 10000 to inf | 25 | 25 | 1.0 |
| family avhrr | 10 to 100 | 3657 | 739 | 0.2021 |
| family avhrr | 100 to 1000 | 462 | 184 | 0.3983 |
| family avhrr | 1000 to 10000 | 102 | 86 | 0.8431 |
| family avhrr | 10000 to inf | 25 | 25 | 1.0 |
| family modis | 10 to 100 | 3657 | 1087 | 0.2972 |
| family modis | 100 to 1000 | 462 | 239 | 0.5173 |
| family modis | 1000 to 10000 | 102 | 92 | 0.902 |
| family modis | 10000 to inf | 25 | 25 | 1.0 |
| family viirs | 10 to 100 | 3657 | 1181 | 0.3229 |
| family viirs | 100 to 1000 | 462 | 260 | 0.5628 |
| family viirs | 1000 to 10000 | 102 | 98 | 0.9608 |
| family viirs | 10000 to inf | 25 | 25 | 1.0 |
| merged, level LOW or higher | 10 to 100 | 3657 | 2355 | 0.644 |
| merged, level LOW or higher | 100 to 1000 | 462 | 383 | 0.829 |
| merged, level LOW or higher | 1000 to 10000 | 102 | 101 | 0.9902 |
| merged, level LOW or higher | 10000 to inf | 25 | 25 | 1.0 |
| merged, level MEDIUM or higher | 10 to 100 | 3657 | 2160 | 0.5906 |
| merged, level MEDIUM or higher | 100 to 1000 | 462 | 368 | 0.7965 |
| merged, level MEDIUM or higher | 1000 to 10000 | 102 | 101 | 0.9902 |
| merged, level MEDIUM or higher | 10000 to inf | 25 | 25 | 1.0 |
| merged, level HIGH | 10 to 100 | 3657 | 1827 | 0.4996 |
| merged, level HIGH | 100 to 1000 | 462 | 337 | 0.7294 |
| merged, level HIGH | 1000 to 10000 | 102 | 98 | 0.9608 |
| merged, level HIGH | 10000 to inf | 25 | 25 | 1.0 |

Limits of these results:

- The sources are satellites only. There are no camera detections or community reports.
- A fire is a group of burned cells that touch and burned in near days (`docs/method.md`).
- The burn day of a fire is uncertain by some days. A fire with no burn day has only a month.
- The MODIS orbits drift. The effect on the burn days of late 2024 is not published.
- A delay is relative to the first detection from all sources, not to the start of the fire.
- Only isolated fires give a delay. `delay_fires` is their number. It is a small sample.
- The precision against the map is 1 minus the unmatched share. It is a lower limit:
  an unmatched detection is not always a false alarm. The fire can be too small for the map.
- A fire that burned for many days matches the detections of all those days.
- GOES has no low-probability detections, and has holes in late September to November 2024.
- The availability delay of each sensor family is an estimate in `config.py`.
- Smoke level is not in these tables yet.
- A fire in January can have detections in December of the year before. We do not count those.
