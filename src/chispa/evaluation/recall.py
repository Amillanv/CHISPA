"""Recall and delay: which fires does a configuration find, and when does it find them?

A configuration is a subset of the detections: one source, one sensor family, or the merged
alerts of a level. Each configuration gets the same measures, thus the rows are comparable.
"""

import numpy as np

from chispa.evaluation.inputs import size_classes
from chispa.evaluation.match import Fields, Pairs, first_times
from chispa.evaluation.report import percentile, share
from chispa.fusion import LEVELS


def measure(name: str, chosen: np.ndarray, detections: Fields, pairs: Pairs, fires: Fields) -> dict:
    """Return the measures of one configuration: one subset of the detections.

    A delay is the first time of the configuration minus the first time of all detections.
    Only isolated fires give a delay.
    """
    count = len(fires["area_ha"]) - 1
    counted = fires["counted"]
    everything = np.ones(len(chosen), dtype=bool)
    found = np.isfinite(first_times(pairs, chosen, detections["observed"], count)) & counted
    matched = np.zeros(len(chosen), dtype=bool)
    matched[pairs[0]] = True
    timed = found & fires["isolated"]
    row = {
        "configuration": name,
        "detections": int(chosen.sum()),
        "unmatched_detections": int((chosen & ~matched).sum()),
        "unmatched_share": share((chosen & ~matched).sum(), chosen.sum()),
        "fires": int(counted.sum()),
        "fires_found": int(found.sum()),
        "fire_recall": share(found.sum(), counted.sum()),
        "area_recall": share(fires["area_ha"][found].sum(), fires["area_ha"][counted].sum()),
        "delay_fires": int(timed.sum()),
    }
    for time in ("observed", "available"):
        reference = first_times(pairs, everything, detections[time], count)[timed]
        delay_h = (first_times(pairs, chosen, detections[time], count)[timed] - reference) / 3600
        row[f"delay_{time}_h_median"] = percentile(delay_h, 50)
        row[f"delay_{time}_h_p90"] = percentile(delay_h, 90)
    return row


def configurations(detections: Fields) -> Fields:
    """Return each configuration as a selection of detections.

    A merged row selects the detections whose event had that level, or a higher level,
    immediately after the detection. Thus it shows what a brigade could know at that time.
    """
    chosen = {}
    for source in np.unique(detections["source"]):
        chosen[f"source {source}"] = detections["source"] == source
    for family in np.unique(detections["family"]):
        chosen[f"family {family}"] = detections["family"] == family
    rank = np.array([LEVELS.index(level) for level in LEVELS])
    level_rank = np.select([detections["level"] == level for level in LEVELS], rank)
    chosen["merged, level LOW or higher"] = level_rank >= 0
    chosen["merged, level MEDIUM or higher"] = level_rank >= 1
    chosen["merged, level HIGH"] = level_rank >= 2
    return chosen


def size_table(detections: Fields, pairs: Pairs, fires: Fields, chosen: Fields) -> list[dict]:
    """Return the fire recall of each configuration for each fire size class."""
    count = len(fires["area_ha"]) - 1
    rows = []
    for name, selection in chosen.items():
        found = np.isfinite(first_times(pairs, selection, detections["observed"], count))
        for label, in_class in size_classes(fires):
            rows.append(
                {
                    "configuration": name,
                    "size_class_ha": label,
                    "fires": int(in_class.sum()),
                    "fires_found": int((found & in_class).sum()),
                    "fire_recall": share((found & in_class).sum(), in_class.sum()),
                }
            )
    return rows


def gain_table(detections: Fields, pairs: Pairs, fires: Fields) -> list[dict]:
    """Return what the merge adds to each sensor family alone, for each fire size class.

    `fires_gained` are the fires that the merge finds and the family does not find.
    `fires_later` are the isolated fires that the family finds later than the merge,
    by the `available_at` time.
    """
    count = len(fires["area_ha"]) - 1
    merged = first_times(
        pairs, np.ones(len(detections["family"]), dtype=bool), detections["available"], count
    )
    rows = []
    for family in np.unique(detections["family"]):
        alone = first_times(pairs, detections["family"] == family, detections["available"], count)
        for label, in_class in (*size_classes(fires), ("all", fires["counted"])):
            gained = in_class & np.isfinite(merged) & ~np.isfinite(alone)
            timed = in_class & np.isfinite(alone) & fires["isolated"]
            delay_h = (alone[timed] - merged[timed]) / 3600
            rows.append(
                {
                    "sensor_family": family,
                    "size_class_ha": label,
                    "fires_found_merged": int((in_class & np.isfinite(merged)).sum()),
                    "fires_found_family": int((in_class & np.isfinite(alone)).sum()),
                    "fires_gained": int(gained.sum()),
                    "gained_area_ha": round(float(fires["area_ha"][gained].sum())),
                    "delay_fires": int(timed.sum()),
                    "fires_later": int((delay_h > 0).sum()),
                    "later_h_median": percentile(delay_h[delay_h > 0], 50),
                    "later_h_p90": percentile(delay_h[delay_h > 0], 90),
                }
            )
    return rows
