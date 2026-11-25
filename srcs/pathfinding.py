"""Expose pathfinding utilities and the Dijkstra pathfinder."""
import heapq
from srcs import Graph, ZoneType


def path_turns(graph: Graph, path: list[str]) -> int:
    """Return the total movement cost of the path, excluding its start zone."""
    return sum(graph.zones[z].type.cost for z in path[1:])


def link_cap_check(graph: Graph, path: list[str]) -> int:
    """Return the lowest drone capacity along the path's zones and links."""
    caps = [graph.zones[z].max_drone for z in path[1:-1]]
    for a, b in zip(path, path[1:]):
        caps.append(graph.link(a, b).max_link_capacity)
    return min(caps)


class DijkstraPathfinder:
    """Find routes through a graph using Dijkstra-style path ordering."""

    def __init__(self) -> None:
        """Initialize the pathfinder with an empty path."""
        self.path: list[str] = []

    def print_path(self) -> None:
        """Print a found path."""
        print(self.path)

    def zonelisting(self, graph: Graph) -> None:
        """Prinnt the parsed zone."""
        for e in graph.zones:
            print(e)

    def conneListing(self, graph: Graph) -> None:
        """Print the connexions in the graph."""
        for key, values in graph.neighbors.items():
            print(f"name: {key}, \nvalue: {values}")

    def pathFinder(
            self, graph: Graph,
            banned: set[str] | None = None) -> list[str] | None:
        """Return the best route, excluding banned zones, or None if absent."""
        banned = banned or set()
        if graph.start is None or graph.end is None:
            return None

        best: dict[str, tuple[int, int]] = {graph.start: (0, 0)}
        previous: dict[str, str] = {}
        heap: list[tuple[int, int, str]] = [(0, 0, graph.start)]

        while heap:
            turns, prio, name = heapq.heappop(heap)
            if (turns, prio) > best[name]:
                continue
            if name == graph.end:
                return self._rebuild(previous, graph.start, graph.end)

            for conn in graph.neighbors[name]:
                nxt = conn.other(name)
                zone = graph.zones[nxt]
                if zone.type is ZoneType.BLOCKED or nxt in banned:
                    continue
                bonus = -1 if zone.type is ZoneType.PRIORITY else 0
                new = (turns + zone.type.cost, prio + bonus)
                if nxt not in best or new < best[nxt]:
                    best[nxt] = new
                    previous[nxt] = name
                    heapq.heappush(heap, (new[0], new[1], nxt))

        return None

    def _rebuild(
            self,
            previous: dict[str, str], start: str, end: str) -> list[str]:
        """Generate the best path starting from end."""
        path = [end]
        while path[-1] != start:
            path.append(previous[path[-1]])
        path.reverse()
        return path

    def find_paths(
            self, graph: Graph, limit: int = 10) -> list[list[str]]:
        """Return up to ``limit`` routes ordered by cost and priority."""
        if limit <= 0 or graph.start is None or graph.end is None:
            return []

        paths: list[list[str]] = []
        queue: list[tuple[int, int, tuple[str, ...]]] = [
            (0, 0, (graph.start,))
        ]

        while queue and len(paths) < limit:
            turns, priority, path = heapq.heappop(queue)
            current = path[-1]
            if current == graph.end:
                paths.append(list(path))
                continue

            for conn in graph.neighbors[current]:
                nxt = conn.other(current)
                zone = graph.zones[nxt]
                if nxt in path or zone.type is ZoneType.BLOCKED:
                    continue
                next_path = path + (nxt,)
                next_turns = turns + zone.type.cost
                next_priority = priority + (
                    -1 if zone.type is ZoneType.PRIORITY else 0
                )
                heapq.heappush(
                    queue, (next_turns, next_priority, next_path)
                )

        return paths
