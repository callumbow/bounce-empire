import pygame
import sys
import random
import math
import os
import asyncio

pygame.init()

# ------------------ WEB-SAFE DISPLAY ------------------
WIDTH      = 1280
HEIGHT     = 720
GAME_WIDTH = int(WIDTH * (600 / 900))
SHOP_WIDTH = WIDTH - GAME_WIDTH

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Bounce Empire")

WHITE        = (240, 240, 240)
BLACK        = (15,  15,  15)
DARK_BG      = (20,  20,  20)
DARKER       = (35,  35,  35)
LOCKED_COLOR = (60,  60,  60)
GREEN        = (0,   255, 0)
YELLOW       = (255, 255, 0)
RED          = (255, 0,   0)
GOLD         = (255, 215, 0)
ORANGE       = (255, 140, 0)
PURPLE       = (160, 0,   220)
PURPLE_DARK  = (60,  0,   80)

font       = pygame.font.SysFont(None, 28)
big_font   = pygame.font.SysFont(None, 42)
title_font = pygame.font.SysFont(None, 120)
med_font   = pygame.font.SysFont(None, 52)

clock = pygame.time.Clock()

# ------------------ HIGH SCORE ------------------
_BASE_DIR = os.path.dirname(__file__) or "."

def rel_path(*parts):
    return os.path.join(_BASE_DIR, *parts)

HIGHSCORE_FILE_NORMAL = rel_path("highscore.txt")
HIGHSCORE_FILE_GOON   = rel_path("highscore_goon.txt")
HIGHSCORE_FILE_DEV    = rel_path("highscore_dev.txt")

def _hs_file():
    if cheat_mode: return HIGHSCORE_FILE_DEV
    if goon_mode:  return HIGHSCORE_FILE_GOON
    return HIGHSCORE_FILE_NORMAL

def load_highscore():
    try:
        with open(_hs_file(), "r") as f:
            return int(f.read().strip())
    except Exception:
        return 0

def save_highscore(score):
    try:
        with open(_hs_file(), "w") as f:
            f.write(str(score))
    except Exception:
        pass

highscore      = 0   # set properly after mode globals exist (see below)
_hs_dirty      = False
_hs_save_timer = 0

# ------------------ GAME STATE ------------------
STATE_MENU = "menu"
STATE_GAME = "game"
STATE_CODE = "code"
state = STATE_MENU

coins          = 0
green_coins    = 0   # New World currency (green coins)
start_coins_override = None
free_shop = False
cheat_mode     = False
goon_mode      = False
code_input     = ""
code_message   = ""
code_msg_timer = 0

DEV_COINS = 10 ** 18

def fmt_price(p):
    """Format a shop price compactly."""
    if p >= 1_000_000_000_000_000: return f"£{p/1_000_000_000_000_000:.1f}Q"
    if p >= 1_000_000_000_000:     return f"£{p/1_000_000_000_000:.1f}T"
    if p >= 1_000_000_000: return f"£{p/1_000_000_000:.1f}B"
    if p >= 1_000_000:     return f"£{p/1_000_000:.1f}M"
    if p >= 1_000:         return f"£{p/1_000:.0f}K"
    return f"£{p}"

def fmt_coins(c):
    if cheat_mode: return "\u221e"
    if c >= 1_000_000_000_000_000:  return f"\xa3{c/1_000_000_000_000_000:.2f}Q"
    if c >= 1_000_000_000_000:      return f"\xa3{c/1_000_000_000_000:.2f}T"
    if c >= 1_000_000_000:  return f"\xa3{c/1_000_000_000:.2f}B"
    if c >= 1_000_000:      return f"\xa3{c/1_000_000:.2f}M"
    if c >= 1_000:          return f"\xa3{c/1_000:.1f}K"
    return f"\xa3{c}"

# ------------------ CLICK ANIMATION ------------------
click_animations = []
CLICK_ANIM_TIME  = 200

# ------------------ PERF SAFETY CAPS ------------------
# FIX: Drastically reduced beam cap and tightened shot limit to prevent crash/lag
LASER_MIN_COOLDOWN_MS    = 300          # was 120 — prevent rapid-fire spam
LASER_MAX_SHOTS_PER_TICK = 3            # max beams per bouncer (visible limit)
LASER_MAX_ACTIVE_BEAMS   = 60           # raised cap — new beams always added on bounce
MAX_FLASH_PARTICLES      = 600          # was 1800
MAX_EXPLOSION_PARTICLES  = 800          # was 2400
DONUT_GOON_MAX           = 20
DONUT_INCOME_PER_SEC     = 1_000_000_000_000_000

# FIX: Laser beams now have a shorter max life to self-clean faster
LASER_BEAM_DECAY = 0.025               # was 0.012

# Scrollable shop layout (larger buttons)
SHOP_ROW_H       = 56
SHOP_ROW_GAP     = 10
SHOP_PANEL_TOP   = 42
SHOP_PANEL_BOTTOM_PAD = 10
shop_scroll_offset = 0.0
all_goons_mode = False   # when True, shop shows "upgrade ALL goons at once" tab

def shop_item_rect(i, scroll_off=0.0):
    y = int(SHOP_PANEL_TOP + i * (SHOP_ROW_H + SHOP_ROW_GAP) - scroll_off)
    return pygame.Rect(GAME_WIDTH + 10, y, SHOP_WIDTH - 20, SHOP_ROW_H)

def shop_max_scroll(item_count):
    content_h = max(0, item_count * (SHOP_ROW_H + SHOP_ROW_GAP) - SHOP_ROW_GAP)
    viewport_h = HEIGHT - SHOP_PANEL_TOP - SHOP_PANEL_BOTTOM_PAD
    return max(0.0, float(content_h - viewport_h))

def shop_nav_rects():
    tab = pygame.Rect(GAME_WIDTH + 10, 6, SHOP_WIDTH - 20, 28)
    left  = pygame.Rect(tab.x + 6,        tab.y + 4, 22, tab.height - 8)
    right = pygame.Rect(tab.right - 28,   tab.y + 4, 22, tab.height - 8)
    # ALL button sits between centre and right arrow
    all_btn = pygame.Rect(tab.right - 56, tab.y + 4, 26, tab.height - 8)
    return tab, left, right, all_btn

def all_goons_shop_data():
    """
    Build a merged shop list for ALL goons:
    each item's price = sum of that item's current price across every bouncer
    (so buying it upgrades every goon simultaneously).
    """
    if not bouncers:
        return []
    template = bouncers[0].shop_data
    rows = []
    for idx, item in enumerate(template):
        total_price = sum(b.shop_data[idx]["price"] for b in bouncers if idx < len(b.shop_data))
        rows.append({
            "name":       item["name"],
            "price":      total_price,
            "base_price": item["base_price"],
            "action":     item["action"],
            "bought":     min(b.shop_data[idx]["bought"] for b in bouncers if idx < len(b.shop_data)),
        })
    return rows

def all_goons_is_unlocked(idx):
    """Unlocked if ALL bouncers have it unlocked."""
    return all(b.is_unlocked(idx) for b in bouncers)

# ------------------ HUD TEXT CACHE ------------------
_hud_cache: dict = {}

def hud_surf(key, text, fnt, color):
    full_key = (key, color)
    entry = _hud_cache.get(full_key)
    if entry is None or entry[0] != text:
        _hud_cache[full_key] = (text, fnt.render(text, True, color))
    return _hud_cache[full_key][1]

# ------------------ BASE SHOP ------------------
BASE_SHOP = [
    {"name": "Speed +5%",          "base_price": 2,         "action": "speed"},
    {"name": "Size +5%",           "base_price": 5,         "action": "size"},
    {"name": "Coin Bouncer",       "base_price": 15,        "action": "jew"},
    {"name": "Flashing Bouncer",   "base_price": 50,        "action": "flash"},
    {"name": "Trail Bouncer",      "base_price": 100,       "action": "trail"},
    {"name": "Bonus Bouncer",      "base_price": 500,       "action": "bonus"},
    {"name": "Wave Bouncer",       "base_price": 1000,      "action": "wave"},
    {"name": "Laser Bouncer",      "base_price": 15000,     "action": "laser"},
    {"name": "Implosion Bouncer",  "base_price": 250000,    "action": "implosion"},
    {"name": "Lightning Bouncer",  "base_price": 5000000,  "action": "lightning"},
    {"name": "Goon Factory",        "base_price": 2000000000,"action": "factory"},
    {"name": "Illuminate",            "base_price": 250000000000,"action": "illuminate"},
    {"name": "Gravity Well",           "base_price": 5000000000000,"action": "gravity"},
    {"name": "3D Mode",                  "base_price": 500000000000000,"action": "mode3d"},
    {"name": "Donut Ring",               "base_price": 15000000000000000,"action": "donut"},
    {"name": "God Goon",                "base_price": 375000000000000000,"action": "goongod"},
    {"name": "New World",               "base_price": 10000000000000000000,"action": "newworld"},
]

GOON_SHOP = [
    {"name": "Goon Speed +5%",       "base_price": 2,         "action": "speed"},
    {"name": "Goon Size +5%",        "base_price": 5,         "action": "size"},
    {"name": "Goon Coin Goon",       "base_price": 15,        "action": "jew"},
    {"name": "Goon Flash Goon",      "base_price": 50,        "action": "flash"},
    {"name": "Goon Trail Goon",      "base_price": 100,       "action": "trail"},
    {"name": "Bonus Goon",           "base_price": 500,       "action": "bonus"},
    {"name": "Goon Wave Goon",       "base_price": 1000,      "action": "wave"},
    {"name": "Goon Laser Goon",      "base_price": 15000,     "action": "laser"},
    {"name": "Goon Implosion Goon",  "base_price": 250000,    "action": "implosion"},
    {"name": "Goon Lightning Goon",  "base_price": 5000000,  "action": "lightning"},
    {"name": "Goon Factory Goon",    "base_price": 2000000000,"action": "factory"},
    {"name": "Goon Illuminate Goon",   "base_price": 250000000000,"action": "illuminate"},
    {"name": "Goon Gravity Goon",      "base_price": 5000000000000,"action": "gravity"},
    {"name": "Goon 3D Goon",             "base_price": 500000000000000,"action": "mode3d"},
    {"name": "Donut Goon",               "base_price": 15000000000000000,"action": "donut"},
    {"name": "Goon God Goon",           "base_price": 375000000000000000,"action": "goongod"},
    {"name": "Goon New World",           "base_price": 10000000000000000000,"action": "newworld"},
]

def active_shop():
    return GOON_SHOP if goon_mode else BASE_SHOP

def build_shop_data(existing=None):
    prev = {}
    if existing:
        prev = {it["action"]: it for it in existing}
    rows = []
    for it in active_shop():
        old = prev.get(it["action"])
        rows.append({
            "name": it["name"],
            "price": old["price"] if old else it["base_price"],
            "base_price": it["base_price"],
            "action": it["action"],
            "bought": old["bought"] if old else 0
        })
    return rows

# ------------------ DRIP PARTICLES (goon mode) ------------------
# layout: [x, y, vy, width, length, alpha, decay]
drip_particles = []
MAX_DRIP_PARTICLES = 120
_drip_spawn_timer  = 0

def update_spawn_drips(now):
    global _drip_spawn_timer
    if not goon_mode: return
    if now - _drip_spawn_timer < 80: return
    _drip_spawn_timer = now
    if len(drip_particles) >= MAX_DRIP_PARTICLES: return
    x = random.randint(0, WIDTH)
    drip_particles.append([float(x), -random.randint(0, 60),
                            random.uniform(1.5, 4.0),
                            random.randint(3, 9),
                            random.randint(20, 60),
                            random.randint(160, 255),
                            random.uniform(0.4, 1.2)])

def draw_drips(surface):
    if not goon_mode: return
    i = 0
    while i < len(drip_particles):
        d = drip_particles[i]
        d[1] += d[2]   # fall
        if d[1] > HEIGHT + 80:
            drip_particles[i] = drip_particles[-1]; drip_particles.pop()
            continue
        alpha = max(0, int(d[5]))
        col   = (alpha, alpha, alpha)
        x, y, w, ln = int(d[0]), int(d[1]), d[3], d[4]
        # drip body
        pygame.draw.rect(surface, col, (x - w//2, y, w, ln))
        # rounded drop at bottom
        pygame.draw.circle(surface, col, (x, y + ln), w)
        i += 1

# Pre-baked implosion hold glow surfaces
_IMP_HOLD_GLOWS = []
for _gr, _ga in [(32, 25), (20, 55), (12, 110), (6, 220), (3, 255)]:
    _gs = pygame.Surface((_gr * 2, _gr * 2), pygame.SRCALPHA)
    pygame.draw.circle(_gs, (255, 255, 255, _ga), (_gr, _gr), _gr)
    _IMP_HOLD_GLOWS.append((_gr, _gs))

# Pre-baked trail colours
TRAIL_COLORS = []
for _i in range(40):
    _c = pygame.Color(0)
    _c.hsva = ((_i * 10) % 360, 100, 100, 100)
    TRAIL_COLORS.append((int(_c.r), int(_c.g), int(_c.b)))

# ------------------ PARTICLES ------------------
flash_particles     = []
explosion_particles = []
_EXP_COLORS = [(255,80,0),(255,160,0),(255,220,0),(255,40,40),(255,0,0)]
_TWO_PI     = 2.0 * math.pi

def spawn_flash_particles(cx, cy, color):
    free_slots = MAX_FLASH_PARTICLES - len(flash_particles)
    if free_slots <= 0:
        return
    r, g, b = color
    br, bg, bb = min(r+80,255), min(g+80,255), min(b+80,255)
    cos_f = math.cos; sin_f = math.sin; uni = random.uniform; randi = random.randint
    count = min(randi(10, 20), free_slots)   # FIX: reduced particle count
    for _ in range(count):
        a   = uni(0, _TWO_PI)
        spd = uni(3, 9)
        flash_particles.append([cx, cy, cos_f(a)*spd, sin_f(a)*spd,
                                 br, bg, bb, 1.0, uni(0.03, 0.07), randi(3, 7)])

def spawn_explosion(cx, cy):
    free_slots = MAX_EXPLOSION_PARTICLES - len(explosion_particles)
    if free_slots <= 0:
        return
    cos_f = math.cos; sin_f = math.sin; uni = random.uniform
    randi = random.randint; choice = random.choice
    count = min(randi(8, 15), free_slots)   # FIX: reduced particle count
    for _ in range(count):
        a   = uni(0, _TWO_PI)
        spd = uni(2, 8)
        ec  = choice(_EXP_COLORS)
        explosion_particles.append([cx, cy, cos_f(a)*spd, sin_f(a)*spd,
                                     ec[0], ec[1], ec[2], 1.0, uni(0.04, 0.09), randi(3, 8)])

def update_draw_particles(plist, surface, life_fade):
    draw_circle = pygame.draw.circle
    i = 0
    while i < len(plist):
        p     = plist[i]
        p[0] += p[2];  p[1] += p[3]
        p[2] *= 0.93;  p[3] *= 0.93
        p[7] -= p[8]
        if p[7] <= 0:
            plist[i] = plist[-1]; plist.pop()
        else:
            if life_fade:
                lf  = p[7]
                col = (int(p[4]*lf), int(p[5]*lf), int(p[6]*lf))
            else:
                col = (p[4], p[5], p[6])
            draw_circle(surface, col, (int(p[0]), int(p[1])), max(1, int(p[9])))
            i += 1

# ------------------ WAVE RING ------------------
WAVE_MAX_RADIUS = int(math.hypot(GAME_WIDTH, HEIGHT)) + 40

class WaveRing:
    __slots__ = ('x','y','radius','max_radius','color','alive',
                 'origin_side','paid_opposite','_draw_col','payout')
    def __init__(self, x, y, color, origin_side, payout=300):
        self.x = x; self.y = y
        self.radius       = 10
        self.max_radius   = WAVE_MAX_RADIUS
        self.color        = color
        self.alive        = True
        self.origin_side  = origin_side
        self.paid_opposite= False
        self.payout       = int(max(1, payout))
        r, g, b           = color
        self._draw_col    = (min(r+60,255), min(g+60,255), min(b+60,255))

    def update(self):
        global coins
        self.radius += 4
        if self.radius >= self.max_radius:
            self.alive = False
            return
        if not self.paid_opposite:
            os = self.origin_side
            if ((os=='left'   and self.radius >= GAME_WIDTH - self.x) or
                (os=='right'  and self.radius >= self.x) or
                (os=='top'    and self.radius >= HEIGHT   - self.y) or
                (os=='bottom' and self.radius >= self.y)):
                coins += self.payout
                self.paid_opposite = True

    def draw(self, surface):
        r = int(self.radius)
        if r < 1: return
        fade = max(0.0, 1.0 - self.radius / self.max_radius)
        thickness = max(1, int(8 * fade))
        # Outer glow ring
        cr, cg, cb = self._draw_col
        glow_col = (int(cr * fade), int(cg * fade), int(cb * fade))
        if thickness > 1:
            pygame.draw.circle(surface, glow_col,    (int(self.x), int(self.y)), r + 2, thickness + 3)
        pygame.draw.circle(surface, self._draw_col, (int(self.x), int(self.y)), r,     thickness)
        # bright inner highlight
        if fade > 0.3 and r > 4:
            hi = (min(255, int(cr + 80*fade)), min(255, int(cg + 80*fade)), min(255, int(cb + 80*fade)))
            pygame.draw.circle(surface, hi, (int(self.x), int(self.y)), max(1, r - 1), max(1, thickness - 1))

wave_rings = []

# ------------------ LASER BEAM ------------------
class LaserBeam:
    __slots__ = ('x','y','vx','vy','life','decay','trail','trail_len','alive')
    def __init__(self, x, y, angle):
        self.x  = float(x); self.y = float(y)
        self.vx = math.cos(angle) * 10.0
        self.vy = math.sin(angle) * 10.0
        self.life      = 1.0
        self.decay     = 0.010          # slow decay = longer life
        self.trail     = [(self.x, self.y)]
        self.trail_len = 22             # longer trail
        self.alive     = True

    def update(self):
        self.x += self.vx; self.y += self.vy
        bounced = False
        if self.x <= 0 or self.x >= GAME_WIDTH:
            self.vx = -self.vx
            self.x  = max(0.0, min(float(GAME_WIDTH), self.x))
            bounced = True
        if self.y <= 0 or self.y >= HEIGHT:
            self.vy = -self.vy
            self.y  = max(0.0, min(float(HEIGHT), self.y))
            bounced = True
        if bounced:
            if random.random() < 0.4:
                spawn_explosion(int(self.x), int(self.y))
        self.trail.append((self.x, self.y))
        if len(self.trail) > self.trail_len:
            self.trail.pop(0)
        self.life -= self.decay
        if self.life <= 0:
            self.alive = False

    def draw(self, surface):
        tr = self.trail
        if len(tr) < 2: return
        n = len(tr); life = self.life
        draw_line = pygame.draw.line
        for i in range(1, n):
            bright = (i / n) * life
            p0 = (int(tr[i-1][0]), int(tr[i-1][1]))
            p1 = (int(tr[i][0]),   int(tr[i][1]))
            draw_line(surface, (int(140*bright), 0, 0), p0, p1, 18)   # thick glow
            draw_line(surface, (int(255*bright), int(60*bright), 0), p0, p1, 10)  # mid
            draw_line(surface, (255, int(200*bright), int(200*bright)), p0, p1, 4) # bright core
        pygame.draw.circle(surface, (255, 120, 120), (int(self.x), int(self.y)), 10)
        pygame.draw.circle(surface, (255, 255, 255), (int(self.x), int(self.y)), 5)

laser_beams = []

# ------------------ LIGHTNING SYSTEM ------------------
LIGHTNING_LIFETIME_MS  = 600
LIGHTNING_PAYOUT       = 100000

lightning_sessions = []

def _jagged_line_points(x1, y1, x2, y2, jag=14, segs=8):
    pts = [(x1, y1)]
    dx = x2 - x1; dy = y2 - y1
    length = math.hypot(dx, dy)
    if length == 0:
        return [(x1, y1), (x2, y2)]
    px = -dy / length; py = dx / length
    for i in range(1, segs):
        t   = i / segs
        mx  = x1 + dx * t
        my  = y1 + dy * t
        off = random.uniform(-jag, jag)
        pts.append((mx + px * off, my + py * off))
    pts.append((x2, y2))
    return pts

class LightningSession:
    __slots__ = ("edges", "born", "alive")

    def __init__(self, origin_bouncer, payout_per_hit):
        global coins
        self.born  = pygame.time.get_ticks()
        self.alive = True
        self.edges = []

        visited  = {id(origin_bouncer)}
        frontier = [origin_bouncer]
        total_pay = 0

        while frontier:
            next_frontier = []
            for src in frontier:
                candidates = []
                for b in bouncers:
                    if id(b) in visited: continue
                    d = math.hypot(b.rect.centerx - src.rect.centerx,
                                   b.rect.centery - src.rect.centery)
                    candidates.append((d, b))
                candidates.sort(key=lambda t: t[0])
                for _, tgt in candidates[:2]:
                    visited.add(id(tgt))
                    next_frontier.append(tgt)
                    sx, sy = src.rect.centerx, src.rect.centery
                    tx, ty = tgt.rect.centerx, tgt.rect.centery
                    pts = _jagged_line_points(sx, sy, tx, ty)
                    self.edges.append(pts)
                    total_pay += payout_per_hit
            frontier = next_frontier

        coins += total_pay

    def update(self):
        if pygame.time.get_ticks() - self.born >= LIGHTNING_LIFETIME_MS:
            self.alive = False

    def draw(self, surface):
        age     = pygame.time.get_ticks() - self.born
        alpha_f = max(0.0, 1.0 - age / LIGHTNING_LIFETIME_MS)
        if alpha_f <= 0: return
        draw_line = pygame.draw.line
        draw_circle = pygame.draw.circle
        for pts in self.edges:
            ipts = [(int(p[0]), int(p[1])) for p in pts]
            for i in range(1, len(ipts)):
                p0, p1 = ipts[i-1], ipts[i]
                # outer blue halo
                draw_line(surface, (0, int(30*alpha_f), int(120*alpha_f)), p0, p1, 14)
                # mid purple-blue
                draw_line(surface, (int(100*alpha_f), int(100*alpha_f), int(255*alpha_f)), p0, p1, 6)
                # bright white-blue core
                draw_line(surface, (int(220*alpha_f), int(220*alpha_f), int(255*alpha_f)), p0, p1, 2)
            # glow dot at each node
            for p in ipts[::max(1, len(ipts)//4)]:
                r2 = max(2, int(8 * alpha_f))
                draw_circle(surface, (int(180*alpha_f), int(180*alpha_f), 255), p, r2)

# ------------------ IMPLOSION SYSTEM ------------------
IMP_IDLE    = 0
IMP_SHRINK  = 1
IMP_HOLD    = 2
IMP_EXPLODE = 3
IMP_GRACE   = 4

IMPLOSION_SHRINK_MS   = 600
IMPLOSION_HOLD_MS     = 500
IMPLOSION_EXPLODE_MS  = 400
IMPLOSION_GRACE_MS    = 300
IMPLOSION_BASE_WINDOW = 60000
WALL_MARGIN           = 120

class ImplosionEffect:
    __slots__ = ('owner','phase','phase_start','spin_angle','_orig_size',
                 '_cx','_cy','_anim_ms','last_finish')
    def __init__(self, owner):
        self.owner       = owner
        self.phase       = IMP_IDLE
        self.phase_start = 0
        self.spin_angle  = 0.0
        self._orig_size  = owner.size
        self._cx         = owner.rect.centerx
        self._cy         = owner.rect.centery
        self._anim_ms    = (IMPLOSION_SHRINK_MS + IMPLOSION_HOLD_MS +
                            IMPLOSION_EXPLODE_MS + IMPLOSION_GRACE_MS)
        self.last_finish = pygame.time.get_ticks() - self._cooldown()

    def _cooldown(self):
        p = max(self.owner.bought_count("implosion"), 1)
        return max(2000, IMPLOSION_BASE_WINDOW // p - self._anim_ms)

    def _owner_safe(self):
        if cheat_mode: return True
        r = self.owner.rect
        if r.left < WALL_MARGIN or r.right > GAME_WIDTH - WALL_MARGIN: return False
        if r.top  < WALL_MARGIN or r.bottom > HEIGHT - WALL_MARGIN:    return False
        return True

    def _start_shrink(self, now):
        self.phase       = IMP_SHRINK
        self.phase_start = now
        self._orig_size  = self.owner.size
        self.owner.implosion_frozen = False
        self._cx = self.owner.rect.centerx
        self._cy = self.owner.rect.centery

    def _start_hold(self, now):
        self.phase       = IMP_HOLD
        self.phase_start = now
        self.spin_angle  = 0.0

    def _start_explode(self, now):
        global coins
        self.phase       = IMP_EXPLODE
        self.phase_start = now
        cx, cy = self._cx, self._cy
        o = self.owner
        prev_speed = math.hypot(o.speed_x, o.speed_y)
        purchases = max(o.bought_count("implosion"), 1)
        o.size = self._orig_size
        o.rect.width = o.rect.height = self._orig_size
        o.rect.center = (cx, cy)
        o.fx = float(o.rect.x); o.fy = float(o.rect.y)
        o.implosion_frozen = False
        ang = random.uniform(0, _TWO_PI)
        carry      = min(prev_speed * 0.8, 450.0)
        base_blast = random.uniform(900.0, 1300.0) * (1.0 + 0.12 * (purchases - 1))
        blast_spd  = carry + base_blast
        o.speed_x = math.cos(ang) * blast_spd
        o.speed_y = math.sin(ang) * blast_spd
        coins += 300000 * o.earnings_multiplier()
        for _ in range(4): spawn_explosion(cx, cy)

    def _start_grace(self, now):
        self.phase = IMP_GRACE; self.phase_start = now

    def _finish(self, now):
        self.last_finish = now; self.phase = IMP_IDLE

    def update(self):
        now = pygame.time.get_ticks()
        ph  = self.phase
        if ph == IMP_IDLE:
            if now - self.last_finish >= self._cooldown() and self._owner_safe():
                self._start_shrink(now)
        elif ph == IMP_SHRINK:
            elapsed  = now - self.phase_start
            progress = min(elapsed / IMPLOSION_SHRINK_MS, 1.0)
            self.spin_angle += 0.10
            o        = self.owner
            new_size = max(4, int(self._orig_size * (1.0 - progress * progress)))
            cx_live  = o.rect.centerx; cy_live = o.rect.centery
            o.size = new_size
            o.rect.width = o.rect.height = new_size
            o.rect.centerx = cx_live; o.rect.centery = cy_live
            o.fx = float(o.rect.x); o.fy = float(o.rect.y)
            self._cx = cx_live; self._cy = cy_live
            if progress >= 1.0:
                o.size = 4; o.rect.width = o.rect.height = 4
                self._cx = o.rect.centerx; self._cy = o.rect.centery
                o.implosion_frozen = True
                self._start_hold(now)
        elif ph == IMP_HOLD:
            self.spin_angle += 0.18
            if now - self.phase_start >= IMPLOSION_HOLD_MS:
                self._start_explode(now)
        elif ph == IMP_EXPLODE:
            if now - self.phase_start >= IMPLOSION_EXPLODE_MS:
                self._start_grace(now)
        elif ph == IMP_GRACE:
            if now - self.phase_start >= IMPLOSION_GRACE_MS:
                self._finish(now)

    def _draw_pulsar_beams(self, surface, cx, cy, strength, base_len):
        if strength <= 0.0:
            return
        now = pygame.time.get_ticks()
        beam_count = 8
        core_col = (
            min(255, int(170 + 80 * strength)),
            min(255, int(190 + 65 * strength)),
            255
        )
        glow_col = (
            min(255, int(70 + 110 * strength)),
            min(255, int(90 + 120 * strength)),
            min(255, int(140 + 95 * strength))
        )
        core_w = max(1, int(2 + 3 * strength))
        glow_w = core_w + 5

        for i in range(beam_count):
            spoke = self.spin_angle + i * (_TWO_PI / beam_count)
            wobble = 0.22 * math.sin(now / 130.0 + i * 1.2)
            ang = spoke + wobble
            pulse = 0.75 + 0.25 * math.sin(now / 95.0 + i * 1.7)
            beam_len = int(base_len * pulse)
            ex = cx + int(math.cos(ang) * beam_len)
            ey = cy + int(math.sin(ang) * beam_len)
            pygame.draw.line(surface, glow_col, (cx, cy), (ex, ey), glow_w)
            pygame.draw.line(surface, core_col, (cx, cy), (ex, ey), core_w)

    def draw(self, surface):
        now = pygame.time.get_ticks()
        cx  = self._cx; cy = self._cy
        ph  = self.phase
        cos_f = math.cos; sin_f = math.sin

        if ph == IMP_SHRINK:
            elapsed  = now - self.phase_start
            progress = min(elapsed / IMPLOSION_SHRINK_MS, 1.0)
            ease     = progress * progress
            self._draw_pulsar_beams(surface, cx, cy, ease, int(self._orig_size * 1.6))
            glow_r   = max(2, int(self._orig_size * 0.6 * (1.0 - ease * 0.7)))
            wa       = int(80 + 175 * ease)
            for gr, ga in [(glow_r, max(0,wa-120)), (glow_r//2, max(0,wa-60)),
                           (max(2,glow_r//4), wa)]:
                if gr < 1: continue
                gs = pygame.Surface((gr*2, gr*2), pygame.SRCALPHA)
                pygame.draw.circle(gs, (255,255,255,min(255,ga)), (gr,gr), gr)
                surface.blit(gs, (cx-gr, cy-gr))
            ob = int(self._orig_size * 0.8 * (1.0 - ease * 0.5) + 12)
            for i in range(5):
                ang = self.spin_angle + i * (_TWO_PI / 5)
                orb = max(8, ob + int(6 * math.sin(elapsed/120 + i*1.1)))
                for t in range(6):
                    tr = orb - t
                    if tr < 2: continue
                    ta = ang - t*0.12
                    bv = int(200 * ease * (1 - t/6))
                    pygame.draw.circle(surface, (bv,bv,bv),
                        (cx+int(cos_f(ta)*tr), cy+int(sin_f(ta)*tr)), max(1,4-t))
                bh = int(255*ease)
                pygame.draw.circle(surface, (bh,bh,bh),
                    (cx+int(cos_f(ang)*orb), cy+int(sin_f(ang)*orb)), max(1,int(5*ease)))

        elif ph == IMP_HOLD:
            self._draw_pulsar_beams(surface, cx, cy, 1.0, int(self._orig_size * 1.9))
            for gr, gs in _IMP_HOLD_GLOWS:
                surface.blit(gs, (cx-gr, cy-gr))
            pygame.draw.circle(surface, (255,255,255), (cx,cy), 4)
            elapsed = now - self.phase_start
            for i in range(5):
                ang = self.spin_angle + i * (_TWO_PI / 5)
                orb = int(38 + 10 * math.sin(elapsed/120 + i*1.1))
                for t in range(8):
                    tr = orb - t
                    if tr < 2: continue
                    ta = ang - t*0.12
                    bv = int(255*(1-t/8))
                    pygame.draw.circle(surface, (bv,bv,bv),
                        (cx+int(cos_f(ta)*tr), cy+int(sin_f(ta)*tr)), max(1,5-t))
                pygame.draw.circle(surface, (255,255,255),
                    (cx+int(cos_f(ang)*orb), cy+int(sin_f(ang)*orb)), 5)

        elif ph == IMP_EXPLODE:
            elapsed  = now - self.phase_start
            progress = min(elapsed / IMPLOSION_EXPLODE_MS, 1.0)
            shock_r  = int(progress * 280)
            if shock_r > 0:
                thick = max(1, int(10*(1-progress)))
                pygame.draw.circle(surface, (255,255,255), (cx,cy), shock_r, thick)
                ir = int(shock_r*0.6)
                if ir > 0:
                    pygame.draw.circle(surface, (200,200,255), (cx,cy), ir, max(1,thick-2))

    def draw_cooldown_hud(self, surface):
        if self.phase != IMP_IDLE: return
        now      = pygame.time.get_ticks()
        progress = min((now - self.last_finish) / self._cooldown(), 1.0)
        bx = self.owner.rect.x; by = self.owner.rect.bottom + 4
        bw = self.owner.rect.width
        pygame.draw.rect(surface, (40,0,60),  (bx, by, bw, 5))
        pygame.draw.rect(surface, PURPLE,     (bx, by, int(bw*progress), 5))

implosion_effects = []

# ------------------ MENU BACKGROUND BOUNCERS ------------------
class BgBouncer:
    __slots__ = ('x','y','vx','vy','_surf','_size')
    def __init__(self):
        self._size = random.randint(20, 60)
        self.x     = random.randint(0, WIDTH)
        self.y     = random.randint(0, HEIGHT)
        spd        = random.uniform(1, 3)
        ang        = random.uniform(0, _TWO_PI)
        self.vx    = math.cos(ang) * spd
        self.vy    = math.sin(ang) * spd
        color      = (random.randint(60,200), random.randint(60,200), random.randint(60,200))
        alpha      = random.randint(40, 120)
        s = pygame.Surface((self._size, self._size), pygame.SRCALPHA)
        s.fill((*color, alpha))
        self._surf = s

    def update(self):
        self.x += self.vx; self.y += self.vy
        if self.x < 0 or self.x > WIDTH:  self.vx = -self.vx
        if self.y < 0 or self.y > HEIGHT: self.vy = -self.vy

    def draw(self, surface):
        surface.blit(self._surf, (int(self.x), int(self.y)))

bg_bouncers = [BgBouncer() for _ in range(25)]

# ------------------ FACTORY SYSTEM ------------------
factories = []
_factory_income_timer = 0
FACTORY_INCOME_PER_SEC = 100_000_000

class Factory:
    """
    Two pale vertical cylinders connected by a long horizontal pipe in the middle.
    White liquid drips from the tops of both cylinders.
    """
    __slots__ = ('x', 'phase', 'gear_angle', 'liquid_drops', '_drop_timer',
                 'valve_angle', 'pressure_pulse')

    CYL_W    = 32    # cylinder width
    CYL_H    = 130   # cylinder height
    PIPE_H   = 18    # connecting pipe height (vertical centre position)
    SPACING  = 68    # centre-to-centre of the two cylinders

    def __init__(self, x):
        self.x             = x
        self.phase         = random.uniform(0, 6.28)
        self.gear_angle    = 0.0
        self.valve_angle   = 0.0
        self.pressure_pulse= random.uniform(0, 6.28)
        self._drop_timer   = random.uniform(0, 0.4)
        # drops: [x, y, vy, size, alpha, phase_off]
        self.liquid_drops  = []
        for _ in range(6):
            self.liquid_drops.append(self._new_drop(random.choice([-1, 1])))

    def _cyl_cx(self, side):
        """Centre-x of left (side=-1) or right (side=+1) cylinder."""
        return self.x + side * self.SPACING // 2

    def _new_drop(self, side):
        cx   = self._cyl_cx(side)
        top_y = HEIGHT - self.CYL_H - 4
        return [
            float(cx + random.randint(-self.CYL_W//2 + 4, self.CYL_W//2 - 4)),
            float(top_y),
            random.uniform(28.0, 55.0),   # fall speed
            random.uniform(3.5, 6.0),     # blob radius
            1.0,                          # alpha (life)
            random.choice([-1, 1]),       # which cylinder
        ]

    def update(self, dt, now):
        self.gear_angle     += 1.4 * dt
        self.valve_angle    += 0.7 * dt
        self.pressure_pulse += 2.1 * dt

        self._drop_timer -= dt
        if self._drop_timer <= 0.0:
            self._drop_timer = random.uniform(0.06, 0.18)
            side = random.choice([-1, 1])
            if len(self.liquid_drops) < 40:
                self.liquid_drops.append(self._new_drop(side))

        i = 0
        while i < len(self.liquid_drops):
            d = self.liquid_drops[i]
            d[1] += d[2] * dt
            d[4] -= dt * 0.55
            # splat on ground
            if d[1] > HEIGHT - 8 or d[4] <= 0:
                self.liquid_drops[i] = self.liquid_drops[-1]
                self.liquid_drops.pop()
            else:
                i += 1

    def _draw_cylinder(self, surface, cx, t):
        """Draw a single detailed pale cylinder."""
        cw   = self.CYL_W
        ch   = self.CYL_H
        by   = HEIGHT - ch  # top-left y of cylinder body

        # ── Colours (very pale, slightly warm) ────────────────────────────
        body_pale   = (230, 228, 224)
        body_mid    = (210, 208, 204)
        body_dark   = (175, 172, 168)
        body_shadow = (145, 142, 138)
        rim_col     = (245, 243, 240)
        rim_dark    = (190, 188, 184)
        highlight   = (255, 254, 252)
        seam_col    = (160, 158, 154)
        rivet_col   = (200, 198, 194)
        liquid_col  = (245, 250, 255)   # near-white blue-white

        # ── Top ellipse (rim) ──────────────────────────────────────────────
        rim_rect  = pygame.Rect(cx - cw//2, by - 8, cw, 16)
        pygame.draw.ellipse(surface, body_mid,  rim_rect)
        pygame.draw.ellipse(surface, rim_col,   pygame.Rect(cx - cw//2+2, by-6, cw-4, 12))
        pygame.draw.ellipse(surface, rim_dark,  rim_rect, 2)

        # ── Cylinder body ─────────────────────────────────────────────────
        body_rect = pygame.Rect(cx - cw//2, by, cw, ch)
        # base fill
        pygame.draw.rect(surface, body_pale, body_rect)
        # left shadow strip
        pygame.draw.rect(surface, body_shadow, (cx - cw//2, by, 6, ch))
        # right shadow strip
        pygame.draw.rect(surface, body_dark,   (cx + cw//2 - 7, by, 7, ch))
        # centre highlight strip
        hi_w = max(2, cw//4)
        pygame.draw.rect(surface, highlight,   (cx - hi_w//2, by + 4, hi_w, ch - 8))

        # ── Horizontal weld seams ──────────────────────────────────────────
        for seam_y in range(by + 24, by + ch - 10, 22):
            pygame.draw.line(surface, seam_col, (cx - cw//2, seam_y), (cx + cw//2, seam_y), 2)
            pygame.draw.line(surface, rim_col,  (cx - cw//2, seam_y+1), (cx + cw//2, seam_y+1), 1)

        # ── Rivets along seams ─────────────────────────────────────────────
        for seam_y in range(by + 24, by + ch - 10, 22):
            for rx in [cx - cw//2 + 5, cx + cw//2 - 5]:
                pygame.draw.circle(surface, rivet_col, (rx, seam_y), 3)
                pygame.draw.circle(surface, body_shadow, (rx+1, seam_y+1), 2)

        # ── Pressure gauge (small circle on body face) ────────────────────
        gx, gy = cx, by + 40
        gauge_r = 8
        pygame.draw.circle(surface, body_dark, (gx, gy), gauge_r + 2)
        pygame.draw.circle(surface, (240, 240, 220), (gx, gy), gauge_r)
        # needle
        pressure = 0.3 + 0.7 * abs(math.sin(t * 1.8 + self.pressure_pulse))
        needle_ang = -math.pi * 0.8 + pressure * math.pi * 1.6
        nex = gx + int(math.cos(needle_ang) * (gauge_r - 2))
        ney = gy + int(math.sin(needle_ang) * (gauge_r - 2))
        pygame.draw.line(surface, (220, 40, 40), (gx, gy), (nex, ney), 2)
        pygame.draw.circle(surface, body_dark, (gx, gy), 2)
        pygame.draw.circle(surface, body_shadow, (gx, gy), gauge_r + 2, 2)

        # ── Valve wheel (below gauge) ──────────────────────────────────────
        vx, vy = cx, by + 68
        pygame.draw.circle(surface, body_dark,  (vx, vy), 9, 2)
        pygame.draw.circle(surface, body_mid,   (vx, vy), 7)
        for k in range(4):
            va = self.valve_angle + k * math.pi / 2
            pygame.draw.line(surface, body_shadow,
                             (vx, vy),
                             (vx + int(math.cos(va)*9), vy + int(math.sin(va)*9)), 3)
        pygame.draw.circle(surface, seam_col, (vx, vy), 3)

        # ── Outlet nozzle at top ───────────────────────────────────────────
        nozzle_w = 8; nozzle_h = 10
        pygame.draw.rect(surface, body_dark, (cx - nozzle_w//2, by - 8 - nozzle_h, nozzle_w, nozzle_h))
        pygame.draw.rect(surface, rim_col, (cx - nozzle_w//2, by - 8 - nozzle_h, nozzle_w, nozzle_h), 1)
        # Nozzle tip ellipse
        pygame.draw.ellipse(surface, rim_dark,
                            (cx - nozzle_w//2 - 2, by - 8 - nozzle_h - 4, nozzle_w + 4, 8))

        # ── Liquid pool at top of nozzle (small meniscus) ─────────────────
        pool_pulse = 0.7 + 0.3 * math.sin(t * 5.2 + self.phase)
        pool_r = max(1, int(5 * pool_pulse))
        ps2 = pygame.Surface((pool_r*2, pool_r*2), pygame.SRCALPHA)
        pygame.draw.circle(ps2, (245, 252, 255, 220), (pool_r, pool_r), pool_r)
        surface.blit(ps2, (cx - pool_r, by - 8 - nozzle_h - pool_r - 2))

        # ── Bottom ellipse cap ─────────────────────────────────────────────
        bot_rect = pygame.Rect(cx - cw//2, HEIGHT - 18, cw, 18)
        pygame.draw.ellipse(surface, body_mid, bot_rect)
        pygame.draw.ellipse(surface, body_dark, bot_rect, 2)
        pygame.draw.rect(surface, body_pale, (cx - cw//2, HEIGHT - 12, cw, 6))

        # ── Outline ───────────────────────────────────────────────────────
        pygame.draw.rect(surface, seam_col, body_rect, 1)

    def draw(self, surface, now):
        t   = now / 1000.0
        cw  = self.CYL_W
        ch  = self.CYL_H
        cx_l = self._cyl_cx(-1)
        cx_r = self._cyl_cx(+1)
        pipe_cy = HEIGHT - ch // 2  # pipe vertical centre

        # ── Ground shadow ─────────────────────────────────────────────────
        sh_w = self.SPACING + cw + 24
        sh = pygame.Surface((sh_w, 14), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 70), (0, 4, sh_w, 10))
        surface.blit(sh, (self.x - sh_w//2, HEIGHT - 12))

        # ── Connecting horizontal pipe ────────────────────────────────────
        pipe_h     = 20   # pipe diameter
        pipe_x1    = cx_l + cw//2
        pipe_x2    = cx_r - cw//2
        pipe_top   = pipe_cy - pipe_h//2

        pipe_pale  = (220, 218, 214)
        pipe_hi    = (242, 241, 238)
        pipe_dark  = (168, 165, 160)
        pipe_seam  = (150, 148, 144)

        # Pipe body
        pygame.draw.rect(surface, pipe_pale, (pipe_x1, pipe_top, pipe_x2-pipe_x1, pipe_h))
        # Top highlight
        pygame.draw.rect(surface, pipe_hi, (pipe_x1, pipe_top+2, pipe_x2-pipe_x1, pipe_h//3))
        # Bottom shadow
        pygame.draw.rect(surface, pipe_dark, (pipe_x1, pipe_top+pipe_h*2//3, pipe_x2-pipe_x1, pipe_h//3+1))
        # Seam line
        pygame.draw.line(surface, pipe_seam, (pipe_x1, pipe_cy), (pipe_x2, pipe_cy), 1)
        # Pipe outline
        pygame.draw.rect(surface, pipe_seam, (pipe_x1, pipe_top, pipe_x2-pipe_x1, pipe_h), 1)

        # Left flange (where pipe meets cylinder)
        for fl_x in [pipe_x1, pipe_x2 - 8]:
            pygame.draw.rect(surface, pipe_dark, (fl_x, pipe_top - 4, 8, pipe_h + 8), border_radius=2)
            pygame.draw.rect(surface, pipe_pale, (fl_x+1, pipe_top - 3, 6, pipe_h + 6), border_radius=1)
            pygame.draw.rect(surface, pipe_seam, (fl_x, pipe_top - 4, 8, pipe_h + 8), 1, border_radius=2)
            # flange bolts
            for bolt_y in [pipe_top - 1, pipe_top + pipe_h + 1]:
                pygame.draw.circle(surface, pipe_dark, (fl_x + 4, bolt_y), 3)
                pygame.draw.circle(surface, pipe_pale, (fl_x + 3, bolt_y - 1), 1)

        # ── Pressure relief valve on pipe (small T-junction) ──────────────
        relief_x = (pipe_x1 + pipe_x2) // 2
        pygame.draw.rect(surface, pipe_dark, (relief_x - 5, pipe_top - 16, 10, 18))
        pygame.draw.rect(surface, pipe_pale, (relief_x - 4, pipe_top - 15, 8, 16))
        pygame.draw.ellipse(surface, pipe_dark, (relief_x - 8, pipe_top - 22, 16, 10))
        pygame.draw.ellipse(surface, pipe_hi, (relief_x - 7, pipe_top - 21, 14, 8))
        # Tiny leak drip from relief valve
        leak_phase = (t * 2.8 + self.phase) % 1.0
        leak_y = int(pipe_top - 22 + leak_phase * 20)
        if leak_y < pipe_cy:
            ls = pygame.Surface((5, 6), pygame.SRCALPHA)
            pygame.draw.ellipse(ls, (245, 252, 255, int(210*(1-leak_phase))), (0,0,5,6))
            surface.blit(ls, (relief_x - 2, leak_y))

        # ── Draw both cylinders (left then right) ─────────────────────────
        self._draw_cylinder(surface, cx_l, t)
        self._draw_cylinder(surface, cx_r, t)

        # ── Liquid drops falling from nozzle tops ────────────────────────
        for d in self.liquid_drops:
            r = max(1, int(d[3]))
            a = max(0, min(255, int(d[4] * 240)))
            # Elongate drop slightly as it falls
            drop_w = max(2, r - 1)
            drop_h = max(2, r + 2)
            ds = pygame.Surface((drop_w*2, drop_h*2), pygame.SRCALPHA)
            pygame.draw.ellipse(ds, (245, 252, 255, a), (0, 0, drop_w*2, drop_h*2))
            # Blue-white core
            if drop_w > 2:
                pygame.draw.ellipse(ds, (255, 255, 255, min(255, a+30)),
                                    (drop_w//2, drop_h//2, drop_w, drop_h))
            surface.blit(ds, (int(d[0])-drop_w, int(d[1])-drop_h))

        # ── Liquid splat puddles at base ───────────────────────────────────
        for cx_side in [cx_l, cx_r]:
            puddle_pulse = 0.65 + 0.35 * math.sin(t * 3.1 + (1 if cx_side == cx_l else -1) * 1.4 + self.phase)
            pud_r = max(3, int(12 * puddle_pulse))
            ps3 = pygame.Surface((pud_r*4, pud_r*2), pygame.SRCALPHA)
            pygame.draw.ellipse(ps3, (235, 248, 255, 130), (0, 0, pud_r*4, pud_r*2))
            pygame.draw.ellipse(ps3, (255, 255, 255, 80),
                                (pud_r//2, pud_r//4, pud_r*3, pud_r))
            surface.blit(ps3, (cx_side - pud_r*2, HEIGHT - pud_r - 4))


def update_factories(dt, now):
    global coins, _factory_income_timer
    if not factories: return
    for f in factories:
        f.update(dt, now)
    if now - _factory_income_timer >= 1000:
        ticks = (now - _factory_income_timer) // 1000
        coins += len(factories) * FACTORY_INCOME_PER_SEC * ticks
        _factory_income_timer += ticks * 1000

def draw_factories(surface, now):
    for f in factories:
        f.draw(surface, now)


# ------------------ ILLUMINATE SYSTEM ------------------
illuminate_effects = []

class IlluminateEffect:
    """A large glowing all-seeing-eye triangle with a sweeping red laser beam."""
    __slots__ = ('cx','cy','size','angle','laser_angle','laser_speed',
                 'income_timer','born','_glow_cache_t')

    INCOME_PER_SEC = 50_000_000_000
    BASE_SIZE      = 160

    def __init__(self):
        self.cx           = GAME_WIDTH // 2
        self.cy           = HEIGHT // 2
        self.size         = self.BASE_SIZE
        self.angle        = 0.0            # slow rotation of the whole triangle
        self.laser_angle  = 0.0            # laser sweep angle
        self.laser_speed  = 0.012          # radians per frame
        self.income_timer = pygame.time.get_ticks()
        self.born         = pygame.time.get_ticks()
        self._glow_cache_t = -1

    def update(self):
        global coins
        self.angle       += 0.003
        self.laser_angle += self.laser_speed
        now = pygame.time.get_ticks()
        if now - self.income_timer >= 1000:
            ticks = (now - self.income_timer) // 1000
            coins += self.INCOME_PER_SEC * ticks
            self.income_timer += ticks * 1000

    def _triangle_pts(self, cx, cy, size, angle):
        pts = []
        for k in range(3):
            a = angle + k * (2 * math.pi / 3) - math.pi / 2
            pts.append((cx + math.cos(a) * size, cy + math.sin(a) * size))
        return pts

    def draw(self, surface):
        now  = pygame.time.get_ticks()
        cx   = self.cx
        cy   = self.cy
        sz   = self.size
        ang  = self.angle
        t    = now / 1000.0

        # ── Outer glow rings (pulsing) ──────────────────────────────────────
        pulse = 0.5 + 0.5 * math.sin(t * 2.1)
        for r, a in [(sz*2.4, 18), (sz*2.0, 30), (sz*1.6, 45), (sz*1.2, 65)]:
            ir = int(r)
            if ir < 2: continue
            alpha = int(a * (0.7 + 0.3 * pulse))
            gs = pygame.Surface((ir*2, ir*2), pygame.SRCALPHA)
            pygame.draw.circle(gs, (220, 30, 30, alpha), (ir, ir), ir)
            surface.blit(gs, (cx - ir, cy - ir))

        # ── Triangle layers (thick outline → filled inner) ──────────────────
        pts_outer = self._triangle_pts(cx, cy, sz,        ang)
        pts_mid   = self._triangle_pts(cx, cy, sz * 0.92, ang)
        pts_inner = self._triangle_pts(cx, cy, sz * 0.72, ang)
        pts_fill  = self._triangle_pts(cx, cy, sz * 0.60, ang)

        # dark fill
        pygame.draw.polygon(surface, (8, 0, 0),       [(int(x),int(y)) for x,y in pts_outer])
        # gold/amber border stroke (thick)
        for p_list, thick, col in [
            (pts_outer, 6,  (200, 160, 20)),
            (pts_mid,   3,  (255, 210, 60)),
            (pts_inner, 2,  (255, 240, 120)),
        ]:
            ipts = [(int(x), int(y)) for x, y in p_list]
            pygame.draw.polygon(surface, col, ipts, thick)

        # ── Inner eye ───────────────────────────────────────────────────────
        eye_r  = int(sz * 0.30)
        eye_r2 = int(sz * 0.18)
        eye_r3 = int(sz * 0.09)

        # sclera glow
        for r2, a2 in [(eye_r + 12, 40), (eye_r + 6, 80), (eye_r, 130)]:
            gs2 = pygame.Surface((r2*2, r2*2), pygame.SRCALPHA)
            pygame.draw.circle(gs2, (255, 200, 0, a2), (r2, r2), r2)
            surface.blit(gs2, (cx - r2, cy - r2))
        pygame.draw.circle(surface, (255, 220, 40), (cx, cy), eye_r)

        # iris
        iris_pulse = 0.85 + 0.15 * math.sin(t * 3.3)
        ip = int(eye_r2 * iris_pulse)
        for r3, col3 in [(ip+4, (180, 60, 0)), (ip+2, (220, 80, 0)), (ip, (255, 120, 20))]:
            pygame.draw.circle(surface, col3, (cx, cy), r3)

        # pupil
        pp2 = int(eye_r3 * (0.9 + 0.1 * math.sin(t * 5.0)))
        pygame.draw.circle(surface, (5, 0, 0),     (cx, cy), pp2 + 2)
        pygame.draw.circle(surface, (0, 0, 0),     (cx, cy), pp2)
        # catchlight
        pygame.draw.circle(surface, (255, 255, 255), (cx - pp2//3, cy - pp2//3), max(1, pp2//4))

        # ── Radial gold lines from eye outward ──────────────────────────────
        num_spokes = 12
        for k in range(num_spokes):
            spoke_a = ang + k * (2 * math.pi / num_spokes)
            brightness = int(180 + 60 * math.sin(t * 2 + k * 0.5))
            ex = cx + int(math.cos(spoke_a) * sz * 0.55)
            ey = cy + int(math.sin(spoke_a) * sz * 0.55)
            pygame.draw.line(surface, (brightness, int(brightness*0.7), 0),
                             (cx, cy), (ex, ey), 1)

        # ── Corner decorations on triangle vertices ──────────────────────────
        for vx, vy in pts_outer:
            ivx, ivy = int(vx), int(vy)
            vp = 0.7 + 0.3 * math.sin(t * 2.5)
            vr = int(10 * vp)
            gs3 = pygame.Surface((vr*2+2, vr*2+2), pygame.SRCALPHA)
            pygame.draw.circle(gs3, (255, 200, 0, 180), (vr+1, vr+1), vr)
            surface.blit(gs3, (ivx - vr - 1, ivy - vr - 1))
            pygame.draw.circle(surface, (255, 240, 120), (ivx, ivy), max(2, vr//2))

        # ── Sweeping red laser ───────────────────────────────────────────────
        laser_len = int(math.hypot(GAME_WIDTH, HEIGHT) * 1.2)
        la = self.laser_angle
        lx2 = cx + int(math.cos(la) * laser_len)
        ly2 = cy + int(math.sin(la) * laser_len)
        pygame.draw.line(surface, (80, 0, 0),    (cx, cy), (lx2, ly2), 10)
        pygame.draw.line(surface, (200, 0, 0),   (cx, cy), (lx2, ly2), 5)
        pygame.draw.line(surface, (255, 60, 60), (cx, cy), (lx2, ly2), 2)
        # laser tip glow
        tip_pulse = 0.6 + 0.4 * math.sin(now / 80.0)
        tr2 = int(14 * tip_pulse)
        if tr2 > 1:
            tgs = pygame.Surface((tr2*2, tr2*2), pygame.SRCALPHA)
            pygame.draw.circle(tgs, (255, 80, 80, 200), (tr2, tr2), tr2)
            surface.blit(tgs, (lx2 - tr2, ly2 - tr2))

        # ── "All-seeing" text arc ────────────────────────────────────────────
        label = font.render("I L L U M I N A T E", True, (255, 215, 0))
        surface.blit(label, label.get_rect(center=(cx, cy + sz + 22)))


# ------------------ GRAVITY WELL SYSTEM ------------------
gravity_effects = []
_gravity_income_timer = 0
GRAVITY_INCOME_PER_SEC = 1_000_000_000_000   # 1 trillion/sec

class GravityOrb:
    """Single distortion orb orbiting the well."""
    __slots__ = ('angle','radius','speed','size','hue_off')
    def __init__(self, angle, radius, speed, size, hue_off):
        self.angle   = angle
        self.radius  = radius
        self.speed   = speed
        self.size    = size
        self.hue_off = hue_off

class GravityWellEffect:
    """Spectacular purple singularity with orbital particles and lens-warp rings."""
    __slots__ = ('bouncer','orbs','ring_angles','debris','income_timer','born','pulse')

    RING_COUNT = 5
    ORB_COUNT  = 24

    def __init__(self, bouncer):
        self.bouncer      = bouncer
        self.income_timer = pygame.time.get_ticks()
        self.born         = pygame.time.get_ticks()
        self.pulse        = random.uniform(0, 6.28)

        # Layered orbital rings — different tilt / speed / radius
        self.ring_angles = [random.uniform(0, 6.28) for _ in range(self.RING_COUNT)]

        # Orbiting glowing particles
        self.orbs = [
            GravityOrb(
                angle   = i * (6.28 / self.ORB_COUNT) + random.uniform(-0.2, 0.2),
                radius  = random.randint(28, 90),
                speed   = random.uniform(0.03, 0.09) * random.choice((-1, 1)),
                size    = random.randint(2, 7),
                hue_off = random.uniform(0, 1)
            )
            for i in range(self.ORB_COUNT)
        ]

        # Debris chunks (slow drifting shards)
        self.debris = [
            [random.uniform(0, 6.28),           # angle
             random.randint(50, 120),            # radius
             random.uniform(0.005, 0.02),        # speed
             random.randint(4, 10),              # width
             random.randint(2, 5),               # height
             random.uniform(0, 6.28)]            # tilt
            for _ in range(12)
        ]

    def _purple_hue(self, t, hue_off, alpha=255):
        """Cycle purple→magenta→violet."""
        r = int(160 + 80 * math.sin(t * 1.3 + hue_off * 6.28))
        g = int(0   + 30 * math.sin(t * 0.9 + hue_off * 6.28 + 1))
        b = int(220 + 35 * math.sin(t * 1.7 + hue_off * 6.28 + 2))
        return (max(0,min(255,r)), max(0,min(255,g)), max(0,min(255,b)))

    def update(self):
        global coins
        now = pygame.time.get_ticks()
        t   = now / 1000.0

        for k in range(self.RING_COUNT):
            self.ring_angles[k] += 0.008 * (1 + k * 0.4)

        for orb in self.orbs:
            orb.angle += orb.speed

        for d in self.debris:
            d[0] += d[2]

        if now - self.income_timer >= 1000:
            ticks = (now - self.income_timer) // 1000
            coins += GRAVITY_INCOME_PER_SEC * self.bouncer.gravity_purchases * ticks
            self.income_timer += ticks * 1000

    def draw(self, surface):
        b   = self.bouncer
        cx  = b.rect.centerx
        cy  = b.rect.centery
        now = pygame.time.get_ticks()
        t   = now / 1000.0
        pulse = 0.5 + 0.5 * math.sin(t * 2.4 + self.pulse)

        # ── 1. Deep warp rings (ellipses at different tilts) ─────────────────
        for k, ang in enumerate(self.ring_angles):
            base_r   = 55 + k * 22
            tilt     = ang * 0.6
            rx       = int(base_r)
            ry       = max(4, int(base_r * (0.18 + 0.12 * abs(math.sin(tilt)))))
            fade     = 1.0 - k * 0.12
            alpha_r  = int(90 * fade * (0.6 + 0.4 * pulse))
            ring_col = self._purple_hue(t, k * 0.2)
            surf_w   = rx * 2 + 4; surf_h = ry * 2 + 4
            gs = pygame.Surface((surf_w, surf_h), pygame.SRCALPHA)
            rc = (*ring_col, alpha_r)
            thick = max(1, 3 - k // 2)
            pygame.draw.ellipse(gs, rc, (2, 2, surf_w-4, surf_h-4), thick)
            rx_off = int(math.cos(tilt) * base_r * 0.3)
            ry_off = int(math.sin(tilt) * base_r * 0.1)
            surface.blit(gs, (cx - rx - 2 + rx_off, cy - ry - 2 + ry_off))

        # ── 2. Glow aura layers ───────────────────────────────────────────────
        for gr, ga in [(75, 70), (55, 110), (35, 160), (20, 210)]:
            gc = self._purple_hue(t, 0)
            ags = pygame.Surface((gr*2, gr*2), pygame.SRCALPHA)
            actual_a = int(ga * (0.7 + 0.3 * pulse))
            pygame.draw.circle(ags, (*gc, actual_a), (gr, gr), gr)
            surface.blit(ags, (cx - gr, cy - gr))

        # ── 3. Debris shards ─────────────────────────────────────────────────
        for d in self.debris:
            da  = d[0]; dr = d[1]; dw = d[3]; dh = d[4]; dtilt = d[5]
            dx  = cx + int(math.cos(da) * dr)
            dy  = cy + int(math.sin(da) * dr)
            srf = pygame.Surface((dw, dh), pygame.SRCALPHA)
            dc  = self._purple_hue(t, da / 6.28)
            srf.fill((*dc, 180))
            rot = pygame.transform.rotate(srf, math.degrees(dtilt + da))
            surface.blit(rot, rot.get_rect(center=(dx, dy)))

        # ── 4. Orbiting particles ─────────────────────────────────────────────
        for orb in self.orbs:
            ox  = cx + int(math.cos(orb.angle) * orb.radius)
            oy  = cy + int(math.sin(orb.angle) * orb.radius)
            oc  = self._purple_hue(t, orb.hue_off)
            # outer glow
            og  = pygame.Surface((orb.size*4, orb.size*4), pygame.SRCALPHA)
            pygame.draw.circle(og, (*oc, 90), (orb.size*2, orb.size*2), orb.size*2)
            surface.blit(og, (ox - orb.size*2, oy - orb.size*2))
            # bright core
            pygame.draw.circle(surface, oc,            (ox, oy), orb.size)
            pygame.draw.circle(surface, (255,255,255), (ox, oy), max(1, orb.size // 2))

        # ── 5. Central singularity ────────────────────────────────────────────
        # Dark core with purple rim
        core_r = int(14 + 4 * pulse)
        pygame.draw.circle(surface, (5, 0, 10),    (cx, cy), core_r + 5)
        pygame.draw.circle(surface, (5, 0, 10),    (cx, cy), core_r)
        rim_c = self._purple_hue(t, 0.5)
        pygame.draw.circle(surface, rim_c,         (cx, cy), core_r, 3)
        # Inner bright ring
        pygame.draw.circle(surface, (200, 100, 255), (cx, cy), max(3, core_r - 6), 2)
        # Tiny white hot centre
        pygame.draw.circle(surface, (240, 220, 255), (cx, cy), max(2, core_r // 3))

        # ── 6. Lens flare spikes (4 diagonal) ────────────────────────────────
        for spike_a in (0.785, 2.356, 3.927, 5.498):  # 45° intervals
            spike_len = int((45 + 20 * pulse))
            ex = cx + int(math.cos(spike_a) * spike_len)
            ey = cy + int(math.sin(spike_a) * spike_len)
            sc = self._purple_hue(t, spike_a / 6.28)
            pygame.draw.line(surface, (*sc, ), (cx, cy), (ex, ey), 2)

        # ── 7. "GRAVITY WELL" label ───────────────────────────────────────────
        lc = self._purple_hue(t, 0.7)
        lbl = font.render("GRAVITY WELL", True, lc)
        surface.blit(lbl, lbl.get_rect(center=(cx, cy + 110)))


def update_gravity_wells(dt, now):
    for eff in gravity_effects:
        eff.update()

def draw_gravity_wells(surface, now):
    for eff in gravity_effects:
        eff.draw(surface)


# ================== 3D CUBE MODE SYSTEM ==================
mode3d_active    = False
mode3d_effect    = None
_3d_income_timer = 0
MODE3D_INCOME_PER_SEC = 75_000_000_000_000

def _3d_rot(pts, rx, ry, rz):
    cx,sx = math.cos(rx),math.sin(rx)
    cy,sy = math.cos(ry),math.sin(ry)
    cz,sz = math.cos(rz),math.sin(rz)
    out = []
    for x,y,z in pts:
        y,z  = cx*y - sx*z, sx*y + cx*z
        x,z  = cy*x + sy*z, -sy*x + cy*z
        x,y  = cz*x - sz*y,  sz*x + cz*y
        out.append((x,y,z))
    return out

def _3d_proj(pts, rx, ry, rz, scx, scy, fov=900.0, z_off=800.0):
    rotated = _3d_rot(pts, rx, ry, rz)
    result  = []
    for x,y,z in rotated:
        w  = fov / (fov + z + z_off)
        result.append((scx + x*w, scy + y*w, z, w))
    return result


class GlitchLayer:
    def __init__(self):
        self.timer       = 0.0
        self.next_glitch = random.uniform(1.5, 4.0)
        self.active      = False
        self.duration    = 0.0
        self.strips      = []

    def update(self, dt):
        self.timer += dt
        if not self.active and self.timer >= self.next_glitch:
            self.active     = True
            self.duration   = random.uniform(0.06, 0.22)
            self.timer      = 0.0
            self.next_glitch = random.uniform(1.0, 5.0)
            n = random.randint(2, 7)
            self.strips = []
            for _ in range(n):
                y    = random.randint(0, HEIGHT - 20)
                h    = random.randint(4, 40)
                dx   = random.randint(-30, 30)
                tint = random.choice([
                    (255,0,0,60),(0,255,0,50),(0,100,255,60),(255,0,255,50),(0,0,0,80)
                ])
                self.strips.append((y, h, dx, tint))
        if self.active:
            self.duration -= dt
            if self.duration <= 0:
                self.active = False
                self.strips = []

    def draw(self, surface):
        if not self.active:
            return
        w = GAME_WIDTH
        for y, h, dx, tint in self.strips:
            clip = pygame.Rect(0, y, w, h)
            if clip.bottom > surface.get_height(): continue
            strip_surf = surface.subsurface(clip).copy()
            surface.blit(strip_surf, (dx, y))
            overlay = pygame.Surface((w, h), pygame.SRCALPHA)
            overlay.fill(tint)
            surface.blit(overlay, (0, y))
        if random.random() < 0.4:
            cy2 = random.randint(0, HEIGHT - 6)
            ch2 = random.randint(2, 8)
            clip2 = pygame.Rect(0, cy2, w, ch2)
            if clip2.bottom <= surface.get_height():
                try:
                    ca = surface.subsurface(clip2).copy()
                    r_shift = pygame.Surface((w, ch2), pygame.SRCALPHA)
                    r_shift.fill((255,0,0,40))
                    ca_r = ca.copy(); ca_r.blit(r_shift,(0,0))
                    surface.blit(ca_r,(4,cy2))
                    b_shift = pygame.Surface((w, ch2), pygame.SRCALPHA)
                    b_shift.fill((0,0,255,40))
                    ca_b = ca.copy(); ca_b.blit(b_shift,(0,0))
                    surface.blit(ca_b,(-4,cy2))
                except Exception:
                    pass


class Obj3DBouncer:
    def __init__(self, bouncer, half_world):
        self.b = bouncer
        self.base_hw = half_world
        self.sz = self._target_size()
        self.hw = max(40.0, self.base_hw - self.sz)
        self.x = random.uniform(-self.hw, self.hw)
        self.y = random.uniform(-self.hw, self.hw)
        self.z = random.uniform(-self.hw, self.hw)
        base2d_spd = max(1.0, math.hypot(self.b.speed_x, self.b.speed_y))
        spd      = max(85.0, min(300.0, base2d_spd * 0.45))
        ang      = random.uniform(0, math.pi*2)
        ang2     = random.uniform(0, math.pi*2)
        self.vx  = spd*math.cos(ang)*math.cos(ang2)
        self.vy  = spd*math.sin(ang)
        self.vz  = spd*math.cos(ang)*math.sin(ang2)
        self.rx  = 0.0; self.ry = 0.0; self.rz = 0.0
        self.rxv = random.uniform(-0.9, 0.9)
        self.ryv = random.uniform(-0.9, 0.9)
        self.rzv = random.uniform(-0.4, 0.4)
        self.trail = []
        self.hit_events = []

    def _target_size(self):
        min_sz = 6 if self.b.implosion_enabled else 30
        return max(min_sz, int(self.b.size * 0.38))

    def update(self, dt):
        self.sz = self._target_size()
        self.hw = max(40.0, self.base_hw - self.sz)
        self.hit_events.clear()
        if self.b.implosion_frozen:
            self.vx *= 0.82; self.vy *= 0.82; self.vz *= 0.82
            if abs(self.vx) < 1.0: self.vx = 0.0
            if abs(self.vy) < 1.0: self.vy = 0.0
            if abs(self.vz) < 1.0: self.vz = 0.0
        else:
            target = max(95.0, min(620.0, math.hypot(self.b.speed_x, self.b.speed_y) * 0.75))
            cur = math.sqrt(self.vx*self.vx + self.vy*self.vy + self.vz*self.vz)
            if cur < 1e-6:
                ang = random.uniform(0, _TWO_PI)
                ang2 = random.uniform(0, _TWO_PI)
                self.vx = math.cos(ang) * math.cos(ang2) * target
                self.vy = math.sin(ang) * target
                self.vz = math.cos(ang) * math.sin(ang2) * target
            else:
                new_mag = cur + (target - cur) * 0.35
                scale = new_mag / cur
                self.vx *= scale; self.vy *= scale; self.vz *= scale
            self.x += self.vx*dt; self.y += self.vy*dt; self.z += self.vz*dt
        self.rx += self.rxv*dt; self.ry += self.ryv*dt; self.rz += self.rzv*dt
        hw = self.hw
        if self.x < -hw:
            self.x = -hw
            self.vx = abs(self.vx)
            self.hit_events.append(((self.x, self.y, self.z), (1.0, 0.0, 0.0)))
        if self.x > hw:
            self.x = hw
            self.vx = -abs(self.vx)
            self.hit_events.append(((self.x, self.y, self.z), (-1.0, 0.0, 0.0)))
        if self.y < -hw:
            self.y = -hw
            self.vy = abs(self.vy)
            self.hit_events.append(((self.x, self.y, self.z), (0.0, 1.0, 0.0)))
        if self.y > hw:
            self.y = hw
            self.vy = -abs(self.vy)
            self.hit_events.append(((self.x, self.y, self.z), (0.0, -1.0, 0.0)))
        if self.z < -hw:
            self.z = -hw
            self.vz = abs(self.vz)
            self.hit_events.append(((self.x, self.y, self.z), (0.0, 0.0, 1.0)))
        if self.z > hw:
            self.z = hw
            self.vz = -abs(self.vz)
            self.hit_events.append(((self.x, self.y, self.z), (0.0, 0.0, -1.0)))
        self.trail.append((self.x, self.y, self.z))
        if len(self.trail) > 44: self.trail.pop(0)

    def draw(self, surface, rx, ry, rz, scx, scy, fov=900.0, z_off=800.0):
        col = self.b.color
        sz  = self.sz
        imp_eff = next((e for e in implosion_effects if e.owner is self.b), None)
        if imp_eff and imp_eff.phase != IMP_IDLE:
            cp = _3d_proj([(self.x, self.y, self.z)], rx, ry, rz, scx, scy, fov, z_off)[0]
            cpt = (int(cp[0]), int(cp[1]))
            phase = imp_eff.phase
            now = pygame.time.get_ticks()
            if goon_mode:
                core_col = (110, 255, 170)
                glow_col = (40, 140, 90)
            else:
                core_col = (210, 150, 255)
                glow_col = (90, 40, 150)

            if phase in (IMP_SHRINK, IMP_HOLD):
                if phase == IMP_SHRINK:
                    prog = min((now - imp_eff.phase_start) / max(1, IMPLOSION_SHRINK_MS), 1.0)
                else:
                    prog = 1.0
                beam_len = max(10, int((sz * 2.2 + 26) * (1.15 - 0.35 * prog)))
                beam_n = 10
                for bi in range(beam_n):
                    ang = now / 220.0 + bi * (_TWO_PI / beam_n)
                    ex = cpt[0] + int(math.cos(ang) * beam_len)
                    ey = cpt[1] + int(math.sin(ang) * beam_len)
                    pygame.draw.line(surface, glow_col, (ex, ey), cpt, 4)
                    pygame.draw.line(surface, core_col, (ex, ey), cpt, 2)
                rr = max(6, int((22 - 12 * prog) * max(0.6, cp[3] * 2.2)))
                pygame.draw.circle(surface, glow_col, cpt, rr + 7, 2)
                pygame.draw.circle(surface, core_col, cpt, rr + 2, 2)
                pygame.draw.circle(surface, (0, 0, 0), cpt, rr)
                pygame.draw.circle(surface, (255, 255, 255), cpt, max(2, rr // 3))
            elif phase == IMP_EXPLODE:
                prog = min((now - imp_eff.phase_start) / max(1, IMPLOSION_EXPLODE_MS), 1.0)
                rr = max(10, int((250 * prog + 10) * max(0.55, cp[3] * 2.1)))
                thick = max(1, int(10 * (1.0 - prog)))
                pygame.draw.circle(surface, (255, 255, 255), cpt, rr, thick)
                pygame.draw.circle(surface, core_col, cpt, max(4, int(rr * 0.6)), max(1, thick - 1))
            return

        CUBE_FACES = [(0,1,2,3),(4,5,6,7),(0,1,5,4),(2,3,7,6),(0,3,7,4),(1,2,6,5)]
        CUBE_EDGES = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
        FACE_NORMS = [(0,0,-1),(0,0,1),(0,-1,0),(0,1,0),(-1,0,0),(1,0,0)]

        local = [(dx*sz, dy*sz, dz*sz)
                 for dx,dy,dz in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
                                  (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
        spun_local = _3d_rot(local, self.rx, self.ry, self.rz)
        corners = [(self.x + px, self.y + py, self.z + pz) for px, py, pz in spun_local]
        proj = _3d_proj(corners, rx, ry, rz, scx, scy, fov, z_off)
        sp   = [(int(p[0]),int(p[1])) for p in proj]
        deps = [p[2] for p in proj]

        # Trail — draw before cube so cube appears on top
        if self.b.trail_enabled and len(self.trail) > 1:
            tr_proj = _3d_proj(self.trail, rx, ry, rz, scx, scy, fov, z_off)
            for ti in range(1, len(tr_proj)):
                fade = ti/len(tr_proj)
                ci = (ti * 3 + (pygame.time.get_ticks() // 35)) % len(TRAIL_COLORS)
                rb = TRAIL_COLORS[ci]
                tc = (int(rb[0] * fade), int(rb[1] * fade), int(rb[2] * fade))
                p0   = (int(tr_proj[ti-1][0]),int(tr_proj[ti-1][1]))
                p1   = (int(tr_proj[ti][0]),  int(tr_proj[ti][1]))
                glow = (int(tc[0] * 0.35), int(tc[1] * 0.35), int(tc[2] * 0.35))
                w = max(1, int(9 * fade))
                pygame.draw.line(surface, glow, p0, p1, w + 5)
                pygame.draw.line(surface, tc, p0, p1, w)

        # Faces — depth sorted, drawn directly (no per-face Surface alloc)
        face_d = [(sum(deps[k] for k in f)/4, fi, f) for fi,f in enumerate(CUBE_FACES)]
        face_d.sort(key=lambda x: x[0])
        light = (0.3, 0.6, 0.8)
        for avg_z, fi, face in face_d:
            nx,ny,nz = FACE_NORMS[fi]
            nr1 = _3d_rot([(nx, ny, nz)], self.rx, self.ry, self.rz)[0]
            nr  = _3d_rot([nr1], rx, ry, rz)[0]
            dot = nr[0]*light[0]+nr[1]*light[1]+nr[2]*light[2]
            br  = max(0.25, min(1.0, 0.4+0.6*dot))
            fc  = (int(col[0]*br), int(col[1]*br), int(col[2]*br))
            pts4 = [sp[k] for k in face]
            pygame.draw.polygon(surface, fc, pts4)

        # Edges
        for e0,e1 in CUBE_EDGES:
            pygame.draw.line(surface, (220,235,255), sp[e0], sp[e1], 1)

        # Bright highlight on nearest corner
        front_k = max(range(8), key=lambda k: deps[k])
        pygame.draw.circle(surface, (255,255,255), sp[front_k], 3)

        # Centre glow dot
        cp = _3d_proj([(self.x,self.y,self.z)], rx, ry, rz, scx, scy, fov, z_off)[0]
        cpt = (int(cp[0]), int(cp[1]))
        core_r = max(4, int(sz * 0.48))
        pulse = 0.8 + 0.2 * math.sin(pygame.time.get_ticks() / 120.0)
        core_col = (min(255, int(col[0] * pulse)),
                    min(255, int(col[1] * pulse)),
                    min(255, int(col[2] * pulse)))
        pygame.draw.circle(surface, core_col, cpt, core_r)
        pygame.draw.circle(surface, (255,255,255), cpt, max(2, int(sz*0.18)))

        if self.b.laser_enabled:
            pygame.draw.circle(surface, (255, 80, 80), cpt, core_r + 4, 2)
        if self.b.lightning_enabled:
            pygame.draw.circle(surface, (120, 180, 255), cpt, core_r + 8, 1)
        if self.b.implosion_enabled:
            pygame.draw.circle(surface, (170, 90, 255), cpt, core_r + 12, 1)


class Obj3DPrism:
    """Centered illuminati pyramid with an eye on the front face."""
    def __init__(self, x, y, z, power=1):
        self.x = x; self.y = y; self.z = z
        self.power = max(1, int(power))
        self.spin  = 0.0
        self.spinv = 0.38
        self.pulse = random.uniform(0, 6.28)
        self.laser_angle = random.uniform(0, 6.28)

    def update(self, dt):
        self.spin += self.spinv * dt
        self.laser_angle += 1.15 * dt

    def draw(self, surface, rx, ry, rz, scx, scy, t, fov=900.0, z_off=800.0):
        p = 0.5 + 0.5 * math.sin(t * 2.1 + self.pulse)
        bob = math.sin(t * 1.7 + self.pulse) * (6 + min(4, self.power))
        base_r = 84 + min(4, self.power - 1) * 8
        apex_h = 148 + min(4, self.power - 1) * 12
        y0 = self.y + bob

        # Square-base pyramid so it reads clearly as a 3D illuminati piece.
        ao = [self.spin + math.pi * 0.25 + k * math.pi * 0.5 for k in range(4)]
        base_y = y0 + apex_h * 0.38
        base = [(self.x + base_r * math.cos(a), base_y, self.z + base_r * math.sin(a)) for a in ao]
        apex = (self.x, y0 - apex_h * 0.72, self.z)
        verts = base + [apex]  # 0..3 base, 4 apex

        FACES = [(0,1,4), (1,2,4), (2,3,4), (3,0,4), (3,2,1,0)]
        EDGES = [(0,1),(1,2),(2,3),(3,0),(0,4),(1,4),(2,4),(3,4)]

        proj = _3d_proj(verts, rx, ry, rz, scx, scy, fov, z_off)
        sp = [(int(q[0]), int(q[1])) for q in proj]
        deps = [q[2] for q in proj]

        face_d = []
        for fi, face in enumerate(FACES):
            avg_z = sum(deps[k] for k in face) / len(face)
            fade = max(0.22, min(1.0, 0.48 + avg_z / 900.0))
            face_d.append((avg_z, fi, face, fade))
        face_d.sort(key=lambda x: x[0])

        for _, fi, face, fade in face_d:
            pts = [sp[k] for k in face]
            if fi == 4:  # base
                fc = (int(45 * fade), int(32 * fade), int(14 * fade))
            else:
                g1 = int((150 + 75 * p) * fade)
                g2 = int((115 + 60 * p) * fade)
                g3 = int((24 + 26 * p) * fade)
                fc = (max(30, g1), max(20, g2), max(6, g3))
            pygame.draw.polygon(surface, fc, pts)

        for e0, e1 in EDGES:
            pygame.draw.line(surface, (255, 225, 110), sp[e0], sp[e1], 2)
            pygame.draw.line(surface, (130, 90, 20), sp[e0], sp[e1], 1)

        # Put the eye on the face currently nearest to the camera.
        side_faces = FACES[:4]
        front_face = side_faces[max(range(4), key=lambda i: sum(deps[k] for k in side_faces[i]))]
        ew = (
            sum(verts[k][0] for k in front_face) / 3.0,
            sum(verts[k][1] for k in front_face) / 3.0,
            sum(verts[k][2] for k in front_face) / 3.0
        )
        ep = _3d_proj([ew], rx, ry, rz, scx, scy, fov, z_off)[0]
        eye_pt = (int(ep[0]), int(ep[1]))
        er = max(6, int((10 + 4 * p) * max(0.6, ep[3] * 1.8)))

        eg = max(8, int(er * 2.2))
        glow = pygame.Surface((eg * 2, eg * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow, (255, 200, 50, 85), (eg, eg), eg)
        surface.blit(glow, (eye_pt[0] - eg, eye_pt[1] - eg))

        pygame.draw.circle(surface, (255, 220, 55), eye_pt, er)
        pygame.draw.circle(surface, (255, 130, 20), eye_pt, max(3, er // 2))
        pygame.draw.circle(surface, (0, 0, 0), eye_pt, max(2, er // 4))
        pygame.draw.circle(surface, (255, 255, 255),
                           (eye_pt[0] - max(1, er // 4), eye_pt[1] - max(1, er // 4)),
                           max(1, er // 6))
        for vk in front_face:
            pygame.draw.line(surface, (175, 125, 30), eye_pt, sp[vk], 1)

        # Bring back the illuminate laser for 3D mode.
        beam_len = 220 + int(40 * p)
        lx = ew[0] + math.cos(self.laser_angle) * beam_len
        lz = ew[2] + math.sin(self.laser_angle) * beam_len
        ly = ew[1] + math.sin(t * 1.5 + self.pulse) * 16
        lp = _3d_proj([(lx, ly, lz)], rx, ry, rz, scx, scy, fov, z_off)[0]
        lpt = (int(lp[0]), int(lp[1]))
        pygame.draw.line(surface, (80, 0, 0), eye_pt, lpt, 7)
        pygame.draw.line(surface, (210, 0, 0), eye_pt, lpt, 4)
        pygame.draw.line(surface, (255, 80, 80), eye_pt, lpt, 2)
        tr = max(3, int(8 * (0.8 + 0.2 * p)))
        tip = pygame.Surface((tr * 2, tr * 2), pygame.SRCALPHA)
        pygame.draw.circle(tip, (255, 80, 80, 180), (tr, tr), tr)
        surface.blit(tip, (lpt[0] - tr, lpt[1] - tr))


class Obj3DFactory:
    def __init__(self, wx, half_world, wz=0.0):
        self.x = wx; self.y = half_world*0.75; self.z = wz
        self.pulse = random.uniform(0,6.28)
        self.gear = random.uniform(0, 6.28)
        self.smoke = [self._spawn_smoke() for _ in range(8)]

    def _spawn_smoke(self):
        return [
            self.x + random.uniform(-24, 24),
            self.y - 96 - random.uniform(0, 26),
            self.z + random.uniform(-10, 10),
            random.uniform(18, 30),   # rise speed
            random.uniform(7, 14),    # base radius
            random.uniform(0.6, 1.0), # life
            random.uniform(-4, 4),
            random.uniform(-4, 4),
        ]

    def update(self, dt):
        self.gear += 1.5 * dt
        for puff in self.smoke:
            puff[0] += puff[6] * dt
            puff[2] += puff[7] * dt
            puff[1] -= puff[3] * dt
            puff[5] -= 0.24 * dt
            if puff[5] <= 0.0 or puff[1] < self.y - 180:
                puff[:] = self._spawn_smoke()

    def draw(self, surface, rx, ry, rz, scx, scy, t, fov=900.0, z_off=800.0):
        p = 0.6 + 0.4 * math.sin(t * 1.8 + self.pulse)

        def draw_box(cx, cy, cz, hw, hh, hd, face_cols, edge_col):
            corners = [
                (cx-hw,cy-hh,cz-hd),(cx+hw,cy-hh,cz-hd),(cx+hw,cy+hh,cz-hd),(cx-hw,cy+hh,cz-hd),
                (cx-hw,cy-hh,cz+hd),(cx+hw,cy-hh,cz+hd),(cx+hw,cy+hh,cz+hd),(cx-hw,cy+hh,cz+hd),
            ]
            faces = [(0,1,2,3),(4,5,6,7),(0,1,5,4),(2,3,7,6),(0,3,7,4),(1,2,6,5)]
            edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
            proj = _3d_proj(corners, rx, ry, rz, scx, scy, fov, z_off)
            sp = [(int(q[0]), int(q[1])) for q in proj]
            deps = [q[2] for q in proj]
            face_d = [(sum(deps[k] for k in f) / 4.0, fi, f) for fi, f in enumerate(faces)]
            face_d.sort(key=lambda x: x[0])
            for _, fi, face in face_d:
                pygame.draw.polygon(surface, face_cols[fi], [sp[k] for k in face])
            for e0, e1 in edges:
                pygame.draw.line(surface, edge_col, sp[e0], sp[e1], 1)
            return sp

        body_cols = [(52, 62, 72), (80, 92, 108), (65, 76, 90),
                     (40, 48, 58), (58, 68, 80), (72, 84, 98)]
        draw_box(self.x, self.y, self.z, 42, 50, 30, body_cols, (130, 150, 170))

        roof_cols = [(34, 42, 52), (54, 64, 76), (44, 52, 64),
                     (28, 34, 44), (46, 56, 68), (58, 68, 82)]
        draw_box(self.x, self.y - 58, self.z, 48, 8, 34, roof_cols, (160, 175, 195))

        # Three chimneys on the roof.
        for i, ox in enumerate((-24, 0, 24)):
            h = 18 + i * 8
            ch_cols = [(40, 48, 58), (62, 72, 84), (48, 58, 70),
                       (34, 40, 50), (44, 52, 62), (56, 66, 78)]
            draw_box(self.x + ox, self.y - 76 - h * 0.5, self.z - 6, 6, h * 0.5, 6,
                     ch_cols, (155, 170, 185))

        # Front glowing windows.
        for row in range(2):
            wy = self.y - 18 + row * 22
            for ox in (-20, 0, 20):
                wp = _3d_proj([(self.x + ox, wy, self.z - 31)], rx, ry, rz, scx, scy, fov, z_off)[0]
                scale = max(0.45, wp[3] * 2.0)
                ww = max(4, int(8 * scale))
                wh = max(3, int(6 * scale))
                flick = 0.75 + 0.25 * math.sin(t * 7.3 + ox * 0.2 + row)
                wc = (int(255 * flick), int(160 * flick), 0)
                wr = pygame.Rect(int(wp[0] - ww // 2), int(wp[1] - wh // 2), ww, wh)
                pygame.draw.rect(surface, (15, 15, 15), wr)
                pygame.draw.rect(surface, wc, wr.inflate(-2, -2))
                pygame.draw.rect(surface, (200, 200, 200), wr, 1)

        # Front gear detail.
        gp = _3d_proj([(self.x, self.y + 24, self.z - 31)], rx, ry, rz, scx, scy, fov, z_off)[0]
        gr = max(5, int(11 * max(0.55, gp[3] * 2.1)))
        gear_pts = []
        for k in range(16):
            a = self.gear + k * (math.pi / 8)
            rad = gr + 3 if k % 2 == 0 else gr - 2
            gear_pts.append((int(gp[0] + math.cos(a) * rad), int(gp[1] + math.sin(a) * rad)))
        pygame.draw.polygon(surface, (170, 128, 32), gear_pts)
        pygame.draw.circle(surface, (20, 20, 20), (int(gp[0]), int(gp[1])), max(2, gr - 4))
        pygame.draw.circle(surface, (220, 180, 60), (int(gp[0]), int(gp[1])), max(1, gr // 4))

        # Smokestack puffs.
        for sx, sy, sz3, _, rad, life, _, _ in self.smoke:
            sp = _3d_proj([(sx, sy, sz3)], rx, ry, rz, scx, scy, fov, z_off)[0]
            sr = max(2, int(rad * max(0.35, sp[3] * 2.0)))
            sa = max(0, int(105 * life))
            sg = pygame.Surface((sr * 2, sr * 2), pygame.SRCALPHA)
            gc = int(120 + 70 * life)
            pygame.draw.circle(sg, (gc, gc, gc, sa), (sr, sr), sr)
            surface.blit(sg, (int(sp[0]) - sr, int(sp[1]) - sr))


class Obj3DDonutRing:
    def __init__(self, owners, half_world):
        self.owners = owners
        self.half = half_world
        self.spin = random.uniform(0, _TWO_PI)
        self.wobble = random.uniform(0, _TWO_PI)
        self.ring_goons = []
        self.hit_glows = []

    def _target_count(self):
        cnt = sum(max(0, b.donut_ring_count) for b in self.owners)
        return max(0, min(DONUT_GOON_MAX, cnt))

    def _torus_dims(self):
        # Keep this uniform so the donut is evenly sized and always around the cube.
        tube = max(56.0, self.half * 0.16)
        major = self.half * math.sqrt(2.0) + tube + 26.0
        return major, tube

    def _spawn_ring_goon(self):
        major, tube = self._torus_dims()
        inner = tube * 0.82
        u = random.uniform(0.0, _TWO_PI)
        v = random.uniform(0.0, _TWO_PI)
        # Uniform-ish fill inside tube cross-section.
        rr = math.sqrt(random.random()) * inner * 0.92
        x = (major + rr * math.cos(v)) * math.cos(u)
        y = rr * math.sin(v)
        z = (major + rr * math.cos(v)) * math.sin(u)
        speed = random.uniform(430.0, 610.0)
        # Strong forward tangent component makes donut-goons feel fast.
        tx, ty, tz = -math.sin(u), 0.0, math.cos(u)
        a = random.uniform(0.0, _TWO_PI)
        b = random.uniform(-0.6, 0.6)
        rx = math.cos(a) * math.cos(b)
        ry = math.sin(b)
        rz = math.sin(a) * math.cos(b)
        vx = tx * speed * 0.78 + rx * speed * 0.46
        vy = ty * speed * 0.78 + ry * speed * 0.46
        vz = tz * speed * 0.78 + rz * speed * 0.46
        vm = math.sqrt(max(1e-9, vx * vx + vy * vy + vz * vz))
        return {
            "x": x, "y": y, "z": z,
            "vx": vx / vm * speed,
            "vy": vy / vm * speed,
            "vz": vz / vm * speed,
            "trail": [(x, y, z)],
            "hue": random.randint(0, max(1, len(TRAIL_COLORS) - 1))
        }

    def _sync_ring_goons(self):
        target = self._target_count()
        while len(self.ring_goons) < target:
            self.ring_goons.append(self._spawn_ring_goon())
        if len(self.ring_goons) > target:
            del self.ring_goons[target:]

    def _collide_torus(self, g, major, inner_tube):
        x, y, z = g["x"], g["y"], g["z"]
        rho = math.hypot(x, z)
        if rho < 1e-6:
            x = major
            z = 0.0
            rho = major
        rd = rho - major
        dist = math.sqrt(rd * rd + y * y)
        if dist <= inner_tube:
            g["x"], g["y"], g["z"] = x, y, z
            return False

        inv_rho = 1.0 / max(rho, 1e-6)
        inv_dist = 1.0 / max(dist, 1e-6)
        nx = (x * inv_rho) * rd * inv_dist
        ny = y * inv_dist
        nz = (z * inv_rho) * rd * inv_dist

        # Push back just inside the donut tube boundary.
        excess = dist - inner_tube
        x -= nx * (excess + 0.25)
        y -= ny * (excess + 0.25)
        z -= nz * (excess + 0.25)
        g["x"], g["y"], g["z"] = x, y, z

        dot = g["vx"] * nx + g["vy"] * ny + g["vz"] * nz
        g["vx"] -= 2.0 * dot * nx
        g["vy"] -= 2.0 * dot * ny
        g["vz"] -= 2.0 * dot * nz
        return True

    def update(self, dt):
        self.spin += 0.58 * dt
        self.wobble += 1.05 * dt
        self._sync_ring_goons()

        major, tube = self._torus_dims()
        inner_tube = tube * 0.82
        target_speed = 470.0 + min(280.0, self._target_count() * 14.0)
        for g in self.ring_goons:
            vx, vy, vz = g["vx"], g["vy"], g["vz"]
            spd = math.sqrt(vx * vx + vy * vy + vz * vz)
            if spd < 1e-6:
                a = random.uniform(0.0, _TWO_PI)
                b = random.uniform(0.0, _TWO_PI)
                g["vx"] = math.cos(a) * math.cos(b) * target_speed
                g["vy"] = math.sin(a) * target_speed
                g["vz"] = math.cos(a) * math.sin(b) * target_speed
            else:
                s = (spd + (target_speed - spd) * 0.24) / spd
                g["vx"] *= s
                g["vy"] *= s
                g["vz"] *= s

            g["x"] += g["vx"] * dt
            g["y"] += g["vy"] * dt
            g["z"] += g["vz"] * dt

            bounced = self._collide_torus(g, major, inner_tube)
            # Second pass prevents tunneling with larger dt spikes.
            if self._collide_torus(g, major, inner_tube):
                bounced = True

            g["trail"].append((g["x"], g["y"], g["z"]))
            if len(g["trail"]) > 12:
                g["trail"].pop(0)

            if bounced:
                self.hit_glows.append({
                    "x": g["x"], "y": g["y"], "z": g["z"],
                    "life": 0.35, "r": 6.0
                })

        i = 0
        while i < len(self.hit_glows):
            hg = self.hit_glows[i]
            hg["life"] -= dt
            hg["r"] += dt * 90.0
            if hg["life"] <= 0.0:
                self.hit_glows[i] = self.hit_glows[-1]
                self.hit_glows.pop()
            else:
                i += 1

    def draw(self, surface, rx, ry, rz, scx, scy, t, fov=900.0, z_off=800.0, layer="all"):
        cnt = self._target_count()
        if cnt <= 0:
            return

        # Ring wraps around the whole 3D cube.
        cx, cy, cz = 0.0, 0.0, 0.0
        major, tube = self._torus_dims()
        pulse = 0.65 + 0.35 * math.sin(self.wobble + t * 2.1)

        if goon_mode:
            c_ring = (55, 230, 165)
            c_core = (180, 255, 230)
        else:
            c_ring = (210, 125, 255)
            c_core = (245, 220, 255)

        # True torus mesh (uniform tube width all around).
        major_n = 22
        minor_n = 12

        verts3 = []
        for iu in range(major_n):
            u = self.spin + iu * (_TWO_PI / major_n)
            cu = math.cos(u)
            su = math.sin(u)
            for iv in range(minor_n):
                v = iv * (_TWO_PI / minor_n)
                cv = math.cos(v)
                sv = math.sin(v)
                rr = major + tube * cv
                x = rr * cu
                y = tube * sv
                z = rr * su
                verts3.append((cx + x, cy + y, cz + z))

        pr = _3d_proj(verts3, rx, ry, rz, scx, scy, fov, z_off)
        sp = [(int(q[0]), int(q[1])) for q in pr]
        dep = [q[2] for q in pr]

        def vidx(iu, iv):
            return (iu % major_n) * minor_n + (iv % minor_n)

        faces = []
        for iu in range(major_n):
            for iv in range(minor_n):
                a = vidx(iu, iv)
                b = vidx(iu + 1, iv)
                c = vidx(iu + 1, iv + 1)
                d = vidx(iu, iv + 1)
                avg = (dep[a] + dep[b] + dep[c] + dep[d]) * 0.25
                if layer == "back" and avg < 0.0:
                    continue
                if layer == "front" and avg >= 0.0:
                    continue
                shade = 0.52 + 0.42 * (0.5 + 0.5 * math.sin((iv / minor_n) * _TWO_PI + self.wobble))
                rc = (
                    min(255, int(c_ring[0] * shade * pulse)),
                    min(255, int(c_ring[1] * shade * pulse)),
                    min(255, int(c_ring[2] * shade * pulse)),
                )
                faces.append((avg, (a, b, c, d), rc))
        faces.sort(key=lambda x: x[0])
        for _, face, rc in faces:
            pts = [sp[k] for k in face]
            pygame.draw.polygon(surface, rc, pts)
            pygame.draw.polygon(surface, (int(rc[0] * 0.55), int(rc[1] * 0.55), int(rc[2] * 0.55)), pts, 1)

        rc = (int(c_ring[0] * pulse), int(c_ring[1] * pulse), int(c_ring[2] * pulse))
        # Fast ring-goons stay confined inside the donut volume.
        if self.ring_goons:
            gproj = _3d_proj([(g["x"], g["y"], g["z"]) for g in self.ring_goons],
                             rx, ry, rz, scx, scy, fov, z_off)
            order = sorted(range(len(self.ring_goons)), key=lambda i: gproj[i][2])
            for idx in order:
                g = self.ring_goons[idx]
                gp = gproj[idx]
                if layer == "back" and gp[2] < 0.0:
                    continue
                if layer == "front" and gp[2] >= 0.0:
                    continue
                s = max(4, int(12 * max(0.45, gp[3] * 2.0)))
                px, py = int(gp[0]), int(gp[1])
                # Rainbow trail in 3D.
                if len(g["trail"]) > 1:
                    tp = _3d_proj(g["trail"], rx, ry, rz, scx, scy, fov, z_off)
                    for ti in range(1, len(tp)):
                        fade = ti / len(tp)
                        ci = (g["hue"] + ti * 3 + int(t * 20)) % len(TRAIL_COLORS)
                        col = TRAIL_COLORS[ci]
                        tc = (int(col[0] * fade), int(col[1] * fade), int(col[2] * fade))
                        p0 = (int(tp[ti - 1][0]), int(tp[ti - 1][1]))
                        p1 = (int(tp[ti][0]), int(tp[ti][1]))
                        pygame.draw.line(surface, (int(tc[0] * 0.3), int(tc[1] * 0.3), int(tc[2] * 0.3)), p0, p1, max(1, int(5 * fade)))
                        pygame.draw.line(surface, tc, p0, p1, max(1, int(3 * fade)))
                glow_r = s + 6
                glow = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
                base = TRAIL_COLORS[g["hue"] % len(TRAIL_COLORS)]
                pygame.draw.circle(glow, (base[0], base[1], base[2], 120), (glow_r, glow_r), glow_r)
                surface.blit(glow, (px - glow_r, py - glow_r))
                pygame.draw.circle(surface, rc, (px, py), s)
                pygame.draw.circle(surface, c_core, (px, py), max(2, s - 3))
                pygame.draw.circle(surface, (255, 255, 255), (px, py), max(1, s // 3))

        # Wall-hit pulses for ring-goons.
        for hg in self.hit_glows:
            pp = _3d_proj([(hg["x"], hg["y"], hg["z"])], rx, ry, rz, scx, scy, fov, z_off)[0]
            if layer == "back" and pp[2] < 0.0:
                continue
            if layer == "front" and pp[2] >= 0.0:
                continue
            fade = max(0.0, min(1.0, hg["life"] / 0.35))
            rr = max(2, int(hg["r"] * max(0.5, pp[3] * 2.0)))
            c1 = (int(rc[0] * fade), int(rc[1] * fade), int(rc[2] * fade))
            pygame.draw.circle(surface, c1, (int(pp[0]), int(pp[1])), rr, max(1, int(3 * fade)))

        # Center glow pulse.
        if layer != "back":
            cp = _3d_proj([(cx, cy, cz)], rx, ry, rz, scx, scy, fov, z_off)[0]
            cr = max(8, int((18 + cnt * 0.9) * max(0.45, cp[3] * 2.0)))
            glow = pygame.Surface((cr * 4, cr * 4), pygame.SRCALPHA)
            pygame.draw.circle(glow, (*c_ring, 120), (cr * 2, cr * 2), cr * 2)
            surface.blit(glow, (int(cp[0]) - cr * 2, int(cp[1]) - cr * 2))
            pygame.draw.circle(surface, c_core, (int(cp[0]), int(cp[1])), max(2, cr // 2))


class Obj3DGoonGod:
    """
    A fully 3D Greek-god Zeus - Corinthian helmet, muscular torso in bronze armour,
    toga drape, beard, face with nose/brow ridges, and a crackling lightning bolt.
    He is anchored in CAMERA space on the LEFT side so he is always visible.
    """

    def __init__(self, power, half_world):
        self.power = max(1, int(power))
        self.half = half_world
        self.t = 0.0
        self.hand_t = 0.0
        self.cam_rx = 0.0
        self.cam_ry = 0.0
        self.cam_rz = 0.0
        self.spawn_acc = 0.0
        self.burst_timer = 0.35
        self.spray = []
        self.cube_marks = []
        # lightning bolt verts (local Zeus space, regenerated each frame)
        self._bolt_pts = []
        self._bolt_timer = 0.0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _camera_to_world(self, cx, cy, cz, rx, ry, rz):
        """Invert camera rotation: camera-space -> world-space."""
        cxx, sxx = math.cos(rx), math.sin(rx)
        cyy, syy = math.cos(ry), math.sin(ry)
        czz, szz = math.cos(rz), math.sin(rz)
        x0, y0 = czz * cx + szz * cy, -szz * cx + czz * cy
        x0, z0 = cyy * x0 - syy * cz, syy * x0 + cyy * cz
        y0, z0 = cxx * y0 + sxx * z0, -sxx * y0 + cxx * z0
        return (x0, y0, z0)

    def _root_world(self, rx, ry, rz):
        """
        Zeus is always pinned to the left side of the screen in camera space,
        regardless of cube rotation. We use a fixed camera-space offset and
        un-rotate it to get the world position.
        """
        s = self._scale()
        # Camera-space: left of cube, slightly above centre, and behind the cube
        cam_x = -self.half * 1.70
        cam_y = self.half * 0.12
        cam_z = -self.half * 0.45
        return self._camera_to_world(cam_x, cam_y, cam_z, rx, ry, rz)

    def _scale(self):
        return self.half * (1.30 + min(0.75, self.power * 0.040))

    def _hand_world(self, rx, ry, rz):
        """Hand positioned at waist in camera space."""
        s = self.half * 0.28
        rx0, ry0, rz0 = self._root_world(rx, ry, rz)
        # In camera space the waist is slightly below and forward of root
        cx, cy, cz = (
            -self.half * 1.70,
            self.half * 0.12 + s * (0.78 + 0.18 * math.sin(self.hand_t)),
            -self.half * 0.45 + s * 0.10,
        )
        wx, wy, wz = self._camera_to_world(cx, cy, cz, rx, ry, rz)
        return (wx, wy, wz)

    def _random_unit(self):
        uy = random.uniform(-1.0, 1.0)
        a = random.uniform(0.0, _TWO_PI)
        rr = math.sqrt(max(0.0, 1.0 - uy * uy))
        return (math.cos(a) * rr, uy, math.sin(a) * rr)

    # ------------------------------------------------------------------
    # Spray / mark helpers (unchanged logic, just uses new _hand_world)
    # ------------------------------------------------------------------

    def _spawn_spray(self, hx, hy, hz, mode="mix"):
        hw = self.half
        if mode == "mix":
            r = random.random()
            mode = "cube" if r < 0.45 else ("burst" if r < 0.78 else "wide")

        if mode == "cube":
            face = random.randint(0, 5)
            if face == 0:
                tx, ty, tz = (hw, random.uniform(-hw, hw), random.uniform(-hw, hw))
            elif face == 1:
                tx, ty, tz = (-hw, random.uniform(-hw, hw), random.uniform(-hw, hw))
            elif face == 2:
                tx, ty, tz = (random.uniform(-hw, hw), hw, random.uniform(-hw, hw))
            elif face == 3:
                tx, ty, tz = (random.uniform(-hw, hw), -hw, random.uniform(-hw, hw))
            elif face == 4:
                tx, ty, tz = (random.uniform(-hw, hw), random.uniform(-hw, hw), hw)
            else:
                tx, ty, tz = (random.uniform(-hw, hw), random.uniform(-hw, hw), -hw)
            dx, dy, dz = tx - hx, ty - hy, tz - hz
            dm = math.sqrt(max(1e-9, dx * dx + dy * dy + dz * dz))
            nx, ny, nz = dx / dm, dy / dm, dz / dm
            speed = random.uniform(520.0, 860.0)
        elif mode == "burst":
            nx, ny, nz = self._random_unit()
            ny *= 0.85
            nm = math.sqrt(max(1e-9, nx * nx + ny * ny + nz * nz))
            nx, ny, nz = nx / nm, ny / nm, nz / nm
            speed = random.uniform(420.0, 920.0)
        else:
            tx = hx + random.uniform(-hw * 2.2, hw * 2.2)
            ty = hy + random.uniform(-hw * 1.9, hw * 1.9)
            tz = hz + random.uniform(-hw * 2.5, hw * 1.2)
            dx, dy, dz = tx - hx, ty - hy, tz - hz
            dm = math.sqrt(max(1e-9, dx * dx + dy * dy + dz * dz))
            nx, ny, nz = dx / dm, dy / dm, dz / dm
            speed = random.uniform(360.0, 760.0)

        spread = 0.30 if mode != "cube" else 0.18
        nx += random.uniform(-spread, spread)
        ny += random.uniform(-spread, spread)
        nz += random.uniform(-spread, spread)
        nm = math.sqrt(max(1e-9, nx * nx + ny * ny + nz * nz))
        nx, ny, nz = nx / nm, ny / nm, nz / nm
        self.spray.append({
            "x": hx, "y": hy, "z": hz,
            "vx": nx * speed, "vy": ny * speed, "vz": nz * speed,
            "life": random.uniform(0.70, 1.35),
            "trail": [(hx, hy, hz)],
            "size": random.uniform(2.0, 5.2),
        })

    def _mark_cube_hit(self, x, y, z):
        hw = self.half
        ax, ay, az = abs(x), abs(y), abs(z)
        if ax >= ay and ax >= az:
            x = hw if x >= 0 else -hw
        elif ay >= ax and ay >= az:
            y = hw if y >= 0 else -hw
        else:
            z = hw if z >= 0 else -hw
        self.cube_marks.append({
            "x": x, "y": y, "z": z,
            "life": random.uniform(0.95, 1.35),
            "r": random.uniform(5.0, 11.0),
            "grow": random.uniform(18.0, 34.0),
        })
        if len(self.cube_marks) > 300:
            del self.cube_marks[:-300]

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, dt, cam_rx=None, cam_ry=None, cam_rz=None):
        if cam_rx is not None:
            self.cam_rx, self.cam_ry, self.cam_rz = cam_rx, cam_ry, cam_rz
        self.t += dt
        self.hand_t += dt * (1.55 + min(1.30, self.power * 0.05))

        # Regenerate jagged lightning bolt every 0.18 s
        self._bolt_timer -= dt
        if self._bolt_timer <= 0.0:
            self._bolt_timer = 0.18
            n = 10
            self._bolt_pts = []
            y0 = 0.0
            for k in range(n + 1):
                t_frac = k / n
                self._bolt_pts.append((
                    random.uniform(-6, 6),
                    y0 - t_frac * 90,
                    random.uniform(-4, 4),
                ))

        hx, hy, hz = self._hand_world(self.cam_rx, self.cam_ry, self.cam_rz)

        spray_rate = min(130.0, 46.0 + self.power * 5.2)
        self.spawn_acc += spray_rate * dt
        while self.spawn_acc >= 1.0 and len(self.spray) < 460:
            self._spawn_spray(hx, hy, hz, "mix")
            self.spawn_acc -= 1.0

        self.burst_timer -= dt
        if self.burst_timer <= 0.0:
            burst_count = min(96, 26 + self.power * 3)
            for _ in range(burst_count):
                if len(self.spray) >= 460:
                    break
                self._spawn_spray(hx, hy, hz, "burst")
            self.burst_timer = random.uniform(0.22, 0.52)

        hw = self.half
        i = 0
        while i < len(self.spray):
            p = self.spray[i]
            drag = max(0.0, 1.0 - dt * 0.20)
            p["vx"] *= drag
            p["vy"] *= drag
            p["vz"] *= drag
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["z"] += p["vz"] * dt
            p["vy"] += 90.0 * dt
            p["life"] -= dt * 0.88
            p["trail"].append((p["x"], p["y"], p["z"]))
            if len(p["trail"]) > 9:
                p["trail"].pop(0)
            inside = abs(p["x"]) <= hw and abs(p["y"]) <= hw and abs(p["z"]) <= hw
            if inside:
                self._mark_cube_hit(p["x"], p["y"], p["z"])
                self.spray[i] = self.spray[-1]
                self.spray.pop()
                continue
            if (p["life"] <= 0 or abs(p["x"]) > hw * 2.7 or
                abs(p["y"]) > hw * 2.7 or abs(p["z"]) > hw * 3.2):
                self.spray[i] = self.spray[-1]
                self.spray.pop()
                continue
            i += 1

        j = 0
        while j < len(self.cube_marks):
            mk = self.cube_marks[j]
            mk["life"] -= dt * 0.62
            mk["r"] += mk["grow"] * dt
            if mk["life"] <= 0.0:
                self.cube_marks[j] = self.cube_marks[-1]
                self.cube_marks.pop()
            else:
                j += 1

    # ------------------------------------------------------------------
    # Draw helpers
    # ------------------------------------------------------------------

    def _proj1(self, x, y, z, rx, ry, rz, scx, scy, fov, z_off):
        """Project a single world point to screen."""
        p = _3d_proj([(x, y, z)], rx, ry, rz, scx, scy, fov, z_off)[0]
        return int(p[0]), int(p[1]), p[3]  # sx, sy, scale

    def _draw_ellipse_alpha(self, surface, col_rgb, alpha, cx, cy, rx, ry):
        if rx < 1 or ry < 1:
            return
        s = pygame.Surface((rx * 2, ry * 2), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (*col_rgb, alpha), (0, 0, rx * 2, ry * 2))
        surface.blit(s, (cx - rx, cy - ry))

    def _draw_circle_glow(self, surface, col_rgb, cx, cy, r, alpha=100):
        if r < 1:
            return
        s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*col_rgb, alpha), (r, r), r)
        surface.blit(s, (cx - r, cy - r))

    # ------------------------------------------------------------------
    # Main draw
    # ------------------------------------------------------------------

    def draw(self, surface, rx, ry, rz, scx, scy, t, fov=900.0, z_off=800.0, layer="all"):
        """
        Draw Zeus fully in 3D. layer="behind" draws body, layer="fx" draws spray.
        The method is also called with layer="all" from legacy call sites.
        """
        # Root world position (always left of camera)
        wx, wy, wz = self._root_world(rx, ry, rz)
        s = self._scale()

        # Build a local-to-world function that cancels camera rotation so Zeus
        # never tilts with the cube - he always stands upright.
        cxx, sxx = math.cos(rx), math.sin(rx)
        cyy, syy = math.cos(ry), math.sin(ry)
        czz, szz = math.cos(rz), math.sin(rz)

        def lw(lx, ly, lz):
            """Local Zeus-body offset -> world coords (camera rotation cancelled)."""
            # Invert camera rotation (ZYX)
            x0, y0 = czz * lx + szz * ly, -szz * lx + czz * ly
            x0, z0 = cyy * x0 - syy * lz, syy * x0 + cyy * lz
            y0, z0 = cxx * y0 + sxx * z0, -sxx * y0 + cxx * z0
            return (wx + x0, wy + y0, wz + z0)

        def p1(lx, ly, lz):
            """Local -> projected screen point (sx, sy, scale)."""
            wpt = lw(lx, ly, lz)
            pp = _3d_proj([wpt], rx, ry, rz, scx, scy, fov, z_off)[0]
            return int(pp[0]), int(pp[1]), max(0.3, pp[3] * 2.2)

        def pline(surface, col, pts_local, w=2):
            """Draw a polyline through local-space points."""
            if len(pts_local) < 2:
                return
            wpts = [lw(*pt) for pt in pts_local]
            proj = _3d_proj(wpts, rx, ry, rz, scx, scy, fov, z_off)
            sp = [(int(q[0]), int(q[1])) for q in proj]
            for i in range(1, len(sp)):
                pygame.draw.line(surface, col, sp[i - 1], sp[i], w)

        def pfill(surface, col, pts_local):
            """Draw a filled polygon through local-space points."""
            wpts = [lw(*pt) for pt in pts_local]
            proj = _3d_proj(wpts, rx, ry, rz, scx, scy, fov, z_off)
            sp = [(int(q[0]), int(q[1])) for q in proj]
            if len(sp) >= 3:
                pygame.draw.polygon(surface, col, sp)

        def pfill_outline(surface, col, outline_col, pts_local, bw=1):
            pfill(surface, col, pts_local)
            wpts = [lw(*pt) for pt in pts_local]
            proj = _3d_proj(wpts, rx, ry, rz, scx, scy, fov, z_off)
            sp = [(int(q[0]), int(q[1])) for q in proj]
            if len(sp) >= 3:
                pygame.draw.polygon(surface, outline_col, sp, bw)

        # Color palette
        BRONZE = (180, 120, 40)
        BRONZE_DARK = (120, 75, 20)
        BRONZE_LT = (220, 175, 80)
        SKIN = (225, 195, 160)
        SKIN_DARK = (170, 130, 100)
        LINEN = (230, 225, 200)
        LINEN_DARK = (180, 170, 145)
        BEARD_COL = (230, 230, 235)  # white/silver beard
        HELMET_CREST = (200, 30, 30)
        LIGHTNING = (255, 255, 160)
        BOLT_GLOW = (200, 200, 80)
        GOLD_COL = (255, 215, 40)

        # pulse for living effects
        pulse = 0.5 + 0.5 * math.sin(t * 2.4)

        if layer in ("behind", "all"):

            # 1. Aura glow behind Zeus
            ax, ay, ascl = p1(0, -s * 0.4, 0)
            gr = max(20, int(s * 0.85 * ascl))
            self._draw_circle_glow(surface, (230, 240, 255), ax, ay, gr, int(70 * (0.7 + 0.3 * pulse)))
            self._draw_circle_glow(surface, (180, 210, 255), ax, ay, int(gr * 0.65), int(50 * (0.7 + 0.3 * pulse)))

            # 2. Toga / robe (back layer)
            toga_back = [
                (-s * 0.52, -s * 0.18, -s * 0.08),
                (-s * 0.48, s * 0.28, -s * 0.08),
                (-s * 0.35, s * 0.70, -s * 0.08),
                (-s * 0.10, s * 0.90, -s * 0.08),
                (s * 0.10, s * 0.88, -s * 0.08),
                (s * 0.35, s * 0.70, -s * 0.08),
                (s * 0.48, s * 0.28, -s * 0.08),
                (s * 0.52, -s * 0.18, -s * 0.08),
            ]
            pfill(surface, LINEN_DARK, toga_back)

            toga_front = [
                (-s * 0.48, -s * 0.20, s * 0.10),
                (-s * 0.44, s * 0.25, s * 0.10),
                (-s * 0.32, s * 0.68, s * 0.10),
                (-s * 0.08, s * 0.88, s * 0.10),
                (s * 0.08, s * 0.86, s * 0.10),
                (s * 0.32, s * 0.68, s * 0.10),
                (s * 0.44, s * 0.25, s * 0.10),
                (s * 0.48, -s * 0.20, s * 0.10),
            ]
            pfill_outline(surface, LINEN, LINEN_DARK, toga_front, 1)

            # Toga diagonal drape fold
            pline(surface, LINEN_DARK, [
                (-s * 0.44, s * 0.00, s * 0.12),
                (s * 0.10, s * 0.38, s * 0.14),
                (s * 0.44, s * 0.22, s * 0.12),
            ], 3)
            pline(surface, (210, 205, 182), [
                (-s * 0.44, s * 0.00, s * 0.13),
                (s * 0.10, s * 0.38, s * 0.15),
                (s * 0.44, s * 0.22, s * 0.13),
            ], 1)

            # 3. Breastplate / cuirass
            chest = [
                (-s * 0.36, -s * 0.32, s * 0.12),
                (s * 0.36, -s * 0.32, s * 0.12),
                (s * 0.28, s * 0.22, s * 0.14),
                (-s * 0.28, s * 0.22, s * 0.14),
            ]
            pfill_outline(surface, BRONZE, BRONZE_DARK, chest, 2)
            # Centre ridge
            pline(surface, BRONZE_LT, [
                (0, -s * 0.30, s * 0.16),
                (0, s * 0.20, s * 0.16),
            ], 2)
            # Pec muscle lines
            for sx2 in (-1, 1):
                pline(surface, BRONZE_DARK, [
                    (sx2 * s * 0.08, -s * 0.24, s * 0.17),
                    (sx2 * s * 0.28, -s * 0.12, s * 0.16),
                    (sx2 * s * 0.26, s * 0.04, s * 0.15),
                ], 2)
            # Waist pteryges (leather strips)
            for k in range(7):
                px2 = -s * 0.28 + k * (s * 0.56 / 6)
                strip = [
                    (px2, s * 0.20, s * 0.15),
                    (px2, s * 0.42, s * 0.15),
                    (px2 + s * 0.04, s * 0.42, s * 0.15),
                    (px2 + s * 0.04, s * 0.20, s * 0.15),
                ]
                col_strip = BRONZE if k % 2 == 0 else BRONZE_DARK
                pfill_outline(surface, col_strip, BRONZE_DARK, strip, 1)

            # 4. Legs
            # Left leg
            pfill_outline(surface, SKIN, SKIN_DARK, [
                (-s * 0.28, s * 0.42, s * 0.12),
                (-s * 0.06, s * 0.42, s * 0.12),
                (-s * 0.08, s * 0.88, s * 0.10),
                (-s * 0.26, s * 0.88, s * 0.10),
            ], 1)
            # Right leg
            pfill_outline(surface, SKIN, SKIN_DARK, [
                (s * 0.06, s * 0.42, s * 0.12),
                (s * 0.28, s * 0.42, s * 0.12),
                (s * 0.26, s * 0.88, s * 0.10),
                (s * 0.08, s * 0.88, s * 0.10),
            ], 1)
            # Greaves (bronze shin guards)
            for sx2 in (-1, 1):
                greave = [
                    (sx2 * s * 0.08, s * 0.55, s * 0.14),
                    (sx2 * s * 0.24, s * 0.55, s * 0.14),
                    (sx2 * s * 0.24, s * 0.86, s * 0.13),
                    (sx2 * s * 0.08, s * 0.86, s * 0.13),
                ]
                pfill_outline(surface, BRONZE, BRONZE_DARK, greave, 1)
                pline(surface, BRONZE_LT, [
                    (sx2 * s * 0.16, s * 0.58, s * 0.15),
                    (sx2 * s * 0.16, s * 0.83, s * 0.15),
                ], 1)
            # Sandals
            for sx2 in (-1, 1):
                sandal = [
                    (sx2 * s * 0.06, s * 0.86, s * 0.14),
                    (sx2 * s * 0.27, s * 0.86, s * 0.14),
                    (sx2 * s * 0.28, s * 0.92, s * 0.13),
                    (sx2 * s * 0.04, s * 0.92, s * 0.13),
                ]
                pfill_outline(surface, BRONZE_DARK, (80, 40, 10), sandal, 1)

            # 5. Arms
            hand_t_anim = self.hand_t

            # LEFT arm - raised holding lightning bolt
            l_shoulder = lw(-s * 0.38, -s * 0.28, s * 0.10)
            l_elbow = lw(-s * 0.55, -s * 0.08, s * 0.10)
            l_hand = lw(-s * 0.64, -s * 0.38, s * 0.10)  # raised up

            sh_pts = [l_shoulder, l_elbow, l_hand]
            proj_sh = _3d_proj(sh_pts, rx, ry, rz, scx, scy, fov, z_off)
            sp_sh = [(int(q[0]), int(q[1])) for q in proj_sh]
            scl_sh = max(0.4, proj_sh[0][3] * 2.1)

            for i in range(1, len(sp_sh)):
                pygame.draw.line(surface, SKIN_DARK, sp_sh[i - 1], sp_sh[i], max(6, int(16 * scl_sh)))
                pygame.draw.line(surface, SKIN, sp_sh[i - 1], sp_sh[i], max(4, int(10 * scl_sh)))

            # RIGHT arm - raised, down at side, slight forward pose
            lift_r = math.sin(hand_t_anim) * s * 0.06
            r_shoulder = lw(s * 0.38, -s * 0.28, s * 0.10)
            r_elbow = lw(s * 0.55, -s * 0.10 + lift_r, s * 0.12)
            r_hand = lw(s * 0.65, -s * 0.20 + lift_r * 2, s * 0.14)

            sh_pts_r = [r_shoulder, r_elbow, r_hand]
            proj_shr = _3d_proj(sh_pts_r, rx, ry, rz, scx, scy, fov, z_off)
            sp_shr = [(int(q[0]), int(q[1])) for q in proj_shr]

            for i in range(1, len(sp_shr)):
                pygame.draw.line(surface, SKIN_DARK, sp_shr[i - 1], sp_shr[i], max(6, int(16 * scl_sh)))
                pygame.draw.line(surface, SKIN, sp_shr[i - 1], sp_shr[i], max(4, int(10 * scl_sh)))

            # Shoulder pauldrons
            for sx2, rsx, rsy in ((-1, -s * 0.38, -s * 0.28), (1, s * 0.38, -s * 0.28)):
                pauldron = [
                    (rsx - sx2 * s * 0.02, rsy - s * 0.04, s * 0.11),
                    (rsx + sx2 * s * 0.12, rsy - s * 0.04, s * 0.11),
                    (rsx + sx2 * s * 0.14, rsy + s * 0.10, s * 0.10),
                    (rsx - sx2 * s * 0.04, rsy + s * 0.10, s * 0.10),
                ]
                pfill_outline(surface, BRONZE, BRONZE_DARK, pauldron, 1)

            # 6. Neck + head (3D sphere-ish)
            nx2, ny2, nscl = p1(0, -s * 0.46, s * 0.10)
            neck_r = max(4, int(9 * nscl))
            pygame.draw.circle(surface, SKIN_DARK, (nx2, ny2), neck_r + 3)
            pygame.draw.circle(surface, SKIN, (nx2, ny2), neck_r)

            hx2, hy2, hscl = p1(0, -s * 0.74, s * 0.10)
            head_r = max(8, int(22 * hscl))

            # Head back (dark)
            self._draw_circle_glow(surface, SKIN_DARK, hx2, hy2, head_r + 3, 220)
            # Head front
            pygame.draw.circle(surface, SKIN, (hx2, hy2), head_r)
            pygame.draw.circle(surface, SKIN_DARK, (hx2, hy2), head_r, 2)

            # Ear left
            ex, ey, _ = p1(-s * 0.18, -s * 0.70, s * 0.06)
            ear_r = max(2, int(5 * hscl))
            pygame.draw.ellipse(surface, SKIN_DARK, (ex - ear_r, ey - ear_r * 2, ear_r * 2, ear_r * 4))
            pygame.draw.ellipse(surface, SKIN, (ex - ear_r + 1, ey - ear_r * 2 + 2, ear_r * 2 - 2, ear_r * 4 - 4))

            # Eye sockets / brow ridge
            for ex_off in (-0.38, 0.38):
                ex3, ey3, _ = p1(ex_off * s * 0.38, -s * 0.80, s * 0.22)
                eye_r = max(2, int(5 * hscl))
                # Brow
                brow_pts = [(ex3 - eye_r * 2, ey3 - eye_r - 3), (ex3 + eye_r * 2, ey3 - eye_r - 3)]
                pygame.draw.line(surface, (70, 60, 50), brow_pts[0], brow_pts[1], max(2, int(3 * hscl)))
                # Eye white
                pygame.draw.ellipse(surface, (255, 255, 255),
                                    (ex3 - eye_r, ey3 - eye_r // 2, eye_r * 2, eye_r))
                # Iris
                pygame.draw.circle(surface, (60, 100, 180), (ex3, ey3), max(1, eye_r - 1))
                # Pupil
                pygame.draw.circle(surface, (5, 5, 5), (ex3, ey3), max(1, eye_r // 2))

            # Nose (ridge)
            nx3, ny3a, _ = p1(0, -s * 0.76, s * 0.24)
            nx4, ny3b, _ = p1(0, -s * 0.62, s * 0.26)
            pygame.draw.line(surface, SKIN_DARK, (nx3, ny3a), (nx4, ny3b), max(2, int(4 * hscl)))
            nx5, ny3c, _ = p1(-s * 0.08, -s * 0.60, s * 0.24)
            nx6, ny3d, _ = p1(s * 0.08, -s * 0.60, s * 0.24)
            pygame.draw.line(surface, SKIN_DARK, (nx5, ny3c), (nx4, ny3b), max(2, int(3 * hscl)))
            pygame.draw.line(surface, SKIN_DARK, (nx6, ny3d), (nx4, ny3b), max(2, int(3 * hscl)))

            # Mouth - stern / divine
            mx3, my3, _ = p1(-s * 0.10, -s * 0.54, s * 0.24)
            mx4, my4, _ = p1(s * 0.10, -s * 0.54, s * 0.24)
            pygame.draw.line(surface, SKIN_DARK, (mx3, my3), (mx4, my4), max(2, int(3 * hscl)))

            # Beard (layered wavy strips)
            for bk, by_off in enumerate([0.0, 0.06, 0.12, 0.18]):
                bpts = []
                n_bp = 7
                for bj in range(n_bp):
                    bfrac = bj / (n_bp - 1)
                    bx_local = (-0.24 + bfrac * 0.48) * s
                    wave = math.sin(t * 3.0 + bj * 0.8 + bk * 1.2) * s * 0.015
                    bpts.append((bx_local + wave, -s * 0.48 + s * by_off + wave * 0.5, s * 0.22))
                pline(surface, BEARD_COL, bpts, max(2, int(6 * hscl) - bk))
            # Beard tip
            pline(surface, BEARD_COL, [
                (0, -s * 0.30, s * 0.22),
                (s * 0.04, -s * 0.14, s * 0.20),
                (0, -s * 0.06, s * 0.18),
            ], max(2, int(5 * hscl)))
            # Moustache
            for mx_off, mx_end in ((-1, -0.22), (1, 0.22)):
                pline(surface, BEARD_COL, [
                    (0, -s * 0.52, s * 0.25),
                    (mx_off * s * 0.12, -s * 0.53, s * 0.26),
                    (mx_end * s, -s * 0.51, s * 0.24),
                ], max(2, int(4 * hscl)))

            # 7. Corinthian helmet
            # Helmet bowl
            helm_pts = []
            n_h = 12
            for k in range(n_h + 1):
                a = math.pi * k / n_h  # 0..pi (semicircle front)
                hpx = math.cos(a) * s * 0.22
                hpy = -s * 0.74 - s * 0.28 + math.sin(a) * s * 0.28
                helm_pts.append((hpx, hpy, s * 0.12))
            pline(surface, BRONZE_DARK, helm_pts, max(2, int(4 * hscl) + 1))
            pline(surface, BRONZE_LT, helm_pts, max(1, int(2 * hscl)))

            # Cheek guards
            for sx2 in (-1, 1):
                cheek = [
                    (sx2 * s * 0.20, -s * 0.74, s * 0.18),
                    (sx2 * s * 0.24, -s * 0.60, s * 0.20),
                    (sx2 * s * 0.18, -s * 0.52, s * 0.21),
                    (sx2 * s * 0.12, -s * 0.54, s * 0.22),
                    (sx2 * s * 0.12, -s * 0.70, s * 0.22),
                ]
                pfill_outline(surface, BRONZE, BRONZE_DARK, cheek, 1)

            # Nose guard
            ng = [
                (0, -s * 0.74, s * 0.26),
                (-s * 0.03, -s * 0.68, s * 0.27),
                (s * 0.03, -s * 0.68, s * 0.27),
            ]
            pfill(surface, BRONZE, ng)

            # Crest - red plume along top
            crest_root = [(k * s * 0.04 - s * 0.20, -s * 0.74 - s * 0.28 + s * 0.04, s * 0.12) for k in range(11)]
            crest_tip = []
            for k, cr in enumerate(crest_root):
                wave = math.sin(t * 4.0 + k * 0.4) * s * 0.02
                crest_tip.append((cr[0], cr[1] - s * 0.20 + wave, s * 0.14))
            crest_back = list(reversed(crest_root))
            crest_poly = crest_root + crest_tip + crest_back
            pfill(surface, HELMET_CREST, crest_poly)
            pline(surface, (240, 60, 60), crest_tip, max(2, int(4 * hscl)))

            # Helmet rim highlight
            rim_pts = [
                (-s * 0.22, -s * 0.74, s * 0.18),
                (-s * 0.24, -s * 0.66, s * 0.20),
                (0, -s * 0.63, s * 0.26),
                (s * 0.24, -s * 0.66, s * 0.20),
                (s * 0.22, -s * 0.74, s * 0.18),
            ]
            pline(surface, BRONZE_LT, rim_pts, max(1, int(2 * hscl)))

            # 8. Left hand holds lightning bolt
            bolt_base = l_hand
            bolt_proj = _3d_proj([bolt_base], rx, ry, rz, scx, scy, fov, z_off)[0]
            bscl = max(0.4, bolt_proj[3] * 2.1)
            if self._bolt_pts:
                bolt_world = [lw(bolt_base[0] / s * s + bpt[0],
                                 # anchor to hand local pos
                                 (-s * 0.38 + bpt[1]),
                                 s * 0.10 + bpt[2])
                              for bpt in self._bolt_pts]
                # Hack: move bolt relative to hand in world space
                bx_w, by_w, bz_w = bolt_base
                bolt_world2 = []
                for bpt in self._bolt_pts:
                    bolt_world2.append((bx_w + bpt[0], by_w + bpt[1], bz_w + bpt[2]))
                bolt_proj2 = _3d_proj(bolt_world2, rx, ry, rz, scx, scy, fov, z_off)
                bsp = [(int(q[0]), int(q[1])) for q in bolt_proj2]
                bw = max(2, int(4 * bscl))
                # Outer glow
                for i in range(1, len(bsp)):
                    pygame.draw.line(surface, (80, 80, 0), bsp[i - 1], bsp[i], bw + 6)
                    pygame.draw.line(surface, BOLT_GLOW, bsp[i - 1], bsp[i], bw + 3)
                    pygame.draw.line(surface, LIGHTNING, bsp[i - 1], bsp[i], bw)
                    pygame.draw.line(surface, (255, 255, 255), bsp[i - 1], bsp[i], max(1, bw - 2))
                # Tip glow
                if bsp:
                    tip = bsp[-1]
                    gr2 = max(4, int(12 * bscl))
                    self._draw_circle_glow(surface, (255, 255, 200), tip[0], tip[1], gr2, int(180 * pulse))
                    pygame.draw.circle(surface, (255, 255, 255), tip, max(2, gr2 // 2))

            # 9. Right hand - palm-down divine gesture
            rhand_p = _3d_proj([r_hand], rx, ry, rz, scx, scy, fov, z_off)[0]
            rh_scl = max(0.4, rhand_p[3] * 2.1)
            rh_r = max(4, int(9 * rh_scl))
            self._draw_circle_glow(surface, (255, 230, 180), int(rhand_p[0]), int(rhand_p[1]), rh_r + 4, int(100 * pulse))
            pygame.draw.circle(surface, SKIN, (int(rhand_p[0]), int(rhand_p[1])), rh_r)
            pygame.draw.circle(surface, SKIN_DARK, (int(rhand_p[0]), int(rhand_p[1])), rh_r, 1)

            # 10. Gold sandal laces
            for sx2 in (-1, 1):
                for k in range(3):
                    y_lace = s * (0.56 + k * 0.08)
                    pline(surface, GOLD_COL, [
                        (sx2 * s * 0.08, y_lace, s * 0.16),
                        (sx2 * s * 0.24, y_lace, s * 0.16),
                    ], 1)

        if layer in ("fx", "all"):
            # Spray trails
            for p_spr in self.spray:
                tr = p_spr["trail"]
                if len(tr) > 1:
                    tproj = _3d_proj(tr, rx, ry, rz, scx, scy, fov, z_off)
                    for i2 in range(1, len(tproj)):
                        f = i2 / len(tproj)
                        c1 = (int(100 * f), int(120 * f), int(155 * f))
                        c2 = (int(225 * f), int(238 * f), int(255 * f))
                        p0 = (int(tproj[i2 - 1][0]), int(tproj[i2 - 1][1]))
                        p1b = (int(tproj[i2][0]), int(tproj[i2][1]))
                        pygame.draw.line(surface, c1, p0, p1b, max(1, int(5 * f)))
                        pygame.draw.line(surface, c2, p0, p1b, max(1, int(3 * f)))
                pp = _3d_proj([(p_spr["x"], p_spr["y"], p_spr["z"])], rx, ry, rz, scx, scy, fov, z_off)[0]
                fade = max(0.0, min(1.0, p_spr["life"]))
                rr2 = max(1, int(p_spr["size"] * max(0.45, pp[3] * 2.1)))
                pygame.draw.circle(surface, (int(210 * fade), int(230 * fade), int(255 * fade)),
                                   (int(pp[0]), int(pp[1])), rr2)
                if rr2 > 1:
                    pygame.draw.circle(surface, (255, 255, 255), (int(pp[0]), int(pp[1])), max(1, rr2 // 2))

            # Cube impact marks
            for mk in self.cube_marks:
                mp = _3d_proj([(mk["x"], mk["y"], mk["z"])], rx, ry, rz, scx, scy, fov, z_off)[0]
                fade = max(0.0, min(1.0, mk["life"]))
                rr2 = max(1, int(mk["r"] * max(0.45, mp[3] * 2.0)))
                c2 = (int(230 * fade), int(240 * fade), int(255 * fade))
                pygame.draw.circle(surface, c2, (int(mp[0]), int(mp[1])), rr2, max(1, int(4 * fade)))
                pygame.draw.circle(surface, (255, 255, 255), (int(mp[0]), int(mp[1])), max(1, rr2 // 3))


class Obj3DGravityWell:
    def __init__(self, bouncer_obj):
        self.bobj  = bouncer_obj
        self.angle = 0.0
        self.pulse = random.uniform(0,6.28)

    def update(self, dt):
        self.angle += 0.9*dt

    def draw(self, surface, rx, ry, rz, scx, scy, t, fov=900.0, z_off=800.0):
        wx,wy,wz = self.bobj.x, self.bobj.y, self.bobj.z
        p   = 0.5+0.5*math.sin(t*2.4+self.pulse)
        col = (int(160+80*p),int(0+30*p),int(220+35*p))
        ring_pts = []
        for k in range(16):
            a = self.angle+k*math.pi/8
            ring_pts.append((wx+55*math.cos(a), wy, wz+55*math.sin(a)))
        pr = _3d_proj(ring_pts, rx, ry, rz, scx, scy, fov, z_off)
        rsp = [(int(q[0]),int(q[1])) for q in pr]
        for i in range(len(rsp)):
            pygame.draw.line(surface,col,rsp[i],rsp[(i+1)%len(rsp)],2)
        cp = _3d_proj([(wx,wy,wz)], rx, ry, rz, scx, scy, fov, z_off)[0]
        cr = max(6,int(18*(0.8+0.2*p)))
        gs = pygame.Surface((cr*4,cr*4),pygame.SRCALPHA)
        pygame.draw.circle(gs,(*col,120),(cr*2,cr*2),cr*2)
        surface.blit(gs,(int(cp[0])-cr*2,int(cp[1])-cr*2))
        pygame.draw.circle(surface,col,(int(cp[0]),int(cp[1])),cr)
        pygame.draw.circle(surface,(5,0,10),(int(cp[0]),int(cp[1])),max(2,cr//2))


class Mode3DEffect:
    FOV  = 900.0
    RX_V = 0.00055
    RY_V = 0.00095
    RZ_V = 0.00022

    def __init__(self):
        self.income_timer = pygame.time.get_ticks()
        self._half_base = min(GAME_WIDTH,HEIGHT)*0.44
        self._half_god  = min(GAME_WIDTH,HEIGHT)*0.32
        self.half  = self._half_god if total_goon_god_power() > 0 else self._half_base
        self.rx    = 0.18; self.ry = 0.28; self.rz = 0.04
        self.cam_t = 0.0
        self.pulse = 0.0
        self.world_objs = []
        self._bouncer_objs = []
        self._waves3d = []
        self._laser3d = []
        self._lightning3d = []
        self._rebuild_world()

    def _sync_half(self):
        target = self._half_god if total_goon_god_power() > 0 else self._half_base
        if abs(self.half - target) > 0.01:
            self.half = target
            self._rebuild_world()

    def _rebuild_world(self):
        self.world_objs.clear()
        self._bouncer_objs.clear()
        hw = self.half
        # Bouncer cubes
        bouncer_objs = []
        for b in bouncers:
            obj = Obj3DBouncer(b, hw)
            self.world_objs.append(obj)
            bouncer_objs.append(obj)
            self._bouncer_objs.append(obj)
        donut_owners = [b for b in bouncers if b.donut_enabled and b.donut_ring_count > 0]
        if donut_owners:
            self.world_objs.append(Obj3DDonutRing(donut_owners, hw))
        god_power = sum(max(0, b.goon_god_purchases) for b in bouncers if b.goon_god_enabled)
        if god_power > 0:
            self.world_objs.append(Obj3DGoonGod(god_power, hw))
        # Illuminate pyramid (always centred in 3D mode)
        n = len(illuminate_effects)
        if n > 0:
            self.world_objs.append(Obj3DPrism(0.0, 0.0, 0.0, n))
        # Factory boxes
        n_fac = len(factories)
        for i in range(n_fac):
            if n_fac == 1:
                x3, z3 = 0.0, 0.0
            else:
                a = i * (_TWO_PI / n_fac)
                band = 0.45 + 0.18 * (1 if i % 2 == 0 else -1)
                x3 = hw * band * math.cos(a)
                z3 = hw * (0.28 + 0.12 * math.sin(i * 1.7)) * math.sin(a)
            self.world_objs.append(Obj3DFactory(x3, hw, z3))
        # Gravity well orbs (paired to bouncer objs)
        for geff in gravity_effects:
            paired = next((o for o in bouncer_objs if o.b is geff.bouncer), None)
            if paired:
                self.world_objs.append(Obj3DGravityWell(paired))

    def _world_signature(self):
        """A hashable key representing which game objects currently exist."""
        return (tuple((id(b), b.donut_enabled, b.donut_ring_count, b.goon_god_enabled, b.goon_god_purchases) for b in bouncers),
                len(illuminate_effects), len(factories),
                tuple(id(g.bouncer) for g in gravity_effects))

    def _spawn_bounce_fx(self, bobj, hit_pt, normal):
        nx, ny, nz = normal
        donut_power = bobj.b.donut_ring_count * 25 if bobj.b.donut_enabled else 0
        wave_on = bobj.b.waves_enabled or donut_power > 0
        laser_power = bobj.b.laser_purchases + donut_power
        lightning_power = bobj.b.lightning_purchases + donut_power
        # Build an orthonormal basis around the wall normal for spread.
        ax = (1.0, 0.0, 0.0) if abs(nx) < 0.9 else (0.0, 1.0, 0.0)
        ux = ny * ax[2] - nz * ax[1]
        uy = nz * ax[0] - nx * ax[2]
        uz = nx * ax[1] - ny * ax[0]
        um = math.sqrt(max(1e-9, ux*ux + uy*uy + uz*uz))
        ux, uy, uz = ux / um, uy / um, uz / um
        vx = ny * uz - nz * uy
        vy = nz * ux - nx * uz
        vz = nx * uy - ny * ux

        if wave_on:
            def dist_to_box(pos, direction):
                x0, y0, z0 = pos
                dx, dy, dz = direction
                tmin = float("inf")
                for p0, dp in ((x0, dx), (y0, dy), (z0, dz)):
                    if abs(dp) < 1e-6:
                        continue
                    edge = self.half if dp > 0 else -self.half
                    t = (edge - p0) / dp
                    if t > 0:
                        tmin = min(tmin, t)
                return tmin if tmin != float("inf") else 0.0

            du1 = dist_to_box(hit_pt, (ux, uy, uz))
            du2 = dist_to_box(hit_pt, (-ux, -uy, -uz))
            dv1 = dist_to_box(hit_pt, (vx, vy, vz))
            dv2 = dist_to_box(hit_pt, (-vx, -vy, -vz))
            max_r = max(18.0, min(du1, du2, dv1, dv2) * 0.95)
            wave_col = (100, 255, 170) if goon_mode else bobj.b.color
            self._waves3d.append({
                "c": hit_pt,
                "u": (ux, uy, uz),
                "v": (vx, vy, vz),
                "r": 8.0,
                "max_r": max_r,
                "col": wave_col,
            })

        if laser_power > 0:
            shots = min(laser_power, LASER_MAX_SHOTS_PER_TICK)
            half = (shots - 1) * 0.5
            for si in range(shots):
                spread = (si - half) * 0.22
                bend = random.uniform(-0.08, 0.08)
                dx = nx + ux * spread + vx * bend
                dy = ny + uy * spread + vy * bend
                dz = nz + uz * spread + vz * bend
                dm = math.sqrt(max(1e-9, dx*dx + dy*dy + dz*dz))
                spd = 290.0
                self._laser3d.append({
                    "x": hit_pt[0], "y": hit_pt[1], "z": hit_pt[2],
                    "vx": dx / dm * spd, "vy": dy / dm * spd, "vz": dz / dm * spd,
                    "life": 1.0, "trail": [hit_pt],
                })

        if lightning_power > 0:
            targets = [o for o in self._bouncer_objs if o is not bobj]
            targets.sort(key=lambda o: (o.x - hit_pt[0])**2 + (o.y - hit_pt[1])**2 + (o.z - hit_pt[2])**2)
            chain_count = min(len(targets), max(1, min(8, lightning_power)))
            segments = []
            for target in targets[:chain_count]:
                segments.append(self._jagged_line_points3d(hit_pt, (target.x, target.y, target.z), jag=18, segs=8))
            if segments:
                self._lightning3d.append({"segments": segments, "life": 0.45})

    def _jagged_line_points3d(self, p0, p1, jag=14, segs=8):
        x1, y1, z1 = p0
        x2, y2, z2 = p1
        dx, dy, dz = x2 - x1, y2 - y1, z2 - z1
        length = math.sqrt(dx*dx + dy*dy + dz*dz)
        if length <= 1e-6:
            return [p0, p1]
        tx, ty, tz = dx / length, dy / length, dz / length
        ax = (1.0, 0.0, 0.0) if abs(tx) < 0.9 else (0.0, 1.0, 0.0)
        ux = ty * ax[2] - tz * ax[1]
        uy = tz * ax[0] - tx * ax[2]
        uz = tx * ax[1] - ty * ax[0]
        um = math.sqrt(max(1e-9, ux*ux + uy*uy + uz*uz))
        ux, uy, uz = ux / um, uy / um, uz / um
        vx = ty * uz - tz * uy
        vy = tz * ux - tx * uz
        vz = tx * uy - ty * ux

        pts = [p0]
        for i in range(1, segs):
            t = i / segs
            mx = x1 + dx * t
            my = y1 + dy * t
            mz = z1 + dz * t
            o1 = random.uniform(-jag, jag)
            o2 = random.uniform(-jag, jag)
            pts.append((mx + ux * o1 + vx * o2, my + uy * o1 + vy * o2, mz + uz * o1 + vz * o2))
        pts.append(p1)
        return pts

    def update(self, dt):
        global coins
        self._sync_half()
        self.cam_t += dt
        # Keep motion dynamic but never allow upside-down camera flips.
        self.rx = 0.12 + 0.14 * math.sin(self.cam_t * 0.45)
        self.ry += 0.20 * dt
        self.rz = 0.03 * math.sin(self.cam_t * 0.30)
        self.pulse += dt*2.2
        # Only rebuild when objects appear/disappear, not every frame
        sig = self._world_signature()
        if not hasattr(self,'_last_sig') or sig != self._last_sig:
            self._last_sig = sig
            self._rebuild_world()
        for obj in self.world_objs:
            if isinstance(obj, Obj3DGoonGod):
                obj.update(dt, self.rx, self.ry, self.rz)
            else:
                obj.update(dt)
            if isinstance(obj, Obj3DBouncer) and obj.hit_events:
                for hit_pt, normal in obj.hit_events:
                    self._spawn_bounce_fx(obj, hit_pt, normal)

        # Update 3D hit waves constrained to cube walls.
        wi = 0
        while wi < len(self._waves3d):
            wv = self._waves3d[wi]
            wv["r"] += dt * 220.0
            if wv["r"] >= wv["max_r"]:
                self._waves3d[wi] = self._waves3d[-1]
                self._waves3d.pop()
            else:
                wi += 1

        # Update 3D-only laser trails (spawned from 3D wall hits).
        hw = self.half
        i = 0
        while i < len(self._laser3d):
            beam = self._laser3d[i]
            beam["x"] += beam["vx"] * dt
            beam["y"] += beam["vy"] * dt
            beam["z"] += beam["vz"] * dt

            if beam["x"] < -hw:
                beam["x"] = -hw
                beam["vx"] = abs(beam["vx"])
            if beam["x"] > hw:
                beam["x"] = hw
                beam["vx"] = -abs(beam["vx"])
            if beam["y"] < -hw:
                beam["y"] = -hw
                beam["vy"] = abs(beam["vy"])
            if beam["y"] > hw:
                beam["y"] = hw
                beam["vy"] = -abs(beam["vy"])
            if beam["z"] < -hw:
                beam["z"] = -hw
                beam["vz"] = abs(beam["vz"])
            if beam["z"] > hw:
                beam["z"] = hw
                beam["vz"] = -abs(beam["vz"])

            beam["trail"].append((beam["x"], beam["y"], beam["z"]))
            if len(beam["trail"]) > 34:
                beam["trail"].pop(0)
            beam["life"] -= dt * 0.55
            if beam["life"] <= 0.0:
                self._laser3d[i] = self._laser3d[-1]
                self._laser3d.pop()
            else:
                i += 1

        j = 0
        while j < len(self._lightning3d):
            bolt = self._lightning3d[j]
            bolt["life"] -= dt
            if bolt["life"] <= 0.0:
                self._lightning3d[j] = self._lightning3d[-1]
                self._lightning3d.pop()
            else:
                j += 1

        if len(self._laser3d) > LASER_MAX_ACTIVE_BEAMS:
            del self._laser3d[:-LASER_MAX_ACTIVE_BEAMS]
        if len(self._lightning3d) > 40:
            del self._lightning3d[:-40]
        if len(self._waves3d) > 48:
            del self._waves3d[:-48]
        now = pygame.time.get_ticks()
        if now - self.income_timer >= 1000:
            ticks = (now - self.income_timer) // 1000
            coins += MODE3D_INCOME_PER_SEC * ticks
            self.income_timer += ticks * 1000

    def draw(self, surface):
        self._sync_half()
        now   = pygame.time.get_ticks()
        t     = now/1000.0
        pulse = 0.5+0.5*math.sin(self.pulse)
        hs    = self.half
        scx   = GAME_WIDTH//2
        scy   = int(HEIGHT*0.68) if total_goon_god_power() > 0 else HEIGHT//2
        rx,ry,rz = self.rx,self.ry,self.rz

        surface.fill((4,4,12))
        for i in range(48):
            sx2 = int((i*137+42) % GAME_WIDTH)
            sy2 = int((i*97+18) % HEIGHT)
            br2 = 30+(i*31)%120
            pygame.draw.circle(surface,(br2,br2,br2+20),(sx2,sy2),1)

        raw = [(-hs,-hs,-hs),(+hs,-hs,-hs),(+hs,+hs,-hs),(-hs,+hs,-hs),
               (-hs,-hs,+hs),(+hs,-hs,+hs),(+hs,+hs,+hs),(-hs,+hs,+hs)]
        FACES = [(0,1,2,3,"back"),(4,5,6,7,"front"),
                 (0,1,5,4,"bottom"),(2,3,7,6,"top"),
                 (0,3,7,4,"left"),(1,2,6,5,"right")]
        EDGES = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
        NORMALS = {"back":(0,0,-1),"front":(0,0,1),"bottom":(0,-1,0),
                   "top":(0,1,0),"left":(-1,0,0),"right":(1,0,0)}
        FACE_BASE = {"back":(0,15,50),"front":(0,5,35),"bottom":(8,0,35),
                     "top":(0,30,15),"left":(30,8,0),"right":(0,8,35)}

        proj   = _3d_proj(raw,rx,ry,rz,scx,scy,self.FOV,hs*2)
        sp     = [(int(p[0]),int(p[1])) for p in proj]
        depths = [p[2] for p in proj]
        light  = (0.35,0.55,0.85)
        god_obj = next((o for o in self.world_objs if isinstance(o, Obj3DGoonGod)), None)
        if god_obj is not None:
            god_obj.draw(surface, rx, ry, rz, scx, scy, t, self.FOV, hs*2, layer="behind")
        donut_obj = next((o for o in self.world_objs if isinstance(o, Obj3DDonutRing)), None)
        if donut_obj is not None:
            donut_obj.draw(surface, rx, ry, rz, scx, scy, t, self.FOV, hs*2, layer="back")

        face_list = []
        for i0,i1,i2,i3,fname in FACES:
            avg_z = (depths[i0]+depths[i1]+depths[i2]+depths[i3])/4
            nx,ny,nz = NORMALS[fname]
            nr  = _3d_rot([(nx,ny,nz)],rx,ry,rz)[0]
            dot = nr[0]*light[0]+nr[1]*light[1]+nr[2]*light[2]
            br  = max(0.10,min(1.0,0.35+0.65*dot))
            face_list.append((avg_z,i0,i1,i2,i3,fname,br))
        face_list.sort(key=lambda x:x[0])

        for avg_z,i0,i1,i2,i3,fname,br in face_list:
            pts4  = [sp[i0],sp[i1],sp[i2],sp[i3]]
            base  = FACE_BASE[fname]
            hue_o = (t*0.22+avg_z/(hs*2)*0.25) % 1.0
            r2 = int((base[0]+70*(0.5+0.5*math.sin(hue_o*6.28)))*br)
            g2 = int((base[1]+70*(0.5+0.5*math.sin(hue_o*6.28+2.09)))*br)
            b2 = int((base[2]+100*(0.5+0.5*math.sin(hue_o*6.28+4.19)))*br)
            col2  = (max(0,min(255,r2)),max(0,min(255,g2)),max(0,min(255,b2)))
            glow = 0.78 + 0.22 * pulse
            col2 = (int(col2[0] * glow), int(col2[1] * glow), int(col2[2] * glow))
            pygame.draw.polygon(surface, col2, pts4)

        for obj in self.world_objs:
            if isinstance(obj,Obj3DBouncer):
                obj.draw(surface, rx, ry, rz, scx, scy, self.FOV, hs*2)
            elif isinstance(obj,Obj3DPrism):
                obj.draw(surface, rx, ry, rz, scx, scy, t, self.FOV, hs*2)
            elif isinstance(obj,Obj3DFactory):
                obj.draw(surface, rx, ry, rz, scx, scy, t, self.FOV, hs*2)
            elif isinstance(obj,Obj3DDonutRing):
                continue
            elif isinstance(obj,Obj3DGoonGod):
                continue
            elif isinstance(obj,Obj3DGravityWell):
                obj.draw(surface, rx, ry, rz, scx, scy, t, self.FOV, hs*2)

        # Project 2D upgrade effects into 3D space so upgrades stay visible in 3D mode.
        sx_scale = hs * 1.7 / GAME_WIDTH
        sy_scale = hs * 1.7 / HEIGHT

        def to_world(x2, y2, z2=0.0):
            return ((x2 - GAME_WIDTH * 0.5) * sx_scale,
                    (y2 - HEIGHT * 0.5) * sy_scale,
                    z2)

        # 3D wall-hit waves (stay on hit wall and inside cube).
        for wv in self._waves3d:
            fade = max(0.0, 1.0 - wv["r"] / max(1.0, wv["max_r"]))
            if fade <= 0.0:
                continue
            cx, cy, cz = wv["c"]
            ux, uy, uz = wv["u"]
            vx, vy, vz = wv["v"]
            r = wv["r"]
            pts3 = []
            for k in range(32):
                a = k * (2.0 * math.pi / 32.0)
                ca = math.cos(a); sa = math.sin(a)
                px = cx + (ux * ca + vx * sa) * r
                py = cy + (uy * ca + vy * sa) * r
                pz = cz + (uz * ca + vz * sa) * r
                px = max(-hs, min(hs, px))
                py = max(-hs, min(hs, py))
                pz = max(-hs, min(hs, pz))
                pts3.append((px, py, pz))
            pr = _3d_proj(pts3, rx, ry, rz, scx, scy, self.FOV, hs*2)
            ip = [(int(q[0]), int(q[1])) for q in pr]
            rc = wv["col"]
            c1 = (int(rc[0] * fade), int(rc[1] * fade), int(rc[2] * fade))
            c2 = (int(c1[0] * 0.45), int(c1[1] * 0.45), int(c1[2] * 0.45))
            w = max(1, int(4 * fade))
            for i in range(len(ip)):
                p0 = ip[i]
                p1 = ip[(i + 1) % len(ip)]
                pygame.draw.line(surface, c2, p0, p1, w + 2)
                pygame.draw.line(surface, c1, p0, p1, w)

        # 3D wall-hit lasers
        for beam in self._laser3d:
            tr = beam["trail"]
            if len(tr) < 2:
                continue
            proj_tr = _3d_proj(tr, rx, ry, rz, scx, scy, self.FOV, hs*2)
            n = len(proj_tr)
            life = beam["life"]
            for i in range(1, n):
                bright = (i / n) * life
                p0 = (int(proj_tr[i-1][0]), int(proj_tr[i-1][1]))
                p1 = (int(proj_tr[i][0]), int(proj_tr[i][1]))
                pygame.draw.line(surface, (int(140*bright), 0, 0), p0, p1, 10)
                pygame.draw.line(surface, (int(255*bright), int(60*bright), 0), p0, p1, 6)
                pygame.draw.line(surface, (255, int(200*bright), int(200*bright)), p0, p1, 3)
            hp = proj_tr[-1]
            pygame.draw.circle(surface, (255, 120, 120), (int(hp[0]), int(hp[1])), 7)
            pygame.draw.circle(surface, (255, 255, 255), (int(hp[0]), int(hp[1])), 3)

        # 3D wall-hit lightning
        for bolt in self._lightning3d:
            alpha_f = max(0.0, bolt["life"] / 0.45)
            if alpha_f <= 0.0:
                continue
            for seg in bolt["segments"]:
                proj_e = _3d_proj(seg, rx, ry, rz, scx, scy, self.FOV, hs*2)
                ipts = [(int(q[0]), int(q[1])) for q in proj_e]
                for i in range(1, len(ipts)):
                    p0, p1 = ipts[i-1], ipts[i]
                    pygame.draw.line(surface, (0, int(30*alpha_f), int(120*alpha_f)), p0, p1, 10)
                    pygame.draw.line(surface, (int(100*alpha_f), int(100*alpha_f), int(255*alpha_f)), p0, p1, 5)
                    pygame.draw.line(surface, (int(220*alpha_f), int(220*alpha_f), int(255*alpha_f)), p0, p1, 2)

        # Implosion effect states
        for eff in implosion_effects:
            if eff.phase == IMP_IDLE:
                continue
            cp = _3d_proj([to_world(eff._cx, eff._cy, 0.0)], rx, ry, rz, scx, scy, self.FOV, hs*2)[0]
            cpt = (int(cp[0]), int(cp[1]))
            scale = max(0.5, cp[3] * 2.0)
            if goon_mode:
                core_col = (110, 255, 170)
                glow_col = (40, 120, 90)
            else:
                core_col = (210, 150, 255)
                glow_col = (95, 35, 145)
            if eff.phase == IMP_SHRINK:
                prog = min((now - eff.phase_start) / max(1, IMPLOSION_SHRINK_MS), 1.0)
                rr = max(6, int((74 - 56 * prog) * scale))
                for k in range(12):
                    a = (k / 12.0) * _TWO_PI + now / 260.0
                    px = cpt[0] + int(math.cos(a) * rr)
                    py = cpt[1] + int(math.sin(a) * rr)
                    pygame.draw.line(surface, glow_col, (px, py), cpt, 2)
                pygame.draw.circle(surface, core_col, cpt, rr, 3)
                pygame.draw.circle(surface, (255, 255, 255), cpt, max(2, rr // 5))
            elif eff.phase == IMP_HOLD:
                rr = max(7, int(16 * scale))
                pulse_r = rr + int(3 * math.sin(now / 80.0))
                pygame.draw.circle(surface, glow_col, cpt, pulse_r + 4, 2)
                pygame.draw.circle(surface, core_col, cpt, pulse_r, 2)
                pygame.draw.circle(surface, (0, 0, 0), cpt, max(2, rr // 2))
                pygame.draw.circle(surface, (255, 255, 255), cpt, max(1, rr // 5))
            elif eff.phase == IMP_EXPLODE:
                prog = min((now - eff.phase_start) / max(1, IMPLOSION_EXPLODE_MS), 1.0)
                rr = max(10, int((260 * prog + 10) * scale))
                thick = max(1, int(10 * (1.0 - prog)))
                pygame.draw.circle(surface, (255, 255, 255), cpt, rr, thick)
                pygame.draw.circle(surface, core_col, cpt, max(3, int(rr * 0.55)), max(1, thick - 1))
                for k in range(8):
                    a = (k / 8.0) * _TWO_PI + now / 140.0
                    ex = cpt[0] + int(math.cos(a) * rr)
                    ey = cpt[1] + int(math.sin(a) * rr)
                    pygame.draw.circle(surface, core_col, (ex, ey), max(1, int(4 * (1.0 - prog))))

        # Flash + explosion particles in 3D
        def draw_projected_particles(plist, life_fade):
            i = 0
            while i < len(plist):
                p = plist[i]
                p[0] += p[2]
                p[1] += p[3]
                p[7] -= p[8]
                if p[7] <= 0:
                    plist[i] = plist[-1]
                    plist.pop()
                    continue
                if life_fade:
                    lf = p[7]
                    col = (int(p[4] * lf), int(p[5] * lf), int(p[6] * lf))
                else:
                    col = (int(p[4]), int(p[5]), int(p[6]))
                pp = _3d_proj([to_world(p[0], p[1], 0.0)], rx, ry, rz, scx, scy, self.FOV, hs*2)[0]
                rr = max(1, int(p[9] * max(0.45, pp[3] * 2.2)))
                pygame.draw.circle(surface, col, (int(pp[0]), int(pp[1])), rr)
                i += 1

        draw_projected_particles(flash_particles, False)
        draw_projected_particles(explosion_particles, True)
        if god_obj is not None:
            god_obj.draw(surface, rx, ry, rz, scx, scy, t, self.FOV, hs*2, layer="fx")

        for e0,e1 in EDGES:
            p0,p1  = sp[e0],sp[e1]
            d_avg  = (depths[e0]+depths[e1])*0.5
            eb     = max(0.35,min(1.0,0.5+d_avg/(hs*2)))
            ep     = int((150+100*pulse)*eb)
            pygame.draw.line(surface,(0,ep//4,ep),p0,p1,3)
            pygame.draw.line(surface,(ep,ep,255),p0,p1,1)

        for k,cpt in enumerate(sp):
            df  = max(0.3,min(1.0,0.5+depths[k]/(hs*2)))
            cr2 = max(3,int(9*df*(0.75+0.25*pulse)))
            pygame.draw.circle(surface,(60,180,255),cpt,cr2+3)
            pygame.draw.circle(surface,(200,240,255),cpt,max(1,cr2-1))

        # Draw donut front-half pass so it wraps around the cube, not flat in front.
        if donut_obj is not None:
            donut_obj.draw(surface, rx, ry, rz, scx, scy, t, self.FOV, hs*2, layer="front")

        pc  = (int(80+175*pulse),int(200+55*pulse),255)
        lbl = font.render("3 D   M O D E", True, pc)
        surface.blit(lbl, lbl.get_rect(center=(scx, scy+int(hs)+32)))


def update_mode3d(dt, now):
    if mode3d_effect:
        mode3d_effect.update(dt)

def draw_mode3d_pre(surface):
    return surface

def draw_mode3d_post(surface):
    if mode3d_active and mode3d_effect:
        mode3d_effect.draw(surface)

def select_bouncer(idx):
    global selected_index
    if not bouncers:
        return
    idx = idx % len(bouncers)
    bouncers[selected_index].selected = False
    selected_index = idx
    bouncers[selected_index].selected = True
    bouncers[selected_index].sync_shop_data()

# ------------------ BOUNCER ------------------
class Bouncer:
    __slots__ = ('size','fx','fy','rect','color','speed_x','speed_y','selected',
                 'waves_enabled','laser_enabled','last_laser_time','laser_cooldown',
                 'laser_purchases','flashing','flash_amount','flash_interval',
                 'flash_purchases','next_flash','coin_bonus','trail_enabled',
                 'trail_points','last_trail_income','trail_income','wave_income','last_donut_income','last_god_income',
                 'laser_income','implosion_enabled','implosion_frozen','lightning_enabled',
                 'lightning_purchases','illuminate_enabled','gravity_enabled','gravity_purchases',
                 'mode3d_enabled','donut_enabled','donut_ring_count',
                 'goon_god_enabled','goon_god_purchases','shop_data','draw_rect')

    def __init__(self, x, y):
        self.size    = 80
        self.fx      = float(x)
        self.fy      = float(y)
        self.rect    = pygame.Rect(x, y, self.size, self.size)
        self.draw_rect = pygame.Rect(x, y, self.size, self.size)
        self.color   = self._random_color()
        self.speed_x = 240.0
        self.speed_y = 240.0
        self.selected = False

        self.waves_enabled   = False
        self.laser_enabled   = False
        self.last_laser_time = 0
        self.laser_cooldown  = 1500
        self.laser_purchases = 0

        self.flashing        = False
        self.flash_amount    = 10
        self.flash_interval  = 5000
        self.flash_purchases = 0
        self.next_flash      = 0

        self.coin_bonus          = 0
        self.trail_enabled       = False
        self.trail_points        = []
        self.last_trail_income   = 0
        self.trail_income        = 0
        self.wave_income         = 0
        self.laser_income        = 0
        self.last_donut_income   = 0
        self.last_god_income     = 0
        self.implosion_enabled   = False
        self.implosion_frozen    = False
        self.lightning_enabled   = False
        self.lightning_purchases = 0
        self.illuminate_enabled  = False
        self.gravity_enabled     = False
        self.gravity_purchases   = 0
        self.mode3d_enabled      = False
        self.donut_enabled       = False
        self.donut_ring_count    = 0
        self.goon_god_enabled    = False
        self.goon_god_purchases  = 0

        self.shop_data = build_shop_data()

    def _random_color(self):
        return (random.randint(80,255), random.randint(80,255), random.randint(80,255))

    def random_color(self): return self._random_color()

    def increase_price(self, item):
        item["price"] = math.ceil(item["price"] * 1.25)

    def sync_shop_data(self):
        self.shop_data = build_shop_data(self.shop_data)

    def bought_count(self, action):
        it = next((entry for entry in self.shop_data if entry["action"] == action), None)
        return it["bought"] if it else 0

    def donut_upgrade_power(self):
        if not self.donut_enabled or self.donut_ring_count <= 0:
            return 0
        return self.donut_ring_count * 25

    def earnings_multiplier(self):
        if self.donut_enabled and self.donut_ring_count > 0:
            return self.donut_ring_count * 10
        return 1

    def is_unlocked(self, index):
        if cheat_mode or index == 0: return True
        action = self.shop_data[index]["action"]
        if action in ("bonus", "wave"):
            return self.bought_count("trail") >= 3
        return self.shop_data[index-1]["bought"] >= 3

    def _spawn_wave(self, side):
        if len(wave_rings) < 12:
            wc = (100, 255, 170) if goon_mode else self.color
            wave_rings.append(WaveRing(self.rect.centerx, self.rect.centery, wc, side,
                                       payout=300 * self.earnings_multiplier()))

    def _fire_laser(self, angle):
        cx, cy = self.rect.centerx, self.rect.centery
        laser_beams.append(LaserBeam(cx, cy, angle))

    def _emit_lasers(self, wall_side=None, extra_shots=0):
        # Fire from the bounce direction, not random, so wall hits feel intentional.
        shots = min(self.laser_purchases + max(0, int(extra_shots)), LASER_MAX_SHOTS_PER_TICK)
        if shots <= 0:
            return
        base_by_side = {
            "left":   0.0,
            "right":  math.pi,
            "top":    math.pi * 0.5,
            "bottom": -math.pi * 0.5,
        }
        base = base_by_side.get(wall_side)
        if base is None:
            for _ in range(shots):
                self._fire_laser(random.uniform(0, _TWO_PI))
            return
        spread = 0.22
        half = (shots - 1) * 0.5
        for si in range(shots):
            self._fire_laser(base + (si - half) * spread)

    def move(self, dt):
        global coins
        now = pygame.time.get_ticks()
        dp = self.donut_upgrade_power()
        mul = self.earnings_multiplier()
        flash_enabled_eff = self.flashing or dp > 0
        trail_enabled_eff = self.trail_enabled or dp > 0
        wave_enabled_eff = self.waves_enabled or dp > 0
        laser_power_eff = self.laser_purchases + dp
        lightning_power_eff = self.lightning_purchases + dp
        flash_amount_eff = self.flash_amount + dp * 10
        trail_income_eff = self.trail_income + dp * 5
        coin_bonus_eff = self.coin_bonus + dp
        wave_income_eff = self.wave_income + dp * 100
        donut_income_eff = DONUT_INCOME_PER_SEC * self.donut_ring_count if self.donut_enabled else 0
        god_income_eff = DONUT_INCOME_PER_SEC * 15 * self.goon_god_purchases if self.goon_god_enabled else 0

        if donut_income_eff > 0 and now - self.last_donut_income >= 1000:
            ticks = (now - self.last_donut_income) // 1000
            coins += donut_income_eff * ticks
            self.last_donut_income += ticks * 1000
        if god_income_eff > 0 and now - self.last_god_income >= 1000:
            ticks = (now - self.last_god_income) // 1000
            coins += god_income_eff * ticks
            self.last_god_income += ticks * 1000

        if self.implosion_frozen:
            if flash_enabled_eff and now >= self.next_flash:
                coins += flash_amount_eff * mul
                self.next_flash = now + self.flash_interval
                spawn_flash_particles(self.rect.centerx, self.rect.centery, self.color)
            if trail_enabled_eff and now - self.last_trail_income >= 1000:
                ticks = (now - self.last_trail_income) // 1000
                coins += trail_income_eff * mul * ticks
                self.last_trail_income += ticks * 1000
            return

        self.fx += self.speed_x * dt
        self.fy += self.speed_y * dt

        hit = False; side = None; sz = self.size

        if self.fx <= 0.0:
            self.fx = 0.0
            if self.speed_x < 0: self.speed_x = -self.speed_x
            hit = True; side = "left"
        elif self.fx + sz >= GAME_WIDTH:
            self.fx = float(GAME_WIDTH - sz)
            if self.speed_x > 0: self.speed_x = -self.speed_x
            hit = True; side = "right"

        if self.fy <= 0.0:
            self.fy = 0.0
            if self.speed_y < 0: self.speed_y = -self.speed_y
            hit = True
            if side is None: side = "top"
        elif self.fy + sz >= HEIGHT:
            self.fy = float(HEIGHT - sz)
            if self.speed_y > 0: self.speed_y = -self.speed_y
            hit = True
            if side is None: side = "bottom"

        self.rect.x = int(self.fx); self.rect.y = int(self.fy)
        self.draw_rect.x = round(self.fx); self.draw_rect.y = round(self.fy)
        self.draw_rect.width = self.draw_rect.height = self.size

        if hit:
            coins += (1 + coin_bonus_eff + wave_income_eff) * mul
            self.color = self._random_color()
            if wave_enabled_eff: self._spawn_wave(side)
            if lightning_power_eff > 0:
                payout = LIGHTNING_PAYOUT * lightning_power_eff * mul
                if len(lightning_sessions) < 5:
                    lightning_sessions.append(LightningSession(self, payout))
            if laser_power_eff > 0:
                beams_before = len(laser_beams)
                self._emit_lasers(side, dp)
                coins += (len(laser_beams) - beams_before) * 2000 * mul

        for other in bouncers:
            if other is self or other.implosion_frozen: continue
            if not self.rect.colliderect(other.rect): continue
            ox = self.rect.centerx - other.rect.centerx
            oy = self.rect.centery - other.rect.centery
            if ox == 0 and oy == 0: ox = 1
            d  = math.hypot(ox, oy); nx = ox/d; ny = oy/d
            ovx = (self.rect.width//2  + other.rect.width//2)  - abs(ox)
            ovy = (self.rect.height//2 + other.rect.height//2) - abs(oy)
            if ovx < ovy:
                push = ovx/2.0 + 1
                self.fx += nx*push;   other.fx -= nx*push
                self.speed_x, other.speed_x = other.speed_x, self.speed_x
            else:
                push = ovy/2.0 + 1
                self.fy += ny*push;   other.fy -= ny*push
                self.speed_y, other.speed_y = other.speed_y, self.speed_y
            gw = float(GAME_WIDTH); gh = float(HEIGHT)
            self.fx  = max(0.0, min(gw-self.size,  self.fx))
            self.fy  = max(0.0, min(gh-self.size,  self.fy))
            other.fx = max(0.0, min(gw-other.size, other.fx))
            other.fy = max(0.0, min(gh-other.size, other.fy))
            self.rect.x  = int(self.fx);  self.rect.y  = int(self.fy)
            other.rect.x = int(other.fx); other.rect.y = int(other.fy)
            self.draw_rect.x  = round(self.fx);  self.draw_rect.y  = round(self.fy)
            other.draw_rect.x = round(other.fx); other.draw_rect.y = round(other.fy)

        if flash_enabled_eff and now >= self.next_flash:
            coins += flash_amount_eff * mul
            self.next_flash = now + self.flash_interval
            spawn_flash_particles(self.rect.centerx, self.rect.centery, self.color)

        if trail_enabled_eff:
            # Store center position every frame; keep 60 points for longer ribbon
            cx_t = self.rect.centerx; cy_t = self.rect.centery
            if not self.trail_points or self.trail_points[-1] != (cx_t, cy_t):
                self.trail_points.append((cx_t, cy_t))
            if len(self.trail_points) > 60: self.trail_points.pop(0)
            if now - self.last_trail_income >= 1000:
                ticks = (now - self.last_trail_income) // 1000
                coins += trail_income_eff * mul * ticks
                self.last_trail_income += ticks * 1000

    def draw(self, surface):
        if self.implosion_frozen and self.implosion_enabled:
            return

        any_illum = any(b.illuminate_enabled for b in bouncers)

        if self.illuminate_enabled:
            # Visual upgrades hidden; bouncer itself is invisible (triangle takes over)
            if self.selected:
                pygame.draw.rect(surface, YELLOW, self.draw_rect, 2)
            return

        # When illuminate is active on any bouncer, shade all other bouncers (less opaque)
        if any_illum:
            shade = pygame.Surface((self.draw_rect.width, self.draw_rect.height), pygame.SRCALPHA)
            r, g, b = self.color
            dim = (max(0, r//4), max(0, g//4), max(0, b//4))
            shade.fill((*dim, 80))   # 80 alpha = subtle ghost
            surface.blit(shade, self.draw_rect.topleft)
            if self.selected:
                pygame.draw.rect(surface, (100, 100, 0), self.draw_rect, 1)
            return

        if self.trail_enabled or self.donut_upgrade_power() > 0:
            pts = self.trail_points
            if len(pts) > 1:
                dl = pygame.draw.line; dc = pygame.draw.circle; tc = TRAIL_COLORS
                for i in range(1, len(pts)):
                    col = tc[i % 40]
                    dl(surface, col, pts[i-1], pts[i], 28)
                    dc(surface, col, pts[i], 14)

        if self.implosion_enabled:
            pygame.draw.rect(surface, PURPLE, self.draw_rect.inflate(10,10), border_radius=8)

        # ── Bouncer body: rounded rect with highlight ─────────────────────
        r2 = self.draw_rect
        br  = min(10, max(1, min(r2.width, r2.height)//2))   # border radius
        pygame.draw.rect(surface, self.color, r2, border_radius=br)
        # Top highlight strip
        hr, hg, hb = self.color
        hi_col = (min(255,hr+80), min(255,hg+80), min(255,hb+80))
        hi_w = max(1, r2.width - 8)
        hi_h = max(1, r2.height // 3)
        hi_rect = pygame.Rect(r2.x + 4, r2.y + 4, hi_w, hi_h)
        if hi_rect.width > 0 and hi_rect.height > 0:
            hi_surf = pygame.Surface((hi_rect.width, hi_rect.height), pygame.SRCALPHA)
            hi_surf.fill((*hi_col, 60))
            surface.blit(hi_surf, hi_rect.topleft)
        # Dark bottom shadow strip
        sh_w = max(1, r2.width - 8)
        sh_h = max(1, r2.height // 3 - 4)
        sh_rect = pygame.Rect(r2.x + 4, r2.bottom - r2.height//3, sh_w, sh_h)
        if sh_rect.width > 0 and sh_rect.height > 0:
            sh_surf = pygame.Surface((sh_rect.width, sh_rect.height), pygame.SRCALPHA)
            sh_surf.fill((0, 0, 0, 50))
            surface.blit(sh_surf, sh_rect.topleft)
        # Label
        if r2.width >= 24 and r2.height >= 14:
            if goon_mode:
                lbl_text = "IMPLSN" if self.implosion_enabled else "GOON"
            else:
                lbl_text = "IMPLSN" if self.implosion_enabled else "BOUNCE"
            lbl = font.render(lbl_text, True, (0, 0, 0, 200))
            surface.blit(lbl, lbl.get_rect(center=r2.center))
        # Border glow when selected
        if self.selected:
            pygame.draw.rect(surface, YELLOW, r2, 3, border_radius=br)
        else:
            pygame.draw.rect(surface, (0,0,0,80), r2, 1, border_radius=br)


# ------------------ HELPERS ------------------
def reset_game():
    global coins, start_coins_override, free_shop, bouncers, selected_index, _hud_cache
    global wave_rings, laser_beams, flash_particles, explosion_particles
    global click_animations, implosion_effects, drip_particles, lightning_sessions, factories, _factory_income_timer, illuminate_effects, gravity_effects, _gravity_income_timer, mode3d_active, mode3d_effect, _3d_income_timer, shop_scroll_offset, all_goons_mode
    if cheat_mode:
        coins = DEV_COINS
    else:
        coins = start_coins_override if start_coins_override is not None else 0
    bouncers = [Bouncer(GAME_WIDTH//2, HEIGHT//2)]
    bouncers[0].selected = True
    selected_index = 0
    wave_rings.clear(); laser_beams.clear()
    flash_particles.clear(); explosion_particles.clear()
    click_animations.clear(); implosion_effects.clear()
    drip_particles.clear()
    lightning_sessions.clear()
    factories.clear()
    _factory_income_timer = 0
    illuminate_effects.clear()
    gravity_effects.clear()
    _gravity_income_timer = 0
    mode3d_active = False
    mode3d_effect = None
    _3d_income_timer = 0
    shop_scroll_offset = 0.0
    all_goons_mode = False
    _hud_cache.clear()

def total_donut_goons():
    return min(DONUT_GOON_MAX,
               sum(max(0, b.donut_ring_count) for b in bouncers if b.donut_enabled))

def total_goon_god_power():
    return sum(max(0, b.goon_god_purchases) for b in bouncers if b.goon_god_enabled)

def update_highscore():
    global highscore, _hs_dirty, _hs_save_timer
    if not cheat_mode and coins > highscore:
        highscore = coins; _hs_dirty = True
    now = pygame.time.get_ticks()
    if _hs_dirty and now - _hs_save_timer > 2000:
        save_highscore(highscore)
        _hs_dirty = False; _hs_save_timer = now

def draw_menu():
    screen.fill(DARK_BG)
    for bg in bg_bouncers: bg.update(); bg.draw(screen)

    now_t = pygame.time.get_ticks()
    update_spawn_drips(now_t)
    draw_drips(screen)

    if goon_mode:
        title_str = "GOON EMPIRE"
        shadow_col = (0, 40, 0)
        c1 = (0, 200, 80)
        c2 = (100, 255, 150)
    else:
        title_str = "BOUNCE EMPIRE"
        shadow_col = (60, 30, 0)
        c1 = ORANGE
        c2 = GOLD

    shadow = title_font.render(title_str, True, shadow_col)
    screen.blit(shadow, shadow.get_rect(center=(WIDTH//2+4, HEIGHT//2-116)))
    t1 = title_font.render(title_str, True, c1)
    t2 = title_font.render(title_str, True, c2)
    screen.blit(t1, t1.get_rect(center=(WIDTH//2, HEIGHT//2-120)))
    screen.blit(t2, t2.get_rect(center=(WIDTH//2, HEIGHT//2-122)))

    hs_surf = med_font.render(f"HIGH SCORE:  \xa3{highscore}", True, GOLD)
    screen.blit(hs_surf, hs_surf.get_rect(center=(WIDTH//2, HEIGHT//2+10)))

    btn_rect = pygame.Rect(0,0,260,70)
    btn_rect.center = (WIDTH//2, HEIGHT//2+110)
    mx, my = pygame.mouse.get_pos()
    hover  = btn_rect.collidepoint(mx, my)
    pygame.draw.rect(screen, (80,200,80) if hover else (50,150,50), btn_rect, border_radius=16)
    pygame.draw.rect(screen, GREEN, btn_rect, 3, border_radius=16)
    lbl = med_font.render("PLAY", True, BLACK)
    screen.blit(lbl, lbl.get_rect(center=btn_rect.center))

    hint = font.render("ESC to quit", True, (120,120,120))
    screen.blit(hint, (WIDTH//2 - hint.get_width()//2, HEIGHT-40))

    code_btn = pygame.Rect(WIDTH-104, HEIGHT-50, 90, 36)
    code_hover = code_btn.collidepoint(mx, my)
    pygame.draw.rect(screen, (80,80,120) if code_hover else (45,45,70), code_btn, border_radius=8)
    pygame.draw.rect(screen, (100,100,160), code_btn, 2, border_radius=8)
    ct = font.render("CODE", True, (180,180,255))
    screen.blit(ct, ct.get_rect(center=code_btn.center))

    if cheat_mode:
        screen.blit(font.render("\u2605 DEV MODE ON \u2605", True, GOLD), (14, HEIGHT-40))
    if goon_mode:
        screen.blit(font.render("\U0001f4a6 GOON MODE ON \U0001f4a6", True, (100,255,150)), (14, HEIGHT-65))

    return btn_rect, code_btn

def draw_code_screen():
    ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    ov.fill((0,0,0,170)); screen.blit(ov, (0,0))
    pw, ph = 420, 260
    panel  = pygame.Rect((WIDTH-pw)//2, (HEIGHT-ph)//2, pw, ph)
    pygame.draw.rect(screen, (30,30,50),    panel, border_radius=16)
    pygame.draw.rect(screen, (100,100,180), panel, 2, border_radius=16)
    t = big_font.render("ENTER CODE", True, WHITE)
    screen.blit(t, t.get_rect(center=(WIDTH//2, panel.y+40)))
    ibox = pygame.Rect(panel.x+40, panel.y+90, pw-80, 56)
    pygame.draw.rect(screen, (15,15,30),    ibox, border_radius=8)
    pygame.draw.rect(screen, (120,120,200), ibox, 2, border_radius=8)
    ds = "*"*len(code_input) if code_input else ""
    inp = med_font.render(ds or "____", True, (200,200,255) if code_input else (80,80,100))
    screen.blit(inp, inp.get_rect(center=ibox.center))
    now = pygame.time.get_ticks()
    if code_message and now < code_msg_timer:
        col = GOLD if code_message.startswith("\u2605") else RED
        msg = font.render(code_message, True, col)
        screen.blit(msg, msg.get_rect(center=(WIDTH//2, panel.y+170)))
    hint = font.render("ENTER to confirm  \u2022  ESC to go back", True, (100,100,130))
    screen.blit(hint, hint.get_rect(center=(WIDTH//2, panel.y+215)))


# ------------------ INIT ------------------
bouncers            = []
selected_index      = 0
_shop_header_surf   = big_font.render("BOUNCER UPGRADES", True, WHITE)
_goon_header_surf   = big_font.render("GOON UPGRADES", True, (100,255,150))
reset_game()
highscore = load_highscore()   # load after modes are defined

# ------------------ MAIN LOOP ------------------

# =============================================================================
# NEW WORLD CINEMATIC + BATHROOM WORLD  (async-safe, pygbag compatible)
# Call: await new_world_cinematic(screen, clock, WIDTH, HEIGHT, font)
# =============================================================================

def _nw_rng(seed):
    s = [seed & 0xffffffff]
    def r():
        s[0] = (s[0] * 1664525 + 1013904223) & 0xffffffff
        return s[0] / 0xffffffff
    return r

def _nw_ease_in(t):  return t * t
def _nw_ease_out(t): return 1 - (1-t)*(1-t)
def _nw_ease_io(t):
    return 2*t*t if t < 0.5 else 1 - (-2*t+2)**2/2
def _nw_clamp(v, a, b): return max(a, min(b, v))

def _nw_stars(n, rng, W, H):
    return [{"x": rng()*W, "y": rng()*H, "r": rng()*1.8+0.3,
             "br": rng()*0.7+0.3, "tw": rng()*6} for _ in range(n)]

def _nw_nebula(rng, W, H):
    return [{"x": rng()*W, "y": rng()*H,
             "rx": rng()*180+80, "ry": rng()*90+40,
             "hue": rng()*360, "al": rng()*0.08+0.03} for _ in range(12)]

def _nw_streaks(n, rng, W, H):
    out = []
    for _ in range(n):
        a = rng()*math.pi*2
        dist = rng()*0.5+0.05
        h = int(rng()*60+200) % 360
        col = pygame.Color(0)
        col.hsva = (h, 80, min(100, int(rng()*30+55)), 100)
        out.append({"angle": a, "dist": dist, "speed": rng()*3+1.5,
                    "color": (col.r, col.g, col.b)})
    return out



# NW bouncer state (persists across draws, updated by cinematic loop)

# NW bouncer state - persistent across frames
_nw_bo_x  = 300.0
_nw_bo_y  = 200.0
_nw_bo_vx = 220.0
_nw_bo_vy = 160.0
_nw_bo_r  = 32
_nw_bo_color = (200, 120, 255)   # random colour, changes on bounce
NW_GAME_W = int(1280 * (600/900))  # mirrors GAME_WIDTH

def _nw_update_bouncer(dt, floor_y, W, H):
    global _nw_bo_x, _nw_bo_y, _nw_bo_vx, _nw_bo_vy, _nw_bo_color
    r = _nw_bo_r
    _nw_bo_x += _nw_bo_vx * dt
    _nw_bo_y += _nw_bo_vy * dt
    hit = False
    if _nw_bo_x - r <= 0:
        _nw_bo_vx = abs(_nw_bo_vx); _nw_bo_x = float(r); hit = True
    if _nw_bo_x + r >= NW_GAME_W:
        _nw_bo_vx = -abs(_nw_bo_vx); _nw_bo_x = float(NW_GAME_W - r); hit = True
    ceil_y = 56
    if _nw_bo_y - r <= ceil_y:
        _nw_bo_vy = abs(_nw_bo_vy); _nw_bo_y = float(ceil_y + r); hit = True
    if _nw_bo_y + r >= floor_y - 2:
        _nw_bo_vy = -abs(_nw_bo_vy); _nw_bo_y = float(floor_y - 2 - r); hit = True
    if hit:
        _nw_bo_color = (random.randint(80,255), random.randint(80,255), random.randint(80,255))
    return int(_nw_bo_x), int(_nw_bo_y), hit


def _nw_draw_bouncer(surf, cx, cy, r, color):
    """Draw a bouncer exactly like the main-game 2D bouncer (rounded rect + label)."""
    sz = r * 2
    draw_rect = pygame.Rect(cx - r, cy - r, sz, sz)
    br = min(10, max(1, sz // 2))
    # trail / body
    pygame.draw.rect(surf, color, draw_rect, border_radius=br)
    # top highlight
    hr, hg, hb = color
    hi_col = (min(255,hr+80), min(255,hg+80), min(255,hb+80))
    hi_surf = pygame.Surface((max(1,sz-8), max(1,sz//3)), pygame.SRCALPHA)
    hi_surf.fill((*hi_col, 60))
    surf.blit(hi_surf, (cx - r + 4, cy - r + 4))
    # bottom shadow
    sh_surf = pygame.Surface((max(1,sz-8), max(1,sz//3-4)), pygame.SRCALPHA)
    sh_surf.fill((0, 0, 0, 50))
    surf.blit(sh_surf, (cx - r + 4, cy + r - sz//3))
    # label
    if sz >= 24:
        lbl = pygame.font.SysFont(None, 22).render("BOUNCE", True, (0,0,0))
        surf.blit(lbl, lbl.get_rect(center=(cx, cy)))
    # border
    pygame.draw.rect(surf, (0,0,0,80), draw_rect, 1, border_radius=br)


def _nw_draw_shop_icon(surf, act, rect, accent_col, unlocked):
    """Draw shop icon on a surface (not on screen) — mirrors draw_shop_icon logic."""
    icon_bg = pygame.Rect(rect.x + 8, rect.y + 8, 40, rect.height - 16)
    pygame.draw.rect(surf, (20,20,24) if unlocked else (35,35,40), icon_bg, border_radius=8)
    pygame.draw.rect(surf, accent_col if unlocked else (70,70,76), icon_bg, 1, border_radius=8)
    cx, cy = icon_bg.centerx, icon_bg.centery
    ic = accent_col if unlocked else (100,100,110)
    if act == "nw_speed":
        pts = [(cx-5,cy-10),(cx+1,cy-3),(cx-2,cy-3),(cx+5,cy+10),(cx-1,cy+2),(cx+2,cy+2)]
        pygame.draw.polygon(surf, ic, pts)
    elif act == "nw_size":
        pygame.draw.rect(surf, ic, (cx-8,cy-8,16,16), 2, border_radius=2)
    else:
        pygame.draw.circle(surf, ic, (cx,cy), 8, 2)


NW_SHOP_THEME = {
    "nw_speed": ((40,40,50),  (120,200,255)),
    "nw_size":  ((40,50,40),  (100,220,120)),
}
NW_SHOP_ITEMS = [
    {"name": "Speed +5%",  "base_price": 5,  "action": "nw_speed"},
    {"name": "Size  +5%",  "base_price": 8,  "action": "nw_size"},
]
_nw_shop_bought = {"nw_speed": 0, "nw_size": 0}

def _nw_shop_price(action):
    bought = _nw_shop_bought[action]
    base   = next(i["base_price"] for i in NW_SHOP_ITEMS if i["action"] == action)
    return math.ceil(base * (1.25 ** bought))

def _nw_shop_item_rects(W, H):
    """Return list of (pygame.Rect, item_dict) for hit-testing."""
    SP_X = NW_GAME_W; SP_W = W - NW_GAME_W
    ROW_H=56; ROW_G=10; TOP=42
    out = []
    for i, item in enumerate(NW_SHOP_ITEMS):
        ry = int(TOP + i*(ROW_H+ROW_G))
        out.append((pygame.Rect(SP_X+10, ry, SP_W-20, ROW_H), item))
    return out


def _nw_draw_bathroom(surf, W, H, t, nw_bounce_particles=None):
    """Bathroom world — big toilet on floor, bouncing bouncer, NW shop identical to main shop."""
    floor_y = int(H * 0.70)

    # ── Background walls gradient
    for sy in range(H):
        f = sy/H
        pygame.draw.line(surf,(int(218-f*14),int(222-f*12),int(214-f*10)),(0,sy),(W,sy))

    # ── Subway wall tiles
    TILE_W,TILE_H=60,34
    for row in range(int((floor_y-52)/TILE_H)+2):
        for col in range(int(W/TILE_W)+2):
            ox=(row%2)*(TILE_W//2); tx=col*TILE_W-ox; ty=52+row*TILE_H
            shade=(234,236,230) if (row+col)%3!=0 else (226,228,222)
            pygame.draw.rect(surf,shade,(tx+2,ty+2,TILE_W-4,TILE_H-4),border_radius=2)
            pygame.draw.rect(surf,(244,246,242),(tx+3,ty+3,TILE_W-6,6))
            pygame.draw.rect(surf,(178,180,174),(tx+2,ty+2,TILE_W-4,TILE_H-4),1,border_radius=2)

    # ── Floor tiles
    FTW,FTH=40,20
    for row in range(int((H-floor_y)/FTH)+3):
        for col in range(int(W/FTW)+3):
            tx=col*FTW+(row%2)*(FTW//2); ty=floor_y+row*FTH
            shade=(150,134,118) if (row+col)%2==0 else (138,124,108)
            pygame.draw.rect(surf,shade,(tx+1,ty+1,FTW-2,FTH-2))
            pygame.draw.rect(surf,(168,152,136),(tx+1,ty+1,FTW-2,FTH-2),1)
    refl=pygame.Surface((W,18),pygame.SRCALPHA)
    pygame.draw.rect(refl,(255,255,255,28),(0,0,W,18)); surf.blit(refl,(0,floor_y))

    # ── Baseboard
    for sy in range(floor_y,floor_y+18):
        f=(sy-floor_y)/18
        pygame.draw.line(surf,(int(212-f*28),int(210-f*26),int(202-f*24)),(0,sy),(W,sy))
    pygame.draw.rect(surf,(240,238,232),(0,floor_y+2,W,3))

    # ── Ceiling cornice
    for cy2 in range(0,52):
        f=cy2/52
        pygame.draw.line(surf,(int(248-f*20),int(248-f*18),int(244-f*16)),(0,cy2),(W,cy2))
    for ci in range(0,W,18):
        pygame.draw.arc(surf,(212,210,202),(ci,44,20,12),0,math.pi,2)
    pygame.draw.rect(surf,(202,200,194),(0,50,W,3))

    # ── Window
    wx,wy,ww,wh=W//2-85,56,170,128
    pygame.draw.rect(surf,(162,160,154),(wx-10,wy-10,ww+20,wh+20),border_radius=4)
    pygame.draw.rect(surf,(234,232,226),(wx-6,wy-6,ww+12,wh+12),border_radius=3)
    pygame.draw.rect(surf,(150,148,142),(wx-6,wy-6,ww+12,wh+12),3,border_radius=3)
    for sy in range(wh):
        f=sy/wh
        pygame.draw.line(surf,(min(255,int(118+f*60)),min(255,int(182+f*38)),min(255,int(228+f*22))),(wx,wy+sy),(wx+ww,wy+sy))
    for cxb,cyb,pts in [
        (int(wx+18+math.sin(t*0.28)*6),wy+30,[(0,0,18),(14,-4,14),(28,0,16),(44,0,14)]),
        (int(wx+76+math.sin(t*0.18+1)*4),wy+18,[(0,0,11),(12,-3,9),(22,0,11),(32,0,9)]),
    ]:
        for dx,dy,r2 in pts:
            for dr,da in [(r2+4,55),(r2,200),(r2-3,255)]:
                if dr>0:
                    gs=pygame.Surface((dr*2,dr*2),pygame.SRCALPHA)
                    pygame.draw.circle(gs,(255,255,255,da),(dr,dr),dr); surf.blit(gs,(cxb+dx-dr,cyb+dy-dr))
    pygame.draw.line(surf,(150,148,142),(wx+ww//2,wy),(wx+ww//2,wy+wh),3)
    pygame.draw.line(surf,(150,148,142),(wx,wy+wh//2),(wx+ww,wy+wh//2),3)
    pygame.draw.rect(surf,(226,224,218),(wx-8,wy+wh,ww+16,18),border_radius=2)
    px,py=wx+ww-22,wy+wh+4
    pygame.draw.polygon(surf,(158,82,42),[(px-10,py+14),(px-7,py+26),(px+7,py+26),(px+10,py+14)])
    for leaf,(ldx,ldy,lr) in enumerate([(0,-24,12),(-8,-20,10),(8,-20,10),(-4,-32,9)]):
        pygame.draw.ellipse(surf,(72+leaf*7,128+leaf*4,56+leaf*3),(px+ldx-lr//2,py+ldy-lr//2,lr,int(lr*1.4)))

    # ── Ceiling light
    lx,ly=W//2,18
    glow_r=int(115+18*math.sin(t*2.2))
    gs=pygame.Surface((glow_r*2,glow_r*2),pygame.SRCALPHA)
    for gr in range(glow_r,0,-6):
        a=int(28*(1-gr/glow_r)**0.5); pygame.draw.circle(gs,(255,250,220,min(255,a)),(glow_r,glow_r),gr)
    surf.blit(gs,(lx-glow_r,0))
    pygame.draw.line(surf,(180,170,155),(lx,0),(lx,ly+12),3)
    pygame.draw.ellipse(surf,(200,195,185),(lx-32,ly-8,64,26))
    pygame.draw.circle(surf,(255,248,200),(lx,ly+8),10)

    # ── Shower (left)
    sx,sy2,sw=38,52,148; sh=floor_y-52+16
    glass=pygame.Surface((sw,sh),pygame.SRCALPHA)
    for row in range(int(sh/22)+2):
        for col in range(int(sw/24)+2):
            tx2,ty2=col*24,row*22
            shade2=(118,170,208,78) if (row+col)%2==0 else (106,158,198,78)
            rw2=min(22,sw-tx2-1);rh2=min(20,sh-ty2-1)
            if rw2>0 and rh2>0:
                pygame.draw.rect(glass,shade2,(tx2+1,ty2+1,rw2,rh2))
                pygame.draw.rect(glass,(80,128,168,55),(tx2+1,ty2+1,rw2,rh2),1)
    surf.blit(glass,(sx,sy2)); pygame.draw.rect(surf,(88,138,172),(sx,sy2,sw,sh),3)
    tray_y=floor_y-10
    pygame.draw.rect(surf,(178,196,208),(sx,tray_y,sw,sh-(tray_y-sy2)),border_radius=3)
    pygame.draw.line(surf,(168,178,185),(sx,sy2+24),(sx+sw,sy2+24),5)
    for ri in range(8):
        pygame.draw.circle(surf,(128,152,168),(sx+10+int(ri*(sw-20)/7),sy2+24),5,2)
    cw2=int(sw*0.45); fold_s=pygame.Surface((cw2,sh-24),pygame.SRCALPHA); fw2=max(1,cw2//7)
    for fi in range(7):
        c1=(130,60,165,200) if fi%2==0 else (98,30,130,200); c2=(165,95,200,200) if fi%2==0 else (115,48,165,200)
        for px3 in range(fw2):
            ff=px3/max(1,fw2)
            col2=(int(c1[0]+(c2[0]-c1[0])*ff),int(c1[1]+(c2[1]-c1[1])*ff),int(c1[2]+(c2[2]-c1[2])*ff),200)
            pygame.draw.line(fold_s,col2,(fi*fw2+px3,0),(fi*fw2+px3,sh-24))
    surf.blit(fold_s,(sx,sy2+24))
    hx2,hy2=sx+sw-20,sy2+70
    pygame.draw.arc(surf,(140,158,172),(hx2-30,sy2+20,22,66),0,math.pi,5)
    pygame.draw.ellipse(surf,(158,175,188),(hx2-18,hy2,36,18))
    dp=(t*1.5)%1; rng_d=_nw_rng(7777)
    for d in range(14):
        dxv=int(hx2-12+rng_d()*24); dph=(dp+d*0.0714)%1
        if dph<0.88:
            dys=int(hy2+16+dph*55); a=int((0.8-dph*0.7)*255)
            ds2=pygame.Surface((5,9),pygame.SRCALPHA)
            pygame.draw.ellipse(ds2,(140,195,225,max(0,a)),(0,0,5,9)); surf.blit(ds2,(dxv-2,dys-4))

    # ── TOILET — big, base on floor_y ───────────────────────────────────
    TW=160; toi_cx=int(W*0.38)
    ped_h=38; bowl_h=64; seat_h=82; tank_h=90
    ped_bot=floor_y; ped_top=ped_bot-ped_h
    bowl_cy=ped_top-bowl_h//2+10; seat_bot=bowl_cy+24; seat_cy=seat_bot-seat_h//2
    tank_bot=seat_cy-seat_h//2-4; tank_top=tank_bot-tank_h
    # floor shadow
    shad=pygame.Surface((TW+40,22),pygame.SRCALPHA)
    pygame.draw.ellipse(shad,(0,0,0,40),(0,0,TW+40,22)); surf.blit(shad,(toi_cx-TW//2-20,floor_y-6))
    # cistern
    pygame.draw.rect(surf,(214,226,238),(toi_cx-TW//2-2,tank_top,TW+4,tank_h),border_radius=10)
    pygame.draw.rect(surf,(230,240,250),(toi_cx-TW//2+6,tank_top+6,TW-8,24),border_radius=6)
    pygame.draw.rect(surf,(155,178,196),(toi_cx-TW//2-2,tank_top,TW+4,tank_h),2,border_radius=10)
    pygame.draw.rect(surf,(162,184,200),(toi_cx+TW//2-22,tank_top+28,22,16),border_radius=5)
    # seat
    pygame.draw.ellipse(surf,(208,222,234),(toi_cx-TW//2-8,seat_cy-seat_h//2,TW+16,seat_h))
    pygame.draw.ellipse(surf,(155,178,196),(toi_cx-TW//2-8,seat_cy-seat_h//2,TW+16,seat_h),2)
    for hg in range(2):
        pygame.draw.circle(surf,(170,194,208),(toi_cx-TW//2+26+hg*(TW-36),seat_cy-seat_h//2+4),8)
    # bowl
    pygame.draw.ellipse(surf,(220,234,244),(toi_cx-TW//2+2,bowl_cy-bowl_h//2,TW-4,bowl_h))
    pygame.draw.ellipse(surf,(196,214,228),(toi_cx-TW//2+14,bowl_cy-bowl_h//2+8,TW-28,bowl_h-16))
    pygame.draw.ellipse(surf,(155,178,196),(toi_cx-TW//2+2,bowl_cy-bowl_h//2,TW-4,bowl_h),2)
    rt=(t*0.85)%1; rs2=pygame.Surface((TW-8,bowl_h-4),pygame.SRCALPHA)
    rra2=int((0.65-rt*0.5)*255); rrw2=int(52*rt*0.7+14); rrh2=int(rt*10+5)
    if rrw2>0 and rrh2>0 and rra2>0:
        pygame.draw.ellipse(rs2,(158,204,224,max(0,rra2)),((TW-8)//2-rrw2,(bowl_h-4)//2-rrh2,rrw2*2,rrh2*2),2)
    surf.blit(rs2,(toi_cx-TW//2+2,bowl_cy-bowl_h//2))
    pygame.draw.ellipse(surf,(190,210,224),(toi_cx-TW//2+22,bowl_cy-18,TW-44,36))
    # pedestal
    pygame.draw.polygon(surf,(204,220,232),
        [(toi_cx-TW//2+16,ped_top),(toi_cx-TW//2+20,ped_bot),(toi_cx+TW//2-20,ped_bot),(toi_cx+TW//2-16,ped_top)])
    pygame.draw.polygon(surf,(155,178,196),
        [(toi_cx-TW//2+16,ped_top),(toi_cx-TW//2+20,ped_bot),(toi_cx+TW//2-20,ped_bot),(toi_cx+TW//2-16,ped_top)],2)
    # loo roll + bin
    lrx2,lry2=toi_cx+TW//2+18,seat_cy
    pygame.draw.rect(surf,(158,180,192),(lrx2,lry2-6,7,50))
    pygame.draw.circle(surf,(244,236,220),(lrx2+20,lry2+18),18)
    pygame.draw.circle(surf,(196,182,150),(lrx2+20,lry2+18),18,2)
    bix2,biy2=toi_cx+TW//2+18,floor_y-54
    pygame.draw.polygon(surf,(140,162,172),[(bix2,biy2),(bix2+4,biy2+46),(bix2+32,biy2+46),(bix2+36,biy2)])
    pygame.draw.rect(surf,(158,180,188),(bix2-3,biy2-8,42,10))

    # ── Sink (right area)
    snx2,sny2=int(W*0.62),floor_y-198
    pygame.draw.rect(surf,(198,212,224),(snx2+34,sny2+72,24,floor_y-sny2-72),border_radius=4)
    pygame.draw.rect(surf,(220,234,246),(snx2,sny2,138,72),border_radius=12)
    pygame.draw.ellipse(surf,(204,220,234),(snx2+14,sny2+28,110,48))
    pygame.draw.ellipse(surf,(188,208,224),(snx2+22,sny2+36,94,36))
    pygame.draw.rect(surf,(155,182,202),(snx2,sny2,138,72),2,border_radius=12)
    cx3,cy3=snx2,sny2+72; ch2=floor_y-sny2-72
    pygame.draw.rect(surf,(204,220,232),(cx3,cy3,138,ch2),border_radius=4)
    pygame.draw.rect(surf,(142,172,192),(cx3,cy3,138,ch2),2,border_radius=4)
    mx2,my2=snx2-4,sny2-128
    pygame.draw.rect(surf,(220,238,250),(mx2,my2,148,116),border_radius=5)
    pygame.draw.rect(surf,(130,170,194),(mx2,my2,148,116),3,border_radius=5)
    sh3=pygame.Surface((148,116),pygame.SRCALPHA)
    pygame.draw.polygon(sh3,(255,255,255,32),[(12,12),(78,12),(12,66)]); surf.blit(sh3,(mx2,my2))

    # ── Bouncer trail particles
    if nw_bounce_particles:
        for p in nw_bounce_particles:
            pa=int(p[4]*255)
            if pa>0:
                ps=pygame.Surface((p[2]*2+2,p[2]*2+2),pygame.SRCALPHA)
                pygame.draw.circle(ps,(*p[5],pa),(p[2]+1,p[2]+1),p[2])
                surf.blit(ps,(int(p[0])-p[2]-1,int(p[1])-p[2]-1))

    # ── Bouncer body (exact same style as main-game 2D bouncer)
    _nw_draw_bouncer(surf, int(_nw_bo_x), int(_nw_bo_y), _nw_bo_r, _nw_bo_color)

    # ── Green coin ambient sparkles
    gc_rng=_nw_rng(int(t*4+1)&0xFFFFFF)
    for gc in range(4):
        gc_x=int(gc_rng()*NW_GAME_W*0.85+NW_GAME_W*0.05); gc_y=int(gc_rng()*floor_y*0.8+floor_y*0.1)
        gc_pulse=0.5+0.5*math.sin(t*2.2+gc*1.3); gc_a=int(75+55*gc_pulse)
        gc_s=pygame.Surface((20,20),pygame.SRCALPHA)
        pygame.draw.circle(gc_s,(60,220,80,gc_a),(10,10),int(6+3*gc_pulse))
        pygame.draw.circle(gc_s,(160,255,140,min(255,gc_a+80)),(10,10),int(3+gc_pulse),1)
        surf.blit(gc_s,(gc_x-10,gc_y-10))

    # ── LEFT HUD: green coin counter (mirrors main-game £ display)
    gc_big_f=pygame.font.SysFont(None,44)
    pygame.draw.circle(surf,(50,200,70),(24,22),12)
    pygame.draw.circle(surf,(120,255,140),(24,22),9,2)
    gc_surf=gc_big_f.render(fmt_nw_coins(green_coins),True,(80,240,110))
    surf.blit(gc_surf,(42,10))
    gc_lf=pygame.font.SysFont(None,22)
    surf.blit(gc_lf.render("GREEN COINS",True,(60,170,80)),(14,44))

    # ── RIGHT PANEL: shop — IDENTICAL layout/style to main-world shop ───
    SP_X=NW_GAME_W; SP_W=W-NW_GAME_W
    ROW_H=56; ROW_G=10; TOP=42
    shop_t=t

    # Shop header bar (matches main game's shop header)
    pygame.draw.rect(surf,(20,20,24),(SP_X,0,SP_W,TOP))
    hdr_f=pygame.font.SysFont(None,28)
    hdr_s=hdr_f.render("NW UPGRADES",True,(80,230,100))
    surf.blit(hdr_s,hdr_s.get_rect(center=(SP_X+SP_W//2,TOP//2)))

    for i,item in enumerate(NW_SHOP_ITEMS):
        act=item["action"]
        theme=NW_SHOP_THEME.get(act,((50,50,50),(200,200,200)))
        bg_col,accent_col=theme[0],theme[1]
        price=_nw_shop_price(act)
        bought=_nw_shop_bought[act]
        can=(green_coins>=price)

        ry=int(TOP+i*(ROW_H+ROW_G))
        rect=pygame.Rect(SP_X+10,ry,SP_W-20,ROW_H)

        # background (same as main shop)
        bg=bg_col if can else (30,30,34)
        pygame.draw.rect(surf,bg,rect,border_radius=7)

        # animated accent border when affordable
        if can:
            ba=int(160+80*math.sin(shop_t*2.0+i*0.7))
            bc=tuple(min(255,int(c*ba/240)) for c in accent_col)
            pygame.draw.rect(surf,bc,rect,1,border_radius=7)
        else:
            pygame.draw.rect(surf,(55,55,60),rect,1,border_radius=7)

        # left accent stripe
        stripe=pygame.Rect(rect.x,rect.y+5,4,rect.height-10)
        pygame.draw.rect(surf,accent_col if can else (60,60,65),stripe,border_radius=2)

        # icon
        _nw_draw_shop_icon(surf,act,rect,accent_col,can)

        # name text (left)
        tc=(230,230,235) if can else (90,90,100)
        name_txt=f"{item['name']} x{bought}"
        ns=pygame.font.SysFont(None,26).render(name_txt,True,tc)
        surf.blit(ns,(rect.x+56,rect.y+10))

        # price text (right, coloured green/red)
        pp=fmt_nw_coins(price)
        pc=(80,255,120) if (cheat_mode or can) else (255,80,80)
        ps_surf=pygame.font.SysFont(None,24).render(pp,True,pc)
        surf.blit(ps_surf,(rect.right-ps_surf.get_width()-8,rect.y+30))

    # ── NEW WORLD watermark
    la2=int((0.16+0.06*math.sin(t*1.5))*255)
    fn_nw=pygame.font.SysFont("Georgia",54,bold=True)
    lb_nw=fn_nw.render("NEW WORLD",True,(255,255,255))
    lb_nw.set_alpha(la2)
    surf.blit(lb_nw,lb_nw.get_rect(center=(NW_GAME_W//2,H-30)))


def fmt_nw_coins(c):
    if c>=1_000_000_000: return f"G{c/1_000_000_000:.1f}B"
    if c>=1_000_000:     return f"G{c/1_000_000:.1f}M"
    if c>=1_000:         return f"G{c/1_000:.1f}K"
    return f"G{int(c)}"


async def new_world_cinematic(screen, clock, W, H, font):
    """
    Full 5-phase cinematic then bathroom world.
    async so it yields every frame -- works with pygbag (asyncio event loop).
    ESC returns to game.
    """
    global green_coins
    PHASE_DUR = [3200, 3500, 2800, 4000, 2600]

    ra = _nw_rng(42); rb = _nw_rng(99); rc = _nw_rng(17)
    stars   = _nw_stars(280, ra, W, H)
    nebula  = _nw_nebula(rb, W, H)
    streaks = _nw_streaks(150, rc, W, H)

    # pre-bake nebula glow surfaces
    neb_surfs = []
    for n in nebula:
        rx, ry = int(n["rx"]), int(n["ry"])
        ns = pygame.Surface((rx*2, ry*2), pygame.SRCALPHA)
        col = pygame.Color(0)
        col.hsva = (int(n["hue"])%360, 60, 40, 100)
        for step in range(10):
            f = 1 - step/10
            r2 = max(1,int(rx*f)); r3 = max(1,int(ry*f))
            a = int(n["al"]*255*(1-f)*4)
            pygame.draw.ellipse(ns,(col.r,col.g,col.b,min(255,a)),(rx-r2,ry-r3,r2*2,r3*2))
        neb_surfs.append((ns, int(n["x"]-rx), int(n["y"]-ry)))

    phase = 0; phase_ms = 0; global_ms = 0; in_bath = False
    GBW = int(W*(600/900)) if W >= 900 else W*2//3
    PL = ["ZOOM OUT","HYPERSPACE","ZOOM IN","PULSAR","ENTERING","BATHROOM WORLD"]
    PC = [(136,170,255),(255,204,68),(170,221,255),(255,255,255),(136,255,204),(200,232,168)]

    def draw_stars(surf, bm=1.0, tt=0.0):
        for st in stars:
            b = _nw_clamp(st["br"]*bm*(0.7+0.3*math.sin(tt+st["tw"])),0,1)
            pygame.draw.circle(surf,(int(255*b),int(255*b),int(255*b)),
                               (int(st["x"]),int(st["y"])),max(1,int(st["r"])))

    def draw_hud(surf):
        if in_bath: return
        x0 = 10
        for i,(l,pc) in enumerate(zip(PL[:6],PC[:6])):
            active = (i == min(phase,5))
            col = pc if active else (48,56,64)
            pygame.draw.rect(surf,col,(x0,H-28,94,22),1,border_radius=4)
            if active:
                bg_s = pygame.Surface((94,22),pygame.SRCALPHA)
                pygame.draw.rect(bg_s, (*col,40), (0,0,94,22), border_radius=4)
                surf.blit(bg_s,(x0,H-28))
            ls=font.render(l,True,col); surf.blit(ls,ls.get_rect(center=(x0+47,H-17)))
            x0 += 100

    def p0(surf, pt, gt):
        prog = pt/PHASE_DUR[0]
        fp = _nw_clamp(pt/400,0,1)
        fv = 1.0 if fp<0.5 else _nw_ease_out((1-fp)*2)
        sf = _nw_ease_in(prog)
        surf.fill((5,6,15))
        for ns2,bx,by in neb_surfs:
            tmp=ns2.copy(); tmp.set_alpha(int(sf*180)); surf.blit(tmp,(bx,by))
        draw_stars(surf, sf*(0.7+0.3*math.sin(gt/1000)), gt/1000)
        shrink = 1 - _nw_ease_io(prog)*0.88
        bw=int(GBW*shrink); bh=int(H*shrink)
        bx=W//2-bw//2; by=H//2-bh//2
        if bw>4 and bh>4:
            bs=pygame.Surface((bw,bh),pygame.SRCALPHA)
            bs.fill((10,12,40,int(230*shrink))); surf.blit(bs,(bx,by))
            pygame.draw.rect(surf,(int(80*shrink),int(100*shrink),int(220*shrink)),(bx,by,bw,bh),max(1,int(2*shrink)))
            if bw>80:
                fn2=pygame.font.SysFont("Courier New",max(10,int(22*shrink)),bold=True)
                t2=fn2.render("BOUNCE EMPIRE",True,(int(128*shrink),int(160*shrink),255))
                t2.set_alpha(int(shrink*255)); surf.blit(t2,t2.get_rect(center=(W//2,H//2)))
        if fv>0.01:
            fl=pygame.Surface((W,H)); fl.fill((255,255,255)); fl.set_alpha(int(fv*255)); surf.blit(fl,(0,0))

    def p1(surf, pt, gt):
        prog = pt/PHASE_DUR[1]
        surf.fill((2,3,10))
        sp = 0.3+_nw_ease_in(prog)*0.7
        bl = int(18+sp*280)
        for st in streaks:
            sx=int(W//2+math.cos(st["angle"])*st["dist"]*W*0.5)
            sy=int(H//2+math.sin(st["angle"])*st["dist"]*H*0.5)
            ex=int(sx+math.cos(st["angle"])*bl*st["speed"])
            ey=int(sy+math.sin(st["angle"])*bl*st["speed"])
            pygame.draw.line(surf,st["color"],(sx,sy),(ex,ey),max(1,int(0.8+sp)))
        da=_nw_ease_in(prog); dr=int(8+prog*60)
        for r in range(dr*3,0,-4):
            a=int(da*(1-r/(dr*3))*100)
            if a>0: pygame.draw.circle(surf,(200,220,255),(W//2,H//2),r,min(r,max(1,4)))
        la=int(math.sin(prog*math.pi)*200)
        if la>0:
            l=font.render("HYPERSPACE ENGAGED",True,(160,180,255)); l.set_alpha(la)
            surf.blit(l,l.get_rect(center=(W//2,int(H*0.88))))

    def p2(surf, pt, gt):
        prog = pt/PHASE_DUR[2]
        surf.fill((2,3,10))
        for st in stars:
            zp=1+_nw_ease_in(prog)*8
            sx=int(W//2+(st["x"]-W//2)*zp); sy=int(H//2+(st["y"]-H//2)*zp)
            if 0<=sx<W and 0<=sy<H:
                b=st["br"]*(0.5+prog*0.5)
                pygame.draw.circle(surf,(int(255*b),int(255*b),int(255*b)),
                                   (sx,sy),max(1,int(st["r"]*(1+prog))))
        pa=_nw_ease_out(prog); pr=int(prog*80)
        for r in range(pr+50,0,-5):
            a=int(pa*(1-r/(pr+50))*200)
            rc=int(180+(255-180)*(1-r/(pr+50)))
            if a>0: pygame.draw.circle(surf,(rc,min(255,rc+10),255),(W//2,H//2),r,min(r,max(1,5)))
        if pr>0: pygame.draw.circle(surf,(255,255,255),(W//2,H//2),max(1,int(pr*0.2)))

    def p3(surf, pt, gt):
        prog=pt/PHASE_DUR[3]; t3=gt/1000.0
        surf.fill((2,3,10))
        draw_stars(surf,0.35)
        for ri in range(5):
            rp=(prog*2+ri/5)%1; rr=int(rp*W*0.65); ra=int((1-rp)*100)
            if rr>0 and ra>0:
                _w=max(1,int(2+rp*4)); pygame.draw.circle(surf,(200,230,255),(W//2,H//2),rr,min(rr,_w))
        ba=t3*1.4
        for bi in range(12):
            a=ba+bi*math.pi*2/12
            bl=int(260+30*math.sin(t3*2.5+bi))
            ex=int(W//2+math.cos(a)*bl); ey=int(H//2+math.sin(a)*bl)
            br=0.6+0.35*math.sin(t3*3+bi*0.7)
            pygame.draw.line(surf,(int(255*br*0.9),int(210*br*0.7),255),
                             (W//2,H//2),(ex,ey),max(1,int(2.5+math.sin(t3+bi))))
        cr=int(28+8*math.sin(t3*4))
        for r in range(cr*3,0,-3):
            f=1-r/(cr*3)
            pygame.draw.circle(surf,(int(100+155*f),int(160+95*f),255),(W//2,H//2),max(1,r),min(max(1,r),max(1,3)))
        pygame.draw.circle(surf,(255,255,255),(W//2,H//2),max(1,int(cr*0.35)))
        ba2=_nw_ease_out(max(0,(prog-0.4)*1.67))
        if ba2>0.01:
            bw,bh=260,160; bx,by=W//2-130,H//2-40
            bs=pygame.Surface((bw,bh),pygame.SRCALPHA)
            bs.fill((10,20,60,int(ba2*220))); surf.blit(bs,(bx,by))
            pygame.draw.rect(surf,(int(160*ba2),int(220*ba2),255),(bx,by,bw,bh),2,border_radius=10)
            fn2=pygame.font.SysFont("Courier New",22,bold=True)
            t2=fn2.render("NEW WORLD",True,(int(160*ba2),int(216*ba2),255))
            t2b=font.render("DIMENSIONAL RIFT LOCATED",True,(int(80*ba2),int(144*ba2),int(184*ba2)))
            t2c=font.render("ENTERING...",True,(int(80*ba2),int(144*ba2),int(184*ba2)))
            surf.blit(t2,t2.get_rect(center=(W//2,by+52)))
            surf.blit(t2b,t2b.get_rect(center=(W//2,by+84)))
            surf.blit(t2c,t2c.get_rect(center=(W//2,by+106)))

    def p4(surf, pt, gt):
        prog=_nw_ease_io(pt/PHASE_DUR[4]); t4=gt/1000.0
        surf.fill((2,3,10))
        if prog<0.5:
            for st in stars:
                b=st["br"]*(1-prog*2)*0.5
                if b>0:
                    pygame.draw.circle(surf,(int(255*b),int(255*b),int(255*b)),
                                       (int(st["x"]),int(st["y"])),max(1,int(st["r"])))
        sc=0.3+prog*0.8; bw=int(W*sc*0.58); bh=int(H*sc*0.58)
        bx=W//2-bw//2; by=H//2-bh//2
        if prog<0.85 and bw>4 and bh>4:
            bs=pygame.Surface((bw,bh),pygame.SRCALPHA)
            bs.fill((8,18,50,int((0.9-prog*0.9)*220))); surf.blit(bs,(bx,by))
            pygame.draw.rect(surf,(int(100*(1-prog)),int(200*(1-prog)),255),(bx,by,bw,bh),2,border_radius=10)
            fn2=pygame.font.SysFont("Courier New",max(10,int(16+prog*10)),bold=True)
            t2=fn2.render("NEW WORLD",True,(int(160*(1-prog)),int(220*(1-prog)),255))
            surf.blit(t2,t2.get_rect(center=(W//2,H//2)))
        if prog>0.5:
            ba=(prog-0.5)*2
            bath=pygame.Surface((W,H)); _nw_draw_bathroom(bath,W,H,t4)
            cr=max(1,int((1-prog)*W*0.6+W*prog))
            mask=pygame.Surface((W,H),pygame.SRCALPHA)
            pygame.draw.circle(mask,(255,255,255,int(ba*255)),(W//2,H//2),cr)
            bath.blit(mask,(0,0),special_flags=pygame.BLEND_RGBA_MIN)
            surf.blit(bath,(0,0))
        if prog>0.92:
            fa=(prog-0.92)/0.08
            fl=pygame.Surface((W,H)); fl.fill((255,255,255)); fl.set_alpha(int(fa*150)); surf.blit(fl,(0,0))

    # ── Green coin income: 1 per wall bounce ──
    # (tracked via hit_wall flag in physics update)

    # ── Bouncer trail particles: [x, y, r, alpha_f, decay, (r,g,b)] ──
    nw_bounce_particles = []

    # ── main async loop ──
    while True:
        dt = min(clock.tick(60), 50) / 1000.0   # seconds
        global_ms += int(dt * 1000)
        now_ms = pygame.time.get_ticks()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and in_bath:
                mx2, my2 = event.pos
                shop_items = _nw_shop_item_rects(W, H)
                for item_rect, item in shop_items:
                    act = item["action"]
                    price = _nw_shop_price(act)
                    if item_rect.collidepoint(mx2, my2) and green_coins >= price:
                        green_coins -= price
                        _nw_shop_bought[act] += 1
                        if act == "nw_speed":
                            _nw_bo_vx *= 1.05; _nw_bo_vy *= 1.05
                        elif act == "nw_size":
                            global _nw_bo_r
                            _nw_bo_r = min(64, int(_nw_bo_r * 1.05))
                        break

        if not in_bath:
            phase_ms += int(dt * 1000)
            if phase_ms >= PHASE_DUR[phase]:
                phase_ms -= PHASE_DUR[phase]; phase += 1
                if phase >= 5:
                    in_bath = True

        if in_bath:
            t_bath = global_ms / 1000.0
            floor_y_nw = int(H * 0.70)

            # Physics update — earn 1 green coin per wall hit
            bo_cx_i, bo_cy_i, hit_wall = _nw_update_bouncer(dt, floor_y_nw, W, H)
            if hit_wall:
                green_coins += 1

            # Spawn trail + burst particles
            col_trail = _nw_bo_color
            nw_bounce_particles.append([float(bo_cx_i), float(bo_cy_i), max(2,_nw_bo_r//3), 0.6, 0.05, col_trail])
            if hit_wall:
                for _ in range(10):
                    nw_bounce_particles.append([float(bo_cx_i), float(bo_cy_i),
                        random.randint(4,10), 1.0, random.uniform(0.07,0.14), col_trail])

            # Update + cull particles
            i2 = 0
            while i2 < len(nw_bounce_particles):
                p = nw_bounce_particles[i2]
                p[3] -= p[4]
                if p[3] <= 0:
                    nw_bounce_particles[i2] = nw_bounce_particles[-1]; nw_bounce_particles.pop()
                else:
                    i2 += 1

            _nw_draw_bathroom(screen, W, H, t_bath, nw_bounce_particles)
            el = font.render("ESC = Return to Game", True, (90, 140, 100))
            screen.blit(el, (16, H - 28))
        else:
            gt = global_ms
            if   phase==0: p0(screen,phase_ms,gt)
            elif phase==1: p1(screen,phase_ms,gt)
            elif phase==2: p2(screen,phase_ms,gt)
            elif phase==3: p3(screen,phase_ms,gt)
            elif phase==4: p4(screen,phase_ms,gt)
            draw_hud(screen)

        pygame.display.flip()
        await asyncio.sleep(0)   # yield to pygbag event loop every frame

# ============= END NEW WORLD MODULE ==========================================

async def main():
    global state, code_input, code_message, code_msg_timer
    global cheat_mode, goon_mode, highscore, coins
    global shop_scroll_offset, selected_index, mode3d_active, mode3d_effect
    global start_coins_override
    global free_shop
    global all_goons_mode

    while True:
        raw_ms = clock.tick(60)
        dt     = min(raw_ms / 1000.0, 0.05)
        mx, my = pygame.mouse.get_pos()

        # ========== MENU ==========
        if state == STATE_MENU:
            btn_rect, code_btn = draw_menu()
            for event in pygame.event.get():
                if event.type == pygame.QUIT: pygame.quit(); sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE: pygame.quit(); sys.exit()
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        reset_game(); state = STATE_GAME
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if btn_rect.collidepoint(mx, my):
                        reset_game(); state = STATE_GAME
                    elif code_btn.collidepoint(mx, my):
                        state = STATE_CODE; code_input = ""; code_message = ""
            pygame.display.flip()

        # ========== CODE ENTRY ==========
        elif state == STATE_CODE:
            btn_rect, code_btn = draw_menu()
            draw_code_screen()
            for event in pygame.event.get():
                if event.type == pygame.QUIT: pygame.quit(); sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        state = STATE_MENU
                    elif event.key == pygame.K_BACKSPACE:
                        code_input = code_input[:-1]
                    elif event.key == pygame.K_RETURN:
                        if code_input == "1234":
                            cheat_mode = not cheat_mode
                            if cheat_mode:
                                start_coins_override = None
                                free_shop = False
                            code_message = "\u2605 DEV MODE ACTIVATED \u2605" if cheat_mode else "\u2605 DEV MODE DEACTIVATED \u2605"
                            highscore = load_highscore()
                            _hud_cache.clear()
                            code_msg_timer = pygame.time.get_ticks() + 1800
                            pygame.display.flip(); pygame.time.wait(1800)
                            state = STATE_MENU; code_input = ""
                        elif code_input == "1111":
                            cheat_mode = False
                            goon_mode = False
                            start_coins_override = None
                            free_shop = True
                            coins = 0
                            for b in bouncers:
                                b.sync_shop_data()
                            drip_particles.clear()
                            _hud_cache.clear()
                            code_message = "\u2605 NORMAL MODE: FREE SHOP \u2605"
                            highscore = load_highscore()
                            code_msg_timer = pygame.time.get_ticks() + 1800
                            pygame.display.flip(); pygame.time.wait(1800)
                            state = STATE_MENU; code_input = ""
                        elif code_input == "6969":
                            goon_mode = not goon_mode
                            start_coins_override = None
                            free_shop = False
                            for b in bouncers:
                                b.sync_shop_data()
                            drip_particles.clear()
                            _hud_cache.clear()
                            code_message = "\U0001f4a6 GOON MODE ACTIVATED \U0001f4a6" if goon_mode else "\U0001f4a6 GOON MODE DEACTIVATED \U0001f4a6"
                            highscore = load_highscore()
                            code_msg_timer = pygame.time.get_ticks() + 1800
                            pygame.display.flip(); pygame.time.wait(1800)
                            state = STATE_MENU; code_input = ""
                        else:
                            code_message   = "WRONG CODE"
                            code_msg_timer = pygame.time.get_ticks() + 1200
                            code_input     = ""
                    elif event.unicode and event.unicode.isprintable() and len(code_input) < 8:
                        code_input += event.unicode
            pygame.display.flip()

        # ========== GAME ==========
        else:
            screen.fill(DARK_BG)
            now_g = pygame.time.get_ticks()
            if not mode3d_active:
                update_spawn_drips(now_g)
                draw_drips(screen)
            selected_bouncer = bouncers[selected_index]
            selected_bouncer.sync_shop_data()
            shop_scroll_offset = max(0.0, min(shop_scroll_offset, shop_max_scroll(len(selected_bouncer.shop_data))))

            for event in pygame.event.get():
                if event.type == pygame.QUIT: pygame.quit(); sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        update_highscore(); state = STATE_MENU

                if event.type == pygame.MOUSEWHEEL and mx >= GAME_WIDTH:
                    max_sc = shop_max_scroll(len(selected_bouncer.shop_data))
                    shop_scroll_offset = max(0.0, min(max_sc, shop_scroll_offset - event.y * 48.0))

                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button in (4, 5):
                        if mx >= GAME_WIDTH:
                            max_sc = shop_max_scroll(len(selected_bouncer.shop_data))
                            step = -48.0 if event.button == 4 else 48.0
                            shop_scroll_offset = max(0.0, min(max_sc, shop_scroll_offset + step))
                        continue
                    if event.button != 1:
                        continue
                    tab_rect, left_btn, right_btn, all_btn = shop_nav_rects()
                    if left_btn.collidepoint(mx, my):
                        all_goons_mode = False
                        select_bouncer(selected_index - 1)
                        continue
                    if right_btn.collidepoint(mx, my):
                        all_goons_mode = False
                        select_bouncer(selected_index + 1)
                        continue
                    if all_btn.collidepoint(mx, my):
                        all_goons_mode = not all_goons_mode
                        shop_scroll_offset = 0.0
                        continue
                    # Determine which shop list to use
                    if all_goons_mode and len(bouncers) > 1:
                        active_shop_items = all_goons_shop_data()
                    else:
                        active_shop_items = selected_bouncer.shop_data

                    for i, item in enumerate(active_shop_items):
                        row_rect = shop_item_rect(i, shop_scroll_offset)
                        if row_rect.bottom < SHOP_PANEL_TOP or row_rect.top > HEIGHT: continue
                        if not row_rect.collidepoint(mx, my): continue
                        if all_goons_mode and len(bouncers) > 1:
                            if not all_goons_is_unlocked(i): continue
                        else:
                            if not selected_bouncer.is_unlocked(i): continue
                        act = item["action"]
                        if act == "size" and item["bought"] >= 25: continue
                        if act == "donut" and total_donut_goons() >= DONUT_GOON_MAX: continue
                        if act == "bonus" and len(bouncers) >= 20: continue
                        if not cheat_mode and not free_shop and coins < item["price"]: continue
                        if not cheat_mode and not free_shop: coins -= item["price"]
                        click_animations.append({"rect": row_rect.copy(), "time": pygame.time.get_ticks()})

                        if all_goons_mode and len(bouncers) > 1:
                            # Apply upgrade to ALL bouncers
                            targets = list(bouncers)
                        else:
                            targets = [selected_bouncer]

                        for target_b in targets:
                          if i >= len(target_b.shop_data): continue
                          t_item = target_b.shop_data[i]
                          t_item["bought"] += 1
                          target_b.increase_price(t_item)
                          act = t_item["action"]
                          if act == "speed":
                            speed_item = next(it for it in target_b.shop_data if it["action"]=="speed")
                            if speed_item["bought"] <= 25:
                                MAX_SPEED = 2500.0
                                nx = target_b.speed_x * 1.05
                                ny = target_b.speed_y * 1.05
                                spd = math.hypot(nx, ny)
                                if spd > MAX_SPEED:
                                    scale = MAX_SPEED / spd
                                    nx *= scale; ny *= scale
                                target_b.speed_x = nx
                                target_b.speed_y = ny
                          elif act == "size":
                            ccx = target_b.rect.centerx; ccy = target_b.rect.centery
                            target_b.size = int(target_b.size * 1.05)
                            target_b.rect.width = target_b.rect.height = target_b.size
                            target_b.rect.center = (ccx, ccy)
                            target_b.draw_rect.width = target_b.draw_rect.height = target_b.size
                            target_b.draw_rect.center = (ccx, ccy)
                            target_b.fx = float(target_b.rect.x)
                            target_b.fy = float(target_b.rect.y)
                          elif act == "flash":
                            target_b.flashing = True
                            target_b.flash_purchases += 1
                            target_b.flash_interval = 5000 // target_b.flash_purchases
                            target_b.color = target_b._random_color()
                          elif act == "bonus":
                            if len(bouncers) < 20:
                                bouncers.append(Bouncer(GAME_WIDTH//3, HEIGHT//3))
                          elif act == "jew":
                            target_b.coin_bonus += 1
                          elif act == "wave":
                            target_b.waves_enabled = True
                            target_b.wave_income  += 100
                          elif act == "laser":
                            target_b.laser_enabled   = True
                            target_b.laser_purchases += 1
                          elif act == "trail":
                            target_b.trail_enabled = True
                            target_b.trail_income  += 5
                          elif act == "implosion":
                            if not target_b.implosion_enabled:
                                target_b.implosion_enabled = True
                                implosion_effects.append(ImplosionEffect(target_b))
                          elif act == "lightning":
                            target_b.lightning_enabled = True
                            target_b.lightning_purchases += 1
                          elif act == "factory":
                            n = len(factories) + 1
                            new_factories = []
                            for fi in range(n):
                                fx2 = int(GAME_WIDTH * (fi + 1) / (n + 1))
                                new_factories.append(Factory(fx2))
                            factories.clear()
                            factories.extend(new_factories)
                          elif act == "illuminate":
                            target_b.illuminate_enabled = True
                            n = sum(1 for b in bouncers if b.illuminate_enabled)
                            illuminate_effects.clear()
                            for ei in range(n):
                                eff = IlluminateEffect()
                                eff.cx = int(GAME_WIDTH * (ei + 1) / (n + 1))
                                eff.cy = HEIGHT // 2
                                illuminate_effects.append(eff)
                          elif act == "gravity":
                            target_b.gravity_enabled = True
                            target_b.gravity_purchases += 1
                            existing = [e for e in gravity_effects if e.bouncer is target_b]
                            if not existing:
                                gravity_effects.append(GravityWellEffect(target_b))
                          elif act == "mode3d":
                            target_b.mode3d_enabled = True
                            mode3d_active = True
                            mode3d_effect = Mode3DEffect()
                          elif act == "donut":
                            target_b.donut_enabled = True
                            target_b.donut_ring_count += 1
                          elif act == "goongod":
                            target_b.goon_god_enabled = True
                            target_b.goon_god_purchases += 1
                          elif act == "newworld":
                            await new_world_cinematic(screen, clock, WIDTH, HEIGHT, font)

                    for i, b in enumerate(bouncers):
                        if b.rect.collidepoint(mx, my):
                            select_bouncer(i)

            update_highscore()
            if cheat_mode: coins = DEV_COINS

            for eff in implosion_effects: eff.update()
            for b in bouncers: b.move(dt)
            update_mode3d(dt, now_g)

            if mode3d_active:
                # 3D mode draws its own complete world — skip all 2D drawing.
                # Physics still run above for coin/income correctness.
                # Illuminate/factory/gravity income runs inside their own update() calls.
                for eff in illuminate_effects: eff.update()
                update_factories(dt, now_g)
                update_gravity_wells(dt, now_g)
                # Wave/laser/lightning still need to update (income triggers)
                for ring in wave_rings:   ring.update()
                wave_rings[:] = [r for r in wave_rings if r.alive]
                for beam in laser_beams:  beam.update()
                laser_beams[:] = [b for b in laser_beams if b.alive]
                if len(laser_beams) > LASER_MAX_ACTIVE_BEAMS:
                    del laser_beams[:-LASER_MAX_ACTIVE_BEAMS]
                for ls in lightning_sessions: ls.update()
                lightning_sessions[:] = [ls for ls in lightning_sessions if ls.alive]
                draw_mode3d_post(screen)
            else:
                for eff in implosion_effects: eff.draw(screen)
                for b in bouncers: b.draw(screen)
                for eff in implosion_effects: eff.draw_cooldown_hud(screen)

                update_draw_particles(flash_particles,     screen, False)
                update_draw_particles(explosion_particles, screen, True)

                for ring in wave_rings:   ring.update(); ring.draw(screen)
                wave_rings[:]  = [r for r in wave_rings  if r.alive]

                for beam in laser_beams:  beam.update()
                laser_beams[:] = [b for b in laser_beams if b.alive]
                if len(laser_beams) > LASER_MAX_ACTIVE_BEAMS:
                    del laser_beams[:-LASER_MAX_ACTIVE_BEAMS]
                for beam in laser_beams:  beam.draw(screen)

                update_factories(dt, now_g)
                draw_factories(screen, now_g)

                for ls in lightning_sessions: ls.update(); ls.draw(screen)
                lightning_sessions[:] = [ls for ls in lightning_sessions if ls.alive]

                for eff in illuminate_effects: eff.update(); eff.draw(screen)

                update_gravity_wells(dt, now_g)
                draw_gravity_wells(screen, now_g)

            # ---- SHOP PANEL ----
            # Background gradient: dark left edge, slightly lighter right
            pygame.draw.rect(screen, (28, 28, 32), (GAME_WIDTH, 0, SHOP_WIDTH, HEIGHT))
            # Subtle left-edge separator line
            pygame.draw.line(screen, (80, 60, 120), (GAME_WIDTH, 0), (GAME_WIDTH, HEIGHT), 2)

            tab_rect, left_btn, right_btn, all_btn = shop_nav_rects()
            pygame.draw.rect(screen, (24, 24, 30), tab_rect, border_radius=8)
            pygame.draw.rect(screen, (90, 90, 110), tab_rect, 1, border_radius=8)

            hover_left = left_btn.collidepoint(mx, my)
            hover_right = right_btn.collidepoint(mx, my)
            hover_all = all_btn.collidepoint(mx, my)
            btn_col = (120, 180, 120) if hover_left else (70, 120, 70)
            pygame.draw.rect(screen, btn_col, left_btn, border_radius=6)
            pygame.draw.rect(screen, (30, 50, 30), left_btn, 1, border_radius=6)

            btn_col = (120, 180, 120) if hover_right else (70, 120, 70)
            pygame.draw.rect(screen, btn_col, right_btn, border_radius=6)
            pygame.draw.rect(screen, (30, 50, 30), right_btn, 1, border_radius=6)

            # ALL button — glows gold when active
            all_active_col  = (200, 160, 20) if all_goons_mode else ((160, 140, 60) if hover_all else (80, 70, 30))
            all_border_col  = (255, 215, 0)  if all_goons_mode else (120, 110, 50)
            pygame.draw.rect(screen, all_active_col, all_btn, border_radius=5)
            pygame.draw.rect(screen, all_border_col, all_btn, 1, border_radius=5)
            all_lbl = pygame.font.SysFont(None, 18).render("ALL", True, (255, 255, 180) if all_goons_mode else (200, 190, 140))
            screen.blit(all_lbl, all_lbl.get_rect(center=all_btn.center))

            # Arrow glyphs
            lc = left_btn.center
            pygame.draw.polygon(screen, (10, 20, 10),
                                [(lc[0] + 4, lc[1] - 6), (lc[0] + 4, lc[1] + 6), (lc[0] - 4, lc[1])])
            rc = right_btn.center
            pygame.draw.polygon(screen, (10, 20, 10),
                                [(rc[0] - 4, rc[1] - 6), (rc[0] - 4, rc[1] + 6), (rc[0] + 4, rc[1])])

            label_prefix = "GOON" if goon_mode else "BOUNCER"
            if all_goons_mode and len(bouncers) > 1:
                label = f"ALL {len(bouncers)} {label_prefix}S"
            else:
                label = f"{label_prefix} {selected_index+1}/{max(1,len(bouncers))}"
            lbl = font.render(label, True, (255, 215, 0) if all_goons_mode else (200, 200, 220))
            screen.blit(lbl, lbl.get_rect(center=(tab_rect.centerx - 12, tab_rect.centery)))

            now = pygame.time.get_ticks()
            shop_t = now / 1000.0

            # Colour palette per action
            SHOP_THEME = {
                "speed":     ((40,40,50),    (120,200,255), "⚡"),
                "size":      ((40,50,40),    (100,220,120), "⬛"),
                "jew":       ((50,45,20),    (255,215,0),   "🪙"),
                "flash":     ((50,40,50),    (220,120,255), "✦"),
                "trail":     ((25,45,55),    (80,220,200),  "〰"),
                "bonus":     ((50,40,30),    (255,160,60),  "＋"),
                "wave":      ((25,40,60),    (60,160,255),  "〜"),
                "laser":     ((55,25,25),    (255,80,60),   "⊛"),
                "implosion": ((40,20,55),    (180,60,255),  "◎"),
                "lightning": ((20,20,50),    (120,140,255), "⌁"),
                "factory":   ((20,40,20),    (60,210,100),  "⚙"),
                "illuminate":((45,30,5),     (255,200,40),  "△"),
                "gravity":   ((30,10,50),    (200,80,255),  "◉"),
                "mode3d":    ((10,20,50),    (80,200,255),  "■"),
                "donut":     ((15,45,35),    (100,255,180), "◌"),
                "goongod":   ((32,32,44),    (235,235,255), "⚡"),
                "newworld":  ((8,20,48),     (200,240,255), "W"),
            }

            def draw_shop_icon(act, rect, accent_col, unlocked):
                icon_bg = pygame.Rect(rect.x + 8, rect.y + 8, 40, rect.height - 16)
                pygame.draw.rect(screen, (20, 20, 24) if unlocked else (35, 35, 40), icon_bg, border_radius=8)
                pygame.draw.rect(screen, accent_col if unlocked else (70, 70, 76), icon_bg, 1, border_radius=8)
                cx, cy = icon_bg.centerx, icon_bg.centery
                ic = accent_col if unlocked else (100, 100, 110)

                if act == "speed":
                    pts = [(cx - 5, cy - 10), (cx + 1, cy - 3), (cx - 2, cy - 3), (cx + 5, cy + 10), (cx - 1, cy + 2), (cx + 2, cy + 2)]
                    pygame.draw.polygon(screen, ic, pts)
                elif act == "size":
                    pygame.draw.rect(screen, ic, (cx - 8, cy - 8, 16, 16), 2, border_radius=2)
                elif act == "jew":
                    pygame.draw.circle(screen, ic, (cx, cy), 9, 2)
                    pygame.draw.circle(screen, ic, (cx, cy), 3)
                elif act == "flash":
                    pygame.draw.line(screen, ic, (cx - 9, cy), (cx + 9, cy), 2)
                    pygame.draw.line(screen, ic, (cx, cy - 9), (cx, cy + 9), 2)
                elif act == "trail":
                    for k in range(3):
                        pygame.draw.line(screen, ic, (cx - 10 + k * 4, cy - 8), (cx - 4 + k * 4, cy + 8), 2)
                elif act == "bonus":
                    pygame.draw.line(screen, ic, (cx - 8, cy), (cx + 8, cy), 3)
                    pygame.draw.line(screen, ic, (cx, cy - 8), (cx, cy + 8), 3)
                elif act == "wave":
                    for k in range(3):
                        pygame.draw.arc(screen, ic, (cx - 12 + k * 4, cy - 8, 12, 16), math.pi * 0.15, math.pi * 0.85, 2)
                elif act == "laser":
                    pygame.draw.line(screen, ic, (cx - 10, cy), (cx + 10, cy), 3)
                    pygame.draw.circle(screen, ic, (cx + 10, cy), 3)
                elif act == "implosion":
                    pygame.draw.circle(screen, ic, (cx, cy), 10, 2)
                    pygame.draw.circle(screen, ic, (cx, cy), 4, 1)
                elif act == "lightning":
                    pts = [(cx - 5, cy - 10), (cx + 1, cy - 2), (cx - 2, cy - 2), (cx + 4, cy + 10), (cx - 2, cy + 1), (cx + 1, cy + 1)]
                    pygame.draw.polygon(screen, ic, pts)
                elif act == "factory":
                    pygame.draw.rect(screen, ic, (cx - 10, cy - 7, 20, 14), 2)
                    pygame.draw.rect(screen, ic, (cx - 4, cy - 13, 8, 6), 2)
                elif act == "illuminate":
                    pygame.draw.polygon(screen, ic, [(cx, cy - 10), (cx - 9, cy + 8), (cx + 9, cy + 8)], 2)
                elif act == "gravity":
                    pygame.draw.circle(screen, ic, (cx, cy), 10, 2)
                    pygame.draw.circle(screen, ic, (cx + 4, cy), 3)
                elif act == "mode3d":
                    pygame.draw.rect(screen, ic, (cx - 8, cy - 8, 16, 16), 2)
                    pygame.draw.line(screen, ic, (cx - 8, cy - 8), (cx - 3, cy - 13), 1)
                    pygame.draw.line(screen, ic, (cx + 8, cy - 8), (cx + 13, cy - 13), 1)
                elif act == "donut":
                    pygame.draw.circle(screen, ic, (cx, cy), 10, 2)
                    pygame.draw.circle(screen, (20, 20, 24), (cx, cy), 4)
                elif act == "goongod":
                    pygame.draw.circle(screen, ic, (cx, cy - 5), 5)
                    pygame.draw.line(screen, ic, (cx, cy), (cx, cy + 10), 3)
                    pygame.draw.line(screen, ic, (cx - 8, cy + 2), (cx + 8, cy + 2), 2)
                    pygame.draw.line(screen, ic, (cx - 5, cy - 11), (cx - 2, cy - 15), 2)
                    pygame.draw.line(screen, ic, (cx + 5, cy - 11), (cx + 2, cy - 15), 2)
                elif act == "newworld":
                    pygame.draw.circle(screen, ic, (cx, cy-8), 5)
                    for ang in range(0,360,30):
                        rad=math.radians(ang)
                        pygame.draw.line(screen,ic,(cx,cy-8),(int(cx+math.cos(rad)*11),int(cy-8+math.sin(rad)*11)),1)
                    pygame.draw.circle(screen, ic, (cx, cy+6), 8, 2)
                    pygame.draw.rect(screen, ic, (cx-8, cy+2, 16, 8), 1)
                else:
                    pygame.draw.circle(screen, ic, (cx, cy), 8, 2)

            # Choose data source for shop display
            if all_goons_mode and len(bouncers) > 1:
                display_shop_data = all_goons_shop_data()
                def display_is_unlocked(idx): return all_goons_is_unlocked(idx)
            else:
                display_shop_data = selected_bouncer.shop_data
                def display_is_unlocked(idx): return selected_bouncer.is_unlocked(idx)

            max_sc = shop_max_scroll(len(display_shop_data))
            shop_scroll_offset = max(0.0, min(max_sc, shop_scroll_offset))
            shop_clip = pygame.Rect(GAME_WIDTH, SHOP_PANEL_TOP, SHOP_WIDTH, HEIGHT - SHOP_PANEL_TOP)
            prev_clip = screen.get_clip()
            screen.set_clip(shop_clip)

            for i, item in enumerate(display_shop_data):
                rect     = shop_item_rect(i, shop_scroll_offset)
                if rect.bottom < SHOP_PANEL_TOP or rect.top > HEIGHT:
                    continue
                unlocked = display_is_unlocked(i)
                act      = item["action"]

                theme = SHOP_THEME.get(act, ((50,50,50),(200,200,200),"?"))
                bg_col, accent_col, icon = theme[0], theme[1], theme[2] if len(theme)>2 else "?"

                # ALL mode: tint rows gold
                if all_goons_mode and len(bouncers) > 1 and unlocked:
                    bg = tuple(min(255, int(c * 0.7 + g * 0.3)) for c, g in zip(bg_col, (40, 34, 5)))
                elif unlocked:
                    bg = bg_col
                else:
                    bg = (30, 30, 34)
                pygame.draw.rect(screen, bg, rect, border_radius=7)

                # Animated accent border for unlocked items
                if unlocked:
                    border_alpha = int(160 + 80 * math.sin(shop_t * 2.0 + i * 0.7))
                    bc = tuple(min(255, int(c * border_alpha / 240)) for c in accent_col)
                    if all_goons_mode and len(bouncers) > 1:
                        bc = (min(255, bc[0]+40), min(255, bc[1]+30), max(0, bc[2]-20))
                    pygame.draw.rect(screen, bc, rect, 1, border_radius=7)
                else:
                    pygame.draw.rect(screen, (55, 55, 60), rect, 1, border_radius=7)

                # Left accent stripe
                stripe_rect = pygame.Rect(rect.x, rect.y + 5, 4, rect.height - 10)
                pygame.draw.rect(screen, accent_col if unlocked else (60,60,65), stripe_rect, border_radius=2)
                draw_shop_icon(act, rect, accent_col, unlocked)

                tc = (230, 230, 235) if unlocked else (90, 90, 100)
                if all_goons_mode and len(bouncers) > 1 and unlocked:
                    tc = (255, 240, 160)  # gold tint in ALL mode

                # ── Build label text ───────────────────────────────────────────────
                if act == "size":
                    limit_tag = " LIMITED" if item["bought"] >= 25 else ""
                    np = f"{item['name']} x{item['bought']}{limit_tag}"
                elif act == "flash" and selected_bouncer.flashing:
                    np = f"{item['name']} x{item['bought']}  [{5000/selected_bouncer.flash_purchases/1000:.1f}s]"
                elif act == "laser" and selected_bouncer.laser_enabled:
                    np = f"{item['name']} x{item['bought']}  [{selected_bouncer.laser_purchases}b]"
                elif act == "implosion" and selected_bouncer.implosion_enabled:
                    total_s = IMPLOSION_BASE_WINDOW / max(selected_bouncer.bought_count("implosion"), 1) / 1000
                    np = f"{item['name']} x{item['bought']}  [{total_s:.0f}s]"
                elif act == "lightning" and selected_bouncer.lightning_enabled:
                    payout_k = selected_bouncer.lightning_purchases * 100
                    np = f"{item['name']} x{item['bought']}  [£{payout_k}K]"
                elif act == "factory" and len(factories) > 0:
                    np = f"{item['name']} x{item['bought']}  [{len(factories)} £100M/s]"
                elif act == "illuminate" and selected_bouncer.illuminate_enabled:
                    np = f"{item['name']} x{item['bought']}  [+£50B/s]"
                elif act == "gravity" and selected_bouncer.gravity_enabled:
                    np = f"{item['name']} x{item['bought']}  [+£1T/s]"
                elif act == "mode3d" and selected_bouncer.mode3d_enabled:
                    np = f"{item['name']} x{item['bought']}  [+£75T/s]"
                elif act == "donut" and selected_bouncer.donut_enabled:
                    cnt_total = total_donut_goons()
                    cnt_own = selected_bouncer.donut_ring_count
                    np = f"{item['name']} x{item['bought']}  [{cnt_total}/{DONUT_GOON_MAX} ring • own:{cnt_own} • 1000T / sec]"
                elif act == "goongod" and selected_bouncer.goon_god_enabled:
                    gp = total_goon_god_power()
                    np = f"{item['name']} x{item['bought']}  [ZEUS x{gp} • +15x donut]"
                else:
                    np = f"{item['name']} x{item['bought']}"

                # Show "× N goons" suffix in ALL mode
                if all_goons_mode and len(bouncers) > 1:
                    np = np + f"  ×{len(bouncers)}"

                pp = fmt_price(item["price"])
                if not unlocked:
                    pc = (70, 70, 80)
                elif cheat_mode or coins >= item["price"]:
                    pc = (80, 255, 120)
                else:
                    pc = (255, 80, 80)

                # Name left-aligned, price right-aligned
                ns = hud_surf(f"n{i}{'A' if all_goons_mode else ''}", np,  font, tc)
                ps = hud_surf(f"p{i}{'A' if all_goons_mode else ''}", pp,  font, pc)
                screen.blit(ns, (rect.x + 56, rect.y + 11))
                screen.blit(ps, (rect.right - ps.get_width() - 8, rect.y + 30))

            # Scroll bar
            viewport_h = HEIGHT - SHOP_PANEL_TOP - SHOP_PANEL_BOTTOM_PAD
            if max_sc > 0.0 and viewport_h > 8:
                track = pygame.Rect(GAME_WIDTH + SHOP_WIDTH - 8, SHOP_PANEL_TOP, 4, viewport_h)
                pygame.draw.rect(screen, (50, 50, 56), track, border_radius=2)
                thumb_h = max(18, int(viewport_h * (viewport_h / (viewport_h + max_sc))))
                thumb_y = int(SHOP_PANEL_TOP + (viewport_h - thumb_h) * (shop_scroll_offset / max_sc))
                thumb = pygame.Rect(track.x, thumb_y, track.width, thumb_h)
                pygame.draw.rect(screen, (140, 140, 155), thumb, border_radius=2)

            screen.set_clip(prev_clip)

            click_animations[:] = [a for a in click_animations if now-a["time"] < CLICK_ANIM_TIME]
            for anim in click_animations:
                pygame.draw.rect(screen, (80, 255, 120), anim["rect"], 3, border_radius=7)

            screen.blit(hud_surf("coins", fmt_coins(coins),        big_font, GREEN),        (20, 20))
            screen.blit(hud_surf("hs",    f"Best: \xa3{highscore}", font,     GOLD),         (20, 55))
            if green_coins > 0:
                _gc_label = fmt_nw_coins(green_coins)
                screen.blit(hud_surf("gc", f"G {_gc_label}", font, (80, 220, 100)), (20, 72))
            _hud_y2 = 72 + (20 if green_coins > 0 else 6)
            if cheat_mode:
                screen.blit(hud_surf("dev", "\u2605 DEV MODE \u2605", font, GOLD), (20, _hud_y2))
            if goon_mode:
                screen.blit(hud_surf("goon", "\U0001f4a6 GOON MODE \U0001f4a6", font, (100,255,150)), (20, _hud_y2 if not cheat_mode else _hud_y2+20))
            screen.blit(hud_surf("esc",   "ESC = Menu",             font,     (100,100,100)),(20, HEIGHT-30))

            pygame.display.flip()

        await asyncio.sleep(0)


if __name__ == "__main__":
    asyncio.run(main())

import pygame
import sys
import random
import math
import os
import asyncio

pygame.init()

# ------------------ WEB-SAFE DISPLAY ------------------
WIDTH      = 1280
HEIGHT     = 720
GAME_WIDTH = int(WIDTH * (600 / 900))
SHOP_WIDTH = WIDTH - GAME_WIDTH

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Bounce Empire")

WHITE        = (240, 240, 240)
BLACK        = (15,  15,  15)
DARK_BG      = (20,  20,  20)
DARKER       = (35,  35,  35)
LOCKED_COLOR = (60,  60,  60)
GREEN        = (0,   255, 0)
YELLOW       = (255, 255, 0)
RED          = (255, 0,   0)
GOLD         = (255, 215, 0)
ORANGE       = (255, 140, 0)
PURPLE       = (160, 0,   220)
PURPLE_DARK  = (60,  0,   80)

font       = pygame.font.SysFont(None, 28)
big_font   = pygame.font.SysFont(None, 42)
title_font = pygame.font.SysFont(None, 120)
med_font   = pygame.font.SysFont(None, 52)

clock = pygame.time.Clock()

# ------------------ HIGH SCORE ------------------
_BASE_DIR = os.path.dirname(__file__) or "."

def rel_path(*parts):
    return os.path.join(_BASE_DIR, *parts)

HIGHSCORE_FILE_NORMAL = rel_path("highscore.txt")
HIGHSCORE_FILE_GOON   = rel_path("highscore_goon.txt")
HIGHSCORE_FILE_DEV    = rel_path("highscore_dev.txt")

def _hs_file():
    if cheat_mode: return HIGHSCORE_FILE_DEV
    if goon_mode:  return HIGHSCORE_FILE_GOON
    return HIGHSCORE_FILE_NORMAL

def load_highscore():
    try:
        with open(_hs_file(), "r") as f:
            return int(f.read().strip())
    except Exception:
        return 0

def save_highscore(score):
    try:
        with open(_hs_file(), "w") as f:
            f.write(str(score))
    except Exception:
        pass

highscore      = 0   # set properly after mode globals exist (see below)
_hs_dirty      = False
_hs_save_timer = 0

# ------------------ GAME STATE ------------------
STATE_MENU = "menu"
STATE_GAME = "game"
STATE_CODE = "code"
state = STATE_MENU

coins          = 0
green_coins    = 0   # New World currency (green coins)
start_coins_override = None
free_shop = False
cheat_mode     = False
goon_mode      = False
code_input     = ""
code_message   = ""
code_msg_timer = 0

DEV_COINS = 10 ** 18

def fmt_price(p):
    """Format a shop price compactly."""
    if p >= 1_000_000_000_000_000: return f"£{p/1_000_000_000_000_000:.1f}Q"
    if p >= 1_000_000_000_000:     return f"£{p/1_000_000_000_000:.1f}T"
    if p >= 1_000_000_000: return f"£{p/1_000_000_000:.1f}B"
    if p >= 1_000_000:     return f"£{p/1_000_000:.1f}M"
    if p >= 1_000:         return f"£{p/1_000:.0f}K"
    return f"£{p}"

def fmt_coins(c):
    if cheat_mode: return "\u221e"
    if c >= 1_000_000_000_000_000:  return f"\xa3{c/1_000_000_000_000_000:.2f}Q"
    if c >= 1_000_000_000_000:      return f"\xa3{c/1_000_000_000_000:.2f}T"
    if c >= 1_000_000_000:  return f"\xa3{c/1_000_000_000:.2f}B"
    if c >= 1_000_000:      return f"\xa3{c/1_000_000:.2f}M"
    if c >= 1_000:          return f"\xa3{c/1_000:.1f}K"
    return f"\xa3{c}"


def fmt_nw_coins(c):
    """Format New World green coin amounts."""
    if c >= 1_000_000_000: return f"G{c/1_000_000_000:.1f}B"
    if c >= 1_000_000:     return f"G{c/1_000_000:.1f}M"
    if c >= 1_000:         return f"G{c/1_000:.1f}K"
    return f"G{c}"

# ------------------ CLICK ANIMATION ------------------
click_animations = []
CLICK_ANIM_TIME  = 200

# ------------------ PERF SAFETY CAPS ------------------
# FIX: Drastically reduced beam cap and tightened shot limit to prevent crash/lag
LASER_MIN_COOLDOWN_MS    = 300          # was 120 — prevent rapid-fire spam
LASER_MAX_SHOTS_PER_TICK = 3            # max beams per bouncer (visible limit)
LASER_MAX_ACTIVE_BEAMS   = 60           # raised cap — new beams always added on bounce
MAX_FLASH_PARTICLES      = 600          # was 1800
MAX_EXPLOSION_PARTICLES  = 800          # was 2400
DONUT_GOON_MAX           = 20
DONUT_INCOME_PER_SEC     = 1_000_000_000_000_000

# FIX: Laser beams now have a shorter max life to self-clean faster
LASER_BEAM_DECAY = 0.025               # was 0.012

# Scrollable shop layout (larger buttons)
SHOP_ROW_H       = 56
SHOP_ROW_GAP     = 10
SHOP_PANEL_TOP   = 42
SHOP_PANEL_BOTTOM_PAD = 10
shop_scroll_offset = 0.0
all_goons_mode = False   # when True, shop shows "upgrade ALL goons at once" tab

def shop_item_rect(i, scroll_off=0.0):
    y = int(SHOP_PANEL_TOP + i * (SHOP_ROW_H + SHOP_ROW_GAP) - scroll_off)
    return pygame.Rect(GAME_WIDTH + 10, y, SHOP_WIDTH - 20, SHOP_ROW_H)

def shop_max_scroll(item_count):
    content_h = max(0, item_count * (SHOP_ROW_H + SHOP_ROW_GAP) - SHOP_ROW_GAP)
    viewport_h = HEIGHT - SHOP_PANEL_TOP - SHOP_PANEL_BOTTOM_PAD
    return max(0.0, float(content_h - viewport_h))

def shop_nav_rects():
    tab = pygame.Rect(GAME_WIDTH + 10, 6, SHOP_WIDTH - 20, 28)
    left  = pygame.Rect(tab.x + 6,        tab.y + 4, 22, tab.height - 8)
    right = pygame.Rect(tab.right - 28,   tab.y + 4, 22, tab.height - 8)
    # ALL button sits between centre and right arrow
    all_btn = pygame.Rect(tab.right - 56, tab.y + 4, 26, tab.height - 8)
    return tab, left, right, all_btn

def all_goons_shop_data():
    """
    Build a merged shop list for ALL goons:
    each item's price = sum of that item's current price across every bouncer
    (so buying it upgrades every goon simultaneously).
    """
    if not bouncers:
        return []
    template = bouncers[0].shop_data
    rows = []
    for idx, item in enumerate(template):
        total_price = sum(b.shop_data[idx]["price"] for b in bouncers if idx < len(b.shop_data))
        rows.append({
            "name":       item["name"],
            "price":      total_price,
            "base_price": item["base_price"],
            "action":     item["action"],
            "bought":     min(b.shop_data[idx]["bought"] for b in bouncers if idx < len(b.shop_data)),
        })
    return rows

def all_goons_is_unlocked(idx):
    """Unlocked if ALL bouncers have it unlocked."""
    return all(b.is_unlocked(idx) for b in bouncers)

# ------------------ HUD TEXT CACHE ------------------
_hud_cache: dict = {}

def hud_surf(key, text, fnt, color):
    full_key = (key, color)
    entry = _hud_cache.get(full_key)
    if entry is None or entry[0] != text:
        _hud_cache[full_key] = (text, fnt.render(text, True, color))
    return _hud_cache[full_key][1]

# ------------------ BASE SHOP ------------------
BASE_SHOP = [
    {"name": "Speed +5%",          "base_price": 2,         "action": "speed"},
    {"name": "Size +5%",           "base_price": 5,         "action": "size"},
    {"name": "Coin Bouncer",       "base_price": 15,        "action": "jew"},
    {"name": "Flashing Bouncer",   "base_price": 50,        "action": "flash"},
    {"name": "Trail Bouncer",      "base_price": 100,       "action": "trail"},
    {"name": "Bonus Bouncer",      "base_price": 500,       "action": "bonus"},
    {"name": "Wave Bouncer",       "base_price": 1000,      "action": "wave"},
    {"name": "Laser Bouncer",      "base_price": 15000,     "action": "laser"},
    {"name": "Implosion Bouncer",  "base_price": 250000,    "action": "implosion"},
    {"name": "Lightning Bouncer",  "base_price": 5000000,  "action": "lightning"},
    {"name": "Goon Factory",        "base_price": 2000000000,"action": "factory"},
    {"name": "Illuminate",            "base_price": 250000000000,"action": "illuminate"},
    {"name": "Gravity Well",           "base_price": 5000000000000,"action": "gravity"},
    {"name": "3D Mode",                  "base_price": 500000000000000,"action": "mode3d"},
    {"name": "Donut Ring",               "base_price": 15000000000000000,"action": "donut"},
    {"name": "God Goon",                "base_price": 375000000000000000,"action": "goongod"},
]

GOON_SHOP = [
    {"name": "Goon Speed +5%",       "base_price": 2,         "action": "speed"},
    {"name": "Goon Size +5%",        "base_price": 5,         "action": "size"},
    {"name": "Goon Coin Goon",       "base_price": 15,        "action": "jew"},
    {"name": "Goon Flash Goon",      "base_price": 50,        "action": "flash"},
    {"name": "Goon Trail Goon",      "base_price": 100,       "action": "trail"},
    {"name": "Bonus Goon",           "base_price": 500,       "action": "bonus"},
    {"name": "Goon Wave Goon",       "base_price": 1000,      "action": "wave"},
    {"name": "Goon Laser Goon",      "base_price": 15000,     "action": "laser"},
    {"name": "Goon Implosion Goon",  "base_price": 250000,    "action": "implosion"},
    {"name": "Goon Lightning Goon",  "base_price": 5000000,  "action": "lightning"},
    {"name": "Goon Factory Goon",    "base_price": 2000000000,"action": "factory"},
    {"name": "Goon Illuminate Goon",   "base_price": 250000000000,"action": "illuminate"},
    {"name": "Goon Gravity Goon",      "base_price": 5000000000000,"action": "gravity"},
    {"name": "Goon 3D Goon",             "base_price": 500000000000000,"action": "mode3d"},
    {"name": "Donut Goon",               "base_price": 15000000000000000,"action": "donut"},
    {"name": "Goon God Goon",           "base_price": 375000000000000000,"action": "goongod"},
]

def active_shop():
    return GOON_SHOP if goon_mode else BASE_SHOP

def build_shop_data(existing=None):
    prev = {}
    if existing:
        prev = {it["action"]: it for it in existing}
    rows = []
    for it in active_shop():
        old = prev.get(it["action"])
        rows.append({
            "name": it["name"],
            "price": old["price"] if old else it["base_price"],
            "base_price": it["base_price"],
            "action": it["action"],
            "bought": old["bought"] if old else 0
        })
    return rows

# ------------------ DRIP PARTICLES (goon mode) ------------------
# layout: [x, y, vy, width, length, alpha, decay]
drip_particles = []
MAX_DRIP_PARTICLES = 120
_drip_spawn_timer  = 0

def update_spawn_drips(now):
    global _drip_spawn_timer
    if not goon_mode: return
    if now - _drip_spawn_timer < 80: return
    _drip_spawn_timer = now
    if len(drip_particles) >= MAX_DRIP_PARTICLES: return
    x = random.randint(0, WIDTH)
    drip_particles.append([float(x), -random.randint(0, 60),
                            random.uniform(1.5, 4.0),
                            random.randint(3, 9),
                            random.randint(20, 60),
                            random.randint(160, 255),
                            random.uniform(0.4, 1.2)])

def draw_drips(surface):
    if not goon_mode: return
    i = 0
    while i < len(drip_particles):
        d = drip_particles[i]
        d[1] += d[2]   # fall
        if d[1] > HEIGHT + 80:
            drip_particles[i] = drip_particles[-1]; drip_particles.pop()
            continue
        alpha = max(0, int(d[5]))
        col   = (alpha, alpha, alpha)
        x, y, w, ln = int(d[0]), int(d[1]), d[3], d[4]
        # drip body
        pygame.draw.rect(surface, col, (x - w//2, y, w, ln))
        # rounded drop at bottom
        pygame.draw.circle(surface, col, (x, y + ln), w)
        i += 1

# Pre-baked implosion hold glow surfaces
_IMP_HOLD_GLOWS = []
for _gr, _ga in [(32, 25), (20, 55), (12, 110), (6, 220), (3, 255)]:
    _gs = pygame.Surface((_gr * 2, _gr * 2), pygame.SRCALPHA)
    pygame.draw.circle(_gs, (255, 255, 255, _ga), (_gr, _gr), _gr)
    _IMP_HOLD_GLOWS.append((_gr, _gs))

# Pre-baked trail colours
TRAIL_COLORS = []
for _i in range(40):
    _c = pygame.Color(0)
    _c.hsva = ((_i * 10) % 360, 100, 100, 100)
    TRAIL_COLORS.append((int(_c.r), int(_c.g), int(_c.b)))

# ------------------ PARTICLES ------------------
flash_particles     = []
explosion_particles = []
_EXP_COLORS = [(255,80,0),(255,160,0),(255,220,0),(255,40,40),(255,0,0)]
_TWO_PI     = 2.0 * math.pi

def spawn_flash_particles(cx, cy, color):
    free_slots = MAX_FLASH_PARTICLES - len(flash_particles)
    if free_slots <= 0:
        return
    r, g, b = color
    br, bg, bb = min(r+80,255), min(g+80,255), min(b+80,255)
    cos_f = math.cos; sin_f = math.sin; uni = random.uniform; randi = random.randint
    count = min(randi(10, 20), free_slots)   # FIX: reduced particle count
    for _ in range(count):
        a   = uni(0, _TWO_PI)
        spd = uni(3, 9)
        flash_particles.append([cx, cy, cos_f(a)*spd, sin_f(a)*spd,
                                 br, bg, bb, 1.0, uni(0.03, 0.07), randi(3, 7)])

def spawn_explosion(cx, cy):
    free_slots = MAX_EXPLOSION_PARTICLES - len(explosion_particles)
    if free_slots <= 0:
        return
    cos_f = math.cos; sin_f = math.sin; uni = random.uniform
    randi = random.randint; choice = random.choice
    count = min(randi(8, 15), free_slots)   # FIX: reduced particle count
    for _ in range(count):
        a   = uni(0, _TWO_PI)
        spd = uni(2, 8)
        ec  = choice(_EXP_COLORS)
        explosion_particles.append([cx, cy, cos_f(a)*spd, sin_f(a)*spd,
                                     ec[0], ec[1], ec[2], 1.0, uni(0.04, 0.09), randi(3, 8)])

def update_draw_particles(plist, surface, life_fade):
    draw_circle = pygame.draw.circle
    i = 0
    while i < len(plist):
        p     = plist[i]
        p[0] += p[2];  p[1] += p[3]
        p[2] *= 0.93;  p[3] *= 0.93
        p[7] -= p[8]
        if p[7] <= 0:
            plist[i] = plist[-1]; plist.pop()
        else:
            if life_fade:
                lf  = p[7]
                col = (int(p[4]*lf), int(p[5]*lf), int(p[6]*lf))
            else:
                col = (p[4], p[5], p[6])
            draw_circle(surface, col, (int(p[0]), int(p[1])), max(1, int(p[9])))
            i += 1

# ------------------ WAVE RING ------------------
WAVE_MAX_RADIUS = int(math.hypot(GAME_WIDTH, HEIGHT)) + 40

class WaveRing:
    __slots__ = ('x','y','radius','max_radius','color','alive',
                 'origin_side','paid_opposite','_draw_col','payout')
    def __init__(self, x, y, color, origin_side, payout=300):
        self.x = x; self.y = y
        self.radius       = 10
        self.max_radius   = WAVE_MAX_RADIUS
        self.color        = color
        self.alive        = True
        self.origin_side  = origin_side
        self.paid_opposite= False
        self.payout       = int(max(1, payout))
        r, g, b           = color
        self._draw_col    = (min(r+60,255), min(g+60,255), min(b+60,255))

    def update(self):
        global coins
        self.radius += 4
        if self.radius >= self.max_radius:
            self.alive = False
            return
        if not self.paid_opposite:
            os = self.origin_side
            if ((os=='left'   and self.radius >= GAME_WIDTH - self.x) or
                (os=='right'  and self.radius >= self.x) or
                (os=='top'    and self.radius >= HEIGHT   - self.y) or
                (os=='bottom' and self.radius >= self.y)):
                coins += self.payout
                self.paid_opposite = True

    def draw(self, surface):
        r = int(self.radius)
        if r < 1: return
        fade = max(0.0, 1.0 - self.radius / self.max_radius)
        thickness = max(1, int(8 * fade))
        # Outer glow ring
        cr, cg, cb = self._draw_col
        glow_col = (int(cr * fade), int(cg * fade), int(cb * fade))
        if thickness > 1:
            pygame.draw.circle(surface, glow_col,    (int(self.x), int(self.y)), r + 2, thickness + 3)
        pygame.draw.circle(surface, self._draw_col, (int(self.x), int(self.y)), r,     thickness)
        # bright inner highlight
        if fade > 0.3 and r > 4:
            hi = (min(255, int(cr + 80*fade)), min(255, int(cg + 80*fade)), min(255, int(cb + 80*fade)))
            pygame.draw.circle(surface, hi, (int(self.x), int(self.y)), max(1, r - 1), max(1, thickness - 1))

wave_rings = []

# ------------------ LASER BEAM ------------------
class LaserBeam:
    __slots__ = ('x','y','vx','vy','life','decay','trail','trail_len','alive')
    def __init__(self, x, y, angle):
        self.x  = float(x); self.y = float(y)
        self.vx = math.cos(angle) * 10.0
        self.vy = math.sin(angle) * 10.0
        self.life      = 1.0
        self.decay     = 0.010          # slow decay = longer life
        self.trail     = [(self.x, self.y)]
        self.trail_len = 22             # longer trail
        self.alive     = True

    def update(self):
        self.x += self.vx; self.y += self.vy
        bounced = False
        if self.x <= 0 or self.x >= GAME_WIDTH:
            self.vx = -self.vx
            self.x  = max(0.0, min(float(GAME_WIDTH), self.x))
            bounced = True
        if self.y <= 0 or self.y >= HEIGHT:
            self.vy = -self.vy
            self.y  = max(0.0, min(float(HEIGHT), self.y))
            bounced = True
        if bounced:
            if random.random() < 0.4:
                spawn_explosion(int(self.x), int(self.y))
        self.trail.append((self.x, self.y))
        if len(self.trail) > self.trail_len:
            self.trail.pop(0)
        self.life -= self.decay
        if self.life <= 0:
            self.alive = False

    def draw(self, surface):
        tr = self.trail
        if len(tr) < 2: return
        n = len(tr); life = self.life
        draw_line = pygame.draw.line
        for i in range(1, n):
            bright = (i / n) * life
            p0 = (int(tr[i-1][0]), int(tr[i-1][1]))
            p1 = (int(tr[i][0]),   int(tr[i][1]))
            draw_line(surface, (int(140*bright), 0, 0), p0, p1, 18)   # thick glow
            draw_line(surface, (int(255*bright), int(60*bright), 0), p0, p1, 10)  # mid
            draw_line(surface, (255, int(200*bright), int(200*bright)), p0, p1, 4) # bright core
        pygame.draw.circle(surface, (255, 120, 120), (int(self.x), int(self.y)), 10)
        pygame.draw.circle(surface, (255, 255, 255), (int(self.x), int(self.y)), 5)

laser_beams = []

# ------------------ LIGHTNING SYSTEM ------------------
LIGHTNING_LIFETIME_MS  = 600
LIGHTNING_PAYOUT       = 100000

lightning_sessions = []

def _jagged_line_points(x1, y1, x2, y2, jag=14, segs=8):
    pts = [(x1, y1)]
    dx = x2 - x1; dy = y2 - y1
    length = math.hypot(dx, dy)
    if length == 0:
        return [(x1, y1), (x2, y2)]
    px = -dy / length; py = dx / length
    for i in range(1, segs):
        t   = i / segs
        mx  = x1 + dx * t
        my  = y1 + dy * t
        off = random.uniform(-jag, jag)
        pts.append((mx + px * off, my + py * off))
    pts.append((x2, y2))
    return pts

class LightningSession:
    __slots__ = ("edges", "born", "alive")

    def __init__(self, origin_bouncer, payout_per_hit):
        global coins
        self.born  = pygame.time.get_ticks()
        self.alive = True
        self.edges = []

        visited  = {id(origin_bouncer)}
        frontier = [origin_bouncer]
        total_pay = 0

        while frontier:
            next_frontier = []
            for src in frontier:
                candidates = []
                for b in bouncers:
                    if id(b) in visited: continue
                    d = math.hypot(b.rect.centerx - src.rect.centerx,
                                   b.rect.centery - src.rect.centery)
                    candidates.append((d, b))
                candidates.sort(key=lambda t: t[0])
                for _, tgt in candidates[:2]:
                    visited.add(id(tgt))
                    next_frontier.append(tgt)
                    sx, sy = src.rect.centerx, src.rect.centery
                    tx, ty = tgt.rect.centerx, tgt.rect.centery
                    pts = _jagged_line_points(sx, sy, tx, ty)
                    self.edges.append(pts)
                    total_pay += payout_per_hit
            frontier = next_frontier

        coins += total_pay

    def update(self):
        if pygame.time.get_ticks() - self.born >= LIGHTNING_LIFETIME_MS:
            self.alive = False

    def draw(self, surface):
        age     = pygame.time.get_ticks() - self.born
        alpha_f = max(0.0, 1.0 - age / LIGHTNING_LIFETIME_MS)
        if alpha_f <= 0: return
        draw_line = pygame.draw.line
        draw_circle = pygame.draw.circle
        for pts in self.edges:
            ipts = [(int(p[0]), int(p[1])) for p in pts]
            for i in range(1, len(ipts)):
                p0, p1 = ipts[i-1], ipts[i]
                # outer blue halo
                draw_line(surface, (0, int(30*alpha_f), int(120*alpha_f)), p0, p1, 14)
                # mid purple-blue
                draw_line(surface, (int(100*alpha_f), int(100*alpha_f), int(255*alpha_f)), p0, p1, 6)
                # bright white-blue core
                draw_line(surface, (int(220*alpha_f), int(220*alpha_f), int(255*alpha_f)), p0, p1, 2)
            # glow dot at each node
            for p in ipts[::max(1, len(ipts)//4)]:
                r2 = max(2, int(8 * alpha_f))
                draw_circle(surface, (int(180*alpha_f), int(180*alpha_f), 255), p, r2)

# ------------------ IMPLOSION SYSTEM ------------------
IMP_IDLE    = 0
IMP_SHRINK  = 1
IMP_HOLD    = 2
IMP_EXPLODE = 3
IMP_GRACE   = 4

IMPLOSION_SHRINK_MS   = 600
IMPLOSION_HOLD_MS     = 500
IMPLOSION_EXPLODE_MS  = 400
IMPLOSION_GRACE_MS    = 300
IMPLOSION_BASE_WINDOW = 60000
WALL_MARGIN           = 120

class ImplosionEffect:
    __slots__ = ('owner','phase','phase_start','spin_angle','_orig_size',
                 '_cx','_cy','_anim_ms','last_finish')
    def __init__(self, owner):
        self.owner       = owner
        self.phase       = IMP_IDLE
        self.phase_start = 0
        self.spin_angle  = 0.0
        self._orig_size  = owner.size
        self._cx         = owner.rect.centerx
        self._cy         = owner.rect.centery
        self._anim_ms    = (IMPLOSION_SHRINK_MS + IMPLOSION_HOLD_MS +
                            IMPLOSION_EXPLODE_MS + IMPLOSION_GRACE_MS)
        self.last_finish = pygame.time.get_ticks() - self._cooldown()

    def _cooldown(self):
        p = max(self.owner.bought_count("implosion"), 1)
        return max(2000, IMPLOSION_BASE_WINDOW // p - self._anim_ms)

    def _owner_safe(self):
        if cheat_mode: return True
        r = self.owner.rect
        if r.left < WALL_MARGIN or r.right > GAME_WIDTH - WALL_MARGIN: return False
        if r.top  < WALL_MARGIN or r.bottom > HEIGHT - WALL_MARGIN:    return False
        return True

    def _start_shrink(self, now):
        self.phase       = IMP_SHRINK
        self.phase_start = now
        self._orig_size  = self.owner.size
        self.owner.implosion_frozen = False
        self._cx = self.owner.rect.centerx
        self._cy = self.owner.rect.centery

    def _start_hold(self, now):
        self.phase       = IMP_HOLD
        self.phase_start = now
        self.spin_angle  = 0.0

    def _start_explode(self, now):
        global coins
        self.phase       = IMP_EXPLODE
        self.phase_start = now
        cx, cy = self._cx, self._cy
        o = self.owner
        prev_speed = math.hypot(o.speed_x, o.speed_y)
        purchases = max(o.bought_count("implosion"), 1)
        o.size = self._orig_size
        o.rect.width = o.rect.height = self._orig_size
        o.rect.center = (cx, cy)
        o.fx = float(o.rect.x); o.fy = float(o.rect.y)
        o.implosion_frozen = False
        ang = random.uniform(0, _TWO_PI)
        carry      = min(prev_speed * 0.8, 450.0)
        base_blast = random.uniform(900.0, 1300.0) * (1.0 + 0.12 * (purchases - 1))
        blast_spd  = carry + base_blast
        o.speed_x = math.cos(ang) * blast_spd
        o.speed_y = math.sin(ang) * blast_spd
        coins += 300000 * o.earnings_multiplier()
        for _ in range(4): spawn_explosion(cx, cy)

    def _start_grace(self, now):
        self.phase = IMP_GRACE; self.phase_start = now

    def _finish(self, now):
        self.last_finish = now; self.phase = IMP_IDLE

    def update(self):
        now = pygame.time.get_ticks()
        ph  = self.phase
        if ph == IMP_IDLE:
            if now - self.last_finish >= self._cooldown() and self._owner_safe():
                self._start_shrink(now)
        elif ph == IMP_SHRINK:
            elapsed  = now - self.phase_start
            progress = min(elapsed / IMPLOSION_SHRINK_MS, 1.0)
            self.spin_angle += 0.10
            o        = self.owner
            new_size = max(4, int(self._orig_size * (1.0 - progress * progress)))
            cx_live  = o.rect.centerx; cy_live = o.rect.centery
            o.size = new_size
            o.rect.width = o.rect.height = new_size
            o.rect.centerx = cx_live; o.rect.centery = cy_live
            o.fx = float(o.rect.x); o.fy = float(o.rect.y)
            self._cx = cx_live; self._cy = cy_live
            if progress >= 1.0:
                o.size = 4; o.rect.width = o.rect.height = 4
                self._cx = o.rect.centerx; self._cy = o.rect.centery
                o.implosion_frozen = True
                self._start_hold(now)
        elif ph == IMP_HOLD:
            self.spin_angle += 0.18
            if now - self.phase_start >= IMPLOSION_HOLD_MS:
                self._start_explode(now)
        elif ph == IMP_EXPLODE:
            if now - self.phase_start >= IMPLOSION_EXPLODE_MS:
                self._start_grace(now)
        elif ph == IMP_GRACE:
            if now - self.phase_start >= IMPLOSION_GRACE_MS:
                self._finish(now)

    def _draw_pulsar_beams(self, surface, cx, cy, strength, base_len):
        if strength <= 0.0:
            return
        now = pygame.time.get_ticks()
        beam_count = 8
        core_col = (
            min(255, int(170 + 80 * strength)),
            min(255, int(190 + 65 * strength)),
            255
        )
        glow_col = (
            min(255, int(70 + 110 * strength)),
            min(255, int(90 + 120 * strength)),
            min(255, int(140 + 95 * strength))
        )
        core_w = max(1, int(2 + 3 * strength))
        glow_w = core_w + 5

        for i in range(beam_count):
            spoke = self.spin_angle + i * (_TWO_PI / beam_count)
            wobble = 0.22 * math.sin(now / 130.0 + i * 1.2)
            ang = spoke + wobble
            pulse = 0.75 + 0.25 * math.sin(now / 95.0 + i * 1.7)
            beam_len = int(base_len * pulse)
            ex = cx + int(math.cos(ang) * beam_len)
            ey = cy + int(math.sin(ang) * beam_len)
            pygame.draw.line(surface, glow_col, (cx, cy), (ex, ey), glow_w)
            pygame.draw.line(surface, core_col, (cx, cy), (ex, ey), core_w)

    def draw(self, surface):
        now = pygame.time.get_ticks()
        cx  = self._cx; cy = self._cy
        ph  = self.phase
        cos_f = math.cos; sin_f = math.sin

        if ph == IMP_SHRINK:
            elapsed  = now - self.phase_start
            progress = min(elapsed / IMPLOSION_SHRINK_MS, 1.0)
            ease     = progress * progress
            self._draw_pulsar_beams(surface, cx, cy, ease, int(self._orig_size * 1.6))
            glow_r   = max(2, int(self._orig_size * 0.6 * (1.0 - ease * 0.7)))
            wa       = int(80 + 175 * ease)
            for gr, ga in [(glow_r, max(0,wa-120)), (glow_r//2, max(0,wa-60)),
                           (max(2,glow_r//4), wa)]:
                if gr < 1: continue
                gs = pygame.Surface((gr*2, gr*2), pygame.SRCALPHA)
                pygame.draw.circle(gs, (255,255,255,min(255,ga)), (gr,gr), gr)
                surface.blit(gs, (cx-gr, cy-gr))
            ob = int(self._orig_size * 0.8 * (1.0 - ease * 0.5) + 12)
            for i in range(5):
                ang = self.spin_angle + i * (_TWO_PI / 5)
                orb = max(8, ob + int(6 * math.sin(elapsed/120 + i*1.1)))
                for t in range(6):
                    tr = orb - t
                    if tr < 2: continue
                    ta = ang - t*0.12
                    bv = int(200 * ease * (1 - t/6))
                    pygame.draw.circle(surface, (bv,bv,bv),
                        (cx+int(cos_f(ta)*tr), cy+int(sin_f(ta)*tr)), max(1,4-t))
                bh = int(255*ease)
                pygame.draw.circle(surface, (bh,bh,bh),
                    (cx+int(cos_f(ang)*orb), cy+int(sin_f(ang)*orb)), max(1,int(5*ease)))

        elif ph == IMP_HOLD:
            self._draw_pulsar_beams(surface, cx, cy, 1.0, int(self._orig_size * 1.9))
            for gr, gs in _IMP_HOLD_GLOWS:
                surface.blit(gs, (cx-gr, cy-gr))
            pygame.draw.circle(surface, (255,255,255), (cx,cy), 4)
            elapsed = now - self.phase_start
            for i in range(5):
                ang = self.spin_angle + i * (_TWO_PI / 5)
                orb = int(38 + 10 * math.sin(elapsed/120 + i*1.1))
                for t in range(8):
                    tr = orb - t
                    if tr < 2: continue
                    ta = ang - t*0.12
                    bv = int(255*(1-t/8))
                    pygame.draw.circle(surface, (bv,bv,bv),
                        (cx+int(cos_f(ta)*tr), cy+int(sin_f(ta)*tr)), max(1,5-t))
                pygame.draw.circle(surface, (255,255,255),
                    (cx+int(cos_f(ang)*orb), cy+int(sin_f(ang)*orb)), 5)

        elif ph == IMP_EXPLODE:
            elapsed  = now - self.phase_start
            progress = min(elapsed / IMPLOSION_EXPLODE_MS, 1.0)
            shock_r  = int(progress * 280)
            if shock_r > 0:
                thick = max(1, int(10*(1-progress)))
                pygame.draw.circle(surface, (255,255,255), (cx,cy), shock_r, thick)
                ir = int(shock_r*0.6)
                if ir > 0:
                    pygame.draw.circle(surface, (200,200,255), (cx,cy), ir, max(1,thick-2))

    def draw_cooldown_hud(self, surface):
        if self.phase != IMP_IDLE: return
        now      = pygame.time.get_ticks()
        progress = min((now - self.last_finish) / self._cooldown(), 1.0)
        bx = self.owner.rect.x; by = self.owner.rect.bottom + 4
        bw = self.owner.rect.width
        pygame.draw.rect(surface, (40,0,60),  (bx, by, bw, 5))
        pygame.draw.rect(surface, PURPLE,     (bx, by, int(bw*progress), 5))

implosion_effects = []

# ------------------ MENU BACKGROUND BOUNCERS ------------------
class BgBouncer:
    __slots__ = ('x','y','vx','vy','_surf','_size')
    def __init__(self):
        self._size = random.randint(20, 60)
        self.x     = random.randint(0, WIDTH)
        self.y     = random.randint(0, HEIGHT)
        spd        = random.uniform(1, 3)
        ang        = random.uniform(0, _TWO_PI)
        self.vx    = math.cos(ang) * spd
        self.vy    = math.sin(ang) * spd
        color      = (random.randint(60,200), random.randint(60,200), random.randint(60,200))
        alpha      = random.randint(40, 120)
        s = pygame.Surface((self._size, self._size), pygame.SRCALPHA)
        s.fill((*color, alpha))
        self._surf = s

    def update(self):
        self.x += self.vx; self.y += self.vy
        if self.x < 0 or self.x > WIDTH:  self.vx = -self.vx
        if self.y < 0 or self.y > HEIGHT: self.vy = -self.vy

    def draw(self, surface):
        surface.blit(self._surf, (int(self.x), int(self.y)))

bg_bouncers = [BgBouncer() for _ in range(25)]

# ------------------ FACTORY SYSTEM ------------------
factories = []
_factory_income_timer = 0
FACTORY_INCOME_PER_SEC = 100_000_000

class Factory:
    """
    Two pale vertical cylinders connected by a long horizontal pipe in the middle.
    White liquid drips from the tops of both cylinders.
    """
    __slots__ = ('x', 'phase', 'gear_angle', 'liquid_drops', '_drop_timer',
                 'valve_angle', 'pressure_pulse')

    CYL_W    = 32    # cylinder width
    CYL_H    = 130   # cylinder height
    PIPE_H   = 18    # connecting pipe height (vertical centre position)
    SPACING  = 68    # centre-to-centre of the two cylinders

    def __init__(self, x):
        self.x             = x
        self.phase         = random.uniform(0, 6.28)
        self.gear_angle    = 0.0
        self.valve_angle   = 0.0
        self.pressure_pulse= random.uniform(0, 6.28)
        self._drop_timer   = random.uniform(0, 0.4)
        # drops: [x, y, vy, size, alpha, phase_off]
        self.liquid_drops  = []
        for _ in range(6):
            self.liquid_drops.append(self._new_drop(random.choice([-1, 1])))

    def _cyl_cx(self, side):
        """Centre-x of left (side=-1) or right (side=+1) cylinder."""
        return self.x + side * self.SPACING // 2

    def _new_drop(self, side):
        cx   = self._cyl_cx(side)
        top_y = HEIGHT - self.CYL_H - 4
        return [
            float(cx + random.randint(-self.CYL_W//2 + 4, self.CYL_W//2 - 4)),
            float(top_y),
            random.uniform(28.0, 55.0),   # fall speed
            random.uniform(3.5, 6.0),     # blob radius
            1.0,                          # alpha (life)
            random.choice([-1, 1]),       # which cylinder
        ]

    def update(self, dt, now):
        self.gear_angle     += 1.4 * dt
        self.valve_angle    += 0.7 * dt
        self.pressure_pulse += 2.1 * dt

        self._drop_timer -= dt
        if self._drop_timer <= 0.0:
            self._drop_timer = random.uniform(0.06, 0.18)
            side = random.choice([-1, 1])
            if len(self.liquid_drops) < 40:
                self.liquid_drops.append(self._new_drop(side))

        i = 0
        while i < len(self.liquid_drops):
            d = self.liquid_drops[i]
            d[1] += d[2] * dt
            d[4] -= dt * 0.55
            # splat on ground
            if d[1] > HEIGHT - 8 or d[4] <= 0:
                self.liquid_drops[i] = self.liquid_drops[-1]
                self.liquid_drops.pop()
            else:
                i += 1

    def _draw_cylinder(self, surface, cx, t):
        """Draw a single detailed pale cylinder."""
        cw   = self.CYL_W
        ch   = self.CYL_H
        by   = HEIGHT - ch  # top-left y of cylinder body

        # ── Colours (very pale, slightly warm) ────────────────────────────
        body_pale   = (230, 228, 224)
        body_mid    = (210, 208, 204)
        body_dark   = (175, 172, 168)
        body_shadow = (145, 142, 138)
        rim_col     = (245, 243, 240)
        rim_dark    = (190, 188, 184)
        highlight   = (255, 254, 252)
        seam_col    = (160, 158, 154)
        rivet_col   = (200, 198, 194)
        liquid_col  = (245, 250, 255)   # near-white blue-white

        # ── Top ellipse (rim) ──────────────────────────────────────────────
        rim_rect  = pygame.Rect(cx - cw//2, by - 8, cw, 16)
        pygame.draw.ellipse(surface, body_mid,  rim_rect)
        pygame.draw.ellipse(surface, rim_col,   pygame.Rect(cx - cw//2+2, by-6, cw-4, 12))
        pygame.draw.ellipse(surface, rim_dark,  rim_rect, 2)

        # ── Cylinder body ─────────────────────────────────────────────────
        body_rect = pygame.Rect(cx - cw//2, by, cw, ch)
        # base fill
        pygame.draw.rect(surface, body_pale, body_rect)
        # left shadow strip
        pygame.draw.rect(surface, body_shadow, (cx - cw//2, by, 6, ch))
        # right shadow strip
        pygame.draw.rect(surface, body_dark,   (cx + cw//2 - 7, by, 7, ch))
        # centre highlight strip
        hi_w = max(2, cw//4)
        pygame.draw.rect(surface, highlight,   (cx - hi_w//2, by + 4, hi_w, ch - 8))

        # ── Horizontal weld seams ──────────────────────────────────────────
        for seam_y in range(by + 24, by + ch - 10, 22):
            pygame.draw.line(surface, seam_col, (cx - cw//2, seam_y), (cx + cw//2, seam_y), 2)
            pygame.draw.line(surface, rim_col,  (cx - cw//2, seam_y+1), (cx + cw//2, seam_y+1), 1)

        # ── Rivets along seams ─────────────────────────────────────────────
        for seam_y in range(by + 24, by + ch - 10, 22):
            for rx in [cx - cw//2 + 5, cx + cw//2 - 5]:
                pygame.draw.circle(surface, rivet_col, (rx, seam_y), 3)
                pygame.draw.circle(surface, body_shadow, (rx+1, seam_y+1), 2)

        # ── Pressure gauge (small circle on body face) ────────────────────
        gx, gy = cx, by + 40
        gauge_r = 8
        pygame.draw.circle(surface, body_dark, (gx, gy), gauge_r + 2)
        pygame.draw.circle(surface, (240, 240, 220), (gx, gy), gauge_r)
        # needle
        pressure = 0.3 + 0.7 * abs(math.sin(t * 1.8 + self.pressure_pulse))
        needle_ang = -math.pi * 0.8 + pressure * math.pi * 1.6
        nex = gx + int(math.cos(needle_ang) * (gauge_r - 2))
        ney = gy + int(math.sin(needle_ang) * (gauge_r - 2))
        pygame.draw.line(surface, (220, 40, 40), (gx, gy), (nex, ney), 2)
        pygame.draw.circle(surface, body_dark, (gx, gy), 2)
        pygame.draw.circle(surface, body_shadow, (gx, gy), gauge_r + 2, 2)

        # ── Valve wheel (below gauge) ──────────────────────────────────────
        vx, vy = cx, by + 68
        pygame.draw.circle(surface, body_dark,  (vx, vy), 9, 2)
        pygame.draw.circle(surface, body_mid,   (vx, vy), 7)
        for k in range(4):
            va = self.valve_angle + k * math.pi / 2
            pygame.draw.line(surface, body_shadow,
                             (vx, vy),
                             (vx + int(math.cos(va)*9), vy + int(math.sin(va)*9)), 3)
        pygame.draw.circle(surface, seam_col, (vx, vy), 3)

        # ── Outlet nozzle at top ───────────────────────────────────────────
        nozzle_w = 8; nozzle_h = 10
        pygame.draw.rect(surface, body_dark, (cx - nozzle_w//2, by - 8 - nozzle_h, nozzle_w, nozzle_h))
        pygame.draw.rect(surface, rim_col, (cx - nozzle_w//2, by - 8 - nozzle_h, nozzle_w, nozzle_h), 1)
        # Nozzle tip ellipse
        pygame.draw.ellipse(surface, rim_dark,
                            (cx - nozzle_w//2 - 2, by - 8 - nozzle_h - 4, nozzle_w + 4, 8))

        # ── Liquid pool at top of nozzle (small meniscus) ─────────────────
        pool_pulse = 0.7 + 0.3 * math.sin(t * 5.2 + self.phase)
        pool_r = max(1, int(5 * pool_pulse))
        ps2 = pygame.Surface((pool_r*2, pool_r*2), pygame.SRCALPHA)
        pygame.draw.circle(ps2, (245, 252, 255, 220), (pool_r, pool_r), pool_r)
        surface.blit(ps2, (cx - pool_r, by - 8 - nozzle_h - pool_r - 2))

        # ── Bottom ellipse cap ─────────────────────────────────────────────
        bot_rect = pygame.Rect(cx - cw//2, HEIGHT - 18, cw, 18)
        pygame.draw.ellipse(surface, body_mid, bot_rect)
        pygame.draw.ellipse(surface, body_dark, bot_rect, 2)
        pygame.draw.rect(surface, body_pale, (cx - cw//2, HEIGHT - 12, cw, 6))

        # ── Outline ───────────────────────────────────────────────────────
        pygame.draw.rect(surface, seam_col, body_rect, 1)

    def draw(self, surface, now):
        t   = now / 1000.0
        cw  = self.CYL_W
        ch  = self.CYL_H
        cx_l = self._cyl_cx(-1)
        cx_r = self._cyl_cx(+1)
        pipe_cy = HEIGHT - ch // 2  # pipe vertical centre

        # ── Ground shadow ─────────────────────────────────────────────────
        sh_w = self.SPACING + cw + 24
        sh = pygame.Surface((sh_w, 14), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 70), (0, 4, sh_w, 10))
        surface.blit(sh, (self.x - sh_w//2, HEIGHT - 12))

        # ── Connecting horizontal pipe ────────────────────────────────────
        pipe_h     = 20   # pipe diameter
        pipe_x1    = cx_l + cw//2
        pipe_x2    = cx_r - cw//2
        pipe_top   = pipe_cy - pipe_h//2

        pipe_pale  = (220, 218, 214)
        pipe_hi    = (242, 241, 238)
        pipe_dark  = (168, 165, 160)
        pipe_seam  = (150, 148, 144)

        # Pipe body
        pygame.draw.rect(surface, pipe_pale, (pipe_x1, pipe_top, pipe_x2-pipe_x1, pipe_h))
        # Top highlight
        pygame.draw.rect(surface, pipe_hi, (pipe_x1, pipe_top+2, pipe_x2-pipe_x1, pipe_h//3))
        # Bottom shadow
        pygame.draw.rect(surface, pipe_dark, (pipe_x1, pipe_top+pipe_h*2//3, pipe_x2-pipe_x1, pipe_h//3+1))
        # Seam line
        pygame.draw.line(surface, pipe_seam, (pipe_x1, pipe_cy), (pipe_x2, pipe_cy), 1)
        # Pipe outline
        pygame.draw.rect(surface, pipe_seam, (pipe_x1, pipe_top, pipe_x2-pipe_x1, pipe_h), 1)

        # Left flange (where pipe meets cylinder)
        for fl_x in [pipe_x1, pipe_x2 - 8]:
            pygame.draw.rect(surface, pipe_dark, (fl_x, pipe_top - 4, 8, pipe_h + 8), border_radius=2)
            pygame.draw.rect(surface, pipe_pale, (fl_x+1, pipe_top - 3, 6, pipe_h + 6), border_radius=1)
            pygame.draw.rect(surface, pipe_seam, (fl_x, pipe_top - 4, 8, pipe_h + 8), 1, border_radius=2)
            # flange bolts
            for bolt_y in [pipe_top - 1, pipe_top + pipe_h + 1]:
                pygame.draw.circle(surface, pipe_dark, (fl_x + 4, bolt_y), 3)
                pygame.draw.circle(surface, pipe_pale, (fl_x + 3, bolt_y - 1), 1)

        # ── Pressure relief valve on pipe (small T-junction) ──────────────
        relief_x = (pipe_x1 + pipe_x2) // 2
        pygame.draw.rect(surface, pipe_dark, (relief_x - 5, pipe_top - 16, 10, 18))
        pygame.draw.rect(surface, pipe_pale, (relief_x - 4, pipe_top - 15, 8, 16))
        pygame.draw.ellipse(surface, pipe_dark, (relief_x - 8, pipe_top - 22, 16, 10))
        pygame.draw.ellipse(surface, pipe_hi, (relief_x - 7, pipe_top - 21, 14, 8))
        # Tiny leak drip from relief valve
        leak_phase = (t * 2.8 + self.phase) % 1.0
        leak_y = int(pipe_top - 22 + leak_phase * 20)
        if leak_y < pipe_cy:
            ls = pygame.Surface((5, 6), pygame.SRCALPHA)
            pygame.draw.ellipse(ls, (245, 252, 255, int(210*(1-leak_phase))), (0,0,5,6))
            surface.blit(ls, (relief_x - 2, leak_y))

        # ── Draw both cylinders (left then right) ─────────────────────────
        self._draw_cylinder(surface, cx_l, t)
        self._draw_cylinder(surface, cx_r, t)

        # ── Liquid drops falling from nozzle tops ────────────────────────
        for d in self.liquid_drops:
            r = max(1, int(d[3]))
            a = max(0, min(255, int(d[4] * 240)))
            # Elongate drop slightly as it falls
            drop_w = max(2, r - 1)
            drop_h = max(2, r + 2)
            ds = pygame.Surface((drop_w*2, drop_h*2), pygame.SRCALPHA)
            pygame.draw.ellipse(ds, (245, 252, 255, a), (0, 0, drop_w*2, drop_h*2))
            # Blue-white core
            if drop_w > 2:
                pygame.draw.ellipse(ds, (255, 255, 255, min(255, a+30)),
                                    (drop_w//2, drop_h//2, drop_w, drop_h))
            surface.blit(ds, (int(d[0])-drop_w, int(d[1])-drop_h))

        # ── Liquid splat puddles at base ───────────────────────────────────
        for cx_side in [cx_l, cx_r]:
            puddle_pulse = 0.65 + 0.35 * math.sin(t * 3.1 + (1 if cx_side == cx_l else -1) * 1.4 + self.phase)
            pud_r = max(3, int(12 * puddle_pulse))
            ps3 = pygame.Surface((pud_r*4, pud_r*2), pygame.SRCALPHA)
            pygame.draw.ellipse(ps3, (235, 248, 255, 130), (0, 0, pud_r*4, pud_r*2))
            pygame.draw.ellipse(ps3, (255, 255, 255, 80),
                                (pud_r//2, pud_r//4, pud_r*3, pud_r))
            surface.blit(ps3, (cx_side - pud_r*2, HEIGHT - pud_r - 4))


def update_factories(dt, now):
    global coins, _factory_income_timer
    if not factories: return
    for f in factories:
        f.update(dt, now)
    if now - _factory_income_timer >= 1000:
        ticks = (now - _factory_income_timer) // 1000
        coins += len(factories) * FACTORY_INCOME_PER_SEC * ticks
        _factory_income_timer += ticks * 1000

def draw_factories(surface, now):
    for f in factories:
        f.draw(surface, now)


# ------------------ ILLUMINATE SYSTEM ------------------
illuminate_effects = []

class IlluminateEffect:
    """A large glowing all-seeing-eye triangle with a sweeping red laser beam."""
    __slots__ = ('cx','cy','size','angle','laser_angle','laser_speed',
                 'income_timer','born','_glow_cache_t')

    INCOME_PER_SEC = 50_000_000_000
    BASE_SIZE      = 160

    def __init__(self):
        self.cx           = GAME_WIDTH // 2
        self.cy           = HEIGHT // 2
        self.size         = self.BASE_SIZE
        self.angle        = 0.0            # slow rotation of the whole triangle
        self.laser_angle  = 0.0            # laser sweep angle
        self.laser_speed  = 0.012          # radians per frame
        self.income_timer = pygame.time.get_ticks()
        self.born         = pygame.time.get_ticks()
        self._glow_cache_t = -1

    def update(self):
        global coins
        self.angle       += 0.003
        self.laser_angle += self.laser_speed
        now = pygame.time.get_ticks()
        if now - self.income_timer >= 1000:
            ticks = (now - self.income_timer) // 1000
            coins += self.INCOME_PER_SEC * ticks
            self.income_timer += ticks * 1000

    def _triangle_pts(self, cx, cy, size, angle):
        pts = []
        for k in range(3):
            a = angle + k * (2 * math.pi / 3) - math.pi / 2
            pts.append((cx + math.cos(a) * size, cy + math.sin(a) * size))
        return pts

    def draw(self, surface):
        now  = pygame.time.get_ticks()
        cx   = self.cx
        cy   = self.cy
        sz   = self.size
        ang  = self.angle
        t    = now / 1000.0

        # ── Outer glow rings (pulsing) ──────────────────────────────────────
        pulse = 0.5 + 0.5 * math.sin(t * 2.1)
        for r, a in [(sz*2.4, 18), (sz*2.0, 30), (sz*1.6, 45), (sz*1.2, 65)]:
            ir = int(r)
            if ir < 2: continue
            alpha = int(a * (0.7 + 0.3 * pulse))
            gs = pygame.Surface((ir*2, ir*2), pygame.SRCALPHA)
            pygame.draw.circle(gs, (220, 30, 30, alpha), (ir, ir), ir)
            surface.blit(gs, (cx - ir, cy - ir))

        # ── Triangle layers (thick outline → filled inner) ──────────────────
        pts_outer = self._triangle_pts(cx, cy, sz,        ang)
        pts_mid   = self._triangle_pts(cx, cy, sz * 0.92, ang)
        pts_inner = self._triangle_pts(cx, cy, sz * 0.72, ang)
        pts_fill  = self._triangle_pts(cx, cy, sz * 0.60, ang)

        # dark fill
        pygame.draw.polygon(surface, (8, 0, 0),       [(int(x),int(y)) for x,y in pts_outer])
        # gold/amber border stroke (thick)
        for p_list, thick, col in [
            (pts_outer, 6,  (200, 160, 20)),
            (pts_mid,   3,  (255, 210, 60)),
            (pts_inner, 2,  (255, 240, 120)),
        ]:
            ipts = [(int(x), int(y)) for x, y in p_list]
            pygame.draw.polygon(surface, col, ipts, thick)

        # ── Inner eye ───────────────────────────────────────────────────────
        eye_r  = int(sz * 0.30)
        eye_r2 = int(sz * 0.18)
        eye_r3 = int(sz * 0.09)

        # sclera glow
        for r2, a2 in [(eye_r + 12, 40), (eye_r + 6, 80), (eye_r, 130)]:
            gs2 = pygame.Surface((r2*2, r2*2), pygame.SRCALPHA)
            pygame.draw.circle(gs2, (255, 200, 0, a2), (r2, r2), r2)
            surface.blit(gs2, (cx - r2, cy - r2))
        pygame.draw.circle(surface, (255, 220, 40), (cx, cy), eye_r)

        # iris
        iris_pulse = 0.85 + 0.15 * math.sin(t * 3.3)
        ip = int(eye_r2 * iris_pulse)
        for r3, col3 in [(ip+4, (180, 60, 0)), (ip+2, (220, 80, 0)), (ip, (255, 120, 20))]:
            pygame.draw.circle(surface, col3, (cx, cy), r3)

        # pupil
        pp2 = int(eye_r3 * (0.9 + 0.1 * math.sin(t * 5.0)))
        pygame.draw.circle(surface, (5, 0, 0),     (cx, cy), pp2 + 2)
        pygame.draw.circle(surface, (0, 0, 0),     (cx, cy), pp2)
        # catchlight
        pygame.draw.circle(surface, (255, 255, 255), (cx - pp2//3, cy - pp2//3), max(1, pp2//4))

        # ── Radial gold lines from eye outward ──────────────────────────────
        num_spokes = 12
        for k in range(num_spokes):
            spoke_a = ang + k * (2 * math.pi / num_spokes)
            brightness = int(180 + 60 * math.sin(t * 2 + k * 0.5))
            ex = cx + int(math.cos(spoke_a) * sz * 0.55)
            ey = cy + int(math.sin(spoke_a) * sz * 0.55)
            pygame.draw.line(surface, (brightness, int(brightness*0.7), 0),
                             (cx, cy), (ex, ey), 1)

        # ── Corner decorations on triangle vertices ──────────────────────────
        for vx, vy in pts_outer:
            ivx, ivy = int(vx), int(vy)
            vp = 0.7 + 0.3 * math.sin(t * 2.5)
            vr = int(10 * vp)
            gs3 = pygame.Surface((vr*2+2, vr*2+2), pygame.SRCALPHA)
            pygame.draw.circle(gs3, (255, 200, 0, 180), (vr+1, vr+1), vr)
            surface.blit(gs3, (ivx - vr - 1, ivy - vr - 1))
            pygame.draw.circle(surface, (255, 240, 120), (ivx, ivy), max(2, vr//2))

        # ── Sweeping red laser ───────────────────────────────────────────────
        laser_len = int(math.hypot(GAME_WIDTH, HEIGHT) * 1.2)
        la = self.laser_angle
        lx2 = cx + int(math.cos(la) * laser_len)
        ly2 = cy + int(math.sin(la) * laser_len)
        pygame.draw.line(surface, (80, 0, 0),    (cx, cy), (lx2, ly2), 10)
        pygame.draw.line(surface, (200, 0, 0),   (cx, cy), (lx2, ly2), 5)
        pygame.draw.line(surface, (255, 60, 60), (cx, cy), (lx2, ly2), 2)
        # laser tip glow
        tip_pulse = 0.6 + 0.4 * math.sin(now / 80.0)
        tr2 = int(14 * tip_pulse)
        if tr2 > 1:
            tgs = pygame.Surface((tr2*2, tr2*2), pygame.SRCALPHA)
            pygame.draw.circle(tgs, (255, 80, 80, 200), (tr2, tr2), tr2)
            surface.blit(tgs, (lx2 - tr2, ly2 - tr2))

        # ── "All-seeing" text arc ────────────────────────────────────────────
        label = font.render("I L L U M I N A T E", True, (255, 215, 0))
        surface.blit(label, label.get_rect(center=(cx, cy + sz + 22)))


# ------------------ GRAVITY WELL SYSTEM ------------------
gravity_effects = []
_gravity_income_timer = 0
GRAVITY_INCOME_PER_SEC = 1_000_000_000_000   # 1 trillion/sec

class GravityOrb:
    """Single distortion orb orbiting the well."""
    __slots__ = ('angle','radius','speed','size','hue_off')
    def __init__(self, angle, radius, speed, size, hue_off):
        self.angle   = angle
        self.radius  = radius
        self.speed   = speed
        self.size    = size
        self.hue_off = hue_off

class GravityWellEffect:
    """Spectacular purple singularity with orbital particles and lens-warp rings."""
    __slots__ = ('bouncer','orbs','ring_angles','debris','income_timer','born','pulse')

    RING_COUNT = 5
    ORB_COUNT  = 24

    def __init__(self, bouncer):
        self.bouncer      = bouncer
        self.income_timer = pygame.time.get_ticks()
        self.born         = pygame.time.get_ticks()
        self.pulse        = random.uniform(0, 6.28)

        # Layered orbital rings — different tilt / speed / radius
        self.ring_angles = [random.uniform(0, 6.28) for _ in range(self.RING_COUNT)]

        # Orbiting glowing particles
        self.orbs = [
            GravityOrb(
                angle   = i * (6.28 / self.ORB_COUNT) + random.uniform(-0.2, 0.2),
                radius  = random.randint(28, 90),
                speed   = random.uniform(0.03, 0.09) * random.choice((-1, 1)),
                size    = random.randint(2, 7),
                hue_off = random.uniform(0, 1)
            )
            for i in range(self.ORB_COUNT)
        ]

        # Debris chunks (slow drifting shards)
        self.debris = [
            [random.uniform(0, 6.28),           # angle
             random.randint(50, 120),            # radius
             random.uniform(0.005, 0.02),        # speed
             random.randint(4, 10),              # width
             random.randint(2, 5),               # height
             random.uniform(0, 6.28)]            # tilt
            for _ in range(12)
        ]

    def _purple_hue(self, t, hue_off, alpha=255):
        """Cycle purple→magenta→violet."""
        r = int(160 + 80 * math.sin(t * 1.3 + hue_off * 6.28))
        g = int(0   + 30 * math.sin(t * 0.9 + hue_off * 6.28 + 1))
        b = int(220 + 35 * math.sin(t * 1.7 + hue_off * 6.28 + 2))
        return (max(0,min(255,r)), max(0,min(255,g)), max(0,min(255,b)))

    def update(self):
        global coins
        now = pygame.time.get_ticks()
        t   = now / 1000.0

        for k in range(self.RING_COUNT):
            self.ring_angles[k] += 0.008 * (1 + k * 0.4)

        for orb in self.orbs:
            orb.angle += orb.speed

        for d in self.debris:
            d[0] += d[2]

        if now - self.income_timer >= 1000:
            ticks = (now - self.income_timer) // 1000
            coins += GRAVITY_INCOME_PER_SEC * self.bouncer.gravity_purchases * ticks
            self.income_timer += ticks * 1000

    def draw(self, surface):
        b   = self.bouncer
        cx  = b.rect.centerx
        cy  = b.rect.centery
        now = pygame.time.get_ticks()
        t   = now / 1000.0
        pulse = 0.5 + 0.5 * math.sin(t * 2.4 + self.pulse)

        # ── 1. Deep warp rings (ellipses at different tilts) ─────────────────
        for k, ang in enumerate(self.ring_angles):
            base_r   = 55 + k * 22
            tilt     = ang * 0.6
            rx       = int(base_r)
            ry       = max(4, int(base_r * (0.18 + 0.12 * abs(math.sin(tilt)))))
            fade     = 1.0 - k * 0.12
            alpha_r  = int(90 * fade * (0.6 + 0.4 * pulse))
            ring_col = self._purple_hue(t, k * 0.2)
            surf_w   = rx * 2 + 4; surf_h = ry * 2 + 4
            gs = pygame.Surface((surf_w, surf_h), pygame.SRCALPHA)
            rc = (*ring_col, alpha_r)
            thick = max(1, 3 - k // 2)
            pygame.draw.ellipse(gs, rc, (2, 2, surf_w-4, surf_h-4), thick)
            rx_off = int(math.cos(tilt) * base_r * 0.3)
            ry_off = int(math.sin(tilt) * base_r * 0.1)
            surface.blit(gs, (cx - rx - 2 + rx_off, cy - ry - 2 + ry_off))

        # ── 2. Glow aura layers ───────────────────────────────────────────────
        for gr, ga in [(75, 70), (55, 110), (35, 160), (20, 210)]:
            gc = self._purple_hue(t, 0)
            ags = pygame.Surface((gr*2, gr*2), pygame.SRCALPHA)
            actual_a = int(ga * (0.7 + 0.3 * pulse))
            pygame.draw.circle(ags, (*gc, actual_a), (gr, gr), gr)
            surface.blit(ags, (cx - gr, cy - gr))

        # ── 3. Debris shards ─────────────────────────────────────────────────
        for d in self.debris:
            da  = d[0]; dr = d[1]; dw = d[3]; dh = d[4]; dtilt = d[5]
            dx  = cx + int(math.cos(da) * dr)
            dy  = cy + int(math.sin(da) * dr)
            srf = pygame.Surface((dw, dh), pygame.SRCALPHA)
            dc  = self._purple_hue(t, da / 6.28)
            srf.fill((*dc, 180))
            rot = pygame.transform.rotate(srf, math.degrees(dtilt + da))
            surface.blit(rot, rot.get_rect(center=(dx, dy)))

        # ── 4. Orbiting particles ─────────────────────────────────────────────
        for orb in self.orbs:
            ox  = cx + int(math.cos(orb.angle) * orb.radius)
            oy  = cy + int(math.sin(orb.angle) * orb.radius)
            oc  = self._purple_hue(t, orb.hue_off)
            # outer glow
            og  = pygame.Surface((orb.size*4, orb.size*4), pygame.SRCALPHA)
            pygame.draw.circle(og, (*oc, 90), (orb.size*2, orb.size*2), orb.size*2)
            surface.blit(og, (ox - orb.size*2, oy - orb.size*2))
            # bright core
            pygame.draw.circle(surface, oc,            (ox, oy), orb.size)
            pygame.draw.circle(surface, (255,255,255), (ox, oy), max(1, orb.size // 2))

        # ── 5. Central singularity ────────────────────────────────────────────
        # Dark core with purple rim
        core_r = int(14 + 4 * pulse)
        pygame.draw.circle(surface, (5, 0, 10),    (cx, cy), core_r + 5)
        pygame.draw.circle(surface, (5, 0, 10),    (cx, cy), core_r)
        rim_c = self._purple_hue(t, 0.5)
        pygame.draw.circle(surface, rim_c,         (cx, cy), core_r, 3)
        # Inner bright ring
        pygame.draw.circle(surface, (200, 100, 255), (cx, cy), max(3, core_r - 6), 2)
        # Tiny white hot centre
        pygame.draw.circle(surface, (240, 220, 255), (cx, cy), max(2, core_r // 3))

        # ── 6. Lens flare spikes (4 diagonal) ────────────────────────────────
        for spike_a in (0.785, 2.356, 3.927, 5.498):  # 45° intervals
            spike_len = int((45 + 20 * pulse))
            ex = cx + int(math.cos(spike_a) * spike_len)
            ey = cy + int(math.sin(spike_a) * spike_len)
            sc = self._purple_hue(t, spike_a / 6.28)
            pygame.draw.line(surface, (*sc, ), (cx, cy), (ex, ey), 2)

        # ── 7. "GRAVITY WELL" label ───────────────────────────────────────────
        lc = self._purple_hue(t, 0.7)
        lbl = font.render("GRAVITY WELL", True, lc)
        surface.blit(lbl, lbl.get_rect(center=(cx, cy + 110)))


def update_gravity_wells(dt, now):
    for eff in gravity_effects:
        eff.update()

def draw_gravity_wells(surface, now):
    for eff in gravity_effects:
        eff.draw(surface)


# ================== 3D CUBE MODE SYSTEM ==================
mode3d_active    = False
mode3d_effect    = None
_3d_income_timer = 0
MODE3D_INCOME_PER_SEC = 75_000_000_000_000

def _3d_rot(pts, rx, ry, rz):
    cx,sx = math.cos(rx),math.sin(rx)
    cy,sy = math.cos(ry),math.sin(ry)
    cz,sz = math.cos(rz),math.sin(rz)
    out = []
    for x,y,z in pts:
        y,z  = cx*y - sx*z, sx*y + cx*z
        x,z  = cy*x + sy*z, -sy*x + cy*z
        x,y  = cz*x - sz*y,  sz*x + cz*y
        out.append((x,y,z))
    return out

def _3d_proj(pts, rx, ry, rz, scx, scy, fov=900.0, z_off=800.0):
    rotated = _3d_rot(pts, rx, ry, rz)
    result  = []
    for x,y,z in rotated:
        w  = fov / (fov + z + z_off)
        result.append((scx + x*w, scy + y*w, z, w))
    return result


class GlitchLayer:
    def __init__(self):
        self.timer       = 0.0
        self.next_glitch = random.uniform(1.5, 4.0)
        self.active      = False
        self.duration    = 0.0
        self.strips      = []

    def update(self, dt):
        self.timer += dt
        if not self.active and self.timer >= self.next_glitch:
            self.active     = True
            self.duration   = random.uniform(0.06, 0.22)
            self.timer      = 0.0
            self.next_glitch = random.uniform(1.0, 5.0)
            n = random.randint(2, 7)
            self.strips = []
            for _ in range(n):
                y    = random.randint(0, HEIGHT - 20)
                h    = random.randint(4, 40)
                dx   = random.randint(-30, 30)
                tint = random.choice([
                    (255,0,0,60),(0,255,0,50),(0,100,255,60),(255,0,255,50),(0,0,0,80)
                ])
                self.strips.append((y, h, dx, tint))
        if self.active:
            self.duration -= dt
            if self.duration <= 0:
                self.active = False
                self.strips = []

    def draw(self, surface):
        if not self.active:
            return
        w = GAME_WIDTH
        for y, h, dx, tint in self.strips:
            clip = pygame.Rect(0, y, w, h)
            if clip.bottom > surface.get_height(): continue
            strip_surf = surface.subsurface(clip).copy()
            surface.blit(strip_surf, (dx, y))
            overlay = pygame.Surface((w, h), pygame.SRCALPHA)
            overlay.fill(tint)
            surface.blit(overlay, (0, y))
        if random.random() < 0.4:
            cy2 = random.randint(0, HEIGHT - 6)
            ch2 = random.randint(2, 8)
            clip2 = pygame.Rect(0, cy2, w, ch2)
            if clip2.bottom <= surface.get_height():
                try:
                    ca = surface.subsurface(clip2).copy()
                    r_shift = pygame.Surface((w, ch2), pygame.SRCALPHA)
                    r_shift.fill((255,0,0,40))
                    ca_r = ca.copy(); ca_r.blit(r_shift,(0,0))
                    surface.blit(ca_r,(4,cy2))
                    b_shift = pygame.Surface((w, ch2), pygame.SRCALPHA)
                    b_shift.fill((0,0,255,40))
                    ca_b = ca.copy(); ca_b.blit(b_shift,(0,0))
                    surface.blit(ca_b,(-4,cy2))
                except Exception:
                    pass


class Obj3DBouncer:
    def __init__(self, bouncer, half_world):
        self.b = bouncer
        self.base_hw = half_world
        self.sz = self._target_size()
        self.hw = max(40.0, self.base_hw - self.sz)
        self.x = random.uniform(-self.hw, self.hw)
        self.y = random.uniform(-self.hw, self.hw)
        self.z = random.uniform(-self.hw, self.hw)
        base2d_spd = max(1.0, math.hypot(self.b.speed_x, self.b.speed_y))
        spd      = max(85.0, min(300.0, base2d_spd * 0.45))
        ang      = random.uniform(0, math.pi*2)
        ang2     = random.uniform(0, math.pi*2)
        self.vx  = spd*math.cos(ang)*math.cos(ang2)
        self.vy  = spd*math.sin(ang)
        self.vz  = spd*math.cos(ang)*math.sin(ang2)
        self.rx  = 0.0; self.ry = 0.0; self.rz = 0.0
        self.rxv = random.uniform(-0.9, 0.9)
        self.ryv = random.uniform(-0.9, 0.9)
        self.rzv = random.uniform(-0.4, 0.4)
        self.trail = []
        self.hit_events = []

    def _target_size(self):
        min_sz = 6 if self.b.implosion_enabled else 30
        return max(min_sz, int(self.b.size * 0.38))

    def update(self, dt):
        self.sz = self._target_size()
        self.hw = max(40.0, self.base_hw - self.sz)
        self.hit_events.clear()
        if self.b.implosion_frozen:
            self.vx *= 0.82; self.vy *= 0.82; self.vz *= 0.82
            if abs(self.vx) < 1.0: self.vx = 0.0
            if abs(self.vy) < 1.0: self.vy = 0.0
            if abs(self.vz) < 1.0: self.vz = 0.0
        else:
            target = max(95.0, min(620.0, math.hypot(self.b.speed_x, self.b.speed_y) * 0.75))
            cur = math.sqrt(self.vx*self.vx + self.vy*self.vy + self.vz*self.vz)
            if cur < 1e-6:
                ang = random.uniform(0, _TWO_PI)
                ang2 = random.uniform(0, _TWO_PI)
                self.vx = math.cos(ang) * math.cos(ang2) * target
                self.vy = math.sin(ang) * target
                self.vz = math.cos(ang) * math.sin(ang2) * target
            else:
                new_mag = cur + (target - cur) * 0.35
                scale = new_mag / cur
                self.vx *= scale; self.vy *= scale; self.vz *= scale
            self.x += self.vx*dt; self.y += self.vy*dt; self.z += self.vz*dt
        self.rx += self.rxv*dt; self.ry += self.ryv*dt; self.rz += self.rzv*dt
        hw = self.hw
        if self.x < -hw:
            self.x = -hw
            self.vx = abs(self.vx)
            self.hit_events.append(((self.x, self.y, self.z), (1.0, 0.0, 0.0)))
        if self.x > hw:
            self.x = hw
            self.vx = -abs(self.vx)
            self.hit_events.append(((self.x, self.y, self.z), (-1.0, 0.0, 0.0)))
        if self.y < -hw:
            self.y = -hw
            self.vy = abs(self.vy)
            self.hit_events.append(((self.x, self.y, self.z), (0.0, 1.0, 0.0)))
        if self.y > hw:
            self.y = hw
            self.vy = -abs(self.vy)
            self.hit_events.append(((self.x, self.y, self.z), (0.0, -1.0, 0.0)))
        if self.z < -hw:
            self.z = -hw
            self.vz = abs(self.vz)
            self.hit_events.append(((self.x, self.y, self.z), (0.0, 0.0, 1.0)))
        if self.z > hw:
            self.z = hw
            self.vz = -abs(self.vz)
            self.hit_events.append(((self.x, self.y, self.z), (0.0, 0.0, -1.0)))
        self.trail.append((self.x, self.y, self.z))
        if len(self.trail) > 44: self.trail.pop(0)

    def draw(self, surface, rx, ry, rz, scx, scy, fov=900.0, z_off=800.0):
        col = self.b.color
        sz  = self.sz
        imp_eff = next((e for e in implosion_effects if e.owner is self.b), None)
        if imp_eff and imp_eff.phase != IMP_IDLE:
            cp = _3d_proj([(self.x, self.y, self.z)], rx, ry, rz, scx, scy, fov, z_off)[0]
            cpt = (int(cp[0]), int(cp[1]))
            phase = imp_eff.phase
            now = pygame.time.get_ticks()
            if goon_mode:
                core_col = (110, 255, 170)
                glow_col = (40, 140, 90)
            else:
                core_col = (210, 150, 255)
                glow_col = (90, 40, 150)

            if phase in (IMP_SHRINK, IMP_HOLD):
                if phase == IMP_SHRINK:
                    prog = min((now - imp_eff.phase_start) / max(1, IMPLOSION_SHRINK_MS), 1.0)
                else:
                    prog = 1.0
                beam_len = max(10, int((sz * 2.2 + 26) * (1.15 - 0.35 * prog)))
                beam_n = 10
                for bi in range(beam_n):
                    ang = now / 220.0 + bi * (_TWO_PI / beam_n)
                    ex = cpt[0] + int(math.cos(ang) * beam_len)
                    ey = cpt[1] + int(math.sin(ang) * beam_len)
                    pygame.draw.line(surface, glow_col, (ex, ey), cpt, 4)
                    pygame.draw.line(surface, core_col, (ex, ey), cpt, 2)
                rr = max(6, int((22 - 12 * prog) * max(0.6, cp[3] * 2.2)))
                pygame.draw.circle(surface, glow_col, cpt, rr + 7, 2)
                pygame.draw.circle(surface, core_col, cpt, rr + 2, 2)
                pygame.draw.circle(surface, (0, 0, 0), cpt, rr)
                pygame.draw.circle(surface, (255, 255, 255), cpt, max(2, rr // 3))
            elif phase == IMP_EXPLODE:
                prog = min((now - imp_eff.phase_start) / max(1, IMPLOSION_EXPLODE_MS), 1.0)
                rr = max(10, int((250 * prog + 10) * max(0.55, cp[3] * 2.1)))
                thick = max(1, int(10 * (1.0 - prog)))
                pygame.draw.circle(surface, (255, 255, 255), cpt, rr, thick)
                pygame.draw.circle(surface, core_col, cpt, max(4, int(rr * 0.6)), max(1, thick - 1))
            return

        CUBE_FACES = [(0,1,2,3),(4,5,6,7),(0,1,5,4),(2,3,7,6),(0,3,7,4),(1,2,6,5)]
        CUBE_EDGES = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
        FACE_NORMS = [(0,0,-1),(0,0,1),(0,-1,0),(0,1,0),(-1,0,0),(1,0,0)]

        local = [(dx*sz, dy*sz, dz*sz)
                 for dx,dy,dz in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
                                  (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
        spun_local = _3d_rot(local, self.rx, self.ry, self.rz)
        corners = [(self.x + px, self.y + py, self.z + pz) for px, py, pz in spun_local]
        proj = _3d_proj(corners, rx, ry, rz, scx, scy, fov, z_off)
        sp   = [(int(p[0]),int(p[1])) for p in proj]
        deps = [p[2] for p in proj]

        # Trail — draw before cube so cube appears on top
        if self.b.trail_enabled and len(self.trail) > 1:
            tr_proj = _3d_proj(self.trail, rx, ry, rz, scx, scy, fov, z_off)
            for ti in range(1, len(tr_proj)):
                fade = ti/len(tr_proj)
                ci = (ti * 3 + (pygame.time.get_ticks() // 35)) % len(TRAIL_COLORS)
                rb = TRAIL_COLORS[ci]
                tc = (int(rb[0] * fade), int(rb[1] * fade), int(rb[2] * fade))
                p0   = (int(tr_proj[ti-1][0]),int(tr_proj[ti-1][1]))
                p1   = (int(tr_proj[ti][0]),  int(tr_proj[ti][1]))
                glow = (int(tc[0] * 0.35), int(tc[1] * 0.35), int(tc[2] * 0.35))
                w = max(1, int(9 * fade))
                pygame.draw.line(surface, glow, p0, p1, w + 5)
                pygame.draw.line(surface, tc, p0, p1, w)

        # Faces — depth sorted, drawn directly (no per-face Surface alloc)
        face_d = [(sum(deps[k] for k in f)/4, fi, f) for fi,f in enumerate(CUBE_FACES)]
        face_d.sort(key=lambda x: x[0])
        light = (0.3, 0.6, 0.8)
        for avg_z, fi, face in face_d:
            nx,ny,nz = FACE_NORMS[fi]
            nr1 = _3d_rot([(nx, ny, nz)], self.rx, self.ry, self.rz)[0]
            nr  = _3d_rot([nr1], rx, ry, rz)[0]
            dot = nr[0]*light[0]+nr[1]*light[1]+nr[2]*light[2]
            br  = max(0.25, min(1.0, 0.4+0.6*dot))
            fc  = (int(col[0]*br), int(col[1]*br), int(col[2]*br))
            pts4 = [sp[k] for k in face]
            pygame.draw.polygon(surface, fc, pts4)

        # Edges
        for e0,e1 in CUBE_EDGES:
            pygame.draw.line(surface, (220,235,255), sp[e0], sp[e1], 1)

        # Bright highlight on nearest corner
        front_k = max(range(8), key=lambda k: deps[k])
        pygame.draw.circle(surface, (255,255,255), sp[front_k], 3)

        # Centre glow dot
        cp = _3d_proj([(self.x,self.y,self.z)], rx, ry, rz, scx, scy, fov, z_off)[0]
        cpt = (int(cp[0]), int(cp[1]))
        core_r = max(4, int(sz * 0.48))
        pulse = 0.8 + 0.2 * math.sin(pygame.time.get_ticks() / 120.0)
        core_col = (min(255, int(col[0] * pulse)),
                    min(255, int(col[1] * pulse)),
                    min(255, int(col[2] * pulse)))
        pygame.draw.circle(surface, core_col, cpt, core_r)
        pygame.draw.circle(surface, (255,255,255), cpt, max(2, int(sz*0.18)))

        if self.b.laser_enabled:
            pygame.draw.circle(surface, (255, 80, 80), cpt, core_r + 4, 2)
        if self.b.lightning_enabled:
            pygame.draw.circle(surface, (120, 180, 255), cpt, core_r + 8, 1)
        if self.b.implosion_enabled:
            pygame.draw.circle(surface, (170, 90, 255), cpt, core_r + 12, 1)


class Obj3DPrism:
    """Centered illuminati pyramid with an eye on the front face."""
    def __init__(self, x, y, z, power=1):
        self.x = x; self.y = y; self.z = z
        self.power = max(1, int(power))
        self.spin  = 0.0
        self.spinv = 0.38
        self.pulse = random.uniform(0, 6.28)
        self.laser_angle = random.uniform(0, 6.28)

    def update(self, dt):
        self.spin += self.spinv * dt
        self.laser_angle += 1.15 * dt

    def draw(self, surface, rx, ry, rz, scx, scy, t, fov=900.0, z_off=800.0):
        p = 0.5 + 0.5 * math.sin(t * 2.1 + self.pulse)
        bob = math.sin(t * 1.7 + self.pulse) * (6 + min(4, self.power))
        base_r = 84 + min(4, self.power - 1) * 8
        apex_h = 148 + min(4, self.power - 1) * 12
        y0 = self.y + bob

        # Square-base pyramid so it reads clearly as a 3D illuminati piece.
        ao = [self.spin + math.pi * 0.25 + k * math.pi * 0.5 for k in range(4)]
        base_y = y0 + apex_h * 0.38
        base = [(self.x + base_r * math.cos(a), base_y, self.z + base_r * math.sin(a)) for a in ao]
        apex = (self.x, y0 - apex_h * 0.72, self.z)
        verts = base + [apex]  # 0..3 base, 4 apex

        FACES = [(0,1,4), (1,2,4), (2,3,4), (3,0,4), (3,2,1,0)]
        EDGES = [(0,1),(1,2),(2,3),(3,0),(0,4),(1,4),(2,4),(3,4)]

        proj = _3d_proj(verts, rx, ry, rz, scx, scy, fov, z_off)
        sp = [(int(q[0]), int(q[1])) for q in proj]
        deps = [q[2] for q in proj]

        face_d = []
        for fi, face in enumerate(FACES):
            avg_z = sum(deps[k] for k in face) / len(face)
            fade = max(0.22, min(1.0, 0.48 + avg_z / 900.0))
            face_d.append((avg_z, fi, face, fade))
        face_d.sort(key=lambda x: x[0])

        for _, fi, face, fade in face_d:
            pts = [sp[k] for k in face]
            if fi == 4:  # base
                fc = (int(45 * fade), int(32 * fade), int(14 * fade))
            else:
                g1 = int((150 + 75 * p) * fade)
                g2 = int((115 + 60 * p) * fade)
                g3 = int((24 + 26 * p) * fade)
                fc = (max(30, g1), max(20, g2), max(6, g3))
            pygame.draw.polygon(surface, fc, pts)

        for e0, e1 in EDGES:
            pygame.draw.line(surface, (255, 225, 110), sp[e0], sp[e1], 2)
            pygame.draw.line(surface, (130, 90, 20), sp[e0], sp[e1], 1)

        # Put the eye on the face currently nearest to the camera.
        side_faces = FACES[:4]
        front_face = side_faces[max(range(4), key=lambda i: sum(deps[k] for k in side_faces[i]))]
        ew = (
            sum(verts[k][0] for k in front_face) / 3.0,
            sum(verts[k][1] for k in front_face) / 3.0,
            sum(verts[k][2] for k in front_face) / 3.0
        )
        ep = _3d_proj([ew], rx, ry, rz, scx, scy, fov, z_off)[0]
        eye_pt = (int(ep[0]), int(ep[1]))
        er = max(6, int((10 + 4 * p) * max(0.6, ep[3] * 1.8)))

        eg = max(8, int(er * 2.2))
        glow = pygame.Surface((eg * 2, eg * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow, (255, 200, 50, 85), (eg, eg), eg)
        surface.blit(glow, (eye_pt[0] - eg, eye_pt[1] - eg))

        pygame.draw.circle(surface, (255, 220, 55), eye_pt, er)
        pygame.draw.circle(surface, (255, 130, 20), eye_pt, max(3, er // 2))
        pygame.draw.circle(surface, (0, 0, 0), eye_pt, max(2, er // 4))
        pygame.draw.circle(surface, (255, 255, 255),
                           (eye_pt[0] - max(1, er // 4), eye_pt[1] - max(1, er // 4)),
                           max(1, er // 6))
        for vk in front_face:
            pygame.draw.line(surface, (175, 125, 30), eye_pt, sp[vk], 1)

        # Bring back the illuminate laser for 3D mode.
        beam_len = 220 + int(40 * p)
        lx = ew[0] + math.cos(self.laser_angle) * beam_len
        lz = ew[2] + math.sin(self.laser_angle) * beam_len
        ly = ew[1] + math.sin(t * 1.5 + self.pulse) * 16
        lp = _3d_proj([(lx, ly, lz)], rx, ry, rz, scx, scy, fov, z_off)[0]
        lpt = (int(lp[0]), int(lp[1]))
        pygame.draw.line(surface, (80, 0, 0), eye_pt, lpt, 7)
        pygame.draw.line(surface, (210, 0, 0), eye_pt, lpt, 4)
        pygame.draw.line(surface, (255, 80, 80), eye_pt, lpt, 2)
        tr = max(3, int(8 * (0.8 + 0.2 * p)))
        tip = pygame.Surface((tr * 2, tr * 2), pygame.SRCALPHA)
        pygame.draw.circle(tip, (255, 80, 80, 180), (tr, tr), tr)
        surface.blit(tip, (lpt[0] - tr, lpt[1] - tr))


class Obj3DFactory:
    def __init__(self, wx, half_world, wz=0.0):
        self.x = wx; self.y = half_world*0.75; self.z = wz
        self.pulse = random.uniform(0,6.28)
        self.gear = random.uniform(0, 6.28)
        self.smoke = [self._spawn_smoke() for _ in range(8)]

    def _spawn_smoke(self):
        return [
            self.x + random.uniform(-24, 24),
            self.y - 96 - random.uniform(0, 26),
            self.z + random.uniform(-10, 10),
            random.uniform(18, 30),   # rise speed
            random.uniform(7, 14),    # base radius
            random.uniform(0.6, 1.0), # life
            random.uniform(-4, 4),
            random.uniform(-4, 4),
        ]

    def update(self, dt):
        self.gear += 1.5 * dt
        for puff in self.smoke:
            puff[0] += puff[6] * dt
            puff[2] += puff[7] * dt
            puff[1] -= puff[3] * dt
            puff[5] -= 0.24 * dt
            if puff[5] <= 0.0 or puff[1] < self.y - 180:
                puff[:] = self._spawn_smoke()

    def draw(self, surface, rx, ry, rz, scx, scy, t, fov=900.0, z_off=800.0):
        p = 0.6 + 0.4 * math.sin(t * 1.8 + self.pulse)

        def draw_box(cx, cy, cz, hw, hh, hd, face_cols, edge_col):
            corners = [
                (cx-hw,cy-hh,cz-hd),(cx+hw,cy-hh,cz-hd),(cx+hw,cy+hh,cz-hd),(cx-hw,cy+hh,cz-hd),
                (cx-hw,cy-hh,cz+hd),(cx+hw,cy-hh,cz+hd),(cx+hw,cy+hh,cz+hd),(cx-hw,cy+hh,cz+hd),
            ]
            faces = [(0,1,2,3),(4,5,6,7),(0,1,5,4),(2,3,7,6),(0,3,7,4),(1,2,6,5)]
            edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
            proj = _3d_proj(corners, rx, ry, rz, scx, scy, fov, z_off)
            sp = [(int(q[0]), int(q[1])) for q in proj]
            deps = [q[2] for q in proj]
            face_d = [(sum(deps[k] for k in f) / 4.0, fi, f) for fi, f in enumerate(faces)]
            face_d.sort(key=lambda x: x[0])
            for _, fi, face in face_d:
                pygame.draw.polygon(surface, face_cols[fi], [sp[k] for k in face])
            for e0, e1 in edges:
                pygame.draw.line(surface, edge_col, sp[e0], sp[e1], 1)
            return sp

        body_cols = [(52, 62, 72), (80, 92, 108), (65, 76, 90),
                     (40, 48, 58), (58, 68, 80), (72, 84, 98)]
        draw_box(self.x, self.y, self.z, 42, 50, 30, body_cols, (130, 150, 170))

        roof_cols = [(34, 42, 52), (54, 64, 76), (44, 52, 64),
                     (28, 34, 44), (46, 56, 68), (58, 68, 82)]
        draw_box(self.x, self.y - 58, self.z, 48, 8, 34, roof_cols, (160, 175, 195))

        # Three chimneys on the roof.
        for i, ox in enumerate((-24, 0, 24)):
            h = 18 + i * 8
            ch_cols = [(40, 48, 58), (62, 72, 84), (48, 58, 70),
                       (34, 40, 50), (44, 52, 62), (56, 66, 78)]
            draw_box(self.x + ox, self.y - 76 - h * 0.5, self.z - 6, 6, h * 0.5, 6,
                     ch_cols, (155, 170, 185))

        # Front glowing windows.
        for row in range(2):
            wy = self.y - 18 + row * 22
            for ox in (-20, 0, 20):
                wp = _3d_proj([(self.x + ox, wy, self.z - 31)], rx, ry, rz, scx, scy, fov, z_off)[0]
                scale = max(0.45, wp[3] * 2.0)
                ww = max(4, int(8 * scale))
                wh = max(3, int(6 * scale))
                flick = 0.75 + 0.25 * math.sin(t * 7.3 + ox * 0.2 + row)
                wc = (int(255 * flick), int(160 * flick), 0)
                wr = pygame.Rect(int(wp[0] - ww // 2), int(wp[1] - wh // 2), ww, wh)
                pygame.draw.rect(surface, (15, 15, 15), wr)
                pygame.draw.rect(surface, wc, wr.inflate(-2, -2))
                pygame.draw.rect(surface, (200, 200, 200), wr, 1)

        # Front gear detail.
        gp = _3d_proj([(self.x, self.y + 24, self.z - 31)], rx, ry, rz, scx, scy, fov, z_off)[0]
        gr = max(5, int(11 * max(0.55, gp[3] * 2.1)))
        gear_pts = []
        for k in range(16):
            a = self.gear + k * (math.pi / 8)
            rad = gr + 3 if k % 2 == 0 else gr - 2
            gear_pts.append((int(gp[0] + math.cos(a) * rad), int(gp[1] + math.sin(a) * rad)))
        pygame.draw.polygon(surface, (170, 128, 32), gear_pts)
        pygame.draw.circle(surface, (20, 20, 20), (int(gp[0]), int(gp[1])), max(2, gr - 4))
        pygame.draw.circle(surface, (220, 180, 60), (int(gp[0]), int(gp[1])), max(1, gr // 4))

        # Smokestack puffs.
        for sx, sy, sz3, _, rad, life, _, _ in self.smoke:
            sp = _3d_proj([(sx, sy, sz3)], rx, ry, rz, scx, scy, fov, z_off)[0]
            sr = max(2, int(rad * max(0.35, sp[3] * 2.0)))
            sa = max(0, int(105 * life))
            sg = pygame.Surface((sr * 2, sr * 2), pygame.SRCALPHA)
            gc = int(120 + 70 * life)
            pygame.draw.circle(sg, (gc, gc, gc, sa), (sr, sr), sr)
            surface.blit(sg, (int(sp[0]) - sr, int(sp[1]) - sr))


class Obj3DDonutRing:
    def __init__(self, owners, half_world):
        self.owners = owners
        self.half = half_world
        self.spin = random.uniform(0, _TWO_PI)
        self.wobble = random.uniform(0, _TWO_PI)
        self.ring_goons = []
        self.hit_glows = []

    def _target_count(self):
        cnt = sum(max(0, b.donut_ring_count) for b in self.owners)
        return max(0, min(DONUT_GOON_MAX, cnt))

    def _torus_dims(self):
        # Keep this uniform so the donut is evenly sized and always around the cube.
        tube = max(56.0, self.half * 0.16)
        major = self.half * math.sqrt(2.0) + tube + 26.0
        return major, tube

    def _spawn_ring_goon(self):
        major, tube = self._torus_dims()
        inner = tube * 0.82
        u = random.uniform(0.0, _TWO_PI)
        v = random.uniform(0.0, _TWO_PI)
        # Uniform-ish fill inside tube cross-section.
        rr = math.sqrt(random.random()) * inner * 0.92
        x = (major + rr * math.cos(v)) * math.cos(u)
        y = rr * math.sin(v)
        z = (major + rr * math.cos(v)) * math.sin(u)
        speed = random.uniform(430.0, 610.0)
        # Strong forward tangent component makes donut-goons feel fast.
        tx, ty, tz = -math.sin(u), 0.0, math.cos(u)
        a = random.uniform(0.0, _TWO_PI)
        b = random.uniform(-0.6, 0.6)
        rx = math.cos(a) * math.cos(b)
        ry = math.sin(b)
        rz = math.sin(a) * math.cos(b)
        vx = tx * speed * 0.78 + rx * speed * 0.46
        vy = ty * speed * 0.78 + ry * speed * 0.46
        vz = tz * speed * 0.78 + rz * speed * 0.46
        vm = math.sqrt(max(1e-9, vx * vx + vy * vy + vz * vz))
        return {
            "x": x, "y": y, "z": z,
            "vx": vx / vm * speed,
            "vy": vy / vm * speed,
            "vz": vz / vm * speed,
            "trail": [(x, y, z)],
            "hue": random.randint(0, max(1, len(TRAIL_COLORS) - 1))
        }

    def _sync_ring_goons(self):
        target = self._target_count()
        while len(self.ring_goons) < target:
            self.ring_goons.append(self._spawn_ring_goon())
        if len(self.ring_goons) > target:
            del self.ring_goons[target:]

    def _collide_torus(self, g, major, inner_tube):
        x, y, z = g["x"], g["y"], g["z"]
        rho = math.hypot(x, z)
        if rho < 1e-6:
            x = major
            z = 0.0
            rho = major
        rd = rho - major
        dist = math.sqrt(rd * rd + y * y)
        if dist <= inner_tube:
            g["x"], g["y"], g["z"] = x, y, z
            return False

        inv_rho = 1.0 / max(rho, 1e-6)
        inv_dist = 1.0 / max(dist, 1e-6)
        nx = (x * inv_rho) * rd * inv_dist
        ny = y * inv_dist
        nz = (z * inv_rho) * rd * inv_dist

        # Push back just inside the donut tube boundary.
        excess = dist - inner_tube
        x -= nx * (excess + 0.25)
        y -= ny * (excess + 0.25)
        z -= nz * (excess + 0.25)
        g["x"], g["y"], g["z"] = x, y, z

        dot = g["vx"] * nx + g["vy"] * ny + g["vz"] * nz
        g["vx"] -= 2.0 * dot * nx
        g["vy"] -= 2.0 * dot * ny
        g["vz"] -= 2.0 * dot * nz
        return True

    def update(self, dt):
        self.spin += 0.58 * dt
        self.wobble += 1.05 * dt
        self._sync_ring_goons()

        major, tube = self._torus_dims()
        inner_tube = tube * 0.82
        target_speed = 470.0 + min(280.0, self._target_count() * 14.0)
        for g in self.ring_goons:
            vx, vy, vz = g["vx"], g["vy"], g["vz"]
            spd = math.sqrt(vx * vx + vy * vy + vz * vz)
            if spd < 1e-6:
                a = random.uniform(0.0, _TWO_PI)
                b = random.uniform(0.0, _TWO_PI)
                g["vx"] = math.cos(a) * math.cos(b) * target_speed
                g["vy"] = math.sin(a) * target_speed
                g["vz"] = math.cos(a) * math.sin(b) * target_speed
            else:
                s = (spd + (target_speed - spd) * 0.24) / spd
                g["vx"] *= s
                g["vy"] *= s
                g["vz"] *= s

            g["x"] += g["vx"] * dt
            g["y"] += g["vy"] * dt
            g["z"] += g["vz"] * dt

            bounced = self._collide_torus(g, major, inner_tube)
            # Second pass prevents tunneling with larger dt spikes.
            if self._collide_torus(g, major, inner_tube):
                bounced = True

            g["trail"].append((g["x"], g["y"], g["z"]))
            if len(g["trail"]) > 12:
                g["trail"].pop(0)

            if bounced:
                self.hit_glows.append({
                    "x": g["x"], "y": g["y"], "z": g["z"],
                    "life": 0.35, "r": 6.0
                })

        i = 0
        while i < len(self.hit_glows):
            hg = self.hit_glows[i]
            hg["life"] -= dt
            hg["r"] += dt * 90.0
            if hg["life"] <= 0.0:
                self.hit_glows[i] = self.hit_glows[-1]
                self.hit_glows.pop()
            else:
                i += 1

    def draw(self, surface, rx, ry, rz, scx, scy, t, fov=900.0, z_off=800.0, layer="all"):
        cnt = self._target_count()
        if cnt <= 0:
            return

        # Ring wraps around the whole 3D cube.
        cx, cy, cz = 0.0, 0.0, 0.0
        major, tube = self._torus_dims()
        pulse = 0.65 + 0.35 * math.sin(self.wobble + t * 2.1)

        if goon_mode:
            c_ring = (55, 230, 165)
            c_core = (180, 255, 230)
        else:
            c_ring = (210, 125, 255)
            c_core = (245, 220, 255)

        # True torus mesh (uniform tube width all around).
        major_n = 22
        minor_n = 12

        verts3 = []
        for iu in range(major_n):
            u = self.spin + iu * (_TWO_PI / major_n)
            cu = math.cos(u)
            su = math.sin(u)
            for iv in range(minor_n):
                v = iv * (_TWO_PI / minor_n)
                cv = math.cos(v)
                sv = math.sin(v)
                rr = major + tube * cv
                x = rr * cu
                y = tube * sv
                z = rr * su
                verts3.append((cx + x, cy + y, cz + z))

        pr = _3d_proj(verts3, rx, ry, rz, scx, scy, fov, z_off)
        sp = [(int(q[0]), int(q[1])) for q in pr]
        dep = [q[2] for q in pr]

        def vidx(iu, iv):
            return (iu % major_n) * minor_n + (iv % minor_n)

        faces = []
        for iu in range(major_n):
            for iv in range(minor_n):
                a = vidx(iu, iv)
                b = vidx(iu + 1, iv)
                c = vidx(iu + 1, iv + 1)
                d = vidx(iu, iv + 1)
                avg = (dep[a] + dep[b] + dep[c] + dep[d]) * 0.25
                if layer == "back" and avg < 0.0:
                    continue
                if layer == "front" and avg >= 0.0:
                    continue
                shade = 0.52 + 0.42 * (0.5 + 0.5 * math.sin((iv / minor_n) * _TWO_PI + self.wobble))
                rc = (
                    min(255, int(c_ring[0] * shade * pulse)),
                    min(255, int(c_ring[1] * shade * pulse)),
                    min(255, int(c_ring[2] * shade * pulse)),
                )
                faces.append((avg, (a, b, c, d), rc))
        faces.sort(key=lambda x: x[0])
        for _, face, rc in faces:
            pts = [sp[k] for k in face]
            pygame.draw.polygon(surface, rc, pts)
            pygame.draw.polygon(surface, (int(rc[0] * 0.55), int(rc[1] * 0.55), int(rc[2] * 0.55)), pts, 1)

        rc = (int(c_ring[0] * pulse), int(c_ring[1] * pulse), int(c_ring[2] * pulse))
        # Fast ring-goons stay confined inside the donut volume.
        if self.ring_goons:
            gproj = _3d_proj([(g["x"], g["y"], g["z"]) for g in self.ring_goons],
                             rx, ry, rz, scx, scy, fov, z_off)
            order = sorted(range(len(self.ring_goons)), key=lambda i: gproj[i][2])
            for idx in order:
                g = self.ring_goons[idx]
                gp = gproj[idx]
                if layer == "back" and gp[2] < 0.0:
                    continue
                if layer == "front" and gp[2] >= 0.0:
                    continue
                s = max(4, int(12 * max(0.45, gp[3] * 2.0)))
                px, py = int(gp[0]), int(gp[1])
                # Rainbow trail in 3D.
                if len(g["trail"]) > 1:
                    tp = _3d_proj(g["trail"], rx, ry, rz, scx, scy, fov, z_off)
                    for ti in range(1, len(tp)):
                        fade = ti / len(tp)
                        ci = (g["hue"] + ti * 3 + int(t * 20)) % len(TRAIL_COLORS)
                        col = TRAIL_COLORS[ci]
                        tc = (int(col[0] * fade), int(col[1] * fade), int(col[2] * fade))
                        p0 = (int(tp[ti - 1][0]), int(tp[ti - 1][1]))
                        p1 = (int(tp[ti][0]), int(tp[ti][1]))
                        pygame.draw.line(surface, (int(tc[0] * 0.3), int(tc[1] * 0.3), int(tc[2] * 0.3)), p0, p1, max(1, int(5 * fade)))
                        pygame.draw.line(surface, tc, p0, p1, max(1, int(3 * fade)))
                glow_r = s + 6
                glow = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
                base = TRAIL_COLORS[g["hue"] % len(TRAIL_COLORS)]
                pygame.draw.circle(glow, (base[0], base[1], base[2], 120), (glow_r, glow_r), glow_r)
                surface.blit(glow, (px - glow_r, py - glow_r))
                pygame.draw.circle(surface, rc, (px, py), s)
                pygame.draw.circle(surface, c_core, (px, py), max(2, s - 3))
                pygame.draw.circle(surface, (255, 255, 255), (px, py), max(1, s // 3))

        # Wall-hit pulses for ring-goons.
        for hg in self.hit_glows:
            pp = _3d_proj([(hg["x"], hg["y"], hg["z"])], rx, ry, rz, scx, scy, fov, z_off)[0]
            if layer == "back" and pp[2] < 0.0:
                continue
            if layer == "front" and pp[2] >= 0.0:
                continue
            fade = max(0.0, min(1.0, hg["life"] / 0.35))
            rr = max(2, int(hg["r"] * max(0.5, pp[3] * 2.0)))
            c1 = (int(rc[0] * fade), int(rc[1] * fade), int(rc[2] * fade))
            pygame.draw.circle(surface, c1, (int(pp[0]), int(pp[1])), rr, max(1, int(3 * fade)))

        # Center glow pulse.
        if layer != "back":
            cp = _3d_proj([(cx, cy, cz)], rx, ry, rz, scx, scy, fov, z_off)[0]
            cr = max(8, int((18 + cnt * 0.9) * max(0.45, cp[3] * 2.0)))
            glow = pygame.Surface((cr * 4, cr * 4), pygame.SRCALPHA)
            pygame.draw.circle(glow, (*c_ring, 120), (cr * 2, cr * 2), cr * 2)
            surface.blit(glow, (int(cp[0]) - cr * 2, int(cp[1]) - cr * 2))
            pygame.draw.circle(surface, c_core, (int(cp[0]), int(cp[1])), max(2, cr // 2))


class Obj3DGoonGod:
    """
    A fully 3D Greek-god Zeus - Corinthian helmet, muscular torso in bronze armour,
    toga drape, beard, face with nose/brow ridges, and a crackling lightning bolt.
    He is anchored in CAMERA space on the LEFT side so he is always visible.
    """

    def __init__(self, power, half_world):
        self.power = max(1, int(power))
        self.half = half_world
        self.t = 0.0
        self.hand_t = 0.0
        self.cam_rx = 0.0
        self.cam_ry = 0.0
        self.cam_rz = 0.0
        self.spawn_acc = 0.0
        self.burst_timer = 0.35
        self.spray = []
        self.cube_marks = []
        # lightning bolt verts (local Zeus space, regenerated each frame)
        self._bolt_pts = []
        self._bolt_timer = 0.0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _camera_to_world(self, cx, cy, cz, rx, ry, rz):
        """Invert camera rotation: camera-space -> world-space."""
        cxx, sxx = math.cos(rx), math.sin(rx)
        cyy, syy = math.cos(ry), math.sin(ry)
        czz, szz = math.cos(rz), math.sin(rz)
        x0, y0 = czz * cx + szz * cy, -szz * cx + czz * cy
        x0, z0 = cyy * x0 - syy * cz, syy * x0 + cyy * cz
        y0, z0 = cxx * y0 + sxx * z0, -sxx * y0 + cxx * z0
        return (x0, y0, z0)

    def _root_world(self, rx, ry, rz):
        """
        Zeus is always pinned to the left side of the screen in camera space,
        regardless of cube rotation. We use a fixed camera-space offset and
        un-rotate it to get the world position.
        """
        s = self._scale()
        # Camera-space: left of cube, slightly above centre, and behind the cube
        cam_x = -self.half * 1.70
        cam_y = self.half * 0.12
        cam_z = -self.half * 0.45
        return self._camera_to_world(cam_x, cam_y, cam_z, rx, ry, rz)

    def _scale(self):
        return self.half * (1.30 + min(0.75, self.power * 0.040))

    def _hand_world(self, rx, ry, rz):
        """Hand positioned at waist in camera space."""
        s = self.half * 0.28
        rx0, ry0, rz0 = self._root_world(rx, ry, rz)
        # In camera space the waist is slightly below and forward of root
        cx, cy, cz = (
            -self.half * 1.70,
            self.half * 0.12 + s * (0.78 + 0.18 * math.sin(self.hand_t)),
            -self.half * 0.45 + s * 0.10,
        )
        wx, wy, wz = self._camera_to_world(cx, cy, cz, rx, ry, rz)
        return (wx, wy, wz)

    def _random_unit(self):
        uy = random.uniform(-1.0, 1.0)
        a = random.uniform(0.0, _TWO_PI)
        rr = math.sqrt(max(0.0, 1.0 - uy * uy))
        return (math.cos(a) * rr, uy, math.sin(a) * rr)

    # ------------------------------------------------------------------
    # Spray / mark helpers (unchanged logic, just uses new _hand_world)
    # ------------------------------------------------------------------

    def _spawn_spray(self, hx, hy, hz, mode="mix"):
        hw = self.half
        if mode == "mix":
            r = random.random()
            mode = "cube" if r < 0.45 else ("burst" if r < 0.78 else "wide")

        if mode == "cube":
            face = random.randint(0, 5)
            if face == 0:
                tx, ty, tz = (hw, random.uniform(-hw, hw), random.uniform(-hw, hw))
            elif face == 1:
                tx, ty, tz = (-hw, random.uniform(-hw, hw), random.uniform(-hw, hw))
            elif face == 2:
                tx, ty, tz = (random.uniform(-hw, hw), hw, random.uniform(-hw, hw))
            elif face == 3:
                tx, ty, tz = (random.uniform(-hw, hw), -hw, random.uniform(-hw, hw))
            elif face == 4:
                tx, ty, tz = (random.uniform(-hw, hw), random.uniform(-hw, hw), hw)
            else:
                tx, ty, tz = (random.uniform(-hw, hw), random.uniform(-hw, hw), -hw)
            dx, dy, dz = tx - hx, ty - hy, tz - hz
            dm = math.sqrt(max(1e-9, dx * dx + dy * dy + dz * dz))
            nx, ny, nz = dx / dm, dy / dm, dz / dm
            speed = random.uniform(520.0, 860.0)
        elif mode == "burst":
            nx, ny, nz = self._random_unit()
            ny *= 0.85
            nm = math.sqrt(max(1e-9, nx * nx + ny * ny + nz * nz))
            nx, ny, nz = nx / nm, ny / nm, nz / nm
            speed = random.uniform(420.0, 920.0)
        else:
            tx = hx + random.uniform(-hw * 2.2, hw * 2.2)
            ty = hy + random.uniform(-hw * 1.9, hw * 1.9)
            tz = hz + random.uniform(-hw * 2.5, hw * 1.2)
            dx, dy, dz = tx - hx, ty - hy, tz - hz
            dm = math.sqrt(max(1e-9, dx * dx + dy * dy + dz * dz))
            nx, ny, nz = dx / dm, dy / dm, dz / dm
            speed = random.uniform(360.0, 760.0)

        spread = 0.30 if mode != "cube" else 0.18
        nx += random.uniform(-spread, spread)
        ny += random.uniform(-spread, spread)
        nz += random.uniform(-spread, spread)
        nm = math.sqrt(max(1e-9, nx * nx + ny * ny + nz * nz))
        nx, ny, nz = nx / nm, ny / nm, nz / nm
        self.spray.append({
            "x": hx, "y": hy, "z": hz,
            "vx": nx * speed, "vy": ny * speed, "vz": nz * speed,
            "life": random.uniform(0.70, 1.35),
            "trail": [(hx, hy, hz)],
            "size": random.uniform(2.0, 5.2),
        })

    def _mark_cube_hit(self, x, y, z):
        hw = self.half
        ax, ay, az = abs(x), abs(y), abs(z)
        if ax >= ay and ax >= az:
            x = hw if x >= 0 else -hw
        elif ay >= ax and ay >= az:
            y = hw if y >= 0 else -hw
        else:
            z = hw if z >= 0 else -hw
        self.cube_marks.append({
            "x": x, "y": y, "z": z,
            "life": random.uniform(0.95, 1.35),
            "r": random.uniform(5.0, 11.0),
            "grow": random.uniform(18.0, 34.0),
        })
        if len(self.cube_marks) > 300:
            del self.cube_marks[:-300]

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, dt, cam_rx=None, cam_ry=None, cam_rz=None):
        if cam_rx is not None:
            self.cam_rx, self.cam_ry, self.cam_rz = cam_rx, cam_ry, cam_rz
        self.t += dt
        self.hand_t += dt * (1.55 + min(1.30, self.power * 0.05))

        # Regenerate jagged lightning bolt every 0.18 s
        self._bolt_timer -= dt
        if self._bolt_timer <= 0.0:
            self._bolt_timer = 0.18
            n = 10
            self._bolt_pts = []
            y0 = 0.0
            for k in range(n + 1):
                t_frac = k / n
                self._bolt_pts.append((
                    random.uniform(-6, 6),
                    y0 - t_frac * 90,
                    random.uniform(-4, 4),
                ))

        hx, hy, hz = self._hand_world(self.cam_rx, self.cam_ry, self.cam_rz)

        spray_rate = min(130.0, 46.0 + self.power * 5.2)
        self.spawn_acc += spray_rate * dt
        while self.spawn_acc >= 1.0 and len(self.spray) < 460:
            self._spawn_spray(hx, hy, hz, "mix")
            self.spawn_acc -= 1.0

        self.burst_timer -= dt
        if self.burst_timer <= 0.0:
            burst_count = min(96, 26 + self.power * 3)
            for _ in range(burst_count):
                if len(self.spray) >= 460:
                    break
                self._spawn_spray(hx, hy, hz, "burst")
            self.burst_timer = random.uniform(0.22, 0.52)

        hw = self.half
        i = 0
        while i < len(self.spray):
            p = self.spray[i]
            drag = max(0.0, 1.0 - dt * 0.20)
            p["vx"] *= drag
            p["vy"] *= drag
            p["vz"] *= drag
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["z"] += p["vz"] * dt
            p["vy"] += 90.0 * dt
            p["life"] -= dt * 0.88
            p["trail"].append((p["x"], p["y"], p["z"]))
            if len(p["trail"]) > 9:
                p["trail"].pop(0)
            inside = abs(p["x"]) <= hw and abs(p["y"]) <= hw and abs(p["z"]) <= hw
            if inside:
                self._mark_cube_hit(p["x"], p["y"], p["z"])
                self.spray[i] = self.spray[-1]
                self.spray.pop()
                continue
            if (p["life"] <= 0 or abs(p["x"]) > hw * 2.7 or
                abs(p["y"]) > hw * 2.7 or abs(p["z"]) > hw * 3.2):
                self.spray[i] = self.spray[-1]
                self.spray.pop()
                continue
            i += 1

        j = 0
        while j < len(self.cube_marks):
            mk = self.cube_marks[j]
            mk["life"] -= dt * 0.62
            mk["r"] += mk["grow"] * dt
            if mk["life"] <= 0.0:
                self.cube_marks[j] = self.cube_marks[-1]
                self.cube_marks.pop()
            else:
                j += 1

    # ------------------------------------------------------------------
    # Draw helpers
    # ------------------------------------------------------------------

    def _proj1(self, x, y, z, rx, ry, rz, scx, scy, fov, z_off):
        """Project a single world point to screen."""
        p = _3d_proj([(x, y, z)], rx, ry, rz, scx, scy, fov, z_off)[0]
        return int(p[0]), int(p[1]), p[3]  # sx, sy, scale

    def _draw_ellipse_alpha(self, surface, col_rgb, alpha, cx, cy, rx, ry):
        if rx < 1 or ry < 1:
            return
        s = pygame.Surface((rx * 2, ry * 2), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (*col_rgb, alpha), (0, 0, rx * 2, ry * 2))
        surface.blit(s, (cx - rx, cy - ry))

    def _draw_circle_glow(self, surface, col_rgb, cx, cy, r, alpha=100):
        if r < 1:
            return
        s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*col_rgb, alpha), (r, r), r)
        surface.blit(s, (cx - r, cy - r))

    # ------------------------------------------------------------------
    # Main draw
    # ------------------------------------------------------------------

    def draw(self, surface, rx, ry, rz, scx, scy, t, fov=900.0, z_off=800.0, layer="all"):
        """
        Draw Zeus fully in 3D. layer="behind" draws body, layer="fx" draws spray.
        The method is also called with layer="all" from legacy call sites.
        """
        # Root world position (always left of camera)
        wx, wy, wz = self._root_world(rx, ry, rz)
        s = self._scale()

        # Build a local-to-world function that cancels camera rotation so Zeus
        # never tilts with the cube - he always stands upright.
        cxx, sxx = math.cos(rx), math.sin(rx)
        cyy, syy = math.cos(ry), math.sin(ry)
        czz, szz = math.cos(rz), math.sin(rz)

        def lw(lx, ly, lz):
            """Local Zeus-body offset -> world coords (camera rotation cancelled)."""
            # Invert camera rotation (ZYX)
            x0, y0 = czz * lx + szz * ly, -szz * lx + czz * ly
            x0, z0 = cyy * x0 - syy * lz, syy * x0 + cyy * lz
            y0, z0 = cxx * y0 + sxx * z0, -sxx * y0 + cxx * z0
            return (wx + x0, wy + y0, wz + z0)

        def p1(lx, ly, lz):
            """Local -> projected screen point (sx, sy, scale)."""
            wpt = lw(lx, ly, lz)
            pp = _3d_proj([wpt], rx, ry, rz, scx, scy, fov, z_off)[0]
            return int(pp[0]), int(pp[1]), max(0.3, pp[3] * 2.2)

        def pline(surface, col, pts_local, w=2):
            """Draw a polyline through local-space points."""
            if len(pts_local) < 2:
                return
            wpts = [lw(*pt) for pt in pts_local]
            proj = _3d_proj(wpts, rx, ry, rz, scx, scy, fov, z_off)
            sp = [(int(q[0]), int(q[1])) for q in proj]
            for i in range(1, len(sp)):
                pygame.draw.line(surface, col, sp[i - 1], sp[i], w)

        def pfill(surface, col, pts_local):
            """Draw a filled polygon through local-space points."""
            wpts = [lw(*pt) for pt in pts_local]
            proj = _3d_proj(wpts, rx, ry, rz, scx, scy, fov, z_off)
            sp = [(int(q[0]), int(q[1])) for q in proj]
            if len(sp) >= 3:
                pygame.draw.polygon(surface, col, sp)

        def pfill_outline(surface, col, outline_col, pts_local, bw=1):
            pfill(surface, col, pts_local)
            wpts = [lw(*pt) for pt in pts_local]
            proj = _3d_proj(wpts, rx, ry, rz, scx, scy, fov, z_off)
            sp = [(int(q[0]), int(q[1])) for q in proj]
            if len(sp) >= 3:
                pygame.draw.polygon(surface, outline_col, sp, bw)

        # Color palette
        BRONZE = (180, 120, 40)
        BRONZE_DARK = (120, 75, 20)
        BRONZE_LT = (220, 175, 80)
        SKIN = (225, 195, 160)
        SKIN_DARK = (170, 130, 100)
        LINEN = (230, 225, 200)
        LINEN_DARK = (180, 170, 145)
        BEARD_COL = (230, 230, 235)  # white/silver beard
        HELMET_CREST = (200, 30, 30)
        LIGHTNING = (255, 255, 160)
        BOLT_GLOW = (200, 200, 80)
        GOLD_COL = (255, 215, 40)

        # pulse for living effects
        pulse = 0.5 + 0.5 * math.sin(t * 2.4)

        if layer in ("behind", "all"):

            # 1. Aura glow behind Zeus
            ax, ay, ascl = p1(0, -s * 0.4, 0)
            gr = max(20, int(s * 0.85 * ascl))
            self._draw_circle_glow(surface, (230, 240, 255), ax, ay, gr, int(70 * (0.7 + 0.3 * pulse)))
            self._draw_circle_glow(surface, (180, 210, 255), ax, ay, int(gr * 0.65), int(50 * (0.7 + 0.3 * pulse)))

            # 2. Toga / robe (back layer)
            toga_back = [
                (-s * 0.52, -s * 0.18, -s * 0.08),
                (-s * 0.48, s * 0.28, -s * 0.08),
                (-s * 0.35, s * 0.70, -s * 0.08),
                (-s * 0.10, s * 0.90, -s * 0.08),
                (s * 0.10, s * 0.88, -s * 0.08),
                (s * 0.35, s * 0.70, -s * 0.08),
                (s * 0.48, s * 0.28, -s * 0.08),
                (s * 0.52, -s * 0.18, -s * 0.08),
            ]
            pfill(surface, LINEN_DARK, toga_back)

            toga_front = [
                (-s * 0.48, -s * 0.20, s * 0.10),
                (-s * 0.44, s * 0.25, s * 0.10),
                (-s * 0.32, s * 0.68, s * 0.10),
                (-s * 0.08, s * 0.88, s * 0.10),
                (s * 0.08, s * 0.86, s * 0.10),
                (s * 0.32, s * 0.68, s * 0.10),
                (s * 0.44, s * 0.25, s * 0.10),
                (s * 0.48, -s * 0.20, s * 0.10),
            ]
            pfill_outline(surface, LINEN, LINEN_DARK, toga_front, 1)

            # Toga diagonal drape fold
            pline(surface, LINEN_DARK, [
                (-s * 0.44, s * 0.00, s * 0.12),
                (s * 0.10, s * 0.38, s * 0.14),
                (s * 0.44, s * 0.22, s * 0.12),
            ], 3)
            pline(surface, (210, 205, 182), [
                (-s * 0.44, s * 0.00, s * 0.13),
                (s * 0.10, s * 0.38, s * 0.15),
                (s * 0.44, s * 0.22, s * 0.13),
            ], 1)

            # 3. Breastplate / cuirass
            chest = [
                (-s * 0.36, -s * 0.32, s * 0.12),
                (s * 0.36, -s * 0.32, s * 0.12),
                (s * 0.28, s * 0.22, s * 0.14),
                (-s * 0.28, s * 0.22, s * 0.14),
            ]
            pfill_outline(surface, BRONZE, BRONZE_DARK, chest, 2)
            # Centre ridge
            pline(surface, BRONZE_LT, [
                (0, -s * 0.30, s * 0.16),
                (0, s * 0.20, s * 0.16),
            ], 2)
            # Pec muscle lines
            for sx2 in (-1, 1):
                pline(surface, BRONZE_DARK, [
                    (sx2 * s * 0.08, -s * 0.24, s * 0.17),
                    (sx2 * s * 0.28, -s * 0.12, s * 0.16),
                    (sx2 * s * 0.26, s * 0.04, s * 0.15),
                ], 2)
            # Waist pteryges (leather strips)
            for k in range(7):
                px2 = -s * 0.28 + k * (s * 0.56 / 6)
                strip = [
                    (px2, s * 0.20, s * 0.15),
                    (px2, s * 0.42, s * 0.15),
                    (px2 + s * 0.04, s * 0.42, s * 0.15),
                    (px2 + s * 0.04, s * 0.20, s * 0.15),
                ]
                col_strip = BRONZE if k % 2 == 0 else BRONZE_DARK
                pfill_outline(surface, col_strip, BRONZE_DARK, strip, 1)

            # 4. Legs
            # Left leg
            pfill_outline(surface, SKIN, SKIN_DARK, [
                (-s * 0.28, s * 0.42, s * 0.12),
                (-s * 0.06, s * 0.42, s * 0.12),
                (-s * 0.08, s * 0.88, s * 0.10),
                (-s * 0.26, s * 0.88, s * 0.10),
            ], 1)
            # Right leg
            pfill_outline(surface, SKIN, SKIN_DARK, [
                (s * 0.06, s * 0.42, s * 0.12),
                (s * 0.28, s * 0.42, s * 0.12),
                (s * 0.26, s * 0.88, s * 0.10),
                (s * 0.08, s * 0.88, s * 0.10),
            ], 1)
            # Greaves (bronze shin guards)
            for sx2 in (-1, 1):
                greave = [
                    (sx2 * s * 0.08, s * 0.55, s * 0.14),
                    (sx2 * s * 0.24, s * 0.55, s * 0.14),
                    (sx2 * s * 0.24, s * 0.86, s * 0.13),
                    (sx2 * s * 0.08, s * 0.86, s * 0.13),
                ]
                pfill_outline(surface, BRONZE, BRONZE_DARK, greave, 1)
                pline(surface, BRONZE_LT, [
                    (sx2 * s * 0.16, s * 0.58, s * 0.15),
                    (sx2 * s * 0.16, s * 0.83, s * 0.15),
                ], 1)
            # Sandals
            for sx2 in (-1, 1):
                sandal = [
                    (sx2 * s * 0.06, s * 0.86, s * 0.14),
                    (sx2 * s * 0.27, s * 0.86, s * 0.14),
                    (sx2 * s * 0.28, s * 0.92, s * 0.13),
                    (sx2 * s * 0.04, s * 0.92, s * 0.13),
                ]
                pfill_outline(surface, BRONZE_DARK, (80, 40, 10), sandal, 1)

            # 5. Arms
            hand_t_anim = self.hand_t

            # LEFT arm - raised holding lightning bolt
            l_shoulder = lw(-s * 0.38, -s * 0.28, s * 0.10)
            l_elbow = lw(-s * 0.55, -s * 0.08, s * 0.10)
            l_hand = lw(-s * 0.64, -s * 0.38, s * 0.10)  # raised up

            sh_pts = [l_shoulder, l_elbow, l_hand]
            proj_sh = _3d_proj(sh_pts, rx, ry, rz, scx, scy, fov, z_off)
            sp_sh = [(int(q[0]), int(q[1])) for q in proj_sh]
            scl_sh = max(0.4, proj_sh[0][3] * 2.1)

            for i in range(1, len(sp_sh)):
                pygame.draw.line(surface, SKIN_DARK, sp_sh[i - 1], sp_sh[i], max(6, int(16 * scl_sh)))
                pygame.draw.line(surface, SKIN, sp_sh[i - 1], sp_sh[i], max(4, int(10 * scl_sh)))

            # RIGHT arm - raised, down at side, slight forward pose
            lift_r = math.sin(hand_t_anim) * s * 0.06
            r_shoulder = lw(s * 0.38, -s * 0.28, s * 0.10)
            r_elbow = lw(s * 0.55, -s * 0.10 + lift_r, s * 0.12)
            r_hand = lw(s * 0.65, -s * 0.20 + lift_r * 2, s * 0.14)

            sh_pts_r = [r_shoulder, r_elbow, r_hand]
            proj_shr = _3d_proj(sh_pts_r, rx, ry, rz, scx, scy, fov, z_off)
            sp_shr = [(int(q[0]), int(q[1])) for q in proj_shr]

            for i in range(1, len(sp_shr)):
                pygame.draw.line(surface, SKIN_DARK, sp_shr[i - 1], sp_shr[i], max(6, int(16 * scl_sh)))
                pygame.draw.line(surface, SKIN, sp_shr[i - 1], sp_shr[i], max(4, int(10 * scl_sh)))

            # Shoulder pauldrons
            for sx2, rsx, rsy in ((-1, -s * 0.38, -s * 0.28), (1, s * 0.38, -s * 0.28)):
                pauldron = [
                    (rsx - sx2 * s * 0.02, rsy - s * 0.04, s * 0.11),
                    (rsx + sx2 * s * 0.12, rsy - s * 0.04, s * 0.11),
                    (rsx + sx2 * s * 0.14, rsy + s * 0.10, s * 0.10),
                    (rsx - sx2 * s * 0.04, rsy + s * 0.10, s * 0.10),
                ]
                pfill_outline(surface, BRONZE, BRONZE_DARK, pauldron, 1)

            # 6. Neck + head (3D sphere-ish)
            nx2, ny2, nscl = p1(0, -s * 0.46, s * 0.10)
            neck_r = max(4, int(9 * nscl))
            pygame.draw.circle(surface, SKIN_DARK, (nx2, ny2), neck_r + 3)
            pygame.draw.circle(surface, SKIN, (nx2, ny2), neck_r)

            hx2, hy2, hscl = p1(0, -s * 0.74, s * 0.10)
            head_r = max(8, int(22 * hscl))

            # Head back (dark)
            self._draw_circle_glow(surface, SKIN_DARK, hx2, hy2, head_r + 3, 220)
            # Head front
            pygame.draw.circle(surface, SKIN, (hx2, hy2), head_r)
            pygame.draw.circle(surface, SKIN_DARK, (hx2, hy2), head_r, 2)

            # Ear left
            ex, ey, _ = p1(-s * 0.18, -s * 0.70, s * 0.06)
            ear_r = max(2, int(5 * hscl))
            pygame.draw.ellipse(surface, SKIN_DARK, (ex - ear_r, ey - ear_r * 2, ear_r * 2, ear_r * 4))
            pygame.draw.ellipse(surface, SKIN, (ex - ear_r + 1, ey - ear_r * 2 + 2, ear_r * 2 - 2, ear_r * 4 - 4))

            # Eye sockets / brow ridge
            for ex_off in (-0.38, 0.38):
                ex3, ey3, _ = p1(ex_off * s * 0.38, -s * 0.80, s * 0.22)
                eye_r = max(2, int(5 * hscl))
                # Brow
                brow_pts = [(ex3 - eye_r * 2, ey3 - eye_r - 3), (ex3 + eye_r * 2, ey3 - eye_r - 3)]
                pygame.draw.line(surface, (70, 60, 50), brow_pts[0], brow_pts[1], max(2, int(3 * hscl)))
                # Eye white
                pygame.draw.ellipse(surface, (255, 255, 255),
                                    (ex3 - eye_r, ey3 - eye_r // 2, eye_r * 2, eye_r))
                # Iris
                pygame.draw.circle(surface, (60, 100, 180), (ex3, ey3), max(1, eye_r - 1))
                # Pupil
                pygame.draw.circle(surface, (5, 5, 5), (ex3, ey3), max(1, eye_r // 2))

            # Nose (ridge)
            nx3, ny3a, _ = p1(0, -s * 0.76, s * 0.24)
            nx4, ny3b, _ = p1(0, -s * 0.62, s * 0.26)
            pygame.draw.line(surface, SKIN_DARK, (nx3, ny3a), (nx4, ny3b), max(2, int(4 * hscl)))
            nx5, ny3c, _ = p1(-s * 0.08, -s * 0.60, s * 0.24)
            nx6, ny3d, _ = p1(s * 0.08, -s * 0.60, s * 0.24)
            pygame.draw.line(surface, SKIN_DARK, (nx5, ny3c), (nx4, ny3b), max(2, int(3 * hscl)))
            pygame.draw.line(surface, SKIN_DARK, (nx6, ny3d), (nx4, ny3b), max(2, int(3 * hscl)))

            # Mouth - stern / divine
            mx3, my3, _ = p1(-s * 0.10, -s * 0.54, s * 0.24)
            mx4, my4, _ = p1(s * 0.10, -s * 0.54, s * 0.24)
            pygame.draw.line(surface, SKIN_DARK, (mx3, my3), (mx4, my4), max(2, int(3 * hscl)))

            # Beard (layered wavy strips)
            for bk, by_off in enumerate([0.0, 0.06, 0.12, 0.18]):
                bpts = []
                n_bp = 7
                for bj in range(n_bp):
                    bfrac = bj / (n_bp - 1)
                    bx_local = (-0.24 + bfrac * 0.48) * s
                    wave = math.sin(t * 3.0 + bj * 0.8 + bk * 1.2) * s * 0.015
                    bpts.append((bx_local + wave, -s * 0.48 + s * by_off + wave * 0.5, s * 0.22))
                pline(surface, BEARD_COL, bpts, max(2, int(6 * hscl) - bk))
            # Beard tip
            pline(surface, BEARD_COL, [
                (0, -s * 0.30, s * 0.22),
                (s * 0.04, -s * 0.14, s * 0.20),
                (0, -s * 0.06, s * 0.18),
            ], max(2, int(5 * hscl)))
            # Moustache
            for mx_off, mx_end in ((-1, -0.22), (1, 0.22)):
                pline(surface, BEARD_COL, [
                    (0, -s * 0.52, s * 0.25),
                    (mx_off * s * 0.12, -s * 0.53, s * 0.26),
                    (mx_end * s, -s * 0.51, s * 0.24),
                ], max(2, int(4 * hscl)))

            # 7. Corinthian helmet
            # Helmet bowl
            helm_pts = []
            n_h = 12
            for k in range(n_h + 1):
                a = math.pi * k / n_h  # 0..pi (semicircle front)
                hpx = math.cos(a) * s * 0.22
                hpy = -s * 0.74 - s * 0.28 + math.sin(a) * s * 0.28
                helm_pts.append((hpx, hpy, s * 0.12))
            pline(surface, BRONZE_DARK, helm_pts, max(2, int(4 * hscl) + 1))
            pline(surface, BRONZE_LT, helm_pts, max(1, int(2 * hscl)))

            # Cheek guards
            for sx2 in (-1, 1):
                cheek = [
                    (sx2 * s * 0.20, -s * 0.74, s * 0.18),
                    (sx2 * s * 0.24, -s * 0.60, s * 0.20),
                    (sx2 * s * 0.18, -s * 0.52, s * 0.21),
                    (sx2 * s * 0.12, -s * 0.54, s * 0.22),
                    (sx2 * s * 0.12, -s * 0.70, s * 0.22),
                ]
                pfill_outline(surface, BRONZE, BRONZE_DARK, cheek, 1)

            # Nose guard
            ng = [
                (0, -s * 0.74, s * 0.26),
                (-s * 0.03, -s * 0.68, s * 0.27),
                (s * 0.03, -s * 0.68, s * 0.27),
            ]
            pfill(surface, BRONZE, ng)

            # Crest - red plume along top
            crest_root = [(k * s * 0.04 - s * 0.20, -s * 0.74 - s * 0.28 + s * 0.04, s * 0.12) for k in range(11)]
            crest_tip = []
            for k, cr in enumerate(crest_root):
                wave = math.sin(t * 4.0 + k * 0.4) * s * 0.02
                crest_tip.append((cr[0], cr[1] - s * 0.20 + wave, s * 0.14))
            crest_back = list(reversed(crest_root))
            crest_poly = crest_root + crest_tip + crest_back
            pfill(surface, HELMET_CREST, crest_poly)
            pline(surface, (240, 60, 60), crest_tip, max(2, int(4 * hscl)))

            # Helmet rim highlight
            rim_pts = [
                (-s * 0.22, -s * 0.74, s * 0.18),
                (-s * 0.24, -s * 0.66, s * 0.20),
                (0, -s * 0.63, s * 0.26),
                (s * 0.24, -s * 0.66, s * 0.20),
                (s * 0.22, -s * 0.74, s * 0.18),
            ]
            pline(surface, BRONZE_LT, rim_pts, max(1, int(2 * hscl)))

            # 8. Left hand holds lightning bolt
            bolt_base = l_hand
            bolt_proj = _3d_proj([bolt_base], rx, ry, rz, scx, scy, fov, z_off)[0]
            bscl = max(0.4, bolt_proj[3] * 2.1)
            if self._bolt_pts:
                bolt_world = [lw(bolt_base[0] / s * s + bpt[0],
                                 # anchor to hand local pos
                                 (-s * 0.38 + bpt[1]),
                                 s * 0.10 + bpt[2])
                              for bpt in self._bolt_pts]
                # Hack: move bolt relative to hand in world space
                bx_w, by_w, bz_w = bolt_base
                bolt_world2 = []
                for bpt in self._bolt_pts:
                    bolt_world2.append((bx_w + bpt[0], by_w + bpt[1], bz_w + bpt[2]))
                bolt_proj2 = _3d_proj(bolt_world2, rx, ry, rz, scx, scy, fov, z_off)
                bsp = [(int(q[0]), int(q[1])) for q in bolt_proj2]
                bw = max(2, int(4 * bscl))
                # Outer glow
                for i in range(1, len(bsp)):
                    pygame.draw.line(surface, (80, 80, 0), bsp[i - 1], bsp[i], bw + 6)
                    pygame.draw.line(surface, BOLT_GLOW, bsp[i - 1], bsp[i], bw + 3)
                    pygame.draw.line(surface, LIGHTNING, bsp[i - 1], bsp[i], bw)
                    pygame.draw.line(surface, (255, 255, 255), bsp[i - 1], bsp[i], max(1, bw - 2))
                # Tip glow
                if bsp:
                    tip = bsp[-1]
                    gr2 = max(4, int(12 * bscl))
                    self._draw_circle_glow(surface, (255, 255, 200), tip[0], tip[1], gr2, int(180 * pulse))
                    pygame.draw.circle(surface, (255, 255, 255), tip, max(2, gr2 // 2))

            # 9. Right hand - palm-down divine gesture
            rhand_p = _3d_proj([r_hand], rx, ry, rz, scx, scy, fov, z_off)[0]
            rh_scl = max(0.4, rhand_p[3] * 2.1)
            rh_r = max(4, int(9 * rh_scl))
            self._draw_circle_glow(surface, (255, 230, 180), int(rhand_p[0]), int(rhand_p[1]), rh_r + 4, int(100 * pulse))
            pygame.draw.circle(surface, SKIN, (int(rhand_p[0]), int(rhand_p[1])), rh_r)
            pygame.draw.circle(surface, SKIN_DARK, (int(rhand_p[0]), int(rhand_p[1])), rh_r, 1)

            # 10. Gold sandal laces
            for sx2 in (-1, 1):
                for k in range(3):
                    y_lace = s * (0.56 + k * 0.08)
                    pline(surface, GOLD_COL, [
                        (sx2 * s * 0.08, y_lace, s * 0.16),
                        (sx2 * s * 0.24, y_lace, s * 0.16),
                    ], 1)

        if layer in ("fx", "all"):
            # Spray trails
            for p_spr in self.spray:
                tr = p_spr["trail"]
                if len(tr) > 1:
                    tproj = _3d_proj(tr, rx, ry, rz, scx, scy, fov, z_off)
                    for i2 in range(1, len(tproj)):
                        f = i2 / len(tproj)
                        c1 = (int(100 * f), int(120 * f), int(155 * f))
                        c2 = (int(225 * f), int(238 * f), int(255 * f))
                        p0 = (int(tproj[i2 - 1][0]), int(tproj[i2 - 1][1]))
                        p1b = (int(tproj[i2][0]), int(tproj[i2][1]))
                        pygame.draw.line(surface, c1, p0, p1b, max(1, int(5 * f)))
                        pygame.draw.line(surface, c2, p0, p1b, max(1, int(3 * f)))
                pp = _3d_proj([(p_spr["x"], p_spr["y"], p_spr["z"])], rx, ry, rz, scx, scy, fov, z_off)[0]
                fade = max(0.0, min(1.0, p_spr["life"]))
                rr2 = max(1, int(p_spr["size"] * max(0.45, pp[3] * 2.1)))
                pygame.draw.circle(surface, (int(210 * fade), int(230 * fade), int(255 * fade)),
                                   (int(pp[0]), int(pp[1])), rr2)
                if rr2 > 1:
                    pygame.draw.circle(surface, (255, 255, 255), (int(pp[0]), int(pp[1])), max(1, rr2 // 2))

            # Cube impact marks
            for mk in self.cube_marks:
                mp = _3d_proj([(mk["x"], mk["y"], mk["z"])], rx, ry, rz, scx, scy, fov, z_off)[0]
                fade = max(0.0, min(1.0, mk["life"]))
                rr2 = max(1, int(mk["r"] * max(0.45, mp[3] * 2.0)))
                c2 = (int(230 * fade), int(240 * fade), int(255 * fade))
                pygame.draw.circle(surface, c2, (int(mp[0]), int(mp[1])), rr2, max(1, int(4 * fade)))
                pygame.draw.circle(surface, (255, 255, 255), (int(mp[0]), int(mp[1])), max(1, rr2 // 3))


class Obj3DGravityWell:
    def __init__(self, bouncer_obj):
        self.bobj  = bouncer_obj
        self.angle = 0.0
        self.pulse = random.uniform(0,6.28)

    def update(self, dt):
        self.angle += 0.9*dt

    def draw(self, surface, rx, ry, rz, scx, scy, t, fov=900.0, z_off=800.0):
        wx,wy,wz = self.bobj.x, self.bobj.y, self.bobj.z
        p   = 0.5+0.5*math.sin(t*2.4+self.pulse)
        col = (int(160+80*p),int(0+30*p),int(220+35*p))
        ring_pts = []
        for k in range(16):
            a = self.angle+k*math.pi/8
            ring_pts.append((wx+55*math.cos(a), wy, wz+55*math.sin(a)))
        pr = _3d_proj(ring_pts, rx, ry, rz, scx, scy, fov, z_off)
        rsp = [(int(q[0]),int(q[1])) for q in pr]
        for i in range(len(rsp)):
            pygame.draw.line(surface,col,rsp[i],rsp[(i+1)%len(rsp)],2)
        cp = _3d_proj([(wx,wy,wz)], rx, ry, rz, scx, scy, fov, z_off)[0]
        cr = max(6,int(18*(0.8+0.2*p)))
        gs = pygame.Surface((cr*4,cr*4),pygame.SRCALPHA)
        pygame.draw.circle(gs,(*col,120),(cr*2,cr*2),cr*2)
        surface.blit(gs,(int(cp[0])-cr*2,int(cp[1])-cr*2))
        pygame.draw.circle(surface,col,(int(cp[0]),int(cp[1])),cr)
        pygame.draw.circle(surface,(5,0,10),(int(cp[0]),int(cp[1])),max(2,cr//2))


class Mode3DEffect:
    FOV  = 900.0
    RX_V = 0.00055
    RY_V = 0.00095
    RZ_V = 0.00022

    def __init__(self):
        self.income_timer = pygame.time.get_ticks()
        self._half_base = min(GAME_WIDTH,HEIGHT)*0.44
        self._half_god  = min(GAME_WIDTH,HEIGHT)*0.32
        self.half  = self._half_god if total_goon_god_power() > 0 else self._half_base
        self.rx    = 0.18; self.ry = 0.28; self.rz = 0.04
        self.cam_t = 0.0
        self.pulse = 0.0
        self.world_objs = []
        self._bouncer_objs = []
        self._waves3d = []
        self._laser3d = []
        self._lightning3d = []
        self._rebuild_world()

    def _sync_half(self):
        target = self._half_god if total_goon_god_power() > 0 else self._half_base
        if abs(self.half - target) > 0.01:
            self.half = target
            self._rebuild_world()

    def _rebuild_world(self):
        self.world_objs.clear()
        self._bouncer_objs.clear()
        hw = self.half
        # Bouncer cubes
        bouncer_objs = []
        for b in bouncers:
            obj = Obj3DBouncer(b, hw)
            self.world_objs.append(obj)
            bouncer_objs.append(obj)
            self._bouncer_objs.append(obj)
        donut_owners = [b for b in bouncers if b.donut_enabled and b.donut_ring_count > 0]
        if donut_owners:
            self.world_objs.append(Obj3DDonutRing(donut_owners, hw))
        god_power = sum(max(0, b.goon_god_purchases) for b in bouncers if b.goon_god_enabled)
        if god_power > 0:
            self.world_objs.append(Obj3DGoonGod(god_power, hw))
        # Illuminate pyramid (always centred in 3D mode)
        n = len(illuminate_effects)
        if n > 0:
            self.world_objs.append(Obj3DPrism(0.0, 0.0, 0.0, n))
        # Factory boxes
        n_fac = len(factories)
        for i in range(n_fac):
            if n_fac == 1:
                x3, z3 = 0.0, 0.0
            else:
                a = i * (_TWO_PI / n_fac)
                band = 0.45 + 0.18 * (1 if i % 2 == 0 else -1)
                x3 = hw * band * math.cos(a)
                z3 = hw * (0.28 + 0.12 * math.sin(i * 1.7)) * math.sin(a)
            self.world_objs.append(Obj3DFactory(x3, hw, z3))
        # Gravity well orbs (paired to bouncer objs)
        for geff in gravity_effects:
            paired = next((o for o in bouncer_objs if o.b is geff.bouncer), None)
            if paired:
                self.world_objs.append(Obj3DGravityWell(paired))

    def _world_signature(self):
        """A hashable key representing which game objects currently exist."""
        return (tuple((id(b), b.donut_enabled, b.donut_ring_count, b.goon_god_enabled, b.goon_god_purchases) for b in bouncers),
                len(illuminate_effects), len(factories),
                tuple(id(g.bouncer) for g in gravity_effects))

    def _spawn_bounce_fx(self, bobj, hit_pt, normal):
        nx, ny, nz = normal
        donut_power = bobj.b.donut_ring_count * 25 if bobj.b.donut_enabled else 0
        wave_on = bobj.b.waves_enabled or donut_power > 0
        laser_power = bobj.b.laser_purchases + donut_power
        lightning_power = bobj.b.lightning_purchases + donut_power
        # Build an orthonormal basis around the wall normal for spread.
        ax = (1.0, 0.0, 0.0) if abs(nx) < 0.9 else (0.0, 1.0, 0.0)
        ux = ny * ax[2] - nz * ax[1]
        uy = nz * ax[0] - nx * ax[2]
        uz = nx * ax[1] - ny * ax[0]
        um = math.sqrt(max(1e-9, ux*ux + uy*uy + uz*uz))
        ux, uy, uz = ux / um, uy / um, uz / um
        vx = ny * uz - nz * uy
        vy = nz * ux - nx * uz
        vz = nx * uy - ny * ux

        if wave_on:
            def dist_to_box(pos, direction):
                x0, y0, z0 = pos
                dx, dy, dz = direction
                tmin = float("inf")
                for p0, dp in ((x0, dx), (y0, dy), (z0, dz)):
                    if abs(dp) < 1e-6:
                        continue
                    edge = self.half if dp > 0 else -self.half
                    t = (edge - p0) / dp
                    if t > 0:
                        tmin = min(tmin, t)
                return tmin if tmin != float("inf") else 0.0

            du1 = dist_to_box(hit_pt, (ux, uy, uz))
            du2 = dist_to_box(hit_pt, (-ux, -uy, -uz))
            dv1 = dist_to_box(hit_pt, (vx, vy, vz))
            dv2 = dist_to_box(hit_pt, (-vx, -vy, -vz))
            max_r = max(18.0, min(du1, du2, dv1, dv2) * 0.95)
            wave_col = (100, 255, 170) if goon_mode else bobj.b.color
            self._waves3d.append({
                "c": hit_pt,
                "u": (ux, uy, uz),
                "v": (vx, vy, vz),
                "r": 8.0,
                "max_r": max_r,
                "col": wave_col,
            })

        if laser_power > 0:
            shots = min(laser_power, LASER_MAX_SHOTS_PER_TICK)
            half = (shots - 1) * 0.5
            for si in range(shots):
                spread = (si - half) * 0.22
                bend = random.uniform(-0.08, 0.08)
                dx = nx + ux * spread + vx * bend
                dy = ny + uy * spread + vy * bend
                dz = nz + uz * spread + vz * bend
                dm = math.sqrt(max(1e-9, dx*dx + dy*dy + dz*dz))
                spd = 290.0
                self._laser3d.append({
                    "x": hit_pt[0], "y": hit_pt[1], "z": hit_pt[2],
                    "vx": dx / dm * spd, "vy": dy / dm * spd, "vz": dz / dm * spd,
                    "life": 1.0, "trail": [hit_pt],
                })

        if lightning_power > 0:
            targets = [o for o in self._bouncer_objs if o is not bobj]
            targets.sort(key=lambda o: (o.x - hit_pt[0])**2 + (o.y - hit_pt[1])**2 + (o.z - hit_pt[2])**2)
            chain_count = min(len(targets), max(1, min(8, lightning_power)))
            segments = []
            for target in targets[:chain_count]:
                segments.append(self._jagged_line_points3d(hit_pt, (target.x, target.y, target.z), jag=18, segs=8))
            if segments:
                self._lightning3d.append({"segments": segments, "life": 0.45})

    def _jagged_line_points3d(self, p0, p1, jag=14, segs=8):
        x1, y1, z1 = p0
        x2, y2, z2 = p1
        dx, dy, dz = x2 - x1, y2 - y1, z2 - z1
        length = math.sqrt(dx*dx + dy*dy + dz*dz)
        if length <= 1e-6:
            return [p0, p1]
        tx, ty, tz = dx / length, dy / length, dz / length
        ax = (1.0, 0.0, 0.0) if abs(tx) < 0.9 else (0.0, 1.0, 0.0)
        ux = ty * ax[2] - tz * ax[1]
        uy = tz * ax[0] - tx * ax[2]
        uz = tx * ax[1] - ty * ax[0]
        um = math.sqrt(max(1e-9, ux*ux + uy*uy + uz*uz))
        ux, uy, uz = ux / um, uy / um, uz / um
        vx = ty * uz - tz * uy
        vy = tz * ux - tx * uz
        vz = tx * uy - ty * ux

        pts = [p0]
        for i in range(1, segs):
            t = i / segs
            mx = x1 + dx * t
            my = y1 + dy * t
            mz = z1 + dz * t
            o1 = random.uniform(-jag, jag)
            o2 = random.uniform(-jag, jag)
            pts.append((mx + ux * o1 + vx * o2, my + uy * o1 + vy * o2, mz + uz * o1 + vz * o2))
        pts.append(p1)
        return pts

    def update(self, dt):
        global coins
        self._sync_half()
        self.cam_t += dt
        # Keep motion dynamic but never allow upside-down camera flips.
        self.rx = 0.12 + 0.14 * math.sin(self.cam_t * 0.45)
        self.ry += 0.20 * dt
        self.rz = 0.03 * math.sin(self.cam_t * 0.30)
        self.pulse += dt*2.2
        # Only rebuild when objects appear/disappear, not every frame
        sig = self._world_signature()
        if not hasattr(self,'_last_sig') or sig != self._last_sig:
            self._last_sig = sig
            self._rebuild_world()
        for obj in self.world_objs:
            if isinstance(obj, Obj3DGoonGod):
                obj.update(dt, self.rx, self.ry, self.rz)
            else:
                obj.update(dt)
            if isinstance(obj, Obj3DBouncer) and obj.hit_events:
                for hit_pt, normal in obj.hit_events:
                    self._spawn_bounce_fx(obj, hit_pt, normal)

        # Update 3D hit waves constrained to cube walls.
        wi = 0
        while wi < len(self._waves3d):
            wv = self._waves3d[wi]
            wv["r"] += dt * 220.0
            if wv["r"] >= wv["max_r"]:
                self._waves3d[wi] = self._waves3d[-1]
                self._waves3d.pop()
            else:
                wi += 1

        # Update 3D-only laser trails (spawned from 3D wall hits).
        hw = self.half
        i = 0
        while i < len(self._laser3d):
            beam = self._laser3d[i]
            beam["x"] += beam["vx"] * dt
            beam["y"] += beam["vy"] * dt
            beam["z"] += beam["vz"] * dt

            if beam["x"] < -hw:
                beam["x"] = -hw
                beam["vx"] = abs(beam["vx"])
            if beam["x"] > hw:
                beam["x"] = hw
                beam["vx"] = -abs(beam["vx"])
            if beam["y"] < -hw:
                beam["y"] = -hw
                beam["vy"] = abs(beam["vy"])
            if beam["y"] > hw:
                beam["y"] = hw
                beam["vy"] = -abs(beam["vy"])
            if beam["z"] < -hw:
                beam["z"] = -hw
                beam["vz"] = abs(beam["vz"])
            if beam["z"] > hw:
                beam["z"] = hw
                beam["vz"] = -abs(beam["vz"])

            beam["trail"].append((beam["x"], beam["y"], beam["z"]))
            if len(beam["trail"]) > 34:
                beam["trail"].pop(0)
            beam["life"] -= dt * 0.55
            if beam["life"] <= 0.0:
                self._laser3d[i] = self._laser3d[-1]
                self._laser3d.pop()
            else:
                i += 1

        j = 0
        while j < len(self._lightning3d):
            bolt = self._lightning3d[j]
            bolt["life"] -= dt
            if bolt["life"] <= 0.0:
                self._lightning3d[j] = self._lightning3d[-1]
                self._lightning3d.pop()
            else:
                j += 1

        if len(self._laser3d) > LASER_MAX_ACTIVE_BEAMS:
            del self._laser3d[:-LASER_MAX_ACTIVE_BEAMS]
        if len(self._lightning3d) > 40:
            del self._lightning3d[:-40]
        if len(self._waves3d) > 48:
            del self._waves3d[:-48]
        now = pygame.time.get_ticks()
        if now - self.income_timer >= 1000:
            ticks = (now - self.income_timer) // 1000
            coins += MODE3D_INCOME_PER_SEC * ticks
            self.income_timer += ticks * 1000

    def draw(self, surface):
        self._sync_half()
        now   = pygame.time.get_ticks()
        t     = now/1000.0
        pulse = 0.5+0.5*math.sin(self.pulse)
        hs    = self.half
        scx   = GAME_WIDTH//2
        scy   = int(HEIGHT*0.68) if total_goon_god_power() > 0 else HEIGHT//2
        rx,ry,rz = self.rx,self.ry,self.rz

        surface.fill((4,4,12))
        for i in range(48):
            sx2 = int((i*137+42) % GAME_WIDTH)
            sy2 = int((i*97+18) % HEIGHT)
            br2 = 30+(i*31)%120
            pygame.draw.circle(surface,(br2,br2,br2+20),(sx2,sy2),1)

        raw = [(-hs,-hs,-hs),(+hs,-hs,-hs),(+hs,+hs,-hs),(-hs,+hs,-hs),
               (-hs,-hs,+hs),(+hs,-hs,+hs),(+hs,+hs,+hs),(-hs,+hs,+hs)]
        FACES = [(0,1,2,3,"back"),(4,5,6,7,"front"),
                 (0,1,5,4,"bottom"),(2,3,7,6,"top"),
                 (0,3,7,4,"left"),(1,2,6,5,"right")]
        EDGES = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
        NORMALS = {"back":(0,0,-1),"front":(0,0,1),"bottom":(0,-1,0),
                   "top":(0,1,0),"left":(-1,0,0),"right":(1,0,0)}
        FACE_BASE = {"back":(0,15,50),"front":(0,5,35),"bottom":(8,0,35),
                     "top":(0,30,15),"left":(30,8,0),"right":(0,8,35)}

        proj   = _3d_proj(raw,rx,ry,rz,scx,scy,self.FOV,hs*2)
        sp     = [(int(p[0]),int(p[1])) for p in proj]
        depths = [p[2] for p in proj]
        light  = (0.35,0.55,0.85)
        god_obj = next((o for o in self.world_objs if isinstance(o, Obj3DGoonGod)), None)
        if god_obj is not None:
            god_obj.draw(surface, rx, ry, rz, scx, scy, t, self.FOV, hs*2, layer="behind")
        donut_obj = next((o for o in self.world_objs if isinstance(o, Obj3DDonutRing)), None)
        if donut_obj is not None:
            donut_obj.draw(surface, rx, ry, rz, scx, scy, t, self.FOV, hs*2, layer="back")

        face_list = []
        for i0,i1,i2,i3,fname in FACES:
            avg_z = (depths[i0]+depths[i1]+depths[i2]+depths[i3])/4
            nx,ny,nz = NORMALS[fname]
            nr  = _3d_rot([(nx,ny,nz)],rx,ry,rz)[0]
            dot = nr[0]*light[0]+nr[1]*light[1]+nr[2]*light[2]
            br  = max(0.10,min(1.0,0.35+0.65*dot))
            face_list.append((avg_z,i0,i1,i2,i3,fname,br))
        face_list.sort(key=lambda x:x[0])

        for avg_z,i0,i1,i2,i3,fname,br in face_list:
            pts4  = [sp[i0],sp[i1],sp[i2],sp[i3]]
            base  = FACE_BASE[fname]
            hue_o = (t*0.22+avg_z/(hs*2)*0.25) % 1.0
            r2 = int((base[0]+70*(0.5+0.5*math.sin(hue_o*6.28)))*br)
            g2 = int((base[1]+70*(0.5+0.5*math.sin(hue_o*6.28+2.09)))*br)
            b2 = int((base[2]+100*(0.5+0.5*math.sin(hue_o*6.28+4.19)))*br)
            col2  = (max(0,min(255,r2)),max(0,min(255,g2)),max(0,min(255,b2)))
            glow = 0.78 + 0.22 * pulse
            col2 = (int(col2[0] * glow), int(col2[1] * glow), int(col2[2] * glow))
            pygame.draw.polygon(surface, col2, pts4)

        for obj in self.world_objs:
            if isinstance(obj,Obj3DBouncer):
                obj.draw(surface, rx, ry, rz, scx, scy, self.FOV, hs*2)
            elif isinstance(obj,Obj3DPrism):
                obj.draw(surface, rx, ry, rz, scx, scy, t, self.FOV, hs*2)
            elif isinstance(obj,Obj3DFactory):
                obj.draw(surface, rx, ry, rz, scx, scy, t, self.FOV, hs*2)
            elif isinstance(obj,Obj3DDonutRing):
                continue
            elif isinstance(obj,Obj3DGoonGod):
                continue
            elif isinstance(obj,Obj3DGravityWell):
                obj.draw(surface, rx, ry, rz, scx, scy, t, self.FOV, hs*2)

        # Project 2D upgrade effects into 3D space so upgrades stay visible in 3D mode.
        sx_scale = hs * 1.7 / GAME_WIDTH
        sy_scale = hs * 1.7 / HEIGHT

        def to_world(x2, y2, z2=0.0):
            return ((x2 - GAME_WIDTH * 0.5) * sx_scale,
                    (y2 - HEIGHT * 0.5) * sy_scale,
                    z2)

        # 3D wall-hit waves (stay on hit wall and inside cube).
        for wv in self._waves3d:
            fade = max(0.0, 1.0 - wv["r"] / max(1.0, wv["max_r"]))
            if fade <= 0.0:
                continue
            cx, cy, cz = wv["c"]
            ux, uy, uz = wv["u"]
            vx, vy, vz = wv["v"]
            r = wv["r"]
            pts3 = []
            for k in range(32):
                a = k * (2.0 * math.pi / 32.0)
                ca = math.cos(a); sa = math.sin(a)
                px = cx + (ux * ca + vx * sa) * r
                py = cy + (uy * ca + vy * sa) * r
                pz = cz + (uz * ca + vz * sa) * r
                px = max(-hs, min(hs, px))
                py = max(-hs, min(hs, py))
                pz = max(-hs, min(hs, pz))
                pts3.append((px, py, pz))
            pr = _3d_proj(pts3, rx, ry, rz, scx, scy, self.FOV, hs*2)
            ip = [(int(q[0]), int(q[1])) for q in pr]
            rc = wv["col"]
            c1 = (int(rc[0] * fade), int(rc[1] * fade), int(rc[2] * fade))
            c2 = (int(c1[0] * 0.45), int(c1[1] * 0.45), int(c1[2] * 0.45))
            w = max(1, int(4 * fade))
            for i in range(len(ip)):
                p0 = ip[i]
                p1 = ip[(i + 1) % len(ip)]
                pygame.draw.line(surface, c2, p0, p1, w + 2)
                pygame.draw.line(surface, c1, p0, p1, w)

        # 3D wall-hit lasers
        for beam in self._laser3d:
            tr = beam["trail"]
            if len(tr) < 2:
                continue
            proj_tr = _3d_proj(tr, rx, ry, rz, scx, scy, self.FOV, hs*2)
            n = len(proj_tr)
            life = beam["life"]
            for i in range(1, n):
                bright = (i / n) * life
                p0 = (int(proj_tr[i-1][0]), int(proj_tr[i-1][1]))
                p1 = (int(proj_tr[i][0]), int(proj_tr[i][1]))
                pygame.draw.line(surface, (int(140*bright), 0, 0), p0, p1, 10)
                pygame.draw.line(surface, (int(255*bright), int(60*bright), 0), p0, p1, 6)
                pygame.draw.line(surface, (255, int(200*bright), int(200*bright)), p0, p1, 3)
            hp = proj_tr[-1]
            pygame.draw.circle(surface, (255, 120, 120), (int(hp[0]), int(hp[1])), 7)
            pygame.draw.circle(surface, (255, 255, 255), (int(hp[0]), int(hp[1])), 3)

        # 3D wall-hit lightning
        for bolt in self._lightning3d:
            alpha_f = max(0.0, bolt["life"] / 0.45)
            if alpha_f <= 0.0:
                continue
            for seg in bolt["segments"]:
                proj_e = _3d_proj(seg, rx, ry, rz, scx, scy, self.FOV, hs*2)
                ipts = [(int(q[0]), int(q[1])) for q in proj_e]
                for i in range(1, len(ipts)):
                    p0, p1 = ipts[i-1], ipts[i]
                    pygame.draw.line(surface, (0, int(30*alpha_f), int(120*alpha_f)), p0, p1, 10)
                    pygame.draw.line(surface, (int(100*alpha_f), int(100*alpha_f), int(255*alpha_f)), p0, p1, 5)
                    pygame.draw.line(surface, (int(220*alpha_f), int(220*alpha_f), int(255*alpha_f)), p0, p1, 2)

        # Implosion effect states
        for eff in implosion_effects:
            if eff.phase == IMP_IDLE:
                continue
            cp = _3d_proj([to_world(eff._cx, eff._cy, 0.0)], rx, ry, rz, scx, scy, self.FOV, hs*2)[0]
            cpt = (int(cp[0]), int(cp[1]))
            scale = max(0.5, cp[3] * 2.0)
            if goon_mode:
                core_col = (110, 255, 170)
                glow_col = (40, 120, 90)
            else:
                core_col = (210, 150, 255)
                glow_col = (95, 35, 145)
            if eff.phase == IMP_SHRINK:
                prog = min((now - eff.phase_start) / max(1, IMPLOSION_SHRINK_MS), 1.0)
                rr = max(6, int((74 - 56 * prog) * scale))
                for k in range(12):
                    a = (k / 12.0) * _TWO_PI + now / 260.0
                    px = cpt[0] + int(math.cos(a) * rr)
                    py = cpt[1] + int(math.sin(a) * rr)
                    pygame.draw.line(surface, glow_col, (px, py), cpt, 2)
                pygame.draw.circle(surface, core_col, cpt, rr, 3)
                pygame.draw.circle(surface, (255, 255, 255), cpt, max(2, rr // 5))
            elif eff.phase == IMP_HOLD:
                rr = max(7, int(16 * scale))
                pulse_r = rr + int(3 * math.sin(now / 80.0))
                pygame.draw.circle(surface, glow_col, cpt, pulse_r + 4, 2)
                pygame.draw.circle(surface, core_col, cpt, pulse_r, 2)
                pygame.draw.circle(surface, (0, 0, 0), cpt, max(2, rr // 2))
                pygame.draw.circle(surface, (255, 255, 255), cpt, max(1, rr // 5))
            elif eff.phase == IMP_EXPLODE:
                prog = min((now - eff.phase_start) / max(1, IMPLOSION_EXPLODE_MS), 1.0)
                rr = max(10, int((260 * prog + 10) * scale))
                thick = max(1, int(10 * (1.0 - prog)))
                pygame.draw.circle(surface, (255, 255, 255), cpt, rr, thick)
                pygame.draw.circle(surface, core_col, cpt, max(3, int(rr * 0.55)), max(1, thick - 1))
                for k in range(8):
                    a = (k / 8.0) * _TWO_PI + now / 140.0
                    ex = cpt[0] + int(math.cos(a) * rr)
                    ey = cpt[1] + int(math.sin(a) * rr)
                    pygame.draw.circle(surface, core_col, (ex, ey), max(1, int(4 * (1.0 - prog))))

        # Flash + explosion particles in 3D
        def draw_projected_particles(plist, life_fade):
            i = 0
            while i < len(plist):
                p = plist[i]
                p[0] += p[2]
                p[1] += p[3]
                p[7] -= p[8]
                if p[7] <= 0:
                    plist[i] = plist[-1]
                    plist.pop()
                    continue
                if life_fade:
                    lf = p[7]
                    col = (int(p[4] * lf), int(p[5] * lf), int(p[6] * lf))
                else:
                    col = (int(p[4]), int(p[5]), int(p[6]))
                pp = _3d_proj([to_world(p[0], p[1], 0.0)], rx, ry, rz, scx, scy, self.FOV, hs*2)[0]
                rr = max(1, int(p[9] * max(0.45, pp[3] * 2.2)))
                pygame.draw.circle(surface, col, (int(pp[0]), int(pp[1])), rr)
                i += 1

        draw_projected_particles(flash_particles, False)
        draw_projected_particles(explosion_particles, True)
        if god_obj is not None:
            god_obj.draw(surface, rx, ry, rz, scx, scy, t, self.FOV, hs*2, layer="fx")

        for e0,e1 in EDGES:
            p0,p1  = sp[e0],sp[e1]
            d_avg  = (depths[e0]+depths[e1])*0.5
            eb     = max(0.35,min(1.0,0.5+d_avg/(hs*2)))
            ep     = int((150+100*pulse)*eb)
            pygame.draw.line(surface,(0,ep//4,ep),p0,p1,3)
            pygame.draw.line(surface,(ep,ep,255),p0,p1,1)

        for k,cpt in enumerate(sp):
            df  = max(0.3,min(1.0,0.5+depths[k]/(hs*2)))
            cr2 = max(3,int(9*df*(0.75+0.25*pulse)))
            pygame.draw.circle(surface,(60,180,255),cpt,cr2+3)
            pygame.draw.circle(surface,(200,240,255),cpt,max(1,cr2-1))

        # Draw donut front-half pass so it wraps around the cube, not flat in front.
        if donut_obj is not None:
            donut_obj.draw(surface, rx, ry, rz, scx, scy, t, self.FOV, hs*2, layer="front")

        pc  = (int(80+175*pulse),int(200+55*pulse),255)
        lbl = font.render("3 D   M O D E", True, pc)
        surface.blit(lbl, lbl.get_rect(center=(scx, scy+int(hs)+32)))


def update_mode3d(dt, now):
    if mode3d_effect:
        mode3d_effect.update(dt)

def draw_mode3d_pre(surface):
    return surface

def draw_mode3d_post(surface):
    if mode3d_active and mode3d_effect:
        mode3d_effect.draw(surface)

def select_bouncer(idx):
    global selected_index
    if not bouncers:
        return
    idx = idx % len(bouncers)
    bouncers[selected_index].selected = False
    selected_index = idx
    bouncers[selected_index].selected = True
    bouncers[selected_index].sync_shop_data()

# ------------------ BOUNCER ------------------
class Bouncer:
    __slots__ = ('size','fx','fy','rect','color','speed_x','speed_y','selected',
                 'waves_enabled','laser_enabled','last_laser_time','laser_cooldown',
                 'laser_purchases','flashing','flash_amount','flash_interval',
                 'flash_purchases','next_flash','coin_bonus','trail_enabled',
                 'trail_points','last_trail_income','trail_income','wave_income','last_donut_income','last_god_income',
                 'laser_income','implosion_enabled','implosion_frozen','lightning_enabled',
                 'lightning_purchases','illuminate_enabled','gravity_enabled','gravity_purchases',
                 'mode3d_enabled','donut_enabled','donut_ring_count',
                 'goon_god_enabled','goon_god_purchases','shop_data','draw_rect')

    def __init__(self, x, y):
        self.size    = 80
        self.fx      = float(x)
        self.fy      = float(y)
        self.rect    = pygame.Rect(x, y, self.size, self.size)
        self.draw_rect = pygame.Rect(x, y, self.size, self.size)
        self.color   = self._random_color()
        self.speed_x = 240.0
        self.speed_y = 240.0
        self.selected = False

        self.waves_enabled   = False
        self.laser_enabled   = False
        self.last_laser_time = 0
        self.laser_cooldown  = 1500
        self.laser_purchases = 0

        self.flashing        = False
        self.flash_amount    = 10
        self.flash_interval  = 5000
        self.flash_purchases = 0
        self.next_flash      = 0

        self.coin_bonus          = 0
        self.trail_enabled       = False
        self.trail_points        = []
        self.last_trail_income   = 0
        self.trail_income        = 0
        self.wave_income         = 0
        self.laser_income        = 0
        self.last_donut_income   = 0
        self.last_god_income     = 0
        self.implosion_enabled   = False
        self.implosion_frozen    = False
        self.lightning_enabled   = False
        self.lightning_purchases = 0
        self.illuminate_enabled  = False
        self.gravity_enabled     = False
        self.gravity_purchases   = 0
        self.mode3d_enabled      = False
        self.donut_enabled       = False
        self.donut_ring_count    = 0
        self.goon_god_enabled    = False
        self.goon_god_purchases  = 0

        self.shop_data = build_shop_data()

    def _random_color(self):
        return (random.randint(80,255), random.randint(80,255), random.randint(80,255))

    def random_color(self): return self._random_color()

    def increase_price(self, item):
        item["price"] = math.ceil(item["price"] * 1.25)

    def sync_shop_data(self):
        self.shop_data = build_shop_data(self.shop_data)

    def bought_count(self, action):
        it = next((entry for entry in self.shop_data if entry["action"] == action), None)
        return it["bought"] if it else 0

    def donut_upgrade_power(self):
        if not self.donut_enabled or self.donut_ring_count <= 0:
            return 0
        return self.donut_ring_count * 25

    def earnings_multiplier(self):
        if self.donut_enabled and self.donut_ring_count > 0:
            return self.donut_ring_count * 10
        return 1

    def is_unlocked(self, index):
        if cheat_mode or index == 0: return True
        action = self.shop_data[index]["action"]
        if action in ("bonus", "wave"):
            return self.bought_count("trail") >= 3
        return self.shop_data[index-1]["bought"] >= 3

    def _spawn_wave(self, side):
        if len(wave_rings) < 12:
            wc = (100, 255, 170) if goon_mode else self.color
            wave_rings.append(WaveRing(self.rect.centerx, self.rect.centery, wc, side,
                                       payout=300 * self.earnings_multiplier()))

    def _fire_laser(self, angle):
        cx, cy = self.rect.centerx, self.rect.centery
        laser_beams.append(LaserBeam(cx, cy, angle))

    def _emit_lasers(self, wall_side=None, extra_shots=0):
        # Fire from the bounce direction, not random, so wall hits feel intentional.
        shots = min(self.laser_purchases + max(0, int(extra_shots)), LASER_MAX_SHOTS_PER_TICK)
        if shots <= 0:
            return
        base_by_side = {
            "left":   0.0,
            "right":  math.pi,
            "top":    math.pi * 0.5,
            "bottom": -math.pi * 0.5,
        }
        base = base_by_side.get(wall_side)
        if base is None:
            for _ in range(shots):
                self._fire_laser(random.uniform(0, _TWO_PI))
            return
        spread = 0.22
        half = (shots - 1) * 0.5
        for si in range(shots):
            self._fire_laser(base + (si - half) * spread)

    def move(self, dt):
        global coins
        now = pygame.time.get_ticks()
        dp = self.donut_upgrade_power()
        mul = self.earnings_multiplier()
        flash_enabled_eff = self.flashing or dp > 0
        trail_enabled_eff = self.trail_enabled or dp > 0
        wave_enabled_eff = self.waves_enabled or dp > 0
        laser_power_eff = self.laser_purchases + dp
        lightning_power_eff = self.lightning_purchases + dp
        flash_amount_eff = self.flash_amount + dp * 10
        trail_income_eff = self.trail_income + dp * 5
        coin_bonus_eff = self.coin_bonus + dp
        wave_income_eff = self.wave_income + dp * 100
        donut_income_eff = DONUT_INCOME_PER_SEC * self.donut_ring_count if self.donut_enabled else 0
        god_income_eff = DONUT_INCOME_PER_SEC * 15 * self.goon_god_purchases if self.goon_god_enabled else 0

        if donut_income_eff > 0 and now - self.last_donut_income >= 1000:
            ticks = (now - self.last_donut_income) // 1000
            coins += donut_income_eff * ticks
            self.last_donut_income += ticks * 1000
        if god_income_eff > 0 and now - self.last_god_income >= 1000:
            ticks = (now - self.last_god_income) // 1000
            coins += god_income_eff * ticks
            self.last_god_income += ticks * 1000

        if self.implosion_frozen:
            if flash_enabled_eff and now >= self.next_flash:
                coins += flash_amount_eff * mul
                self.next_flash = now + self.flash_interval
                spawn_flash_particles(self.rect.centerx, self.rect.centery, self.color)
            if trail_enabled_eff and now - self.last_trail_income >= 1000:
                ticks = (now - self.last_trail_income) // 1000
                coins += trail_income_eff * mul * ticks
                self.last_trail_income += ticks * 1000
            return

        self.fx += self.speed_x * dt
        self.fy += self.speed_y * dt

        hit = False; side = None; sz = self.size

        if self.fx <= 0.0:
            self.fx = 0.0
            if self.speed_x < 0: self.speed_x = -self.speed_x
            hit = True; side = "left"
        elif self.fx + sz >= GAME_WIDTH:
            self.fx = float(GAME_WIDTH - sz)
            if self.speed_x > 0: self.speed_x = -self.speed_x
            hit = True; side = "right"

        if self.fy <= 0.0:
            self.fy = 0.0
            if self.speed_y < 0: self.speed_y = -self.speed_y
            hit = True
            if side is None: side = "top"
        elif self.fy + sz >= HEIGHT:
            self.fy = float(HEIGHT - sz)
            if self.speed_y > 0: self.speed_y = -self.speed_y
            hit = True
            if side is None: side = "bottom"

        self.rect.x = int(self.fx); self.rect.y = int(self.fy)
        self.draw_rect.x = round(self.fx); self.draw_rect.y = round(self.fy)
        self.draw_rect.width = self.draw_rect.height = self.size

        if hit:
            coins += (1 + coin_bonus_eff + wave_income_eff) * mul
            self.color = self._random_color()
            if wave_enabled_eff: self._spawn_wave(side)
            if lightning_power_eff > 0:
                payout = LIGHTNING_PAYOUT * lightning_power_eff * mul
                if len(lightning_sessions) < 5:
                    lightning_sessions.append(LightningSession(self, payout))
            if laser_power_eff > 0:
                beams_before = len(laser_beams)
                self._emit_lasers(side, dp)
                coins += (len(laser_beams) - beams_before) * 2000 * mul

        for other in bouncers:
            if other is self or other.implosion_frozen: continue
            if not self.rect.colliderect(other.rect): continue
            ox = self.rect.centerx - other.rect.centerx
            oy = self.rect.centery - other.rect.centery
            if ox == 0 and oy == 0: ox = 1
            d  = math.hypot(ox, oy); nx = ox/d; ny = oy/d
            ovx = (self.rect.width//2  + other.rect.width//2)  - abs(ox)
            ovy = (self.rect.height//2 + other.rect.height//2) - abs(oy)
            if ovx < ovy:
                push = ovx/2.0 + 1
                self.fx += nx*push;   other.fx -= nx*push
                self.speed_x, other.speed_x = other.speed_x, self.speed_x
            else:
                push = ovy/2.0 + 1
                self.fy += ny*push;   other.fy -= ny*push
                self.speed_y, other.speed_y = other.speed_y, self.speed_y
            gw = float(GAME_WIDTH); gh = float(HEIGHT)
            self.fx  = max(0.0, min(gw-self.size,  self.fx))
            self.fy  = max(0.0, min(gh-self.size,  self.fy))
            other.fx = max(0.0, min(gw-other.size, other.fx))
            other.fy = max(0.0, min(gh-other.size, other.fy))
            self.rect.x  = int(self.fx);  self.rect.y  = int(self.fy)
            other.rect.x = int(other.fx); other.rect.y = int(other.fy)
            self.draw_rect.x  = round(self.fx);  self.draw_rect.y  = round(self.fy)
            other.draw_rect.x = round(other.fx); other.draw_rect.y = round(other.fy)

        if flash_enabled_eff and now >= self.next_flash:
            coins += flash_amount_eff * mul
            self.next_flash = now + self.flash_interval
            spawn_flash_particles(self.rect.centerx, self.rect.centery, self.color)

        if trail_enabled_eff:
            # Store center position every frame; keep 60 points for longer ribbon
            cx_t = self.rect.centerx; cy_t = self.rect.centery
            if not self.trail_points or self.trail_points[-1] != (cx_t, cy_t):
                self.trail_points.append((cx_t, cy_t))
            if len(self.trail_points) > 60: self.trail_points.pop(0)
            if now - self.last_trail_income >= 1000:
                ticks = (now - self.last_trail_income) // 1000
                coins += trail_income_eff * mul * ticks
                self.last_trail_income += ticks * 1000

    def draw(self, surface):
        if self.implosion_frozen and self.implosion_enabled:
            return

        any_illum = any(b.illuminate_enabled for b in bouncers)

        if self.illuminate_enabled:
            # Visual upgrades hidden; bouncer itself is invisible (triangle takes over)
            if self.selected:
                pygame.draw.rect(surface, YELLOW, self.draw_rect, 2)
            return

        # When illuminate is active on any bouncer, shade all other bouncers (less opaque)
        if any_illum:
            shade = pygame.Surface((self.draw_rect.width, self.draw_rect.height), pygame.SRCALPHA)
            r, g, b = self.color
            dim = (max(0, r//4), max(0, g//4), max(0, b//4))
            shade.fill((*dim, 80))   # 80 alpha = subtle ghost
            surface.blit(shade, self.draw_rect.topleft)
            if self.selected:
                pygame.draw.rect(surface, (100, 100, 0), self.draw_rect, 1)
            return

        if self.trail_enabled or self.donut_upgrade_power() > 0:
            pts = self.trail_points
            if len(pts) > 1:
                dl = pygame.draw.line; dc = pygame.draw.circle; tc = TRAIL_COLORS
                for i in range(1, len(pts)):
                    col = tc[i % 40]
                    dl(surface, col, pts[i-1], pts[i], 28)
                    dc(surface, col, pts[i], 14)

        if self.implosion_enabled:
            pygame.draw.rect(surface, PURPLE, self.draw_rect.inflate(10,10), border_radius=8)

        # ── Bouncer body: rounded rect with highlight ─────────────────────
        r2 = self.draw_rect
        br  = min(10, max(1, min(r2.width, r2.height)//2))   # border radius
        pygame.draw.rect(surface, self.color, r2, border_radius=br)
        # Top highlight strip
        hr, hg, hb = self.color
        hi_col = (min(255,hr+80), min(255,hg+80), min(255,hb+80))
        hi_w = max(1, r2.width - 8)
        hi_h = max(1, r2.height // 3)
        hi_rect = pygame.Rect(r2.x + 4, r2.y + 4, hi_w, hi_h)
        if hi_rect.width > 0 and hi_rect.height > 0:
            hi_surf = pygame.Surface((hi_rect.width, hi_rect.height), pygame.SRCALPHA)
            hi_surf.fill((*hi_col, 60))
            surface.blit(hi_surf, hi_rect.topleft)
        # Dark bottom shadow strip
        sh_w = max(1, r2.width - 8)
        sh_h = max(1, r2.height // 3 - 4)
        sh_rect = pygame.Rect(r2.x + 4, r2.bottom - r2.height//3, sh_w, sh_h)
        if sh_rect.width > 0 and sh_rect.height > 0:
            sh_surf = pygame.Surface((sh_rect.width, sh_rect.height), pygame.SRCALPHA)
            sh_surf.fill((0, 0, 0, 50))
            surface.blit(sh_surf, sh_rect.topleft)
        # Label
        if r2.width >= 24 and r2.height >= 14:
            if goon_mode:
                lbl_text = "IMPLSN" if self.implosion_enabled else "GOON"
            else:
                lbl_text = "IMPLSN" if self.implosion_enabled else "BOUNCE"
            lbl = font.render(lbl_text, True, (0, 0, 0, 200))
            surface.blit(lbl, lbl.get_rect(center=r2.center))
        # Border glow when selected
        if self.selected:
            pygame.draw.rect(surface, YELLOW, r2, 3, border_radius=br)
        else:
            pygame.draw.rect(surface, (0,0,0,80), r2, 1, border_radius=br)


# ------------------ HELPERS ------------------
def reset_game():
    global coins, start_coins_override, free_shop, bouncers, selected_index, _hud_cache
    global wave_rings, laser_beams, flash_particles, explosion_particles
    global click_animations, implosion_effects, drip_particles, lightning_sessions, factories, _factory_income_timer, illuminate_effects, gravity_effects, _gravity_income_timer, mode3d_active, mode3d_effect, _3d_income_timer, shop_scroll_offset, all_goons_mode
    if cheat_mode:
        coins = DEV_COINS
    else:
        coins = start_coins_override if start_coins_override is not None else 0
    bouncers = [Bouncer(GAME_WIDTH//2, HEIGHT//2)]
    bouncers[0].selected = True
    selected_index = 0
    wave_rings.clear(); laser_beams.clear()
    flash_particles.clear(); explosion_particles.clear()
    click_animations.clear(); implosion_effects.clear()
    drip_particles.clear()
    lightning_sessions.clear()
    factories.clear()
    _factory_income_timer = 0
    illuminate_effects.clear()
    gravity_effects.clear()
    _gravity_income_timer = 0
    mode3d_active = False
    mode3d_effect = None
    _3d_income_timer = 0
    shop_scroll_offset = 0.0
    all_goons_mode = False
    _hud_cache.clear()

def total_donut_goons():
    return min(DONUT_GOON_MAX,
               sum(max(0, b.donut_ring_count) for b in bouncers if b.donut_enabled))

def total_goon_god_power():
    return sum(max(0, b.goon_god_purchases) for b in bouncers if b.goon_god_enabled)

def update_highscore():
    global highscore, _hs_dirty, _hs_save_timer
    if not cheat_mode and coins > highscore:
        highscore = coins; _hs_dirty = True
    now = pygame.time.get_ticks()
    if _hs_dirty and now - _hs_save_timer > 2000:
        save_highscore(highscore)
        _hs_dirty = False; _hs_save_timer = now


# ==================== SAVE / LOAD SYSTEM ====================
# Works on desktop (writes .json files next to the script).
# On web/pygbag file writes silently fail — progress only
# persists while the tab is open (green coins, etc stay in memory).

NUM_SAVE_SLOTS = 3

def _save_path(slot):
    return rel_path(f"save_slot_{slot}.json")

def save_game(slot):
    """Persist full game state to slot file. Silent-fail on web."""
    try:
        import json as _j
        data = {
            "coins":       coins,
            "green_coins": green_coins,
            "highscore":   highscore,
            "goon_mode":   goon_mode,
            "cheat_mode":  cheat_mode,
            "bouncers":    []
        }
        for b in bouncers:
            bd = {
                "size":b.size,"x":b.fx,"y":b.fy,
                "speed_x":b.speed_x,"speed_y":b.speed_y,
                "color":list(b.color),"selected":b.selected,
                "shop_data":b.shop_data,
                "waves_enabled":b.waves_enabled,
                "laser_enabled":b.laser_enabled,"laser_purchases":b.laser_purchases,
                "flashing":b.flashing,"flash_purchases":b.flash_purchases,
                "coin_bonus":b.coin_bonus,"trail_enabled":b.trail_enabled,
                "implosion_enabled":b.implosion_enabled,
                "lightning_enabled":b.lightning_enabled,"lightning_purchases":b.lightning_purchases,
                "illuminate_enabled":b.illuminate_enabled,
                "gravity_enabled":b.gravity_enabled,"gravity_purchases":b.gravity_purchases,
                "mode3d_enabled":b.mode3d_enabled,
                "donut_enabled":b.donut_enabled,"donut_ring_count":b.donut_ring_count,
                "goon_god_enabled":b.goon_god_enabled,"goon_god_purchases":b.goon_god_purchases,
            }
            data["bouncers"].append(bd)
        with open(_save_path(slot), "w") as f:
            _j.dump(data, f)
        return True
    except Exception:
        return False

def load_game_slot(slot):
    """Load slot into global state. Returns True on success."""
    global coins, green_coins, highscore, goon_mode, cheat_mode
    global bouncers, selected_index, _hud_cache, start_coins_override
    global wave_rings, laser_beams, flash_particles, explosion_particles
    global click_animations, implosion_effects, drip_particles, lightning_sessions
    global factories, _factory_income_timer, illuminate_effects
    global gravity_effects, _gravity_income_timer, mode3d_active, mode3d_effect
    global _3d_income_timer, shop_scroll_offset, all_goons_mode, free_shop
    try:
        import json as _j
        with open(_save_path(slot), "r") as f:
            data = _j.load(f)
        coins        = data.get("coins", 0)
        green_coins  = data.get("green_coins", 0)
        highscore    = data.get("highscore", 0)
        goon_mode    = data.get("goon_mode", False)
        cheat_mode   = data.get("cheat_mode", False)
        start_coins_override = coins
        # Clear effects
        wave_rings.clear(); laser_beams.clear()
        flash_particles.clear(); explosion_particles.clear()
        click_animations.clear(); implosion_effects.clear()
        drip_particles.clear(); lightning_sessions.clear()
        factories.clear(); illuminate_effects.clear(); gravity_effects.clear()
        _factory_income_timer=0; _gravity_income_timer=0
        mode3d_active=False; mode3d_effect=None; _3d_income_timer=0
        shop_scroll_offset=0.0; all_goons_mode=False; free_shop=False
        # Rebuild bouncers
        bouncers = []
        for bd in data.get("bouncers", []):
            b = Bouncer(int(bd.get("x",400)), int(bd.get("y",300)))
            b.size = bd.get("size", 80)
            b.fx = float(bd.get("x", 400)); b.fy = float(bd.get("y", 300))
            b.rect.x=int(b.fx); b.rect.y=int(b.fy)
            b.rect.width=b.rect.height=b.size
            b.draw_rect.x=b.rect.x; b.draw_rect.y=b.rect.y
            b.draw_rect.width=b.draw_rect.height=b.size
            b.speed_x=float(bd.get("speed_x",240)); b.speed_y=float(bd.get("speed_y",240))
            b.color=tuple(bd.get("color",[200,200,200]))
            b.selected=bd.get("selected",False)
            b.shop_data=bd.get("shop_data", build_shop_data())
            b.waves_enabled=bd.get("waves_enabled",False)
            b.laser_enabled=bd.get("laser_enabled",False)
            b.laser_purchases=bd.get("laser_purchases",0)
            b.flashing=bd.get("flashing",False)
            b.flash_purchases=bd.get("flash_purchases",0)
            b.coin_bonus=bd.get("coin_bonus",0)
            b.trail_enabled=bd.get("trail_enabled",False)
            b.implosion_enabled=bd.get("implosion_enabled",False)
            b.lightning_enabled=bd.get("lightning_enabled",False)
            b.lightning_purchases=bd.get("lightning_purchases",0)
            b.illuminate_enabled=bd.get("illuminate_enabled",False)
            b.gravity_enabled=bd.get("gravity_enabled",False)
            b.gravity_purchases=bd.get("gravity_purchases",0)
            b.mode3d_enabled=bd.get("mode3d_enabled",False)
            b.donut_enabled=bd.get("donut_enabled",False)
            b.donut_ring_count=bd.get("donut_ring_count",0)
            b.goon_god_enabled=bd.get("goon_god_enabled",False)
            b.goon_god_purchases=bd.get("goon_god_purchases",0)
            bouncers.append(b)
        if not bouncers:
            bouncers=[Bouncer(GAME_WIDTH//2, HEIGHT//2)]
        selected_index=next((i for i,b in enumerate(bouncers) if b.selected),0)
        bouncers[selected_index].selected=True
        _hud_cache.clear()
        return True
    except Exception:
        return False

def slot_info(slot):
    """Return display string for slot, or None if empty/unreadable."""
    try:
        import json as _j
        with open(_save_path(slot), "r") as f:
            data = _j.load(f)
        c  = data.get("coins", 0)
        gc = data.get("green_coins", 0)
        nb = len(data.get("bouncers", []))
        mode = " [GOON]" if data.get("goon_mode") else ""
        return f"Slot {slot+1}  {fmt_coins(c)}  |  {nb} bouncer{'s' if nb!=1 else ''}  |  G{gc}{mode}"
    except Exception:
        return None

# track which save slot we're in for in-game autosave
_current_save_slot = None   # None = new game (no file yet)
_save_msg          = ""
_save_msg_timer    = 0

def draw_menu():
    global _save_msg, _save_msg_timer
    screen.fill(DARK_BG)
    for bg in bg_bouncers: bg.update(); bg.draw(screen)

    now_t = pygame.time.get_ticks()
    update_spawn_drips(now_t)
    draw_drips(screen)

    if goon_mode:
        title_str="GOON EMPIRE"; shadow_col=(0,40,0); c1=(0,200,80); c2=(100,255,150)
    else:
        title_str="BOUNCE EMPIRE"; shadow_col=(60,30,0); c1=ORANGE; c2=GOLD

    shadow=title_font.render(title_str,True,shadow_col)
    screen.blit(shadow,shadow.get_rect(center=(WIDTH//2+4,HEIGHT//2-116)))
    t1=title_font.render(title_str,True,c1); t2=title_font.render(title_str,True,c2)
    screen.blit(t1,t1.get_rect(center=(WIDTH//2,HEIGHT//2-120)))
    screen.blit(t2,t2.get_rect(center=(WIDTH//2,HEIGHT//2-122)))

    hs_surf=med_font.render(f"HIGH SCORE:  \xa3{highscore}",True,GOLD)
    screen.blit(hs_surf,hs_surf.get_rect(center=(WIDTH//2,HEIGHT//2+10)))

    mx,my=pygame.mouse.get_pos()

    # ── 3 save-slot buttons ──────────────────────────────────────────────
    slot_rects=[]
    for s in range(NUM_SAVE_SLOTS):
        info=slot_info(s)
        bw=520; bh=54
        bx=WIDTH//2-bw//2
        by=HEIGHT//2+55+s*(bh+12)
        rect=pygame.Rect(bx,by,bw,bh)
        slot_rects.append(rect)
        hov=rect.collidepoint(mx,my)
        if info:
            # filled slot
            pygame.draw.rect(screen,(35,75,120) if hov else (22,52,85),rect,border_radius=12)
            pygame.draw.rect(screen,(90,170,255),rect,2,border_radius=12)
            lbl=font.render(info,True,(200,230,255))
            screen.blit(lbl,lbl.get_rect(center=rect.center))
        else:
            # empty — new game
            pygame.draw.rect(screen,(55,130,55) if hov else (38,92,38),rect,border_radius=12)
            pygame.draw.rect(screen,GREEN,rect,2,border_radius=12)
            lbl=med_font.render(f"NEW GAME  —  Slot {s+1}",True,BLACK)
            screen.blit(lbl,lbl.get_rect(center=rect.center))

    hint=font.render("Click a slot to play  |  ESC to quit",True,(120,120,120))
    screen.blit(hint,(WIDTH//2-hint.get_width()//2,HEIGHT-40))

    # Save message feedback
    if _save_msg and now_t < _save_msg_timer:
        ms=font.render(_save_msg,True,GOLD)
        screen.blit(ms,ms.get_rect(center=(WIDTH//2,HEIGHT//2+42)))

    code_btn=pygame.Rect(WIDTH-104,HEIGHT-50,90,36)
    chov=code_btn.collidepoint(mx,my)
    pygame.draw.rect(screen,(80,80,120) if chov else (45,45,70),code_btn,border_radius=8)
    pygame.draw.rect(screen,(100,100,160),code_btn,2,border_radius=8)
    screen.blit(font.render("CODE",True,(180,180,255)),font.render("CODE",True,(180,180,255)).get_rect(center=code_btn.center))

    if cheat_mode: screen.blit(font.render("\u2605 DEV MODE ON \u2605",True,GOLD),(14,HEIGHT-40))
    if goon_mode:  screen.blit(font.render("\U0001f4a6 GOON MODE ON \U0001f4a6",True,(100,255,150)),(14,HEIGHT-65))

    return slot_rects, code_btn

def draw_code_screen():
    ov=pygame.Surface((WIDTH,HEIGHT),pygame.SRCALPHA)
    ov.fill((0,0,0,170)); screen.blit(ov,(0,0))
    pw,ph=420,260
    panel=pygame.Rect((WIDTH-pw)//2,(HEIGHT-ph)//2,pw,ph)
    pygame.draw.rect(screen,(30,30,50),panel,border_radius=16)
    pygame.draw.rect(screen,(100,100,180),panel,2,border_radius=16)
    t=big_font.render("ENTER CODE",True,WHITE)
    screen.blit(t,t.get_rect(center=(WIDTH//2,panel.y+40)))
    ibox=pygame.Rect(panel.x+40,panel.y+90,pw-80,56)
    pygame.draw.rect(screen,(15,15,30),ibox,border_radius=8)
    pygame.draw.rect(screen,(120,120,200),ibox,2,border_radius=8)
    ds="*"*len(code_input) if code_input else ""
    inp=med_font.render(ds or "____",True,(200,200,255) if code_input else (80,80,100))
    screen.blit(inp,inp.get_rect(center=ibox.center))
    now=pygame.time.get_ticks()
    if code_message and now<code_msg_timer:
        col=GOLD if code_message.startswith("\u2605") else RED
        msg=font.render(code_message,True,col)
        screen.blit(msg,msg.get_rect(center=(WIDTH//2,panel.y+170)))
    hint=font.render("ENTER to confirm  \u2022  ESC to go back",True,(100,100,130))
    screen.blit(hint,hint.get_rect(center=(WIDTH//2,panel.y+215)))


# ------------------ INIT ------------------
bouncers            = []
selected_index      = 0
_shop_header_surf   = big_font.render("BOUNCER UPGRADES", True, WHITE)
_goon_header_surf   = big_font.render("GOON UPGRADES", True, (100,255,150))
reset_game()
highscore = load_highscore()

# ------------------ MAIN LOOP ------------------
async def main():
    global state, code_input, code_message, code_msg_timer
    global cheat_mode, goon_mode, highscore, coins
    global shop_scroll_offset, selected_index, mode3d_active, mode3d_effect
    global start_coins_override, free_shop, all_goons_mode
    global _current_save_slot, _save_msg, _save_msg_timer

    while True:
        raw_ms = clock.tick(60)
        dt     = min(raw_ms / 1000.0, 0.05)
        mx, my = pygame.mouse.get_pos()

        # ========== MENU ==========
        if state == STATE_MENU:
            slot_rects, code_btn = draw_menu()
            for event in pygame.event.get():
                if event.type == pygame.QUIT: pygame.quit(); sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE: pygame.quit(); sys.exit()
                if event.type == pygame.MOUSEBUTTONDOWN:
                    for s, rect in enumerate(slot_rects):
                        if rect.collidepoint(mx, my):
                            if slot_info(s):
                                load_game_slot(s)
                                _current_save_slot = s
                            else:
                                reset_game()
                                _current_save_slot = s
                            state = STATE_GAME
                            break
                    else:
                        if code_btn.collidepoint(mx, my):
                            state = STATE_CODE; code_input = ""; code_message = ""
            pygame.display.flip()

        # ========== CODE ENTRY ==========
        elif state == STATE_CODE:
            slot_rects, code_btn = draw_menu()
            draw_code_screen()
            for event in pygame.event.get():
                if event.type == pygame.QUIT: pygame.quit(); sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        state = STATE_MENU
                    elif event.key == pygame.K_BACKSPACE:
                        code_input = code_input[:-1]
                    elif event.key == pygame.K_RETURN:
                        if code_input == "1234":
                            cheat_mode = not cheat_mode
                            if cheat_mode: start_coins_override=None; free_shop=False
                            code_message="\u2605 DEV MODE ACTIVATED \u2605" if cheat_mode else "\u2605 DEV MODE DEACTIVATED \u2605"
                            highscore=load_highscore(); _hud_cache.clear()
                            code_msg_timer=pygame.time.get_ticks()+1800
                            pygame.display.flip(); pygame.time.wait(1800)
                            state=STATE_MENU; code_input=""
                        elif code_input=="1111":
                            cheat_mode=False; goon_mode=False; start_coins_override=None; free_shop=True; coins=0
                            for b in bouncers: b.sync_shop_data()
                            drip_particles.clear(); _hud_cache.clear()
                            code_message="\u2605 NORMAL MODE: FREE SHOP \u2605"
                            highscore=load_highscore()
                            code_msg_timer=pygame.time.get_ticks()+1800
                            pygame.display.flip(); pygame.time.wait(1800)
                            state=STATE_MENU; code_input=""
                        elif code_input=="6969":
                            goon_mode=not goon_mode; start_coins_override=None; free_shop=False
                            for b in bouncers: b.sync_shop_data()
                            drip_particles.clear(); _hud_cache.clear()
                            code_message="\U0001f4a6 GOON MODE ACTIVATED \U0001f4a6" if goon_mode else "\U0001f4a6 GOON MODE DEACTIVATED \U0001f4a6"
                            highscore=load_highscore()
                            code_msg_timer=pygame.time.get_ticks()+1800
                            pygame.display.flip(); pygame.time.wait(1800)
                            state=STATE_MENU; code_input=""
                        else:
                            code_message="WRONG CODE"
                            code_msg_timer=pygame.time.get_ticks()+1200
                            code_input=""
                    elif event.unicode and event.unicode.isprintable() and len(code_input)<8:
                        code_input+=event.unicode
            pygame.display.flip()

        # ========== GAME ==========
        else:
            screen.fill(DARK_BG)
            now_g = pygame.time.get_ticks()
            if not mode3d_active:
                update_spawn_drips(now_g)
                draw_drips(screen)
            selected_bouncer = bouncers[selected_index]
            selected_bouncer.sync_shop_data()
            shop_scroll_offset = max(0.0, min(shop_scroll_offset, shop_max_scroll(len(selected_bouncer.shop_data))))

            for event in pygame.event.get():
                if event.type == pygame.QUIT: pygame.quit(); sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        update_highscore()
                        if _current_save_slot is not None:
                            ok = save_game(_current_save_slot)
                            _save_msg = f"\u2713 Saved to Slot {_current_save_slot+1}" if ok else "Save failed (web mode)"
                            _save_msg_timer = pygame.time.get_ticks() + 2500
                        state = STATE_MENU

                if event.type == pygame.MOUSEWHEEL and mx >= GAME_WIDTH:
                    max_sc = shop_max_scroll(len(selected_bouncer.shop_data))
                    shop_scroll_offset = max(0.0, min(max_sc, shop_scroll_offset - event.y * 48.0))

                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button in (4, 5):
                        if mx >= GAME_WIDTH:
                            max_sc = shop_max_scroll(len(selected_bouncer.shop_data))
                            step = -48.0 if event.button == 4 else 48.0
                            shop_scroll_offset = max(0.0, min(max_sc, shop_scroll_offset + step))
                        continue
                    if event.button != 1:
                        continue
                    tab_rect, left_btn, right_btn, all_btn = shop_nav_rects()
                    if left_btn.collidepoint(mx, my):
                        all_goons_mode = False
                        select_bouncer(selected_index - 1)
                        continue
                    if right_btn.collidepoint(mx, my):
                        all_goons_mode = False
                        select_bouncer(selected_index + 1)
                        continue
                    if all_btn.collidepoint(mx, my):
                        all_goons_mode = not all_goons_mode
                        shop_scroll_offset = 0.0
                        continue
                    # Determine which shop list to use
                    if all_goons_mode and len(bouncers) > 1:
                        active_shop_items = all_goons_shop_data()
                    else:
                        active_shop_items = selected_bouncer.shop_data

                    for i, item in enumerate(active_shop_items):
                        row_rect = shop_item_rect(i, shop_scroll_offset)
                        if row_rect.bottom < SHOP_PANEL_TOP or row_rect.top > HEIGHT: continue
                        if not row_rect.collidepoint(mx, my): continue
                        if all_goons_mode and len(bouncers) > 1:
                            if not all_goons_is_unlocked(i): continue
                        else:
                            if not selected_bouncer.is_unlocked(i): continue
                        act = item["action"]
                        if act == "size" and item["bought"] >= 25: continue
                        if act == "donut" and total_donut_goons() >= DONUT_GOON_MAX: continue
                        if act == "bonus" and len(bouncers) >= 20: continue
                        if not cheat_mode and not free_shop and coins < item["price"]: continue
                        if not cheat_mode and not free_shop: coins -= item["price"]
                        click_animations.append({"rect": row_rect.copy(), "time": pygame.time.get_ticks()})

                        if all_goons_mode and len(bouncers) > 1:
                            # Apply upgrade to ALL bouncers
                            targets = list(bouncers)
                        else:
                            targets = [selected_bouncer]

                        for target_b in targets:
                          if i >= len(target_b.shop_data): continue
                          t_item = target_b.shop_data[i]
                          t_item["bought"] += 1
                          target_b.increase_price(t_item)
                          act = t_item["action"]
                          if act == "speed":
                            speed_item = next(it for it in target_b.shop_data if it["action"]=="speed")
                            if speed_item["bought"] <= 25:
                                MAX_SPEED = 2500.0
                                nx = target_b.speed_x * 1.05
                                ny = target_b.speed_y * 1.05
                                spd = math.hypot(nx, ny)
                                if spd > MAX_SPEED:
                                    scale = MAX_SPEED / spd
                                    nx *= scale; ny *= scale
                                target_b.speed_x = nx
                                target_b.speed_y = ny
                          elif act == "size":
                            ccx = target_b.rect.centerx; ccy = target_b.rect.centery
                            target_b.size = int(target_b.size * 1.05)
                            target_b.rect.width = target_b.rect.height = target_b.size
                            target_b.rect.center = (ccx, ccy)
                            target_b.draw_rect.width = target_b.draw_rect.height = target_b.size
                            target_b.draw_rect.center = (ccx, ccy)
                            target_b.fx = float(target_b.rect.x)
                            target_b.fy = float(target_b.rect.y)
                          elif act == "flash":
                            target_b.flashing = True
                            target_b.flash_purchases += 1
                            target_b.flash_interval = 5000 // target_b.flash_purchases
                            target_b.color = target_b._random_color()
                          elif act == "bonus":
                            if len(bouncers) < 20:
                                bouncers.append(Bouncer(GAME_WIDTH//3, HEIGHT//3))
                          elif act == "jew":
                            target_b.coin_bonus += 1
                          elif act == "wave":
                            target_b.waves_enabled = True
                            target_b.wave_income  += 100
                          elif act == "laser":
                            target_b.laser_enabled   = True
                            target_b.laser_purchases += 1
                          elif act == "trail":
                            target_b.trail_enabled = True
                            target_b.trail_income  += 5
                          elif act == "implosion":
                            if not target_b.implosion_enabled:
                                target_b.implosion_enabled = True
                                implosion_effects.append(ImplosionEffect(target_b))
                          elif act == "lightning":
                            target_b.lightning_enabled = True
                            target_b.lightning_purchases += 1
                          elif act == "factory":
                            n = len(factories) + 1
                            new_factories = []
                            for fi in range(n):
                                fx2 = int(GAME_WIDTH * (fi + 1) / (n + 1))
                                new_factories.append(Factory(fx2))
                            factories.clear()
                            factories.extend(new_factories)
                          elif act == "illuminate":
                            target_b.illuminate_enabled = True
                            n = sum(1 for b in bouncers if b.illuminate_enabled)
                            illuminate_effects.clear()
                            for ei in range(n):
                                eff = IlluminateEffect()
                                eff.cx = int(GAME_WIDTH * (ei + 1) / (n + 1))
                                eff.cy = HEIGHT // 2
                                illuminate_effects.append(eff)
                          elif act == "gravity":
                            target_b.gravity_enabled = True
                            target_b.gravity_purchases += 1
                            existing = [e for e in gravity_effects if e.bouncer is target_b]
                            if not existing:
                                gravity_effects.append(GravityWellEffect(target_b))
                          elif act == "mode3d":
                            target_b.mode3d_enabled = True
                            mode3d_active = True
                            mode3d_effect = Mode3DEffect()
                          elif act == "donut":
                            target_b.donut_enabled = True
                            target_b.donut_ring_count += 1
                          elif act == "goongod":
                            target_b.goon_god_enabled = True
                            target_b.goon_god_purchases += 1
                          elif act == "newworld":
                            await new_world_cinematic(screen, clock, WIDTH, HEIGHT, font)

                    for i, b in enumerate(bouncers):
                        if b.rect.collidepoint(mx, my):
                            select_bouncer(i)

            update_highscore()
            if cheat_mode: coins = DEV_COINS

            for eff in implosion_effects: eff.update()
            for b in bouncers: b.move(dt)
            update_mode3d(dt, now_g)

            if mode3d_active:
                # 3D mode draws its own complete world — skip all 2D drawing.
                # Physics still run above for coin/income correctness.
                # Illuminate/factory/gravity income runs inside their own update() calls.
                for eff in illuminate_effects: eff.update()
                update_factories(dt, now_g)
                update_gravity_wells(dt, now_g)
                # Wave/laser/lightning still need to update (income triggers)
                for ring in wave_rings:   ring.update()
                wave_rings[:] = [r for r in wave_rings if r.alive]
                for beam in laser_beams:  beam.update()
                laser_beams[:] = [b for b in laser_beams if b.alive]
                if len(laser_beams) > LASER_MAX_ACTIVE_BEAMS:
                    del laser_beams[:-LASER_MAX_ACTIVE_BEAMS]
                for ls in lightning_sessions: ls.update()
                lightning_sessions[:] = [ls for ls in lightning_sessions if ls.alive]
                draw_mode3d_post(screen)
            else:
                for eff in implosion_effects: eff.draw(screen)
                for b in bouncers: b.draw(screen)
                for eff in implosion_effects: eff.draw_cooldown_hud(screen)

                update_draw_particles(flash_particles,     screen, False)
                update_draw_particles(explosion_particles, screen, True)

                for ring in wave_rings:   ring.update(); ring.draw(screen)
                wave_rings[:]  = [r for r in wave_rings  if r.alive]

                for beam in laser_beams:  beam.update()
                laser_beams[:] = [b for b in laser_beams if b.alive]
                if len(laser_beams) > LASER_MAX_ACTIVE_BEAMS:
                    del laser_beams[:-LASER_MAX_ACTIVE_BEAMS]
                for beam in laser_beams:  beam.draw(screen)

                update_factories(dt, now_g)
                draw_factories(screen, now_g)

                for ls in lightning_sessions: ls.update(); ls.draw(screen)
                lightning_sessions[:] = [ls for ls in lightning_sessions if ls.alive]

                for eff in illuminate_effects: eff.update(); eff.draw(screen)

                update_gravity_wells(dt, now_g)
                draw_gravity_wells(screen, now_g)

            # ---- SHOP PANEL ----
            # Background gradient: dark left edge, slightly lighter right
            pygame.draw.rect(screen, (28, 28, 32), (GAME_WIDTH, 0, SHOP_WIDTH, HEIGHT))
            # Subtle left-edge separator line
            pygame.draw.line(screen, (80, 60, 120), (GAME_WIDTH, 0), (GAME_WIDTH, HEIGHT), 2)

            tab_rect, left_btn, right_btn, all_btn = shop_nav_rects()
            pygame.draw.rect(screen, (24, 24, 30), tab_rect, border_radius=8)
            pygame.draw.rect(screen, (90, 90, 110), tab_rect, 1, border_radius=8)

            hover_left = left_btn.collidepoint(mx, my)
            hover_right = right_btn.collidepoint(mx, my)
            hover_all = all_btn.collidepoint(mx, my)
            btn_col = (120, 180, 120) if hover_left else (70, 120, 70)
            pygame.draw.rect(screen, btn_col, left_btn, border_radius=6)
            pygame.draw.rect(screen, (30, 50, 30), left_btn, 1, border_radius=6)

            btn_col = (120, 180, 120) if hover_right else (70, 120, 70)
            pygame.draw.rect(screen, btn_col, right_btn, border_radius=6)
            pygame.draw.rect(screen, (30, 50, 30), right_btn, 1, border_radius=6)

            # ALL button — glows gold when active
            all_active_col  = (200, 160, 20) if all_goons_mode else ((160, 140, 60) if hover_all else (80, 70, 30))
            all_border_col  = (255, 215, 0)  if all_goons_mode else (120, 110, 50)
            pygame.draw.rect(screen, all_active_col, all_btn, border_radius=5)
            pygame.draw.rect(screen, all_border_col, all_btn, 1, border_radius=5)
            all_lbl = pygame.font.SysFont(None, 18).render("ALL", True, (255, 255, 180) if all_goons_mode else (200, 190, 140))
            screen.blit(all_lbl, all_lbl.get_rect(center=all_btn.center))

            # Arrow glyphs
            lc = left_btn.center
            pygame.draw.polygon(screen, (10, 20, 10),
                                [(lc[0] + 4, lc[1] - 6), (lc[0] + 4, lc[1] + 6), (lc[0] - 4, lc[1])])
            rc = right_btn.center
            pygame.draw.polygon(screen, (10, 20, 10),
                                [(rc[0] - 4, rc[1] - 6), (rc[0] - 4, rc[1] + 6), (rc[0] + 4, rc[1])])

            label_prefix = "GOON" if goon_mode else "BOUNCER"
            if all_goons_mode and len(bouncers) > 1:
                label = f"ALL {len(bouncers)} {label_prefix}S"
            else:
                label = f"{label_prefix} {selected_index+1}/{max(1,len(bouncers))}"
            lbl = font.render(label, True, (255, 215, 0) if all_goons_mode else (200, 200, 220))
            screen.blit(lbl, lbl.get_rect(center=(tab_rect.centerx - 12, tab_rect.centery)))

            now = pygame.time.get_ticks()
            shop_t = now / 1000.0

            # Colour palette per action
            SHOP_THEME = {
                "speed":     ((40,40,50),    (120,200,255), "⚡"),
                "size":      ((40,50,40),    (100,220,120), "⬛"),
                "jew":       ((50,45,20),    (255,215,0),   "🪙"),
                "flash":     ((50,40,50),    (220,120,255), "✦"),
                "trail":     ((25,45,55),    (80,220,200),  "〰"),
                "bonus":     ((50,40,30),    (255,160,60),  "＋"),
                "wave":      ((25,40,60),    (60,160,255),  "〜"),
                "laser":     ((55,25,25),    (255,80,60),   "⊛"),
                "implosion": ((40,20,55),    (180,60,255),  "◎"),
                "lightning": ((20,20,50),    (120,140,255), "⌁"),
                "factory":   ((20,40,20),    (60,210,100),  "⚙"),
                "illuminate":((45,30,5),     (255,200,40),  "△"),
                "gravity":   ((30,10,50),    (200,80,255),  "◉"),
                "mode3d":    ((10,20,50),    (80,200,255),  "■"),
                "donut":     ((15,45,35),    (100,255,180), "◌"),
                "goongod":   ((32,32,44),    (235,235,255), "⚡"),
            }

            def draw_shop_icon(act, rect, accent_col, unlocked):
                icon_bg = pygame.Rect(rect.x + 8, rect.y + 8, 40, rect.height - 16)
                pygame.draw.rect(screen, (20, 20, 24) if unlocked else (35, 35, 40), icon_bg, border_radius=8)
                pygame.draw.rect(screen, accent_col if unlocked else (70, 70, 76), icon_bg, 1, border_radius=8)
                cx, cy = icon_bg.centerx, icon_bg.centery
                ic = accent_col if unlocked else (100, 100, 110)

                if act == "speed":
                    pts = [(cx - 5, cy - 10), (cx + 1, cy - 3), (cx - 2, cy - 3), (cx + 5, cy + 10), (cx - 1, cy + 2), (cx + 2, cy + 2)]
                    pygame.draw.polygon(screen, ic, pts)
                elif act == "size":
                    pygame.draw.rect(screen, ic, (cx - 8, cy - 8, 16, 16), 2, border_radius=2)
                elif act == "jew":
                    pygame.draw.circle(screen, ic, (cx, cy), 9, 2)
                    pygame.draw.circle(screen, ic, (cx, cy), 3)
                elif act == "flash":
                    pygame.draw.line(screen, ic, (cx - 9, cy), (cx + 9, cy), 2)
                    pygame.draw.line(screen, ic, (cx, cy - 9), (cx, cy + 9), 2)
                elif act == "trail":
                    for k in range(3):
                        pygame.draw.line(screen, ic, (cx - 10 + k * 4, cy - 8), (cx - 4 + k * 4, cy + 8), 2)
                elif act == "bonus":
                    pygame.draw.line(screen, ic, (cx - 8, cy), (cx + 8, cy), 3)
                    pygame.draw.line(screen, ic, (cx, cy - 8), (cx, cy + 8), 3)
                elif act == "wave":
                    for k in range(3):
                        pygame.draw.arc(screen, ic, (cx - 12 + k * 4, cy - 8, 12, 16), math.pi * 0.15, math.pi * 0.85, 2)
                elif act == "laser":
                    pygame.draw.line(screen, ic, (cx - 10, cy), (cx + 10, cy), 3)
                    pygame.draw.circle(screen, ic, (cx + 10, cy), 3)
                elif act == "implosion":
                    pygame.draw.circle(screen, ic, (cx, cy), 10, 2)
                    pygame.draw.circle(screen, ic, (cx, cy), 4, 1)
                elif act == "lightning":
                    pts = [(cx - 5, cy - 10), (cx + 1, cy - 2), (cx - 2, cy - 2), (cx + 4, cy + 10), (cx - 2, cy + 1), (cx + 1, cy + 1)]
                    pygame.draw.polygon(screen, ic, pts)
                elif act == "factory":
                    pygame.draw.rect(screen, ic, (cx - 10, cy - 7, 20, 14), 2)
                    pygame.draw.rect(screen, ic, (cx - 4, cy - 13, 8, 6), 2)
                elif act == "illuminate":
                    pygame.draw.polygon(screen, ic, [(cx, cy - 10), (cx - 9, cy + 8), (cx + 9, cy + 8)], 2)
                elif act == "gravity":
                    pygame.draw.circle(screen, ic, (cx, cy), 10, 2)
                    pygame.draw.circle(screen, ic, (cx + 4, cy), 3)
                elif act == "mode3d":
                    pygame.draw.rect(screen, ic, (cx - 8, cy - 8, 16, 16), 2)
                    pygame.draw.line(screen, ic, (cx - 8, cy - 8), (cx - 3, cy - 13), 1)
                    pygame.draw.line(screen, ic, (cx + 8, cy - 8), (cx + 13, cy - 13), 1)
                elif act == "donut":
                    pygame.draw.circle(screen, ic, (cx, cy), 10, 2)
                    pygame.draw.circle(screen, (20, 20, 24), (cx, cy), 4)
                elif act == "goongod":
                    pygame.draw.circle(screen, ic, (cx, cy - 5), 5)
                    pygame.draw.line(screen, ic, (cx, cy), (cx, cy + 10), 3)
                    pygame.draw.line(screen, ic, (cx - 8, cy + 2), (cx + 8, cy + 2), 2)
                    pygame.draw.line(screen, ic, (cx - 5, cy - 11), (cx - 2, cy - 15), 2)
                    pygame.draw.line(screen, ic, (cx + 5, cy - 11), (cx + 2, cy - 15), 2)
                else:
                    pygame.draw.circle(screen, ic, (cx, cy), 8, 2)

            # Choose data source for shop display
            if all_goons_mode and len(bouncers) > 1:
                display_shop_data = all_goons_shop_data()
                def display_is_unlocked(idx): return all_goons_is_unlocked(idx)
            else:
                display_shop_data = selected_bouncer.shop_data
                def display_is_unlocked(idx): return selected_bouncer.is_unlocked(idx)

            max_sc = shop_max_scroll(len(display_shop_data))
            shop_scroll_offset = max(0.0, min(max_sc, shop_scroll_offset))
            shop_clip = pygame.Rect(GAME_WIDTH, SHOP_PANEL_TOP, SHOP_WIDTH, HEIGHT - SHOP_PANEL_TOP)
            prev_clip = screen.get_clip()
            screen.set_clip(shop_clip)

            for i, item in enumerate(display_shop_data):
                rect     = shop_item_rect(i, shop_scroll_offset)
                if rect.bottom < SHOP_PANEL_TOP or rect.top > HEIGHT:
                    continue
                unlocked = display_is_unlocked(i)
                act      = item["action"]

                theme = SHOP_THEME.get(act, ((50,50,50),(200,200,200),"?"))
                bg_col, accent_col, icon = theme[0], theme[1], theme[2] if len(theme)>2 else "?"

                # ALL mode: tint rows gold
                if all_goons_mode and len(bouncers) > 1 and unlocked:
                    bg = tuple(min(255, int(c * 0.7 + g * 0.3)) for c, g in zip(bg_col, (40, 34, 5)))
                elif unlocked:
                    bg = bg_col
                else:
                    bg = (30, 30, 34)
                pygame.draw.rect(screen, bg, rect, border_radius=7)

                # Animated accent border for unlocked items
                if unlocked:
                    border_alpha = int(160 + 80 * math.sin(shop_t * 2.0 + i * 0.7))
                    bc = tuple(min(255, int(c * border_alpha / 240)) for c in accent_col)
                    if all_goons_mode and len(bouncers) > 1:
                        bc = (min(255, bc[0]+40), min(255, bc[1]+30), max(0, bc[2]-20))
                    pygame.draw.rect(screen, bc, rect, 1, border_radius=7)
                else:
                    pygame.draw.rect(screen, (55, 55, 60), rect, 1, border_radius=7)

                # Left accent stripe
                stripe_rect = pygame.Rect(rect.x, rect.y + 5, 4, rect.height - 10)
                pygame.draw.rect(screen, accent_col if unlocked else (60,60,65), stripe_rect, border_radius=2)
                draw_shop_icon(act, rect, accent_col, unlocked)

                tc = (230, 230, 235) if unlocked else (90, 90, 100)
                if all_goons_mode and len(bouncers) > 1 and unlocked:
                    tc = (255, 240, 160)  # gold tint in ALL mode

                # ── Build label text ───────────────────────────────────────────────
                if act == "size":
                    limit_tag = " LIMITED" if item["bought"] >= 25 else ""
                    np = f"{item['name']} x{item['bought']}{limit_tag}"
                elif act == "flash" and selected_bouncer.flashing:
                    np = f"{item['name']} x{item['bought']}  [{5000/selected_bouncer.flash_purchases/1000:.1f}s]"
                elif act == "laser" and selected_bouncer.laser_enabled:
                    np = f"{item['name']} x{item['bought']}  [{selected_bouncer.laser_purchases}b]"
                elif act == "implosion" and selected_bouncer.implosion_enabled:
                    total_s = IMPLOSION_BASE_WINDOW / max(selected_bouncer.bought_count("implosion"), 1) / 1000
                    np = f"{item['name']} x{item['bought']}  [{total_s:.0f}s]"
                elif act == "lightning" and selected_bouncer.lightning_enabled:
                    payout_k = selected_bouncer.lightning_purchases * 100
                    np = f"{item['name']} x{item['bought']}  [£{payout_k}K]"
                elif act == "factory" and len(factories) > 0:
                    np = f"{item['name']} x{item['bought']}  [{len(factories)} £100M/s]"
                elif act == "illuminate" and selected_bouncer.illuminate_enabled:
                    np = f"{item['name']} x{item['bought']}  [+£50B/s]"
                elif act == "gravity" and selected_bouncer.gravity_enabled:
                    np = f"{item['name']} x{item['bought']}  [+£1T/s]"
                elif act == "mode3d" and selected_bouncer.mode3d_enabled:
                    np = f"{item['name']} x{item['bought']}  [+£75T/s]"
                elif act == "donut" and selected_bouncer.donut_enabled:
                    cnt_total = total_donut_goons()
                    cnt_own = selected_bouncer.donut_ring_count
                    np = f"{item['name']} x{item['bought']}  [{cnt_total}/{DONUT_GOON_MAX} ring • own:{cnt_own} • 1000T / sec]"
                elif act == "goongod" and selected_bouncer.goon_god_enabled:
                    gp = total_goon_god_power()
                    np = f"{item['name']} x{item['bought']}  [ZEUS x{gp} • +15x donut]"
                else:
                    np = f"{item['name']} x{item['bought']}"

                # Show "× N goons" suffix in ALL mode
                if all_goons_mode and len(bouncers) > 1:
                    np = np + f"  ×{len(bouncers)}"

                pp = fmt_price(item["price"])
                if not unlocked:
                    pc = (70, 70, 80)
                elif cheat_mode or coins >= item["price"]:
                    pc = (80, 255, 120)
                else:
                    pc = (255, 80, 80)

                # Name left-aligned, price right-aligned
                ns = hud_surf(f"n{i}{'A' if all_goons_mode else ''}", np,  font, tc)
                ps = hud_surf(f"p{i}{'A' if all_goons_mode else ''}", pp,  font, pc)
                screen.blit(ns, (rect.x + 56, rect.y + 11))
                screen.blit(ps, (rect.right - ps.get_width() - 8, rect.y + 30))

            # Scroll bar
            viewport_h = HEIGHT - SHOP_PANEL_TOP - SHOP_PANEL_BOTTOM_PAD
            if max_sc > 0.0 and viewport_h > 8:
                track = pygame.Rect(GAME_WIDTH + SHOP_WIDTH - 8, SHOP_PANEL_TOP, 4, viewport_h)
                pygame.draw.rect(screen, (50, 50, 56), track, border_radius=2)
                thumb_h = max(18, int(viewport_h * (viewport_h / (viewport_h + max_sc))))
                thumb_y = int(SHOP_PANEL_TOP + (viewport_h - thumb_h) * (shop_scroll_offset / max_sc))
                thumb = pygame.Rect(track.x, thumb_y, track.width, thumb_h)
                pygame.draw.rect(screen, (140, 140, 155), thumb, border_radius=2)

            screen.set_clip(prev_clip)

            click_animations[:] = [a for a in click_animations if now-a["time"] < CLICK_ANIM_TIME]
            for anim in click_animations:
                pygame.draw.rect(screen, (80, 255, 120), anim["rect"], 3, border_radius=7)

            screen.blit(hud_surf("coins", fmt_coins(coins),        big_font, GREEN),        (20, 20))
            screen.blit(hud_surf("hs",    f"Best: \xa3{highscore}", font,     GOLD),         (20, 55))
            if green_coins > 0:
                _gc_label = fmt_nw_coins(green_coins)
                screen.blit(hud_surf("gc", f"G {_gc_label}", font, (80, 220, 100)), (20, 72))
            _hud_y2 = 72 + (20 if green_coins > 0 else 6)
            if cheat_mode:
                screen.blit(hud_surf("dev", "\u2605 DEV MODE \u2605", font, GOLD), (20, _hud_y2))
            if goon_mode:
                screen.blit(hud_surf("goon", "\U0001f4a6 GOON MODE \U0001f4a6", font, (100,255,150)), (20, _hud_y2 if not cheat_mode else _hud_y2+20))
            screen.blit(hud_surf("esc",   "ESC = Menu",             font,     (100,100,100)),(20, HEIGHT-30))

            pygame.display.flip()

        await asyncio.sleep(0)


if __name__ == "__main__":
    asyncio.run(main())
