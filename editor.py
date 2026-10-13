import json
from collections import deque
from pathlib import Path

import pygame

# --- Config -------------------------------------------------------------
TILE_SIZE = 32                  # 32 px = 1 world unit
GRID_W, GRID_H = 25, 18         # map size in tiles
MAP_W = TILE_SIZE * GRID_W
MAP_H = TILE_SIZE * GRID_H
TOOLBAR_H = 48
WINDOW_W = MAP_W
WINDOW_H = MAP_H + TOOLBAR_H
FPS = 60

MAP_FILE = Path(__file__).parent / "level.json"
FORMAT_VERSION = 1
STATUS_DURATION_MS = 2000
UNDO_LIMIT = 100

BG_COLOR = (30, 30, 36)
GRID_COLOR = (60, 60, 70)
HOVER_COLOR = (255, 255, 255)
TOOLBAR_COLOR = (22, 22, 26)
TEXT_COLOR = (220, 220, 230)
OK_COLOR = (120, 200, 120)
ERROR_COLOR = (230, 100, 100)

EMPTY = 0
TILE_TYPES = {
    1: ("Grass",  (110, 160, 90)),
    2: ("Dirt",   (140, 100, 60)),
    3: ("Stone",  (130, 130, 140)),
    4: ("Water",  (60, 110, 180)),
    5: ("Spikes", (190, 60, 60)),
}

KEY_TO_TILE = {
    pygame.K_1: 1,
    pygame.K_2: 2,
    pygame.K_3: 3,
    pygame.K_4: 4,
    pygame.K_5: 5,
}

SWATCH_SIZE = 32
SWATCH_GAP = 8


# --- Map data -----------------------------------------------------------
def create_map(width, height):
    return [[EMPTY for _ in range(width)] for _ in range(height)]


def copy_map(tilemap):
    return [row.copy() for row in tilemap]


def in_bounds(tile):
    tx, ty = tile
    return 0 <= tx < GRID_W and 0 <= ty < GRID_H


def set_tile(tilemap, tile, value):
    if in_bounds(tile):
        tx, ty = tile
        tilemap[ty][tx] = value


def mouse_to_tile(mouse_pos):
    mx, my = mouse_pos
    return mx // TILE_SIZE, my // TILE_SIZE


# --- Undo / redo --------------------------------------------------------
class History:
    """Undo/redo by storing whole-map snapshots."""

    def __init__(self, limit=UNDO_LIMIT):
        # deque with maxlen drops the oldest entry automatically when full
        self.undo_stack = deque(maxlen=limit)
        self.redo_stack = []

    def record(self, before):
        """Call after a change, passing the map as it was BEFORE the change."""
        self.undo_stack.append(before)
        self.redo_stack.clear()     # a new edit invalidates the redo branch

    def undo(self, current):
        """Return the previous map, or None if there is nothing to undo."""
        if not self.undo_stack:
            return None
        self.redo_stack.append(copy_map(current))
        return self.undo_stack.pop()

    def redo(self, current):
        """Return the next map, or None if there is nothing to redo."""
        if not self.redo_stack:
            return None
        self.undo_stack.append(copy_map(current))
        return self.redo_stack.pop()


# --- Save / load --------------------------------------------------------
def save_map(tilemap, path):
    data = {
        "version": FORMAT_VERSION,
        "tile_size": TILE_SIZE,
        "width": GRID_W,
        "height": GRID_H,
        "tile_types": {str(tile_id): name for tile_id, (name, _color) in TILE_TYPES.items()},
        "tiles": tilemap,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def load_map(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("version") != FORMAT_VERSION:
        raise ValueError(f"unsupported version: {data.get('version')}")
    if data.get("width") != GRID_W or data.get("height") != GRID_H:
        raise ValueError(f"map is {data.get('width')}x{data.get('height')}, editor is {GRID_W}x{GRID_H}")

    tiles = data["tiles"]
    if len(tiles) != GRID_H or any(len(row) != GRID_W for row in tiles):
        raise ValueError("tile grid has the wrong shape")
    for row in tiles:
        for tile_id in row:
            if tile_id != EMPTY and tile_id not in TILE_TYPES:
                raise ValueError(f"unknown tile id: {tile_id}")

    return tiles


# --- Toolbar ------------------------------------------------------------
def swatch_rect(index):
    x = SWATCH_GAP + index * (SWATCH_SIZE + SWATCH_GAP)
    y = MAP_H + (TOOLBAR_H - SWATCH_SIZE) // 2
    return pygame.Rect(x, y, SWATCH_SIZE, SWATCH_SIZE)


def tile_at_swatch(mouse_pos):
    """Return the tile id of the swatch under the mouse, or None."""
    for index, tile_id in enumerate(TILE_TYPES):
        if swatch_rect(index).collidepoint(mouse_pos):
            return tile_id
    return None


# --- Drawing ------------------------------------------------------------
def draw_tiles(surface, tilemap):
    for ty, row in enumerate(tilemap):
        for tx, tile_id in enumerate(row):
            if tile_id != EMPTY:
                _name, color = TILE_TYPES[tile_id]
                rect = pygame.Rect(tx * TILE_SIZE, ty * TILE_SIZE, TILE_SIZE, TILE_SIZE)
                pygame.draw.rect(surface, color, rect)


def draw_grid(surface):
    for x in range(0, MAP_W + 1, TILE_SIZE):
        pygame.draw.line(surface, GRID_COLOR, (x, 0), (x, MAP_H))
    for y in range(0, MAP_H + 1, TILE_SIZE):
        pygame.draw.line(surface, GRID_COLOR, (0, y), (MAP_W, y))


def draw_hover(surface, tile):
    if in_bounds(tile):
        tx, ty = tile
        rect = pygame.Rect(tx * TILE_SIZE, ty * TILE_SIZE, TILE_SIZE, TILE_SIZE)
        pygame.draw.rect(surface, HOVER_COLOR, rect, width=2)


def draw_toolbar(surface, selected, font, status):
    pygame.draw.rect(surface, TOOLBAR_COLOR, (0, MAP_H, WINDOW_W, TOOLBAR_H))

    for index, (tile_id, (name, color)) in enumerate(TILE_TYPES.items()):
        rect = swatch_rect(index)
        pygame.draw.rect(surface, color, rect)
        if tile_id == selected:
            pygame.draw.rect(surface, HOVER_COLOR, rect.inflate(6, 6), width=2)
        key_label = font.render(str(tile_id), True, TEXT_COLOR)
        surface.blit(key_label, (rect.x + 3, rect.y + 2))

    center_y = MAP_H + TOOLBAR_H // 2

    name, _color = TILE_TYPES[selected]
    label = font.render(f"Brush: {name}", True, TEXT_COLOR)
    last = swatch_rect(len(TILE_TYPES) - 1)
    surface.blit(label, (last.right + 16, center_y - label.get_height() // 2))

    if status is not None:
        text, color = status
    else:
        text, color = "Ctrl+S save  Ctrl+O load  Ctrl+Z undo  Ctrl+Y redo", TEXT_COLOR
    msg = font.render(text, True, color)
    surface.blit(msg, (WINDOW_W - msg.get_width() - 12, center_y - msg.get_height() // 2))


# --- Main loop ----------------------------------------------------------
def main():
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("Tilemap Editor")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 22)

    tilemap = create_map(GRID_W, GRID_H)
    history = History()
    selected = 1
    stroke_before = None
    status = None
    status_until = 0

    def show_status(text, color):
        nonlocal status, status_until
        status = (text, color)
        status_until = pygame.time.get_ticks() + STATUS_DURATION_MS

    running = True
    while running:
        # 1. Input: discrete events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                ctrl_held = event.mod & pygame.KMOD_CTRL
                shift_held = event.mod & pygame.KMOD_SHIFT
                stroke_active = stroke_before is not None

                if ctrl_held and event.key == pygame.K_s:
                    try:
                        save_map(tilemap, MAP_FILE)
                        show_status(f"Saved {MAP_FILE.name}", OK_COLOR)
                    except OSError as e:
                        show_status(f"Save failed: {e}", ERROR_COLOR)

                elif ctrl_held and event.key == pygame.K_o:
                    try:
                        loaded = load_map(MAP_FILE)
                        history.record(copy_map(tilemap))
                        tilemap = loaded
                        show_status(f"Loaded {MAP_FILE.name}", OK_COLOR)
                    except FileNotFoundError:
                        show_status("No level.json yet, save first", ERROR_COLOR)
                    except (OSError, ValueError, KeyError) as e:
                        show_status(f"Load failed: {e}", ERROR_COLOR)

                elif ctrl_held and not stroke_active and (
                    event.key == pygame.K_y or (event.key == pygame.K_z and shift_held)
                ):
                    result = history.redo(tilemap)
                    if result is not None:
                        tilemap = result
                        show_status(f"Redo ({len(history.redo_stack)} left)", OK_COLOR)
                    else:
                        show_status("Nothing to redo", TEXT_COLOR)

                elif ctrl_held and not stroke_active and event.key == pygame.K_z:
                    result = history.undo(tilemap)
                    if result is not None:
                        tilemap = result
                        show_status(f"Undo ({len(history.undo_stack)} left)", OK_COLOR)
                    else:
                        show_status("Nothing to undo", TEXT_COLOR)

                elif event.key in KEY_TO_TILE:
                    selected = KEY_TO_TILE[event.key]

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                clicked = tile_at_swatch(event.pos)
                if clicked is not None:
                    selected = clicked

        if status is not None and pygame.time.get_ticks() > status_until:
            status = None

        # Input: continuous state. One stroke = press, drag, release.
        hovered = mouse_to_tile(pygame.mouse.get_pos())
        left, _middle, right = pygame.mouse.get_pressed()

        if (left or right) and stroke_before is None and in_bounds(hovered):
            stroke_before = copy_map(tilemap)   

        if stroke_before is not None:
            if left:
                set_tile(tilemap, hovered, selected)
            elif right:
                set_tile(tilemap, hovered, EMPTY)
            else:                                       
                if tilemap != stroke_before:        # compares contents
                    history.record(stroke_before)
                stroke_before = None

        # Render
        screen.fill(BG_COLOR)
        draw_tiles(screen, tilemap)
        draw_grid(screen)
        draw_hover(screen, hovered)
        draw_toolbar(screen, selected, font, status)
        pygame.display.flip()

        clock.tick(FPS)

    pygame.quit()


if __name__ == "__main__":
    main()