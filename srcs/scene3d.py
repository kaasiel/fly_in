from __future__ import annotations

import math
from pathlib import Path
import pyray as rl
from .model import Graph, ZoneType
from .replay import Replay
from .visual import (BG, HUD_BG, HUD_HEIGHT, LINK_FULL,
                     LINK_PART, MUTED, ROUTES, TEXT, rgb, zone_color)

SCALE = 3.8            # world units per map unit (hub spacing)
PORTAL_R = 0.85
PORTAL_H = PORTAL_R + 0.3
DRONE_SIZE = 1.5       # largest dimension of the drone model
FLY_Y = 1.25
TRANSIT_Y = 2.2
MODEL_YAW_OFFSET = 0.0  # tune if your model does not face +z
STACK_LIMIT = 0        # drones shown on start/end pads (0 = emerge one by one)
ORBIT_SPEED = 0.35     # degrees per pixel when dragging
LINK_FREE_3D = rl.Color(122, 132, 165, 255)
LEGEND_TEXT = ("portal = hub | gold halo = priority | spiked = restricted"
               " | sealed = blocked | pips = capacity"
               " | shadow color = route | gray = waiting")


def lerp3(a: rl.Vector3, b: rl.Vector3, t: float) -> rl.Vector3:
    return rl.Vector3(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t,
                      a.z + (b.z - a.z) * t)


def darker(color: rl.Color, k: float) -> rl.Color:
    return rl.Color(int(color.r * k), int(color.g * k),
                    int(color.b * k), color.a)


class IsoCamera:
    ISO_ELEVATION = math.degrees(math.atan(1 / math.sqrt(2)))

    def __init__(self) -> None:
        self.azimuth = 315.0
        self.elevation = self.ISO_ELEVATION
        self.target = rl.Vector3(0, 0, 0)
        self.span = 30.0       # visible world height at the target
        self.ortho = True
        self.pinch: tuple[float, rl.Vector2, float] | None = None

    def right_axis(self) -> tuple[float, float]:
        az = math.radians(self.azimuth)
        return math.cos(az), -math.sin(az)

    def forward_axis(self) -> tuple[float, float]:
        az = math.radians(self.azimuth)
        return -math.sin(az), -math.cos(az)

    def fit(self, xs: list[float], zs: list[float], aspect: float) -> None:
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
        ray = rl.get_screen_to_world_ray(screen, self.build())
        if abs(ray.direction.y) < 1e-6:
            return None
        k = -ray.position.y / ray.direction.y
        return rl.Vector3(ray.position.x + ray.direction.x * k, 0.0,
                          ray.position.z + ray.direction.z * k)

    def zoom_at(self, factor: float, screen: rl.Vector2) -> None:
        before = self.ground_at(screen)
        self.span = max(6.0, min(160.0, self.span * factor))
        after = self.ground_at(screen)
        if before is not None and after is not None:
            self.target.x += before.x - after.x
            self.target.z += before.z - after.z

    def pan_screen(self, prev: rl.Vector2, cur: rl.Vector2) -> None:
        a, b = self.ground_at(prev), self.ground_at(cur)
        if a is not None and b is not None:
            self.target.x += a.x - b.x
            self.target.z += a.z - b.z

    def orbit_pixels(self, dx: float, dy: float) -> None:
        self.azimuth = (self.azimuth - dx * ORBIT_SPEED) % 360
        self.elevation = max(12.0, min(88.0,
                                       self.elevation + dy * ORBIT_SPEED))

    def snap_iso(self) -> None:
        self.elevation = self.ISO_ELEVATION
        self.azimuth = (round((self.azimuth - 45) / 90) * 90 + 45) % 360

    def update_touch(self) -> None:
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

    def update(self, dt: float) -> None:
        key = rl.KeyboardKey
        height = rl.get_screen_height()
        mouse = rl.get_mouse_position()
        centre = rl.Vector2(rl.get_screen_width() / 2, height / 2)
        wheel = rl.get_mouse_wheel_move()
        if wheel:
            self.zoom_at(0.9 ** wheel, mouse)
        if rl.is_key_down(key.KEY_EQUAL) or rl.is_key_down(key.KEY_KP_ADD):
            self.zoom_at(0.4 ** dt, centre)
        if rl.is_key_down(key.KEY_MINUS) \
                or rl.is_key_down(key.KEY_KP_SUBTRACT):
            self.zoom_at(2.5 ** dt, centre)
        if rl.is_key_down(key.KEY_Q):
            self.azimuth = (self.azimuth - 60 * dt) % 360
        if rl.is_key_down(key.KEY_E):
            self.azimuth = (self.azimuth + 60 * dt) % 360
        step = self.span * 0.6 * dt
        rx, rz = self.right_axis()
        fx, fz = self.forward_axis()
        for k, sx, sz in ((key.KEY_W, fx, fz), (key.KEY_S, -fx, -fz),
                          (key.KEY_D, rx, rz), (key.KEY_A, -rx, -rz)):
            if rl.is_key_down(k):
                self.target.x += sx * step
                self.target.z += sz * step
        if rl.is_key_pressed(key.KEY_P):
            self.ortho = not self.ortho
        if rl.is_key_pressed(key.KEY_I):
            self.snap_iso()
        if rl.get_touch_point_count() >= 2:
            self.update_touch()
            return
        self.pinch = None
        d = rl.get_mouse_delta()
        mb = rl.MouseButton
        if rl.is_mouse_button_down(mb.MOUSE_BUTTON_LEFT):
            self.orbit_pixels(d.x, d.y)
        if rl.is_mouse_button_down(mb.MOUSE_BUTTON_RIGHT) \
                or rl.is_mouse_button_down(mb.MOUSE_BUTTON_MIDDLE):
            self.pan_screen(rl.Vector2(mouse.x - d.x, mouse.y - d.y),
                            mouse)


class DroneArt:
    def __init__(self, model_path: str | None) -> None:
        self.model: rl.Model | None = None
        self.scale = 1.0
        self.lift = 0.0
        if model_path and Path(model_path).is_file():
            model = rl.load_model(model_path)
            if rl.is_model_valid(model):
                box = rl.get_model_bounding_box(model)
                size = max(box.max.x - box.min.x, box.max.y - box.min.y,
                           box.max.z - box.min.z, 0.001)
                self.scale = DRONE_SIZE / size
                self.lift = -box.min.y * self.scale
                self.model = model

    def close(self) -> None:
        if self.model is not None:
            rl.unload_model(self.model)

    def draw(self, pos: rl.Vector3, yaw: float, color: rl.Color,
             waiting: bool, t: float, ident: int) -> None:
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
    def __init__(self, graph: Graph, replay: Replay, cam: IsoCamera,
                 art: DroneArt) -> None:
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
        return name in (self.graph.start, self.graph.end)

    def bounds(self) -> tuple[list[float], list[float]]:
        pts = list(self.pos.values())
        return [p.x for p in pts], [p.z for p in pts]

    # ---------- opaque pass ----------
    def draw_floor(self) -> None:
        xs, zs = self.bounds()
        cx, cz = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
        size = rl.Vector2(max(xs) - min(xs) + 10, max(zs) - min(zs) + 10)
        rl.draw_plane(rl.Vector3(cx, -0.03, cz), size,
                      rl.Color(27, 30, 43, 255))

    def strip(self, a: rl.Vector3, b: rl.Vector3, width: float,
              y: float, color: rl.Color) -> None:
        dx, dz = b.x - a.x, b.z - a.z
        rl.rl_push_matrix()
        rl.rl_translatef((a.x + b.x) / 2, y, (a.z + b.z) / 2)
        rl.rl_rotatef(math.degrees(math.atan2(dx, dz)), 0, 1, 0)
        rl.draw_cube(rl.Vector3(0, 0, 0), width, 0.04,
                     math.hypot(dx, dz), color)
        rl.rl_pop_matrix()

    def link_color(self, used: int, cap: int) -> rl.Color:
        if used >= cap:
            return LINK_FULL
        return LINK_PART if used > 0 else LINK_FREE_3D

    def draw_links(self, turn: int) -> None:
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
        rl.draw_cylinder_ex(rl.Vector3(a[0], PORTAL_H + a[1], z),
                            rl.Vector3(b[0], PORTAL_H + b[1], z),
                            r, r, 6, color)

    def draw_frame_ring(self, ztype: ZoneType, color: rl.Color) -> None:
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
        zone, dest = self.replay.frames[frame][ident]
        if dest is not None:
            return TRANSIT_Y
        if ident in self.replay.waiting[frame] and zone != self.replay.start:
            return FLY_Y - 0.3
        return FLY_Y

    def stacked(self, frame: int, ident: int) -> bool:
        zone, dest = self.replay.frames[frame][ident]
        if dest is not None or not self.special(zone):
            return False
        return len(self.replay.occupants[frame][zone]) > STACK_LIMIT

    def drone_pose(self, turn: int, progress: float,
                   ident: int) -> rl.Vector3 | None:
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
    def __init__(self, graph: Graph, lines: list[str],
                 model_path: str | None = "assets/dragon.glb",
                 width: int = 1280, height: int = 720) -> None:
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

    def open(self) -> None:
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
        self.art.close()
        rl.close_window()

    def handle_keys(self) -> None:
        key = rl.KeyboardKey
        last = self.replay.turns
        if rl.is_key_pressed(key.KEY_SPACE):
            self.playing = not self.playing
        if rl.is_key_pressed(key.KEY_RIGHT):
            self.turn, self.progress = min(self.turn + 1, last), 0.0
        if rl.is_key_pressed(key.KEY_LEFT):
            self.turn, self.progress = max(self.turn - 1, 0), 0.0
        if rl.is_key_pressed(key.KEY_UP):
            self.speed = min(self.speed + 0.5, 8.0)
        if rl.is_key_pressed(key.KEY_DOWN):
            self.speed = max(self.speed - 0.5, 0.5)
        if rl.is_key_pressed(key.KEY_HOME):
            self.turn, self.progress, self.playing = 0, 0.0, True
        if rl.is_key_pressed(key.KEY_R):
            x, z, span = self.home_cam
            self.cam.target = rl.Vector3(x, 0, z)
            self.cam.span = span
            self.cam.azimuth = 315.0
            self.cam.elevation = IsoCamera.ISO_ELEVATION

    def advance(self) -> None:
        if not self.playing or self.turn >= self.replay.turns:
            return
        self.progress += rl.get_frame_time() * self.speed
        if self.progress >= 1.0:
            self.turn, self.progress = self.turn + 1, 0.0

    def draw_frame(self) -> None:
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

    def draw_hud(self, shown: int) -> None:
        rl.draw_rectangle(0, 0, self.width, HUD_HEIGHT, HUD_BG)
        moves = self.replay.moves_per_turn[shown - 1] if shown > 0 else 0
        mode = "iso" if self.cam.ortho else "perspective"
        state = "playing" if self.playing else "paused"
        items = [
            (f"Turn {shown} / {self.replay.turns}", 16),
            (f"Delivered {self.replay.delivered(shown)} / "
             f"{self.graph.nb_drones}", 220),
            (f"Moves {moves}", 450),
            (f"{state} x{self.speed:.1f}  [{mode}]", 600),
        ]
        for text, x in items:
            rl.draw_text(text, x, 13, 20, TEXT)
        hint = "drag orbit | right-drag pan | wheel zoom | P iso/3D | R reset"
        rl.draw_text(hint, self.width - rl.measure_text(hint, 14) - 16,
                     15, 14, MUTED)
        rl.draw_rectangle(0, self.height - 28, self.width, 28, HUD_BG)
        rl.draw_text(LEGEND_TEXT, 16, self.height - 21, 14, MUTED)

    def draw_hover(self, camera: rl.Camera3D) -> None:
        mouse = rl.get_mouse_position()
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
        self.open()
        try:
            while not rl.window_should_close():
                self.handle_keys()
                self.cam.update(rl.get_frame_time())
                self.advance()
                self.draw_frame()
        finally:
            self.close()