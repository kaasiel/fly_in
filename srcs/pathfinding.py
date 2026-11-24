import heapq
from srcs import Graph, ZoneType


def path_turns(graph: Graph, path: list[str]) -> int:
    return sum(graph.zones[z].type.cost for z in path[1:])


def link_cap_check(graph: Graph, path: list[str]) -> int:
    caps = [graph.zones[z].max_drone for z in path[1:-1]]
    for a, b in zip(path, path[1:]):
        caps.append(graph.link(a, b).max_link_capacity)
    return min(caps)


class DijkstraPathfinder:
    def __init__(self) -> None:
        self.path: list[str] = []

    def print_path(self) -> None:
        print(self.path)

    def zonelisting(self, graph: Graph) -> None:
        for e in graph.zones:
            print(e)

    def conneListing(self, graph: Graph) -> None:
        for key, values in graph.neighbors.items():
            print(f"name: {key}, \nvalue: {values}")

    def pathFinder(
            self, graph: Graph, banned: set[str] | None = None
    ) -> list[str] | None:
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
        path = [end]
        while path[-1] != start:
            path.append(previous[path[-1]])
        path.reverse()
        return path

    def find_paths(
            self, graph: Graph, limit: int = 100) -> list[list[str]]:
        if graph.start is None or graph.end is None:
            return []

        heap: list[tuple[int, int, tuple[str, ...]]] = [
            (0, 0, (graph.start,))
        ]
        paths: list[list[str]] = []
        seen: set[tuple[str, ...]] = set()

        while heap and len(paths) < limit:
            turns, prio, path = heapq.heappop(heap)
            name = path[-1]
            if name == graph.end:
                result = list(path)
                if result not in paths:
                    paths.append(result)
                continue

            for conn in graph.neighbors[name]:
                nxt = conn.other(name)
                if nxt in path:
                    continue
                zone = graph.zones[nxt]
                if zone.type is ZoneType.BLOCKED:
                    continue
                new_path = path + (nxt,)
                if new_path in seen:
                    continue
                seen.add(new_path)
                bonus = -1 if zone.type is ZoneType.PRIORITY else 0
                heapq.heappush(
                    heap,
                    (turns + zone.type.cost, prio + bonus, new_path),
                )
        return paths
