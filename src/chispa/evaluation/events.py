"""Events against fires: is one event one fire, and what does a confidence level mean?

The fusion can merge two fires into one event, and it can split one fire into many events.
These tables measure the two errors, and the share of events of each level that match a fire.
"""

import numpy as np

from chispa.evaluation.inputs import size_classes
from chispa.evaluation.match import Fields, Pairs
from chispa.evaluation.report import percentile, share
from chispa.fusion import LEVELS


def _links(detections: Fields, pairs: Pairs, fires: Fields) -> tuple[np.ndarray, ...]:
    """Return each different (event, counted fire) that a match connects, as three arrays:
    the event, the fire, and the number of matches between the two."""
    counted = fires["counted"][pairs[1]]
    both = np.stack([detections["event"][pairs[0][counted]], pairs[1][counted]])
    (events, numbers), matches = np.unique(both, axis=1, return_counts=True)
    return events, numbers, matches


def _main_share(group: np.ndarray, matches: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return, for each group number, all its matches and the matches of its largest link."""
    total = np.bincount(group, weights=matches)
    main = np.zeros(len(total))
    np.maximum.at(main, group, matches)
    return total, main


def events_with_a_match(detections: Fields, pairs: Pairs) -> set[int]:
    """Return each event that has a minimum of one detection that matches a fire."""
    matched = np.zeros(len(detections["event"]), dtype=bool)
    matched[pairs[0]] = True
    return set(np.unique(detections["event"][matched]).tolist())


def event_table(detections: Fields, pairs: Pairs, fires: Fields, final_level: dict) -> list[dict]:
    """Return, for each final level, how many events match a fire and how many fires.

    `matched_share` is the precision against the map. `purity` is the share of the matches
    of an event that are on its main fire. A low purity shows that the fusion merged fires.
    """
    matched_events = events_with_a_match(detections, pairs)
    link_event, _, matches = _links(detections, pairs, fires)
    on_fires, position = np.unique(link_event, return_inverse=True)
    total, main = _main_share(position, matches)
    fires_of = np.bincount(position)
    rows = []
    for level in (*LEVELS, "all"):
        of_level = [level == "all" or final_level[event] == level for event in on_fires.tolist()]
        events = [
            event
            for event in np.unique(detections["event"]).tolist()
            if level == "all" or final_level[event] == level
        ]
        hits = sum(event in matched_events for event in events)
        rows.append(
            {
                "final_level": level,
                "events": len(events),
                "events_matched": hits,
                "matched_share": share(hits, len(events)),
                "events_on_counted_fires": sum(of_level),
                "events_on_one_fire": int((fires_of[of_level] == 1).sum()),
                "fires_per_event_max": int(fires_of[of_level].max()) if any(of_level) else None,
                "purity": share(main[of_level].sum(), total[of_level].sum()),
            }
        )
    return rows


def split_table(detections: Fields, pairs: Pairs, fires: Fields) -> list[dict]:
    """Return, for each fire size class, into how many events the fusion split a fire.

    `completeness` is the share of the matches of a fire that are in its main event.
    """
    _, link_fire, matches = _links(detections, pairs, fires)
    count = len(fires["area_ha"])
    events_of = np.bincount(link_fire, minlength=count)
    total, main = (
        np.pad(values, (0, count - len(values))) for values in _main_share(link_fire, matches)
    )
    rows = []
    for label, in_class in (*size_classes(fires), ("all", fires["counted"])):
        found = in_class & (events_of > 0)
        rows.append(
            {
                "size_class_ha": label,
                "fires": int(in_class.sum()),
                "fires_with_burn_day": int((in_class & (fires["first_day"] > 0)).sum()),
                "fires_isolated": int((in_class & fires["isolated"]).sum()),
                "fires_found": int(found.sum()),
                "fires_in_one_event": int((events_of[found] == 1).sum()),
                "events_per_fire_median": percentile(events_of[found], 50),
                "events_per_fire_max": int(events_of[found].max()) if found.any() else None,
                "completeness": share(main[found].sum(), total[found].sum()),
            }
        )
    return rows
