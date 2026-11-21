from srcs import Graph, Drone, StateType, ZoneType
from srcs import DijkstraPathfinder, link_cap_check, path_turns


class SimulationError(Exception):
    ...


def assign(graph: Graph, paths: list[list[str]]) -> list[list[str]]:
    turns = [path_turns(graph, p) for p in paths]
    caps = [link_cap_check(graph, p) for p in paths]
    load = [0] * len(paths)
    result: list[list[str]] = []
    for _ in range(graph.nb_drones):
        i = min(range(len(paths)),
                key=lambda k: turns[k] + load[k] // caps[k])
        load[i] += 1
        result.append(paths[i])
    return result


class Simulator:
    def __init__(
            self, graph: Graph, assignement: list[list[str]]) -> None:
        if graph.start is None or graph.end is None:
            raise SimulationError("map has no start or and")
        self.graph = graph
        self.start: str = graph.start
        self.end: str = graph.end
        self.occup: dict[str, int] = {name: 0 for name in graph.zones}
        self.occup[self.start] = graph.nb_drones
        self.drones: list[Drone] = [
            Drone(id=i, position=self.start, path=assignement[i])
            for i in range(graph.nb_drones)
        ]

    def run(self) -> list[str]:
        lines: list[str] = []
        while not all(d.state is StateType.DELIVERED for d in self.drones):
            line = self.play_turn()
            if not line:
                raise SimulationError("Deadlock: no drone can move")
            lines.append(line)
        return lines

    def play_turn(self) -> str:
        gra = self.graph
        moves: list[str] = []
        link_use: dict[frozenset[str], int] = {}
        done: set[int] = set()

        for dro in self.drones:
            if dro.state is StateType.TRANSIT and dro.target is not None:
                key = frozenset((dro.position, dro.target))
                link_use[key] = link_use.get(key, 0) + 1
                dro.position, dro.target = dro.target, None
                dro.step += 1
                dro.state = (StateType.DELIVERED if dro.position == self.end
                             else StateType.AT_ZONE)
                moves.append(f"D{dro.id}-{dro.position}")
                done.add(dro.id)

        in_standby = [dro for dro in self.drones
                      if dro.state is StateType.AT_ZONE and dro.id not in done]
        for dro in sorted(in_standby, key=lambda d: -d.step):
            nxt = dro.path[dro.step + 1]
            zone = gra.zones[nxt]
            key = frozenset((dro.position, nxt))
            link = gra.link(dro.position, nxt)

            if nxt != self.end and self.occup[nxt] >= zone.max_drone:
                continue
            if link_use.get(key, 0) >= link.max_link_capacity:
                continue

            link_use[key] = link_use.get(key, 0) + 1
            self.occup[dro.position] -= 1
            self.occup[nxt] += 1

            if zone.type is ZoneType.RESTRICTED:
                dro.state = StateType.TRANSIT
                dro.target = nxt
                moves.append(f"D{dro.id}-{dro.position}-{nxt}")

            else:
                dro.position = nxt
                dro.step += 1
                if nxt == self.end:
                    dro.state = StateType.DELIVERED
                moves.append(f"D{dro.id}-{nxt}")

        return " ".join(moves)


class Solver:
    def __init__(self) -> None:
        self.finder = DijkstraPathfinder()

    def solve(self, graph: Graph) -> list[str]:
        paths = self.finder.find_paths(graph)
        if not paths:
            raise SimulationError("No path has been found")

        best: list[str] | None = None
        for i in range(1, len(paths) + 1):
            assignement = assign(graph, paths[:i])
            try:
                lines = Simulator(graph, assignement).run()
            except SimulationError:
                continue
            if best is None or len(lines) < len(best):
                best = lines

        if best is None:
            raise SimulationError("No valid simulation has been generated")
        return best
