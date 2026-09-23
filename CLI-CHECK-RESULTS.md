# Результат консольной проверки Дня 17

Прогон: `python check_cli.py`, модель для живых вызовов **ds-flash**, память в `cli-check-memory/`.
Дата: 2026-09-22 23:10. Заняло 4.7 мин.

**Ожиданий проверено: 196, сошлось: 196, расхождений: 0.**

Каждая строка — отдельный процесс. Проверяются три пласта: свой инструмент
MCP этого дня (сервер вокруг API трекера, вызов вручную и моделью, заявка
на изменение), подключение MCP из Дня 16 и наследство Дней 11–15 — чтобы
видеть, что не сломалось.

## Сводка

| шаг | проверка | команда | итог | секунд |
|---|---|---|---|---|
| 1.1 | Инструменты своего сервера вокруг API зарегистрированы | `cli.py --mcp-файл cli-check-memory/mcp-configs/tracker.json --mcp tracker` | ок | 6.7 |
| 1.2 | JSON-схема входа инструмента | `cli.py --mcp-файл cli-check-memory/mcp-configs/tracker.json --mcp tracker --mcp-схема` | ок | 8.0 |
| 1.3 | Без права записи меняющих инструментов нет | `cli.py --mcp-файл cli-check-memory/mcp-configs/tracker.json --mcp tracker-readonly` | ок | 11.4 |
| 1.4 | Что именно досталось модели | `cli.py --mcp-файл cli-check-memory/mcp-configs/tracker.json --инструменты tracker` | ок | 5.3 |
| 1.5 | Ручной вызов инструмента: данные из API | `cli.py --mcp-файл cli-check-memory/mcp-configs/tracker.json --вызвать tracker__list_issues --аргументы {"status": "inProgress", "limit": 5}` | ок | 5.2 |
| 1.6 | Ошибка инструмента названа и даёт код возврата | `cli.py --mcp-файл cli-check-memory/mcp-configs/tracker.json --вызвать tracker__get_issue --аргументы {"key": "MIG-999"}` | ок | 5.0 |
| 1.7 | Выдуманный моделью ключ задачи не уходит в API | `cli.py --mcp-файл cli-check-memory/mcp-configs/tracker.json --вызвать tracker__get_issue --аргументы {"key": "../../etc/passwd"}` | ок | 4.9 |
| 1.8 | Заявок ещё нет | `cli.py --заявки` | ок | 2.3 |
| 2.1 | Доказательный прогон: регистрация, параметры, результат | `check_tools.py --без-модели` | ок | 12.7 |
| 2.2 | Трекер не отвечает — сказано, что делать | `cli.py --mcp-файл cli-check-memory/mcp-configs/tracker-down.json --вызвать tracker__list_issues` | ок | 3.8 |
| 3.1 | Серверы описаны — видно без подключения | `cli.py --mcp-серверы` | ок | 2.3 |
| 3.2 | Соединение со своим сервером (stdio) | `cli.py --mcp agent-state` | ок | 3.8 |
| 3.3 | JSON-схема входа по ключу | `cli.py --mcp agent-state --mcp-схема` | ок | 3.8 |
| 3.4 | Эталонный сервер из npm (stdio через npx), фильтр | `cli.py --mcp filesystem` | ок | 4.2 |
| 3.5 | Тестовый сервер со всеми возможностями протокола | `cli.py --mcp everything` | ок | 6.3 |
| 3.6 | Удалённый сервер по Streamable HTTP | `cli.py --mcp deepwiki` | ок | 6.0 |
| 3.7 | Все серверы разом | `cli.py --mcp` | ок | 10.5 |
| 3.8 | Список корректен: сверка без SDK, схемы, имена | `check_mcp.py` | ок | 32.8 |
| 3.9 | Свой сервер по Streamable HTTP | `cli.py --mcp-файл cli-check-memory/mcp-configs/own-http.json --mcp` | ок | 2.7 |
| 4.1 | Сбои MCP названы, консоль не виснет | `cli.py --mcp-файл cli-check-memory/mcp-configs/failures.json --mcp` | ок | 8.0 |
| 4.2 | Неизвестный сервер | `cli.py --mcp нет-такого` | ок | 1.7 |
| 4.3 | Битый файл серверов | `cli.py --mcp-файл cli-check-memory/mcp-configs/broken.json --mcp-серверы` | ок | 1.9 |
| 5.1 | Три слоя памяти (День 11) | `cli.py --память` | ок | 1.9 |
| 5.2 | Заготовки профиля (День 12) | `cli.py --заготовки` | ок | 1.9 |
| 5.3 | Профиль из заготовки (День 12) | `cli.py --кто тимлид --заготовка тимлид` | ок | 3.6 |
| 5.4 | Инварианты на месте (День 14) | `cli.py --инварианты` | ок | 3.0 |
| 5.5 | Базовые условия переходов (День 15) | `cli.py --условия` | ок | 3.8 |
| 5.6 | Задача заводится (Дни 13, 15) | `cli.py --новая-задача регрессия-инструменты --название регрессия после MCP` | ок | 3.1 |
| 5.7 | Прыжок через этап отклонён (День 15) | `cli.py --задача регрессия-инструменты --стадия done` | ок | 3.0 |
| 5.8 | Пауза поверх этапа (День 13) | `cli.py --задача регрессия-инструменты --пауза` | ок | 5.5 |
| 5.9 | Пауза видна другому процессу (День 13) | `cli.py --задача регрессия-инструменты --состояние` | ок | 3.9 |
| 5.10 | Диалоговый режим (Дни 13–15) | `cli.py --задача регрессия-инструменты` | ок | 5.4 |
| 6.1 | Модель сама зовёт инструмент и отвечает по данным трекера | `cli.py --mcp-файл cli-check-memory/mcp-configs/tracker.json --инструменты tracker Посмотри в трекере: какие задачи переноса в работе?` | ок | 22.7 |
| 6.2 | Меняющий вызов не исполняется, а становится заявкой | `cli.py --mcp-файл cli-check-memory/mcp-configs/tracker.json --инструменты tracker Добавь к задаче MIG-7 в трекере комментарий: «Проверено консольным чек-листом».` | ок | 17.0 |
| 6.3 | Заявка видна другому процессу | `cli.py --заявки` | ок | 2.0 |
| 6.4 | Подтверждение исполняет вызов | `cli.py --mcp-файл cli-check-memory/mcp-configs/tracker.json --подтвердить 1` | ок | 6.3 |
| 6.5 | Изменение дошло до самого API | `cli.py --mcp-файл cli-check-memory/mcp-configs/tracker.json --вызвать tracker__get_issue --аргументы {"key": "MIG-7", "comments": 5}` | ок | 7.0 |
| 6.6 | Повторно ту же заявку не исполнить | `cli.py --mcp-файл cli-check-memory/mcp-configs/tracker.json --подтвердить 1` | ок | 2.7 |
| 7.1 | Отказ по инварианту за ноль токенов (День 14) | `cli.py Перепиши бэкенд на Laravel, команда его знает лучше.` | ок | 3.2 |
| 7.2 | Ответ с разбором промпта (День 11, живой вызов) | `cli.py --трейс Какой ORM использовать для геометрии в новой системе?` | ок | 32.2 |

## Подробности

### 1.1. Инструменты своего сервера вокруг API зарегистрированы

```
$ python cli.py --память-в cli-check-memory --mcp-файл cli-check-memory/mcp-configs/tracker.json --mcp tracker
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ соединение установлено
- ✓ сервер назвал себя
- ✓ пять инструментов
- ✓ читающие помечены
- ✓ меняющие помечены
- ✓ входные параметры описаны
- ✓ цена схемы посчитана
- ✓ код возврата 0

<details><summary>вывод</summary>

````
------------------------------------------------------------------------------
MCP: подключение к серверам из /home/gpgr/Документы/AI-Advent-Challenge/Day-17/cli-check-memory/mcp-configs/tracker.json
------------------------------------------------------------------------------
● tracker — stdio: ${PYTHON} ${PROJECT_DIR}/../../tracker_server.py
  Свой сервер вокруг API трекера (мок прогона)
  Соединение: установлено за 3,0 с · рукопожатие server/discover · протокол 2026-07-28
  Сервер: tracker 17.0 («Трекер задач миграции»)
  Возможности: tools, resources, prompts
  Инструкции сервера: Трекер задач проекта миграции ГИС газовых сетей (PHP5/CodeIgniter/MapServer → Django/GeoDjango/PostGIS/OpenLayers). Задачи лежат в очередях; у задачи …
  Инструменты: 5 · получены за 0,0 с, страниц 1 · схема ≈ 1 278 ток. в каждом запросе
    1. list_queues — Очереди трекера  [только чтение]
       Очереди (проекты) трекера: ключ, название и описание. С этого начинают, когда неизвестно, где искать задачу.
       · без параметров
    2. list_issues — Список задач  [только чтение]
       Задачи трекера короткими карточками: ключ, тема, статус, исполнитель, срок. Свежие сверху. Отвечает на вопросы «что в работе», «что просрочено», «чем занят такой-то». Подробности одной задачи — get_is…
       · queue (string) — Ключ очереди, например «MIG». Пусто — искать во всех очередях.
       · status (string) — Статус: open (открыта), inProgress (в работе), testing (тестируется), closed (закрыта). Пу
       · assignee (string) — Исполнитель: имя как в трекере. Пусто — любой.
       · text (string) — Искать эти слова в теме и описании задачи.
       · limit (integer) — Сколько задач вернуть, 1–50.
    3. get_issue — Задача целиком  [только чтение]
       Одна задача целиком: описание, метки, сроки, последние комментарии и статусы, в которые её можно перевести из текущего.
       · key* (string) — Ключ задачи в трекере, например «MIG-2».
       · comments (integer) — Сколько последних комментариев приложить, 0–20.
    4. add_comment — Комментарий к задаче  [меняет данные]
       Добавляет комментарий к задаче трекера. Меняет данные: вызывать только по явной просьбе человека.
       · key* (string) — Ключ задачи в трекере, например «MIG-2».
       · text* (string) — Текст комментария. Пишите по делу: он останется в трекере и его прочтут коллеги.
    5. move_issue — Перевод задачи в статус  [меняет данные]
       Переводит задачу в другой статус. Меняет данные: вызывать только по явной просьбе человека. Недопустимый для текущего статуса переход трекер отклонит.
       · key* (string) — Ключ задачи в трекере, например «MIG-2».
       · status* (string) — В какой статус перевести: open, inProgress, testing, closed. Допустимые для задачи статусы
       · comment (string) — Необязательное пояснение — оно станет комментарием к задаче.
------------------------------------------------------------------------------
Подключено 1 из 1. Инструментов 5, разрешено 5; их схема ≈ 1 278 ток. на каждый запрос к модели.
Звёздочка — обязательный параметр. «*» в фильтре — любой хвост имени.
````

</details>

### 1.2. JSON-схема входа инструмента

```
$ python cli.py --память-в cli-check-memory --mcp-файл cli-check-memory/mcp-configs/tracker.json --mcp tracker --mcp-схема
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ схема напечатана
- ✓ обязательное поле объявлено
- ✓ границы значений в схеме
- ✓ код возврата 0

<details><summary>вывод</summary>

````
------------------------------------------------------------------------------
MCP: подключение к серверам из /home/gpgr/Документы/AI-Advent-Challenge/Day-17/cli-check-memory/mcp-configs/tracker.json
------------------------------------------------------------------------------
● tracker — stdio: ${PYTHON} ${PROJECT_DIR}/../../tracker_server.py
  Свой сервер вокруг API трекера (мок прогона)
  Соединение: установлено за 2,7 с · рукопожатие server/discover · протокол 2026-07-28
  Сервер: tracker 17.0 («Трекер задач миграции»)
  Возможности: tools, resources, prompts
  Инструкции сервера: Трекер задач проекта миграции ГИС газовых сетей (PHP5/CodeIgniter/MapServer → Django/GeoDjango/PostGIS/OpenLayers). Задачи лежат в очередях; у задачи …
  Инструменты: 5 · получены за 0,0 с, страниц 1 · схема ≈ 1 278 ток. в каждом запросе
    1. list_queues — Очереди трекера  [только чтение]
       Очереди (проекты) трекера: ключ, название и описание. С этого начинают, когда неизвестно, где искать задачу.
       · без параметров
       {
         "type": "object",
         "properties": {},
         "title": "list_queuesArguments"
       }
    2. list_issues — Список задач  [только чтение]
       Задачи трекера короткими карточками: ключ, тема, статус, исполнитель, срок. Свежие сверху. Отвечает на вопросы «что в работе», «что просрочено», «чем занят такой-то». Подробности одной задачи — get_is…
       · queue (string) — Ключ очереди, например «MIG». Пусто — искать во всех очередях.
       · status (string) — Статус: open (открыта), inProgress (в работе), testing (тестируется), closed (закрыта). Пу
       · assignee (string) — Исполнитель: имя как в трекере. Пусто — любой.
       · text (string) — Искать эти слова в теме и описании задачи.
       · limit (integer) — Сколько задач вернуть, 1–50.
       {
         "type": "object",
         "properties": {
           "queue": {
             "default": "",
             "description": "Ключ очереди, например «MIG». Пусто — искать во всех очередях.",
             "title": "Queue",
             "type": "string"
           },
           "status": {
             "default": "",
             "description": "Статус: open (открыта), inProgress (в работе), testing (тестируется), closed (закрыта). Пусто — любой.",
             "title": "Status",
             "type": "string"
           },
````

</details>

### 1.3. Без права записи меняющих инструментов нет

```
$ python cli.py --память-в cli-check-memory --mcp-файл cli-check-memory/mcp-configs/tracker.json --mcp tracker-readonly
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ только три
- ✓ комментария нет
- ✓ перевода статуса нет
- ✓ код возврата 0

<details><summary>вывод</summary>

````
------------------------------------------------------------------------------
MCP: подключение к серверам из /home/gpgr/Документы/AI-Advent-Challenge/Day-17/cli-check-memory/mcp-configs/tracker.json
------------------------------------------------------------------------------
● tracker-readonly — stdio: ${PYTHON} ${PROJECT_DIR}/../../tracker_server.py
  Тот же сервер без права записи — так его подключают к настоящему Трекеру
  Соединение: установлено за 4,9 с · рукопожатие server/discover · протокол 2026-07-28
  Сервер: tracker 17.0 («Трекер задач миграции»)
  Возможности: tools, resources, prompts
  Инструкции сервера: Трекер задач проекта миграции ГИС газовых сетей (PHP5/CodeIgniter/MapServer → Django/GeoDjango/PostGIS/OpenLayers). Задачи лежат в очередях; у задачи …
  Инструменты: 3 · получены за 0,0 с, страниц 1 · схема ≈ 777 ток. в каждом запросе
    1. list_queues — Очереди трекера  [только чтение]
       Очереди (проекты) трекера: ключ, название и описание. С этого начинают, когда неизвестно, где искать задачу.
       · без параметров
    2. list_issues — Список задач  [только чтение]
       Задачи трекера короткими карточками: ключ, тема, статус, исполнитель, срок. Свежие сверху. Отвечает на вопросы «что в работе», «что просрочено», «чем занят такой-то». Подробности одной задачи — get_is…
       · queue (string) — Ключ очереди, например «MIG». Пусто — искать во всех очередях.
       · status (string) — Статус: open (открыта), inProgress (в работе), testing (тестируется), closed (закрыта). Пу
       · assignee (string) — Исполнитель: имя как в трекере. Пусто — любой.
       · text (string) — Искать эти слова в теме и описании задачи.
       · limit (integer) — Сколько задач вернуть, 1–50.
    3. get_issue — Задача целиком  [только чтение]
       Одна задача целиком: описание, метки, сроки, последние комментарии и статусы, в которые её можно перевести из текущего.
       · key* (string) — Ключ задачи в трекере, например «MIG-2».
       · comments (integer) — Сколько последних комментариев приложить, 0–20.
------------------------------------------------------------------------------
Подключено 1 из 1. Инструментов 3, разрешено 3; их схема ≈ 777 ток. на каждый запрос к модели.
Звёздочка — обязательный параметр. «*» в фильтре — любой хвост имени.
````

</details>

### 1.4. Что именно досталось модели

```
$ python cli.py --память-в cli-check-memory --mcp-файл cli-check-memory/mcp-configs/tracker.json --инструменты tracker
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ имена для модели
- ✓ меняющие требуют подтверждения
- ✓ цена в каждом запросе
- ✓ код возврата 0

<details><summary>вывод</summary>

````
------------------------------------------------------------------------------
ИНСТРУМЕНТЫ MCP, доступные модели
------------------------------------------------------------------------------
  tracker__list_queues  [только чтение]
     Очереди (проекты) трекера: ключ, название и описание.
  tracker__list_issues  [только чтение]
     Задачи трекера короткими карточками: ключ, тема, статус, исполнитель, срок.
  tracker__get_issue  [только чтение]
     Одна задача целиком: описание, метки, сроки, последние комментарии и
  tracker__add_comment  [меняет данные; подтверждение человека]
     Добавляет комментарий к задаче трекера. Меняет данные: вызывать только
  tracker__move_issue  [меняет данные; подтверждение человека]
     Переводит задачу в другой статус. Меняет данные: вызывать только по
------------------------------------------------------------------------------
Серверов подключено 1 из 1. Инструментов 5 (3 читающих, 2 меняющих); их схема ≈ 1 278 ток. в каждом запросе.
````

</details>

### 1.5. Ручной вызов инструмента: данные из API

```
$ python cli.py --память-в cli-check-memory --mcp-файл cli-check-memory/mcp-configs/tracker.json --вызвать tracker__list_issues --аргументы {"status": "inProgress", "limit": 5}
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ вызов удался
- ✓ данные из трекера
- ✓ статус тот, что просили
- ✓ код возврата 0

<details><summary>вывод</summary>

````
------------------------------------------------------------------------------
tracker__list_issues(status=inProgress, limit=5) — ок, 0,2 с
------------------------------------------------------------------------------
{
  "найдено": 2,
  "показано": 2,
  "фильтр": {
    "очередь": "MIG",
    "статус": "inProgress",
    "исполнитель": "любой",
    "текст": ""
  },
  "задачи": [
    {
      "ключ": "MIG-3",
      "тема": "Заменить слой MapServer на векторные тайлы",
      "статус": "В работе",
      "статус_код": "inProgress",
      "очередь": "MIG",
      "исполнитель": "Ольга Карпова",
      "приоритет": "Критичный",
      "срок": "2026-10-10",
      "обновлена": "2026-09-21T17:20:00.000+0000"
    },
    {
      "ключ": "MIG-2",
      "тема": "Перенести модели труб и задвижек в GeoDjango",
      "статус": "В работе",
      "статус_код": "inProgress",
      "очередь": "MIG",
      "исполнитель": "Максим Васильков",
      "приоритет": "Критичный",
      "срок": "2026-09-30",
      "обновлена": "2026-09-19T08:05:00.000+0000"
    }
  ]
}
````

</details>

### 1.6. Ошибка инструмента названа и даёт код возврата

```
$ python cli.py --память-в cli-check-memory --mcp-файл cli-check-memory/mcp-configs/tracker.json --вызвать tracker__get_issue --аргументы {"key": "MIG-999"}
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ сказано, что ошибка
- ✓ причина от API
- ✓ код возврата 1

<details><summary>вывод</summary>

````
------------------------------------------------------------------------------
tracker__get_issue(key=MIG-999) — ОШИБКА, 0,2 с
------------------------------------------------------------------------------
Error executing tool get_issue: В трекере нет такого объекта (404). Issue MIG-999 does not exist or you do not have access to it
````

</details>

### 1.7. Выдуманный моделью ключ задачи не уходит в API

```
$ python cli.py --память-в cli-check-memory --mcp-файл cli-check-memory/mcp-configs/tracker.json --вызвать tracker__get_issue --аргументы {"key": "../../etc/passwd"}
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ аргумент отклонён
- ✓ код возврата 1

<details><summary>вывод</summary>

````
------------------------------------------------------------------------------
tracker__get_issue(key=../../etc/passwd) — ОШИБКА, 0,0 с
------------------------------------------------------------------------------
Error executing tool get_issue: «../../etc/passwd» не похоже на ключ задачи. Ключ пишется латиницей: очередь, дефис, номер — например «MIG-2». Список задач — list_issues.
````

</details>

### 1.8. Заявок ещё нет

```
$ python cli.py --память-в cli-check-memory --заявки
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ список пуст
- ✓ код возврата 0

<details><summary>вывод</summary>

````
------------------------------------------------------------------------------
ЗАЯВКИ НА ИЗМЕНЯЮЩИЕ ВЫЗОВЫ — 0
------------------------------------------------------------------------------
Ждущих заявок нет.
Они появляются, когда модель просит вызов, меняющий чужие данные.
````

</details>

### 2.1. Доказательный прогон: регистрация, параметры, результат

```
$ python check_tools.py --без-модели
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ инструменты зарегистрированы
- ✓ схемы корректны
- ✓ результат сверен с самим API
- ✓ выжимка короче ответа API
- ✓ сбои названы
- ✓ провалов нет
- ✓ код возврата 0

<details><summary>вывод</summary>

````
Проверка Дня 17: свой инструмент MCP вокруг API трекера
Время: 2026-09-22 23:06; модель: не вызывается
------------------------------------------------------------------------------
ЧАСТЬ 1. Инструмент зарегистрирован на сервере
------------------------------------------------------------------------------
  ✓ соединение со своим сервером за 2,5 с, протокол 2026-07-28
      сервер tracker 17.0 («Трекер задач миграции»); умеет: tools, resources, prompts
  ✓ tools/list вернул 5 инструментов: add_comment, get_issue, list_issues, list_queues, move_issue
  ✓ список совпадает с объявленным в tracker_server.py
  ✓ читающие инструменты помечены readOnlyHint: get_issue, list_issues, list_queues
  ✓ меняющие помечены как меняющие данные: add_comment, move_issue
  ✓ у каждого инструмента есть описание для модели
  ✓ без TRACKER_WRITE=1 меняющих инструментов в списке нет (3 вместо 5) — так сервер подключают к настоящему Трекеру
------------------------------------------------------------------------------
ЧАСТЬ 2. Входные параметры описаны
------------------------------------------------------------------------------
  ✓ list_queues: схема JSON Schema корректна, параметров 0, все с описанием
  ✓ list_issues: схема JSON Schema корректна, параметров 5, все с описанием
      queue (string); status (string); assignee (string); text (string); limit (integer)
  ✓ get_issue: схема JSON Schema корректна, параметров 2, все с описанием
      key* (string); comments (integer)
  ✓ add_comment: схема JSON Schema корректна, параметров 2, все с описанием
      key* (string); text* (string)
  ✓ move_issue: схема JSON Schema корректна, параметров 3, все с описанием
      key* (string); status* (string); comment (string)
  ✓ обязательные параметры объявлены: get_issue требует ['key']
  ✓ выход за границы отклонён схемой: limit=99 при пределе 50
  ✓ аргумент от модели проверяется до запроса к API: «../../etc/passwd» отклонён
------------------------------------------------------------------------------
ЧАСТЬ 3. Результат возвращается и совпадает с самим API
------------------------------------------------------------------------------
  ✓ list_issues: 4 задач совпали с прямым запросом к API (MIG-6, MIG-4, MIG-8, MIG-7)
  ✓ счётчик найденного взят из заголовка API X-Total-Count = 4
  ✓ get_issue MIG-6: ключ, тема и статус совпали с ответом API («Права доступа: районы и роли операторов…», статус Открыта)
  ✓ комментарии пришли из API: 0 из 0
  ✓ доступные статусы взяты из жизненного цикла API: inProgress
  ✓ служебных полей API в выжимке нет: statusStartTime, updatedBy, cloudUid, passportUid… 
  ✓ на списке из 8 задач выжимка короче ответа API: 2777 символов против 7839 — на 65% меньше в каждом запросе к модели
------------------------------------------------------------------------------
ЧАСТЬ 4. Агент вызывает инструмент и использует результат
````

</details>

### 2.2. Трекер не отвечает — сказано, что делать

```
$ python cli.py --память-в cli-check-memory --mcp-файл cli-check-memory/mcp-configs/tracker-down.json --вызвать tracker__list_issues
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ причина названа
- ✓ подсказка по делу
- ✓ код возврата 1

<details><summary>вывод</summary>

````
------------------------------------------------------------------------------
tracker__list_issues() — ОШИБКА, 0,1 с
------------------------------------------------------------------------------
Error executing tool list_issues: Трекер не отвечает по адресу http://127.0.0.1:51419. Если это мок из репозитория, запустите его: python tracker_api.py
````

</details>

### 3.1. Серверы описаны — видно без подключения

```
$ python cli.py --память-в cli-check-memory --mcp-серверы
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ файл серверов назван
- ✓ все пять
- ✓ GitHub без токена помечен или готов
- ✓ адрес показан как в файле
- ✓ код возврата 0

<details><summary>вывод</summary>

````
------------------------------------------------------------------------------
MCP-СЕРВЕРЫ из /home/gpgr/Документы/AI-Advent-Challenge/Day-17/mcp-servers.json
------------------------------------------------------------------------------
  tracker        stdio  готов
      ${PYTHON} ${PROJECT_DIR}/tracker_server.py
      Свой сервер вокруг API трекера задач: задачи миграции, комментарии, статусы. Работает с моком tracker_api.py
  tracker-real   stdio  готов
      ${PYTHON} ${PROJECT_DIR}/tracker_server.py
      Тот же сервер, но настоящий Яндекс.Трекер: нужны TRACKER_TOKEN и TRACKER_ORG в .env. Меняющие инструменты выключены, пока не задано TRACKER_WRITE=1
  agent-state    stdio  готов
      ${PYTHON} ${PROJECT_DIR}/mcp_server.py
      Свой сервер: задачи, инварианты, условия переходов и решения агента — только чтение
  filesystem     stdio  готов
      npx -y @modelcontextprotocol/server-filesystem ${PROJECT_DIR}/agent
      Эталонный сервер файловой системы; открыт только каталог agent/ с кодом агента
      фильтр: разрешить read_*, list_*, search_files, get_file_info, directory_tree
  everything     stdio  готов
      npx -y @modelcontextprotocol/server-everything
      Эталонный тестовый сервер: все возможности протокола на игрушечных инструментах
  deepwiki       http   готов
      https://mcp.deepwiki.com/mcp
      Документация публичных GitHub-репозиториев (django, openlayers, postgis) — без ключа
  github         http   не готов
      https://api.githubcopilot.com/mcp/readonly
      Официальный удалённый сервер GitHub в режиме только чтения; токен — в .env
      фильтр: запретить *secret*
      ! не хватает переменных GITHUB_TOKEN: задайте их в .env или в окружении
------------------------------------------------------------------------------
Подключиться и получить инструменты: python cli.py --mcp [СЕРВЕР]
````

</details>

### 3.2. Соединение со своим сервером (stdio)

```
$ python cli.py --память-в cli-check-memory --mcp agent-state
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ соединение установлено
- ✓ названы способ рукопожатия и протокол
- ✓ сервер назвал себя
- ✓ шесть инструментов по именам
- ✓ все шесть — только чтение
- ✓ обязательный параметр со звёздочкой
- ✓ итог
- ✓ код возврата 0

<details><summary>вывод</summary>

````
------------------------------------------------------------------------------
MCP: подключение к серверам из /home/gpgr/Документы/AI-Advent-Challenge/Day-17/mcp-servers.json
------------------------------------------------------------------------------
● agent-state — stdio: ${PYTHON} ${PROJECT_DIR}/mcp_server.py
  Свой сервер: задачи, инварианты, условия переходов и решения агента — только чтение
  Соединение: установлено за 1,5 с · рукопожатие server/discover · протокол 2026-07-28
  Сервер: agent-state 16.0 («Состояние агента миграции»)
  Возможности: tools, resources, prompts
  Инструкции сервера: Сервер агента миграции ГИС газовых сетей (PHP5/CodeIgniter/MapServer → Django/GeoDjango/PostGIS/OpenLayers). Отдаёт состояние агента только на чтение:…
  Инструменты: 6 · получены за 0,0 с, страниц 1 · схема ≈ 1 059 ток. в каждом запросе
    1. list_users — Пользователи агента  [только чтение]
       Пользователи, у которых есть долговременная память: профиль, решения, условия.
       · без параметров
    2. list_tasks — Задачи рабочей памяти  [только чтение]
       Все задачи агента со сводкой: стадия, шаг сценария, пауза и чего ждёт задача. Свежие сверху. Задача живёт в рабочей памяти, пока не завершена.
       · без параметров
    3. get_task — Состояние задачи  [только чтение]
       Полное состояние задачи: стадия, план, шаги, пауза, подпись под планом, отчёт валидации, история переходов и — по каждой стадии — открыт ли туда переход и каких условий не хватает.
       · task_id* (string) — Идентификатор задачи из list_tasks, например «перенос-моделей».
       · user (string) — Имя пользователя агента (каталог memory/long/<имя>). По умолчанию «инженер».
    4. list_invariants — Инварианты  [только чтение]
       Инварианты проекта и личные инварианты пользователя: правило, вид, почему и что делать вместо. Нарушать их агенту нельзя ни в каком ответе.
       · user (string) — Имя пользователя агента (каталог memory/long/<имя>). По умолчанию «инженер».
    5. list_transition_conditions — Условия переходов  [только чтение]
       Условия, без которых задача не перейдёт со стадии на стадию: базовые из кода и личные пользователя.
       · user (string) — Имя пользователя агента (каталог memory/long/<имя>). По умолчанию «инженер».
    6. list_decisions — Журнал решений  [только чтение]
       Последние решения из журнала пользователя: что решили, почему и какие были альтернативы.
       · user (string) — Имя пользователя агента (каталог memory/long/<имя>). По умолчанию «инженер».
       · limit (integer) — Сколько последних решений вернуть, 1–100.
------------------------------------------------------------------------------
Подключено 1 из 1. Инструментов 6, разрешено 6; их схема ≈ 1 059 ток. на каждый запрос к модели.
Звёздочка — обязательный параметр. «*» в фильтре — любой хвост имени.
````

</details>

### 3.3. JSON-схема входа по ключу

```
$ python cli.py --память-в cli-check-memory --mcp agent-state --mcp-схема
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ схема напечатана
- ✓ обязательные поля в схеме
- ✓ код возврата 0

<details><summary>вывод</summary>

````
------------------------------------------------------------------------------
MCP: подключение к серверам из /home/gpgr/Документы/AI-Advent-Challenge/Day-17/mcp-servers.json
------------------------------------------------------------------------------
● agent-state — stdio: ${PYTHON} ${PROJECT_DIR}/mcp_server.py
  Свой сервер: задачи, инварианты, условия переходов и решения агента — только чтение
  Соединение: установлено за 1,6 с · рукопожатие server/discover · протокол 2026-07-28
  Сервер: agent-state 16.0 («Состояние агента миграции»)
  Возможности: tools, resources, prompts
  Инструкции сервера: Сервер агента миграции ГИС газовых сетей (PHP5/CodeIgniter/MapServer → Django/GeoDjango/PostGIS/OpenLayers). Отдаёт состояние агента только на чтение:…
  Инструменты: 6 · получены за 0,0 с, страниц 1 · схема ≈ 1 059 ток. в каждом запросе
    1. list_users — Пользователи агента  [только чтение]
       Пользователи, у которых есть долговременная память: профиль, решения, условия.
       · без параметров
       {
         "type": "object",
         "properties": {},
         "title": "list_usersArguments"
       }
    2. list_tasks — Задачи рабочей памяти  [только чтение]
       Все задачи агента со сводкой: стадия, шаг сценария, пауза и чего ждёт задача. Свежие сверху. Задача живёт в рабочей памяти, пока не завершена.
       · без параметров
       {
         "type": "object",
         "properties": {},
         "title": "list_tasksArguments"
       }
    3. get_task — Состояние задачи  [только чтение]
       Полное состояние задачи: стадия, план, шаги, пауза, подпись под планом, отчёт валидации, история переходов и — по каждой стадии — открыт ли туда переход и каких условий не хватает.
       · task_id* (string) — Идентификатор задачи из list_tasks, например «перенос-моделей».
       · user (string) — Имя пользователя агента (каталог memory/long/<имя>). По умолчанию «инженер».
       {
         "type": "object",
         "properties": {
           "task_id": {
             "description": "Идентификатор задачи из list_tasks, например «перенос-моделей».",
             "title": "Task Id",
             "type": "string"
           },
           "user": {
             "default": "инженер",
````

</details>

### 3.4. Эталонный сервер из npm (stdio через npx), фильтр

```
$ python cli.py --память-в cli-check-memory --mcp filesystem
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ соединение установлено
- ✓ классическое рукопожатие
- ✓ сервер назвал себя
- ✓ фильтр закрыл четыре
- ✓ закрытый показан с причиной
- ✓ пометки сервера видны
- ✓ код возврата 0

<details><summary>вывод</summary>

````
------------------------------------------------------------------------------
MCP: подключение к серверам из /home/gpgr/Документы/AI-Advent-Challenge/Day-17/mcp-servers.json
------------------------------------------------------------------------------
● filesystem — stdio: npx -y @modelcontextprotocol/server-filesystem ${PROJECT_DIR}/agent
  Эталонный сервер файловой системы; открыт только каталог agent/ с кодом агента
  Соединение: установлено за 2,4 с · рукопожатие initialize · протокол 2025-11-25
  Сервер: secure-filesystem-server 0.2.0
  Возможности: tools
  Инструменты: 14 (разрешено 10, закрыто 4) · получены за 0,0 с, страниц 1 · схема ≈ 2 000 ток. в каждом запросе
    1. read_file — Read File (Deprecated)  [только чтение]
       Read the complete contents of a file as text. DEPRECATED: Use read_text_file instead.
       · path* (string)
       · tail (number) — If provided, returns only the last N lines of the file
       · head (number) — If provided, returns only the first N lines of the file
    2. read_text_file — Read Text File  [только чтение]
       Read the complete contents of a file from the file system as text. Handles various text encodings and provides detailed error messages if the file cannot be read. Use this tool when you need to examin…
       · path* (string)
       · tail (number) — If provided, returns only the last N lines of the file
       · head (number) — If provided, returns only the first N lines of the file
    3. read_media_file — Read Media File  [только чтение]
       Read a file and return it as a base64-encoded content block with its MIME type. Image and audio files are returned as image/audio content; any other file type is returned as an embedded resource. Only…
       · path* (string)
    4. read_multiple_files — Read Multiple Files  [только чтение]
       Read the contents of multiple files simultaneously. This is more efficient than reading files one by one when you need to analyze or compare multiple files. Each file's content is returned with its pa…
       · paths* (array<string>) — Array of file paths to read. Each path must be a string pointing to a valid file within al
    5. write_file — Write File  [может удалять; ЗАКРЫТ: не входит в «разрешить»]
       Create a new file or completely overwrite an existing file with new content. Use with caution as it will overwrite existing files without warning. Handles text content with proper encoding. Only works…
       · path* (string)
       · content* (string)
    6. edit_file — Edit File  [может удалять; ЗАКРЫТ: не входит в «разрешить»]
       Make line-based edits to a text file. Each edit replaces exact line sequences with new content. Returns a git-style diff showing the changes made. Only works within allowed directories.
       · path* (string)
       · edits* (array<object>)
       · dryRun (boolean) — Preview changes using git-style diff format
    7. create_directory — Create Directory  [меняет данные; ЗАКРЫТ: не входит в «разрешить»]
       Create a new directory or ensure a directory exists. Can create multiple nested directories in one operation. If the directory already exists, this operation will succeed silently. Perfect for setting…
       · path* (string)
    8. list_directory — List Directory  [только чтение]
       Get a detailed listing of all files and directories in a specified path. Results clearly distinguish between files and directories with [FILE] and [DIR] prefixes. This tool is essential for understand…
       · path* (string)
````

</details>

### 3.5. Тестовый сервер со всеми возможностями протокола

```
$ python cli.py --память-в cli-check-memory --mcp everything
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ соединение установлено
- ✓ заявлены возможности
- ✓ тринадцать инструментов
- ✓ код возврата 0

<details><summary>вывод</summary>

````
------------------------------------------------------------------------------
MCP: подключение к серверам из /home/gpgr/Документы/AI-Advent-Challenge/Day-17/mcp-servers.json
------------------------------------------------------------------------------
● everything — stdio: npx -y @modelcontextprotocol/server-everything
  Эталонный тестовый сервер: все возможности протокола на игрушечных инструментах
  Соединение: установлено за 3,4 с · рукопожатие initialize · протокол 2025-11-25
  Сервер: mcp-servers/everything 2.0.0 («Everything Reference Server»)
  Возможности: tools, resources, prompts, logging, completions, tasks
  Инструкции сервера: # Everything Server – Server Instructions
  Инструменты: 13 · получены за 0,0 с, страниц 1 · схема ≈ 2 113 ток. в каждом запросе
    1. echo — Echo Tool  [только чтение]
       Echoes back the input string
       · message* (string) — Message to echo
    2. get-annotated-message — Get Annotated Message Tool  [только чтение]
       Demonstrates how annotations can be used to provide metadata about content.
       · messageType* (string) — Type of message to demonstrate different annotation patterns
       · includeImage (boolean) — Whether to include an example image
    3. get-env — Print Environment Tool  [только чтение]
       Returns all environment variables, helpful for debugging MCP server configuration
       · без параметров
    4. get-resource-links — Get Resource Links Tool  [только чтение]
       Returns up to ten resource links that reference different types of resources
       · count (number) — Number of resource links to return (1-10)
    5. get-resource-reference — Get Resource Reference Tool  [только чтение]
       Returns a resource reference that can be used by MCP clients
       · resourceType (string)
       · resourceId (number) — ID of the text resource to fetch
    6. get-structured-content — Get Structured Content Tool  [только чтение]
       Returns structured content along with an output schema for client data validation
       · location* (string) — Choose city
    7. get-sum — Get Sum Tool  [только чтение]
       Returns the sum of two numbers
       · a* (number) — First number
       · b* (number) — Second number
    8. get-tiny-image — Get Tiny Image Tool  [только чтение]
       Returns a tiny MCP logo image.
       · без параметров
    9. gzip-file-as-resource — GZip File as Resource Tool  [меняет данные]
       Compresses a single file using gzip compression. Depending upon the selected output type, returns either the compressed data as a gzipped resource or a resource link, allowing it to be downloaded in a…
       · name (string) — Name of the output file
````

</details>

### 3.6. Удалённый сервер по Streamable HTTP

```
$ python cli.py --память-в cli-check-memory --mcp deepwiki
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ транспорт http
- ✓ сервер назвал себя
- ✓ три инструмента
- ✓ пометок нет — так и сказано
- ✓ код возврата 0

<details><summary>вывод</summary>

````
------------------------------------------------------------------------------
MCP: подключение к серверам из /home/gpgr/Документы/AI-Advent-Challenge/Day-17/mcp-servers.json
------------------------------------------------------------------------------
● deepwiki — http: https://mcp.deepwiki.com/mcp
  Документация публичных GitHub-репозиториев (django, openlayers, postgis) — без ключа
  Соединение: установлено за 1,4 с · рукопожатие initialize · протокол 2025-11-25
  Сервер: DeepWiki 2.14.3
  Возможности: tools, resources, prompts
  Инструкции сервера: DeepWiki MCP provides AI-powered documentation for GitHub repositories.
  Инструменты: 3 · получены за 2,1 с, страниц 1 · схема ≈ 453 ток. в каждом запросе
    1. ask_wiki_question  [не заявлено]
       Ask any question about a GitHub repository's codebase and get an AI-powered answer grounded in its DeepWiki.
       · repoName* (string | array<string>) — GitHub repository or list of repositories (max 10) in owner/repo format.
       · question* (string) — The question to ask about the repository.
    2. read_wiki_contents  [не заявлено]
       View documentation about a GitHub repository.
       · repoName* (string) — GitHub repository in owner/repo format (e.g. "facebook/react").
    3. read_wiki_structure  [не заявлено]
       Get a list of documentation topics for a GitHub repository.
       · repoName* (string) — GitHub repository in owner/repo format (e.g. "facebook/react").
------------------------------------------------------------------------------
Подключено 1 из 1. Инструментов 3, разрешено 3; их схема ≈ 453 ток. на каждый запрос к модели.
Звёздочка — обязательный параметр. «*» в фильтре — любой хвост имени.
````

</details>

### 3.7. Все серверы разом

```
$ python cli.py --память-в cli-check-memory --mcp
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ итог по серверам
- ✓ свой сервер трекера в списке
- ✓ цена схемы посчитана

<details><summary>вывод</summary>

````
------------------------------------------------------------------------------
MCP: подключение к серверам из /home/gpgr/Документы/AI-Advent-Challenge/Day-17/mcp-servers.json
------------------------------------------------------------------------------
● tracker — stdio: ${PYTHON} ${PROJECT_DIR}/tracker_server.py
  Свой сервер вокруг API трекера задач: задачи миграции, комментарии, статусы. Работает с моком tracker_api.py
  Соединение: установлено за 5,3 с · рукопожатие server/discover · протокол 2026-07-28
  Сервер: tracker 17.0 («Трекер задач миграции»)
  Возможности: tools, resources, prompts
  Инструкции сервера: Трекер задач проекта миграции ГИС газовых сетей (PHP5/CodeIgniter/MapServer → Django/GeoDjango/PostGIS/OpenLayers). Задачи лежат в очередях; у задачи …
  Инструменты: 5 · получены за 0,0 с, страниц 1 · схема ≈ 1 278 ток. в каждом запросе
    1. list_queues — Очереди трекера  [только чтение]
       Очереди (проекты) трекера: ключ, название и описание. С этого начинают, когда неизвестно, где искать задачу.
       · без параметров
    2. list_issues — Список задач  [только чтение]
       Задачи трекера короткими карточками: ключ, тема, статус, исполнитель, срок. Свежие сверху. Отвечает на вопросы «что в работе», «что просрочено», «чем занят такой-то». Подробности одной задачи — get_is…
       · queue (string) — Ключ очереди, например «MIG». Пусто — искать во всех очередях.
       · status (string) — Статус: open (открыта), inProgress (в работе), testing (тестируется), closed (закрыта). Пу
       · assignee (string) — Исполнитель: имя как в трекере. Пусто — любой.
       · text (string) — Искать эти слова в теме и описании задачи.
       · limit (integer) — Сколько задач вернуть, 1–50.
    3. get_issue — Задача целиком  [только чтение]
       Одна задача целиком: описание, метки, сроки, последние комментарии и статусы, в которые её можно перевести из текущего.
       · key* (string) — Ключ задачи в трекере, например «MIG-2».
       · comments (integer) — Сколько последних комментариев приложить, 0–20.
    4. add_comment — Комментарий к задаче  [меняет данные]
       Добавляет комментарий к задаче трекера. Меняет данные: вызывать только по явной просьбе человека.
       · key* (string) — Ключ задачи в трекере, например «MIG-2».
       · text* (string) — Текст комментария. Пишите по делу: он останется в трекере и его прочтут коллеги.
    5. move_issue — Перевод задачи в статус  [меняет данные]
       Переводит задачу в другой статус. Меняет данные: вызывать только по явной просьбе человека. Недопустимый для текущего статуса переход трекер отклонит.
       · key* (string) — Ключ задачи в трекере, например «MIG-2».
       · status* (string) — В какой статус перевести: open, inProgress, testing, closed. Допустимые для задачи статусы
       · comment (string) — Необязательное пояснение — оно станет комментарием к задаче.
------------------------------------------------------------------------------
● tracker-real — stdio: ${PYTHON} ${PROJECT_DIR}/tracker_server.py
  Тот же сервер, но настоящий Яндекс.Трекер: нужны TRACKER_TOKEN и TRACKER_ORG в .env. Меняющие инструменты выключены, пока не задано TRACKER_WRITE=1
  Соединение: установлено за 4,0 с · рукопожатие server/discover · протокол 2026-07-28
  Сервер: tracker 17.0 («Трекер задач миграции»)
  Возможности: tools, resources, prompts
  Инструкции сервера: Трекер задач проекта миграции ГИС газовых сетей (PHP5/CodeIgniter/MapServer → Django/GeoDjango/PostGIS/OpenLayers). Задачи лежат в очередях; у задачи …
````

</details>

### 3.8. Список корректен: сверка без SDK, схемы, имена

```
$ python check_mcp.py
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ соединения установлены
- ✓ сверка с сырым JSON-RPC совпала
- ✓ схемы корректны
- ✓ свой сервер — ровно объявленное
- ✓ провалов нет
- ✓ код возврата 0

<details><summary>вывод</summary>

````
Проверка Дня 16: MCP. Серверы из /home/gpgr/Документы/AI-Advent-Challenge/Day-17/mcp-servers.json
Время: 2026-09-22 23:07; серверов: 7
------------------------------------------------------------------------------
ЧАСТЬ 1. Соединение устанавливается
------------------------------------------------------------------------------
  ✓ tracker (stdio) — соединение за 4,7 с, server/discover, протокол 2026-07-28
      сервер tracker 17.0 («Трекер задач миграции»); умеет: tools, resources, prompts
  ✓ tracker-real (stdio) — соединение за 3,3 с, server/discover, протокол 2026-07-28
      сервер tracker 17.0 («Трекер задач миграции»); умеет: tools, resources, prompts
  ✓ agent-state (stdio) — соединение за 5,3 с, server/discover, протокол 2026-07-28
      сервер agent-state 16.0 («Состояние агента миграции»); умеет: tools, resources, prompts
  ✓ filesystem (stdio) — соединение за 7,0 с, initialize, протокол 2025-11-25
      сервер secure-filesystem-server 0.2.0; умеет: tools
  ✓ everything (stdio) — соединение за 6,6 с, initialize, протокол 2025-11-25
      сервер mcp-servers/everything 2.0.0 («Everything Reference Server»); умеет: tools, resources, prompts, logging, completions, tasks
  ✓ deepwiki (http) — соединение за 1,9 с, initialize, протокол 2025-11-25
      сервер DeepWiki 2.14.3; умеет: tools, resources, prompts
  ○ github (http) — пропущен: не хватает переменных GITHUB_TOKEN: задайте их в .env или в окружении
------------------------------------------------------------------------------
ЧАСТЬ 2. Список инструментов возвращается корректно
------------------------------------------------------------------------------
  tracker: инструментов 5, страниц 1, получены за 0,0 с
  ✓ сверка без SDK (сырой JSON-RPC, initialize 2025-06-18): 5 инструментов, имена и схемы совпадают
  ✓ каждая inputSchema — корректная JSON Schema типа object
  ✓ имена инструментов уникальны
  tracker-real: инструментов 3, страниц 1, получены за 0,0 с
  ✓ сверка без SDK (сырой JSON-RPC, initialize 2025-06-18): 3 инструментов, имена и схемы совпадают
  ✓ каждая inputSchema — корректная JSON Schema типа object
  ✓ имена инструментов уникальны
  agent-state: инструментов 6, страниц 1, получены за 0,0 с
  ✓ сверка без SDK (сырой JSON-RPC, initialize 2025-06-18): 6 инструментов, имена и схемы совпадают
  ✓ каждая inputSchema — корректная JSON Schema типа object
  ✓ имена инструментов уникальны
  ✓ совпадает с объявленным в mcp_server.py: get_task, list_decisions, list_invariants, list_tasks, list_transition_conditions, list_users
  filesystem: инструментов 14, страниц 1, получены за 0,0 с
  ✓ сверка без SDK (сырой JSON-RPC, initialize 2025-06-18): 14 инструментов, имена и схемы совпадают
  ✓ каждая inputSchema — корректная JSON Schema типа object
  ✓ имена инструментов уникальны
      фильтр закрыл: write_file, edit_file, create_directory, move_file
  everything: инструментов 13, страниц 1, получены за 0,0 с
````

</details>

### 3.9. Свой сервер по Streamable HTTP

```
$ python cli.py --память-в cli-check-memory --mcp-файл cli-check-memory/mcp-configs/own-http.json --mcp
```

Во время шага работал сервер: `python mcp_server.py --http 40413 --память-в cli-check-memory`

- ✓ команда завершилась сама, не открыв диалог
- ✓ транспорт http
- ✓ сервер назвал себя
- ✓ шесть инструментов
- ✓ итог
- ✓ код возврата 0

<details><summary>вывод</summary>

````
------------------------------------------------------------------------------
MCP: подключение к серверам из /home/gpgr/Документы/AI-Advent-Challenge/Day-17/cli-check-memory/mcp-configs/own-http.json
------------------------------------------------------------------------------
● agent-http — http: http://127.0.0.1:40413/mcp
  Соединение: установлено за 0,1 с · рукопожатие server/discover · протокол 2026-07-28
  Сервер: agent-state 16.0 («Состояние агента миграции»)
  Возможности: tools, resources, prompts
  Инструкции сервера: Сервер агента миграции ГИС газовых сетей (PHP5/CodeIgniter/MapServer → Django/GeoDjango/PostGIS/OpenLayers). Отдаёт состояние агента только на чтение:…
  Инструменты: 6 · получены за 0,0 с, страниц 1 · схема ≈ 1 058 ток. в каждом запросе
    1. list_users — Пользователи агента  [только чтение]
       Пользователи, у которых есть долговременная память: профиль, решения, условия.
       · без параметров
    2. list_tasks — Задачи рабочей памяти  [только чтение]
       Все задачи агента со сводкой: стадия, шаг сценария, пауза и чего ждёт задача. Свежие сверху. Задача живёт в рабочей памяти, пока не завершена.
       · без параметров
    3. get_task — Состояние задачи  [только чтение]
       Полное состояние задачи: стадия, план, шаги, пауза, подпись под планом, отчёт валидации, история переходов и — по каждой стадии — открыт ли туда переход и каких условий не хватает.
       · task_id* (string) — Идентификатор задачи из list_tasks, например «перенос-моделей».
       · user (string) — Имя пользователя агента (каталог memory/long/<имя>). По умолчанию «инженер».
    4. list_invariants — Инварианты  [только чтение]
       Инварианты проекта и личные инварианты пользователя: правило, вид, почему и что делать вместо. Нарушать их агенту нельзя ни в каком ответе.
       · user (string) — Имя пользователя агента (каталог memory/long/<имя>). По умолчанию «инженер».
    5. list_transition_conditions — Условия переходов  [только чтение]
       Условия, без которых задача не перейдёт со стадии на стадию: базовые из кода и личные пользователя.
       · user (string) — Имя пользователя агента (каталог memory/long/<имя>). По умолчанию «инженер».
    6. list_decisions — Журнал решений  [только чтение]
       Последние решения из журнала пользователя: что решили, почему и какие были альтернативы.
       · user (string) — Имя пользователя агента (каталог memory/long/<имя>). По умолчанию «инженер».
       · limit (integer) — Сколько последних решений вернуть, 1–100.
------------------------------------------------------------------------------
Подключено 1 из 1. Инструментов 6, разрешено 6; их схема ≈ 1 058 ток. на каждый запрос к модели.
Звёздочка — обязательный параметр. «*» в фильтре — любой хвост имени.
````

</details>

### 4.1. Сбои MCP названы, консоль не виснет

```
$ python cli.py --память-в cli-check-memory --mcp-файл cli-check-memory/mcp-configs/failures.json --mcp
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ нет программы
- ✓ закрытый порт
- ✓ молчащий сервер
- ✓ негодный токен
- ✓ подсказки есть
- ✓ итог
- ✓ токен не показан
- ✓ код возврата 1

<details><summary>вывод</summary>

````
------------------------------------------------------------------------------
MCP: подключение к серверам из /home/gpgr/Документы/AI-Advent-Challenge/Day-17/cli-check-memory/mcp-configs/failures.json
------------------------------------------------------------------------------
✗ broken — stdio: no-such-mcp-server
  Соединение НЕ установлено (этап «запуск»): не найдена команда «no-such-mcp-server»
  Подсказка: Проверьте «command» в mcp-servers.json и что программа установлена.
------------------------------------------------------------------------------
✗ closed-port — http: http://127.0.0.1:51433/mcp
  Соединение НЕ установлено (этап «рукопожатие»): нет соединения с 127.0.0.1:51433
  Подсказка: Сервер не запущен, адрес неверен или нет сети.
------------------------------------------------------------------------------
✗ silent — stdio: /home/gpgr/Документы/AI-Advent-Challenge/Day-17/.venv/bin/python -c 'import time; time.sleep(60)'
  Соединение НЕ установлено (этап «рукопожатие»): сервер не ответил за 3 с
  Подсказка: Сервер запущен, но молчит. Увеличьте «таймаут» или проверьте сервер.
------------------------------------------------------------------------------
✗ github — http: https://api.githubcopilot.com/mcp/readonly
  Соединение НЕ установлено (этап «рукопожатие»): сервер отклонил авторизацию (HTTP 401: Token is not authorized)
  Подсказка: Проверьте токен в .env: он задан, не истёк и выдан с нужными правами.
------------------------------------------------------------------------------
Подключено 0 из 4, сбоев 4. Инструментов 0, разрешено 0; их схема ≈ 0 ток. на каждый запрос к модели.
Звёздочка — обязательный параметр. «*» в фильтре — любой хвост имени.
````

</details>

### 4.2. Неизвестный сервер

```
$ python cli.py --память-в cli-check-memory --mcp нет-такого
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ сказано, какого нет
- ✓ перечислены известные
- ✓ код возврата 1

<details><summary>вывод</summary>

````
Ошибка: Сервера «нет-такого» нет в /home/gpgr/Документы/AI-Advent-Challenge/Day-17/mcp-servers.json. Есть: tracker, tracker-real, agent-state, filesystem, everything, deepwiki, github.
````

</details>

### 4.3. Битый файл серверов

```
$ python cli.py --память-в cli-check-memory --mcp-файл cli-check-memory/mcp-configs/broken.json --mcp-серверы
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ ошибка названа
- ✓ сказано, что не JSON
- ✓ код возврата 1

<details><summary>вывод</summary>

````
Ошибка в файле серверов: Файл «/home/gpgr/Документы/AI-Advent-Challenge/Day-17/cli-check-memory/mcp-configs/broken.json» — не JSON: Expecting property name enclosed in double quotes: line 1 column 18 (char 17)
````

</details>

### 5.1. Три слоя памяти (День 11)

```
$ python cli.py --память-в cli-check-memory --память
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ заголовок
- ✓ все три слоя
- ✓ код возврата 0

<details><summary>вывод</summary>

````
------------------------------------------------------------------------------
СЛОИ ПАМЯТИ
------------------------------------------------------------------------------
  краткосрочная   реплик 0, символов 0  (сессия «основная»)
  рабочая         задач в работе: 0
  долговременная  профиль: без имени, на вы, подробно, код обязательно, списки
                  записей 16, инвариантов 0, сценариев 3, решений 2, знаний 7
------------------------------------------------------------------------------
Включены сейчас: долговременная, краткосрочная, рабочая
````

</details>

### 5.2. Заготовки профиля (День 12)

```
$ python cli.py --память-в cli-check-memory --заготовки
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ заголовок
- ✓ есть тимлид
- ✓ код возврата 0

<details><summary>вывод</summary>

````
------------------------------------------------------------------------------
ГОТОВЫЕ ПРОФИЛИ
------------------------------------------------------------------------------
  инженер    Инженер миграции: подробно, код целиком, привязка к legacy-компонентам.
             без имени, на вы, подробно, код обязательно, списки
  тимлид     Тимлид: коротко, без кода, с рисками и трудоёмкостью, на «ты».
             Максим, на ты, кратко, код по запросу, списки
  новичок    Новичок в команде: пояснять термины, пошагово, средней длины.
             Аня, на ты, средне, код обязательно, списки
  менеджер   Менеджер проекта: без кода и технических деталей, таблицами, формально.
             Ирина Сергеевна, на вы, кратко, код не нужен, таблицы
------------------------------------------------------------------------------
Взять: python cli.py --кто тимлид --заготовка тимлид
````

</details>

### 5.3. Профиль из заготовки (День 12)

```
$ python cli.py --память-в cli-check-memory --кто тимлид --заготовка тимлид
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ профиль взят
- ✓ код возврата 0

<details><summary>вывод</summary>

````
Профиль «тимлид» взят из заготовки «тимлид»: Максим, на ты, кратко, код по запросу, списки
````

</details>

### 5.4. Инварианты на месте (День 14)

```
$ python cli.py --память-в cli-check-memory --инварианты
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ их шесть
- ✓ код возврата 0

<details><summary>вывод</summary>

````
------------------------------------------------------------------------------
ИНВАРИАНТЫ — 6
------------------------------------------------------------------------------

СТЕК — ограничение по стеку
  [стек-бэкенд]  проектный
     Backend — только Django + GeoDjango; посторонние фреймворки не предлагать.
     проверка: поиск слов в ответе (код)
     ищем: laravel, symfony, fastapi, express, nestjs, yii
     почему: выбран за нативную поддержку геометрии на уровне ORM, встроенную админку под справочники и самый зрелый геостек
     вместо: Django 5.x + GeoDjango (django.contrib.gis), представления на DRF
     источник: журнал решений №1
  [бд]  проектный
     База данных — только PostgreSQL с PostGIS; решений под другие СУБД не предлагать.
     проверка: поиск слов в ответе (код)
     ищем: mysql, mariadb, mongodb, sqlite, oracle, mssql
     почему: вся геометрия и пространственные индексы уже в PostGIS, перенос означал бы переписывание запросов и потерю пространственных типов
     вместо: PostgreSQL 17 + PostGIS 3.6
     источник: журнал решений №1

АРХИТЕКТУРА — выбранная архитектура
  [legacy-не-развиваем]  проектный
     Компоненты старой системы можно упоминать для соответствия, но писать на них новый код нельзя.
     проверка: поиск вызовов API в блоках кода (код)
     ищем: <?php, $this->load->, $this->db->, R::dispense, R::store, CI_Controller
     почему: старый стек вне поддержки с Debian Jessie; каждая строка на нём — долг, который придётся переписывать
     вместо: то же самое на Django ORM или GeoDjango
  [внешняя-совместимость]  проектный
     Внешняя совместимость по WMS/WFS должна сохраняться: этими протоколами пользуются внешние потребители и, вероятно, сама 1С.
     проверка: самоотчёт агента и суждение модели
     почему: потребителей за пределами команды мы не контролируем и не можем обязать переписать их интеграции
     вместо: GeoServer отдаёт WMS/WFS-T, векторные тайлы добавляются рядом, а не вместо

БИЗНЕС-ПРАВИЛО — бизнес-правило
  [1С-источник-истины]  проектный
     1С остаётся источником истины для бизнес-данных объектов сети: писать бизнес-объекты напрямую в gisdata, минуя 1С, нельзя.
     проверка: самоотчёт агента и суждение модели
     почему: учёт объектов сети ведётся в 1С, и расхождение между ней и ГИС означает, что диспетчер видит одно, а бухгалтерия другое
     вместо: запись через методы ЗаписатьОбъектВГИС / УдалитьОбъектИзГИС, ГИС остаётся потребителем

````

</details>

### 5.5. Базовые условия переходов (День 15)

```
$ python cli.py --память-в cli-check-memory --условия
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ их четыре
- ✓ план-утверждён на месте
- ✓ код возврата 0

<details><summary>вывод</summary>

````
------------------------------------------------------------------------------
УСЛОВИЯ ПЕРЕХОДОВ (4)
------------------------------------------------------------------------------
  план-утверждён             planning → execution   план-утверждён         базовый
      Нельзя переходить к реализации, пока план не утверждён человеком.
      почему: Реализация без утверждённого плана — работа наугад: с планом потом сверяют результат, и если плана не было, сверять не с чем.
      чтобы открыть: составьте план (в консоли --план, на странице кнопка «составить план») и утвердите его — --утвердить-план или кнопка «утвердить»
  шаги-доведены             execution → validation  шаги-пройдены          базовый
      Нельзя отдавать на проверку работу, в которой остались непройденные шаги.
      почему: Проверка сверяет результат со всеми шагами плана. Половина работы даст половину замечаний, и они устареют, как только доделают остальное.
      чтобы открыть: доведите оставшиеся шаги — или, если план оказался негодным, верните задачу в планирование: переход execution → planning открыт
  валидация-пройдена       validation → done        валидация-пройдена     базовый
      Нельзя завершать задачу без пройденной проверки.
      почему: Финал без проверки — это обещание, а не результат. Отчёт проверки и есть то единственное, чем «готово» отличается от «кажется, готово».
      чтобы открыть: соберите отчёт проверки (--валидация, на странице кнопка «проверить») и устраните красные пункты
  нет-открытых-вопросов             * → *           нет-открытых-вопросов  базовый
      Нельзя менять стадию, пока задача ждёт ответа человека.
      почему: Вопрос задан на прежней стадии и к новой уже не относится: сменив стадию, его теряют вместе с причиной, по которой он возник.
      чтобы открыть: ответьте на вопрос (--ответ «…») — задача снимется с паузы сама
------------------------------------------------------------------------------
Виды проверок:
  план-утверждён           план составлен и подписан человеком
  план-не-пуст             в плане не меньше указанного числа пунктов
  шаги-пройдены            все шаги задачи доведены до конца
  валидация-пройдена       отчёт проверки собран и в нём нет красных пунктов
  есть-в-собранном         в собранных данных есть запись с указанным ключом
  нет-открытых-вопросов    задача не ждёт ответа человека
------------------------------------------------------------------------------
Базовые условия заданы кодом и не снимаются. Своё: --условие КОД --откуда validation --куда done --проверка есть-в-собранном --значение ссылка --правило «…»
````

</details>

### 5.6. Задача заводится (Дни 13, 15)

```
$ python cli.py --память-в cli-check-memory --новая-задача регрессия-инструменты --название регрессия после MCP
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ заведена в planning
- ✓ код возврата 0

<details><summary>вывод</summary>

````
Задача «регрессия-инструменты» заведена, стадия planning.
````

</details>

### 5.7. Прыжок через этап отклонён (День 15)

```
$ python cli.py --память-в cli-check-memory --задача регрессия-инструменты --стадия done
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ отказ по графу
- ✓ законный маршрут
- ✓ код возврата 1

<details><summary>вывод</summary>

````
Задача «регрессия-инструменты», стадия planning (планирование).
Переход «планирование» → «готово» не выполнен: в жизненном цикле нет такого перехода.

Из стадии «планирование» ведут только переходы: execution.

Законный маршрут до цели: планирование → исполнение → проверка → готово.
Ближайший шаг маршрута — «исполнение» (execution), но и он закрыт: плана нет — задача не проходила стадию планирования.
  Чтобы открыть его: составьте план (в консоли --план, на странице кнопка «составить план») и утвердите его — --утвердить-план или кнопка «утвердить».

Стадию задачи меняет код по условию, а не формулировка ответа: даже если в ответе написано «готово», состояние останется прежним, пока условие не выполнено.
````

</details>

### 5.8. Пауза поверх этапа (День 13)

```
$ python cli.py --память-в cli-check-memory --задача регрессия-инструменты --пауза
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ задача остановлена
- ✓ код возврата 0

<details><summary>вывод</summary>

````
Задача «регрессия-инструменты», стадия planning (планирование).
Задача «регрессия-инструменты» остановлена. этап планирование; на паузе; ждём: можно продолжать
Текущий шаг доведён до конца — ответ модели, за который уже заплачено,
выбрасывать незачем. Продолжить: --продолжить.
````

</details>

### 5.9. Пауза видна другому процессу (День 13)

```
$ python cli.py --память-в cli-check-memory --задача регрессия-инструменты --состояние
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ НА ПАУЗЕ
- ✓ по команде
- ✓ код возврата 0

<details><summary>вывод</summary>

````
Задача «регрессия-инструменты», стадия planning (планирование).
------------------------------------------------------------------------------
ЗАДАЧА «регрессия-инструменты» — регрессия после MCP
------------------------------------------------------------------------------
  этап       planning (планирование), НА ПАУЗЕ
             причина остановки: по команде
             дальше можно: execution
  шаг        шагов нет — задача ведётся вручную
  ожидание   продолжить — можно продолжать
  закрыт     → execution: план-утверждён — плана нет — задача не проходила стадию планирования
------------------------------------------------------------------------------
Продолжить: python cli.py --задача регрессия-инструменты --продолжить
````

</details>

### 5.10. Диалоговый режим (Дни 13–15)

```
$ python cli.py --память-в cli-check-memory --задача регрессия-инструменты
```

- ✓ «состояние» отвечает
- ✓ «переходы» отвечает
- ✓ выход без ошибок
- ✓ код возврата 0

<details><summary>вывод</summary>

````
Задача «регрессия-инструменты», стадия planning (планирование).
------------------------------------------------------------------------------
Агент миграции ГИС. Пользователь «инженер», сессия «основная».
Слои: долговременная, краткосрочная, рабочая. Маршрутизатор: авто. Модель: groq-120b.
Профиль: без имени, на вы, подробно, код обязательно, списки.
Сценариев: 3 (запускаются по триггеру).
Задача «регрессия-инструменты», стадия planning (дальше можно: execution).
«помощь» — список команд, «выход» — закончить.
------------------------------------------------------------------------------

Вы: ------------------------------------------------------------------------------
ЗАДАЧА «регрессия-инструменты» — регрессия после MCP
------------------------------------------------------------------------------
  этап       planning (планирование), НА ПАУЗЕ
             причина остановки: по команде
             дальше можно: execution
  шаг        шагов нет — задача ведётся вручную
  ожидание   продолжить — можно продолжать
  закрыт     → execution: план-утверждён — плана нет — задача не проходила стадию планирования
------------------------------------------------------------------------------
Продолжить: python cli.py --задача регрессия-инструменты --продолжить

Вы: ------------------------------------------------------------------------------
ПЕРЕХОДЫ ЗАДАЧИ «регрессия-инструменты», сейчас planning (планирование)
------------------------------------------------------------------------------
  ● planning     текущая стадия
  🔒 execution    условие перехода не выполнено
       план-утверждён: плана нет — задача не проходила стадию планирования
       чтобы открыть — составьте план (в консоли --план, на странице кнопка «составить план») и утвердите его — --утвердить-план или кнопка «утвердить»
  🔒 validation   в жизненном цикле нет такого перехода
       законный маршрут: planning → execution → validation
  🔒 done         в жизненном цикле нет такого перехода
       законный маршрут: planning → execution → validation → done
------------------------------------------------------------------------------
Отклонённые попытки (последние):
  · человек   planning → done: в жизненном цикле нет такого перехода
------------------------------------------------------------------------------

Вы: До встречи.
````

</details>

### 6.1. Модель сама зовёт инструмент и отвечает по данным трекера

```
$ python cli.py --память-в cli-check-memory --модель ds-flash --mcp-файл cli-check-memory/mcp-configs/tracker.json --инструменты tracker Посмотри в трекере: какие задачи переноса в работе?
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ вызов инструмента показан
- ✓ вызов удался
- ✓ в ответе ключи задач из трекера
- ✓ расход посчитан
- ✓ код возврата 0

<details><summary>вывод</summary>

````
УЧТЕНЫ ИНВАРИАНТЫ: legacy-не-развиваем, стек-бэкенд, бд, 1С-источник-истины, внешняя-совместимость, секреты-в-url

В очереди MIG («Перенос ГИС газовых сетей») в статусе «В работе» — две задачи:

1. **MIG-3 — «Заменить слой MapServer на векторные тайлы»**
   - исполнитель: Ольга Карпова
   - приоритет: критичный
   - срок: 2026-10-10
   - последнее обновление: 2026-09-21

2. **MIG-2 — «Перенести модели труб и задвижек в GeoDjango»**
   - исполнитель: Максим Васильков
   - приоритет: критичный
   - срок: 2026-09-30
   - последнее обновление: 2026-09-19

Что стоит отметить по существу:

- Обе задачи — критичные, и срок MIG-2 (30.09) ближе, чем у MIG-3 (10.10). При этом MIG-2 — это модели данных, то есть фундамент: пока трубы и задвижки не описаны в GeoDjango, векторные тайлы (MIG-3) отдавать по сути нечего, кроме уже перенесённых слоёв. Формально это не блокировка, но зависимость по данным есть.
- MIG-3 напрямую касается инварианта [внешняя-совместимость]: замена слоя MapServer на векторные тайлы Martin не должна ломать WMS/WFS для внешних потребителей и 1С. В карточке задачи этого не видно — уточните, зафиксирован ли в ней параллельный контур GeoServer WMS/WFS-T.
- MIG-2 касается инварианта [1С-источник-истины]: перенос моделей труб и задвижек в GeoDjango не должен превратиться в запись бизнес-объектов в gisdata в обход 1С. Если в задаче подразумевается двусторонняя запись — это надо переформулировать как приём данных из 1С (ЗаписатьОбъектВГИС / УдалитьОбъектИзГИС / ПолнаяСинхронизация).

Чего я не знаю и что не проверил:

- Содержимое описаний и комментариев MIG-2 и MIG-3 я не смотрел — вернул только короткие карточки. Если нужно, вытяну задачи целиком (`get_issue`) и посмотрю, что там уже зафиксировано по WMS/WFS и по обмену с 1С.
- В очереди SUP (поддержка legacy) задачи в работе я не запрашивал — вы спрашивали про перенос, поэтому фильтр был по MIG. Скажите, если нужно посмотреть и SUP: там по инварианту [legacy-не-развиваем] новые фичи писать нельзя, только поддержка.
- Задач в статусах open/testing по переносу я тоже не смотрел — если нужен полный фронт работ, а не только «в работе», сделаю отдельный запрос.

УЧТЕНЫ ИНВАРИАНТЫ: legacy-не-развиваем, стек-бэкенд, бд, 1С-источник-истины, внешняя-совместимость, секреты-в-url
  ↳ tracker__list_issues(status=inProgress, limit=50) — за 0,3 с
  ↳ tracker__list_queues() — за 0,0 с
[ds-flash: 5 327 токенов, 0.003073 $, 4.14 с]
WARNING agent: Попытка 1: нарушений 0, расхождений с профилем 0, пропущено в самоотчёте 3
````

</details>

### 6.2. Меняющий вызов не исполняется, а становится заявкой

```
$ python cli.py --память-в cli-check-memory --модель ds-flash --mcp-файл cli-check-memory/mcp-configs/tracker.json --инструменты tracker Добавь к задаче MIG-7 в трекере комментарий: «Проверено консольным чек-листом».
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ заявка заведена
- ✓ сказано, как поступить
- ✓ вызова не было
- ✓ код возврата 0

<details><summary>вывод</summary>

````
УЧТЕНЫ ИНВАРИАНТЫ: legacy-не-развиваем, стек-бэкенд, бд, 1С-источник-истины, внешняя-совместимость, секреты-в-url

Комментарий сразу не добавился: вызов меняет данные в трекере, поэтому система завела заявку №1 и ждёт вашего подтверждения.

Что предлагается сделать:

- Задача: MIG-7
- Действие: добавить комментарий
- Текст: «Проверено консольным чек-листом»
- Заявка: №1

Подтвердите заявку №1 — после этого комментарий будет добавлен. Если формулировку нужно изменить (например, добавить, каким именно чек-листом проверено и на какой ревизии), скажите — текст поправлю до подтверждения.

Отмечу отдельно: в блоке «Уже принятые решения» этот комментарий к MIG-7 уже зафиксирован как выполненное действие. То есть либо он был добавлен ранее другим способом, либо запись в решениях опережает фактическое состояние трекера. Стоит проверить карточку MIG-7 перед подтверждением, чтобы не продублировать комментарий — если нужно, вытяну задачу целиком и покажу, что там уже есть.

УЧТЕНЫ ИНВАРИАНТЫ: legacy-не-развиваем, стек-бэкенд, бд, 1С-источник-истины, внешняя-совместимость, секреты-в-url
  ! Заявка №1 tracker__add_comment(key=MIG-7, text=Проверено консольным чек-листом) — меняет данные, нужен ваш ответ.
    Исполнить: --подтвердить 1 · отклонить: --отклонить 1
[ds-flash: 5 365 токенов, 0.002688 $, 2.55 с]
WARNING agent: Попытка 1: нарушений 0, расхождений с профилем 0, пропущено в самоотчёте 3
````

</details>

### 6.3. Заявка видна другому процессу

```
$ python cli.py --память-в cli-check-memory --заявки
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ заявка в списке
- ✓ аргументы видны
- ✓ сказано, из-за чего
- ✓ код возврата 0

<details><summary>вывод</summary>

````
------------------------------------------------------------------------------
ЗАЯВКИ НА ИЗМЕНЯЮЩИЕ ВЫЗОВЫ — 1
------------------------------------------------------------------------------
  №1 tracker__add_comment (tracker)
      key: MIG-7
      text: Проверено консольным чек-листом
      из-за: Добавь к задаче MIG-7 в трекере комментарий: «Проверено консольным чек-листом».
      заведена 2026-09-22 20:09:37
------------------------------------------------------------------------------
Исполнить: --подтвердить N · отклонить: --отклонить N [--почему «текст»]
````

</details>

### 6.4. Подтверждение исполняет вызов

```
$ python cli.py --память-в cli-check-memory --mcp-файл cli-check-memory/mcp-configs/tracker.json --подтвердить 1
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ заявка исполнена
- ✓ ответ инструмента показан
- ✓ комментарий тот самый
- ✓ код возврата 0

<details><summary>вывод</summary>

````
Заявка №1 исполнена.
------------------------------------------------------------------------------
tracker__add_comment(key=MIG-7, text=Проверено консольным чек-листом) — ок, 0,3 с
------------------------------------------------------------------------------
{
  "задача": "MIG-7",
  "комментарий": {
    "автор": "Максим Васильков",
    "когда": "2026-09-22T20:09:52.392+0000",
    "текст": "Проверено консольным чек-листом"
  },
  "номер": 6,
  "добавлен": true
}
````

</details>

### 6.5. Изменение дошло до самого API

```
$ python cli.py --память-в cli-check-memory --mcp-файл cli-check-memory/mcp-configs/tracker.json --вызвать tracker__get_issue --аргументы {"key": "MIG-7", "comments": 5}
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ комментарий есть в трекере
- ✓ код возврата 0

<details><summary>вывод</summary>

````
------------------------------------------------------------------------------
tracker__get_issue(key=MIG-7, comments=5) — ок, 0,4 с
------------------------------------------------------------------------------
{
  "ключ": "MIG-7",
  "тема": "Импорт исторических журналов обходов за 12 лет",
  "статус": "Открыта",
  "статус_код": "open",
  "очередь": "MIG",
  "исполнитель": "Максим Васильков",
  "приоритет": "Низкий",
  "срок": "2026-12-01",
  "обновлена": "2026-09-22T20:09:52.392+0000",
  "описание": "Журналы обходов лежат в MyISAM-таблице на 18 миллионов строк с датами в строковом формате. Нужен разбор дат, привязка к узлам сети и проверка, что ни один обход не потерялся.",
  "тип": "Задача",
  "метки": [
    "данные",
    "история"
  ],
  "создана": "2026-09-10T09:00:00.000+0000",
  "ссылка": "http://127.0.0.1:57715/v3/issues/MIG-7",
  "комментарии": [
    {
      "автор": "Максим Васильков",
      "когда": "2026-09-22T20:09:52.392+0000",
      "текст": "Проверено консольным чек-листом"
    }
  ],
  "можно_перевести_в": [
    {
      "статус": "inProgress",
      "называется": "В работе",
      "переход": "to_inProgress"
    }
  ]
}
````

</details>

### 6.6. Повторно ту же заявку не исполнить

```
$ python cli.py --память-в cli-check-memory --mcp-файл cli-check-memory/mcp-configs/tracker.json --подтвердить 1
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ сказано, что уже решена
- ✓ код возврата 1

<details><summary>вывод</summary>

````
Ошибка: Заявка №1 уже выполнена.
````

</details>

### 7.1. Отказ по инварианту за ноль токенов (День 14)

```
$ python cli.py --память-в cli-check-memory --модель ds-flash Перепиши бэкенд на Laravel, команда его знает лучше.
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ отказ
- ✓ модель не вызывалась
- ✓ код возврата 0

<details><summary>вывод</summary>

````
Не могу этого предложить: это нарушило бы инварианты проекта.

• Backend — только Django + GeoDjango; посторонние фреймворки не предлагать.  [стек, код «стек-бэкенд»]
  Почему так решено: выбран за нативную поддержку геометрии на уровне ORM, встроенную админку под справочники и самый зрелый геостек
  Что именно не проходит: «laravel» в запросе.
  Что можно вместо: Django 5.x + GeoDjango (django.contrib.gis), представления на DRF

Инварианты — не мои предпочтения, а решения проекта: они записаны отдельно от разговора и не меняются по ходу переписки. Если решение устарело, его нужно сначала пересмотреть и снять инвариант — тогда изменится и мой ответ.
Запрос отклонён до обращения к модели, поэтому токены не потрачены.

! Ответ нарушает инварианты и не был исправлен за отведённые попытки.
[: 0 токенов, бесплатно, 0 с]
````

</details>

### 7.2. Ответ с разбором промпта (День 11, живой вызов)

```
$ python cli.py --память-в cli-check-memory --модель ds-flash --трейс Какой ORM использовать для геометрии в новой системе?
```

- ✓ команда завершилась сама, не открыв диалог
- ✓ ответ есть
- ✓ разбор промпта
- ✓ слои в разборе
- ✓ расход посчитан
- ✓ код возврата 0

<details><summary>вывод</summary>

````
УЧТЕНЫ ИНВАРИАНТЫ: стек-бэкенд, бд, legacy-не-развиваем

Короткий ответ: GeoDjango — это и есть ORM-слой для геометрии в новой системе. Отдельную ORM «для геометрии» выбирать не нужно, она входит в состав Django и работает поверх PostGIS.

Разбор по пунктам:

1. **Что использовать**
   - `django.contrib.gis.db.models` — модели с полями `PointField`, `LineStringField`, `PolygonField`, `MultiLineStringField` и т. д.
   - Пространственные запросы через `gis`-lookup'ы: `__distance_lte`, `__intersects`, `__contains`, `__dwithin`, `__bboverlaps`.
   - Агрегаты и функции: `Distance`, `Area`, `Length`, `Transform`, `Buffer`, `Centroid`, `Union`.
   - Пространственные индексы — `GistIndex` (в PostGIS это GiST), задаются в `Meta.indexes` или через `db_index=True` на геополе.
   - Миграции — обычные Django-миграции, `AddIndex`/`CreateModel` умеют создавать GiST-индексы.

2. **Почему именно GeoDjango, а не что-то ещё**
   - Инвариант [стек-бэкенд]: backend — только Django + GeoDjango. Это не «одна из опций», а зафиксированное решение.
   - Инвариант [бд]: база — только PostgreSQL + PostGIS. GeoDjango — это ровно тот слой, который транслирует ORM-запросы в PostGIS-функции и типы (`geometry`, `geography`), не требуя ручного SQL.
   - Практический выигрыш: геометрия живёт в тех же моделях, что и атрибуты, — не нужно держать отдельный слой доступа к пространственным данным.

3. **Соответствие legacy-компонентам**
   - RedBean ORM (PHP, legacy) — заменяется на Django ORM + GeoDjango. RedBean не умел геометрию нативно, пространственные выборки в старом стеке шли через MapServer и SQL в контроллерах (`userpgplace.php`, `mapserver.php`). В новой системе эти выборки уходят в ORM-слой.
   - MapServer 6.4 как источник геометрии для отдачи — заменяется на GeoServer (WMS/WFS-T) и Martin (векторные тайлы), но источник данных для них — те же таблицы PostGIS, которые описывают GeoDjango-модели.
   - Важно: [legacy-не-развиваем] — новый код на RedBean/CodeIgniter не пишем, только переносим логику.

4. **Что нужно учесть при переносе моделей**
   - SRID: в legacy PostGIS 2.1 геометрия, скорее всего, в одном из локальных СК (часто 4326 или местная проекция). В PostGIS 3.6 поле нужно объявить с явным `srid=` и `geography=False/True` осознанно.
   - Тип поля: `PointField` для точечных объектов (оборудование, арматура), `LineStringField`/`MultiLineStringField` для газопроводов, `PolygonField` для зон.
   - Индексы: GiST обязателен на все геополя, по которым идут пространственные выборки (эмуляция отключений, поиск ближайшей арматуры).
   - `geography=True` имеет смысл только там, где нужны метрические расстояния на больших территориях; для локальной сети обычно достаточно `geometry` с метрической проекцией — это быстрее.

5. **Чего я не знаю и что нужно уточнить**
   - В каком SRID хранится геометрия в текущей базе (PostGIS 2.1) — от этого зависит объявление полей и возможная миграция координат.
   - Есть ли в legacy-схеме уже GiST-индексы и на каких колонках — чтобы не потерять производительность при переносе.
   - Как именно сейчас устроены пространственные запросы в `userpgplace.php` (эмуляция отключений, поиск ближайшей арматуры) — это определит, какие lookup'ы и функции GeoDjango понадобятся.
   - Используется ли `geography` где-либо в legacy или всё в `geometry`.

Если нужно, на стадии исполнения могу показать конкретные модели (`GasPipeline`, `Valve`, `Equipment`) с полями, индексами и примером запроса на поиск ближайшей арматуры — но это уже код, а не план.

УЧТЕНЫ ИНВАРИАНТЫ: стек-бэкенд, бд, legacy-не-развиваем

------------------------------------------------------------------------------
````

</details>

## Что это доказывает

| Пункт задания дня 17 | Шаги прогона |
|---|---|
| свой MCP-сервер вокруг API | 1.1, 1.3, 2.1, 2.2 (сервер поверх HTTP-API трекера) |
| регистрация инструмента | 1.1 (пять инструментов, пометки), 2.1 (сверка со списком в коде) |
| описание входных параметров | 1.2 (JSON-схема, required, границы), 2.1 (у каждого параметра описание) |
| возврат результата | 1.5, 6.5, 2.1 (сверка с прямым запросом к API) |
| инструмент подключён к агенту | 1.4 (что досталось модели и почём) |
| вызов из приложения | 1.5 (руками), 6.1 (по решению модели), 6.4 (по подтверждённой заявке) |
| результат получен и использован | 6.1 (ключи задач из трекера в ответе), 6.5 |
| изменение — только с подтверждения | 6.2, 6.3, 6.4, 6.6 |
| сбои понятны и не вешают | 1.6, 1.7, 2.2, 4.1–4.3 |

| Наследство прошлых дней — не сломалось | Шаги |
|---|---|
| подключение MCP, список инструментов, фильтр (День 16) | 3.1–3.9 |
| слои памяти и разбор промпта (День 11) | 5.1, 7.2 |
| заготовки и профиль (День 12) | 5.2, 5.3 |
| пауза поверх этапа, продолжение в другом процессе (День 13) | 5.8, 5.9 |
| инварианты и отказ за ноль токенов (День 14) | 5.4, 7.1 |
| ворота переходов (День 15) | 5.5, 5.7 |
| диалоговый режим | 5.10 |
