"""T-86 (27.08.2026, запрошено пользователем — "давай в автомат ставь видео
монтаж не в ручной режим"): автоматическая сборка короткого вертикального
ролика (9:16) из сырого видео-облёта машины — БЕЗ ручного отсмотра кадров
человеком/Claude, в отличие от процесса, описанного в монтажном листе
(https://claude.ai/code/artifact/28e39b53-cb5e-453c-b570-d7c797bf1cb9),
который явно ручной ("автоматический подбор самых удачных моментов я не
делаю — отбираю кадры вручную по превью").

Статус: прототип, ПРОВЕРЕН только на одном реальном видео (Nissan Altima,
IMG_0933, 37с) — сначала вручную (см. сессию 26-27.08.2026), затем этим
модулем полностью автоматически. НЕ подключён к живому пайплайну
userbot_parser.py — интеграция описана в TASKS.md T-86.

Пайплайн (build_short()):
  1. Найти "склейки" в исходнике (scene cuts) — считаем, что дилер уже
     смонтировал сырое видео в InShot из отдельных кадров-планов (это видно
     по резким склейкам между ракурсами на реальном тестовом видео) —
     значит не нужно самим выдумывать, где начинается/кончается один план,
     достаточно найти эти границы.
  2. Внутри каждого плана найти самое резкое (наименее смазанное) окно
     нужной длины — по дисперсии Лапласиана (стандартная мера резкости),
     чтобы не попасть на смазанный движением камеры момент (тот самый
     класс проблемы, что и у OCR-детекта бейджа, см. watermark_video.py).
  3. Для каждого кандидата — проверить, есть ли в нём бейдж winner_auto_club
     (переиспользуем detect_boxes() из watermark_video.py, тот же
     OCR-детект+трекинг, что и в ручном процессе). Три исхода:
       - НЕТ бейджа ни в одном кадре -> SAFE, используем как есть.
       - Бейдж уверенно найден и закрашен в почти всех кадрах (>=90%) ->
         COVERED, используем, закрасив (render()).
       - Бейдж есть, но закраска ненадёжна (частично) -> RISKY, ПРОПУСКАЕМ
         этот план целиком и берём следующего кандидата. Тот же принцип
         "лучше пропустить, чем испортить/показать номер", что и везде в
         T-85 — теперь применён не к отдельному кадру, а к выбору целого
         плана для монтажа.
  4. Собрать хук (первый безопасный план) + до 2 планов машины + деталь +
     призыв (последний безопасный план, по возможности COVERED — с машиной
     в кадре) — бюджет длительности гибкий (было решено пользователем: "уже
     лучше" на ролике короче заявленных 15с, лучше короче и чисто, чем по
     таймингу, но с риском).
  5. Текст хука — из уже распарсенных полей поста (title/mileage,
     parse_winner_auto_club() в userbot_parser.py) — НЕ выдумываем цифры.
     Текст призыва — из банка монтажного листа, фиксированная строка.
  6. Каждый план: закраска (если COVERED) -> вертикальная 9:16-раскладка
     (размытый фон на весь кадр + чёткое видео по центру, чтобы не
     обрезать машину при смене пропорций) -> склейка всех планов.
  7. Один сплошной слой звука на весь ролик — из начала исходника, по
     длительности итогового ролика (решение пользователя: "звук нужно
     скачать и наложить на тайминг сплошной", НЕ по кускам).

Использование как библиотека:
    from auto_montage import build_short
    build_short(in_path, parsed, out_path, log=print)
parsed — тот же dict, что возвращает SOURCE_PARSERS[source_username](text)
(поля title/mileage используются; остальные не обязательны).
CPU-bound, минуты — в асинхронном коде вызывать через asyncio.to_thread,
как и watermark_video.process_video (см. T-85 про ту же проблему).
"""
import subprocess
import sys
import time

import cv2
import numpy as np

import watermark_video as wv

# ---- Тайминг-бюджет (ориентир "Короткий" шаблон монтажного листа, 15с) ----
HOOK_DUR = 3.0
CAR_SHOT_DUR = 3.0
DETAIL_DUR = 2.0
CTA_DUR = 3.0
CTA_HOLD_EXTRA = 2.0  # заморозка последнего кадра призыва — как в ручной версии,
                      # чтобы текст успели прочитать (короткие резервные окна
                      # с бейджем часто <1с, см. T-85 про смазанные кадры)

MIN_SHOT_DUR = 1.0    # план короче — не рассматриваем (слишком мало на кадр)
COVERAGE_SAFE_MAX = 0.0    # 0 кадров с бейджем -> считаем план безопасным как есть
COVERAGE_COVERED_MIN = 0.9  # >=90% кадров закрашено -> считаем план безопасным после закраски

CTA_TEXT = "Пишите в бота — цена и детали"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

_VFILT_BASE = (
    "split=2[bg][fg];"
    "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=30,eq=brightness=-0.08[bgblur];"
    "[fg]scale=1080:-2[fgs];"
    "[bgblur][fgs]overlay=(W-w)/2:(H-h)/2"
)


def _ffprobe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


PEAK_SAMPLE_STEP = 0.5   # с, шаг сканирования резкости по всему видео
PEAK_MIN_GAP = 3.0       # с, минимальное расстояние между выбранными пиками
PEAK_MAX_CANDIDATES = 8  # сколько пиков-кандидатов рассматривать максимум


def _sharpness_track(path):
    """Резкость (дисперсия Лапласиана) через равные промежутки по ВСЕМУ
    видео. 27.08.2026: первая версия искала "склейки" (резкие скачки между
    планами) и резала видео по ним на явные планы — оказалось, что реальное
    тестовое видео (IMG_0933) смонтировано НЕ по жёстким склейкам, а снято
    непрерывным движением камеры (плавная панорама вокруг машины) — резких
    скачков между планами почти нет, метод находил только 2-3 ложных
    "плана" на весь ролик. Вместо этого ищем локальные ПИКИ резкости прямо
    по всей длине — именно те редкие моменты, когда камера ненадолго
    останавливается/статична (в остальное время смаз движения размывает
    кадр, там и OCR бейджа не читает — см. watermark_video.py про то же)."""
    cap = cv2.VideoCapture(path)
    duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / (cap.get(cv2.CAP_PROP_FPS) or 30.0)
    track = []
    t = 0.0
    while t < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ret, frame = cap.read()
        if ret:
            track.append((t, _sharpness(frame)))
        t += PEAK_SAMPLE_STEP
    cap.release()
    return track, duration


def _pick_peaks(track, want_dur, max_candidates=PEAK_MAX_CANDIDATES):
    """Жадно выбирает самые резкие моменты, не ближе PEAK_MIN_GAP друг к
    другу — каждый становится центром окна кандидата длиной want_dur."""
    ranked = sorted(track, key=lambda x: -x[1])
    chosen = []
    for t, score in ranked:
        if all(abs(t - c) >= PEAK_MIN_GAP for c in chosen):
            chosen.append(t)
        if len(chosen) >= max_candidates:
            break
    return sorted(chosen)


def _shot_boundaries(path):
    """Возвращает окна-кандидаты (start, dur) вокруг локальных пиков
    резкости — замена старому поиску "планов" по склейкам (см. коммент в
    _sharpness_track). Каждое окно уже clamp'нуто в границы видео и не
    залезает на соседний уже выбранный пик."""
    want_dur = max(HOOK_DUR, CAR_SHOT_DUR, CTA_DUR)
    track, duration = _sharpness_track(path)
    peaks = _pick_peaks(track, want_dur)
    windows = []
    for i, tp in enumerate(peaks):
        lo = peaks[i - 1] + PEAK_MIN_GAP / 2 if i > 0 else 0.0
        hi = peaks[i + 1] - PEAK_MIN_GAP / 2 if i < len(peaks) - 1 else duration
        start = max(lo, tp - want_dur / 2)
        end = min(hi, tp + want_dur / 2, duration)
        if end - start >= MIN_SHOT_DUR:
            windows.append((start, end))
    return windows


def _sharpness(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def _best_window(path, t0, t1, want_dur, sample_every=0.2):
    """Внутри плана [t0,t1] ищет самое резкое окно длиной want_dur (по
    средней резкости сэмплированных кадров) — избегаем смазанных движением
    участков, та же проблема, что валила OCR в T-85."""
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    t1 = min(t1, t0 + max(want_dur, t1 - t0))
    samples = []
    t = t0
    while t <= t1:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ret, frame = cap.read()
        if ret:
            samples.append((t, _sharpness(frame)))
        t += sample_every
    cap.release()
    if not samples:
        return t0, min(want_dur, t1 - t0)
    avail = t1 - t0
    win = min(want_dur, avail)
    best_start, best_score = t0, -1.0
    for start, _ in samples:
        if start + win > t1 + 1e-6:
            continue
        scores = [sc for (tt, sc) in samples if start <= tt < start + win]
        if not scores:
            continue
        avg = sum(scores) / len(scores)
        if avg > best_score:
            best_score, best_start = avg, start
    return best_start, win


def _extract(src, t0, dur, out_path):
    subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", src,
         "-c:v", "libx264", "-crf", "18", "-an", out_path],
        check=True, capture_output=True,
    )


def _classify_badge(seg_path, log):
    results = wv.detect_boxes(seg_path, log=lambda m: None)
    total = len(results)
    if total == 0:
        return "safe", results
    n_boxed = sum(1 for _, b, _ in results if b is not None)
    ratio = n_boxed / total
    if ratio <= COVERAGE_SAFE_MAX:
        return "safe", results
    if ratio >= COVERAGE_COVERED_MIN:
        return "covered", results
    log(f"  риск: план {seg_path} — бейдж в {ratio:.0%} кадров, ненадёжно, пропускаю план")
    return "risky", results


def _paint(seg_path, results, out_path):
    wv.render(seg_path, results, out_path, log=lambda m: None)


def _vertical(in_path, out_path, text=None, text_top=True, hold_extra=0.0):
    filt = _VFILT_BASE
    if text:
        y = 260 if text_top else 1550
        safe = text.replace("'", r"\'").replace(":", r"\:")
        filt += f",drawtext=fontfile={FONT}:text='{safe}':fontsize=58:fontcolor=white:borderw=6:bordercolor=black:x=(w-text_w)/2:y={y}"
    if hold_extra > 0:
        filt += f",tpad=stop_mode=clone:stop_duration={hold_extra:.2f}"
    subprocess.run(
        ["ffmpeg", "-y", "-i", in_path, "-vf", filt, "-an", out_path],
        check=True, capture_output=True,
    )


def _hook_text(parsed):
    if not parsed:
        return None
    title = (parsed.get("title") or "").strip()
    mileage = (parsed.get("mileage") or "").strip()
    if title and mileage:
        return f"{title}, пробег {mileage}"
    return title or None


def build_short(in_path, parsed, out_path, log=lambda msg: None):
    t0_all = time.time()
    shots = _shot_boundaries(in_path)
    log(f"найдено планов: {len(shots)} -> {shots}")

    candidates = []
    for (a, b) in shots:
        want = max(HOOK_DUR, CAR_SHOT_DUR, CTA_DUR)  # берём с запасом, обрежем при использовании
        start, win = _best_window(in_path, a, b, min(want, b - a))
        seg_tmp = f"{out_path}.cand_{len(candidates)}.mp4"
        _extract(in_path, start, win, seg_tmp)
        status, results = _classify_badge(seg_tmp, log)
        candidates.append({"t0": start, "dur": win, "path": seg_tmp, "status": status, "results": results})
        log(f"план {a:.1f}-{b:.1f}с -> окно {start:.2f}+{win:.2f}с, статус={status}")

    usable = [c for c in candidates if c["status"] in ("safe", "covered")]
    if not usable:
        raise RuntimeError("ни одного безопасного плана не найдено — авто-монтаж невозможен на этом видео")

    hook_c = usable[0]
    rest = usable[1:]
    covered_rest = [c for c in rest if c["status"] == "covered"] or rest
    cta_c = covered_rest[-1] if covered_rest else usable[-1]
    middle = [c for c in rest if c is not cta_c][:3]  # до 3 планов: 2 машины + деталь

    log(f"выбрано: hook={hook_c['t0']:.1f}с, middle={[c['t0'] for c in middle]}, cta={cta_c['t0']:.1f}с")

    segs_final = []

    def _prep(c, dur_cap, text=None, text_top=True, hold=0.0):
        painted = c["path"] + ".painted.mp4"
        if c["status"] == "covered":
            _paint(c["path"], c["results"], painted)
        else:
            painted = c["path"]
        trimmed = painted + ".trim.mp4"
        actual_dur = min(dur_cap, c["dur"])
        subprocess.run(["ffmpeg", "-y", "-i", painted, "-t", f"{actual_dur:.3f}", "-an", trimmed],
                        check=True, capture_output=True)
        vert = trimmed + ".vert.mp4"
        _vertical(trimmed, vert, text=text, text_top=text_top, hold_extra=hold)
        return vert

    hook_text = _hook_text(parsed)
    segs_final.append(_prep(hook_c, HOOK_DUR, text=hook_text, text_top=True))
    for c in middle:
        dur = DETAIL_DUR if c is middle[-1] and len(middle) >= 2 else CAR_SHOT_DUR
        segs_final.append(_prep(c, dur))
    segs_final.append(_prep(cta_c, CTA_DUR, text=CTA_TEXT, text_top=False, hold=CTA_HOLD_EXTRA))

    list_path = out_path + ".concat.txt"
    with open(list_path, "w") as f:
        for s in segs_final:
            f.write(f"file '{s}'\n")
    silent_out = out_path + ".silent.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
         "-c:v", "libx264", "-crf", "20", "-r", "30", silent_out],
        check=True, capture_output=True,
    )

    total_dur = _ffprobe_duration(silent_out)
    audio_bed = out_path + ".audio.m4a"
    subprocess.run(
        ["ffmpeg", "-y", "-i", in_path, "-t", f"{total_dur:.3f}", "-vn", "-c:a", "aac", audio_bed],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", silent_out, "-i", audio_bed, "-map", "0:v", "-map", "1:a",
         "-c:v", "copy", "-c:a", "aac", "-shortest", out_path],
        check=True, capture_output=True,
    )

    log(f"build_short: готово за {time.time() - t0_all:.1f}с, длительность ролика {total_dur:.1f}с -> {out_path}")
    return out_path


if __name__ == "__main__":
    in_path, out_path = sys.argv[1], sys.argv[2]
    title = sys.argv[3] if len(sys.argv) > 3 else None
    mileage = sys.argv[4] if len(sys.argv) > 4 else None
    build_short(in_path, {"title": title, "mileage": mileage}, out_path, log=print)
    print(f"done -> {out_path}")
