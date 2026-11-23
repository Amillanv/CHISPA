"""The events as they were at a time, not as they are at the end.

The fusion merges two events when a detection connects them. After a merge, the store shows
one event. But a brigade got two alerts before the merge. To say what an alert was at a time,
or to give the correct result for an alert, we must undo the merges that came later.
The fusion saves the alert that each detection joined at its time (the issued id), and each
merge with its time. This module puts them together for one moment.
"""

from dataclasses import dataclass, field


@dataclass
class Replay:
    """The groups of issued ids at a moment. The moment can only go forward.

    `merges` has (time, the id that stops, the id that continues) for each merge.
    """

    merges: list[tuple[float, int, int]]
    parent: dict[int, int] = field(default_factory=dict)
    members: dict[int, list[int]] = field(default_factory=dict)
    done: int = 0

    def __post_init__(self) -> None:
        self.merges = sorted(self.merges)

    def advance(self, time: float) -> None:
        """Do each merge with a time at or before this time."""
        while self.done < len(self.merges) and self.merges[self.done][0] <= time:
            _, absorbed, into = self.merges[self.done]
            stops, continues = self.root(absorbed), self.root(into)
            if stops != continues:
                self.parent[stops] = continues
                self.members[continues] = self.ids(continues) + self.members.pop(stops, [stops])
            self.done += 1

    def root(self, issued: int) -> int:
        """Return the id of the event that holds this issued id at the moment."""
        while issued in self.parent:
            issued = self.parent[issued]
        return issued

    def ids(self, issued: int) -> list[int]:
        """Return each issued id that is in the same event at the moment."""
        root = self.root(issued)
        return self.members.get(root, [root])
