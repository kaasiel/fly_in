"""Precompute the frames of a drone simulation from its output lines."""
from .model import Graph

Place = tuple[str, str | None]
LinkKey = frozenset[str]


class ReplayError(Exception):
    """Raise when the map or the simulation output cannot be replayed."""


class Replay:
    """Turn the output of a simulation into frames ready to be drawn.

    A frame is the position of every drone after a turn. A position is a
    ``Place``: ``(zone, None)`` when the drone is inside a zone, and
    ``(zone, dest)`` when it is on the link between ``zone`` and ``dest``.

    Attributes:
        frames: One frame per turn. Index 0 is the start, where every
            drone is in the start zone.
        moves_per_turn: Number of moves written on each line.
        occupants: For each frame, the drones inside each zone.
        reserved: For each frame, the number of drones heading to each
            zone.
        link_use: For each frame, the number of drones that used each
            link during the turn.
        waiting: For each frame, the drones that did not move during the
            turn.
        route_of: Route index of each drone. Drones that followed the
            same path share the same index.
    """

    def __init__(self, graph: Graph, lines: list[str]) -> None:
        """Parse the simulation output and build every frame.

        Each token of a line looks like ``D1-zone`` (the drone ends the
        turn in a zone) or ``D1-zoneA-zoneB`` (it is on the link between
        the two zones).

        Args:
            graph: Graph of the map, with a start and an end zone.
            lines: Simulation output, one line of moves per turn.

        Raises:
            ReplayError: If the map has no start or no end, or if a
                token cannot be parsed.
        """
        if graph.start is None or graph.end is None:
            raise ReplayError("map has no start or end")
        self.graph = graph
        self.start: str = graph.start
        self.end: str = graph.end
        self.moves_per_turn = [len(line.split()) for line in lines]

        current: dict[int, Place] = {
            d: (self.start, None) for d in range(graph.nb_drones)
        }
        self.frames: list[dict[int, Place]] = [dict(current)]
        for line in lines:
            for token in line.split():
                ident, *names = token[1:].split("-")
                if len(names) == 1:
                    current[int(ident)] = (names[0], None)
                elif len(names) == 2:
                    current[int(ident)] = (names[0], names[1])
                else:
                    raise ReplayError(f"bad token '{token}'")
            self.frames.append(dict(current))

        self.occupants = [self._occupants(f) for f in self.frames]
        self.reserved = [self._reserved(f) for f in self.frames]
        self.link_use: list[dict[LinkKey, int]] = [{}] + [
            self._link_use(self.frames[k - 1], self.frames[k])
            for k in range(1, len(self.frames))
        ]
        self.waiting = [set[int]()] + [
            self._waiting(self.frames[k - 1], self.frames[k])
            for k in range(1, len(self.frames))
        ]
        self.route_of = self._routes()

    @property
    def turns(self) -> int:
        """Return the number of turns of the simulation."""
        return len(self.frames) - 1

    def delivered(self, k: int) -> int:
        """Return how many drones are in the end zone after turn ``k``."""
        return len(self.occupants[k].get(self.end, []))

    def _occupants(self, frame: dict[int, Place]) -> dict[str, list[int]]:
        """Group by zone name the drones that are inside a zone."""
        res: dict[str, list[int]] = {}
        for ident, (zone, dest) in sorted(frame.items()):
            if dest is None:
                res.setdefault(zone, []).append(ident)
        return res

    def _reserved(self, frame: dict[int, Place]) -> dict[str, int]:
        """Count, for each zone, the drones that are heading to it."""
        res: dict[str, int] = {}
        for _, dest in frame.values():
            if dest is not None:
                res[dest] = res.get(dest, 0) + 1
        return res

    def _link_use(
        self, prev: dict[int, Place], cur: dict[int, Place]
    ) -> dict[LinkKey, int]:
        """Count the drones that moved on each link between two frames.

        A drone that was already on a link finishes on that link. A drone
        that just entered a link uses it. Otherwise it used the link
        between its previous zone and its new zone.
        """
        res: dict[LinkKey, int] = {}
        for ident, new in cur.items():
            old = prev[ident]
            if old == new:
                continue
            if old[1] is not None:
                key = frozenset((old[0], old[1]))
            elif new[1] is not None:
                key = frozenset((new[0], new[1]))
            else:
                key = frozenset((old[0], new[0]))
            res[key] = res.get(key, 0) + 1
        return res

    def _waiting(
        self, prev: dict[int, Place], cur: dict[int, Place]
    ) -> set[int]:
        """Return the drones that did not move, except those at the end."""
        return {
            ident for ident, place in cur.items()
            if place == prev[ident] and place[0] != self.end
        }

    def _routes(self) -> dict[int, int]:
        """Give each drone a route index from the places it went through.

        Drones that visited the same sequence of places share the same
        index, which the visualizer turns into a color.
        """
        visited: dict[int, list[str]] = {d: [] for d in self.frames[0]}
        for frame in self.frames:
            for ident, (zone, dest) in frame.items():
                here = dest if dest is not None else zone
                if not visited[ident] or visited[ident][-1] != here:
                    visited[ident].append(here)
        index: dict[tuple[str, ...], int] = {}
        res: dict[int, int] = {}
        for ident, path in visited.items():
            sig = tuple(path)
            res[ident] = index.setdefault(sig, len(index))
        return res
