"""T-85 (26.08.2026): удаление бейджа WINNER AUTO CLUB с ВИДЕО.

Статус: рабочий, проверенный прототип — НЕ подключён к живому пайплайну
userbot_parser.py (VIDEO_DRY_RUN/VIDEO_DRY_RUN_SOURCES). Видео с этим
бейджем по-прежнему уходит в тестовую группу как есть, необработанным,
пока это не подключат явно (см. TASKS.md T-85, раздел "видео").

v1 (25.08.2026, /tmp/video_watermark_prototype.py, сессия — не в репозитории)
был построен на том же raw template matching, что и v1 фото-детектора —
и страдал той же болезнью (см. T-85 про фото): образцы, вырезанные из
других фото/видео, ненадёжно совпадают на конкретном кадре другого видео.

v2 (этот файл, 26.08.2026) — гибрид:
  1. Редкие OCR-якоря (та же логика, что для фото — см.
     userbot_parser._find_badge_box) на каждый ANCHOR_INTERVAL-й кадр.
     OCR медленный (секунды на кадр) — потому и редкий.
  2. Между якорями — быстрый локальный cv2.matchTemplate, но НЕ против
     заранее вырезанного образца, а против РЕАЛЬНОГО кропа, который OCR
     только что нашёл на этом же видео несколько кадров назад (соседние
     кадры одного видео визуально почти идентичны — то же освещение/
     ракурс/сжатие, в отличие от чужого шаблона с другого кадра/фото).
     Поиск ограничен небольшим окном вокруг последней известной позиции —
     дёшево (~15-20мс/кадр).
  3. Если и OCR-якорь, и локальный трекинг ничего не находят — кадр НЕ
     трогаем (тот же принцип "лучше пропустить, чем испортить", что и в
     фото-детекторе).

Важное наблюдение по проверке на реальном видео (IMG_0826, Lexus LX570,
40с, съёмка с рук, не статичный поворотный стенд): OCR уверенно находит
бейдж только в кадрах, где он не смазан движением камеры — на быстрой
динамичной съёмке таких кадров может быть немного (в тестовом ролике —
2 коротких статичных момента из ~1200 кадров). Это ОЖИДАЕМОЕ поведение
метода, завязанного на чтение текста, а не признак поломки: чем спокойнее
снято видео (меньше motion blur), тем больше кадров будет обработано.

Использование:
    python3 watermark_video.py входное.mp4 выходное.mp4

Или как библиотека — process_video(in_path, out_path) в асинхронном коде
следует вызывать через asyncio.to_thread (вся обработка — несколько
десятков секунд до нескольких минут в зависимости от длины видео и
количества OCR-якорей, чисто CPU-bound, блокировать event loop нельзя —
см. T-85 про тот же вопрос для фото в userbot_parser._prepare_media_list).
"""
import subprocess
import sys
import time

import cv2

import userbot_parser as up

ANCHOR_INTERVAL = 10       # кадров между OCR-попытками (якорями) — подобрано на
                           # реальном тестовом видео: динамичная съёмка с рук
                           # часто даёт смазанные кадры, часть якорей "мажет"
                           # из-за блюра; более частые якоря короче разрывы
                           # трекинга между двумя удачными
TRACK_SEARCH_PAD = 70      # px, радиус локального поиска вокруг предыдущей позиции
TRACK_SCALES = (0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15)
TRACK_SCORE_THRESH = 0.55  # T-98 (28.08.2026, было 0.65): реальный тест
                           # (IMG_0901) показал, что на плавном повороте
                           # (поворотный стенд) собственный скор трекинга
                           # закономерно и плавно снижается кадр за кадром
                           # (0.92 -> 0.85 -> 0.77 -> 0.71 -> 0.64 -> ...) по
                           # мере того, как ракурс/перспектива меняются —
                           # 0.65 обрывал ЖИВОЕ, продолжающееся слежение
                           # слишком рано. 0.55 — всё ещё заметно строже,
                           # чем 0.55 у generic template matching фото-
                           # детектора v1 (там сравнение против чужого кадра,
                           # тут — против недавнего кадра этого же видео).
TRACK_MAX_MISSES = 6       # столько кадров подряд трекинг может промахнуться,
                           # прежде чем считаем бейдж потерянным (ждём следующий
                           # плановый OCR-якорь, не раньше — см. FULL_PLATE_AR
                           # комментарий про стоимость OCR ниже)
FULL_PLATE_AR = 7.0        # запас по ширине области закрытия — OCR обычно ловит
                           # не все 3 слова таблички целиком, только часть.
                           # 26.08.2026: было 5.5 — реальный тест (IMG_0933)
                           # показал кадр, где смазанность картинки не даёт
                           # ни OCR, ни локальному трекингу поймать больше,
                           # чем одно слово ("WINNER" без "AUTO CLUB") — а
                           # т.к. неизвестно, какое из трёх слов поймали
                           # (крайнее левое/среднее/крайнее правое), запас
                           # должен быть с большим избытком на обе стороны,
                           # не только по факту пойманного слова.


def _badge_video_regions(img):
    """Область поиска для видео шире, чем для фото (userbot_parser._find_badge_box
    по умолчанию смотрит только в нижние углы кадра): на реальном тестовом видео
    бейдж висит по ЦЕНТРУ низа кадра (на номере), не только по углам, как на
    фото из T-85 — берём весь низ кадра одной полосой.

    26.08.2026: было 0.55-0.92 — на реальном видео IMG_0933 (задний ракурс,
    камера ближе к машине) бейдж оказался ВЫШЕ границы 0.55h, верх букв
    обрезался полосой и OCR переставал распознавать текст целиком (см. T-85,
    тот же класс бага, что чинили для фото — _badge_corner_regions). Подняли
    верхнюю границу до 0.45h с тем же запасом, что и у фото-детектора."""
    h, w = img.shape[:2]
    return ((0, int(h * 0.45), w, int(h * 0.92)),)


# T-98 (28.08.2026): реальный тест (IMG_0901, студийная съёмка на
# поворотном стенде) показал, что штатные _BADGE_OCR_SCALES=(3,2) и psm=11
# (заточены под УЗКИЕ угловые кропы фото) на ШИРОКОМ видео-регионе (вся
# ширина кадра, см. _badge_video_regions) при апскейле дают 2560-3840px и
# Tesseract разваливается в шум — крупный чёткий анфас-бейдж (первый кадр
# того видео) не находился ВООБЩЕ. psm=6 (один блок текста, не россыпь
# слов) + меньшие scale надёжно его ловят — проверено, находит и WINNER, и
# CLUB с точным/почти точным совпадением там, где старые настройки не
# давали вообще ни одного совпадения.
_VIDEO_OCR_SCALES = (1.5, 1.8)
_VIDEO_OCR_PSM = 6


def ocr_anchor(frame_bgr):
    """OCR-детект (переиспользует userbot_parser._find_badge_box) — медленный
    (секунды), вызываем только на редких кадрах-якорях, не на каждом кадре."""
    return up._find_badge_box(
        frame_bgr,
        regions=_badge_video_regions(frame_bgr),
        scales=_VIDEO_OCR_SCALES,
        psm=_VIDEO_OCR_PSM,
    )


def make_live_template(frame_gray, box):
    x, y, w, h = box
    return frame_gray[y:y + h, x:x + w].copy()


def track_local(frame_gray, template_gray, last_box):
    """Ищет template_gray (реальный кроп бейджа, найденный OCR-якорем несколько
    кадров назад в ЭТОМ ЖЕ видео) в небольшом окне вокруг last_box — быстро
    (маленькая область поиска, немного масштабов) и надёжно (матчим против
    себя же в соседнем кадре, а не против чужого статичного образца — именно
    это подвело v1, см. докстринг модуля)."""
    th, tw = template_gray.shape[:2]
    if th < 4 or tw < 4:
        return None
    lx, ly, lw, lh = last_box
    cx, cy = lx + lw / 2, ly + lh / 2
    H, W = frame_gray.shape[:2]
    sx0 = max(0, int(cx - lw / 2 - TRACK_SEARCH_PAD))
    sy0 = max(0, int(cy - lh / 2 - TRACK_SEARCH_PAD))
    sx1 = min(W, int(cx + lw / 2 + TRACK_SEARCH_PAD + tw))
    sy1 = min(H, int(cy + lh / 2 + TRACK_SEARCH_PAD + lh))
    search = frame_gray[sy0:sy1, sx0:sx1]
    if search.shape[0] < th or search.shape[1] < tw:
        return None
    best = None
    for scale in TRACK_SCALES:
        w = max(4, int(tw * scale))
        h = max(4, int(th * scale))
        if w > search.shape[1] or h > search.shape[0]:
            continue
        resized = cv2.resize(template_gray, (w, h))
        result = cv2.matchTemplate(search, resized, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if best is None or max_val > best[4]:
            best = (sx0 + max_loc[0], sy0 + max_loc[1], w, h, max_val)
    if best is None or best[4] < TRACK_SCORE_THRESH:
        return None
    return best  # (x, y, w, h, score)


def detect_boxes(path, log=lambda msg: None):
    """Проходит по видео и для каждого кадра определяет box бейджа (или None).
    Возвращает список (frame_idx, box_or_None, source), source: 'ocr' | 'track' | None."""
    cap = cv2.VideoCapture(path)
    idx = 0
    results = []
    live_template = None
    last_box = None
    misses = 0
    t0 = time.time()
    ocr_calls = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        box = None
        source = None

        # OCR-якоря — ТОЛЬКО по расписанию (idx % ANCHOR_INTERVAL), никогда
        # чаще. v1 этого модуля дополнительно дёргал OCR на каждом кадре, где
        # трекинг промахивался N раз подряд — на реальном видео это давало
        # сотни OCR-вызовов подряд на участках, где бейджа в кадре просто нет
        # (машина повёрнута другим боком): 2-3с x сотни кадров = много минут
        # на 40-секундном ролике. Теперь между якорями работает только
        # быстрый локальный трекинг; если он гаснет — ждём следующего
        # планового якоря, не раньше.
        if idx % ANCHOR_INTERVAL == 0:
            ocr_box = ocr_anchor(frame)
            ocr_calls += 1
            if ocr_box is not None:
                # 26.08.2026: реальный тест (IMG_0933) показал регрессию —
                # плановый OCR-якорь иногда ловит только ОДНО слово бейджа
                # ("WINNER" без "AUTO CLUB"), а не весь текст целиком (напр.
                # лёгкий блюр/ракурс именно на этом кадре). Раньше такой
                # узкий box сразу становился новым шаблоном для трекинга —
                # и следующие ANCHOR_INTERVAL-1 кадров закрашивались слишком
                # узко, часть текста оставалась видна. Если трекинг ДО этого
                # был живым (misses == 0, т.е. предыдущий полный box ещё
                # актуален) и новый якорь заметно уже старого box — считаем
                # это неполным распознаванием этого конкретного кадра и
                # просто продолжаем трекинг по старому (более полному)
                # шаблону, не заменяя его. Обновляем на новый якорь только
                # когда он не хуже старого — иначе так никогда не подхватим
                # реально сузившийся/удаляющийся бейдж.
                prev_alive = live_template is not None and misses == 0 and last_box is not None
                if prev_alive and ocr_box[2] < last_box[2] * 0.7:
                    tracked = track_local(gray, live_template, last_box)
                    if tracked is not None:
                        box = tracked[:4]
                        source = 'track'
                        last_box = box
                        misses = 0
                    else:
                        # трекинг по старому шаблону тоже не сработал на этом
                        # кадре — лучше взять узкий якорь, чем не закрасить вообще
                        box = ocr_box
                        source = 'ocr'
                        live_template = make_live_template(gray, box)
                        last_box = box
                        misses = 0
                else:
                    box = ocr_box
                    source = 'ocr'
                    live_template = make_live_template(gray, box)
                    last_box = box
                    misses = 0
            elif live_template is not None:
                # T-98 (28.08.2026): ПОЧИНЕНО — раньше здесь было
                # live_template=None + misses=TRACK_MAX_MISSES, то есть ОДИН
                # неудачный ПЛАНОВЫЙ якорь мгновенно выбрасывал живой шаблон,
                # даже если локальный трекинг по нему только что уверенно
                # отработал несколько кадров подряд (реальный тест IMG_0901:
                # якорь на 200 поймал бейдж, трекинг вёл его 201-204 без
                # проблем — а на следующем плановом якоре, 210, OCR ничего не
                # нашёл (перспектива/блик именно на этом кадре) и тут же
                # обнулял всё, хотя трекинг почти наверняка продолжил бы
                # вести бейдж и дальше). Теперь неудачный якорь — это просто
                # ещё один промах трекинга, не особый случай: пробуем
                # локальный трекинг по уже имеющемуся шаблону и сдаёмся
                # только после TRACK_MAX_MISSES промахов подряд, как и в
                # остальное время между якорями.
                tracked = track_local(gray, live_template, last_box)
                if tracked is not None:
                    box = tracked[:4]
                    source = 'track'
                    last_box = box
                    misses = 0
                else:
                    misses += 1
                    if misses >= TRACK_MAX_MISSES:
                        live_template = None
            else:
                misses = TRACK_MAX_MISSES
        elif live_template is not None:
            tracked = track_local(gray, live_template, last_box)
            if tracked is not None:
                box = tracked[:4]
                source = 'track'
                last_box = box
                misses = 0
            else:
                misses += 1
                if misses >= TRACK_MAX_MISSES:
                    live_template = None

        results.append((idx, box, source))
        idx += 1
    cap.release()
    dt = time.time() - t0
    n_found = sum(1 for _, b, _ in results if b is not None)
    log(f"detect_boxes: {idx} кадров, {ocr_calls} OCR-вызовов, {n_found} кадров с бейджем, {dt:.1f}с")
    return results


def fill_frame(frame, box):
    x, y, w, h = box
    target_w = int(h * FULL_PLATE_AR)
    if target_w > w:
        extra = target_w - w
        x = x - extra // 2
        w = target_w
    # 26.08.2026: было max(8, w // 8) / max(8, h // 4) — недостаточно, когда
    # box построен по ОДНОМУ пойманному слову на смазанном/наклонном кадре
    # (см. FULL_PLATE_AR коммент выше): табличка снята под углом крупным
    # планом, из-за перспективы "CLUB" оказывается не только правее, но и
    # НИЖЕ "WINNER" — часть текста оставалась видна и по x, и по y на
    # выходе (проверено на IMG_0933, кадр 10). Увеличили запас по обеим осям.
    pad_x = max(150, w // 2)
    pad_y = max(40, h)
    x0, y0 = max(0, x - pad_x), max(0, y - pad_y)
    x1, y1 = min(frame.shape[1], x + w + pad_x), min(frame.shape[0], y + h + pad_y)
    roi = frame[y0:y1, x0:x1]
    if roi.size == 0:
        return frame
    fill_color = cv2.mean(roi)[:3]
    frame[y0:y1, x0:x1] = fill_color
    return frame


def render(path, results, out_path, log=lambda msg: None):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(out_path, fourcc, fps, (w, h))
    idx = 0
    filled = 0
    box_by_idx = {r[0]: r[1] for r in results}
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        box = box_by_idx.get(idx)
        if box is not None:
            frame = fill_frame(frame, box)
            filled += 1
        writer.write(frame)
        idx += 1
    cap.release()
    writer.release()
    log(f"render: записано {idx} кадров, закрашено {filled}")


def mux_audio(video_only_path, source_path, out_path):
    """cv2.VideoWriter не пишет звук — без этого шага видео с закрашенным
    бейджем ушло бы немым. Копируем аудиодорожку из исходника без
    перекодирования (-c:v copy — видео уже готово, -c:a copy — звук не
    трогаем). '1:a:0?' — знак вопроса означает "если есть аудиодорожка"
    (у некоторых исходников её может не быть, тогда просто без звука)."""
    cmd = [
        "ffmpeg", "-y", "-i", video_only_path, "-i", source_path,
        "-map", "0:v:0", "-map", "1:a:0?",
        "-c:v", "copy", "-c:a", "copy", "-shortest", out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def process_video(in_path, out_path, log=lambda msg: None):
    """Полный пайплайн: детект -> рендер -> сведение звука. CPU-bound, может
    занимать от десятков секунд до нескольких минут — в асинхронном коде
    вызывать через asyncio.to_thread(process_video, in_path, out_path)."""
    results = detect_boxes(in_path, log=log)
    tmp_video_only = out_path + ".video_only.mp4"
    try:
        render(in_path, results, tmp_video_only, log=log)
        mux_audio(tmp_video_only, in_path, out_path)
    finally:
        import os
        if os.path.exists(tmp_video_only):
            os.remove(tmp_video_only)
    return out_path


if __name__ == '__main__':
    process_video(sys.argv[1], sys.argv[2], log=print)
    print(f"done -> {sys.argv[2]}")
