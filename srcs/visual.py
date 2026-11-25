"""Interactive pyray visualizer that replays a Fly-in simulation."""
import math
import pyray as rl
from .model import Connection, Graph, ZoneType
from .replay import Place, Replay

Rgb = tuple[int, int, int]

NAMED: dict[str, Rgb] = {
    "red": (217, 74, 58), "green": (47, 143, 78), "blue": (59, 125, 216),
    "yellow": (232, 193, 58), "orange": (224, 138, 44),
    "purple": (122, 90, 214), "violet": (122, 90, 214),
    "gray": (110, 115, 130), "grey": (110, 115, 130),
    "black": (40, 42, 50), "brown": (139, 90, 60),
    "maroon": (128, 32, 48), "gold": (212, 175, 55),
    "darkred": (139, 26, 26), "crimson": (220, 20, 60),
    "cyan": (0, 188, 212), "pink": (236, 111, 160),
    "white": (235, 235, 240),
}
LEGEND: list[tuple[str, str]] = [
    ("normal", "normal"), ("priority", "priority"),
    ("restricted", "restricted"), ("blocked", "blocked"),
    ("waiting", "waiting"), ("inside", "in zone"),
    ("reserved", "reserved"), ("free", "free"),
    ("link_free", "link free"), ("link_part", "link used"),
    ("link_full", "link full"),
]

LEGEND_FONT = 14
LEGEND_ROW = 26
ROUTES: list[Rgb] = [
    (43, 179, 160), (232, 113, 74), (150, 130, 230), (232, 193, 58),
    (90, 170, 235), (236, 111, 160), (140, 200, 90), (200, 200, 210),
]
BG = rl.Color(20, 22, 30, 255)
HUD_BG = rl.Color(30, 33, 48, 255)
TEXT = rl.Color(230, 232, 240, 255)
MUTED = rl.Color(154, 160, 181, 255)
LINK_FREE = rl.Color(91, 98, 122, 255)
LINK_PART = rl.Color(232, 163, 58, 255)
LINK_FULL = rl.Color(229, 83, 75, 255)
HUD_HEIGHT = 44
TEAL = rl.Color(43, 179, 160, 255)
GOLD = rl.Color(232, 193, 58, 255)
BTN_Y = 4
BTN_H = 26
BTN_GAP = 6
SCRUB_H = 5
SCRUB_HIT = 12
BUTTONS: list[tuple[str, int, str]] = [
    ("replay", 92, "Replay from the start (R)"),
    ("prev", 34, "Previous turn (Left)"),
    ("toggle", 34, "Play / pause (Space)"),
    ("next", 34, "Next turn (Right)"),
    ("slower", 34, "Slower (Down)"),
    ("faster", 34, "Faster (Up)"),
]


def rgb(color: Rgb, alpha: int = 255) -> rl.Color:
    """Convert an RGB tuple and an alpha value to a raylib color."""
    return rl.Color(color[0], color[1], color[2], alpha)


def zone_color(name: str | None) -> rl.Color:
    """Return the display color for a zone color name.

    The special name ``rainbow`` cycles through hues over time. Unknown or
    missing names fall back to grey.
    """
    if name == "rainbow":
        return rl.color_from_hsv((rl.get_time() * 60) % 360, 0.65, 0.9)
    return rgb(NAMED.get(name or "", (110, 115, 130)))


def lerp(a: rl.Vector2, b: rl.Vector2, t: float) -> rl.Vector2:
    """Return the point at fraction ``t`` of the segment ``a`` to ``b``."""
    return rl.Vector2(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t)


class View:
    """Convert graph coordinates to screen pixels, with zoom and pan."""

    def __init__(self, graph: Graph, width: int, height: int) -> None:
        """Fit the graph in the window and reset zoom and pan.

        Args:
            graph: Graph whose zone coordinates are projected.
            width: Window width in pixels.
            height: Window height in pixels.
        """
        xs = [z.coordinate[0] for z in graph.zones.values()]
        ys = [z.coordinate[1] for z in graph.zones.values()]
        margin = 70
        self.graph = graph
        self.min_x, self.min_y = min(xs), min(ys)
        span_x = max(max(xs) - self.min_x, 1)
        span_y = max(max(ys) - self.min_y, 1)
        top = HUD_HEIGHT + margin
        self.scale = min((width - 2 * margin) / span_x,
                         (height - top - margin) / span_y)
        self.left = margin
        self.top = top
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0

    def point(self, zone: str) -> rl.Vector2:
        """Return the screen position of a zone, zoom and pan included."""
        x, y = self.graph.zones[zone].coordinate
        return rl.Vector2(
            self.left + (x - self.min_x) * self.scale * self.zoom
            + self.pan_x,
            self.top + (y - self.min_y) * self.scale * self.zoom
            + self.pan_y,
        )

    def radius(self, zone: str) -> float:
        """Return the drawn radius of a zone, in pixels.

        Start and end zones are 1.5 times larger. Other zones grow with the
        zoom, up to twice their base size.
        """
        base = max(9.0, min(20.0, self.scale * 0.32))
        if zone in (self.graph.start, self.graph.end):
            return base * 1.5
        return base * min(self.zoom, 2.0)


class Renderer:
    """Draw the graph, the drones and the interface of one frame."""

    def __init__(self, graph: Graph, replay: Replay, view: View) -> None:
        """Store what has to be drawn and list each link only once.

        Args:
            graph: Graph to draw.
            replay: Precomputed frames of the simulation.
            view: Converter from graph coordinates to pixels.
        """
        self.graph = graph
        self.replay = replay
        self.view = view
        self.links: list[Connection] = []
        seen: set[frozenset[str]] = set()
        for conns in graph.neighbors.values():
            for conn in conns:
                key = frozenset(conn.ends)
                if key not in seen:
                    seen.add(key)
                    self.links.append(conn)

    def draw_links(self, turn: int) -> None:
        """Draw every link, colored by its usage at the given turn.

        Grey means unused, orange partly used and red full. A thicker line
        means a higher link capacity.
        """
        usage = self.replay.link_use[turn]
        for conn in self.links:
            a, b = conn.ends
            used = usage.get(frozenset(conn.ends), 0)
            cap = conn.max_link_capacity
            color = LINK_FREE
            if used >= cap:
                color = LINK_FULL
            elif used > 0:
                color = LINK_PART
            width = 2.0 + 2.0 * min(cap - 1, 3)
            rl.draw_line_ex(self.view.point(a), self.view.point(b),
                            width, color)

    def draw_zone(self, name: str, turn: int,
                  selected: str | None = None) -> None:
        """Draw one zone with the shape and color of its type.

        Blocked zones are crossed dark circles, restricted zones are squares,
        priority zones have a gold ring and start/end zones a white ring.

        Args:
            name: Zone name.
            turn: Turn used for the occupancy indicators.
            selected: Name of the selected zone, which gets a highlight.
        """
        zone = self.graph.zones[name]
        p = self.view.point(name)
        r = self.view.radius(name)
        color = zone_color(zone.color)
        special = name in (self.graph.start, self.graph.end)
        if name == selected:
            rl.draw_circle_v(p, r + 7, rl.Color(255, 211, 105, 255))
        if zone.type is ZoneType.BLOCKED:
            rl.draw_circle_v(p, r, rl.Color(42, 44, 53, 255))
            d = r * 0.5
            rl.draw_line_ex(rl.Vector2(p.x - d, p.y - d),
                            rl.Vector2(p.x + d, p.y + d), 2, MUTED)
            rl.draw_line_ex(rl.Vector2(p.x + d, p.y - d),
                            rl.Vector2(p.x - d, p.y + d), 2, MUTED)
            return
        if zone.type is ZoneType.RESTRICTED:
            outer = rl.Rectangle(p.x - r - 3, p.y - r - 3,
                                 2 * r + 6, 2 * r + 6)
            inner = rl.Rectangle(p.x - r, p.y - r, 2 * r, 2 * r)
            rl.draw_rectangle_rounded(outer, 0.25, 6,
                                      rl.Color(255, 107, 107, 255))
            rl.draw_rectangle_rounded(inner, 0.25, 6, color)
        else:
            ring = rl.Color(232, 193, 58, 255)
            if zone.type is not ZoneType.PRIORITY:
                ring = rl.Color(255, 255, 255, 255) if special else BG
            rl.draw_circle_v(p, r + 3, ring)
            rl.draw_circle_v(p, r, color)
        self.draw_pips(name, turn, p, r)

    def draw_pips(self, name: str, turn: int, p: rl.Vector2,
                  r: float) -> None:
        """Draw the occupancy indicators under a zone.

        Start and end zones show a counter. Other zones show one pip per
        capacity slot (8 at most): filled if occupied, orange outline if
        reserved and grey outline if free.
        """
        if name in (self.graph.start, self.graph.end):
            count = len(self.replay.occupants[turn].get(name, []))
            label = f"{count}"
            width = rl.measure_text(label, 16)
            rl.draw_text(label, int(p.x - width / 2), int(p.y + r + 6),
                         16, MUTED)
            return
        cap = min(self.graph.zones[name].max_drone, 8)
        count = len(self.replay.occupants[turn].get(name, []))
        reserved = self.replay.reserved[turn].get(name, 0)
        x0 = p.x - (cap - 1) * 4.5
        y = p.y + r + 10
        for i in range(cap):
            c = rl.Vector2(x0 + i * 9, y)
            if i < count:
                rl.draw_circle_v(c, 3.5, TEXT)
            elif i < count + reserved:
                rl.draw_circle_lines(int(c.x), int(c.y), 4, LINK_PART)
            else:
                rl.draw_circle_lines(int(c.x), int(c.y), 3, MUTED)

    def anchor(self, frame: int, ident: int) -> rl.Vector2:
        """Return where a drone is drawn in a given frame.

        A drone in transit sits in the middle of its link. A drone in a zone
        sits at the zone center, or on a small circle around it when several
        drones share the zone.
        """
        zone, dest = self.replay.frames[frame][ident]
        if dest is not None:
            return lerp(self.view.point(zone), self.view.point(dest), 0.5)
        p = self.view.point(zone)
        people = self.replay.occupants[frame][zone]
        if len(people) == 1:
            return p
        angle = 2 * math.pi * people.index(ident) / len(people)
        off = self.view.radius(zone) * 0.55
        return rl.Vector2(p.x + math.cos(angle) * off,
                          p.y + math.sin(angle) * off)

    def stacked(self, frame: int, ident: int) -> bool:
        """Return whether a drone is hidden in a crowded start or end zone.

        With more than 6 drones in the start or end zone, the idle ones are not
        drawn and the counter under the zone shows the total.
        """
        zone, dest = self.replay.frames[frame][ident]
        if dest is not None or zone not in (self.replay.start,
                                            self.replay.end):
            return False
        return len(self.replay.occupants[frame][zone]) > 6

    def draw_drone(self, turn: int, progress: float, ident: int) -> None:
        """Draw one drone, moving between two consecutive turns.

        The position goes from the frame ``turn`` to the next one, eased with a
        smoothstep of ``progress``. Waiting drones get a grey ring, the others
        take the color of their route.
        """
        nxt = min(turn + 1, self.replay.turns)
        here: Place = self.replay.frames[turn][ident]
        there: Place = self.replay.frames[nxt][ident]
        if here == there and self.stacked(turn, ident):
            return
        t = progress * progress * (3 - 2 * progress)
        pos = lerp(self.anchor(turn, ident), self.anchor(nxt, ident), t)
        route = ROUTES[self.replay.route_of[ident] % len(ROUTES)]
        waiting = ident in self.replay.waiting[turn]
        if waiting:
            rl.draw_circle_v(pos, 11, rl.Color(138, 147, 173, 255))
            rl.draw_circle_v(pos, 9, rl.Color(42, 48, 64, 255))
            text_color = TEXT
        else:
            rl.draw_circle_v(pos, 10, rgb(route))
            text_color = rl.Color(13, 15, 22, 255)
        label = f"{ident}"
        width = rl.measure_text(label, 12)
        rl.draw_text(label, int(pos.x - width / 2), int(pos.y - 6),
                     12, text_color)

    def hud_buttons(
        self, width: int
    ) -> list[tuple[str, rl.Rectangle, str]]:
        """Return the HUD buttons, right-aligned.

        Each item is a tuple (name, rectangle, tooltip).
        """
        gaps = BTN_GAP * (len(BUTTONS) - 1)
        total = sum(w for _, w, _ in BUTTONS) + gaps
        x = float(width - 16 - total)
        res: list[tuple[str, rl.Rectangle, str]] = []
        for name, w, tip in BUTTONS:
            res.append((name, rl.Rectangle(x, BTN_Y, w, BTN_H), tip))
            x += w + BTN_GAP
        return res

    def button_at(self, mouse: rl.Vector2, width: int) -> str | None:
        """Return the name of the HUD button under ``mouse``, or None."""
        for name, rect, _ in self.hud_buttons(width):
            if rl.check_collision_point_rec(mouse, rect):
                return name
        return None

    def scrub_rect(self, width: int) -> rl.Rectangle:
        """Return the clickable area of the progress bar."""
        return rl.Rectangle(0, HUD_HEIGHT - SCRUB_HIT, width, SCRUB_HIT)

    def button_enabled(self, name: str, turn: int, speed: float) -> bool:
        """Return whether a HUD button is usable in this state."""
        if name == "prev":
            return turn > 0
        if name == "next":
            return turn < self.replay.turns
        if name == "slower":
            return speed > 0.5
        if name == "faster":
            return speed < 8.0
        return True

    def draw_icon(self, name: str, cx: float, cy: float, ink: rl.Color,
                  playing: bool) -> None:
        """Draw the icon or label of a HUD button centered on (cx, cy)."""
        if name == "replay":
            w = rl.measure_text("Replay", 16)
            rl.draw_text("Replay", int(cx - w / 2), int(cy - 8), 16, ink)
        elif name == "prev":
            rl.draw_triangle(rl.Vector2(cx + 5, cy - 7),
                             rl.Vector2(cx - 6, cy),
                             rl.Vector2(cx + 5, cy + 7), ink)
        elif name == "next" or (name == "toggle" and not playing):
            rl.draw_triangle(rl.Vector2(cx - 5, cy - 7),
                             rl.Vector2(cx - 5, cy + 7),
                             rl.Vector2(cx + 6, cy), ink)
        elif name == "toggle":
            rl.draw_rectangle(int(cx - 6), int(cy - 7), 4, 14, ink)
            rl.draw_rectangle(int(cx + 2), int(cy - 7), 4, 14, ink)
        else:
            rl.draw_rectangle(int(cx - 6), int(cy - 1), 12, 3, ink)
            if name == "faster":
                rl.draw_rectangle(int(cx - 1), int(cy - 6), 3, 13, ink)

    def draw_hud_button(self, name: str, rect: rl.Rectangle, enabled: bool,
                        playing: bool, glow: bool) -> None:
        """Draw one HUD button with its hover, pressed and glow states.

        ``glow`` makes the button pulse in gold. It is used on Replay when the
        animation is finished.
        """
        hover = enabled and rl.check_collision_point_rec(
            rl.get_mouse_position(), rect)
        fill = rl.Color(38, 42, 60, 255)
        if hover and rl.is_mouse_button_down(rl.MouseButton.MOUSE_BUTTON_LEFT):
            fill = rl.Color(70, 76, 108, 255)
        elif hover:
            fill = rl.Color(52, 58, 84, 255)
        ink = TEXT if enabled else LINK_FREE
        if glow:
            pulse = 0.65 + 0.35 * math.sin(rl.get_time() * 5)
            fill = rl.Color(GOLD.r, GOLD.g, GOLD.b, int(255 * pulse))
            ink = rl.Color(13, 15, 22, 255)
        rl.draw_rectangle_rounded(rect, 0.3, 6, fill)
        self.draw_icon(name, rect.x + rect.width / 2,
                       rect.y + rect.height / 2, ink, playing)

    def draw_scrub(self, width: int, frac: float) -> None:
        """Draw the progress bar, ``frac`` being between 0 and 1."""
        y = HUD_HEIGHT - SCRUB_H
        rl.draw_rectangle(0, y, width, SCRUB_H, rl.Color(42, 46, 66, 255))
        rl.draw_rectangle(0, y, int(width * frac), SCRUB_H, TEAL)
        mouse = rl.get_mouse_position()
        if rl.check_collision_point_rec(mouse, self.scrub_rect(width)):
            rl.draw_circle(int(width * frac), y + 2, 6, TEXT)

    def draw_tip(self, text: str, rect: rl.Rectangle, width: int) -> None:
        """Draw a tooltip under the HUD, kept inside the window."""
        w = rl.measure_text(text, 14)
        x = min(int(rect.x + rect.width / 2 - w / 2 - 8), width - w - 24)
        rl.draw_rectangle(x, HUD_HEIGHT + 6, w + 16, 24, HUD_BG)
        rl.draw_text(text, x + 8, HUD_HEIGHT + 11, 14, TEXT)

    def draw_hud(self, turn: int, playing: bool, speed: float,
                 width: int, frac: float) -> None:
        """Draw the top bar: counters, buttons, progress and hints."""
        rl.draw_rectangle(0, 0, width, HUD_HEIGHT, HUD_BG)
        total = self.replay.turns
        moves = self.replay.moves_per_turn[turn - 1] if turn > 0 else 0
        done = self.replay.delivered(turn)
        finished = turn >= total
        state = "playing" if playing else "paused"
        if finished:
            state = "finished"
        items = [
            (f"Turn {turn} / {total}", 16),
            (f"Delivered {done} / {self.graph.nb_drones}", 220),
            (f"Moves {moves}", 450),
            (f"{state}  x{speed:.1f}", 600),
        ]
        for text, x in items:
            rl.draw_text(text, x, 13, 20, TEXT)
        mouse = rl.get_mouse_position()
        tip: tuple[str, rl.Rectangle] | None = None
        for name, rect, text in self.hud_buttons(width):
            enabled = self.button_enabled(name, turn, speed)
            glow = name == "replay" and finished
            self.draw_hud_button(name, rect, enabled, playing, glow)
            if enabled and rl.check_collision_point_rec(mouse, rect):
                tip = (text, rect)
        self.draw_scrub(width, frac)
        if tip is not None:
            self.draw_tip(tip[0], tip[1], width)
        else:
            hint = "drag pan | wheel zoom | double-click reset | click bar"
            rl.draw_text(hint, width - rl.measure_text(hint, 14) - 16,
                         HUD_HEIGHT + 10, 14, MUTED)

    def hover_name(self) -> str | None:
        """Return the name of the zone under the mouse, or None."""
        mouse = rl.get_mouse_position()
        if mouse.y < HUD_HEIGHT:
            return None
        for name, zone in self.graph.zones.items():
            p = self.view.point(name)
            if math.hypot(mouse.x - p.x, mouse.y - p.y) <= \
                    self.view.radius(name) + 3:
                return name
        return None

    def draw_hover(self, selected: str | None) -> None:
        """Draw the hover ring and tooltip, or the selected zone label."""
        name = self.hover_name()
        if name is not None:
            zone = self.graph.zones[name]
            text = f"{name}  {zone.type.value}  cap {zone.max_drone}"
            mouse = rl.get_mouse_position()
            if name != selected:
                p = self.view.point(name)
                r = self.view.radius(name)
                rl.draw_ring(p, r + 5, r + 7, 0, 360, 32,
                             rl.Color(255, 211, 105, 170))
            w = rl.measure_text(text, 16)
            x = min(int(mouse.x + 12), rl.get_screen_width() - w - 24)
            y = min(int(mouse.y + 12), rl.get_screen_height() - 30)
            rl.draw_rectangle(x, y, w + 12, 24, HUD_BG)
            rl.draw_text(text, x + 6, y + 4, 16, TEXT)
        elif selected is not None:
            zone = self.graph.zones[selected]
            text = (f"Selected: {selected}  {zone.type.value}  "
                    f"cap {zone.max_drone}")
            w = rl.measure_text(text, 16)
            rl.draw_rectangle(16, rl.get_screen_height() - 38,
                              w + 24, 30, HUD_BG)
            rl.draw_text(text, 28, rl.get_screen_height() - 32, 16, TEXT)

    def draw(self, turn: int, progress: float, playing: bool,
             speed: float, width: int, selected: str | None = None) -> None:
        """Draw one full frame of the simulation.

        Args:
            turn: Current turn.
            progress: Progress of the current turn, between 0 and 1.
            playing: Whether the animation is playing.
            speed: Playback speed multiplier.
            width: Window width in pixels.
            selected: Name of the selected zone, if any.
        """
        self.draw_links(min(turn + (1 if progress > 0.5 else 0),
                            self.replay.turns))
        shown = min(turn + (1 if progress > 0.5 else 0), self.replay.turns)
        for name in self.graph.zones:
            self.draw_zone(name, shown, selected)
        for ident in self.replay.frames[turn]:
            self.draw_drone(turn, progress, ident)
        turns = self.replay.turns
        frac = 1.0 if turn >= turns else (turn + progress) / turns
        self.draw_hud(shown, playing, speed, width, frac)
        self.draw_legend(width, rl.get_screen_height())
        self.draw_hover(selected)

    def legend_icon(self, kind: str, c: rl.Vector2) -> None:
        """Draw the icon of one legend entry centered on ``c``."""
        base = rgb((110, 115, 130))
        if kind == "normal":
            rl.draw_circle_v(c, 8, base)
        elif kind == "priority":
            rl.draw_circle_v(c, 10, rl.Color(232, 193, 58, 255))
            rl.draw_circle_v(c, 7, base)
        elif kind == "restricted":
            outer = rl.Rectangle(c.x - 10, c.y - 10, 20, 20)
            inner = rl.Rectangle(c.x - 7, c.y - 7, 14, 14)
            rl.draw_rectangle_rounded(outer, 0.25, 6,
                                      rl.Color(255, 107, 107, 255))
            rl.draw_rectangle_rounded(inner, 0.25, 6, base)
        elif kind == "blocked":
            rl.draw_circle_v(c, 9, rl.Color(42, 44, 53, 255))
            rl.draw_line_ex(rl.Vector2(c.x - 4, c.y - 4),
                            rl.Vector2(c.x + 4, c.y + 4), 2, MUTED)
            rl.draw_line_ex(rl.Vector2(c.x + 4, c.y - 4),
                            rl.Vector2(c.x - 4, c.y + 4), 2, MUTED)
        elif kind == "waiting":
            rl.draw_circle_v(c, 10, rl.Color(138, 147, 173, 255))
            rl.draw_circle_v(c, 8, rl.Color(42, 48, 64, 255))
        elif kind == "inside":
            rl.draw_circle_v(c, 3.5, TEXT)
        elif kind == "reserved":
            rl.draw_circle_lines(int(c.x), int(c.y), 4, LINK_PART)
        elif kind == "free":
            rl.draw_circle_lines(int(c.x), int(c.y), 3, MUTED)
        else:
            color = {"link_free": LINK_FREE, "link_part": LINK_PART,
                     "link_full": LINK_FULL}[kind]
            rl.draw_line_ex(rl.Vector2(c.x - 10, c.y),
                            rl.Vector2(c.x + 10, c.y), 4, color)

    def draw_legend(self, width: int, height: int) -> None:
        """Draw the legend bar at the bottom, wrapping on several rows."""
        items: list[tuple[str, str, int, int]] = []
        x, row = 16, 0
        for kind, label in LEGEND:
            size = 26 + rl.measure_text(label, LEGEND_FONT) + 20
            if x + size > width - 16 and x > 16:
                x, row = 16, row + 1
            items.append((kind, label, x, row))
            x += size
        bar = (row + 1) * LEGEND_ROW + 8
        top = height - bar
        rl.draw_rectangle(0, top, width, bar, HUD_BG)
        for kind, label, ix, irow in items:
            cy = top + 4 + irow * LEGEND_ROW + LEGEND_ROW / 2
            self.legend_icon(kind, rl.Vector2(ix + 10, cy))
            rl.draw_text(label, ix + 26, int(cy - LEGEND_FONT / 2),
                         LEGEND_FONT, MUTED)


class App:
    """Own the window, the animation state and the user inputs."""

    def __init__(self, graph: Graph, lines: list[str],
                 width: int = 1280, height: int = 720) -> None:
        """Prepare the replay, the view and the renderer.

        Args:
            graph: Parsed graph of the map.
            lines: Simulation output, one line of moves per turn.
            width: Window width in pixels.
            height: Window height in pixels.
        """
        self.width = width
        self.height = height
        self.graph = graph
        self.replay = Replay(graph, lines)
        self.view = View(graph, width, height)
        self.renderer = Renderer(graph, self.replay, self.view)
        self.turn = 0
        self.progress = 0.0
        self.playing = True
        self.speed = 1.5
        self.selected: str | None = None
        self.dragging = False
        self.last_mouse = rl.get_mouse_position()
        self.pressing = False
        self.dragged = False
        self.scrubbing = False
        self.press_pos = rl.Vector2(0, 0)
        self.last_click = 0.0

    def replay_from_start(self) -> None:
        """Restart the animation from turn 0 and start playing."""
        self.turn, self.progress, self.playing = 0, 0.0, True

    def reset_view(self) -> None:
        """Reset the zoom and the pan to their default values."""
        self.view.zoom = 1.0
        self.view.pan_x = 0.0
        self.view.pan_y = 0.0

    def press_button(self, name: str) -> None:
        """Run the action of a HUD button or of its keyboard shortcut.

        Args:
            name: One of replay, toggle, prev, next, slower or faster.
        """
        last = self.replay.turns
        if name == "replay":
            self.replay_from_start()
        elif name == "toggle":
            if self.turn >= last:
                self.replay_from_start()
            else:
                self.playing = not self.playing
        elif name == "prev":
            self.turn, self.progress = max(self.turn - 1, 0), 0.0
        elif name == "next":
            self.turn, self.progress = min(self.turn + 1, last), 0.0
        elif name == "slower":
            self.speed = max(self.speed - 0.5, 0.5)
        elif name == "faster":
            self.speed = min(self.speed + 0.5, 8.0)

    def scrub_to(self, x: float) -> None:
        """Jump to the turn matching a horizontal pixel position."""
        frac = max(0.0, min(1.0, x / self.width))
        self.turn = round(frac * self.replay.turns)
        self.progress = 0.0

    def handle_zoom(self, mouse: rl.Vector2) -> None:
        """Zoom with the mouse wheel, keeping the point under the cursor."""
        wheel = rl.get_mouse_wheel_move()
        if wheel == 0 or mouse.y < HUD_HEIGHT:
            return
        old = self.view.zoom
        new = max(0.4, min(6.0, old * (1.12 if wheel > 0 else 1 / 1.12)))
        if new == old:
            return
        v = self.view
        wx = (mouse.x - v.left - v.pan_x) / (old * v.scale)
        wy = (mouse.y - v.top - v.pan_y) / (old * v.scale)
        v.zoom = new
        v.pan_x = mouse.x - v.left - wx * v.scale * new
        v.pan_y = mouse.y - v.top - wy * v.scale * new

    def drag_left(self, mouse: rl.Vector2) -> None:
        """Pan the view while the left button is dragged.

        A movement under 4 pixels is ignored, so that a simple click is not
        taken for a drag.
        """
        if not self.dragged:
            dist = math.hypot(mouse.x - self.press_pos.x,
                              mouse.y - self.press_pos.y)
            self.dragged = dist > 4
        if self.dragged:
            delta = rl.get_mouse_delta()
            self.view.pan_x += delta.x
            self.view.pan_y += delta.y

    def click(self) -> None:
        """Handle a left click released without dragging.

        Clicking a zone selects or deselects it. Double-clicking empty space
        resets the view.
        """
        self.pressing = False
        if self.dragged:
            self.dragged = False
            return
        hovered = self.renderer.hover_name()
        now = rl.get_time()
        if hovered is None:
            if now - self.last_click < 0.3:
                self.reset_view()
                now = 0.0
            self.last_click = now
            self.selected = None
        else:
            self.last_click = 0.0
            self.selected = None if hovered == self.selected else hovered

    def update_cursor(self, button: str | None, on_bar: bool) -> None:
        """Choose the mouse cursor from what is under the pointer."""
        if self.dragged or self.dragging:
            cursor = rl.MouseCursor.MOUSE_CURSOR_RESIZE_ALL
        elif (button is not None or on_bar or self.scrubbing
              or self.renderer.hover_name() is not None):
            cursor = rl.MouseCursor.MOUSE_CURSOR_POINTING_HAND
        else:
            cursor = rl.MouseCursor.MOUSE_CURSOR_DEFAULT
        rl.set_mouse_cursor(cursor)

    def handle_mouse(self) -> None:
        """Process the mouse for one frame: buttons, bar, pan, zoom, clicks."""
        mouse = rl.get_mouse_position()
        left = rl.MouseButton.MOUSE_BUTTON_LEFT
        pan_button = rl.MouseButton.MOUSE_BUTTON_RIGHT
        button = self.renderer.button_at(mouse, self.width)
        on_bar = rl.check_collision_point_rec(
            mouse, self.renderer.scrub_rect(self.width))
        self.handle_zoom(mouse)

        if rl.is_mouse_button_pressed(left):
            if button is not None:
                self.press_button(button)
            elif on_bar:
                self.scrubbing = True
            elif mouse.y >= HUD_HEIGHT:
                self.pressing, self.dragged = True, False
                self.press_pos = mouse
        if self.scrubbing:
            if rl.is_mouse_button_down(left):
                self.scrub_to(mouse.x)
            else:
                self.scrubbing = False

        if rl.is_mouse_button_pressed(pan_button):
            self.dragging = True
        if rl.is_mouse_button_down(pan_button) and self.dragging:
            delta = rl.get_mouse_delta()
            self.view.pan_x += delta.x
            self.view.pan_y += delta.y
        if rl.is_mouse_button_released(pan_button):
            self.dragging = False

        if self.pressing and rl.is_mouse_button_down(left):
            self.drag_left(mouse)
        if self.pressing and rl.is_mouse_button_released(left):
            self.click()
        self.update_cursor(button, on_bar)

    def handle_keys(self) -> None:
        """Process the keyboard shortcuts for one frame."""
        keys = [
            (rl.KeyboardKey.KEY_SPACE, "toggle"),
            (rl.KeyboardKey.KEY_RIGHT, "next"),
            (rl.KeyboardKey.KEY_LEFT, "prev"),
            (rl.KeyboardKey.KEY_UP, "faster"),
            (rl.KeyboardKey.KEY_DOWN, "slower"),
            (rl.KeyboardKey.KEY_R, "replay"),
        ]
        for key, name in keys:
            if rl.is_key_pressed(key):
                self.press_button(name)
        if rl.is_key_pressed(rl.KeyboardKey.KEY_HOME):
            self.replay_from_start()
            self.reset_view()
            self.selected = None

    def advance(self) -> None:
        """Advance the animation clock by one frame when playing."""
        if (not self.playing or self.scrubbing
                or self.turn >= self.replay.turns):
            return
        self.progress += rl.get_frame_time() * self.speed
        if self.progress >= 1.0:
            self.turn, self.progress = self.turn + 1, 0.0

    def run(self) -> None:
        """Open the window and run the main loop until it is closed."""
        rl.set_trace_log_level(rl.TraceLogLevel.LOG_NONE)
        rl.init_window(self.width, self.height, "Fly-in")
        rl.set_target_fps(60)
        try:
            while not rl.window_should_close():
                self.handle_keys()
                self.handle_mouse()
                self.advance()
                rl.begin_drawing()
                rl.clear_background(BG)
                self.renderer.draw(self.turn, self.progress, self.playing,
                                   self.speed, self.width, self.selected)
                rl.end_drawing()
        finally:
            rl.close_window()
