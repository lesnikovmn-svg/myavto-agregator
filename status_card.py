"""
T-158: генератор карточки "статус в WhatsApp" (1080x1920 PNG) под бренд
MY Avto (my-avto.online) — золото/чёрный, Unbounded+Inter.

Визуальный эталон — /root/myavto-status-template/Main.dc.html (Claude Design
canvas, опубликован как Artifact в этой же сессии). Здесь та же раскладка
воспроизведена через Pillow для серверной автогенерации, без обращения к
браузеру/canvas.

Явные упрощения относительно .dc.html-эталона (сознательный выбор ради
времени реализации — эталон был для одной ручной публикации, это модуль для
многократной автогенерации):
  - нет 5 line-icon SVG у спек-панели (только подпись+значение);
  - letter-spacing реализован грубо (посимвольная отрисовка с фиксированным
    шагом), не через реальный kerning движка браузера.
Из-за смешанного русского/латинского текста (модели вроде "Mercedes-Benz
GLE Coupe") используется пара шрифтовых файлов на каждое начертание —
кириллический и латинский подсабсеты Unbounded/Inter (иначе PIL не находит
кириллицу в latin-only файле и наоборот) — см. draw_text().

Не импортирует telethon и не имеет побочных эффектов при импорте — можно
тестировать отдельно от бота.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "status_card_assets")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")
LOGO_PATH = os.path.join(ASSETS_DIR, "logo-myavto.jpg")

W, H = 1080, 1920

# Палитра — 1:1 из Main.dc.html (CSS custom properties my-avto.online)
BLACK = (10, 10, 10)
GRAY = (26, 26, 26)
GRAY2 = (42, 42, 42)
GOLD = (201, 168, 76)
GOLD_LIGHT = (240, 217, 138)
MUTED = (136, 136, 136)
WHITE = (245, 244, 240)

_FONT_CACHE: dict = {}

# Только эти начертания реально скачаны (см. Task "fonts"/@fontsource) —
# любой другой запрошенный вес округляется до ближайшего из списка.
_AVAILABLE_WEIGHTS = {
    "unbounded": (500, 700, 900),
    "inter": (400, 500, 600, 700),
}

# Ни Unbounded, ни Inter (в скачанных cyrillic/latin подсабсетах) не содержат
# символы валют (₽/€/$ и т.п. — блок Currency Symbols, U+20A0-U+20CF, в
# гугл-шрифтах не входит ни в latin, ни в cyrillic subset). Отдельный
# fallback-шрифт (DejaVu Sans Bold, MIT/BSD-подобная лицензия, есть глиф)
# только для этих символов — иначе рисуется "квадратик" (проверено, T-158).
_SYMBOLS_FONT_PATH = os.path.join(FONTS_DIR, "Symbols-Bold.ttf")


def _font(family: str, weight: int, size: int, script: str) -> ImageFont.FreeTypeFont:
    """family: 'unbounded'|'inter'; script: 'cyrillic'|'latin'|'symbol'."""
    if script == "symbol":
        key = ("symbol", size)
        if key in _FONT_CACHE:
            return _FONT_CACHE[key]
        font = ImageFont.truetype(_SYMBOLS_FONT_PATH, round(size * 0.85))
        _FONT_CACHE[key] = font
        return font
    avail = _AVAILABLE_WEIGHTS[family]
    weight = min(avail, key=lambda w: abs(w - weight))
    key = (family, weight, size, script)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    fam = "Unbounded" if family == "unbounded" else "Inter"
    suffix = "Cyrillic" if script == "cyrillic" else "Latin"
    path = os.path.join(FONTS_DIR, f"{fam}-{weight}-{suffix}.ttf")
    font = ImageFont.truetype(path, size)
    _FONT_CACHE[key] = font
    return font


_CURRENCY_CHARS = set("₽€$£¥")


def _script_for_char(ch: str) -> str:
    if ch in _CURRENCY_CHARS:
        return "symbol"
    return "cyrillic" if "Ѐ" <= ch <= "ӿ" else "latin"


def measure_text(text: str, family: str, weight: int, size: int, tracking: float = 0.0) -> float:
    if not text:
        return 0.0
    total = 0.0
    for ch in text:
        f = _font(family, weight, size, _script_for_char(ch))
        total += f.getlength(ch)
    return total + tracking * max(0, len(text) - 1)


def fit_font_size(text: str, family: str, weight: int, max_width: float,
                   start_size: int, min_size: int, tracking: float = 0.0) -> int:
    """Подбирает наибольший размер шрифта (кратно 2px) в [min_size,start_size],
    при котором measure_text(text, ...) не превышает max_width — грубый
    aналог CSS'ового "сожмись, если не влезаешь", без переноса строк."""
    size = start_size
    while size > min_size and measure_text(text, family, weight, size, tracking) > max_width:
        size -= 2
    return max(size, min_size)


def _wrap_to_width(text: str, family: str, weight: int, size: int, max_width: float) -> list:
    words = text.split()
    if not words:
        return [text] if text else []
    lines, cur = [], words[0]
    for w in words[1:]:
        trial = cur + " " + w
        if measure_text(trial, family, weight, size) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def fit_wrapped_lines(text: str, family: str, weight: int, max_width: float,
                       start_size: int, min_size: int, max_lines: int = 2) -> tuple:
    """Названия моделей у реальных постов сильно разной длины ("S450d" vs
    "GLE Coupe 4MATIC Plug-in Hybrid", T-158) — одного уменьшения размера
    шрифта недостаточно, длинные не влезают в одну строку даже на min_size.
    Подбирает размер (шаг 2px, start_size..min_size) и перенос на до
    max_lines строк так, чтобы каждая строка влезала по ширине; на min_size
    лишние строки после max_lines обрезаются (крайний случай, в реальных
    названиях моделей практически не встречается)."""
    size = start_size
    while size > min_size:
        lines = _wrap_to_width(text, family, weight, size, max_width)
        if len(lines) <= max_lines:
            return lines, size
        size -= 2
    lines = _wrap_to_width(text, family, weight, min_size, max_width)
    return lines[:max_lines], min_size


def draw_text(draw: ImageDraw.ImageDraw, xy, text: str, family: str, weight: int, size: int,
              fill, anchor_h: str = "left", tracking: float = 0.0) -> float:
    """Отрисовывает text посимвольно, переключая кириллический/латинский файл
    шрифта по unicode-блоку каждого символа (см. докстринг модуля), с
    опциональным фиксированным tracking (px) между символами. anchor_h:
    left/center/right — по x; y в xy — верх строки (top), как textbbox с
    anchor='la' для латиницы. Возвращает суммарную ширину отрисованной строки.
    """
    x0, y = xy
    if not text:
        return 0.0

    def glyph_w(ch, f):
        return f.getlength(ch)

    runs = []  # (char, font)
    for ch in text:
        script = _script_for_char(ch)
        f = _font(family, weight, size, script)
        runs.append((ch, f))

    total_w = sum(glyph_w(ch, f) for ch, f in runs) + tracking * max(0, len(runs) - 1)

    if anchor_h == "center":
        x = x0 - total_w / 2
    elif anchor_h == "right":
        x = x0 - total_w
    else:
        x = x0

    for ch, f in runs:
        draw.text((x, y), ch, font=f, fill=fill)
        x += glyph_w(ch, f) + tracking

    return total_w


def _vertical_gradient_overlay(width: int, height: int, stops) -> Image.Image:
    """stops: list of (pos_0_1, (r,g,b), alpha_0_1) — кусочно-линейная
    интерполяция альфы (и цвета) сверху вниз, как CSS linear-gradient(180deg,...)."""
    grad = Image.new("RGBA", (1, height))
    px = grad.load()
    for y in range(height):
        t = y / max(1, height - 1)
        # найти отрезок [stops[i], stops[i+1]] куда попадает t
        for i in range(len(stops) - 1):
            p0, c0, a0 = stops[i]
            p1, c1, a1 = stops[i + 1]
            if p0 <= t <= p1 or i == len(stops) - 2:
                span = (p1 - p0) or 1e-6
                k = min(1.0, max(0.0, (t - p0) / span))
                r = round(c0[0] + (c1[0] - c0[0]) * k)
                g = round(c0[1] + (c1[1] - c0[1]) * k)
                b = round(c0[2] + (c1[2] - c0[2]) * k)
                a = round((a0 + (a1 - a0) * k) * 255)
                px[0, y] = (r, g, b, a)
                break
    return grad.resize((width, height))


def _cover_crop(img: Image.Image, target_w: int, target_h: int, focus_y: float = 0.20) -> Image.Image:
    """object-fit: cover + object-position: center {focus_y*100}% —
    focus_y=0 верх кадра наверху, 0.5 центр, 1 низ кадра снизу. Обрезает
    (используется только для декоративного размытого фона — см.
    _fit_no_crop, где сама машина этим способом уже НЕ кадрируется,
    T-158 08.09: "фото обрезается, нужно исправить... без обрезани")."""
    img = ImageOps.exif_transpose(img)
    src_w, src_h = img.size
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h
    if src_ratio > target_ratio:
        new_h = src_h
        new_w = round(src_h * target_ratio)
    else:
        new_w = src_w
        new_h = round(src_w / target_ratio)
    max_x = src_w - new_w
    max_y = src_h - new_h
    x0 = max_x // 2
    y0 = round(max_y * focus_y)
    y0 = max(0, min(max_y, y0))
    cropped = img.crop((x0, y0, x0 + new_w, y0 + new_h))
    return cropped.resize((target_w, target_h), Image.LANCZOS)


def _fit_no_crop(img: Image.Image, target_w: int, target_h: int, blur_radius: int = 40, darken: float = 0.45) -> Image.Image:
    """T-158 (08.09.2026, пользователь — "фото обрезается, нужно
    исправить... без обрезани"): реальные фото из постов дилеров бывают
    любых пропорций и с любой композицией (машина не всегда по центру) —
    жёсткий object-fit:cover (см. _cover_crop, старое поведение) при любом
    выборе focus_y на части фото неизбежно отрезал куски машины (колесо,
    номер, зеркало). Теперь фото показывается ЦЕЛИКОМ без обрезки
    (object-fit: contain) поверх залитого тем же фото, растянутого на всю
    зону способом cover + размытого + затемнённого фона — чтобы у зоны не
    было чёрных полос по краям, а результат всё равно выглядел цельно."""
    img = ImageOps.exif_transpose(img).convert("RGB")

    # Фон: cover на всю зону, размытие + затемнение — декоративный, ему
    # обрезка не вредит (сама машина на нём не обязана быть видна целиком).
    bg = _cover_crop(img, target_w, target_h, focus_y=0.5)
    bg = bg.filter(ImageFilter.GaussianBlur(blur_radius))
    dark = Image.new("RGB", (target_w, target_h), (0, 0, 0))
    bg = Image.blend(bg, dark, darken)

    # Передний план: contain — вписываем целиком, ничего не обрезаем.
    src_w, src_h = img.size
    scale = min(target_w / src_w, target_h / src_h)
    fg_w, fg_h = max(1, round(src_w * scale)), max(1, round(src_h * scale))
    fg = img.resize((fg_w, fg_h), Image.LANCZOS)

    bg.paste(fg, ((target_w - fg_w) // 2, (target_h - fg_h) // 2))
    return bg


def _circle_mask(size: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse((0, 0, size, size), fill=255)
    return mask


@dataclass
class Spec:
    label: str
    value: str


@dataclass
class CarCard:
    brand: str
    model: str
    year: str = ""
    subtitle: str = ""
    price: str = ""
    specs: list = field(default_factory=list)  # list[Spec], up to 5
    trust_line1: str = "11 ЛЕТ"
    trust_line2: str = "НА РЫНКЕ"
    footer_line: str = "MY AVTO"
    footer_handle: str = "my-avto.online · импорт авто под ключ"


def render_status_card(car: CarCard, photo_path: str, out_path: str) -> str:
    canvas = Image.new("RGB", (W, H), BLACK)
    draw = ImageDraw.Draw(canvas)

    # --- Photo zone: 0..1220 ---
    PHOTO_H = 1220
    photo = Image.open(photo_path).convert("RGB")
    photo = _fit_no_crop(photo, W, PHOTO_H)
    canvas.paste(photo, (0, 0))

    # scrim gradient (top-heavy, per Main.dc.html linear-gradient stops)
    scrim = _vertical_gradient_overlay(W, PHOTO_H, [
        (0.00, (6, 5, 3), 0.90),
        (0.20, (6, 5, 3), 0.58),
        (0.42, (6, 5, 3), 0.05),
        (0.70, (6, 5, 3), 0.05),
        (0.88, BLACK, 0.55),
        (1.00, BLACK, 1.00),
    ])
    canvas.paste(Image.alpha_composite(photo.convert("RGBA"), scrim).convert("RGB"), (0, 0))

    # decorative gold ring accents
    ring_layer = Image.new("RGBA", (W, PHOTO_H), (0, 0, 0, 0))
    ring_draw = ImageDraw.Draw(ring_layer)
    ring_draw.ellipse((150 - 430, 430 - 330, 150 + 430, 430 + 330), outline=GOLD + (round(0.4 * 255),), width=5)
    ring_draw.ellipse((330 - 270, 360 - 205, 330 + 270, 360 + 205), outline=GOLD_LIGHT + (round(0.28 * 255),), width=4)
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA").crop((0, 0, W, PHOTO_H)), ring_layer).convert("RGB"), (0, 0))
    draw = ImageDraw.Draw(canvas)

    # header row: badge + wordmark (left), trust lines (right)
    try:
        logo = Image.open(LOGO_PATH).convert("RGBA")
        logo = logo.resize((76, 76), Image.LANCZOS)
        mask = _circle_mask(76)
        canvas.paste(logo, (56, 56), mask)
    except FileNotFoundError:
        pass

    wm_x = 56 + 76 + 16
    wm_y = 56 + 76 / 2 - 15
    w1 = draw_text(draw, (wm_x, wm_y), "MY", "unbounded", 700, 30, WHITE)
    draw_text(draw, (wm_x + w1 + 10, wm_y), "Avto", "unbounded", 700, 30, GOLD)

    tr_x = 1080 - 56
    draw_text(draw, (tr_x, 56), car.trust_line1, "inter", 600, 19, GOLD_LIGHT, anchor_h="right", tracking=2)
    draw_text(draw, (tr_x, 56 + 27), car.trust_line2, "inter", 600, 19, GOLD_LIGHT, anchor_h="right", tracking=2)
    draw.rectangle((tr_x - 64, 56 + 27 + 24 + 10, tr_x, 56 + 27 + 24 + 13), fill=GOLD)

    # headline block. Реальные названия моделей сильно разной длины ("S450d"
    # vs "GLE Coupe 4MATIC Plug-in Hybrid") — при фиксированном размере
    # длинные вылезали бы за правый край (T-158), поэтому размер бренда/
    # модели подбирается под доступную ширину (aналог CSS shrink-to-fit),
    # переноса строк нет.
    hx = 56
    hy = 230
    max_w = W - 2 * hx
    brand_size = fit_font_size(car.brand.upper(), "unbounded", 700, max_w, 58, 30)
    draw_text(draw, (hx, hy), car.brand.upper(), "unbounded", 700, brand_size, WHITE)
    hy += brand_size * 1.14

    model_lines, model_size = fit_wrapped_lines(car.model.upper(), "unbounded", 900, max_w, 96, 44, max_lines=2)
    for line in model_lines:
        draw_text(draw, (hx, hy), line, "unbounded", 900, model_size, WHITE)
        hy += model_size * 1.05
    hy += 12
    if car.year:
        draw_text(draw, (hx, hy), car.year, "unbounded", 500, 66, GOLD)
        hy += 76
    if car.subtitle:
        draw_text(draw, (hx, hy + 10), car.subtitle.upper(), "inter", 600, 24, (228, 217, 189), tracking=1)

    # --- Spec dashboard: 1220..1460 ---
    SPEC_TOP = PHOTO_H
    SPEC_H = 240
    draw.rectangle((0, SPEC_TOP, W, SPEC_TOP + SPEC_H), fill=GRAY)

    specs = (car.specs or [])[:5]
    n = len(specs)
    if n:
        col_w = W / n
        for i, spec in enumerate(specs):
            cx = col_w * i + col_w / 2
            if i > 0:
                draw.line((col_w * i, SPEC_TOP + 40, col_w * i, SPEC_TOP + SPEC_H - 40), fill=GRAY2, width=1)
            draw_text(draw, (cx, SPEC_TOP + 84), spec.value, "unbounded", 700, 24, WHITE, anchor_h="center")
            draw_text(draw, (cx, SPEC_TOP + 130), spec.label.upper(), "inter", 600, 14, MUTED, anchor_h="center", tracking=1)

    draw.line((0, SPEC_TOP, W, SPEC_TOP), fill=GRAY2, width=1)
    draw.line((0, SPEC_TOP + SPEC_H, W, SPEC_TOP + SPEC_H), fill=GRAY2, width=1)

    # --- Price: 1460..1650 ---
    PRICE_TOP = SPEC_TOP + SPEC_H
    price_cy = PRICE_TOP + 95
    draw_text(draw, (W / 2, price_cy - 40), car.price or "Цена по запросу", "unbounded", 800, 80, WHITE, anchor_h="center")
    draw.rectangle((W / 2 - 90, price_cy + 62, W / 2 + 90, price_cy + 66), fill=GOLD)

    # --- Footer: rest ---
    footer_cy = H - 100
    draw_text(draw, (W / 2, footer_cy - 30), car.footer_line, "unbounded", 600, 22, GOLD, anchor_h="center", tracking=3)
    draw_text(draw, (W / 2, footer_cy + 6), car.footer_handle, "inter", 500, 18, (102, 102, 102), anchor_h="center", tracking=1)

    canvas.save(out_path, "PNG")
    return out_path


_PLACEHOLDER_SVG_NOTE = None  # нет — иконки сознательно опущены, см. докстрин модуля.


if __name__ == "__main__":
    # локальный самотест: рендер эталонного примера (GLE Coupe, t.me/MY_Avto5/4012)
    car = CarCard(
        brand="Mercedes-Benz",
        model="GLE Coupe",
        year="2026",
        subtitle="4MATIC Plug-in Hybrid · AMG Line Advanced Plus",
        price="12 500 000 ₽",
        specs=[
            Spec("Первая регистрация", "04.2026"),
            Spec("Пробег", "8 000 км"),
            Spec("Мощность", "197 л.с."),
            Spec("Тип", "Гибрид"),
            Spec("Быстрая зарядка", "29 мин"),
        ],
    )
    photo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets_brand", "mercedes_gle_photo.jpg")
    out = "/tmp/status_card_test_gle.png"
    render_status_card(car, photo, out)
    print("saved", out)
