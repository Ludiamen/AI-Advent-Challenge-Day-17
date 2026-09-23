// Сквозная проверка страницы в настоящем браузере.
//
// Зачем отдельно от tests.py: тесты на Python проверяют сервер и структуру
// скрипта, но не могут выполнить страницу. Ошибка, ради которой этот прогон и
// появился, была именно такой — «запуститьСценарий» оказался объявлен внутри
// другой функции. Синтаксис корректен, сервер отвечает, все 150 тестов зелёные,
// а кнопка «Спросить» падает с ReferenceError, и сценарий не запускается вовсе.
//
// Как запускать:
//   1) поднять сервер:   MEMORY_DIR=/tmp/проба PORT=5000 python web.py
//   2) поднять браузер:  google-chrome --headless=new --remote-debugging-port=9222 \
//                          --no-sandbox --disable-gpu about:blank
//   3) сам прогон:       node browser.mjs [адрес] [ключ-модели] [запрос] [режим]
//
// Режимы:
//   сценарий (по умолчанию) — запустить сценарий по триггеру и дождаться конца;
//   пауза                   — включить «подтверждать смену стадии», дождаться
//                             остановки, нажать «Продолжить» и убедиться, что
//                             задача сдвинулась;
//   переходы                — завести задачу, нажать запертую кнопку перехода и
//                             убедиться, что страница показывает разбор отказа,
//                             а после плана и утверждения переход открывается;
//   mcp                     — панель MCP: подключиться к своему серверу, затем ко
//                             всем; проверить карточки (соединение, сбой, пропуск),
//                             пометки доступа, закрытые фильтром инструменты и
//                             JSON-схему. Модель в этом режиме не вызывается.
//   инструменты             — День 17: включить инструменты, задать вопрос про
//                             трекер и увидеть строки вызовов «↳» под ответом;
//                             попросить изменение и убедиться, что появилась
//                             заявка, а вызова не было; подтвердить её и увидеть
//                             результат; вызвать инструмент кнопкой из панели MCP.
//                             Нужен поднятый мок: python tracker_api.py
//
// По умолчанию: http://127.0.0.1:5000, модель ds-flash. Прогон печатает, что
// появляется в чате, и — главное — исключения JS, которых в чате не видно.

const АДРЕС = process.argv[2] || 'http://127.0.0.1:5000';
const МОДЕЛЬ = process.argv[3] || 'ds-flash';
const РЕЖИМ = process.argv[5] || 'сценарий';
const ЗАПРОС = process.argv[4] ||
  'Напиши фичу по получению данных о кадастровых участках с ресурса ' +
  'https://nspd.gov.ru/map и вывода их отдельным слоем на карте ГИС с газопроводами.';
const CDP = process.env.CDP || 'http://127.0.0.1:9222';
const ПРЕДЕЛ_МС = 300000;

const цель = await (await fetch(`${CDP}/json/new?${encodeURIComponent(АДРЕС)}`,
                                {method: 'PUT'})).json();
const ws = new WebSocket(цель.webSocketDebuggerUrl);
const ждущие = new Map();
const ошибки = [];
let счётчик = 0;

ws.addEventListener('message', (событие) => {
  const м = JSON.parse(событие.data);
  if (м.id && ждущие.has(м.id)) { ждущие.get(м.id)(м); ждущие.delete(м.id); }
  if (м.method === 'Runtime.exceptionThrown') {
    const д = м.params.exceptionDetails;
    ошибки.push('исключение: ' + (д.exception?.description || д.text));
  }
  if (м.method === 'Runtime.consoleAPICalled' && м.params.type === 'error') {
    ошибки.push('console.error: ' +
                м.params.args.map(а => а.value ?? а.description).join(' '));
  }
});
await new Promise(р => ws.addEventListener('open', р));

const зов = (метод, параметры = {}) => new Promise(р => {
  const id = ++счётчик;
  ждущие.set(id, р);
  ws.send(JSON.stringify({id, method: метод, params: параметры}));
});

const выполнить = async (код) => {
  const о = await зов('Runtime.evaluate',
                      {expression: код, awaitPromise: true, returnByValue: true});
  if (о.result?.exceptionDetails) ошибки.push('evaluate: ' + о.result.exceptionDetails.text);
  return о.result?.result?.value;
};

await зов('Runtime.enable');
await зов('Log.enable');
await new Promise(р => setTimeout(р, 3000));    // страница подтягивает состояние

console.log('страница:', await выполнить('document.title'));
console.log('модель:', await выполнить(
  `(() => { const с = document.getElementById('модель');
            с.value = ${JSON.stringify(МОДЕЛЬ)};
            с.dispatchEvent(new Event('change'));
            return с.value; })()`));

if (РЕЖИМ === 'пауза') {
  console.log('режим «по шагам»:', await выполнить(
    `(() => { const г = document.getElementById('режим-по-шагам');
              г.checked = true; г.dispatchEvent(new Event('change'));
              return г.checked; })()`));
}

if (РЕЖИМ === 'mcp') {
  const карточки = () => выполнить(`Array.from(document.querySelectorAll('.mcp-сервер')).map(к => ({
    имя: к.dataset['сервер'], класс: к.className.replace('mcp-сервер', '').trim() || '—',
    инструментов: к.querySelectorAll('.mcp-инструмент').length,
    закрыто: к.querySelectorAll('.mcp-инструмент.закрыт').length,
    только_чтение: к.querySelectorAll('.доступ.только-чтение').length,
    текст: к.innerText.split('\\n').slice(0, 4).join(' | ').slice(0, 160) }))`);
  const ждать = async (секунд) => {
    const начало = Date.now();
    while (Date.now() - начало < секунд * 1000) {
      await new Promise(р => setTimeout(р, 1000));
      const идёт = await выполнить(`document.querySelector('#mcp-панель').innerText.includes('Подключаюсь')`);
      if (!идёт) return (Date.now() - начало) / 1000;
    }
    ошибки.push('панель MCP не дождалась конца подключения');
    return -1;
  };

  const до = await карточки();
  console.log('серверов на панели:', до.length, до.map(к => к.имя).join(', '));
  if (до.length < 2) ошибки.push('на панели MCP нет серверов');

  await выполнить(`document.querySelector('.mcp-подключить[data-mcp="agent-state"]').click(); 'ок'`);
  console.log('agent-state подключён за', await ждать(60), 'с');
  const свой = (await карточки()).find(к => к.имя === 'agent-state');
  console.log('agent-state:', JSON.stringify(свой));
  if (!свой || свой.класс !== 'ок') ошибки.push('свой сервер не подключился');
  if (свой && свой.инструментов !== 6) ошибки.push(`у своего сервера ${свой?.инструментов} инструментов вместо 6`);
  if (свой && свой.только_чтение !== 6) ошибки.push('не все инструменты своего сервера помечены «только чтение»');

  // Схема раскрывается и содержит JSON Schema.
  // Список инструментов свёрнут: раскрываем его так же, как человек, — щелчком.
  await выполнить(`document.querySelector('.mcp-список[data-список="agent-state"] summary').click(); 'ок'`);
  const раскрыт = await выполнить(`document.querySelector('.mcp-список[data-список="agent-state"]').open`);
  if (!раскрыт) ошибки.push('список инструментов не раскрывается');
  const схема = await выполнить(`(() => {
    const д = document.querySelector('.mcp-сервер[data-сервер="agent-state"] .mcp-инструмент[data-инструмент="get_task"] details');
    if (!д) return 'нет';
    д.querySelector('summary').click(); return д.querySelector('pre').innerText; })()`);
  console.log('схема get_task:', (схема || '').replace(/\s+/g, ' ').slice(0, 140));
  if (!(схема || '').includes('"task_id"')) ошибки.push('JSON-схема get_task не показана');

  await выполнить(`document.getElementById('mcp-все').click(); 'ок'`);
  console.log('все серверы осмотрены за', await ждать(240), 'с');
  const после = await карточки();
  const остался = await выполнить(`document.querySelector('.mcp-список[data-список="agent-state"]').open`);
  console.log('раскрытый список пережил повторное подключение:', остался ? 'да' : 'НЕТ');
  if (!остался) ошибки.push('после «Подключиться ко всем» раскрытый список свернулся');
  for (const к of после) console.log(`  ${к.имя.padEnd(12)} ${к.класс.padEnd(9)} инструментов ${к.инструментов}, закрыто ${к.закрыто} | ${к.текст}`);
  const фс = после.find(к => к.имя === 'filesystem');
  if (фс && фс.класс === 'ок' && фс.закрыто === 0) ошибки.push('фильтр filesystem не отмечен на странице');
  const гх = после.find(к => к.имя === 'github');
  if (гх && !['пропущен', 'ок'].includes(гх.класс)) ошибки.push('github показан не так, как настроен');

  const итог = await выполнить(`Array.from(document.querySelectorAll('#чат .системное'))
    .map(у => у.innerText).filter(т => т.startsWith('MCP:')).pop() || ''`);
  console.log('\nв чате:', итог);
  if (!итог) ошибки.push('в чате нет итога подключения');
  const сбоиMCP = await выполнить(`document.querySelectorAll('#чат .ошибка').length`);
  console.log('\n=== итог ===');
  console.log('сообщений об ошибке в чате:', сбоиMCP);
  console.log('исключений JS и провалов:', ошибки.length ? ошибки : 'нет');
  ws.close();
  process.exit(ошибки.length || сбоиMCP ? 1 : 0);
}

if (РЕЖИМ === 'инструменты') {
  const чат = () => выполнить(`Array.from(document.querySelectorAll('#чат .msg'))
    .map(у => (у.className.replace('msg','').trim() + ': ' + у.innerText).slice(0, 200))`);
  // Заявка появляется не в переписке, а карточкой справа: ждать её надо по
  // узлу, а не по тексту чата.
  const ждатьУзел = async (селектор, секунд) => {
    const начало = Date.now();
    while (Date.now() - начало < секунд * 1000) {
      await new Promise(р => setTimeout(р, 1000));
      const есть = await выполнить(`!!document.querySelector(${JSON.stringify(селектор)})`);
      if (есть) return (Date.now() - начало) / 1000;
    }
    ошибки.push(`не дождались узла: ${селектор}`);
    return -1;
  };
  const ждатьЧат = async (признак, секунд) => {
    const начало = Date.now();
    while (Date.now() - начало < секунд * 1000) {
      await new Promise(р => setTimeout(р, 1000));
      const есть = await выполнить(
        `document.getElementById('чат').innerText.includes(${JSON.stringify(признак)})`);
      if (есть) return (Date.now() - начало) / 1000;
    }
    ошибки.push(`в чате не дождались: ${признак}`);
    return -1;
  };

  // 1. Включаем инструменты и ждём, пока страница скажет, во что это обходится.
  await выполнить(`(() => {
    document.getElementById('инструменты-серверы').value = 'tracker';
    const г = document.getElementById('инструменты-вкл');
    г.checked = true; г.dispatchEvent(new Event('change')); return 'ок'; })()`);
  const предел = Date.now() + 90000;
  let итогВключения = '';
  while (Date.now() < предел) {
    await new Promise(р => setTimeout(р, 1000));
    итогВключения = await выполнить(`document.getElementById('инструменты-итог').innerText`);
    if (итогВключения && !итогВключения.includes('подключаюсь')) break;
  }
  console.log('инструменты включены:', итогВключения);
  if (!/инстр\./.test(итогВключения)) ошибки.push('страница не показала, что досталось модели');
  if (!/схема ≈ \d+ ток/.test(итогВключения)) ошибки.push('страница не показала цену схемы');

  // 2. Вопрос, на который без трекера не ответить.
  await выполнить(`(() => {
    document.getElementById('ввод').value = 'Посмотри в трекере: какие задачи переноса сейчас в работе?';
    document.getElementById('отправить').click(); return 'ок'; })()`);
  console.log('ответ с вызовами получен за', await ждатьЧат('↳ tracker__', 180), 'с');
  const вызовы = await выполнить(`Array.from(document.querySelectorAll('#чат .вызов'))
    .map(у => у.innerText.slice(0, 120))`);
  console.log('вызовы на странице:');
  for (const в of вызовы || []) console.log('   ', в);
  if (!(вызовы || []).length) ошибки.push('строк вызовов на странице нет');
  const сбойные = await выполнить(`document.querySelectorAll('#чат .вызов.сбой').length`);
  if (сбойные) ошибки.push(`вызовов с ошибкой: ${сбойные}`);
  const ответСДанными = await выполнить(`(() => {
    const у = Array.from(document.querySelectorAll('#чат .от-агента')).pop();
    return у ? у.innerText : ''; })()`);
  console.log('в ответе есть ключи задач:', /MIG-\d/.test(ответСДанными || '') ? 'да' : 'НЕТ');
  if (!/MIG-\d/.test(ответСДанными || '')) ошибки.push('в ответе нет данных из трекера');

  // 3. Просьба изменить данные: вызова быть не должно, должна появиться заявка.
  await выполнить(`(() => {
    document.getElementById('ввод').value =
      'Добавь к задаче MIG-7 в трекере комментарий: «Проверено из браузера».';
    document.getElementById('отправить').click(); return 'ок'; })()`);
  console.log('заявка появилась за', await ждатьУзел('#заявки-панель .заявка', 180), 'с');
  const заявка = await выполнить(`(() => {
    const к = document.querySelector('#заявки-панель .заявка');
    return к ? к.innerText.replace(/\s+/g, ' ').slice(0, 200) : ''; })()`);
  console.log('заявка:', заявка);
  if (!заявка.includes('add_comment')) ошибки.push('в заявке не тот инструмент');
  if (!заявка.includes('MIG-7')) ошибки.push('в заявке не видно аргументов');
  const самовольные = await выполнить(
    `document.getElementById('чат').innerText.includes('↳ tracker__add_comment')`);
  if (самовольные) ошибки.push('меняющий вызов выполнился без подтверждения');

  // 4. Подтверждаем — вызов происходит, результат виден, заявка исчезает.
  await выполнить(`document.querySelector('#заявки-панель .заявка-да').click(); 'ок'`);
  console.log('вызов исполнен за', await ждатьЧат('Заявка №', 120), 'с');
  const результат = await выполнить(`(() => {
    const у = document.querySelector('#чат .ответ-вызова');
    return у ? у.innerText.replace(/\s+/g, ' ').slice(0, 160) : ''; })()`);
  console.log('ответ инструмента:', результат);
  if (!результат.includes('добавлен')) ошибки.push('результат подтверждённого вызова не показан');
  const осталось = await выполнить(`document.querySelectorAll('#заявки-панель .заявка').length`);
  console.log('заявок осталось:', осталось);
  if (осталось) ошибки.push('заявка не исчезла после исполнения');

  // 5. Кнопка «Вызвать» у инструмента в панели MCP. prompt() в headless-браузере
  // сам по себе не отвечает, поэтому подменяем его — человек в этом месте просто
  // вводит аргументы руками.
  await выполнить(`window.prompt = () => '{"key": "MIG-2"}'; 'ок'`);
  await выполнить(`document.querySelector('.mcp-подключить[data-mcp="tracker"]').click(); 'ок'`);
  await new Promise(р => setTimeout(р, 6000));
  const естьКнопка = await выполнить(`(() => {
    const к = document.querySelector('.mcp-вызвать[data-вызвать="tracker__get_issue"]');
    if (!к) return false; к.click(); return true; })()`);
  if (!естьКнопка) ошибки.push('в панели MCP нет кнопки «Вызвать»');
  else {
    console.log('ручной вызов выполнен за', await ждатьЧат('↳ tracker__get_issue', 60), 'с');
    const вручную = await выполнить(`(() => {
      const у = Array.from(document.querySelectorAll('#чат .ответ-вызова')).pop();
      return у ? у.innerText.replace(/\s+/g, ' ').slice(0, 120) : ''; })()`);
    console.log('ответ на ручной вызов:', вручную);
    if (!вручную.includes('MIG-2')) ошибки.push('ручной вызов не вернул задачу');
  }

  console.log('\n=== итог ===');
  console.log('сообщений об ошибке в чате:',
              await выполнить(`document.querySelectorAll('#чат .ошибка').length`));
  for (const строка of (await чат()).slice(-6)) console.log('  ', строка);
  console.log(ошибки.length ? 'ОШИБКИ:\n  ' + ошибки.join('\n  ') : 'ошибок нет');
  ws.close();
  process.exit(ошибки.length ? 1 : 0);
}

if (РЕЖИМ === 'переходы') {
  // Отдельный ход: здесь проверяется жизненный цикл задачи, а не сценарий.
  // Модель зовётся один раз — на составление плана, без которого нечего
  // утверждать, а значит, и нечего открывать.
  const имя = 'ворота-' + Date.now().toString().slice(-6);
  await выполнить(`(() => {
    document.getElementById('новая-задача').value = ${JSON.stringify(имя)};
    document.getElementById('название').value = 'проверка ворот из браузера';
    document.getElementById('создать').click(); return 'ок'; })()`);
  await new Promise(р => setTimeout(р, 2500));

  const кнопки = await выполнить(`Array.from(
    document.querySelectorAll('#переходы button')).map(к => к.textContent.trim())`);
  console.log('кнопки переходов:', кнопки);
  const запертых = (кнопки || []).filter(т => т.includes('🔒')).length;
  console.log('запертых кнопок:', запертых);
  if (!кнопки || кнопки.length < 3) ошибки.push('на странице нет кнопок переходов');
  if (!запертых) ошибки.push('все переходы показаны открытыми — ворота не видны');

  // Нажимаем запертый переход: страница должна показать разбор отказа.
  await выполнить(`(() => {
    const к = Array.from(document.querySelectorAll('#переходы button'))
      .find(к => к.textContent.includes('🔒'));
    if (к) к.click(); return к ? к.textContent : 'нет'; })()`);
  await new Promise(р => setTimeout(р, 2000));
  const отказов = await выполнить(`document.querySelectorAll('#чат .отказ').length`);
  const текстОтказа = await выполнить(
    `(document.querySelector('#чат .отказ') || {}).innerText || ''`);
  console.log('отказов в чате:', отказов);
  console.log('первые строки отказа:\n' + (текстОтказа || '(пусто)').split('\n').slice(0, 6).join('\n'));
  if (!отказов) ошибки.push('нажатие запертого перехода не дало отказа');

  console.log('\nсоставляю план (один вызов модели)…');
  await выполнить(`document.getElementById('план').click(); 'ок'`);
  const началоПлана = Date.now();
  while (Date.now() - началоПлана < 180000) {
    await new Promise(р => setTimeout(р, 3000));
    const занято = await выполнить(`document.getElementById('отправить').disabled`);
    if (!занято && Date.now() - началоПлана > 6000) break;
  }
  const доУтверждения = await выполнить(`document.getElementById('ворота').innerText`);
  console.log('\n=== ворота до утверждения ===\n' + (доУтверждения || '(пусто)'));

  await выполнить(`document.getElementById('утвердить-план').click(); 'ок'`);
  await new Promise(р => setTimeout(р, 2500));
  const послеУтверждения = await выполнить(`document.getElementById('ворота').innerText`);
  console.log('\n=== ворота после утверждения ===\n' + (послеУтверждения || '(пусто)'));

  const открыт = await выполнить(`(() => {
    const к = Array.from(document.querySelectorAll('#переходы button'))
      .find(к => к.textContent.includes('исполнение'));
    return к ? к.textContent.trim() : 'нет кнопки'; })()`);
  console.log('кнопка исполнения после утверждения:', открыт);
  if (открыт.includes('🔒')) ошибки.push('после утверждения плана переход остался закрытым');

  // Шаги задачи, заведённой руками, закрывает кнопка «Шаг сделан»: без неё
  // условие «шаги доведены» из браузера не выполнить вовсе.
  await выполнить(`(() => {
    const к = Array.from(document.querySelectorAll('#переходы button'))
      .find(к => к.textContent.includes('исполнение'));
    if (к) к.click(); return 'ок'; })()`);
  await new Promise(р => setTimeout(р, 2000));
  const шаговДо = await выполнить(
    `document.querySelectorAll('.лента-шагов .готов').length`);
  await выполнить(`document.getElementById('шаг-значение').value = 'сделано из браузера';
                   document.getElementById('закрыть-шаг').click(); 'ок'`);
  await new Promise(р => setTimeout(р, 2000));
  const шаговПосле = await выполнить(
    `document.querySelectorAll('.лента-шагов .готов').length`);
  console.log(`шагов закрыто: было ${шаговДо}, стало ${шаговПосле}`);
  if (шаговПосле <= шаговДо) ошибки.push('кнопка «Шаг сделан» не закрыла шаг');

  const сбоиПереходов = await выполнить(`document.querySelectorAll('#чат .ошибка').length`);
  console.log('\n=== итог ===');
  console.log('сообщений об ошибке в чате:', сбоиПереходов);
  console.log('исключений JS:', ошибки.length ? ошибки : 'нет');
  ws.close();
  process.exit(ошибки.length ? 1 : 0);
}

await выполнить(`document.getElementById('ввод').value = ${JSON.stringify(ЗАПРОС)};
                 document.getElementById('отправить').click(); 'пуск'`);

const начало = Date.now();
let прошлое = '';
while (Date.now() - начало < ПРЕДЕЛ_МС) {
  await new Promise(р => setTimeout(р, 3000));
  const чат = await выполнить(`document.getElementById('чат').innerText`);
  const новое = (чат || '').slice(прошлое.length);
  if (новое.trim()) {
    for (const строка of новое.split('\n').filter(с => с.trim()).slice(0, 3)) {
      console.log(`[${((Date.now() - начало) / 1000).toFixed(0)} с] ${строка.slice(0, 110)}`);
    }
    прошлое = чат;
  }
  const занято = await выполнить(`document.getElementById('отправить').disabled`);
  if (!занято && Date.now() - начало > 8000) break;
}

if (РЕЖИМ === 'пауза') {
  const состояние = await выполнить(
    `document.getElementById('состояние-задачи').innerText`);
  console.log('\n=== состояние задачи на паузе ===\n' + (состояние || '(пусто)'));
  const наПаузе = (состояние || '').includes('на паузе');
  console.log('карточка показывает паузу:', наПаузе ? 'да' : 'НЕТ');

  console.log('\nжму «Продолжить»…');
  await выполнить(`document.getElementById('продолжить-задачу').click(); 'ок'`);
  const начало2 = Date.now();
  while (Date.now() - начало2 < 120000) {
    await new Promise(р => setTimeout(р, 3000));
    const занято = await выполнить(`document.getElementById('отправить').disabled`);
    if (!занято && Date.now() - начало2 > 6000) break;
  }
  const после = await выполнить(`document.getElementById('состояние-задачи').innerText`);
  console.log('\n=== состояние после «Продолжить» ===\n' + (после || '(пусто)'));
  console.log('состояние сдвинулось:', после !== состояние ? 'да' : 'НЕТ');
  if (!наПаузе || после === состояние) ошибки.push('пауза или продолжение не сработали');
}

const чат = await выполнить(`document.getElementById('чат').innerText`);
const отвечено = await выполнить(`document.querySelectorAll('#чат .от-агента').length`);
const сбои = await выполнить(`document.querySelectorAll('#чат .ошибка').length`);

console.log('\n=== итог ===');
console.log('символов в чате:', (чат || '').length);
console.log('ответов агента:', отвечено);
console.log('сообщений об ошибке в чате:', сбои);
console.log('исключений JS:', ошибки.length ? ошибки : 'нет');

ws.close();
// Ненулевой код — чтобы прогон годился и для проверки перед сдачей.
process.exit(ошибки.length || сбои || !отвечено ? 1 : 0);
