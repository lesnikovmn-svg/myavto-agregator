/*
 * Юнит-тест поиска по каталогу — 24.08.2026, по запросу пользователя:
 * "нужно добавить тест записывает клиент как читает по английски но
 * кириллицей" (т.е. когда клиент печатает английское название компании
 * так, как оно ЗВУЧИТ по-русски, а не побуквенно — например "владтд" для
 * VladTD или "май авто" для MY Avto — см. TASKS.md T-68).
 *
 * Тестирует translit()/matchesQuery()/SEARCH_ALIASES из app.js БЕЗ
 * дублирования кода: вырезает реальный блок между маркерами
 * "// TEST-EXTRACT-START" / "// TEST-EXTRACT-END" прямо из app.js и
 * выполняет его — если кто-то поменяет логику в app.js, тест либо
 * останется актуальным (проверяет реальный код), либо сломается на
 * несовпадении, а не молча протухнет на копии.
 *
 * Без внешних зависимостей (никакого npm install/jest) — только
 * встроенный assert, тот же принцип, что и остальной проект (см. T-75:
 * CI гоняет node --check + py_compile, тоже без npm-пакетов).
 *
 * Запуск:
 *     node test_search.js
 * Выход 0 — все тесты прошли, 1 — есть провалы (тот же контракт, что
 * py_compile/node --check в CI, легко подключить сюда же, см. T-75).
 */

const fs = require('fs');
const assert = require('assert');
const path = require('path');

const APP_JS_PATH = path.join(__dirname, 'app.js');
const START_MARKER = '// TEST-EXTRACT-START';
const END_MARKER = '// TEST-EXTRACT-END';

function loadSearchLogic() {
  const src = fs.readFileSync(APP_JS_PATH, 'utf-8');
  const start = src.indexOf(START_MARKER);
  const end = src.indexOf(END_MARKER);
  if (start === -1 || end === -1) {
    throw new Error(
      `Не нашёл маркеры ${START_MARKER}/${END_MARKER} в app.js — блок поиска ` +
      `переименовали или удалили, тест нужно поправить вручную.`
    );
  }
  const snippet = src.slice(start, end);
  const wrapped = snippet + '\nmodule.exports = { translit, matchesQuery, SEARCH_ALIASES, TRANSLIT_MAP };';
  const module_ = { exports: {} };
  // eslint-disable-next-line no-new-func
  new Function('module', 'exports', wrapped)(module_, module_.exports);
  return module_.exports;
}

const { translit, matchesQuery } = loadSearchLogic();

// Фикстуры — упрощённые, но по форме как реальные объекты COMPANIES
// (update_site.py всегда кладёт name/description/directions/tags).
const VLADTD = {
  name: 'VladTD',
  description: 'Автомобили под заказ из Японии, Китая и Южной Кореи.',
  directions: ['Япония', 'Китай', 'Корея'],
  tags: ['Под заказ', 'Полное сопровождение'],
};
const MY_AVTO = {
  name: 'MY Avto',
  description: 'Подбор, параллельный импорт, таможня, доставка.',
  directions: ['Европа', 'Китай', 'Япония'],
  tags: ['Подбор', 'Параллельный импорт'],
};
const WESTMOTORS = {
  name: 'Westmotors',
  description: 'Импорт автомобилей под заказ.',
  directions: ['Корея', 'Китай'],
  tags: [],
};

function search(company, rawQuery) {
  const q = rawQuery.toLowerCase().trim();
  return matchesQuery(company, q, translit(q));
}

let passed = 0;
let failed = 0;
function check(label, actual, expected) {
  try {
    assert.strictEqual(actual, expected);
    console.log(`  OK   ${label}`);
    passed++;
  } catch (e) {
    console.log(`  FAIL ${label} — ожидалось ${expected}, получили ${actual}`);
    failed++;
  }
}

console.log('Тест: поиск по каталогу, когда клиент печатает английское название кириллицей\n');

// 1) побуквенная транслитерация: "владтд" -> "vladtd" совпадает с "VladTD".
check('"владтд" находит VladTD', search(VLADTD, 'владтд'), true);
check('"ВЛАДТД" (регистр не важен) находит VladTD', search(VLADTD, 'ВЛАДТД'), true);

// 2) точечный алиас для фонетических написаний, которые транслитерация
//    не ловит побуквенно (MY читается как "май", не как "мы"/"my").
check('"май авто" находит MY Avto (через SEARCH_ALIASES)', search(MY_AVTO, 'май авто'), true);
check('"майавто" (слитно) находит MY Avto', search(MY_AVTO, 'майавто'), true);

// 3) обычный прямой поиск (без кириллицы) продолжает работать как раньше.
check('"vladtd" (латиницей) находит VladTD', search(VLADTD, 'vladtd'), true);
check('"авто" находит MY Avto по описанию', search(MY_AVTO, 'авто'), true);
check('"корея" находит VladTD по направлению', search(VLADTD, 'корея'), true);
check('"под заказ" находит VladTD по тегу', search(VLADTD, 'под заказ'), true);

// 4) известное ограничение побуквенной транслитерации — ДОКУМЕНТИРУЕМ,
//    а не прячем: "вестморторс" транслитерируется в "vestmotors", что НЕ
//    совпадает с "westmotors" (русское "в" не всегда значит "w"). Если
//    этот тест начнёт падать — значит логику усилили (например, словарём
//    альтернативных транслитераций), стоит обновить комментарий, а не
//    просто поправить ожидание.
check('"вестморторс" пока НЕ находит Westmotors (известное ограничение, см. TASKS.md T-68)',
  search(WESTMOTORS, 'вестморторс'), false);

// 5) отсутствие ложных срабатываний — случайное слово не должно находить
//    несвязанную компанию.
check('случайный запрос не находит VladTD', search(VLADTD, 'случайный текст'), false);
check('пустая транслитерация не ломает поиск ("" запрос)', search(VLADTD, ''), true); // q='' — .includes('') всегда true, ожидаемое поведение JS

console.log(`\nИтого: ${passed} прошло, ${failed} провалено.`);
if (failed > 0) {
  process.exit(1);
}
