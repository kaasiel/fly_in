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


def rgb(color: Rgb, alpha: int = 255) -> rl.Color:
    return rl.Color(color[0], color[1], color[2], alpha)


def zone_color(name: str | None) -> rl.Color:
    if name == "rainbow":
        return rl.color_from_hsv((rl.get_time() * 60) % 360, 0.65, 0.9)
    return rgb(NAMED.get(name or "", (110, 115, 130)))


def lerp(a: rl.Vector2, b: rl.Vector2, t: float) -> rl.Vector2:
    return rl.Vector2(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t)


class View:
    def __init__(self, graph: Graph, width: int, height: int) -> None:
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
        x, y = self.graph.zones[zone].coordinate
        return rl.Vector2(
            self.left + (x - self.min_x) * self.scale * self.zoom
            + self.pan_x,
            self.top + (y - self.min_y) * self.scale * self.zoom
            + self.pan_y,
        )

    def radius(self, zone: str) -> float:
        base = max(9.0, min(20.0, self.scale * 0.32))
        if zone in (self.graph.start, self.graph.end):
            return base * 1.5
        return base * min(self.zoom, 2.0)


class Renderer:
    def __init__(self, graph: Graph, replay: Replay, view: View) -> None:
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

    def draw_zone(self, name: str, turn: int, selected: str | None = None) -> None:
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
        zone, dest = self.replay.frames[frame][ident]
        if dest is not None or zone not in (self.replay.start,
                                            self.replay.end):
            return False
        return len(self.replay.occupants[frame][zone]) > 6

    def draw_drone(self, turn: int, progress: float, ident: int) -> None:
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

    def draw_hud(self, turn: int, playing: bool, speed: float,
                 width: int) -> None:
        rl.draw_rectangle(0, 0, width, HUD_HEIGHT, HUD_BG)
        total = self.replay.turns
        moves = self.replay.moves_per_turn[turn - 1] if turn > 0 else 0
        done = self.replay.delivered(turn)
        state = "playing" if playing else "paused"
        items = [
            (f"Turn {turn} / {total}", 16),
            (f"Delivered {done} / {self.graph.nb_drones}", 220),
            (f"Moves {moves}", 450),
            (f"{state}  x{speed:.1f}", 600),
        ]
        for text, x in items:
            rl.draw_text(text, x, 13, 20, TEXT)
        hint = "Click select | wheel zoom | right-drag pan | Space play"
        rl.draw_text(hint, width - rl.measure_text(hint, 14) - 16, 15,
                     14, MUTED)

    def hover_name(self) -> str | None:
        mouse = rl.get_mouse_position()
        for name, zone in self.graph.zones.items():
            p = self.view.point(name)
            if math.hypot(mouse.x - p.x, mouse.y - p.y) <= \
                    self.view.radius(name) + 3:
                return name
        return None

    def draw_hover(self, selected: str | None) -> None:
        name = self.hover_name()
        if name is not None:
            zone = self.graph.zones[name]
            text = f"{name}  {zone.type.value}  cap {zone.max_drone}"
            mouse = rl.get_mouse_position()
            w = rl.measure_text(text, 16)
            rl.draw_rectangle(int(mouse.x + 12), int(mouse.y + 12),
                              w + 12, 24, HUD_BG)
            rl.draw_text(text, int(mouse.x + 18), int(mouse.y + 16),
                         16, TEXT)
        elif selected is not None:
            zone = self.graph.zones[selected]
            text = f"Selected: {selected}  {zone.type.value}  cap {zone.max_drone}"
            w = rl.measure_text(text, 16)
            rl.draw_rectangle(16, rl.get_screen_height() - 38,
                              w + 24, 30, HUD_BG)
            rl.draw_text(text, 28, rl.get_screen_height() - 32, 16, TEXT)

    def draw(self, turn: int, progress: float, playing: bool,
             speed: float, width: int, selected: str | None = None) -> None:
        self.draw_links(min(turn + (1 if progress > 0.5 else 0),
                            self.replay.turns))
        shown = min(turn + (1 if progress > 0.5 else 0), self.replay.turns)
        for name in self.graph.zones:
            self.draw_zone(name, shown, selected)
        for ident in self.replay.frames[turn]:
            self.draw_drone(turn, progress, ident)
        self.draw_hud(shown, playing, speed, width)
        self.draw_legend(width, rl.get_screen_height())
        self.draw_hover(selected)

    def legend_icon(self, kind: str, c: rl.Vector2) -> None:
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
    def __init__(self, graph: Graph, lines: list[str],
                 width: int = 1280, height: int = 720) -> None:
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

    def handle_mouse(self) -> None:
        mouse = rl.get_mouse_position()

        wheel = rl.get_mouse_wheel_move()
        if wheel != 0:
            old_zoom = self.view.zoom
            new_zoom = max(0.5, min(3.0, old_zoom * (1.12 if wheel > 0 else 1 / 1.12)))
            if new_zoom != old_zoom:
                dx = mouse.x - self.view.left - self.view.pan_x
                dy = mouse.y - self.view.top - self.view.pan_y
                world_x = dx / (old_zoom * self.view.scale)
                world_y = dy / (old_zoom * self.view.scale)
                self.view.zoom = new_zoom
                self.view.pan_x = mouse.x - self.view.left - world_x * self.view.scale * new_zoom
                self.view.pan_y = mouse.y - self.view.top - world_y * self.view.scale * new_zoom

        pan_button = rl.MOUSE_BUTTON_RIGHT if hasattr(rl, "MOUSE_BUTTON_RIGHT") else rl.MOUSE_RIGHT_BUTTON
        if rl.is_mouse_button_pressed(pan_button):
            self.dragging = True
            self.last_mouse = mouse
        if rl.is_mouse_button_down(pan_button) and self.dragging:
            delta = rl.get_mouse_delta()
            self.view.pan_x += delta.x
            self.view.pan_y += delta.y
        if rl.is_mouse_button_released(pan_button):
            self.dragging = False

        if rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
            hovered = self.renderer.hover_name()
            self.selected = hovered

        if rl.is_mouse_button_down(pan_button):
            rl.set_mouse_cursor(rl.MOUSE_CURSOR_RESIZE_ALL)
        elif self.renderer.hover_name() is not None:
            rl.set_mouse_cursor(rl.MOUSE_CURSOR_POINTING_HAND)
        else:
            rl.set_mouse_cursor(rl.MOUSE_CURSOR_DEFAULT)

    def handle_keys(self) -> None:
        last = self.replay.turns
        if rl.is_key_pressed(rl.KeyboardKey.KEY_SPACE):
            self.playing = not self.playing
        if rl.is_key_pressed(rl.KeyboardKey.KEY_RIGHT):
            self.turn, self.progress = min(self.turn + 1, last), 0.0
        if rl.is_key_pressed(rl.KeyboardKey.KEY_LEFT):
            self.turn, self.progress = max(self.turn - 1, 0), 0.0
        if rl.is_key_pressed(rl.KeyboardKey.KEY_UP):
            self.speed = min(self.speed + 0.5, 8.0)
        if rl.is_key_pressed(rl.KeyboardKey.KEY_DOWN):
            self.speed = max(self.speed - 0.5, 0.5)
        if rl.is_key_pressed(rl.KeyboardKey.KEY_HOME):
            self.turn, self.progress, self.playing = 0, 0.0, True
            self.view.zoom = 1.0
            self.view.pan_x = 0.0
            self.view.pan_y = 0.0
            self.selected = None

    def advance(self) -> None:
        if not self.playing or self.turn >= self.replay.turns:
            return
        self.progress += rl.get_frame_time() * self.speed
        if self.progress >= 1.0:
            self.turn, self.progress = self.turn + 1, 0.0

    def run(self) -> None:
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
