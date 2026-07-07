"""
leap_flappy_bird.py

Flappy Bird controlled by your Leap Motion Controller.

Bird's vertical position mirrors your palm height above the sensor -
raise your hand to climb, lower it to dive.

Requires the legacy Leap Motion Orion tracking service running with its
WebSocket enabled (Leap Control Panel -> Settings -> "Allow Web Apps"),
exposing ws://127.0.0.1:6437/v6.json. See notes in leap_handy_bridge.py
if you're on the newer Gemini service instead.

Install:
  pip install pygame websocket-client
"""

import json
import random
import sys
import threading
import time

import pygame
import websocket

LEAP_WS_URL = "ws://127.0.0.1:6437/v6.json"

SCREEN_W, SCREEN_H = 480, 640
FPS = 60

GROUND_HEIGHT = 80
PLAY_H = SCREEN_H - GROUND_HEIGHT

BIRD_X = 100
BIRD_RADIUS = 16
GRAVITY = 0.35
FLAP_IMPULSE = -8.5

PIPE_GAP = 170
PIPE_SPEED = 3.0
PIPE_SPACING = 260
PIPE_WIDTH = 70
PIPE_CAP_HEIGHT = 26
PIPE_CAP_OVERHANG = 6

# Leap's usable vertical range above the sensor, in mm -- tune to your setup
LEAP_Y_MIN, LEAP_Y_MAX = 80, 400

# -------- Palette (flat/candy style)

SKY_TOP = (78, 178, 222)
SKY_BOTTOM = (198, 236, 242)
CLOUD_COLOR = (255, 255, 255)
GROUND_GRASS = (99, 191, 72)
GROUND_GRASS_EDGE = (72, 158, 51)
GROUND_DIRT_TOP = (172, 130, 88)
GROUND_DIRT_BOTTOM = (140, 100, 64)

PIPE_COLOR = (94, 191, 74)
PIPE_EDGE_COLOR = (58, 138, 46)
PIPE_CAP_COLOR = (108, 209, 86)

BIRD_BODY = (255, 205, 52)
BIRD_BELLY = (255, 235, 158)
BIRD_EDGE_COLOR = (206, 140, 20)
BIRD_BEAK = (240, 130, 40)
BIRD_EYE_WHITE = (255, 255, 255)
BIRD_EYE_PUPIL = (40, 30, 20)

TEXT_COLOR = (255, 255, 255)
SHADOW_COLOR = (0, 0, 0)
PANEL_COLOR = (20, 20, 20)
CONNECTED_COLOR = (46, 204, 113)
DISCONNECTED_COLOR = (231, 76, 60)


def make_sky_gradient(width, height, top, bottom):
    surf = pygame.Surface((width, height))
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        pygame.draw.line(surf, color, (0, y), (width, y))
    return surf


def make_cloud(scale):
    """Procedurally build a soft cloud sprite from overlapping circles."""
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


class LeapState:
    """Thread-safe shared state updated by the websocket thread."""

    def __init__(self):
        self._lock = threading.Lock()
        self.palm_y = None  # mm above sensor, None if no hand
        self.connected = False

    def update(self, palm_y):
        with self._lock:
            self.palm_y = palm_y

    def clear_hand(self):
        with self._lock:
            self.palm_y = None

    def read(self):
        with self._lock:
            return self.palm_y


def leap_listener_thread(state: LeapState):
    def on_message(ws, message):
        try:
            frame = json.loads(message)
        except json.JSONDecodeError:
            return
        hands = frame.get("hands", [])
        if not hands:
            state.clear_hand()
            return
        hand = hands[0]
        palm_y = hand.get("palmPosition", [0, 0, 0])[1]
        state.update(palm_y)

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


class Pipe:
    def __init__(self, x):
        self.x = x
        margin = PIPE_GAP // 2 + 40
        self.gap_center = random.randint(margin, PLAY_H - margin)
        self.scored = False

    @property
    def top_rect(self):
        return pygame.Rect(self.x, 0, PIPE_WIDTH, self.gap_center - PIPE_GAP // 2)

    @property
    def bottom_rect(self):
        top_of_bottom = self.gap_center + PIPE_GAP // 2
        return pygame.Rect(self.x, top_of_bottom, PIPE_WIDTH, PLAY_H - top_of_bottom)


def normalize_palm_y(palm_y_mm: float) -> float:
    """Map Leap's mm height to a 0..1 range, clamped."""
    frac = (palm_y_mm - LEAP_Y_MIN) / (LEAP_Y_MAX - LEAP_Y_MIN)
    return max(0.0, min(1.0, frac))


def draw_shadowed_text(surface, font, text, color, pos):
    surface.blit(font.render(text, True, SHADOW_COLOR), (pos[0] + 1, pos[1] + 1))
    surface.blit(font.render(text, True, color), pos)


def draw_pill(surface, rect, color, alpha=150):
    pill = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    pygame.draw.rect(pill, (*color, alpha), pill.get_rect(), border_radius=rect.height // 2)
    surface.blit(pill, rect.topleft)


def draw_pipe(surface, rect, facing_down):
    """facing_down=True for the top pipe (mouth points down toward the gap)."""
    pygame.draw.rect(surface, PIPE_COLOR, rect)
    pygame.draw.rect(surface, PIPE_EDGE_COLOR, rect, width=3)

    cap_y = rect.bottom - PIPE_CAP_HEIGHT if facing_down else rect.top
    cap_rect = pygame.Rect(
        rect.x - PIPE_CAP_OVERHANG, cap_y,
        rect.width + PIPE_CAP_OVERHANG * 2, PIPE_CAP_HEIGHT,
    )
    pygame.draw.rect(surface, PIPE_CAP_COLOR, cap_rect, border_radius=4)
    pygame.draw.rect(surface, PIPE_EDGE_COLOR, cap_rect, width=3, border_radius=4)


def make_bird_sprite():
    size = BIRD_RADIUS * 2 + 12
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size // 2
    pygame.draw.circle(surf, BIRD_BODY, (c, c), BIRD_RADIUS)
    pygame.draw.circle(surf, BIRD_EDGE_COLOR, (c, c), BIRD_RADIUS, width=2)
    pygame.draw.circle(surf, BIRD_BELLY, (c - 2, c + 5), BIRD_RADIUS - 7)
    pygame.draw.circle(surf, BIRD_EYE_WHITE, (c + 6, c - 6), 6)
    pygame.draw.circle(surf, BIRD_EYE_PUPIL, (c + 8, c - 6), 3)
    beak = [(c + BIRD_RADIUS - 4, c - 2), (c + BIRD_RADIUS + 9, c + 2), (c + BIRD_RADIUS - 4, c + 7)]
    pygame.draw.polygon(surf, BIRD_BEAK, beak)
    return surf


def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Leap Flappy Bird")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 24, bold=True)
    font_small = pygame.font.SysFont(None, 18, bold=True)
    font_big = pygame.font.SysFont(None, 44, bold=True)

    sky = make_sky_gradient(SCREEN_W, PLAY_H, SKY_TOP, SKY_BOTTOM)
    clouds = [
        Cloud(random.randint(0, SCREEN_W), random.randint(30, 160), random.uniform(0.7, 1.3), random.uniform(0.25, 0.6))
        for _ in range(4)
    ]
    bird_sprite = make_bird_sprite()
    ground_scroll = 0.0

    leap_state = LeapState()
    threading.Thread(target=leap_listener_thread, args=(leap_state,), daemon=True).start()

    bird_y = PLAY_H / 2
    bird_vy = 0.0

    pipes = []
    score = 0
    game_over = False

    def reset_round():
        nonlocal bird_y, bird_vy, pipes, score, game_over
        bird_y = PLAY_H / 2
        bird_vy = 0.0
        pipes = [Pipe(SCREEN_W + i * PIPE_SPACING) for i in range(3)]
        score = 0
        game_over = False

    reset_round()

    running = True
    while running:
        clock.tick(FPS)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r and game_over:
                    reset_round()
                elif event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    # keyboard fallback so you can test without the sensor
                    bird_vy = FLAP_IMPULSE

        palm_y = leap_state.read()

        for cloud in clouds:
            cloud.update()
        ground_scroll = (ground_scroll + PIPE_SPEED) % 40

        if not game_over:
            if palm_y is not None:
                frac = normalize_palm_y(palm_y)
                target_y = PLAY_H - frac * PLAY_H
                bird_y += (target_y - bird_y) * 0.25  # smoothing
            else:
                bird_vy += GRAVITY
                bird_y += bird_vy

            bird_y = max(BIRD_RADIUS, min(PLAY_H - BIRD_RADIUS, bird_y))

            for pipe in pipes:
                pipe.x -= PIPE_SPEED
                if not pipe.scored and pipe.x + PIPE_WIDTH < BIRD_X:
                    pipe.scored = True
                    score += 1

            if pipes[0].x < -PIPE_WIDTH:
                pipes.pop(0)
                pipes.append(Pipe(pipes[-1].x + PIPE_SPACING))

            bird_rect = pygame.Rect(
                BIRD_X - BIRD_RADIUS, int(bird_y) - BIRD_RADIUS,
                BIRD_RADIUS * 2, BIRD_RADIUS * 2,
            )
            for pipe in pipes:
                if bird_rect.colliderect(pipe.top_rect) or bird_rect.colliderect(pipe.bottom_rect):
                    game_over = True
            if bird_y <= BIRD_RADIUS or bird_y >= PLAY_H - BIRD_RADIUS:
                game_over = True

        # --- draw sky & clouds ---
        screen.blit(sky, (0, 0))
        for cloud in clouds:
            cloud.draw(screen)

        # --- pipes ---
        for pipe in pipes:
            draw_pipe(screen, pipe.top_rect, facing_down=True)
            draw_pipe(screen, pipe.bottom_rect, facing_down=False)

        # --- ground ---
        ground_rect = pygame.Rect(0, PLAY_H, SCREEN_W, GROUND_HEIGHT)
        pygame.draw.rect(screen, GROUND_DIRT_TOP, ground_rect)
        pygame.draw.rect(screen, GROUND_DIRT_BOTTOM, (0, PLAY_H + GROUND_HEIGHT - 18, SCREEN_W, 18))
        pygame.draw.rect(screen, GROUND_GRASS, (0, PLAY_H, SCREEN_W, 14))
        pygame.draw.rect(screen, GROUND_GRASS_EDGE, (0, PLAY_H + 12, SCREEN_W, 3))
        for x in range(-40, SCREEN_W + 40, 40):
            gx = x - int(ground_scroll)
            pygame.draw.line(screen, GROUND_DIRT_BOTTOM, (gx, PLAY_H + 18), (gx - 14, SCREEN_H), 2)

        # --- bird (tilts with vertical velocity) ---
        angle = max(-30, min(75, -bird_vy * 4))
        rotated = pygame.transform.rotate(bird_sprite, angle)
        rect = rotated.get_rect(center=(BIRD_X, int(bird_y)))
        screen.blit(rotated, rect)

        # --- HUD ---
        draw_pill(screen, pygame.Rect(10, 10, 110, 32), PANEL_COLOR)
        draw_shadowed_text(screen, font, f"Score {score}", TEXT_COLOR, (24, 18))

        dot_color = CONNECTED_COLOR if leap_state.connected else DISCONNECTED_COLOR
        draw_pill(screen, pygame.Rect(SCREEN_W - 150, 10, 140, 32), PANEL_COLOR)
        pygame.draw.circle(screen, dot_color, (SCREEN_W - 130, 26), 6)
        conn_label = "Connected" if leap_state.connected else "No signal"
        draw_shadowed_text(screen, font_small, conn_label, TEXT_COLOR, (SCREEN_W - 114, 18))

        if palm_y is not None:
            draw_shadowed_text(screen, font_small, f"y={palm_y:.0f}mm", TEXT_COLOR, (10, SCREEN_H - 26))

        legend = "R: restart   Esc: quit"
        draw_shadowed_text(screen, font_small, legend, (230, 230, 230), (10, SCREEN_H - 20))

        if game_over:
            overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 130))
            screen.blit(overlay, (0, 0))
            over_text = font_big.render("Game Over", True, (255, 90, 90))
            screen.blit(over_text, (SCREEN_W // 2 - over_text.get_width() // 2, SCREEN_H // 2 - 40))
            score_text = font.render(f"Score: {score}", True, TEXT_COLOR)
            screen.blit(score_text, (SCREEN_W // 2 - score_text.get_width() // 2, SCREEN_H // 2 + 10))
            hint_text = font_small.render("Press R to restart", True, TEXT_COLOR)
            screen.blit(hint_text, (SCREEN_W // 2 - hint_text.get_width() // 2, SCREEN_H // 2 + 40))

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
