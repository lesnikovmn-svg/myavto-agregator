const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, AlignmentType, VerticalAlign, LevelFormat,
  convertInchesToTwip, ImageRun
} = require("docx");
const fs = require("fs");

// ---- MY Avto brand palette (sampled from my-avto.online: near-black bg, gold accent) ----
const DARK   = "141414"; // page/header band background
const CARD   = "1E1E1E"; // card / label shading on dark
const GOLD   = "C9A45C"; // primary accent (buttons, prices, headings on the site)
const GOLDLT = "E0C182"; // lighter gold for text-on-dark
const WHITE  = "FFFFFF";
const INK    = "1A1A1A"; // body text on white
const MUTED  = "6B6B6B"; // secondary grey text
const RULE   = "D8C79A"; // thin gold rule on white background
const TABLE_LABEL_BG = "F3EEE2"; // soft warm tint for table label cells on white page

const FULL_W = 9500;

function sectionTitle(text) {
  return [
    new Paragraph({
      spacing: { before: 160, after: 70 },
      border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: GOLD } },
      children: [new TextRun({
        text: text.toUpperCase(),
        bold: true,
        size: 20,
        color: "8A6D2F",
        characterSpacing: 14,
      })],
    }),
  ];
}

function bodyText(text, opts = {}) {
  return new Paragraph({
    spacing: { after: 30, before: 40 },
    children: [new TextRun({ text, size: 18, color: INK, ...opts })],
  });
}

function bullet(text) {
  return new Paragraph({
    numbering: { reference: "offer-bullets", level: 0 },
    spacing: { after: 20 },
    children: [new TextRun({ text, size: 18, color: INK })],
  });
}

function hr() {
  return new Paragraph({
    spacing: { before: 60, after: 60 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: RULE } },
    children: [new TextRun({ text: "" })],
  });
}

function specCell(text, opts = {}) {
  return new TableCell({
    width: { size: opts.width || 3000, type: WidthType.DXA },
    shading: opts.shaded ? { type: ShadingType.CLEAR, fill: TABLE_LABEL_BG } : undefined,
    verticalAlign: VerticalAlign.CENTER,
    margins: { top: 50, bottom: 50, left: 120, right: 120 },
    children: [new Paragraph({
      children: [new TextRun({
        text,
        bold: !!opts.bold,
        size: 17,
        color: opts.bold ? "8A6D2F" : INK,
      })],
    })],
  });
}

function specTable(rows) {
  return new Table({
    width: { size: FULL_W, type: WidthType.DXA },
    columnWidths: [3200, 6300],
    borders: {
      top: { style: BorderStyle.SINGLE, size: 2, color: "E4DCC6" },
      bottom: { style: BorderStyle.SINGLE, size: 2, color: "E4DCC6" },
      left: { style: BorderStyle.SINGLE, size: 2, color: "E4DCC6" },
      right: { style: BorderStyle.SINGLE, size: 2, color: "E4DCC6" },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: "E4DCC6" },
      insideVertical: { style: BorderStyle.SINGLE, size: 2, color: "E4DCC6" },
    },
    rows: rows.map(([k, v]) =>
      new TableRow({
        children: [
          specCell(k, { bold: true, width: 3200, shaded: true }),
          specCell(v, { width: 6300 }),
        ],
      })
    ),
  });
}

// full-width dark "band" — single-cell table used as a colored banner (paragraphs can't carry shading)
function darkBand(paragraphs) {
  return new Table({
    width: { size: FULL_W, type: WidthType.DXA },
    columnWidths: [FULL_W],
    borders: {
      top: { style: BorderStyle.NONE, size: 0, color: DARK },
      bottom: { style: BorderStyle.NONE, size: 0, color: DARK },
      left: { style: BorderStyle.NONE, size: 0, color: DARK },
      right: { style: BorderStyle.NONE, size: 0, color: DARK },
    },
    rows: [
      new TableRow({
        cantSplit: true,
        children: [
          new TableCell({
            width: { size: FULL_W, type: WidthType.DXA },
            shading: { type: ShadingType.CLEAR, fill: DARK },
            margins: { top: 120, bottom: 120, left: 220, right: 220 },
            children: paragraphs,
          }),
        ],
      }),
    ],
  });
}

const today = new Date();
const dateStr = today.toLocaleDateString("ru-RU", { day: "2-digit", month: "long", year: "numeric" });

const doc = new Document({
  numbering: {
    config: [
      {
        reference: "offer-bullets",
        levels: [
          { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
            style: { run: { color: GOLD, bold: true }, paragraph: { indent: { left: convertInchesToTwip(0.35), hanging: convertInchesToTwip(0.18) } } } },
        ],
      },
    ],
  },
  sections: [
    {
      properties: {
        page: {
          size: { width: 11906, height: 16838 }, // A4
          margin: { top: 450, bottom: 450, left: 850, right: 850 },
        },
      },
      children: [
        // ---- Dark header band, mirrors the site's dark navbar + gold logotype ----
        darkBand([
          new Paragraph({
            spacing: { after: 30 },
            children: [
              new TextRun({ text: "MY ", bold: true, size: 28, color: WHITE }),
              new TextRun({ text: "Avto", bold: true, size: 28, color: GOLD }),
              new TextRun({ text: "   Привезём любой автомобиль под ключ", bold: true, size: 16, color: GOLDLT }),
            ],
          }),
          new Paragraph({
            spacing: { after: 0 },
            children: [new TextRun({ text: "my-avto.online · myavto-agregator.ru   ·   Максим +7 938 409-67-08   ·   Антон +7 963 383-79-28", size: 15, color: "BFBFBF" })],
          }),
        ]),

        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 100, after: 30 },
          children: [new TextRun({ text: "КОММЕРЧЕСКОЕ ПРЕДЛОЖЕНИЕ", bold: true, size: 26, color: "8A6D2F" })],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 30 },
          children: [new TextRun({ text: `Geely Galaxy M7 · комплектация 星舰版 (Starship, топ)`, bold: true, size: 21, color: INK })],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 120 },
          children: [new TextRun({ text: `Дата предложения: ${dateStr}`, size: 16, italics: true, color: MUTED })],
        }),

        new Paragraph({
          spacing: { after: 80 },
          children: [new TextRun({
            text: "Уважаемый клиент! Предлагаем к поставке под заказ из Китая кроссовер Geely Galaxy M7 в топовой комплектации Starship (星舰版) — гибридный кроссовер бизнес-класса с рекордным для сегмента запасом хода. Ниже — полные характеристики, состав оснащения и итоговая стоимость «под ключ».",
            size: 18, color: INK,
          })],
        }),

        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 40 },
          children: [new ImageRun({
            type: "png",
            data: fs.readFileSync("/tmp/outputs/m7_photo.png"),
            transformation: { width: 460, height: 274 },
          })],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 140 },
          children: [new TextRun({ text: "Geely Galaxy M7 (цвет серый металлик) — фото автомобиля, иллюстрация", size: 14, italics: true, color: MUTED })],
        }),

        ...sectionTitle("1. Общая информация"),
        specTable([
          ["Марка / модель", "Geely Galaxy M7"],
          ["Комплектация", "星舰版 (Starship) — топовая версия линейки"],
          ["Тип кузова", "Кроссовер (SUV), 5 дверей, 5 мест"],
          ["Год выпуска", "2026"],
          ["Состояние", "Новый автомобиль (ввоз под заказ из Китая)"],
        ]),

        ...sectionTitle("2. Двигатель и гибридная система"),
        specTable([
          ["Силовая установка", "Гибрид Thor (雷神) EM-i — 1-ступенчатая DHT-трансмиссия"],
          ["ДВС", "1.5 л, атм., 4 цилиндра — 82 кВт / 112 л.с., 136 Н·м"],
          ["Электромотор", "175 кВт / 238 л.с. (пиковая), 262 Н·м"],
          ["Привод", "Передний"],
          ["Разгон 0–100 км/ч", "≈ 7 секунд"],
          ["Батарея", "LFP, 29.8 кВт·ч"],
          ["Запас хода на электротяге (CLTC)", "225 км"],
          ["Суммарный запас хода (бак + батарея)", "до 1 730 км"],
          ["Быстрая зарядка DC", "30→80% за 15 минут"],
          ["Зарядка от сети AC", "≈ 4.7 часа"],
        ]),

        ...sectionTitle("3. Габариты и кузов"),
        specTable([
          ["Длина / ширина / высота", "4 770 / 1 905 / 1 685 мм"],
          ["Колёсная база", "2 785 мм"],
          ["Объём багажника", "700–1 990 л (со сложенными задними сиденьями)"],
          ["Колёсные диски", "20″, шины 245/45 R20"],
          ["Подвеска", "Спереди — независимая McPherson, сзади — независимая многорычажная. Одинаковая на всех комплектациях, разницы по версиям нет"],
        ]),

        ...sectionTitle("4. Оснащение комплектации Starship (星舰版)"),
        bodyText("Салон и комфорт:", { bold: true }),
        bullet("Передние сиденья с подогревом, вентиляцией и массажем"),
        bullet("Электрорегулировка и память положения водительского и переднего пассажирского сидений"),
        bullet("Электропривод крышки багажника с сенсорным открыванием и памятью положения"),
        bullet("Внутрисалонное зеркало заднего вида с автозатемнением"),

        bodyText("Мультимедиа и электроника:", { bold: true }),
        bullet("Центральный сенсорный дисплей 15.4″ на чипе Longying-1 (龍鰲一号)"),
        bullet("HUD — проекция показаний на лобовое стекло"),
        bullet("Аудиосистема на 23 динамика"),
        bullet("Встроенный видеорегистратор"),

        bodyText("Системы помощи водителю (ADAS, уровень L2):", { bold: true }),
        bullet("Трассовый автопилот с навигационной поддержкой (NOA)"),
        bullet("3 радара миллиметрового диапазона, 12 ультразвуковых датчиков, 11 камер"),
        bullet("Автоматическая парковка, в т.ч. дистанционный заезд/выезд"),
        bullet("Активное торможение, удержание в полосе, помощь при перестроении, автосмена полосы"),

        bodyText("Экстерьер:", { bold: true }),
        bullet("Колёсные диски 20″ (у версии «探索+» — 19″)"),
        bullet("Адаптивная головная оптика с автопереключением света"),
        bullet("Панорамная крыша"),

        ...sectionTitle("5. Стоимость «под ключ»"),
        darkBand([
          new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [new TextRun({ text: "ИТОГОВАЯ СТОИМОСТЬ ДЛЯ КЛИЕНТА", size: 18, color: "BFBFBF", characterSpacing: 12 })],
          }),
          new Paragraph({
            alignment: AlignmentType.CENTER,
            spacing: { before: 60 },
            children: [new TextRun({ text: "3 250 000 ₽", bold: true, size: 44, color: GOLD })],
          }),
        ]),
        new Paragraph({ spacing: { before: 140, after: 0 }, children: [new TextRun({ text: "" })] }),
        specTable([
          ["Автомобиль, логистика, услуги компании", "2 420 000 ₽ — оплата наличными в компанию MY Avto"],
          ["Таможенный платёж (пошлина, акциз, утильсбор, НДС)", "830 000 ₽ — оплачивается клиентом самостоятельно на свой счёт в ФТС"],
        ]),
        new Paragraph({ spacing: { before: 140, after: 120 }, children: [new TextRun({
          text: "В стоимость включено: закупка автомобиля в Китае, международная логистика, таможенное оформление, СБКТС/ЭПТС, утилизационный сбор и все обязательные таможенные платежи. Цена актуальна на дату предложения и может быть пересмотрена при изменении курса юаня, таможенных ставок или методики расчёта утильсбора.",
          size: 18, italics: true, color: MUTED,
        })] }),
        new Paragraph({ spacing: { after: 120 }, children: [new TextRun({
          text: "Порядок оплаты: сумма за автомобиль, логистику и услуги компании оплачивается наличными в кассу MY Avto, а таможенный платёж вносится клиентом самостоятельно напрямую на свой счёт в ФТС — через Сбербанк Онлайн или в кассе банка. Обе части в сумме составляют указанную выше итоговую стоимость.",
          size: 18, italics: true, color: MUTED,
        })] }),

        ...sectionTitle("6. Условия поставки"),
        bullet("Срок поставки: уточняется индивидуально при подтверждении заказа"),
        bullet("Форма оплаты: 100% предоплата. Таможенный платёж (830 000 ₽) клиент вносит самостоятельно на свой счёт в ФТС (через Сбербанк Онлайн или в кассе банка), остальные 2 420 000 ₽ — наличными в компанию; подробная разбивка — в разделе 5"),
        bullet("Комплект документов при передаче: ЭПТС, СБКТС, договор купли-продажи, таможенная декларация"),
        bullet("Гарантия: условия уточняются отдельно"),

        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 80, after: 20 },
          children: [new ImageRun({
            type: "png",
            data: fs.readFileSync("/tmp/outputs/m7_interior.png"),
            transformation: { width: 360, height: 185 },
          })],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 40 },
          children: [new TextRun({ text: "Geely Galaxy M7 (Starship) — салон, приборная панель и мультимедиа, иллюстрация", size: 14, italics: true, color: MUTED })],
        }),

        hr(),
        new Paragraph({
          spacing: { before: 60, after: 60 },
          children: [new TextRun({ text: "Предложение носит информационный характер и не является публичной офертой. Точные условия фиксируются в договоре с клиентом.", size: 16, italics: true, color: MUTED })],
        }),

        // ---- Dark footer band with contacts, mirrors the site's dark footer ----
        darkBand([
          new Paragraph({
            spacing: { after: 100 },
            children: [
              new TextRun({ text: "MY ", bold: true, size: 26, color: WHITE }),
              new TextRun({ text: "Avto", bold: true, size: 26, color: GOLD }),
              new TextRun({ text: "  —  ваш надёжный партнёр в выборе авто!", size: 18, color: "BFBFBF" }),
            ],
          }),
          new Paragraph({ spacing: { after: 40 }, children: [new TextRun({ text: "Максим — Telegram: LesnikovM  ·  +7 938 409-67-08", size: 18, color: GOLDLT })] }),
          new Paragraph({ spacing: { after: 40 }, children: [new TextRun({ text: "Антон — Telegram: Tohakmv  ·  +7 963 383-79-28", size: 18, color: GOLDLT })] }),
          new Paragraph({ spacing: { after: 40 }, children: [new TextRun({ text: "Telegram-каналы: My_Avto_Optimal · MY_Avto5 · my_avto_opyt", size: 18, color: "BFBFBF" })] }),
          new Paragraph({ spacing: { after: 40 }, children: [new TextRun({ text: "Сайты: my-avto.online · myavto-agregator.ru", size: 18, color: "BFBFBF" })] }),
          new Paragraph({ spacing: { after: 0 }, children: [new TextRun({ text: "Instagram / VK: my_avto5   ·   MAX: присоединиться в профиле   ·   Яндекс: профиль компании", size: 18, color: "BFBFBF" })] }),
        ]),
      ],
    },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  require("fs").writeFileSync("/tmp/outputs/Geely_Galaxy_M7_Starship_offer.docx", buf);
  console.log("written");
});
