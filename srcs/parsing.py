from typing import Any
from .model import Graph, ParseError, Connection, build_zone


def parse_zone(line: str) -> dict[str, Any]:
    _, _, data = line.partition(":")
    data, meta = split_metadata(data)
    parts = data.split()
    if len(parts) != 3:
        raise ParseError("Expected 'name <x> <y>")
    if "-" in parts[0]:
        raise ParseError(f"Dash are not allowed in zone '{parts[0]}'")
    return {"name": parts[0], "x": parts[1], "y": parts[2], **meta}


def parse_conn(line: str) -> Connection:
    _, _, data = line.partition(":")
    data, meta = split_metadata(data)
    names = data.strip().split("-")
    if len(names) != 2 or not all(names):
        raise ParseError("Expected '<zone1>-<zone2>'")
    nb = int(meta.get("max_link_capacity", "1"))
    if nb < 1:
        raise ParseError("Max_link_capacity should be greater or equal to 1")
    return Connection(
        zones={f"{names[0]}": names[1]},
        max_link_capacity=nb,
    )


def parse_drone(line: str) -> int:
    try:
        data = int(line)
    except ValueError:
        raise ParseError(
            f"nb_drone should be an integer, got {line.strip()}")
    if data <= 0:
        raise ParseError(
            f"nb_drone should be greater or equal to 1! got {data}")
    return data


class Parser:
    def parse(self, path: str) -> Graph:
        with open(path) as f:
            lines = f.readlines()

        graph: Graph | None = None
        for num, raw in enumerate(lines, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                graph = self._handle(line, graph)
            except ValueError as e:
                raise ParseError(f"Line {num}: {e}")

        if graph is None:
            raise ParseError("empty file")
        if graph.start is None or graph.end is None:
            raise ParseError("missing start_hub or end_hub")
        return graph

    def _handle(self, line: str, graph: Graph | None) -> Graph:
        kind, _, data = line.partition(":")
        if kind == "nb_drones":
            if graph is not None:
                raise ParseError("nb_drones defined twice")
            return Graph(nb_drones=parse_drone(data))
        if graph is None:
            raise ParseError("first line must be nb_drones")

        if kind in ("hub", "start_hub", "end_hub"):
            zone = build_zone(parse_zone(line))
            graph.add_zone(zone)
            if kind == "start_hub":
                if graph.start is not None:
                    raise ParseError("duplicate start_hub")
                graph.start = zone.name
            elif kind == "end_hub":
                if graph.end is not None:
                    raise ParseError("duplicate end_hub")
                graph.end = zone.name
        elif kind == "connection":
            graph.add_connection(parse_conn(line))
        else:
            raise ParseError(f"unknown line type '{kind}'")
        return graph


def split_metadata(data: str) -> tuple[str, dict[str, str]]:
    meta: dict[str, str] = {}
    if "[" not in data:
        return data, meta
    data, _, block = data.partition("[")
    if not block.endswith("]"):
        raise ParseError("missing cosing ']'")
    for pair in block[:-1].split():
        key, sep, value = pair.partition("=")
        if not sep or not value:
            raise ParseError(f"Invalid metadata '{pair}")
        meta[key] = value
    return data, meta
