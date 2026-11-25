"""Start menu of Fly-in: let the user pick a map and a view mode."""
import math
import os
import pyray as rl

BG = rl.Color(20, 22, 30, 255)
HUD_BG = rl.Color(30, 33, 48, 255)
TEXT = rl.Color(230, 232, 240, 255)
MUTED = rl.Color(154, 160, 181, 255)
LINK = rl.Color(91, 98, 122, 255)
GREEN = rl.Color(47, 143, 78, 255)
ORANGE = rl.Color(224, 138, 44, 255)
RED = rl.Color(217, 74, 58, 255)
PURPLE = rl.Color(122, 90, 214, 255)
TEAL = rl.Color(43, 179, 160, 255)
GOLD = rl.Color(232, 193, 58, 255)

LEVELS: dict[str, tuple[rl.Color, list[str]]] = {
    "Easy": (GREEN, ["maps/easy/01_linear_path.txt",
                     "maps/easy/02_simple_fork.txt",
                     "maps/easy/03_basic_capacity.txt"]),

    "Medium": (RED, ["maps/medium/01_dead_end_trap.txt",
                     "maps/medium/02_circular_loop.txt",
                     "maps/medium/03_priority_puzzle.txt"]),

    "Hard": (ORANGE, ["maps/hard/01_maze_nightmare.txt",
                      "maps/hard/02_capacity_hell.txt",
                      "maps/hard/03_ultimate_challenge.txt"]),
}

CHALLENGER = "maps/challenger/01_the_impossible_dream.txt"

LOGO_SHAPES: list[list[tuple[float, float]]] = [
    [(0, 38), (24, 0), (38, 0), (14, 38)],
    [(0, 38), (52, 38), (52, 50), (0, 50)],
    [(38, 0), (52, 0), (52, 38), (38, 38)],
    [(38, 50), (52, 50), (52, 64), (38, 64)],
    [(58, 0), (100, 0), (100, 12), (58, 12)],
    [(86, 12), (100, 12), (100, 26), (86, 26)],
    [(86, 26), (100, 26), (72, 52), (58, 52)],
    [(58, 52), (100, 52), (100, 64), (58, 64)],
]

Item = tuple[str, str, rl.Color, str]
Choice = tuple[str, str]

VIEW_2D = "2d"
VIEW_ISO = "iso"

BTN_H = 76
BTN_GAP = 18


def lerp(a: rl.Vector2, b: rl.Vector2, t: float) -> rl.Vector2:
    """Return the point at fraction ``t`` of the segment ``a`` to ``b``."""
    return rl.Vector2(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t)


def tri(a: rl.Vector2, b: rl.Vector2, c: rl.Vector2,
        color: rl.Color) -> None:
    """Draw a filled triangle whatever the order of its vertices.

    raylib only draws triangles whose vertices are in counter-clockwise
    order, so the last two vertices are swapped when needed.
    """
    cross = (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)
    if cross > 0:
        b, c = c, b
    rl.draw_triangle(a, b, c, color)


def draw_42(ox: float, oy: float, k: float, color: rl.Color) -> None:
    """Draw the stylized 42 logo made of ``LOGO_SHAPES``.

    Args:
        ox: X position of the top-left corner.
        oy: Y position of the top-left corner.
        k: Size in pixels of one unit of the logo grid.
        color: Fill color, alpha included.
    """
    for shape in LOGO_SHAPES:
        v = [rl.Vector2(ox + x * k, oy + y * k) for x, y in shape]
        tri(v[0], v[1], v[2], color)
        tri(v[0], v[2], v[3], color)


class Menu:
    """Show the start screen: modes, maps, a path input and the view choice.

    The menu has four states: ``main`` (the list of modes), ``level`` (the
    maps of one level), ``load`` (typing the path of a map) and ``view``
    (choosing the 2D or the 3D isometric view). When the user is done,
    ``choice`` holds the result, or ``quit`` is set.
    """

    def __init__(self, width: int, height: int) -> None:
        """Compute the layout of the right-hand panel.

        Args:
            width: Window width in pixels.
            height: Window height in pixels.
        """
        self.width = width
        self.height = height
        self.state = "main"
        self.level = ""
        self.text = ""
        self.error = ""
        self.path = ""
        self.back_to = "main"
        self.quit = False
        self.choice: Choice | None = None
        self.panel_x = int(width * 0.55)
        self.panel_w = width - self.panel_x - 90

    def items(self) -> list[Item]:
        """Return the buttons of the current state.

        Each item is a tuple (label, subtitle, color, action). An action is
        ``level:<name>``, ``map:<path>``, ``view:<mode>``, ``load``, ``back``
        or ``quit``.
        """
        if self.state == "view":
            return [
                ("2D", "flat top-down view", TEAL, f"view:{VIEW_2D}"),
                ("3D isometric", "isometric projection", PURPLE,
                 f"view:{VIEW_ISO}"),
                ("Back", "", MUTED, "back"),
            ]
        if self.state == "level":
            color, paths = LEVELS[self.level]
            res: list[Item] = [
                (f"Map {i + 1}", os.path.basename(p), color, f"map:{p}")
                for i, p in enumerate(paths)
            ]
            return res + [("Back", "", MUTED, "back")]
        if self.state == "load":
            return [("Back", "", MUTED, "back")]
        res = [(name, f"{len(paths)} maps", color, f"level:{name}")
               for name, (color, paths) in LEVELS.items()]
        res.append(("Challenger", "1 map", PURPLE, f"map:{CHALLENGER}"))
        res.append(("Load your own map", "type the path of a map file",
                    TEAL, "load"))
        res.append(("Quit", "", LINK, "quit"))
        return res

    def rect(self, index: int, count: int) -> rl.Rectangle:
        """Return the rectangle of button ``index`` among ``count`` buttons.

        Buttons are stacked and centered vertically, except in the ``load``
        state where they are placed under the input box.
        """
        total = count * BTN_H + (count - 1) * BTN_GAP
        top = (self.height - total) / 2 + 20
        if self.state == "load":
            top = self.height / 2 + 60
        return rl.Rectangle(self.panel_x, top + index * (BTN_H + BTN_GAP),
                            self.panel_w, BTN_H)

    def heading(self) -> str:
        """Return the title shown above the buttons."""
        if self.state == "view":
            return "Choose a view"
        if self.state == "level":
            return f"{self.level} - choose a map"
        if self.state == "load":
            return "Load your own map"
        return "Select a mode"

    def select_path(self, path: str) -> None:
        """Go to the view choice if ``path`` is a file, else store an error.

        Args:
            path: Path of the map file.
        """
        if os.path.isfile(path):
            self.path = path
            self.back_to = self.state
            self.state = "view"
            return
        self.error = f"File not found: {path}"

    def act(self, action: str) -> None:
        """Run the action of a clicked button.

        The menu is over once ``quit`` is set or ``choice`` is filled.

        Args:
            action: Action string of the button, see ``items``.
        """
        self.error = ""
        kind, _, value = action.partition(":")
        if kind == "map":
            self.select_path(value)
        elif kind == "view":
            self.choice = (self.path, value)
        elif kind == "level":
            self.state, self.level = "level", value
        elif kind == "load":
            self.state, self.text = "load", ""
        elif kind == "back":
            self.state = self.back_to if self.state == "view" else "main"
        elif kind == "quit":
            self.quit = True

    def handle_input(self) -> None:
        """Process the keyboard and the mouse for one frame.

        Escape goes back one step, or quits from the main state. Clicking
        a button runs its action.
        """
        if rl.is_key_pressed(rl.KeyboardKey.KEY_ESCAPE):
            self.act("quit" if self.state == "main" else "back")
            return
        mouse = rl.get_mouse_position()
        left = rl.MouseButton.MOUSE_BUTTON_LEFT
        items = self.items()
        hovered = False
        for i, (_, _, _, action) in enumerate(items):
            if rl.check_collision_point_rec(mouse, self.rect(i, len(items))):
                hovered = True
                if rl.is_mouse_button_pressed(left):
                    self.act(action)
                    return
        rl.set_mouse_cursor(
            rl.MouseCursor.MOUSE_CURSOR_POINTING_HAND if hovered
            else rl.MouseCursor.MOUSE_CURSOR_DEFAULT)
        if self.state == "load":
            self.handle_typing()

    def handle_typing(self) -> None:
        """Read the typed path in the ``load`` state.

        Enter validates the text and goes to the view choice if the file
        exists.
        """
        while (char := rl.get_char_pressed()) != 0:
            self.text += chr(char)
            self.error = ""
        back = rl.KeyboardKey.KEY_BACKSPACE
        if rl.is_key_pressed(back) or rl.is_key_pressed_repeat(back):
            self.text = self.text[:-1]
        if rl.is_key_pressed(rl.KeyboardKey.KEY_ENTER) and self.text:
            self.select_path(self.text.strip())

    def center(self) -> rl.Vector2:
        """Return the center of the left area, where the title sits."""
        return rl.Vector2((self.panel_x - 45) / 2, self.height / 2)

    def draw_background(self) -> None:
        """Draw the animated graph around the title.

        A gold dot travels along the edges of a ring of nodes.
        """
        t = rl.get_time()
        c = self.center()
        s = min((self.panel_x - 45) / 660, self.height / 720)
        offsets = [(-250, -190), (-50, -280), (200, -210), (280, 20),
                   (190, 250), (-90, 285), (-275, 100)]
        nodes = [rl.Vector2(c.x + dx * s, c.y + dy * s)
                 for dx, dy in offsets]
        for a, b in zip(nodes, nodes[1:] + nodes[:1]):
            rl.draw_line_ex(a, b, 2, rl.Color(91, 98, 122, 90))
        for n in nodes:
            rl.draw_circle_v(n, 7, rl.Color(91, 98, 122, 140))
        seg = int(t * 0.8) % len(nodes)
        a, b = nodes[seg], nodes[(seg + 1) % len(nodes)]
        rl.draw_circle_v(lerp(a, b, (t * 0.8) % 1.0), 6, GOLD)

    def draw_title(self) -> None:
        """Draw the centered title, its animated bar and the author."""
        c = self.center()
        top = int(c.y - 95)
        w = rl.measure_text("Fly-in", 130)
        rl.draw_text("Fly-in", int(c.x - w / 2), top, 130, TEXT)
        pulse = 0.5 + 0.5 * math.sin(rl.get_time() * 2)
        bar = 90 + int(40 * pulse)
        rl.draw_rectangle(int(c.x - bar / 2), top + 140, bar, 5, TEAL)
        sub_w = rl.measure_text("by belaindr", 28)
        rl.draw_text("by belaindr", int(c.x - sub_w / 2), top + 160, 28,
                     MUTED)

    def draw_button(self, rect: rl.Rectangle, item: Item) -> None:
        """Draw one button, highlighted when the mouse is over it."""
        label, sub, color, _ = item
        hover = rl.check_collision_point_rec(rl.get_mouse_position(), rect)
        rl.draw_rectangle_rec(rect, rl.Color(42, 46, 66, 255) if hover
                              else HUD_BG)
        rl.draw_rectangle(int(rect.x), int(rect.y), 8 if not hover else 14,
                          int(rect.height), color)
        x = int(rect.x) + 32
        if sub:
            rl.draw_text(label, x, int(rect.y) + 14, 28, TEXT)
            rl.draw_text(sub, x, int(rect.y) + 48, 16, MUTED)
        else:
            rl.draw_text(label, x, int(rect.y) + 24, 26, MUTED)

    def draw_load_box(self) -> None:
        """Draw the path input box, its blinking cursor and errors."""
        x, y, w = self.panel_x, int(self.height / 2 - 120), self.panel_w
        rl.draw_text("Path to a map file", x, y, 18, MUTED)
        box = rl.Rectangle(x, y + 30, w, 52)
        rl.draw_rectangle_rec(box, HUD_BG)
        rl.draw_rectangle_lines_ex(box, 2, TEAL)
        shown = self.text
        while shown and rl.measure_text(shown, 22) > w - 28:
            shown = shown[1:]
        rl.draw_text(shown, x + 14, y + 44, 22, TEXT)
        if int(rl.get_time() * 2) % 2 == 0:
            cx = x + 16 + rl.measure_text(shown, 22)
            rl.draw_rectangle(cx, y + 42, 2, 26, TEXT)
        rl.draw_text("Press Enter to open",
                     x, y + 96, 16, MUTED)
        if self.error:
            rl.draw_text(self.error, x, y + 124, 16, RED)

    def draw(self) -> None:
        """Draw one full frame of the menu."""
        self.draw_background()
        self.draw_title()
        rl.draw_line_ex(rl.Vector2(self.panel_x - 45, 90),
                        rl.Vector2(self.panel_x - 45, self.height - 90),
                        2, LINK)
        items = self.items()
        first = self.rect(0, len(items))
        if self.state == "load":
            self.draw_load_box()
        else:
            rl.draw_text(self.heading(), self.panel_x, int(first.y) - 50,
                         24, MUTED)
        for i, item in enumerate(items):
            self.draw_button(self.rect(i, len(items)), item)
        if self.error and self.state != "load":
            rl.draw_text(self.error, 24, self.height - 36, 16, RED)

    def run(self) -> Choice | None:
        """Run the menu loop until the user has chosen or quits.

        Returns:
            A tuple (map path, view), the view being ``2d`` or ``iso``, or
            None to quit.
        """
        while not rl.window_should_close():
            self.handle_input()
            if self.quit:
                return None
            if self.choice is not None:
                return self.choice
            rl.begin_drawing()
            rl.clear_background(BG)
            self.draw()
            rl.end_drawing()
        return None


def choose_map(width: int = 1280, height: int = 720) -> Choice | None:
    """Open a window, show the menu and return the chosen map and view.

    Args:
        width: Window width in pixels.
        height: Window height in pixels.

    Returns:
        A tuple (map path, view), the view being ``2d`` or ``iso``, or
        None if the user quits or closes the window.
    """
    rl.set_trace_log_level(rl.TraceLogLevel.LOG_NONE)
    rl.init_window(width, height, "Fly-in")
    rl.set_exit_key(rl.KeyboardKey.KEY_NULL)
    rl.set_target_fps(60)
    menu = Menu(width, height)
    try:
        return menu.run()
    finally:
        rl.close_window()
