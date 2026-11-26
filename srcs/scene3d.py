"""3D isometric visualizer of a Fly-in simulation, drawn with pyray."""
from __future__ import annotations

import math
from pathlib import Path
import pyray as rl
from .model import Graph, ZoneType
from .replay import Replay
from .visual import (BG, BTN_GAP, BTN_H, BTN_Y, BUTTONS, GOLD, HUD_BG,
                     HUD_HEIGHT, LINK_FREE, LINK_FULL, LINK_PART, MUTED,
                     ROUTES, TEXT, rgb, zone_color)

SCALE = 3.8            # world units per map unit (hub spacing)
PORTAL_R = 0.85
PORTAL_H = PORTAL_R + 0.3
DRONE_SIZE = 1.5       # largest dimension of the drone model
SPRITE_SIZE_MULTIPLIER = 5.0
FLY_Y = 1.25
TRANSIT_Y = 2.2
MODEL_YAW_OFFSET = 0.0  # tune if your model does not face +z
STACK_LIMIT = 0        # drones shown on start/end pads (0 = emerge one by one)
ORBIT_SPEED = 0.35     # degrees per pixel when dragging
LINK_FREE_3D = rl.Color(122, 132, 165, 255)
LEGEND_TEXT = ("portal = hub | gold halo = priority | spiked = restricted"
               " | sealed = blocked | pips = capacity"
               " | shadow color = route | gray = waiting")
TIPS_3D = {
    "replay": "Replay from the start",
    "prev": "Previous turn",
    "toggle": "Play / pause (Space)",
    "next": "Next turn",
    "slower": "Slower",
    "faster": "Faster",
}
BUTTONS_3D: list[tuple[str, int, str]] = [
    (name, width, TIPS_3D[name]) for name, width, _ in BUTTONS
] + [
    ("camera", 58, "Reset the camera"),
    ("proj", 58, "Switch iso / perspective"),
]


def lerp3(a: rl.Vector3, b: rl.Vector3, t: float) -> rl.Vector3:
    """Return the point at fraction ``t`` of the segment ``a`` to ``b``."""
    return rl.Vector3(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t,
                      a.z + (b.z - a.z) * t)


def darker(color: rl.Color, k: float) -> rl.Color:
    """Return ``color`` with its RGB channels multiplied by ``k``."""
    return rl.Color(int(color.r * k), int(color.g * k),
                    int(color.b * k), color.a)


class IsoCamera:
    """Orbit camera, orthographic (isometric) or perspective.

    Angles are in degrees. ``span`` is the visible world height in
    orthographic mode, and sets the distance in perspective mode.
    ``ISO_ELEVATION`` is the elevation of the classic isometric view.
    """

    ISO_ELEVATION = math.degrees(math.atan(1 / math.sqrt(2)))

    def __init__(self) -> None:
        """Start with the isometric view, orthographic."""
        self.azimuth = 315.0
        self.elevation = self.ISO_ELEVATION
        self.target = rl.Vector3(0, 0, 0)
        self.span = 30.0       # visible world height at the target
        self.ortho = True
        self.pinch: tuple[float, rl.Vector2, float] | None = None

    def right_axis(self) -> tuple[float, float]:
        """Return the (x, z) ground direction of the screen right."""
        az = math.radians(self.azimuth)
        return math.cos(az), -math.sin(az)

    def forward_axis(self) -> tuple[float, float]:
        """Return the (x, z) ground direction away from the camera."""
        az = math.radians(self.azimuth)
        return -math.sin(az), -math.cos(az)

    def fit(self, xs: list[float], zs: list[float], aspect: float) -> None:
        """Center the camera on the map and zoom to show all of it.

        Args:
            xs: World X coordinates of the zones.
            zs: World Z coordinates of the zones.
            aspect: Window width divided by window height.
        """
        x0, x1, z0, z1 = min(xs), max(xs), min(zs), max(zs)
        self.target = rl.Vector3((x0 + x1) / 2, 0, (z0 + z1) / 2)
        rx, rz = self.right_axis()
        fx, fz = self.forward_axis()
        sin_el = math.sin(math.radians(self.elevation))
        corners = [(x, z) for x in (x0, x1) for z in (z0, z1)]
        rights = [x * rx + z * rz for x, z in corners]
        ups = [(x * fx + z * fz) * sin_el for x, z in corners]
        width = max(rights) - min(rights) + 8
        height = max(ups) - min(ups) + 9
        self.span = max(height, width / aspect)

    def build(self) -> rl.Camera3D:
        """Build the raylib camera from the current angles and span.

        In perspective mode the camera is placed far enough to show about the
        same area as the orthographic one.
        """
        az = math.radians(self.azimuth)
        el = math.radians(self.elevation)
        if self.ortho:
            distance, fovy = 80.0, self.span
            proj = rl.CameraProjection.CAMERA_ORTHOGRAPHIC
        else:
            fovy = 45.0
            distance = 1.4 * self.span / (
                2 * math.tan(math.radians(fovy / 2)))
            proj = rl.CameraProjection.CAMERA_PERSPECTIVE
        pos = rl.Vector3(
            self.target.x + distance * math.cos(el) * math.sin(az),
            self.target.y + distance * math.sin(el),
            self.target.z + distance * math.cos(el) * math.cos(az))
        return rl.Camera3D(pos, self.target, rl.Vector3(0, 1, 0),
                           fovy, proj)

    def ground_at(self, screen: rl.Vector2) -> rl.Vector3 | None:
        """Return the point of the ground under a screen position.

        Returns:
            The 3D point at height 0, or None if the view ray is parallel to
            the ground.
        """
        ray = rl.get_screen_to_world_ray(screen, self.build())
        if abs(ray.direction.y) < 1e-6:
            return None
        k = -ray.position.y / ray.direction.y
        return rl.Vector3(ray.position.x + ray.direction.x * k, 0.0,
                          ray.position.z + ray.direction.z * k)

    def zoom_at(self, factor: float, screen: rl.Vector2) -> None:
        """Zoom by ``factor`` while keeping the point under ``screen``.

        A factor below 1 zooms in. The visible span stays between 6 and 160
        world units.
        """
        before = self.ground_at(screen)
        self.span = max(6.0, min(160.0, self.span * factor))
        after = self.ground_at(screen)
        if before is not None and after is not None:
            self.target.x += before.x - after.x
            self.target.z += before.z - after.z

    def pan_screen(self, prev: rl.Vector2, cur: rl.Vector2) -> None:
        """Move the target so the ground follows the mouse."""
        a, b = self.ground_at(prev), self.ground_at(cur)
        if a is not None and b is not None:
            self.target.x += a.x - b.x
            self.target.z += a.z - b.z

    def orbit_pixels(self, dx: float, dy: float) -> None:
        """Rotate the camera from a mouse movement in pixels.

        The elevation is kept between 12 and 88 degrees.
        """
        self.azimuth = (self.azimuth - dx * ORBIT_SPEED) % 360
        self.elevation = max(12.0, min(88.0,
                                       self.elevation + dy * ORBIT_SPEED))

    def update_touch(self) -> None:
        """Handle two fingers: pinch to zoom, twist to rotate, drag to pan."""
        a, b = rl.get_touch_position(0), rl.get_touch_position(1)
        dist = math.hypot(b.x - a.x, b.y - a.y)
        mid = rl.Vector2((a.x + b.x) / 2, (a.y + b.y) / 2)
        ang = math.atan2(b.y - a.y, b.x - a.x)
        if self.pinch is not None and dist > 1:
            old_dist, old_mid, old_ang = self.pinch
            if old_dist > 1:
                self.zoom_at(old_dist / dist, mid)
            self.azimuth = (self.azimuth
                            - math.degrees(ang - old_ang)) % 360
            self.pan_screen(old_mid, mid)
        self.pinch = (dist, mid, ang)

    def update_mouse(self, enabled: bool) -> None:
        """Handle the wheel, the touch screen and the mouse drags.

        Left-drag orbits, right or middle drag pans. The wheel does nothing
        over the top bar.

        Args:
            enabled: False to ignore the drags, for example after a click on
                the HUD.
        """
        mouse = rl.get_mouse_position()
        wheel = rl.get_mouse_wheel_move()
        if wheel and mouse.y >= HUD_HEIGHT:
            self.zoom_at(0.9 ** wheel, mouse)
        if rl.get_touch_point_count() >= 2:
            self.update_touch()
            return
        self.pinch = None
        if not enabled:
            return
        d = rl.get_mouse_delta()
        mb = rl.MouseButton
        if rl.is_mouse_button_down(mb.MOUSE_BUTTON_LEFT):
            self.orbit_pixels(d.x, d.y)
        if rl.is_mouse_button_down(mb.MOUSE_BUTTON_RIGHT) \
                or rl.is_mouse_button_down(mb.MOUSE_BUTTON_MIDDLE):
            self.pan_screen(rl.Vector2(mouse.x - d.x, mouse.y - d.y),
                            mouse)


class DroneArt:
    """Load and draw the drone model, with a built-in fallback.

    If the model file is missing or invalid, a small procedural dragon made
    of spheres, a cylinder and triangles is drawn instead.
    """

    def __init__(self, model_path: str | None) -> None:
        """Load the model if it exists and compute its scale and lift.

        Args:
            model_path: Path of the 3D model, or None to use the fallback.
        """
        self.model: rl.Model | None = None
        self.scale = 1.0
        self.lift = 0.0
        if model_path and Path(model_path).is_file():
            model = rl.load_model(model_path)
            if rl.is_model_valid(model):
                box = rl.get_model_bounding_box(model)
                size = max(box.max.x - box.min.x, box.max.y - box.min.y,
                           box.max.z - box.min.z, 0.001)
                target_size = DRONE_SIZE
                if model and Path(model_path).is_file():
                    target_size *= SPRITE_SIZE_MULTIPLIER
                self.scale = target_size / size
                self.lift = -box.min.y * self.scale
                self.model = model

    def close(self) -> None:
        """Unload the model if one was loaded."""
        if self.model is not None:
            rl.unload_model(self.model)

    def draw(self, pos: rl.Vector3, yaw: float, color: rl.Color,
             waiting: bool, t: float, ident: int) -> None:
        """Draw one drone at ``pos``.

        Args:
            pos: World position.
            yaw: Heading in degrees around the vertical axis.
            color: Body color of the fallback dragon (the route color).
            waiting: Whether the drone is waiting, which greys it out.
            t: Time in seconds, used for the wing flap.
            ident: Drone id, so that the flaps are not synchronized.
        """
        if self.model is not None:
            tint = rl.Color(170, 170, 190, 255) if waiting else rl.WHITE
            at = rl.Vector3(pos.x, pos.y - 0.5 + self.lift, pos.z)
            s = self.scale
            rl.draw_model_ex(self.model, at, rl.Vector3(0, 1, 0),
                             yaw + MODEL_YAW_OFFSET,
                             rl.Vector3(s, s, s), tint)
            return
        body = rl.Color(150, 155, 170, 255) if waiting else color
        self.draw_fallback(pos, yaw, body, math.sin(t * 7 + ident))

    def draw_fallback(self, pos: rl.Vector3, yaw: float, body: rl.Color,
                      flap: float) -> None:
        """Draw the built-in dragon.

        Args:
            pos: World position.
            yaw: Heading in degrees around the vertical axis.
            body: Body color.
            flap: Wing flap, between -1 and 1.
        """
        wing = darker(body, 0.6)
        belly = rl.Color(245, 222, 170, 255)
        rl.rl_push_matrix()
        rl.rl_translatef(pos.x, pos.y, pos.z)
        rl.rl_rotatef(yaw, 0, 1, 0)
        rl.draw_sphere_ex(rl.Vector3(0, 0, 0), 0.42, 8, 8, body)
        rl.draw_sphere_ex(rl.Vector3(0, -0.12, 0.2), 0.3, 6, 8, belly)
        rl.draw_sphere_ex(rl.Vector3(0, 0.22, 0.5), 0.26, 8, 8, body)
        for side in (-1, 1):
            rl.draw_sphere_ex(rl.Vector3(side * 0.1, 0.3, 0.7), 0.05,
                              4, 4, rl.WHITE)
        rl.draw_cylinder_ex(rl.Vector3(0, 0, -0.3),
                            rl.Vector3(0, -0.1, -1.0), 0.18, 0.05, 6, body)
        rl.draw_sphere_ex(rl.Vector3(0, -0.1, -1.05), 0.14, 6, 6,
                          rl.Color(255, 120, 30, 255))
        rl.draw_sphere_ex(rl.Vector3(0, -0.1, -1.05), 0.08, 5, 5,
                          rl.Color(255, 230, 90, 255))
        lift = 0.35 + 0.35 * flap
        for side in (-1, 1):
            a = rl.Vector3(side * 0.25, 0.25, 0.1)
            b = rl.Vector3(side * 0.25, 0.25, -0.35)
            c = rl.Vector3(side * 1.15, 0.25 + lift, -0.15)
            rl.draw_triangle_3d(a, b, c, wing)
            rl.draw_triangle_3d(b, a, c, wing)
        rl.rl_pop_matrix()


class Scene3D:
    """Draw the 3D world: floor, links, zones, drones and glows.

    Map coordinates are multiplied by ``SCALE``; the map X and Y become
    the world X and Z.
    """

    def __init__(self, graph: Graph, replay: Replay, cam: IsoCamera,
                 art: DroneArt) -> None:
        """Compute the world position of each zone and list each link once.

        Args:
            graph: Graph of the map.
            replay: Precomputed frames of the simulation.
            cam: Camera, used to turn the portals toward the viewer.
            art: Drawer of the drone model.
        """
        self.graph = graph
        self.replay = replay
        self.cam = cam
        self.art = art
        self.yaw: dict[int, float] = {}
        self.pos = {name: rl.Vector3(z.coordinate[0] * SCALE, 0,
                                     z.coordinate[1] * SCALE)
                    for name, z in graph.zones.items()}
        self.links = []
        seen: set[frozenset[str]] = set()
        for conns in graph.neighbors.values():
            for conn in conns:
                key = frozenset(conn.ends)
                if key not in seen:
                    seen.add(key)
                    self.links.append(conn)
        self.ring = [(math.cos(a) * PORTAL_R, math.sin(a) * PORTAL_R)
                     for a in [i * math.tau / 20 for i in range(20)]]

    def special(self, name: str) -> bool:
        """Return whether ``name`` is the start or the end zone."""
        return name in (self.graph.start, self.graph.end)

    def bounds(self) -> tuple[list[float], list[float]]:
        """Return the world X and Z coordinates of every zone."""
        pts = list(self.pos.values())
        return [p.x for p in pts], [p.z for p in pts]

    # ---------- opaque pass ----------
    def draw_floor(self) -> None:
        """Draw the dark floor under the whole map."""
        xs, zs = self.bounds()
        cx, cz = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
        size = rl.Vector2(max(xs) - min(xs) + 10, max(zs) - min(zs) + 10)
        rl.draw_plane(rl.Vector3(cx, -0.03, cz), size,
                      rl.Color(27, 30, 43, 255))

    def strip(self, a: rl.Vector3, b: rl.Vector3, width: float,
              y: float, color: rl.Color) -> None:
        """Draw a flat strip between two points, used for the links.

        Args:
            a: First end point.
            b: Second end point.
            width: Width of the strip.
            y: Height of the strip above the floor.
            color: Fill color.
        """
        dx, dz = b.x - a.x, b.z - a.z
        rl.rl_push_matrix()
        rl.rl_translatef((a.x + b.x) / 2, y, (a.z + b.z) / 2)
        rl.rl_rotatef(math.degrees(math.atan2(dx, dz)), 0, 1, 0)
        rl.draw_cube(rl.Vector3(0, 0, 0), width, 0.04,
                     math.hypot(dx, dz), color)
        rl.rl_pop_matrix()

    def link_color(self, used: int, cap: int) -> rl.Color:
        """Return the color of a link from its usage.

        Grey when free, orange when partly used and red when full.
        """
        if used >= cap:
            return LINK_FULL
        return LINK_PART if used > 0 else LINK_FREE_3D

    def draw_links(self, turn: int) -> None:
        """Draw every link as a dark strip with a colored center line.

        The color shows the usage of the link at ``turn``.
        """
        usage = self.replay.link_use[turn]
        for conn in self.links:
            a, b = conn.ends
            cap = conn.max_link_capacity
            color = self.link_color(usage.get(frozenset(conn.ends), 0), cap)
            width = 0.32 + 0.16 * min(cap - 1, 3)
            self.strip(self.pos[a], self.pos[b], width, 0.05,
                       darker(color, 0.5))
            self.strip(self.pos[a], self.pos[b], width * 0.35, 0.075,
                       color)

    def draw_link_glow(self, turn: int) -> None:
        """Draw a translucent halo around the links used at ``turn``."""
        usage = self.replay.link_use[turn]
        for conn in self.links:
            a, b = conn.ends
            used = usage.get(frozenset(conn.ends), 0)
            if used == 0:
                continue
            cap = conn.max_link_capacity
            width = 0.32 + 0.16 * min(cap - 1, 3)
            self.strip(self.pos[a], self.pos[b], width * 3.2, 0.1,
                       rl.fade(self.link_color(used, cap), 0.2))

    def draw_zone(self, name: str, turn: int) -> None:
        """Draw the pad of a zone and its portal.

        Start and end zones are larger pads with two colored rings. Other
        zones get a portal frame facing the camera, and capacity pips.
        """
        zone = self.graph.zones[name]
        p = self.pos[name]
        color = zone_color(zone.color)
        pad = 2.0 if self.special(name) else 1.2
        rl.draw_cylinder(rl.Vector3(p.x, 0, p.z), pad, pad, 0.12, 28,
                         rl.Color(38, 42, 60, 255))
        if self.special(name):
            rl.draw_circle_3d(rl.Vector3(p.x, 0.14, p.z), pad - 0.15,
                              rl.Vector3(1, 0, 0), 0, color)
            rl.draw_circle_3d(rl.Vector3(p.x, 0.14, p.z), pad - 0.35,
                              rl.Vector3(1, 0, 0), 0, color)
            return
        rl.rl_push_matrix()
        rl.rl_translatef(p.x, 0, p.z)
        rl.rl_rotatef(self.cam.azimuth, 0, 1, 0)
        self.draw_frame_ring(zone.type, color)
        rl.rl_pop_matrix()
        self.draw_pips(name, turn)

    def tube(self, a: tuple[float, float], b: tuple[float, float],
             r: float, color: rl.Color, z: float = 0.0) -> None:
        """Draw a thin cylinder between two points of the portal plane.

        Args:
            a: First (x, y) point, relative to the center of the portal.
            b: Second (x, y) point, relative to the center of the portal.
            r: Radius of the tube.
            color: Fill color.
            z: Depth offset in the portal plane.
        """
        rl.draw_cylinder_ex(rl.Vector3(a[0], PORTAL_H + a[1], z),
                            rl.Vector3(b[0], PORTAL_H + b[1], z),
                            r, r, 6, color)

    def draw_frame_ring(self, ztype: ZoneType, color: rl.Color) -> None:
        """Draw the portal ring and the decoration of the zone type.

        Priority zones get a gold outer ring, restricted zones red spikes and
        a red outer ring, and blocked zones a darker ring crossed by two red
        bars.
        """
        n = len(self.ring)
        base = darker(color, 0.5) if ztype is ZoneType.BLOCKED else color
        for i in range(n):
            self.tube(self.ring[i], self.ring[(i + 1) % n], 0.09, base)
        if ztype is ZoneType.PRIORITY:
            gold = rl.Color(232, 193, 58, 255)
            for i in range(n):
                a, b = self.ring[i], self.ring[(i + 1) % n]
                k = 1.3
                self.tube((a[0] * k, a[1] * k), (b[0] * k, b[1] * k),
                          0.05, gold)
        elif ztype is ZoneType.RESTRICTED:
            red = rl.Color(255, 107, 107, 255)
            for i in range(4):
                ang = math.radians(45 + 90 * i)
                c, s = math.cos(ang), math.sin(ang)
                rl.draw_cylinder_ex(
                    rl.Vector3(c * PORTAL_R, PORTAL_H + s * PORTAL_R, 0),
                    rl.Vector3(c * (PORTAL_R + 0.5),
                               PORTAL_H + s * (PORTAL_R + 0.5), 0),
                    0.1, 0.0, 6, red)
            for i in range(n):
                a, b = self.ring[i], self.ring[(i + 1) % n]
                k = 1.15
                self.tube((a[0] * k, a[1] * k), (b[0] * k, b[1] * k),
                          0.05, red)
        elif ztype is ZoneType.BLOCKED:
            d = PORTAL_R * 0.7
            bar = rl.Color(229, 83, 75, 255)
            self.tube((-d, -d), (d, d), 0.1, bar)
            self.tube((d, -d), (-d, d), 0.1, bar)

    def draw_pips(self, name: str, turn: int) -> None:
        """Draw the occupancy pips on the ground in front of a zone.

        A filled sphere is an occupied slot, an orange circle a reserved one
        and a grey circle a free one. At most 8 slots are shown.
        """
        p = self.pos[name]
        cap = min(self.graph.zones[name].max_drone, 8)
        count = len(self.replay.occupants[turn].get(name, []))
        reserved = self.replay.reserved[turn].get(name, 0)
        rx, rz = self.cam.right_axis()
        sx, sz = math.sin(math.radians(self.cam.azimuth)), \
            math.cos(math.radians(self.cam.azimuth))
        for i in range(cap):
            o = (i - (cap - 1) / 2) * 0.32
            c = rl.Vector3(p.x + rx * o + sx * 1.0, 0.16,
                           p.z + rz * o + sz * 1.0)
            if i < count:
                rl.draw_sphere_ex(c, 0.12, 5, 6, TEXT)
            elif i < count + reserved:
                rl.draw_circle_3d(c, 0.15, rl.Vector3(1, 0, 0), 0,
                                  LINK_PART)
            else:
                rl.draw_circle_3d(c, 0.11, rl.Vector3(1, 0, 0), 0, MUTED)

    # ---------- drones ----------
    def anchor(self, frame: int, ident: int) -> rl.Vector3:
        """Return the world position of a drone in a frame, at ground level.

        A drone in transit sits in the middle of its link. Several drones in
        the same zone are spread side by side. Drones stacked on the start or
        end pad share the pad center.
        """
        zone, dest = self.replay.frames[frame][ident]
        if dest is not None:
            return lerp3(self.pos[zone], self.pos[dest], 0.5)
        p = self.pos[zone]
        people = self.replay.occupants[frame][zone]
        if len(people) == 1 or self.stacked(frame, ident):
            return p
        rx, rz = self.cam.right_axis()
        o = (people.index(ident) - (len(people) - 1) / 2) * 0.7
        return rl.Vector3(p.x + rx * o, 0, p.z + rz * o)

    def altitude(self, frame: int, ident: int) -> float:
        """Return the flying height of a drone in a frame.

        Drones in transit fly higher. Waiting drones, except at the start,
        hover a little lower.
        """
        zone, dest = self.replay.frames[frame][ident]
        if dest is not None:
            return TRANSIT_Y
        if ident in self.replay.waiting[frame] and zone != self.replay.start:
            return FLY_Y - 0.3
        return FLY_Y

    def stacked(self, frame: int, ident: int) -> bool:
        """Return whether a drone is stacked on the start or end pad.

        With ``STACK_LIMIT`` at 0, every drone on those pads is stacked, so it
        stays hidden there until it leaves.
        """
        zone, dest = self.replay.frames[frame][ident]
        if dest is not None or not self.special(zone):
            return False
        return len(self.replay.occupants[frame][zone]) > STACK_LIMIT

    def drone_pose(self, turn: int, progress: float,
                   ident: int) -> rl.Vector3 | None:
        """Return the position of a drone between two consecutive turns.

        The movement is eased like in the 2D view and gets a small bobbing.
        The heading follows the direction of the movement.

        Returns:
            The world position, or None for a drone idle on the start or end
            pad, which is not drawn.
        """
        nxt = min(turn + 1, self.replay.turns)
        here = self.replay.frames[turn][ident]
        there = self.replay.frames[nxt][ident]
        if here == there and self.stacked(turn, ident):
            return None
        t = progress * progress * (3 - 2 * progress)
        a, b = self.anchor(turn, ident), self.anchor(nxt, ident)
        dx, dz = b.x - a.x, b.z - a.z
        if math.hypot(dx, dz) > 0.01:
            self.yaw[ident] = math.degrees(math.atan2(dx, dz))
        pos = lerp3(a, b, t)
        ay = self.altitude(turn, ident)
        by = self.altitude(nxt, ident)
        pos.y = ay + (by - ay) * t + 0.1 * math.sin(rl.get_time() * 2
                                                    + ident)
        return pos

    def draw_drones(self, turn: int, progress: float) -> list[
            tuple[int, rl.Vector3]]:
        """Draw every visible drone with its shadow.

        The shadow takes the route color, or grey for a waiting drone.

        Returns:
            The (id, world position) of each drawn drone, used for labels.
        """
        shown: list[tuple[int, rl.Vector3]] = []
        t = rl.get_time()
        for ident in self.replay.frames[turn]:
            pos = self.drone_pose(turn, progress, ident)
            if pos is None:
                continue
            route = ROUTES[self.replay.route_of[ident] % len(ROUTES)]
            waiting = ident in self.replay.waiting[turn]
            shadow = rl.Color(138, 147, 173, 150) if waiting \
                else rgb(route, 170)
            rl.draw_cylinder(rl.Vector3(pos.x, 0.02, pos.z), 0.55, 0.55,
                             0.02, 18, shadow)
            self.art.draw(pos, self.yaw.get(ident, 90.0), rgb(route),
                          waiting, t, ident)
            shown.append((ident, pos))
        return shown

    # ---------- translucent pass ----------
    def draw_glow(self, name: str, t: float) -> None:
        """Draw the translucent parts of a zone.

        Start and end zones get a light beam. Other zones get a glowing disc
        in the portal with small sparks, or a dark disc when blocked. Call it
        after the opaque pass.
        """
        zone = self.graph.zones[name]
        p = self.pos[name]
        color = zone_color(zone.color)
        if self.special(name):
            beam = rl.fade(color, 0.16)
            rl.draw_cylinder(rl.Vector3(p.x, 0.12, p.z), 0.8, 0.8, 5.0,
                             16, beam)
            return
        rl.rl_push_matrix()
        rl.rl_translatef(p.x, PORTAL_H, p.z)
        rl.rl_rotatef(self.cam.azimuth, 0, 1, 0)
        if zone.type is ZoneType.BLOCKED:
            rl.rl_rotatef(90, 1, 0, 0)
            rl.draw_cylinder(rl.Vector3(0, -0.02, 0), PORTAL_R * 0.95,
                             PORTAL_R * 0.95, 0.04, 28,
                             rl.Color(10, 10, 14, 200))
        else:
            rl.rl_rotatef(90, 1, 0, 0)
            for k, (scale, alpha) in enumerate(((0.95, 0.22), (0.7, 0.25),
                                                (0.42, 0.3))):
                rl.draw_cylinder(rl.Vector3(0, -0.02 - k * 0.01, 0),
                                 PORTAL_R * scale, PORTAL_R * scale, 0.04,
                                 28, rl.fade(color, alpha))
        rl.rl_pop_matrix()
        if zone.type is not ZoneType.BLOCKED:
            rl.rl_push_matrix()
            rl.rl_translatef(p.x, PORTAL_H, p.z)
            rl.rl_rotatef(self.cam.azimuth, 0, 1, 0)
            for i in range(5):
                a = t * 2.2 + i * math.tau / 5
                r = PORTAL_R * (0.25 + 0.4 * ((i * 0.37 + t * 0.3) % 1.0))
                rl.draw_sphere_ex(
                    rl.Vector3(math.cos(a) * r, math.sin(a) * r, 0.0),
                    0.06, 4, 4, rl.fade(rl.WHITE, 0.8))
            rl.rl_pop_matrix()


class App3D:
    """Own the window, the animation state and the inputs of the 3D view."""

    def __init__(self, graph: Graph, lines: list[str],
                 model_path: str | None = "assets/dragon.glb",
                 width: int = 1280, height: int = 720) -> None:
        """Prepare the replay and the camera.

        Args:
            graph: Parsed graph of the map.
            lines: Simulation output, one line of moves per turn.
            model_path: Path of the drone model, or None for the fallback.
            width: Window width in pixels.
            height: Window height in pixels.
        """
        self.width = width
        self.height = height
        self.graph = graph
        self.replay = Replay(graph, lines)
        self.model_path = model_path
        self.cam = IsoCamera()
        self.turn = 0
        self.progress = 0.0
        self.playing = True
        self.speed = 1.5
        self.hud_press = False

    def open(self) -> None:
        """Open the window, create the scene and fit the camera to the map."""
        rl.set_config_flags(rl.ConfigFlags.FLAG_MSAA_4X_HINT)
        rl.init_window(self.width, self.height, "Fly-in 3D")
        rl.set_target_fps(60)
        self.art = DroneArt(self.model_path)
        self.scene = Scene3D(self.graph, self.replay, self.cam, self.art)
        xs, zs = self.scene.bounds()
        self.cam.fit(xs, zs, self.width / self.height)
        self.home_cam = (self.cam.target.x, self.cam.target.z,
                         self.cam.span)

    def close(self) -> None:
        """Free the model and close the window."""
        self.art.close()
        rl.close_window()

    # ---------- HUD buttons ----------
    def hud_buttons(self) -> list[tuple[str, rl.Rectangle, str]]:
        """Return the HUD buttons as (name, rectangle, tooltip)."""
        gaps = BTN_GAP * (len(BUTTONS_3D) - 1)
        total = sum(w for _, w, _ in BUTTONS_3D) + gaps
        x = float(self.width - 16 - total)
        res: list[tuple[str, rl.Rectangle, str]] = []
        for name, w, tip in BUTTONS_3D:
            res.append((name, rl.Rectangle(x, BTN_Y, w, BTN_H), tip))
            x += w + BTN_GAP
        return res

    def button_at(self, mouse: rl.Vector2) -> str | None:
        """Return the name of the HUD button under ``mouse``, or None."""
        for name, rect, _ in self.hud_buttons():
            if rl.check_collision_point_rec(mouse, rect):
                return name
        return None

    def button_enabled(self, name: str, shown: int) -> bool:
        """Return whether a button is usable at the displayed turn."""
        if name == "prev":
            return shown > 0
        if name == "next":
            return shown < self.replay.turns
        if name == "slower":
            return self.speed > 0.5
        if name == "faster":
            return self.speed < 8.0
        return True

    def replay_from_start(self) -> None:
        """Restart the animation from turn 0 and start playing."""
        self.turn, self.progress, self.playing = 0, 0.0, True

    def reset_camera(self) -> None:
        """Restore the position, zoom and angles of the start."""
        x, z, span = self.home_cam
        self.cam.target = rl.Vector3(x, 0, z)
        self.cam.span = span
        self.cam.azimuth = 315.0
        self.cam.elevation = IsoCamera.ISO_ELEVATION

    def press_button(self, name: str) -> None:
        """Run the action of a HUD button.

        Args:
            name: One of replay, toggle, prev, next, slower, faster, camera or
                proj.
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
        elif name == "camera":
            self.reset_camera()
        elif name == "proj":
            self.cam.ortho = not self.cam.ortho

    def handle_mouse(self) -> None:
        """Process clicks on the HUD buttons and set the mouse cursor.

        A press that starts on the top bar sets ``hud_press``, so the camera
        does not move during that drag.
        """
        mouse = rl.get_mouse_position()
        mb = rl.MouseButton
        buttons = (mb.MOUSE_BUTTON_LEFT, mb.MOUSE_BUTTON_RIGHT,
                   mb.MOUSE_BUTTON_MIDDLE)
        name = self.button_at(mouse)
        if rl.is_mouse_button_pressed(mb.MOUSE_BUTTON_LEFT) \
                and name is not None:
            self.press_button(name)
        if mouse.y < HUD_HEIGHT \
                and any(rl.is_mouse_button_pressed(b) for b in buttons):
            self.hud_press = True
        if not any(rl.is_mouse_button_down(b) for b in buttons):
            self.hud_press = False
        rl.set_mouse_cursor(
            rl.MouseCursor.MOUSE_CURSOR_POINTING_HAND if name is not None
            else rl.MouseCursor.MOUSE_CURSOR_DEFAULT)

    def handle_keys(self) -> None:
        """Pause or resume the animation with the Space bar."""
        if rl.is_key_pressed(rl.KeyboardKey.KEY_SPACE):
            self.press_button("toggle")

    def advance(self) -> None:
        """Advance the animation clock by one frame when playing."""
        if not self.playing or self.turn >= self.replay.turns:
            return
        self.progress += rl.get_frame_time() * self.speed
        if self.progress >= 1.0:
            self.turn, self.progress = self.turn + 1, 0.0

    def draw_frame(self) -> None:
        """Draw one full frame: the 3D scene, the labels and the HUD.

        The opaque objects come first. The translucent glows come last, with
        the depth mask disabled.
        """
        t = rl.get_time()
        shown = min(self.turn + (1 if self.progress > 0.5 else 0),
                    self.replay.turns)
        camera = self.cam.build()
        rl.begin_drawing()
        rl.clear_background(BG)
        rl.begin_mode_3d(camera)
        sc = self.scene
        sc.draw_floor()
        sc.draw_links(shown)
        for name in self.graph.zones:
            sc.draw_zone(name, shown)
        drones = sc.draw_drones(self.turn, self.progress)
        rl.rl_disable_depth_mask()
        sc.draw_link_glow(shown)
        for name in self.graph.zones:
            sc.draw_glow(name, t)
        rl.rl_enable_depth_mask()
        rl.end_mode_3d()
        self.draw_labels(camera, drones, shown)
        self.draw_hud(shown)
        self.draw_hover(camera)
        rl.end_drawing()

    def draw_labels(self, camera: rl.Camera3D,
                    drones: list[tuple[int, rl.Vector3]],
                    shown: int) -> None:
        """Draw the drone numbers and the start and end counters.

        Args:
            camera: Camera used to project world points on the screen.
            drones: (id, world position) of each drawn drone.
            shown: Displayed turn.
        """
        for ident, pos in drones:
            s = rl.get_world_to_screen(
                rl.Vector3(pos.x, pos.y + 0.9, pos.z), camera)
            text = f"{ident}"
            w = rl.measure_text(text, 14)
            rl.draw_rectangle(int(s.x - w / 2 - 4), int(s.y - 9),
                              w + 8, 18, HUD_BG)
            rl.draw_text(text, int(s.x - w / 2), int(s.y - 7), 14, TEXT)
        for name in (self.replay.start, self.replay.end):
            count = len(self.replay.occupants[shown].get(name, []))
            p = self.scene.pos[name]
            s = rl.get_world_to_screen(rl.Vector3(p.x, 5.4, p.z), camera)
            text = f"{name}  x{count}"
            w = rl.measure_text(text, 18)
            rl.draw_text(text, int(s.x - w / 2), int(s.y), 18, TEXT)

    def draw_icon(self, name: str, cx: float, cy: float,
                  ink: rl.Color) -> None:
        """Draw the icon or label of a HUD button centered on (cx, cy)."""
        labels = {"replay": "Replay", "camera": "Reset",
                  "proj": "Iso" if self.cam.ortho else "Persp"}
        if name in labels:
            w = rl.measure_text(labels[name], 16)
            rl.draw_text(labels[name], int(cx - w / 2), int(cy - 8), 16,
                         ink)
        elif name == "prev":
            rl.draw_triangle(rl.Vector2(cx + 5, cy - 7),
                             rl.Vector2(cx - 6, cy),
                             rl.Vector2(cx + 5, cy + 7), ink)
        elif name == "next" or (name == "toggle" and not self.playing):
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
                        glow: bool) -> None:
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
                       rect.y + rect.height / 2, ink)

    def draw_tip(self, text: str, rect: rl.Rectangle) -> None:
        """Draw a tooltip under the HUD, kept inside the window."""
        w = rl.measure_text(text, 14)
        x = min(int(rect.x + rect.width / 2 - w / 2 - 8),
                self.width - w - 24)
        rl.draw_rectangle(x, HUD_HEIGHT + 6, w + 16, 24, HUD_BG)
        rl.draw_text(text, x + 8, HUD_HEIGHT + 11, 14, TEXT)

    def draw_hud(self, shown: int) -> None:
        """Draw the top bar, its tooltip or hint, and the legend bar."""
        rl.draw_rectangle(0, 0, self.width, HUD_HEIGHT, HUD_BG)
        total = self.replay.turns
        moves = self.replay.moves_per_turn[shown - 1] if shown > 0 else 0
        finished = shown >= total
        state = "playing" if self.playing else "paused"
        if finished:
            state = "finished"
        items = [
            (f"Turn {shown} / {total}", 16),
            (f"Delivered {self.replay.delivered(shown)} / "
             f"{self.graph.nb_drones}", 220),
            (f"Moves {moves}", 450),
            (f"{state} x{self.speed:.1f}", 600),
        ]
        for text, x in items:
            rl.draw_text(text, x, 13, 20, TEXT)
        mouse = rl.get_mouse_position()
        tip: tuple[str, rl.Rectangle] | None = None
        for name, rect, text in self.hud_buttons():
            enabled = self.button_enabled(name, shown)
            glow = name == "replay" and finished
            self.draw_hud_button(name, rect, enabled, glow)
            if enabled and rl.check_collision_point_rec(mouse, rect):
                tip = (text, rect)
        if tip is not None:
            self.draw_tip(tip[0], tip[1])
        else:
            hint = ("drag orbit | right-drag pan | wheel zoom"
                    " | Space play/pause")
            rl.draw_text(hint, self.width - rl.measure_text(hint, 14) - 16,
                         HUD_HEIGHT + 10, 14, MUTED)
        rl.draw_rectangle(0, self.height - 28, self.width, 28, HUD_BG)
        rl.draw_text(LEGEND_TEXT, 16, self.height - 21, 14, MUTED)

    def draw_hover(self, camera: rl.Camera3D) -> None:
        """Draw the type and capacity of the zone under the mouse."""
        mouse = rl.get_mouse_position()
        if mouse.y < HUD_HEIGHT:
            return
        for name, zone in self.graph.zones.items():
            p = self.scene.pos[name]
            s = rl.get_world_to_screen(rl.Vector3(p.x, PORTAL_H, p.z),
                                       camera)
            if abs(mouse.x - s.x) < 30 and abs(mouse.y - s.y) < 40:
                text = f"{name}  {zone.type.value}  cap {zone.max_drone}"
                w = rl.measure_text(text, 16)
                rl.draw_rectangle(int(mouse.x + 12), int(mouse.y + 12),
                                  w + 12, 24, HUD_BG)
                rl.draw_text(text, int(mouse.x + 18), int(mouse.y + 16),
                             16, TEXT)
                return

    def run(self) -> None:
        """Open the window and run the main loop until it is closed."""
        self.open()
        try:
            while not rl.window_should_close():
                self.handle_keys()
                self.handle_mouse()
                self.cam.update_mouse(not self.hud_press)
                self.advance()
                self.draw_frame()
        finally:
            self.close()
