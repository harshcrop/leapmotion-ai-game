"""
leap_duck_hunt.py

A simple point-and-shoot gallery game controlled by your Leap Motion
Controller. Point with your index finger to aim; jab your finger
forward (like pulling a trigger) to shoot.

Original mechanics and art -- not affiliated with or based on any
existing shooting-gallery game's assets or code.

Requires the legacy Leap Motion Orion tracking service running with its
WebSocket enabled (Leap Control Panel -> Settings -> "Allow Web Apps"),
exposing ws://127.0.0.1:6437/v6.json.

Install:
  pip install pygame websocket-client
"""

import json
import math
import random
import sys
import threading
import time

import pygame
import websocket

LEAP_WS_URL = "ws://127.0.0.1:6437/v6.json"

SCREEN_W, SCREEN_H = 800, 600
FPS = 60

GROUND_HEIGHT = 90
PLAY_H = SCREEN_H - GROUND_HEIGHT

# Leap's usable range above the sensor, in mm -- tune to your setup
LEAP_X_MIN, LEAP_X_MAX = -180, 180
LEAP_Y_MIN, LEAP_Y_MAX = 80, 400

JAB_VELOCITY_TRIGGER = 550.0  # mm/s downward fingertip speed counts as a shot
GESTURE_COOLDOWN = 0.3        # seconds, prevents double-triggering on one jab

CROSSHAIR_RADIUS = 22
HIT_RADIUS = 46

AMMO_PER_DUCK = 3
LIVES_START = 3
BASE_DUCK_SPEED = 150.0  # px/s
SPEED_STEP = 20.0        # px/s added per round
DUCKS_START = 6
DUCKS_STEP = 2
ROUND_BANNER_TIME = 1.4
RESPAWN_DELAY = 0.6
SHOT_EFFECT_TIME = 0.15

# -------- Palette

SKY_TOP = (78, 178, 222)
SKY_BOTTOM = (198, 236, 242)
CLOUD_COLOR = (255, 255, 255)
GRASS_COLOR = (86, 163, 63)
GRASS_EDGE = (60, 128, 42)
BUSH_COLOR = (66, 140, 54)

DUCK_BODY = (150, 108, 68)
DUCK_HEAD = (46, 87, 74)
DUCK_WING = (110, 78, 46)
DUCK_BEAK = (230, 170, 40)
DUCK_EYE = (20, 20, 20)

TEXT_COLOR = (255, 255, 255)
SHADOW_COLOR = (0, 0, 0)
PANEL_COLOR = (20, 20, 20)
CONNECTED_COLOR = (46, 204, 113)
DISCONNECTED_COLOR = (231, 76, 60)
CROSSHAIR_ACTIVE = (231, 76, 60)
CROSSHAIR_INACTIVE = (150, 150, 150)


def make_sky_gradient(width, height, top, bottom):
    surf = pygame.Surface((width, height))
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        pygame.draw.line(surf, color, (0, y), (width, y))
    return surf


def make_cloud(scale):
    w, h = int(90 * scale), int(40 * scale)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    puffs = [
        (int(w * 0.25), int(h * 0.65), int(h * 0.45)),
        (int(w * 0.5), int(h * 0.4), int(h * 0.55)),
        (int(w * 0.75), int(h * 0.6), int(h * 0.4)),
    ]
    for cx, cy, r in puffs:
        pygame.draw.circle(surf, (*CLOUD_COLOR, 210), (cx, cy), r)
    return surf


class Cloud:
    def __init__(self, x, y, scale, speed):
        self.x = x
        self.y = y
        self.speed = speed
        self.image = make_cloud(scale)

    def update(self):
        self.x -= self.speed
        if self.x + self.image.get_width() < 0:
            self.x = SCREEN_W + random.randint(20, 100)
            self.y = random.randint(30, 160)

    def draw(self, surface):
        surface.blit(self.image, (self.x, self.y))


def normalize(value, lo, hi):
    frac = (value - lo) / (hi - lo)
    return max(0.0, min(1.0, frac))


class LeapState:
    """Thread-safe shared state for the pointing index fingertip."""

    def __init__(self):
        self._lock = threading.Lock()
        self.tip_x = None
        self.tip_y = None
        self.tip_vy = 0.0  # mm/s, computed client-side (bridge doesn't send fingertip velocity)
        self.pointing = False
        self.connected = False
        self._prev_y = None
        self._prev_t = None

    def update_point(self, x, y):
        now = time.time()
        with self._lock:
            if self._prev_y is not None and self._prev_t is not None:
                dt = now - self._prev_t
                if dt > 0:
                    self.tip_vy = (y - self._prev_y) / dt
            self._prev_y = y
            self._prev_t = now
            self.tip_x = x
            self.tip_y = y
            self.pointing = True

    def clear_point(self):
        with self._lock:
            self.tip_x = None
            self.tip_y = None
            self.tip_vy = 0.0
            self.pointing = False
            self._prev_y = None
            self._prev_t = None

    def read(self):
        with self._lock:
            return self.tip_x, self.tip_y, self.tip_vy, self.pointing


def get_index_tip(pointables):
    """Only treat this as an aiming pose if exactly one finger -- the
    index -- is extended (type 1 in Leap's finger enum)."""
    extended = [p for p in pointables if p.get("extended")]
    if len(extended) != 1:
        return None
    finger = extended[0]
    if finger.get("type") != 1:
        return None
    tip = finger.get("tipPosition", [0, 0, 0])
    return tip[0], tip[1]


def leap_listener_thread(state: LeapState):
    def on_message(ws, message):
        try:
            frame = json.loads(message)
        except json.JSONDecodeError:
            return
        tip = get_index_tip(frame.get("pointables", []))
        if tip is None:
            state.clear_point()
        else:
            state.update_point(tip[0], tip[1])

    def on_open(ws):
        state.connected = True
        print("[leap] connected")

    def on_close(ws, code, msg):
        state.connected = False
        print("[leap] disconnected")

    def on_error(ws, error):
        print(f"[leap] error: {error}", file=sys.stderr)

    while True:
        ws_app = websocket.WebSocketApp(
            LEAP_WS_URL,
            on_open=on_open,
            on_message=on_message,
            on_close=on_close,
            on_error=on_error,
        )
        ws_app.run_forever()
        time.sleep(1)  # retry loop if the service isn't up yet


class Duck:
    def __init__(self, round_no):
        self.speed = BASE_DUCK_SPEED + (round_no - 1) * SPEED_STEP
        self.direction = random.choice([-1, 1])
        self.x = -50.0 if self.direction == 1 else SCREEN_W + 50.0
        self.base_y = random.uniform(PLAY_H * 0.15, PLAY_H * 0.55)
        self.amplitude = random.uniform(35, 80)
        self.frequency = random.uniform(1.4, 2.6)
        self.phase = random.uniform(0, 2 * math.pi)
        self.elapsed = 0.0
        self.y = self.base_y
        self.ammo = AMMO_PER_DUCK
        self.hit = False
        self.fall_vy = 0.0

    def update(self, dt):
        if self.hit:
            self.fall_vy += 900 * dt
            self.y += self.fall_vy * dt
        else:
            self.elapsed += dt
            self.x += self.direction * self.speed * dt
            self.y = self.base_y + math.sin(self.elapsed * self.frequency + self.phase) * self.amplitude

    def offscreen(self):
        return self.x < -70 or self.x > SCREEN_W + 70

    def fallen(self):
        return self.y > PLAY_H + 40

    def rect(self):
        return pygame.Rect(int(self.x) - 26, int(self.y) - 20, 52, 40)


def make_duck_sprite(wing_up):
    w, h = 60, 46
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(surf, DUCK_BODY, pygame.Rect(10, 16, 38, 22))
    pygame.draw.circle(surf, DUCK_HEAD, (44, 14), 11)
    pygame.draw.polygon(surf, DUCK_BEAK, [(53, 12), (60, 14), (53, 17)])
    pygame.draw.circle(surf, DUCK_EYE, (47, 11), 2)
    wing_y = 14 if wing_up else 24
    pygame.draw.polygon(surf, DUCK_WING, [(16, 20), (30, wing_y), (34, 26)])
    return surf


def draw_shadowed_text(surface, font, text, color, pos):
    surface.blit(font.render(text, True, SHADOW_COLOR), (pos[0] + 1, pos[1] + 1))
    surface.blit(font.render(text, True, color), pos)


def draw_pill(surface, rect, color, alpha=150):
    pill = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    pygame.draw.rect(pill, (*color, alpha), pill.get_rect(), border_radius=rect.height // 2)
    surface.blit(pill, rect.topleft)


def draw_crosshair(surface, pos, active):
    color = CROSSHAIR_ACTIVE if active else CROSSHAIR_INACTIVE
    x, y = pos
    pygame.draw.circle(surface, color, (x, y), CROSSHAIR_RADIUS, width=3)
    pygame.draw.line(surface, color, (x - CROSSHAIR_RADIUS - 8, y), (x + CROSSHAIR_RADIUS + 8, y), 2)
    pygame.draw.line(surface, color, (x, y - CROSSHAIR_RADIUS - 8), (x, y + CROSSHAIR_RADIUS + 8), 2)


def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Leap Duck Hunt")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 24, bold=True)
    font_small = pygame.font.SysFont(None, 18, bold=True)
    font_big = pygame.font.SysFont(None, 44, bold=True)

    sky = make_sky_gradient(SCREEN_W, PLAY_H, SKY_TOP, SKY_BOTTOM)
    clouds = [
        Cloud(random.randint(0, SCREEN_W), random.randint(30, 160), random.uniform(0.7, 1.3), random.uniform(0.25, 0.6))
        for _ in range(4)
    ]
    bush_positions = [
        (random.randint(0, SCREEN_W), random.randint(10, GROUND_HEIGHT - 20), random.randint(14, 26))
        for _ in range(10)
    ]

    leap_state = LeapState()
    threading.Thread(target=leap_listener_thread, args=(leap_state,), daemon=True).start()

    crosshair_pos = [SCREEN_W / 2, PLAY_H / 2]
    last_shot_time = 0.0
    shot_effects = []

    score = 0
    lives = LIVES_START
    round_number = 1
    ducks_this_round = DUCKS_START
    ducks_processed = 0
    duck = None
    state = "ROUND_BANNER"
    state_timer = ROUND_BANNER_TIME
    game_over = False

    def start_round():
        nonlocal ducks_this_round, ducks_processed, state, state_timer
        ducks_this_round = DUCKS_START + (round_number - 1) * DUCKS_STEP
        ducks_processed = 0
        state = "ROUND_BANNER"
        state_timer = ROUND_BANNER_TIME

    def spawn_duck():
        nonlocal duck, state
        duck = Duck(round_number)
        state = "PLAYING"

    def reset_game():
        nonlocal score, lives, round_number, game_over, duck
        score = 0
        lives = LIVES_START
        round_number = 1
        game_over = False
        duck = None
        start_round()

    reset_game()

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0

        manual_fire = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r and game_over:
                    reset_game()
                elif event.key == pygame.K_SPACE and not game_over:
                    manual_fire = True
            elif event.type == pygame.MOUSEBUTTONDOWN and not game_over:
                manual_fire = True

        tip_x, tip_y, tip_vy, pointing = leap_state.read()

        gesture_fire = False
        now = time.time()
        if pointing and tip_vy < -JAB_VELOCITY_TRIGGER and now - last_shot_time > GESTURE_COOLDOWN:
            gesture_fire = True
            last_shot_time = now

        if pointing and tip_x is not None and tip_y is not None:
            target_x = normalize(tip_x, LEAP_X_MIN, LEAP_X_MAX) * SCREEN_W
            target_y = PLAY_H - normalize(tip_y, LEAP_Y_MIN, LEAP_Y_MAX) * PLAY_H
            crosshair_pos[0] += (target_x - crosshair_pos[0]) * 0.35
            crosshair_pos[1] += (target_y - crosshair_pos[1]) * 0.35

        for cloud in clouds:
            cloud.update()

        if not game_over:
            if state == "ROUND_BANNER":
                state_timer -= dt
                if state_timer <= 0:
                    spawn_duck()
            elif state == "PLAYING":
                duck.update(dt)
                if (manual_fire or gesture_fire) and duck.ammo > 0 and not duck.hit:
                    duck.ammo -= 1
                    shot_effects.append([crosshair_pos[0], crosshair_pos[1], SHOT_EFFECT_TIME])
                    dist = math.hypot(crosshair_pos[0] - duck.x, crosshair_pos[1] - duck.y)
                    if dist <= HIT_RADIUS:
                        duck.hit = True
                        score += 10 * round_number
                if duck.hit and duck.fallen():
                    ducks_processed += 1
                    duck = None
                    state = "BETWEEN"
                    state_timer = RESPAWN_DELAY
                elif not duck.hit and duck.offscreen():
                    lives -= 1
                    ducks_processed += 1
                    duck = None
                    if lives <= 0:
                        game_over = True
                    else:
                        state = "BETWEEN"
                        state_timer = RESPAWN_DELAY
            elif state == "BETWEEN":
                state_timer -= dt
                if state_timer <= 0:
                    if ducks_processed >= ducks_this_round:
                        round_number += 1
                        start_round()
                    else:
                        spawn_duck()

        for eff in shot_effects:
            eff[2] -= dt
        shot_effects = [e for e in shot_effects if e[2] > 0]

        # --- draw ---
        screen.blit(sky, (0, 0))
        for cloud in clouds:
            cloud.draw(screen)

        pygame.draw.rect(screen, GRASS_COLOR, (0, PLAY_H, SCREEN_W, GROUND_HEIGHT))
        pygame.draw.rect(screen, GRASS_EDGE, (0, PLAY_H, SCREEN_W, 6))
        for bx, by, br in bush_positions:
            pygame.draw.circle(screen, BUSH_COLOR, (bx, PLAY_H + by), br)

        if duck is not None:
            wing_up = (not duck.hit) and (int(duck.elapsed * 10) % 2 == 0)
            sprite = make_duck_sprite(wing_up)
            if duck.hit:
                sprite = pygame.transform.flip(sprite, False, True)
            if duck.direction == -1:
                sprite = pygame.transform.flip(sprite, True, False)
            rect = sprite.get_rect(center=(int(duck.x), int(duck.y)))
            screen.blit(sprite, rect)

        for eff in shot_effects:
            t = 1 - (eff[2] / SHOT_EFFECT_TIME)
            radius = int(8 + t * 22)
            alpha = max(0, 255 - int(t * 255))
            ring = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(ring, (255, 230, 120, alpha), (radius + 2, radius + 2), radius, width=3)
            screen.blit(ring, (eff[0] - radius - 2, eff[1] - radius - 2))

        draw_crosshair(screen, (int(crosshair_pos[0]), int(crosshair_pos[1])), pointing)

        # --- HUD ---
        draw_pill(screen, pygame.Rect(10, 10, 130, 32), PANEL_COLOR)
        draw_shadowed_text(screen, font, f"Score {score}", TEXT_COLOR, (24, 18))

        draw_pill(screen, pygame.Rect(150, 10, 110, 32), PANEL_COLOR)
        draw_shadowed_text(screen, font_small, f"Round {round_number}", TEXT_COLOR, (164, 18))

        draw_pill(screen, pygame.Rect(270, 10, 90, 32), PANEL_COLOR)
        draw_shadowed_text(screen, font_small, f"Lives {lives}", TEXT_COLOR, (284, 18))

        if duck is not None and not duck.hit:
            draw_pill(screen, pygame.Rect(370, 10, 90, 32), PANEL_COLOR)
            draw_shadowed_text(screen, font_small, f"Ammo {duck.ammo}", TEXT_COLOR, (384, 18))

        dot_color = CONNECTED_COLOR if leap_state.connected else DISCONNECTED_COLOR
        draw_pill(screen, pygame.Rect(SCREEN_W - 150, 10, 140, 32), PANEL_COLOR)
        pygame.draw.circle(screen, dot_color, (SCREEN_W - 130, 26), 6)
        conn_label = "Connected" if leap_state.connected else "No signal"
        draw_shadowed_text(screen, font_small, conn_label, TEXT_COLOR, (SCREEN_W - 114, 18))

        if not pointing:
            draw_shadowed_text(
                screen, font_small, "Point with your index finger to aim",
                (230, 230, 230), (10, SCREEN_H - 46),
            )

        legend = "Jab forward to shoot   Space: shoot (test)   R: restart   Esc: quit"
        draw_shadowed_text(screen, font_small, legend, (230, 230, 230), (10, SCREEN_H - 20))

        if state == "ROUND_BANNER" and not game_over:
            banner = font_big.render(f"Round {round_number}", True, TEXT_COLOR)
            screen.blit(banner, (SCREEN_W // 2 - banner.get_width() // 2, PLAY_H // 2 - 30))

        if game_over:
            overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 140))
            screen.blit(overlay, (0, 0))
            over_text = font_big.render("Game Over", True, (255, 90, 90))
            screen.blit(over_text, (SCREEN_W // 2 - over_text.get_width() // 2, SCREEN_H // 2 - 50))
            score_text = font.render(f"Final Score: {score}", True, TEXT_COLOR)
            screen.blit(score_text, (SCREEN_W // 2 - score_text.get_width() // 2, SCREEN_H // 2))
            hint_text = font_small.render("Press R to restart", True, TEXT_COLOR)
            screen.blit(hint_text, (SCREEN_W // 2 - hint_text.get_width() // 2, SCREEN_H // 2 + 34))

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
