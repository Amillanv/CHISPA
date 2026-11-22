"""The evaluation: compare detections and alerts with the mapped fires.

Each module answers one question. `match.py`: which detection belongs to which fire?
`recall.py`: which fires does a configuration find, and when? `events.py`: is one event one fire,
and what does a level mean? `run.py` makes all the tables. `report.py` writes them.
The fusion never imports this package.
"""
