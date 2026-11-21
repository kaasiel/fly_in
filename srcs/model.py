from enum import Enum
from pydantic import BaseModel, Field


class ParseError(ValueError):
    ...


class ZoneType(Enum):
    NORMAL = "normal"
    BLOCKED = "blocked"
    RESTRICTED = "restricted"
    PRIORITY = "priority"

    @property
    def cost(self) -> int:
        if self is ZoneType.RESTRICTED:
            return 2
        return 1


class StateType(Enum):
    AT_ZONE = "at_zone"
    TRANSIT = "in_transit"
    DELIVERED = "delivered"


class Zone(BaseModel):
    name: str
    coordinate: tuple[int, int]
    type: ZoneType
    color: str | None = None
    max_drone: int


class Connection(BaseModel):
    zones: dict[str, str]
    max_link_capacity: int = Field(default=1, gt=0)

    @property
    def ends(self) -> tuple[str, str]:
        a, b = next(iter(self.zones.items()))
        return a, b

    def other(self, name: str) -> str:
        a, b = self.ends
        return b if name == a else a


class Graph(BaseModel):
    nb_drones: int = Field()
    start: str | None = None
    end: str | None = None
    zones: dict[str, Zone] = {}
    neighbors: dict[str, list[Connection]] = {}

    def add_zone(self, zone: Zone) -> None:
        if zone.name in self.zones:
            raise ParseError(f"duplicate zone name '{zone.name}'")
        self.zones[zone.name] = zone
        self.neighbors[zone.name] = []

    def add_connection(self, conn: Connection) -> None:
        a, b = conn.ends
        for name in (a, b):
            if name not in self.zones:
                raise ParseError(f"unknown zone '{name}'")
        if a == b:
            raise ParseError(f"zone '{a}' linked to itself")
        for other in self.neighbors[a]:
            if set(other.ends) == {a, b}:
                raise ParseError(f"duplicate connection {a}-{b}")
        self.neighbors[a].append(conn)
        self.neighbors[b].append(conn)

    def link(self, a: str, b: str) -> Connection:
        for conn in self.neighbors[a]:
            if conn.other(a) == b:
                return conn
        raise ValueError(f"no link {a}-{b}")


class Drone(BaseModel):
    id: int
    position: str
    state: StateType = StateType.AT_ZONE
    target: str | None = None
    path: list[str] = []
    step: int = 0


def build_zone(raw: dict[str, str]) -> Zone:
    max = int(raw.get("max_drones", "1"))
    if max < 1:
        raise ParseError("Max_drone should be greater or equal than 1!")
    return Zone(
        name=raw['name'],
        coordinate=(int(raw['x']), int(raw['y'])),
        type=ZoneType(raw.get("zone", "normal")),
        color=raw.get('color'),
        max_drone=max,
        )
