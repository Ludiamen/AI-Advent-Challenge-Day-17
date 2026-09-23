#!/usr/bin/env python3
"""Тесты модели памяти. По умолчанию без сети.

    python tests.py              — все тесты без обращений к API
    python tests.py --живые      — плюс проверки, которым нужен реальный ключ
    python tests.py -v           — подробный вывод

Сетевых вызовов в основном наборе нет намеренно: правила маршрутизации, границы
слоёв и проверка инвариантов — это код, и он должен проверяться без оглядки на
доступность провайдера и на лимиты бесплатного тарифа.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import catalog, interview, preferences, seed as seed_module
from agent.builder import POLICY, PromptBuilder
from agent.memory.long import LongTermError, LongTermMemory
from agent.memory.manager import LONG, OFF, SHORT, WORKING, MemoryManager
from agent.memory.router import Routing, _parse
from agent.memory.short import ShortTermMemory
from agent.memory.working import (
    DONE, EXECUTION, PLANNING, STAGES, VALIDATION, TaskState, TaskStep, TransitionError,
    WorkingMemory, WorkingMemoryError, ЖДЁТ, ГОТОВ, ЗАКРЫТ_ПЕРЕХОД, ЗАПУСТИТЬ,
    ИЗ_ПЛАНА, ИЗ_СЦЕНАРИЯ, НАРУШЕН_ИНВАРИАНТ, НА_ПЕРЕХОДЕ, НЕТ_СВЕДЕНИЙ,
    НИЧЕГО, ОЖИДАНИЯ, ОТВЕТ, ПОДТВЕРДИТЬ, ПО_КОМАНДЕ, ПРОДОЛЖИТЬ, РЕШЕНИЕ,
)
from agent import transitions as tr
from agent.transitions import (
    БАЗОВЫЕ, ЛИЧНЫЙ, МОДЕЛЬ, СЦЕНАРИЙ, ЧЕЛОВЕК, ConditionStore, TransitionConfigError,
    Условие, Ворота, ПереходОтклонён,
)
from agent.preferences import PreferenceChecker, PreferenceError
from agent.scenarios import Scenario, ScenarioError, ScenarioStore, Step
from agent import invariants as inv
from agent.invariants import Invariant, InvariantError, InvariantStore
from agent.validator import Refusal, StateValidator

ЖИВЫЕ = "--живые" in sys.argv
if ЖИВЫЕ:
    sys.argv.remove("--живые")


class ВременнаяПамять(unittest.TestCase):
    """Общий каркас: каждый тест работает на своей копии памяти."""

    def setUp(self) -> None:
        self.каталог = tempfile.mkdtemp(prefix="тест-памяти-")
        self.память = MemoryManager(base_dir=self.каталог, router_mode=OFF)

    def tearDown(self) -> None:
        shutil.rmtree(self.каталог, ignore_errors=True)


# --- краткосрочная память -----------------------------------------------------

class КраткосрочнаяПамять(unittest.TestCase):

    def setUp(self) -> None:
        self.память = ShortTermMemory(":memory:")

    def test_окно_ограничено_числом_сообщений(self):
        for i in range(20):
            self.память.append("с", "user" if i % 2 == 0 else "assistant", f"реплика {i}")
        окно = self.память.window("с", max_messages=6)
        self.assertEqual(len(окно), 6)
        self.assertEqual(окно[-1]["content"], "реплика 19")

    def test_окно_ограничено_символами(self):
        self.память.append("с", "user", "х" * 5000)
        self.память.append("с", "assistant", "короткая")
        окно = self.память.window("с", max_messages=10, max_chars=1000)
        # Первая реплика не влезает по символам, но одна запись остаётся всегда:
        # пустое окно хуже, чем окно из одного сообщения.
        self.assertEqual(len(окно), 1)
        self.assertEqual(окно[0]["content"], "короткая")

    def test_сессии_не_смешиваются(self):
        self.память.append("работа", "user", "про работу")
        self.память.append("черновик", "user", "про черновик")
        self.assertEqual(len(self.память.all("работа")), 1)
        self.assertEqual(len(self.память.all("черновик")), 1)

    def test_пустая_реплика_не_сохраняется(self):
        with self.assertRaises(Exception):
            self.память.append("с", "user", "   ")

    def test_неизвестная_роль_отклоняется(self):
        with self.assertRaises(Exception):
            self.память.append("с", "system", "текст")


# --- рабочая память -----------------------------------------------------------

class РабочаяПамять(unittest.TestCase):

    def setUp(self) -> None:
        self.каталог = tempfile.mkdtemp()
        self.память = WorkingMemory(self.каталог)

    def tearDown(self) -> None:
        shutil.rmtree(self.каталог, ignore_errors=True)

    def test_разрешённый_маршрут_проходит_целиком(self):
        задача = self.память.create("з1", "тест")
        for стадия in (EXECUTION, VALIDATION, DONE):
            задача.transition(стадия)
        self.assertTrue(задача.finished)
        self.assertEqual(len(задача.transitions), 3)

    def test_прыжок_через_стадию_отклоняется(self):
        задача = self.память.create("з2")
        with self.assertRaises(TransitionError):
            задача.transition(DONE)
        self.assertEqual(задача.stage, PLANNING)

    def test_возвраты_разрешены(self):
        задача = self.память.create("з3")
        задача.transition(EXECUTION)
        задача.transition(PLANNING)          # план оказался негодным
        задача.transition(EXECUTION)
        задача.transition(VALIDATION)
        задача.transition(EXECUTION)         # нашли дефект
        self.assertEqual(задача.stage, EXECUTION)

    def test_из_done_никуда(self):
        задача = self.память.create("з4")
        for стадия in (EXECUTION, VALIDATION, DONE):
            задача.transition(стадия)
        self.assertEqual(задача.allowed(), ())
        with self.assertRaises(TransitionError):
            задача.transition(PLANNING)

    def test_состояние_переживает_перезапуск(self):
        задача = self.память.create("з5", "перенос")
        задача.transition(EXECUTION)
        задача.remember("таблиц", "37")
        задача.set_plan(["шаг один", "шаг два"])
        self.память.save(задача)

        другая = WorkingMemory(self.каталог).load("з5")
        self.assertEqual(другая.stage, EXECUTION)
        self.assertEqual(другая.collected["таблиц"], "37")
        self.assertEqual(другая.plan, ["шаг один", "шаг два"])

    def test_повторное_создание_отклоняется(self):
        self.память.create("з6")
        with self.assertRaises(WorkingMemoryError):
            self.память.create("з6")

    def test_недопустимый_идентификатор(self):
        for плохой in ("../побег", "имя с пробелом", "", "a" * 100):
            with self.assertRaises(WorkingMemoryError):
                self.память.create(плохой)

    def test_отсутствующая_задача_даёт_понятную_ошибку(self):
        with self.assertRaises(WorkingMemoryError):
            self.память.load("нет-такой")


class СостояниеЗадачи(unittest.TestCase):
    """Три части состояния: этап, шаг и ожидаемое действие."""

    def setUp(self) -> None:
        self.каталог = tempfile.mkdtemp()
        self.память = WorkingMemory(self.каталог)

    def tearDown(self) -> None:
        shutil.rmtree(self.каталог, ignore_errors=True)

    def _с_шагами(self, ид="з"):
        задача = self.память.create(ид, "проверка")
        задача.set_steps([
            TaskStep(1, "аналитик", ИЗ_СЦЕНАРИЯ, PLANNING, может_спросить=True),
            TaskStep(2, "backend", ИЗ_СЦЕНАРИЯ, EXECUTION),
        ], сценарий="проба")
        return задача

    def test_свежая_задача_ждёт_запуска(self):
        задача = self.память.create("новая")
        self.assertEqual(задача.ожидание, ЗАПУСТИТЬ)
        # Пояснение заполняется само, иначе интерфейс печатает «ожидание: — ».
        self.assertTrue(задача.ожидание_текст)

    def test_указатель_шага_двигается_при_завершении(self):
        задача = self._с_шагами()
        self.assertEqual(задача.шаг.имя, "аналитик")
        задача.начать_шаг()
        self.assertEqual(задача.шаг.состояние, "идёт")
        задача.закончить_шаг("требования собраны")
        self.assertEqual(задача.шаг.имя, "backend")
        self.assertEqual(задача.шаги[0].состояние, "готов")
        self.assertIn("требования", задача.шаги[0].выжимка)

    def test_пройденные_шаги_видно_по_состоянию(self):
        задача = self._с_шагами()
        задача.закончить_шаг("раз")
        задача.закончить_шаг("два")
        self.assertTrue(задача.шаги_пройдены)

    def test_пауза_не_меняет_этап(self):
        # Пауза — флаг поверх стадии, а не пятая стадия автомата.
        задача = self._с_шагами()
        задача.transition(EXECUTION)
        задача.остановить(ПО_КОМАНДЕ)
        self.assertTrue(задача.пауза)
        self.assertEqual(задача.stage, EXECUTION)
        self.assertEqual(задача.allowed(), (VALIDATION, PLANNING))

    def test_пауза_снимается(self):
        задача = self._с_шагами()
        задача.остановить(НА_ПЕРЕХОДЕ, ПОДТВЕРДИТЬ, "перейти к исполнению?")
        self.assertEqual(задача.ожидание, ПОДТВЕРДИТЬ)
        задача.продолжить()
        self.assertFalse(задача.пауза)
        self.assertEqual(задача.ожидание, ПРОДОЛЖИТЬ)

    def test_ответ_снимает_паузу_и_ложится_отдельно(self):
        задача = self._с_шагами()
        задача.остановить(НЕТ_СВЕДЕНИЙ, ОТВЕТ, "какой SRID?")
        задача.ответить("3857")
        self.assertFalse(задача.пауза)
        self.assertEqual(len(задача.ответы), 1)
        self.assertEqual(задача.ответы[0]["ответ"], "3857")
        # Ответ человека — не то же, что собранное агентом.
        self.assertEqual(задача.collected, {})

    def test_пустой_ответ_отклоняется(self):
        задача = self._с_шагами()
        задача.остановить(НЕТ_СВЕДЕНИЙ, ОТВЕТ, "какой SRID?")
        with self.assertRaises(WorkingMemoryError):
            задача.ответить("   ")

    def test_неизвестное_ожидание_отклоняется(self):
        задача = self._с_шагами()
        with self.assertRaises(WorkingMemoryError):
            задача.ждать("подумать")

    def test_неизвестная_причина_паузы_отклоняется(self):
        задача = self._с_шагами()
        with self.assertRaises(WorkingMemoryError):
            задача.остановить("настроение")

    def test_смена_этапа_сбрасывает_прежнее_ожидание(self):
        # Иначе после перехода на экране остаётся «подтвердите переход».
        задача = self._с_шагами()
        задача.остановить(НА_ПЕРЕХОДЕ, ПОДТВЕРДИТЬ, "перейти?")
        задача.продолжить()
        задача.transition(EXECUTION)
        self.assertEqual(задача.ожидание, ПРОДОЛЖИТЬ)

    def test_завершение_ставит_ожидание_ничего(self):
        задача = self._с_шагами()
        for стадия in (EXECUTION, VALIDATION, DONE):
            задача.transition(стадия)
        self.assertEqual(задача.ожидание, НИЧЕГО)

    def test_состояние_переживает_запись_и_чтение(self):
        # Главное свойство: продолжить можно из другого процесса.
        задача = self._с_шагами("живучая")
        задача.начать_шаг()
        задача.закончить_шаг("готово")
        задача.запрос = "исходный запрос"
        задача.остановить(НЕТ_СВЕДЕНИЙ, ОТВЕТ, "какой SRID?")
        self.память.save(задача)

        другая = WorkingMemory(self.каталог).load("живучая")
        self.assertTrue(другая.пауза)
        self.assertEqual(другая.ожидание, ОТВЕТ)
        self.assertEqual(другая.текущий_шаг, 2)
        self.assertEqual(другая.запрос, "исходный запрос")
        # Шаги должны подняться объектами, а не словарями.
        self.assertIsInstance(другая.шаг, TaskStep)
        self.assertEqual(другая.шаг.имя, "backend")

    def test_план_превращается_в_шаги(self):
        задача = self.память.create("ручная", "без сценария")
        задача.set_plan(["выписать таблицы", "описать модели"])
        self.assertEqual(задача.шагов, 2)
        self.assertEqual(задача.шаг.источник, ИЗ_ПЛАНА)

    def test_план_не_затирает_шаги_сценария(self):
        задача = self._с_шагами()
        задача.set_plan(["посторонний пункт"])
        self.assertEqual([ш.имя for ш in задача.шаги], ["аналитик", "backend"])

    def test_состояние_словами_называет_все_три_части(self):
        задача = self._с_шагами()
        строка = задача.состояние_словами
        for кусок in ("этап", "шаг", "ждём"):
            self.assertIn(кусок, строка)

    def test_все_ожидания_имеют_пояснение(self):
        from agent.memory.working import ОЖИДАНИЯ_СЛОВАМИ
        self.assertEqual(set(ОЖИДАНИЯ), set(ОЖИДАНИЯ_СЛОВАМИ))


# --- долговременная память ----------------------------------------------------

class ДолговременнаяПамять(unittest.TestCase):

    def setUp(self) -> None:
        self.каталог = tempfile.mkdtemp()
        self.память = LongTermMemory(self.каталог, "кто-то")

    def tearDown(self) -> None:
        shutil.rmtree(self.каталог, ignore_errors=True)

    def test_каждое_хранилище_в_своём_файле(self):
        self.память.profile.update("ограничения", "бд", "PostgreSQL")
        self.память.decisions.add("Стек", "Django")
        self.память.knowledge.add("ф1", "факт")
        self.память.scenarios.add(Scenario(имя="с", шаги=[Step("а", "делай")]))
        self.память.conditions.add(Условие(
            код="своё", откуда="validation", куда="done", что="есть-в-собранном",
            значение="ссылка", правило="в готово — только со ссылкой на репозиторий"))
        пути = set(self.память.files().values())
        # Профиль, сценарии, решения и знания — четыре разных файла: у каждого
        # свой режим записи, и смешивать их значит терять это различие.
        # Пятый файл — личные условия перехода, заведённые в этом дне.
        self.assertEqual(len(пути), 5)
        for путь in пути:
            self.assertTrue(os.path.exists(путь), путь)

    def test_профиль_перезаписывается_а_решения_дописываются(self):
        self.память.profile.update("ограничения", "бд", "PostgreSQL 16")
        self.память.profile.update("ограничения", "бд", "PostgreSQL 17")
        self.assertEqual(self.память.profile.load()["ограничения"]["бд"], "PostgreSQL 17")

        self.память.decisions.add("Первое", "текст один")
        self.память.decisions.add("Второе", "текст два")
        self.assertEqual(len(self.память.decisions.all()), 2)

    def test_имя_пользователя_не_выводит_за_каталог(self):
        # Имя пользователя превращается в путь. Без проверки «--кто ../../чужой»
        # записывает профиль за пределы каталога памяти — проверено, записывал.
        for плохое in ("../../чужой", "кто/то", "..", "", "a" * 100):
            with self.assertRaises(LongTermError, msg=плохое):
                LongTermMemory(self.каталог, плохое)

    def test_обычное_имя_принимается(self):
        память = LongTermMemory(self.каталог, "инженер-2")
        self.assertTrue(os.path.realpath(память.directory).startswith(
            os.path.realpath(self.каталог)))

    def test_неизвестный_раздел_профиля(self):
        with self.assertRaises(LongTermError):
            self.память.profile.update("настроение", "тон", "бодрый")

    def test_недопустимое_значение_предпочтения_отклоняется(self):
        # Записать «длина: очень кратко» значило бы сохранить то, что не попадёт
        # ни в промпт, ни в проверку, — и никто бы не понял почему.
        with self.assertRaises(LongTermError):
            self.память.profile.update("формат", "длина", "очень кратко")

    def test_профиль_дополняется_умолчаниями_при_чтении(self):
        профиль = self.память.profile.load()
        for раздел in preferences.SECTIONS:
            for поле in preferences.fields(раздел):
                self.assertIn(поле.key, профиль[раздел])

    def test_жёсткий_инвариант_без_значений_отклоняется(self):
        # Инвариант, который нечем проверить, хуже, чем его отсутствие:
        # он создаёт ложное чувство защиты.
        with self.assertRaises(LongTermError):
            self.память.profile.add_invariant(
                {"код": "пустой", "правило": "нельзя", "тип": "запрет-слов", "значения": []}
            )

    def test_негодная_регулярка_отклоняется(self):
        with self.assertRaises(LongTermError):
            self.память.profile.add_invariant(
                {"код": "битый", "правило": "нельзя", "тип": "запрет-регулярок",
                 "значения": ["[незакрытая"]}
            )

    def test_инвариант_обновляется_по_коду(self):
        for правило in ("первая версия", "вторая версия"):
            self.память.profile.add_invariant(
                {"код": "один", "правило": правило, "тип": "мягкий"}
            )
        правила = self.память.profile.invariants()
        self.assertEqual(len(правила), 1)
        self.assertEqual(правила[0]["правило"], "вторая версия")

    def test_знания_отбираются_по_релевантности(self):
        self.память.knowledge.add("схема", "Схема gissys: account, group, organization",
                                  tags=["planning", "бд"])
        self.память.knowledge.add("фронт", "OpenLayers 2.13 рисует слои", tags=["execution"])
        отобрано = [ф["id"] for ф in self.память.knowledge.relevant("что в схеме gissys")]
        self.assertEqual(отобрано, ["схема"])

    def test_несовпавший_запрос_не_тянет_ничего(self):
        self.память.knowledge.add("схема", "Схема gissys", tags=["planning"])
        self.assertEqual(self.память.knowledge.relevant("погода в Москве"), [])

    def test_факт_уточняется_а_не_дублируется(self):
        self.память.knowledge.add("в", "PostGIS 3.4")
        self.память.knowledge.add("в", "PostGIS 3.6")
        факты = self.память.knowledge.all()
        self.assertEqual(len(факты), 1)
        self.assertEqual(факты[0]["текст"], "PostGIS 3.6")


# --- правила маршрутизации ----------------------------------------------------

class ПравилаМаршрутизации(ВременнаяПамять):

    def test_реплика_идёт_в_короткую_память(self):
        self.память.remember_message("user", "вопрос")
        self.assertEqual(self.память.stats()[SHORT]["реплик"], 1)
        последняя = self.память.journal(1)[0]
        self.assertEqual(последняя["правило"], "реплика-диалога")
        self.assertEqual(последняя["слой"], SHORT)

    def test_шаг_задачи_идёт_в_рабочую_память(self):
        задача = self.память.working.create("з", "тест")
        self.память.remember_step(задача, "таблиц", "37")
        self.assertEqual(self.память.working.load("з").collected["таблиц"], "37")
        self.assertEqual(self.память.journal(1)[0]["слой"], WORKING)

    def test_явное_указание_идёт_куда_сказано(self):
        self.память.remember_explicit("знания", "В gisdata 37 таблиц", key="состав")
        запись = self.память.journal(1)[0]
        self.assertEqual(запись["правило"], "явное-указание")
        self.assertEqual(запись["подслой"], "знания")
        self.assertEqual(len(self.память.long.knowledge.all()), 1)

    def test_явное_указание_в_неизвестный_слой_отклоняется(self):
        with self.assertRaises(LongTermError):
            self.память.remember_explicit("подсознание", "что-то")

    def test_свёртка_идёт_на_выбранной_модели(self):
        # Иначе пять шагов честно идут на выбранной модели, а свёртка в конце
        # уходит к своей роли — и роняет весь прогон на последнем шаге.
        задача = self.память.working.create("з", "перенос")
        for стадия in (EXECUTION, VALIDATION):
            задача.transition(стадия)
        self.память.working.save(задача)

        class Считающий:
            def __init__(self): self.модели = []
            spent = {"calls": 0, "tokens": 0, "cost": 0.0}
            def call(self, model_key, messages, **kwargs):
                from agent.llm import Reply
                self.модели.append(model_key)
                return Reply(text='{"заголовок":"и","решение":"р","причина":"п"}',
                             model_key=model_key)
            def close(self): pass

        считающий = Считающий()
        self.память.client = считающий
        self.память.finish_task(задача, model_key="ds-flash")
        self.assertEqual(считающий.модели, ["ds-flash"])

    def test_без_выбора_свёртка_идёт_по_роли(self):
        задача = self.память.working.create("з2", "перенос")
        for стадия in (EXECUTION, VALIDATION):
            задача.transition(стадия)
        self.память.working.save(задача)
        self.assertEqual(self.память.summarizer_model, catalog.for_role("сжатие", offset=0))

    def test_завершение_задачи_переносит_её_в_решения(self):
        задача = self.память.working.create("з", "перенос моделей")
        self.память.remember_step(задача, "итог", "модели описаны")
        for стадия in (EXECUTION, VALIDATION):
            задача.transition(стадия)
        self.память.working.save(задача)

        запись = self.память.finish_task(задача)
        self.assertEqual(len(self.память.long.decisions.all()), 1)
        self.assertIn("перенос моделей", запись["заголовок"])
        # Рабочая память задачи очищена: её итог теперь живёт в журнале решений.
        self.assertEqual(self.память.working.tasks(), [])

    def test_очистка_диалога_не_трогает_другие_слои(self):
        self.память.remember_message("user", "реплика")
        задача = self.память.working.create("з")
        self.память.remember_step(задача, "к", "з")
        self.память.remember_explicit("знания", "факт", key="ф")

        self.память.short.clear(self.память.session)
        сводка = self.память.stats()
        self.assertEqual(сводка[SHORT]["реплик"], 0)
        self.assertEqual(сводка[WORKING]["задач"], 1)
        self.assertEqual(сводка[LONG]["знаний"], 1)

    def test_маршрутизатор_выключен_ничего_не_пишет(self):
        было = self.память.long.profile.load()
        предложение, запись = self.память.route("Отвечай кратко")
        self.assertFalse(предложение.wants_write)
        self.assertFalse(запись["применено"])
        # Профиль не пуст даже без записей: предпочтения всегда имеют умолчания.
        # Значит, проверять надо неизменность, а не пустоту.
        self.assertEqual(self.память.long.profile.load()["формат"], было["формат"])

    def test_отклонённое_предложение_видно_в_журнале(self):
        # Ниже порога — записи нет, но след остаётся: потом видно, что именно
        # агент решил не запоминать.
        self.память.router_mode = "авто"
        self.память.router = _ЗаглушкаМаршрутизатора(
            Routing(target="знания", key="к", value="факт", confidence=0.3)
        )
        предложение, запись = self.память.route("какая-то реплика")
        self.assertFalse(запись["применено"])
        self.assertIn("ниже порога", запись["причина"])
        self.assertEqual(len(self.память.long.knowledge.all()), 0)

    def test_уверенное_предложение_применяется(self):
        self.память.router_mode = "авто"
        self.память.router = _ЗаглушкаМаршрутизатора(
            Routing(target="знания", key="версия", value="PostGIS 3.6", confidence=0.9)
        )
        _, запись = self.память.route("у нас PostGIS 3.6")
        self.assertTrue(запись["применено"])
        self.assertEqual(self.память.long.knowledge.all()[0]["текст"], "PostGIS 3.6")

    def test_выдуманный_раздел_профиля_не_роняет_ответ(self):
        """Найдено при проходе чек-листа Дня 16: на «Перепиши сервис на Laravel»
        маршрутизатор предложил записать реплику в раздел профиля «переписать».
        Хранилище верно отказало, но исключение не ловилось, и страница вместо
        мгновенного отказа по инварианту получила ошибку 500."""
        self.память.router_mode = "авто"
        self.память.router = _ЗаглушкаМаршрутизатора(
            Routing(target="профиль", section="переписать", key="сервис",
                    value="на Laravel", confidence=0.9)
        )
        было = self.память.long.profile.load()
        предложение, запись = self.память.route("Перепиши сервис на Laravel")
        self.assertFalse(запись["применено"])
        self.assertIn("предложение отклонено", запись["причина"])
        self.assertIn("переписать", запись["причина"])
        self.assertEqual(self.память.long.profile.load(), было)

    def test_сбой_маршрутизатора_не_ломает_запись(self):
        self.память.router_mode = "авто"
        self.память.router = _ЗаглушкаМаршрутизатора(Routing(failed=True))
        предложение, запись = self.память.route("реплика")
        self.assertTrue(предложение.failed)
        self.assertFalse(запись["применено"])


class _ЗаглушкаМаршрутизатора:
    """Маршрутизатор с заранее известным ответом — чтобы тесты не ходили в сеть."""

    def __init__(self, routing: Routing) -> None:
        self.routing = routing

    def classify(self, text: str) -> Routing:
        return self.routing


class _СчётчикМаршрутизатора(_ЗаглушкаМаршрутизатора):
    """Та же заглушка, но помнит, сколько раз её звали."""

    def __init__(self, routing: Routing) -> None:
        super().__init__(routing)
        self.вызовы: list[str] = []

    def classify(self, text: str) -> Routing:
        self.вызовы.append(text)
        return self.routing


# --- разбор ответа маршрутизатора ---------------------------------------------

class РазборОтветаМодели(unittest.TestCase):

    def test_чистый_json(self):
        разбор = _parse('{"слой":"знания","ключ":"к","значение":"з","уверенность":0.8}')
        self.assertEqual(разбор.target, "знания")
        self.assertAlmostEqual(разбор.confidence, 0.8)

    def test_json_в_markdown(self):
        разбор = _parse('```json\n{"слой":"профиль","раздел":"стиль","значение":"кратко",'
                        '"уверенность":0.9}\n```')
        self.assertEqual(разбор.target, "профиль")
        self.assertEqual(разбор.section, "стиль")

    def test_json_с_болтовнёй_вокруг(self):
        разбор = _parse('Конечно! Вот ответ: {"слой":"нет","уверенность":0} — надеюсь, помог.')
        self.assertEqual(разбор.target, "нет")

    def test_хвост_после_объекта_не_мешает(self):
        # Слабые модели присылают валидный объект и следом обрывок служебного
        # тега. Срез «от первой { до последней }» на этом ломается.
        разбор = _parse('{"слой":"нет","уверенность":0}</think>{обрывок')
        self.assertEqual(разбор.target, "нет")

    def test_берётся_первый_из_двух_объектов(self):
        разбор = _parse('{"слой":"знания","значение":"факт","уверенность":0.9} {"слой":"нет"}')
        self.assertEqual(разбор.value, "факт")

    def test_скобка_внутри_строки_не_обрывает_разбор(self):
        разбор = _parse('{"слой":"знания","значение":"вот } скобка","уверенность":0.9}')
        self.assertEqual(разбор.value, "вот } скобка")

    def test_мусор_даёт_none(self):
        self.assertIsNone(_parse("я не понял вопроса"))

    def test_неизвестный_слой_даёт_none(self):
        self.assertIsNone(_parse('{"слой":"подсознание","уверенность":1}'))

    def test_уверенность_загоняется_в_границы(self):
        self.assertEqual(_parse('{"слой":"нет","уверенность":7}').confidence, 1.0)
        self.assertEqual(_parse('{"слой":"нет","уверенность":-3}').confidence, 0.0)


# --- сборка промпта -----------------------------------------------------------

class СборкаПромпта(ВременнаяПамять):

    def setUp(self) -> None:
        super().setUp()
        seed_module.seed(self.память)
        self.память.remember_message("user", "прошлая реплика")
        self.сборщик = PromptBuilder(self.память)

    def test_выключенный_слой_не_даёт_записей(self):
        промпт = self.сборщик.build("вопрос", layers={SHORT})
        self.assertNotIn(LONG, промпт.by_layer())
        причины = [б.why for б in промпт.blocks if б.layer == LONG]
        self.assertTrue(all("выключена" in п for п in причины))

    def test_инварианты_идут_всегда(self):
        for стадия in (PLANNING, EXECUTION, VALIDATION, DONE):
            задача = TaskState(task_id="з", stage=стадия)
            промпт = self.сборщик.build("вопрос", задача)
            блок = [б for б in промпт.blocks if б.name == "инварианты"][0]
            self.assertTrue(блок.included, f"инварианты пропали на стадии {стадия}")

    @staticmethod
    def _фактов(промпт) -> int:
        """Сколько записей знаний попало в промпт (0, если блок не включён)."""
        блоки = [б for б in промпт.included if б.name == "знания"]
        return len(блоки[0].entries) if блоки else 0

    def test_знания_зависят_от_стадии(self):
        # Факты о системе нужны, когда строят план, и мешают, когда проверяют
        # уже написанный код. Политика стадий именно это и задаёт.
        вопрос = "как перенести схему gissys"
        планирование = self.сборщик.build(вопрос, TaskState("з", stage=PLANNING))
        проверка = self.сборщик.build(вопрос, TaskState("з", stage=VALIDATION))
        self.assertGreater(self._фактов(планирование), self._фактов(проверка))

    def test_на_завершённой_задаче_знаний_нет(self):
        промпт = self.сборщик.build("итог?", TaskState("з", stage=DONE))
        self.assertEqual(self._фактов(промпт), 0)

    def test_настройки_идут_на_всех_стадиях(self):
        # Иначе стадия, где профиль не показали, гарантированно дала бы
        # расхождение с ним и лишний повтор.
        for стадия in (PLANNING, EXECUTION, VALIDATION, DONE):
            промпт = self.сборщик.build("вопрос", TaskState("з", stage=стадия))
            блок = [б for б in промпт.blocks if б.name == "настройки пользователя"][0]
            self.assertTrue(блок.included, f"настройки пропали на стадии {стадия}")

    def test_на_промежуточном_шаге_настроек_нет(self):
        промпт = self.сборщик.build("вопрос", personal=False)
        блок = [б for б in промпт.blocks if б.name == "настройки пользователя"][0]
        self.assertFalse(блок.included)
        self.assertIn("следующий агент", блок.why)

    def test_роль_шага_попадает_в_ядро(self):
        промпт = self.сборщик.build("вопрос", step_role="РОЛЬ НА ЭТОМ ШАГЕ: аналитик.")
        блок = [б for б in промпт.blocks if б.name == "роль шага"][0]
        self.assertTrue(блок.included)
        имена = [б.name for б in промпт.blocks]
        self.assertLess(имена.index("роль агента"), имена.index("роль шага"))

    def test_план_и_собранное_попадают_на_исполнении(self):
        задача = TaskState("з", stage=EXECUTION, plan=["шаг раз"], collected={"к": "з"})
        промпт = self.сборщик.build("вопрос", задача)
        имена = {б.name for б in промпт.included}
        self.assertIn("план", имена)
        self.assertIn("собранные данные", имена)

    def test_трейс_объясняет_каждый_блок(self):
        промпт = self.сборщик.build("вопрос")
        for блок in промпт.blocks:
            self.assertTrue(блок.why, f"блок «{блок.name}» без объяснения")

    def test_порядок_блоков_фиксирован(self):
        промпт = self.сборщик.build("вопрос")
        имена = [б.name for б in промпт.blocks]
        self.assertLess(имена.index("инварианты"), имена.index("настройки пользователя"))
        self.assertEqual(имена[-1], "вопрос пользователя")

    def test_без_задачи_берётся_политика_планирования(self):
        промпт = self.сборщик.build("вопрос")
        self.assertEqual(промпт.stage, PLANNING)

    def test_все_стадии_описаны_политикой(self):
        for стадия in (PLANNING, EXECUTION, VALIDATION, DONE):
            self.assertIn(стадия, POLICY)

    def test_шагу_сценария_рабочая_память_не_дублируется(self):
        # Иначе результат предыдущего шага уходит в запрос дважды: как явный
        # вход шага и как собранные данные задачи.
        задача = TaskState("з", stage=EXECUTION, collected={"шаг «аналитик»": "требования"})
        промпт = self.сборщик.build("вопрос", задача, step_role="РОЛЬ: backend")
        блок = [б for б in промпт.blocks if б.name == "собранные данные"][0]
        self.assertFalse(блок.included)
        self.assertIn("получает вход явно", блок.why)

    def test_вне_сценария_собранные_данные_показываются(self):
        задача = TaskState("з", stage=EXECUTION, collected={"к": "з"})
        промпт = self.сборщик.build("вопрос", задача)
        блок = [б for б in промпт.blocks if б.name == "собранные данные"][0]
        self.assertTrue(блок.included)

    def test_длинная_запись_обрезается_для_промпта(self):
        # Рабочая память хранит результат шага целиком, а в промпт идёт столько,
        # сколько туда помещается.
        задача = TaskState("з", stage=EXECUTION, collected={"шаг": "х" * 5000})
        промпт = self.сборщик.build("вопрос", задача)
        блок = [б for б in промпт.included if б.name == "собранные данные"][0]
        self.assertLess(len(блок.text), 3000)
        self.assertIn("обрезано", блок.text)


# --- проверка инвариантов -----------------------------------------------------

class ПроверкаИнвариантов(ВременнаяПамять):

    def setUp(self) -> None:
        super().setUp()
        seed_module.seed(self.память)
        # Валидатор берёт инварианты вызовом: их правят посреди разговора.
        self.валидатор = StateValidator(self.память.all_invariants)

    def test_предложение_чужого_стека_ловится(self):
        нарушения = self.валидатор.check("Возьмём Laravel, на нём быстрее.")
        self.assertEqual(len(нарушения), 1)
        self.assertEqual(нарушения[0].код, "стек-бэкенд")

    def test_отказ_от_чужого_стека_не_считается_нарушением(self):
        чисто = self.валидатор.check(
            "Laravel здесь не подойдёт: геометрия только через сырой SQL, берём GeoDjango."
        )
        self.assertEqual(чисто, [])

    def test_упоминание_legacy_разрешено(self):
        чисто = self.валидатор.check(
            "Контроллер userpgplace.php из CodeIgniter 1 превращается в Django-вьюху."
        )
        self.assertEqual(чисто, [])

    def test_код_на_старом_стеке_ловится(self):
        нарушения = self.валидатор.check('```php\n<?php\n$this->load->model("x");\n```')
        self.assertTrue(нарушения)
        self.assertEqual(нарушения[0].где, "коде")

    def test_чужая_субд_в_коде_ловится(self):
        нарушения = self.валидатор.check("```python\nDATABASES = {'ENGINE': 'mysql'}\n```")
        self.assertTrue(нарушения)

    def test_секрет_в_url_ловится(self):
        нарушения = self.валидатор.check("Дёргайте /api/export?token=abc123")
        self.assertEqual(нарушения[0].код, "секреты-в-url")

    def test_чистый_ответ_проходит(self):
        self.assertEqual(self.валидатор.check(
            "```python\nfrom django.contrib.gis.db import models\n\n"
            "class Pipe(models.Model):\n    geom = models.LineStringField(srid=3857)\n```"
        ), [])

    def test_напоминание_содержит_нарушение(self):
        нарушения = self.валидатор.check("Сделаем на Laravel.")
        напоминание = self.валидатор.reminder(нарушения)
        self.assertIn("laravel", напоминание.lower())

    def test_переход_проверяется_без_изменения_состояния(self):
        задача = TaskState("з", stage=PLANNING)
        можно, пояснение = StateValidator.check_transition(задача, DONE)
        self.assertFalse(можно)
        self.assertIn("не разрешён", пояснение)
        self.assertEqual(задача.stage, PLANNING)   # состояние не тронуто

    def test_смысловые_инварианты_не_проверяются_кодом(self):
        жёсткие = {и.код for и in self.валидатор.hard()}
        self.assertNotIn("1С-источник-истины", жёсткие)
        # Но и не забыты: они проверяются самоотчётом и моделью.
        self.assertIn("1С-источник-истины", {и.код for и in self.валидатор.semantic()})


# --- предпочтения -------------------------------------------------------------

class Предпочтения(unittest.TestCase):

    def test_умолчания_заполняют_все_поля(self):
        каркас = preferences.blank()
        for поле in preferences.FIELDS:
            self.assertIn(поле.key, каркас[поле.section])

    def test_недопустимое_значение_отклоняется(self):
        with self.assertRaises(PreferenceError):
            preferences.set_value(preferences.blank(), "формат", "длина", "как-нибудь")

    def test_неизвестное_поле_отклоняется(self):
        with self.assertRaises(PreferenceError):
            preferences.set_value(preferences.blank(), "формат", "цвет", "синий")

    def test_нормализация_чинит_испорченный_профиль(self):
        # Профиль правят руками и присылают формы: значение может оказаться чем
        # угодно, и дальше по коду оно должно быть уже корректным.
        профиль = preferences.normalize({"формат": {"длина": "ОЧЕНЬ КРАТКО"},
                                         "обращение": {"на_ты": "да"}})
        self.assertEqual(профиль["формат"]["длина"], "подробно")   # умолчание
        self.assertIs(профиль["обращение"]["на_ты"], True)

    def test_предел_длины_соответствует_выбору(self):
        для_кратко = preferences.set_value(preferences.blank(), "формат", "длина", "кратко")
        self.assertEqual(preferences.word_limit(для_кратко), 180)
        подробно = preferences.set_value(preferences.blank(), "формат", "длина", "подробно")
        self.assertEqual(preferences.word_limit(подробно), 0)

    def test_язык_кода_молчит_когда_код_не_нужен(self):
        # Иначе в промпт уходит противоречие: «кода не показывай» и «примеры на
        # Python» одновременно.
        профиль = preferences.set_value(preferences.blank(), "формат", "код", "не_нужен")
        self.assertFalse(any("Python" in с for с in preferences.describe(профиль)))

    def test_каждое_поле_умеет_попасть_в_промпт_или_молчать(self):
        профиль = preferences.normalize(preferences.blank())
        for поле in preferences.FIELDS:
            текст = поле.to_prompt(профиль[поле.section][поле.key])
            self.assertIsInstance(текст, str)


class ПроверкаПредпочтений(unittest.TestCase):

    @staticmethod
    def _профиль(**значения):
        профиль = preferences.blank()
        for путь, значение in значения.items():
            раздел, _, ключ = путь.partition("__")
            профиль = preferences.set_value(профиль, раздел, ключ, значение)
        return профиль

    def коды(self, профиль, ответ):
        return {о.code for о in PreferenceChecker(профиль).check(ответ)}

    def test_длина_считается_без_кода(self):
        # Десять строк модели — это не многословие, а ровно то, что просили.
        профиль = self._профиль(формат__длина="кратко")
        ответ = "Коротко.\n```python\n" + "x = 1\n" * 300 + "```"
        self.assertNotIn("длина", self.коды(профиль, ответ))

    def test_длинный_текст_ловится(self):
        профиль = self._профиль(формат__длина="кратко")
        self.assertIn("длина", self.коды(профиль, "слово " * 300))

    def test_допуск_не_придирается_к_паре_слов(self):
        профиль = self._профиль(формат__длина="кратко")
        self.assertNotIn("длина", self.коды(профиль, "слово " * 190))

    def test_код_запрещён_и_найден(self):
        профиль = self._профиль(формат__код="не_нужен")
        self.assertIn("код", self.коды(профиль, "Вот как:\n```python\nx=1\n```"))

    def test_отсутствие_кода_только_замечание(self):
        профиль = self._профиль(формат__код="обязательно")
        расхождения = PreferenceChecker(профиль).check("Объясню словами.")
        по_коду = [о for о in расхождения if о.code == "код"]
        self.assertTrue(по_коду)
        self.assertFalse(по_коду[0].hard, "требовать код на любой вопрос нельзя")

    def test_обращение_на_вы_при_профиле_на_ты(self):
        профиль = self._профиль(обращение__на_ты=True)
        self.assertIn("на_ты", self.коды(профиль, "Вам нужно перенести вашу таблицу."))

    def test_обращение_на_ты_при_профиле_на_вы(self):
        профиль = self._профиль(обращение__на_ты=False)
        self.assertIn("на_ты", self.коды(профиль, "Тебе нужно перенести твою таблицу."))

    def test_вы_внутри_кода_не_считается(self):
        профиль = self._профиль(обращение__на_ты=True)
        ответ = "Сделай так:\n```python\n# передай вам параметр\nf(вам=1)\n```"
        self.assertNotIn("на_ты", self.коды(профиль, ответ))

    def test_имя_требуется_только_когда_просили(self):
        без_имени = self._профиль(обращение__имя="Максим", обращение__по_имени=False)
        self.assertNotIn("имя", self.коды(без_имени, "Ответ без имени."))
        с_именем = self._профиль(обращение__имя="Максим", обращение__по_имени=True)
        self.assertIn("имя", self.коды(с_именем, "Ответ без имени."))
        self.assertNotIn("имя", self.коды(с_именем, "Максим, вот ответ."))

    def test_язык_ответа(self):
        профиль = self._профиль(формат__язык="русский")
        английский = "This is a long answer written entirely in English without any Russian."
        self.assertIn("язык", self.коды(профиль, английский))
        self.assertNotIn("язык", self.коды(профиль, "Это длинный ответ по-русски, "
                                                    "с именами вроде LineStringField."))

    def test_короткая_строка_не_считается_сменой_языка(self):
        профиль = self._профиль(формат__язык="русский")
        self.assertNotIn("язык", self.коды(профиль, "OK"))

    def test_структура_проверяется_мягко(self):
        профиль = self._профиль(формат__структура="таблицы")
        расхождения = PreferenceChecker(профиль).check("Просто текст без таблицы.")
        self.assertTrue(расхождения)
        self.assertFalse(any(о.hard for о in расхождения if о.code == "структура"))

    def test_подходящий_ответ_проходит_чисто(self):
        профиль = self._профиль(обращение__имя="Максим", обращение__по_имени=True,
                                обращение__на_ты=True, формат__длина="кратко",
                                формат__код="не_нужен", формат__структура="списки")
        ответ = ("Максим, порядок такой:\n"
                 "- выгрузи схему таблицы\n"
                 "- опиши модель\n"
                 "- прогони миграцию")
        self.assertEqual(PreferenceChecker(профиль).check(ответ), [])

    def test_напоминание_говорит_что_исправить(self):
        профиль = self._профиль(формат__длина="кратко")
        расхождения = PreferenceChecker(профиль).check("слово " * 300)
        self.assertIn("180", PreferenceChecker(профиль).reminder(расхождения))


# --- мастер настройки ---------------------------------------------------------

class МастерНастройки(unittest.TestCase):

    def test_вопросы_берутся_из_описания_полей(self):
        # Одно описание на всё приложение: добавили предпочтение — вопрос
        # появился сам, и разъехаться им негде.
        self.assertEqual(len(interview.questions()), len(preferences.FIELDS))

    def test_пустой_профиль_просит_настройки(self):
        self.assertTrue(interview.needs_setup({}))

    def test_после_мастера_настройка_не_нужна(self):
        профиль = interview.apply({}, {"формат/длина": "кратко"})
        self.assertFalse(interview.needs_setup(профиль))

    def test_пропущенный_вопрос_ничего_не_меняет(self):
        профиль = interview.apply({}, {"формат/длина": "кратко", "обращение/имя": "  "})
        self.assertEqual(профиль["формат"]["длина"], "кратко")
        self.assertEqual(preferences.normalize(профиль)["обращение"]["имя"], "")

    def test_ключ_без_раздела_тоже_понимается(self):
        профиль = interview.apply({}, {"длина": "средне"})
        self.assertEqual(профиль["формат"]["длина"], "средне")

    def test_негодный_ответ_отклоняется(self):
        with self.assertRaises(PreferenceError):
            interview.apply({}, {"формат/длина": "быстро"})

    def test_заготовка_стирает_то_чего_в_ней_нет(self):
        # Иначе человек берёт «тимлид» с именем Максим, переключается на
        # «инженер», у которой имени нет, — и остаётся Максимом.
        профиль = interview.from_template("тимлид")
        self.assertEqual(preferences.normalize(профиль)["обращение"]["имя"], "Максим")
        профиль = interview.from_template("инженер", профиль)
        self.assertEqual(preferences.normalize(профиль)["обращение"]["имя"], "")
        self.assertFalse(preferences.normalize(профиль)["обращение"]["по_имени"])

    def test_пропущенный_вопрос_мастера_по_прежнему_не_стирает(self):
        # У мастера правило обратное: пустой ответ — «оставить как есть».
        профиль = interview.from_template("тимлид")
        профиль = interview.apply(профиль, {"обращение/имя": "   "})
        self.assertEqual(preferences.normalize(профиль)["обращение"]["имя"], "Максим")

    def test_все_заготовки_корректны(self):
        for имя in interview.TEMPLATES:
            профиль = interview.from_template(имя)
            self.assertFalse(interview.needs_setup(профиль))
            self.assertTrue(профиль.get("контекст"))

    def test_заготовки_действительно_разные(self):
        сводки = {и: preferences.summary(interview.from_template(и))
                  for и in interview.TEMPLATES}
        self.assertEqual(len(set(сводки.values())), len(сводки), сводки)


# --- сценарии -----------------------------------------------------------------

class Сценарии(unittest.TestCase):

    def setUp(self) -> None:
        self.каталог = tempfile.mkdtemp()
        self.хранилище = ScenarioStore(os.path.join(self.каталог, "scenarios.json"))

    def tearDown(self) -> None:
        shutil.rmtree(self.каталог, ignore_errors=True)

    @staticmethod
    def _рабочий():
        return Scenario(
            имя="напиши фичу", триггеры=["напиши фичу"],
            шаги=[
                Step("аналитик", "собрать требования", роль="планирование", стадия=PLANNING),
                Step("backend", "написать код", роль="исполнение", стадия=EXECUTION,
                     вход=["аналитик"]),
                Step("ревьюер", "проверить", роль="исполнение", стадия=VALIDATION,
                     вход=["backend"]),
            ],
        )

    def test_корректный_сценарий_проходит(self):
        self._рабочий().validate()

    def test_маршрут_по_стадиям_проверяется(self):
        # Сценарий, который сломается на середине, должен отвалиться до первого
        # вызова модели, а не после того, как потратил токены.
        кривой = Scenario(имя="кривой", шаги=[
            Step("а", "раз", стадия=PLANNING), Step("б", "два", стадия=DONE),
        ])
        with self.assertRaises(ScenarioError):
            кривой.validate()

    def test_повтор_имён_шагов_отклоняется(self):
        двойной = Scenario(имя="двойной", шаги=[
            Step("а", "раз", стадия=PLANNING), Step("а", "два", стадия=EXECUTION),
        ])
        with self.assertRaises(ScenarioError):
            двойной.validate()

    def test_неизвестная_роль_модели_отклоняется(self):
        плохой = Scenario(имя="п", шаги=[Step("а", "раз", роль="телепатия")])
        with self.assertRaises(ScenarioError):
            плохой.validate()

    def test_сценарий_без_шагов_отклоняется(self):
        with self.assertRaises(ScenarioError):
            Scenario(имя="пустой").validate()

    def test_несколько_шагов_на_одной_стадии_разрешены(self):
        подряд = Scenario(имя="подряд", шаги=[
            Step("а", "раз", стадия=PLANNING), Step("б", "два", стадия=PLANNING),
            Step("в", "три", стадия=EXECUTION),
        ])
        подряд.validate()

    def test_триггер_ищется_в_запросе(self):
        сценарий = self._рабочий()
        self.assertTrue(сценарий.matches("Слушай, напиши фичу для отключений"))
        self.assertFalse(сценарий.matches("Как устроена схема gissys?"))

    def test_хранилище_переживает_перезапись(self):
        self.хранилище.add(self._рабочий())
        другое = ScenarioStore(self.хранилище.path)
        self.assertEqual(len(другое.all()), 1)
        self.assertEqual(другое.get("напиши фичу").шаги[0].агент, "аналитик")

    def test_совпадение_по_триггеру_из_хранилища(self):
        self.хранилище.add(self._рабочий())
        self.assertIsNotNone(self.хранилище.match("напиши фичу: подсветка участков"))
        self.assertIsNone(self.хранилище.match("что такое PostGIS?"))

    def test_удаление(self):
        self.хранилище.add(self._рабочий())
        self.assertTrue(self.хранилище.remove("напиши фичу"))
        self.assertFalse(self.хранилище.remove("напиши фичу"))

    def test_негодный_сценарий_не_сохраняется(self):
        with self.assertRaises(ScenarioError):
            self.хранилище.add(Scenario(имя="пустой"))
        self.assertEqual(self.хранилище.all(), [])

    def test_вход_шага_собирается_из_названных_источников(self):
        from agent.scenarios import ScenarioRunner
        шаг = Step("backend", "написать код", вход=["аналитик"])
        текст = ScenarioRunner._вход(шаг, "исходный запрос", {"аналитик": "требования"})
        self.assertIn("требования", текст)
        self.assertNotIn("исходный запрос", текст)
        self.assertIn("написать код", текст)

    def test_отсутствующий_вход_не_ломает_шаг(self):
        from agent.scenarios import ScenarioRunner
        шаг = Step("backend", "написать код", вход=["архитектор"])
        текст = ScenarioRunner._вход(шаг, "исходный запрос", {})
        self.assertIn("исходный запрос", текст)

    def test_длинный_вход_обрезается(self):
        from agent.scenarios import ScenarioRunner, ВХОД_ШАГА
        шаг = Step("b", "делай", вход=["a"])
        текст = ScenarioRunner._вход(шаг, "q", {"a": "х" * (ВХОД_ШАГА * 3)})
        self.assertIn("обрезано", текст)
        self.assertLess(len(текст), ВХОД_ШАГА * 2)


class _ЗаглушкаКлиента:
    """Клиент, который всегда отвечает одним и тем же — и помнит, кого звали."""

    def __init__(self, текст: str) -> None:
        self.текст = текст
        self.вызовы: list[str] = []
        self.spent = {"calls": 0, "tokens": 0, "cost": 0.0}

    def call(self, model_key, messages, **kwargs):
        from agent.llm import Reply
        self.вызовы.append(model_key)
        return Reply(text=self.текст, model_key=model_key)

    def close(self) -> None:
        pass


class ЛестницаПовторов(unittest.TestCase):
    """Из-за чего агент повторяет запрос и из-за чего меняет модель."""

    def setUp(self) -> None:
        from agent import MemoryAgent
        self.каталог = tempfile.mkdtemp()
        self.агент = MemoryAgent(base_dir=self.каталог, router_mode=OFF,
                                 model_key="groq-20b", require_self_report=False,
                                 judge_semantic=False)

    def tearDown(self) -> None:
        self.агент.close()
        shutil.rmtree(self.каталог, ignore_errors=True)

    def _подменить(self, текст: str) -> _ЗаглушкаКлиента:
        заглушка = _ЗаглушкаКлиента(текст)
        self.агент.client = заглушка
        return заглушка

    def test_расхождение_с_профилем_повторяет_на_той_же_модели(self):
        # Платить за ответ вчетверо дороже потому, что он на двадцать слов
        # длиннее просимого, — плохая сделка.
        self.агент.set_preference("формат", "длина", "кратко")
        заглушка = self._подменить("слово " * 400)
        ответ = self.агент.ask("вопрос")
        self.assertTrue(ответ.deviations)
        self.assertGreater(len(заглушка.вызовы), 1, "повтора не было")
        self.assertEqual(set(заглушка.вызовы), {"groq-20b"})
        self.assertEqual(ответ.escalated_to, "")

    def test_нарушение_инварианта_поднимает_модель(self):
        заглушка = self._подменить("Возьмём Laravel, на нём быстрее.")
        ответ = self.агент.ask("вопрос")
        self.assertTrue(ответ.violations)
        self.assertGreater(len(set(заглушка.вызовы)), 1, "эскалации не было")
        self.assertEqual(заглушка.вызовы[0], "groq-20b")

    def test_подходящий_ответ_не_повторяется(self):
        self.агент.set_preference("формат", "длина", "кратко")
        заглушка = self._подменить("Перенесите таблицу миграцией Django.")
        ответ = self.агент.ask("вопрос")
        self.assertEqual(ответ.attempts, 1)
        self.assertEqual(len(заглушка.вызовы), 1)

    def test_служебный_вызов_не_трогает_память(self):
        # Шаг сценария получает на вход машинный текст из результатов предыдущих
        # шагов. Разбирать его маршрутизатором и класть в диалог нельзя: в базу
        # знаний так попадали куски ответов агентов, принятые за слова человека.
        self.агент.memory.router_mode = "авто"
        self.агент.memory.router = _ЗаглушкаМаршрутизатора(
            Routing(target="знания", key="к", value="машинный текст", confidence=0.99)
        )
        self._подменить("Готово.")
        было_знаний = len(self.агент.memory.long.knowledge.all())
        было_реплик = self.агент.memory.short.stats(self.агент.session)["messages"]

        ответ = self.агент.ask("РЕЗУЛЬТАТ ШАГА «архитектор»: …", internal=True)

        self.assertTrue(ответ.text)
        self.assertEqual(len(self.агент.memory.long.knowledge.all()), было_знаний)
        self.assertEqual(
            self.агент.memory.short.stats(self.агент.session)["messages"], было_реплик
        )

    def test_обычный_вызов_память_пополняет(self):
        self.агент.memory.router_mode = "выкл"
        self._подменить("Готово.")
        было = self.агент.memory.short.stats(self.агент.session)["messages"]
        self.агент.ask("обычный вопрос")
        self.assertEqual(
            self.агент.memory.short.stats(self.агент.session)["messages"], было + 2
        )

    def test_отказ_по_инварианту_не_зовёт_маршрутизатор(self):
        """День 16: проверка запроса идёт раньше маршрутизатора.

        Прежде маршрутизатор — вызов дешёвой модели — шёл первым. Отказ «за
        ноль токенов» ждал его ответа (при 429 — минуту-две), а отклонённый
        запрос успевал предложить запись в долговременную память.
        """
        self.агент.memory.router_mode = "авто"
        маршрутизатор = _СчётчикМаршрутизатора(Routing(
            target="профиль", section="ограничения", key="стек", value="Laravel",
            confidence=0.99))
        self.агент.memory.router = маршрутизатор
        заглушка = self._подменить("не должна вызываться")
        было_реплик = self.агент.memory.short.stats(self.агент.session)["messages"]
        было_профиля = self.агент.memory.long.profile.load()

        ответ = self.агент.ask("Перепиши сервис на Laravel")

        self.assertTrue(ответ.blocked)
        self.assertIn("токены не потрачены", ответ.text)
        self.assertEqual(маршрутизатор.вызовы, [], "маршрутизатор позвали до отказа")
        self.assertEqual(заглушка.вызовы, [], "модель позвали до отказа")
        self.assertEqual(self.агент.memory.long.profile.load(), было_профиля)
        # Сама реплика и отказ — часть разговора и в краткосрочной памяти есть.
        self.assertEqual(
            self.агент.memory.short.stats(self.агент.session)["messages"], было_реплик + 2)

    def test_обычный_вопрос_маршрутизатор_видит(self):
        self.агент.memory.router_mode = "авто"
        маршрутизатор = _СчётчикМаршрутизатора(Routing(target="нет"))
        self.агент.memory.router = маршрутизатор
        self._подменить("Перенесите таблицу миграцией Django.")
        self.агент.ask("Как перенести справочник организаций?")
        self.assertEqual(маршрутизатор.вызовы, ["Как перенести справочник организаций?"])

    def test_промежуточный_шаг_профилем_не_проверяется(self):
        self.агент.set_preference("формат", "длина", "кратко")
        заглушка = self._подменить("слово " * 400)
        ответ = self.агент.ask("вопрос", personal=False)
        self.assertEqual(ответ.deviations, [])
        self.assertEqual(len(заглушка.вызовы), 1)


class _Сценарная:
    """Клиент, отвечающий по списку заготовленных ответов."""

    def __init__(self, ответы: list[str]) -> None:
        self.ответы = list(ответы)
        self.вызовы = 0
        self.spent = {"calls": 0, "tokens": 0, "cost": 0.0}

    def call(self, model_key, messages, **kwargs):
        from agent import prompts
        from agent.llm import Reply
        система = messages[0].get("content", "") if messages else ""
        # Ревизор задачи спрашивает не то, что шаг сценария: он ждёт вердикт
        # JSON. Отдать ему очередную реплику из списка значит получить «вердикт
        # не разобран» и лишнюю эскалацию — то есть мерить не то, что проверяем.
        if система.startswith(prompts.REVIEWER[:40]):
            self.вызовы += 1
            return Reply(text='{"сходится":true,"почему":"заглушка ревизора"}',
                         model_key=model_key)
        текст = self.ответы[min(self.вызовы, len(self.ответы) - 1)]
        self.вызовы += 1
        return Reply(text=текст, model_key=model_key)

    def close(self) -> None:
        pass


class ПаузаИПродолжение(unittest.TestCase):
    """Четыре точки останова и продолжение с того же шага.

    Сети тесты не трогают: проверяется машинерия состояния, а не ответы модели.
    """

    ИТОГ = '{"заголовок":"И","решение":"р","причина":"п"} Сделано.'

    def setUp(self) -> None:
        self.каталог = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.каталог, ignore_errors=True)

    def _агент(self, ответы: list[str], **kwargs):
        from agent import MemoryAgent
        # Самоотчёт и суждение модели здесь выключены: проверяется механика
        # паузы, а не инварианты, и заглушка маркера не пишет.
        kwargs.setdefault("require_self_report", False)
        kwargs.setdefault("judge_semantic", False)
        агент = MemoryAgent(base_dir=self.каталог, router_mode=OFF, **kwargs)
        клиент = _Сценарная(ответы)
        агент.client = клиент
        агент.memory.client = клиент
        агент.memory.router.client = клиент
        агент.validator.client = клиент
        агент.заглушка = клиент
        return агент

    @staticmethod
    def _сценарий():
        return Scenario(имя="проба", триггеры=["проба"], шаги=[
            Step("аналитик", "собрать требования", роль="планирование",
                 стадия=PLANNING, вход=["запрос"], может_спросить=True),
            Step("backend", "написать код", роль="исполнение",
                 стадия=EXECUTION, вход=["аналитик"]),
        ])

    def test_шаг_спрашивает_и_сценарий_встаёт(self):
        агент = self._агент(["Часть ясна.\nНУЖНЫ СВЕДЕНИЯ: какой SRID?", self.ИТОГ])
        try:
            агент.add_scenario(self._сценарий())
            итог = агент.run_scenario("проба: слой", name="проба")
            self.assertTrue(итог.на_паузе)
            self.assertEqual(итог.причина_паузы, НЕТ_СВЕДЕНИЙ)
            self.assertEqual(итог.ожидание, ОТВЕТ)
            self.assertIn("SRID", итог.ожидание_текст)
            # Название спросившего шага должно быть в пояснении: указатель к
            # этому моменту уже стоит на следующем.
            self.assertIn("аналитик", итог.ожидание_текст)
        finally:
            агент.close()

    def test_шагу_без_разрешения_вопрос_не_засчитывается(self):
        # backend спрашивать не вправе: получив проект, он должен писать код.
        сценарий = self._сценарий()
        сценарий.шаги[0].может_спросить = False
        агент = self._агент(["Ответ.\nНУЖНЫ СВЕДЕНИЯ: а что именно?", self.ИТОГ])
        try:
            агент.add_scenario(сценарий)
            итог = агент.run_scenario("проба: слой", name="проба")
            self.assertFalse(итог.на_паузе)
        finally:
            агент.close()

    def test_продолжение_идёт_с_того_же_шага_в_новом_агенте(self):
        первый = self._агент(["Часть ясна.\nНУЖНЫ СВЕДЕНИЯ: какой SRID?"])
        try:
            первый.add_scenario(self._сценарий())
            итог = первый.run_scenario("проба: слой", name="проба")
            task_id = итог.task_id
            сделано_до = len(итог.шаги)
        finally:
            первый.close()

        # Новый агент — то же, что новый запуск процесса: всё берётся с диска.
        второй = self._агент([self.ИТОГ])
        try:
            состояние = второй.use_task(task_id)
            self.assertTrue(состояние.пауза)
            итог2 = второй.resume_scenario(task_id, ответ="SRID 3857")
            self.assertFalse(итог2.на_паузе)
            # Главное: пройденный шаг не переигрывается.
            self.assertEqual(сделано_до, 1)
            self.assertEqual(len(итог2.шаги), 1)
            # Шаг, ревизор перед завершением и свёртка задачи в решение.
            # Ревизор появился в этом дне: без отчёта проверки задача в done
            # не переходит.
            self.assertEqual(второй.заглушка.вызовы, 3)
        finally:
            второй.close()

    def test_ответ_человека_попадает_в_следующий_шаг(self):
        первый = self._агент(["Часть ясна.\nНУЖНЫ СВЕДЕНИЯ: какой SRID?"])
        try:
            первый.add_scenario(self._сценарий())
            task_id = первый.run_scenario("проба: слой", name="проба").task_id
        finally:
            первый.close()

        второй = self._агент([self.ИТОГ])
        перехвачено = []
        настоящий = второй.client.call

        def подглядеть(model_key, messages, **kwargs):
            перехвачено.append(messages[-1]["content"])
            return настоящий(model_key, messages, **kwargs)

        второй.client.call = подглядеть
        try:
            второй.use_task(task_id)
            второй.resume_scenario(task_id, ответ="SRID 3857, как у остальных слоёв")
            self.assertTrue(any("3857" in т for т in перехвачено),
                            "ответ человека не дошёл до шага")
        finally:
            второй.close()

    def test_режим_по_шагам_останавливает_на_переходе(self):
        агент = self._агент(["Требования собраны.", self.ИТОГ])
        try:
            агент.add_scenario(self._сценарий())
            итог = агент.run_scenario("проба: слой", name="проба", по_шагам=True)
            self.assertTrue(итог.на_паузе)
            self.assertEqual(итог.причина_паузы, НА_ПЕРЕХОДЕ)
            self.assertEqual(итог.ожидание, ПОДТВЕРДИТЬ)
            # Стадия при этом не сменилась: переход ещё не подтверждён.
            self.assertEqual(агент.task.stage, PLANNING)
            итог2 = агент.resume_scenario(итог.task_id)
            self.assertFalse(итог2.на_паузе)
            # Два шага, ревизор перед завершением и свёртка.
            self.assertEqual(агент.заглушка.вызовы, 4)
        finally:
            агент.close()

    def test_подтверждение_перехода_выполняет_переход(self):
        # Иначе цикл снова видит несменённую стадию и просит подтвердить тот же
        # переход — и так до бесконечности. Ровно это и было.
        агент = self._агент(["Требования собраны.", self.ИТОГ])
        try:
            агент.add_scenario(self._сценарий())
            итог = агент.run_scenario("проба: слой", name="проба", по_шагам=True)
            self.assertEqual(итог.причина_паузы, НА_ПЕРЕХОДЕ)
            итог2 = агент.resume_scenario(итог.task_id, по_шагам=True)
            self.assertEqual(агент.task.stage if агент.task else DONE, DONE,
                             "переход так и не состоялся")
            self.assertFalse(итог2.на_паузе, итог2.ожидание_текст)
        finally:
            агент.close()

    def test_согласие_действует_на_один_переход(self):
        # Три шага на трёх стадиях: подтвердили первый переход — второй должен
        # снова спросить.
        сценарий = self._сценарий()
        сценарий.шаги.append(Step("ревьюер", "проверить", роль="исполнение",
                                  стадия=VALIDATION, вход=["backend"]))
        агент = self._агент(["Раз.", "Два.", "Три.", self.ИТОГ])
        try:
            агент.add_scenario(сценарий)
            итог = агент.run_scenario("проба: слой", name="проба", по_шагам=True)
            self.assertEqual(итог.причина_паузы, НА_ПЕРЕХОДЕ)
            итог2 = агент.resume_scenario(итог.task_id, по_шагам=True)
            self.assertTrue(итог2.на_паузе, "второй переход прошёл без подтверждения")
            self.assertEqual(итог2.причина_паузы, НА_ПЕРЕХОДЕ)
        finally:
            агент.close()

    def test_нарушение_инварианта_ставит_на_паузу_а_не_роняет(self):
        агент = self._агент(["Возьмём Laravel, на нём быстрее."])
        try:
            агент.add_scenario(self._сценарий())
            итог = агент.run_scenario("проба: слой", name="проба")
            self.assertTrue(итог.на_паузе)
            self.assertEqual(итог.причина_паузы, НАРУШЕН_ИНВАРИАНТ)
            self.assertEqual(итог.ожидание, РЕШЕНИЕ)
        finally:
            агент.close()

    def test_пауза_по_команде_останавливает_перед_следующим_шагом(self):
        агент = self._агент(["Требования собраны.", self.ИТОГ])
        try:
            агент.add_scenario(self._сценарий())
            # Пауза ставится из обработчика «после шага» — так же, как её
            # ставит кнопка на странице во время прогона.
            def после(результат, номер, всего):
                if номер == 1:
                    агент.pause_task()

            итог = агент.run_scenario("проба: слой", name="проба", on_result=после)
            self.assertTrue(итог.на_паузе)
            self.assertEqual(итог.причина_паузы, ПО_КОМАНДЕ)
            self.assertEqual(len(итог.шаги), 1)
            self.assertEqual(агент.заглушка.вызовы, 1)
        finally:
            агент.close()

    def test_продолжать_нечего_если_задача_не_по_сценарию(self):
        агент = self._агент([self.ИТОГ])
        try:
            from agent import AgentError
            агент.start_task("ручная", "без сценария")
            with self.assertRaises(AgentError):
                агент.resume_scenario("ручная")
        finally:
            агент.close()


class ОтветСНарушениемНеВыходит(unittest.TestCase):
    """Главное требование дня: нарушающий ответ не доходит до пользователя."""

    def setUp(self) -> None:
        self.каталог = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.каталог, ignore_errors=True)

    def _агент(self, текст: str, **kwargs):
        from agent import MemoryAgent
        kwargs.setdefault("judge_semantic", False)
        kwargs.setdefault("require_self_report", False)
        агент = MemoryAgent(base_dir=self.каталог, router_mode=OFF, **kwargs)
        клиент = _ЗаглушкаКлиента(текст)
        агент.client = клиент
        агент.memory.client = клиент
        агент.memory.router.client = клиент
        агент.validator.client = клиент
        агент.style.client = клиент
        агент.заглушка = клиент
        return агент

    def test_неисправленный_ответ_заменяется_отказом(self):
        # Прежде такой текст уходил пользователю с пометкой blocked. «Отказался
        # предлагать» и «предложил с пометкой» — разные вещи.
        агент = self._агент("Возьмём Laravel, на нём быстрее.")
        try:
            ответ = агент.ask("Опиши слой доступа к данным")
            self.assertTrue(ответ.blocked)
            self.assertNotIn("Laravel, на нём быстрее", ответ.text)
            self.assertIn("Не могу этого предложить", ответ.text)
            self.assertIsNotNone(ответ.refusal)
            # Сам ответ остаётся для разбора, но не как текст пользователю.
            self.assertTrue(ответ.violations)
        finally:
            агент.close()

    def test_в_диалог_попадает_отказ_а_не_нарушение(self):
        агент = self._агент("Возьмём Laravel, на нём быстрее.")
        try:
            агент.ask("Опиши слой доступа к данным")
            реплики = агент.memory.short.all(агент.session)
            последняя = реплики[-1]["content"]
            self.assertIn("Не могу этого предложить", последняя)
            self.assertNotIn("на нём быстрее", последняя)
        finally:
            агент.close()

    def test_отказ_до_вызова_не_тратит_токенов(self):
        агент = self._агент("Ответ.")
        try:
            ответ = агент.ask("Перепиши слой доступа на Laravel")
            self.assertEqual(агент.заглушка.вызовы, [], "модель звали напрасно")
            self.assertEqual(ответ.attempts, 0)
            self.assertIn("токены не потрачены", ответ.text)
        finally:
            агент.close()

    def test_чистый_ответ_проходит_как_прежде(self):
        агент = self._агент("Модель на GeoDjango, поля как в gissys.")
        try:
            ответ = агент.ask("Опиши модель организации")
            self.assertFalse(ответ.blocked)
            self.assertIsNone(ответ.refusal)
            self.assertIn("GeoDjango", ответ.text)
        finally:
            агент.close()

    def test_самоотчёт_вызывает_повтор(self):
        # Заглушка маркера не пишет, значит все попытки уйдут на напоминания.
        агент = self._агент("Ответ без самоотчёта.", require_self_report=True)
        try:
            ответ = агент.ask("Опиши модель организации на Django")
            self.assertGreater(len(агент.заглушка.вызовы), 1)
            self.assertEqual(ответ.самоотчёт, [])
        finally:
            агент.close()

    def test_обрезанный_ответ_не_требует_самоотчёта(self):
        # Самоотчёт стоит последней строкой, и обрезанный ответ не может его
        # содержать. Требовать его — значит трижды получить тот же обрубок.
        from agent.llm import Reply

        агент = self._агент("Ответ оборван на полусло", require_self_report=True)
        try:
            обычный = агент.client.call

            def обрезанный(model_key, messages, **kwargs):
                ответ = обычный(model_key, messages, **kwargs)
                return Reply(text=ответ.text, model_key=model_key,
                             finish_reason="length")

            агент.client.call = обрезанный
            ответ = агент.ask("Опиши модель организации на Django")
            self.assertEqual(len(агент.заглушка.вызовы), 1,
                             "обрезанный ответ ушёл в повторы")
            self.assertFalse(ответ.blocked)
        finally:
            агент.close()

    def test_возведение_решения_в_инвариант(self):
        агент = self._агент("Ответ.")
        try:
            было = len(агент.invariants())
            инвариант = агент.promote_decision(1)
            self.assertEqual(len(агент.invariants()), было + 1)
            self.assertEqual(инвариант.вид, "решение")
            # После возведения он попадает в промпт наравне с остальными.
            self.assertIn(инвариант.код, {и.код for и in агент.invariants()})
        finally:
            агент.close()

    def test_возведение_несуществующего_решения(self):
        from agent import AgentError
        агент = self._агент("Ответ.")
        try:
            with self.assertRaises(AgentError):
                агент.promote_decision(999)
        finally:
            агент.close()


class РазборВопросаШага(unittest.TestCase):
    """Маркер остановки разбирается кодом, а решение принимает модель."""

    def test_маркер_в_конце_ловится(self):
        from agent.scenarios import вопрос_шага
        self.assertEqual(
            вопрос_шага("Всё описано.\nНУЖНЫ СВЕДЕНИЯ: какой SRID у слоя?"),
            "какой SRID у слоя?")

    def test_маркер_в_разметке_ловится(self):
        from agent.scenarios import вопрос_шага
        self.assertIn("SRID", вопрос_шага("Текст.\n**НУЖНЫ СВЕДЕНИЯ:** какой SRID?"))

    def test_упоминание_в_середине_не_считается(self):
        # Иначе пересказ инструкции самой моделью останавливал бы сценарий.
        from agent.scenarios import вопрос_шага
        текст = ("Если бы не хватало данных, я бы написал НУЖНЫ СВЕДЕНИЯ: и перечислил.\n"
                 + "Но данных хватает.\n" * 6)
        self.assertEqual(вопрос_шага(текст), "")

    def test_без_маркера_пусто(self):
        from agent.scenarios import вопрос_шага
        self.assertEqual(вопрос_шага("Обычный ответ без вопросов."), "")


class ХранилищеИнвариантов(unittest.TestCase):
    """Инварианты проекта отдельно от профиля, два уровня, проверяемость."""

    def setUp(self) -> None:
        self.каталог = tempfile.mkdtemp()
        self.склад = InvariantStore(os.path.join(self.каталог, "invariants.json"))

    def tearDown(self) -> None:
        shutil.rmtree(self.каталог, ignore_errors=True)

    @staticmethod
    def _жёсткий(код="стек", значения=("laravel",)):
        return Invariant(код=код, правило="Только Django", вид=inv.СТЕК,
                         тип=inv.ЗАПРЕТ_СЛОВ, значения=list(значения),
                         почему="геометрия в ORM", вместо="GeoDjango")

    def test_жёсткий_без_значений_отклоняется(self):
        # Непроверяемый запрет хуже отсутствующего: создаёт ложное чувство защиты.
        with self.assertRaises(InvariantError):
            self.склад.add(Invariant(код="пустой", правило="нельзя",
                                     тип=inv.ЗАПРЕТ_СЛОВ))

    def test_негодная_регулярка_отклоняется(self):
        with self.assertRaises(InvariantError):
            self.склад.add(Invariant(код="битый", правило="нельзя",
                                     тип=inv.ЗАПРЕТ_РЕГУЛЯРОК,
                                     значения=["[незакрытая"]))

    def test_неизвестный_вид_отклоняется(self):
        with self.assertRaises(InvariantError):
            self.склад.add(Invariant(код="и", правило="п", вид="настроение"))

    def test_негодный_код_отклоняется(self):
        for плохой in ("", "код с пробелом", "../побег", "к" * 60):
            with self.assertRaises(InvariantError):
                self.склад.add(Invariant(код=плохой, правило="п"))

    def test_переживает_запись_и_чтение(self):
        self.склад.add(self._жёсткий())
        другой = InvariantStore(self.склад.path)
        поднят = другой.get("стек")
        self.assertIsNotNone(поднят)
        self.assertEqual(поднят.значения, ["laravel"])
        self.assertEqual(поднят.вид, inv.СТЕК)

    def test_добавление_по_коду_заменяет(self):
        self.склад.add(self._жёсткий())
        self.склад.add(self._жёсткий(значения=("laravel", "symfony")))
        self.assertEqual(len(self.склад.all()), 1)
        self.assertEqual(len(self.склад.get("стек").значения), 2)

    def test_личный_не_снимает_проектный(self):
        # Ослабить общее ограничение под себя нельзя — ровно тот случай, ради
        # которого инварианты и заводят.
        проектный = self._жёсткий()
        личный = Invariant(код="стек", правило="да можно всё", вид=inv.СТЕК,
                           тип=inv.СМЫСЛОВОЙ, уровень=inv.ЛИЧНЫЙ)
        общий = inv.merge([проектный], [личный])
        self.assertEqual(len(общий), 1)
        self.assertEqual(общий[0].правило, "Только Django")
        self.assertEqual(общий[0].уровень, inv.ПРОЕКТНЫЙ)

    def test_личный_добавляет_свой_запрет(self):
        личный = Invariant(код="мой", правило="не предлагать ночные выкатки",
                           вид=inv.БИЗНЕС_ПРАВИЛО, тип=inv.СМЫСЛОВОЙ)
        общий = inv.merge([self._жёсткий()], [личный])
        self.assertEqual({и.код for и in общий}, {"стек", "мой"})
        self.assertEqual(общий[1].уровень, inv.ЛИЧНЫЙ)

    def test_решение_возводится_в_инвариант(self):
        запись = {"id": 3, "заголовок": "Тайлы отдаёт Martin",
                  "решение": "векторные тайлы — Martin", "причина": "быстрее pg_tileserv",
                  "альтернативы": ["pg_tileserv отклонён"]}
        инвариант = inv.from_decision(запись)
        инвариант.validate()
        self.assertEqual(инвариант.вид, inv.РЕШЕНИЕ)
        # Обоснованием отказа служит причина, по которой решение приняли.
        self.assertIn("pg_tileserv", инвариант.почему)
        self.assertIn("pg_tileserv отклонён", инвариант.вместо)
        self.assertIn("№3", инвариант.источник)

    def test_решение_без_заголовка_не_возводится(self):
        with self.assertRaises(InvariantError):
            inv.from_decision({"id": 1, "решение": "что-то"})


class КонфликтЗапроса(ВременнаяПамять):
    """Первый рубеж: требование нарушить инвариант распознаётся до вызова."""

    def setUp(self) -> None:
        super().setUp()
        seed_module.seed(self.память)
        self.валидатор = StateValidator(self.память.all_invariants)

    def test_требование_ловится(self):
        нарушения = self.валидатор.check_request(
            "Перепиши слой доступа к данным на Laravel и дай код модели")
        self.assertTrue(нарушения)
        self.assertEqual(нарушения[0].код, "стек-бэкенд")

    def test_вопрос_об_инварианте_не_ловится(self):
        # Агент обязан уметь объяснить свои ограничения, иначе он вахтёр.
        for вопрос in ("А почему у нас нельзя Laravel?",
                       "Чем плох Laravel для этой задачи?",
                       "Можно ли было взять Laravel?",
                       "Сравни Laravel и Django для геоданных"):
            self.assertEqual(self.валидатор.check_request(вопрос), [], вопрос)

    def test_упоминание_без_повеления_не_ловится(self):
        self.assertEqual(
            self.валидатор.check_request("В соседнем проекте у нас Laravel"), [])

    def test_отказ_в_самом_запросе_не_ловится(self):
        self.assertEqual(
            self.валидатор.check_request("Сделай так, чтобы Laravel не использовался"), [])

    def test_чужая_субд_в_требовании_ловится(self):
        нарушения = self.валидатор.check_request("Давай возьмём MySQL, он привычнее")
        self.assertEqual(нарушения[0].код, "бд")

    def test_вместо_справа_означает_требование(self):
        # «возьмём MySQL вместо PostGIS» — MySQL и есть цель. На живом прогоне
        # проверка запроса приняла это за отказ от MySQL и пропустила.
        нарушения = self.валидатор.check_request(
            "Давай возьмём MySQL вместо PostGIS, команда его лучше знает")
        self.assertTrue(нарушения)
        self.assertEqual(нарушения[0].код, "бд")

    def test_вместо_слева_означает_отказ(self):
        self.assertEqual(
            self.валидатор.check_request("Вместо Laravel возьми Django"), [])

    def test_безобидный_запрос_проходит(self):
        self.assertEqual(
            self.валидатор.check_request("Опиши модель организации на GeoDjango"), [])


class ОтказПоИнварианту(ВременнаяПамять):
    """Как выглядит отказ и из чего он собран."""

    def setUp(self) -> None:
        super().setUp()
        seed_module.seed(self.память)
        self.валидатор = StateValidator(self.память.all_invariants)

    def _отказ(self) -> Refusal:
        нарушения = self.валидатор.check_request("Перепиши всё на Laravel")
        return self.валидатор.refusal(нарушения, "до вызова")

    def test_отказ_называет_инвариант_и_вид(self):
        текст = self._отказ().текст()
        self.assertIn("стек-бэкенд", текст)
        self.assertIn("стек", текст)

    def test_отказ_объясняет_почему(self):
        # «Так нельзя» — не объяснение. В отказ идёт обоснование инварианта.
        self.assertIn("Почему так решено", self._отказ().текст())

    def test_отказ_предлагает_замену(self):
        self.assertIn("Что можно вместо", self._отказ().текст())
        self.assertIn("GeoDjango", self._отказ().текст())

    def test_отказ_до_вызова_говорит_что_токены_не_потрачены(self):
        self.assertIn("токены не потрачены", self._отказ().текст())

    def test_пустой_отказ_пуст(self):
        отказ = self.валидатор.refusal([], "до вызова")
        self.assertFalse(отказ.есть)
        self.assertEqual(отказ.текст(), "")


class Самоотчёт(ВременнаяПамять):
    """Второй рубеж смысловых инвариантов: агент называет учтённое сам."""

    def setUp(self) -> None:
        super().setUp()
        seed_module.seed(self.память)
        self.валидатор = StateValidator(self.память.all_invariants)

    def test_разбор_самоотчёта(self):
        коды = self.валидатор.self_report(
            "Ответ.\nУЧТЕНЫ ИНВАРИАНТЫ: стек-бэкенд, бд (PostGIS)")
        self.assertEqual(коды, ["стек-бэкенд", "бд"])

    def test_разбор_в_разметке(self):
        коды = self.валидатор.self_report("Текст.\n**УЧТЕНЫ ИНВАРИАНТЫ:** стек-бэкенд")
        self.assertEqual(коды, ["стек-бэкенд"])

    def test_без_самоотчёта_пропущены_все_применимые(self):
        применимые = self.валидатор.applicable("напиши модель на Django")
        пропущено = self.валидатор.check_self_report("Просто ответ.", применимые)
        self.assertEqual(set(пропущено), {и.код for и in применимые})

    def test_полный_самоотчёт_проходит(self):
        применимые = self.валидатор.applicable("напиши модель")
        строка = "УЧТЕНЫ ИНВАРИАНТЫ: " + ", ".join(и.код for и in применимые)
        self.assertEqual(self.валидатор.check_self_report("Ответ.\n" + строка,
                                                          применимые), [])

    def test_жёсткие_применимы_всегда(self):
        применимые = {и.код for и in self.валидатор.applicable("любой текст")}
        self.assertIn("стек-бэкенд", применимые)

    def test_смысловой_применим_по_словам(self):
        # Требовать самоотчёт по бизнес-правилу про 1С в ответе про вёрстку
        # карты значило бы приучать агента писать «учтено» не глядя.
        про_1с = {и.код for и in self.валидатор.applicable(
            "как писать объекты сети через 1С")}
        про_вёрстку = {и.код for и in self.валидатор.applicable(
            "поменяй цвет подписи на карте")}
        self.assertIn("1С-источник-истины", про_1с)
        self.assertNotIn("1С-источник-истины", про_вёрстку)

    def test_самоотчёт_первой_строкой(self):
        # Длинный ответ упирается в предел токенов и обрывается: последней
        # строки тогда просто не существует. Первая от обрезки не страдает.
        коды = self.валидатор.self_report(
            "УЧТЕНЫ ИНВАРИАНТЫ: стек-бэкенд, бд\n\nДальше длинный ответ…")
        self.assertEqual(коды, ["стек-бэкенд", "бд"])

    def test_если_применимых_нет_самоотчёт_не_требуется(self):
        self.assertEqual(self.валидатор.check_self_report("Ответ.", []), [])


class ОбъяснениеИнварианта(ВременнаяПамять):
    """Агент обязан уметь объяснить свои ограничения, а не только их применять."""

    def setUp(self) -> None:
        super().setUp()
        seed_module.seed(self.память)
        self.валидатор = StateValidator(self.память.all_invariants)

    def test_вопрос_об_инварианте_распознаётся(self):
        self.assertTrue(self.валидатор.is_explanatory("А почему у нас нельзя Laravel?"))
        self.assertTrue(self.валидатор.is_explanatory("Чем PostGIS лучше MySQL?"))

    def test_обычный_вопрос_объяснением_не_считается(self):
        self.assertFalse(self.валидатор.is_explanatory("Почему индекс не используется?"))
        self.assertFalse(self.валидатор.is_explanatory("Перепиши на Laravel"))

    def test_в_объяснении_упоминание_не_нарушение(self):
        # Объясняя, почему проект не на Laravel, агент обязан назвать Laravel.
        ответ = ("Laravel — популярный PHP-фреймворк с большой экосистемой. "
                 "В Laravel есть Eloquent, миграции и очереди из коробки. "
                 "Laravel хорош там, где геометрия не нужна.")
        self.assertTrue(self.валидатор.check(ответ), "без пометки должно ловиться")
        self.assertEqual(self.валидатор.check(ответ, explanatory=True), [])

    def test_код_на_запрещённом_стеке_ловится_и_в_объяснении(self):
        # Объяснять можно, писать код на запрещённом стеке — нет.
        ответ = "Вот как это выглядело бы:\n```php\n<?php\n$this->load->model(\"x\");\n```"
        self.assertTrue(self.валидатор.check(ответ, explanatory=True))


class СуждениеМодели(ВременнаяПамять):
    """Третий рубеж: смысловые инварианты судит отдельная модель."""

    def setUp(self) -> None:
        super().setUp()
        seed_module.seed(self.память)

    def _валидатор(self, ответ_модели: str):
        class Судья:
            spent = {"calls": 0, "tokens": 0, "cost": 0.0}

            def __init__(self, текст): self.текст = текст; self.вызовы = 0

            def call(self, model_key, messages, **kwargs):
                from agent.llm import Reply
                self.вызовы += 1
                self.сообщения = messages
                return Reply(text=self.текст, model_key=model_key)

            def close(self): pass

        судья = Судья(ответ_модели)
        return StateValidator(self.память.all_invariants, судья), судья

    def test_вердикт_превращается_в_нарушение_с_обоснованием(self):
        валидатор, _ = self._валидатор(
            '{"нарушены":[{"код":"1С-источник-истины","почему":"пишет прямо в gisdata"}]}')
        применимые = валидатор.applicable("пишем объекты через 1С")
        вердикт = валидатор.judge("любой ответ", применимые)
        self.assertEqual(вердикт.нарушены, ["1С-источник-истины"])
        нарушения = валидатор.violations_from_judge(вердикт)
        self.assertTrue(нарушения[0].почему, "обоснование должно браться из инварианта")
        self.assertTrue(нарушения[0].вместо)

    def test_чистый_вердикт_не_даёт_нарушений(self):
        валидатор, _ = self._валидатор('{"нарушены":[]}')
        применимые = валидатор.applicable("пишем объекты через 1С")
        self.assertEqual(валидатор.judge("ответ", применимые).нарушены, [])

    def test_выдуманный_код_отбрасывается(self):
        # Модель может назвать инвариант, которого нет; верить ей нельзя.
        валидатор, _ = self._валидатор('{"нарушены":[{"код":"выдуманный"}]}')
        применимые = валидатор.applicable("пишем объекты через 1С")
        self.assertEqual(валидатор.judge("ответ", применимые).нарушены, [])

    def test_судья_поднимается_на_ступень_при_сбое(self):
        # Проверяющие модели самые слабые, и пустой ответ от них — обычное дело.
        # Без эскалации смысловые инварианты остаются без проверки вовсе, а
        # выглядит это как «нарушений нет».
        валидатор, судья = self._валидатор("мусор")
        применимые = валидатор.applicable("пишем объекты через 1С")
        валидатор.judge("ответ", применимые)
        self.assertEqual(судья.вызовы, 2, "эскалации не было")

    def test_неразбираемый_вердикт_не_роняет(self):
        валидатор, _ = self._валидатор("я не понял задачу")
        применимые = валидатор.applicable("пишем объекты через 1С")
        вердикт = валидатор.judge("ответ", применимые)
        self.assertTrue(вердикт.сбой)
        self.assertEqual(вердикт.нарушены, [])

    def test_судье_не_показывают_запрос_пользователя(self):
        # Проверяющего нечем уговаривать, если он не видит уговоров.
        валидатор, судья = self._валидатор('{"нарушены":[]}')
        применимые = валидатор.applicable("пишем объекты через 1С")
        валидатор.judge("ответ агента", применимые)
        всё = " ".join(с["content"] for с in судья.сообщения)
        self.assertIn("ответ агента", всё)
        self.assertNotIn("пишем объекты через 1С", всё)

    def test_без_смысловых_модель_не_зовётся(self):
        валидатор, судья = self._валидатор('{"нарушены":[]}')
        только_жёсткие = [и for и in валидатор.hard()]
        валидатор.judge("ответ", только_жёсткие)
        self.assertEqual(судья.вызовы, 0, "лишний вызов модели")


# --- каталог моделей ----------------------------------------------------------

class КаталогМоделей(unittest.TestCase):

    def test_у_каждой_роли_есть_модель(self):
        for роль in catalog.ROLES:
            self.assertIn(catalog.for_role(роль, offset=0), catalog.MODELS)

    def test_частые_роли_чередуют_провайдеров(self):
        модели = {catalog.for_role("маршрутизация", offset=i) for i in range(2)}
        провайдеры = {catalog.get(м).provider for м in модели}
        self.assertGreater(len(провайдеры), 1, "частая роль сидит на одном провайдере")

    def test_эскалация_поднимает_на_ступень(self):
        self.assertEqual(catalog.escalate("groq-allam7b"), "groq-20b")
        self.assertEqual(catalog.escalate("groq-20b"), "groq-120b")
        self.assertEqual(catalog.escalate("groq-120b"), "ds-pro")

    def test_с_вершины_лестницы_некуда(self):
        self.assertEqual(catalog.escalate("ds-pro"), "ds-pro")

    def test_модель_вне_лестницы_идёт_на_сильную_бесплатную(self):
        self.assertEqual(catalog.escalate("groq-qwen27b"), "groq-120b")

    def test_неизвестная_роль_даёт_ошибку(self):
        with self.assertRaises(KeyError):
            catalog.for_role("телепатия")


# --- начальное наполнение -----------------------------------------------------

class НачальноеНаполнение(ВременнаяПамять):

    def test_наполняет_пустую_память(self):
        сводка = seed_module.seed(self.память)
        self.assertGreater(сводка["знания"], 0)
        self.assertEqual(len(self.память.invariants.all()), len(seed_module.INVARIANTS))

    def test_не_перезаписывает_заполненную(self):
        seed_module.seed(self.память)
        self.память.long.profile.update("обращение", "тон", "дружелюбный")
        seed_module.seed(self.память)
        self.assertEqual(
            self.память.long.profile.load()["обращение"]["тон"], "дружелюбный"
        )

    def test_жёсткие_инварианты_проверяемы(self):
        seed_module.seed(self.память)
        for инвариант in self.память.invariants.hard():
            self.assertTrue(инвариант.значения,
                            f"инвариант «{инвариант.код}» нечем проверять")

    def test_омоглифы_в_самоотчёте_не_мешают(self):
        # Модель регулярно печатает «1c» латинской c вместо кириллической.
        from agent.validator import StateValidator as SV
        валидатор = SV(self.память.all_invariants)
        применимые = [и for и in валидатор.all() if и.код == "1С-источник-истины"]
        отчёт = "УЧТЕНЫ ИНВАРИАНТЫ: 1C-источник-истины"      # латинская C
        self.assertEqual(валидатор.check_self_report(отчёт, применимые), [])

    def test_у_каждого_инварианта_есть_обоснование(self):
        # Обоснование и альтернатива идут в текст отказа. Инвариант без них
        # даёт отказ «так нельзя», а это не объяснение.
        seed_module.seed(self.память)
        for инвариант in self.память.invariants.all():
            self.assertTrue(инвариант.почему, f"«{инвариант.код}» без обоснования")
            self.assertTrue(инвариант.вместо, f"«{инвариант.код}» без альтернативы")


class ЛимитыПровайдера(unittest.TestCase):
    """Минутный лимит проходит сам, суточный — нет, и путать их нельзя."""

    def test_минутный_лимит_не_считается_суточным(self):
        from agent.llm import _суточный_лимит
        self.assertFalse(_суточный_лимит(
            "Rate limit reached on tokens per minute (TPM): Limit 8000"))

    def test_суточный_лимит_узнаётся(self):
        from agent.llm import _суточный_лимит
        for сообщение in ("on tokens per day (TPD): Limit 200000",
                          "on requests per day (RPD)",
                          "daily quota exceeded"):
            self.assertTrue(_суточный_лимит(сообщение), сообщение)

    def test_суточный_лимит_не_уходит_в_повторы(self):
        # Ждать по минуте четыре раза, чтобы в конце получить ту же ошибку, —
        # это несколько минут, потраченных впустую.
        import httpx
        from agent.llm import Client, LLMError

        клиент = Client()
        попыток = {"счёт": 0}

        def ответ(запрос: httpx.Request) -> httpx.Response:
            попыток["счёт"] += 1
            return httpx.Response(429, json={"error": {
                "message": "Rate limit reached on tokens per day (TPD): Limit 200000"}})

        клиент._http = httpx.Client(transport=httpx.MockTransport(ответ))
        # Ключ нужен только для того, чтобы запрос дошёл до заглушки: без него
        # вызов обрывается раньше HTTP. Тест не должен зависеть от .env —
        # в свежем клоне его нет, и тест падал на «0 попыток».
        from unittest import mock
        модель = catalog.get("groq-120b")
        try:
            with mock.patch.dict(os.environ, {модель.env_var: "test-key"}), \
                    self.assertRaises(LLMError) as поймано:
                клиент.call("groq-120b", [{"role": "user", "content": "привет"}])
            self.assertEqual(попыток["счёт"], 1, "суточный лимит ушёл в повторы")
            self.assertIn("завтра", str(поймано.exception))
        finally:
            клиент.close()


# --- веб-интерфейс ------------------------------------------------------------

class ВебИнтерфейс(unittest.TestCase):
    """Всё, что можно сделать из консоли, должно быть доступно и со страницы.

    Тесты идут через тестовый клиент Flask и сети не трогают: проверяются ручки
    управления, а не ответы модели.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.каталог = tempfile.mkdtemp(prefix="web-test-")
        # web.py создаёт агента при импорте, поэтому каталог памяти задаётся до
        # него — иначе тест писал бы в рабочую память проекта.
        os.environ["MEMORY_DIR"] = cls.каталог
        import importlib
        import web as модуль
        cls.web = importlib.reload(модуль)
        cls.клиент = cls.web.app.test_client()

    @classmethod
    def tearDownClass(cls) -> None:
        os.environ.pop("MEMORY_DIR", None)
        shutil.rmtree(cls.каталог, ignore_errors=True)

    def состояние(self) -> dict:
        return self.клиент.get("/api/state").get_json()

    def test_страница_открывается(self):
        ответ = self.клиент.get("/")
        self.assertEqual(ответ.status_code, 200)

    def test_состояние_описывает_форму_профиля(self):
        # Из этого описания страница рисует и мастер, и поля профиля: списка
        # полей в разметке нет, иначе он разъехался бы с FIELDS.
        состояние = self.состояние()
        self.assertEqual(len(состояние["profile_fields"]), len(preferences.FIELDS))
        self.assertEqual(len(состояние["setup_questions"]), len(preferences.FIELDS))
        self.assertTrue(состояние["roles"])
        self.assertTrue(состояние["stages"])

    def test_мастер_настройки_со_страницы(self):
        ответ = self.клиент.post("/api/profile", json={
            "action": "мастер",
            "answers": {"обращение/имя": "Ольга", "обращение/по_имени": "да",
                        "формат/длина": "кратко"},
        })
        self.assertEqual(ответ.status_code, 200)
        состояние = ответ.get_json()["state"]
        self.assertIn("Ольга", состояние["profile_summary"])
        self.assertFalse(состояние["needs_setup"])

    def test_негодное_предпочтение_отклоняется_с_объяснением(self):
        ответ = self.клиент.post("/api/profile", json={
            "action": "настройка", "section": "формат", "key": "длина",
            "value": "моментально",
        })
        self.assertEqual(ответ.status_code, 400)
        self.assertIn("кратко", ответ.get_json()["error"])

    def test_свой_сценарий_заводится_и_ловится_по_триггеру(self):
        свой = {
            "имя": "проверь миграцию", "описание": "две ступени",
            "триггеры": ["проверь миграцию"],
            "шаги": [
                {"агент": "сверка", "задача": "сверить схему",
                 "роль": "планирование", "стадия": "planning", "вход": ["запрос"]},
                {"агент": "вывод", "задача": "сделать вывод",
                 "роль": "исполнение", "стадия": "execution", "вход": ["сверка"]},
            ],
        }
        ответ = self.клиент.post("/api/scenario/save", json=свой)
        self.assertEqual(ответ.status_code, 200)
        имена = {с["имя"] for с in ответ.get_json()["state"]["scenarios"]}
        self.assertIn("проверь миграцию", имена)

        совпадение = self.клиент.post(
            "/api/match", json={"query": "проверь миграцию справочника"}
        ).get_json()["matched"]
        self.assertEqual(совпадение["имя"], "проверь миграцию")

        удаление = self.клиент.post("/api/scenario/delete",
                                    json={"name": "проверь миграцию"})
        self.assertEqual(удаление.status_code, 200)

    def test_кривой_сценарий_не_сохраняется(self):
        ответ = self.клиент.post("/api/scenario/save", json={
            "имя": "кривой",
            "шаги": [{"агент": "а", "задача": "раз", "стадия": "planning"},
                     {"агент": "б", "задача": "два", "стадия": "done"}],
        })
        self.assertEqual(ответ.status_code, 400)
        # Отказ должен объяснять, что именно не сошлось: страница показывает
        # это пользователю, а не молча теряет правку.
        ошибка = ответ.get_json()["error"]
        self.assertIn("done", ошибка)
        self.assertIn("planning", ошибка)

    def test_автозапуск_сценариев_выключается(self):
        self.клиент.post("/api/settings", json={"auto_scenarios": False})
        совпадение = self.клиент.post(
            "/api/match", json={"query": "напиши фичу: подсветка участков"}
        ).get_json()["matched"]
        self.assertIsNone(совпадение, "автозапуск выключен, а сценарий предложен")
        self.клиент.post("/api/settings", json={"auto_scenarios": True})
        совпадение = self.клиент.post(
            "/api/match", json={"query": "напиши фичу: подсветка участков"}
        ).get_json()["matched"]
        self.assertIsNotNone(совпадение)

    def test_переключение_пользователя(self):
        ответ = self.клиент.post("/api/user", json={"user": "новый-человек"})
        self.assertEqual(ответ.status_code, 200)
        состояние = ответ.get_json()["state"]
        self.assertEqual(состояние["info"]["user_id"], "новый-человек")
        self.assertTrue(состояние["needs_setup"], "новому пользователю не предложили мастер")

    def test_имя_пользователя_с_побегом_отклоняется(self):
        ответ = self.клиент.post("/api/user", json={"user": "../../чужой"})
        self.assertEqual(ответ.status_code, 400)
        # Агент при этом должен остаться прежним, а не исчезнуть.
        self.assertTrue(self.состояние()["info"]["user_id"])

    def test_явная_запись_в_слой(self):
        ответ = self.клиент.post("/api/remember", json={
            "target": "знания", "key": "проба", "value": "в gisdata 37 таблиц",
        })
        self.assertEqual(ответ.status_code, 200)
        self.assertEqual(ответ.get_json()["entry"]["подслой"], "знания")

    def _подменить_клиента(self, клиент):
        """Ставит клиента во все места, где агент его держит, и возвращает прежнего.

        Мест четыре, и это выяснилось неприятным образом: первая версия
        подменяла только два, а маршрутизатор реплик держит свою ссылку — и
        «тесты без сети» тихо ходили в API, отчего набор шёл двадцать пять
        секунд вместо секунды.
        """
        прежний = self.web.agent.client
        self.web.agent.client = клиент
        self.web.agent.memory.client = клиент
        self.web.agent.memory.router.client = клиент
        self.web.agent.validator.client = клиент
        self.web.agent.style.client = клиент
        # Заглушка маркера самоотчёта не пишет, а проверяется здесь не он.
        self.web.agent.require_self_report = False
        self.web.agent.judge_semantic = False
        return прежний

    def _без_сети(self, текст: str = "Готово."):
        заглушка = _ЗаглушкаКлиента(текст)
        return заглушка, self._подменить_клиента(заглушка)

    def _вернуть(self, прежний) -> None:
        self._подменить_клиента(прежний)

    def _дождаться(self, предел: float = 20.0) -> dict:
        конец = time.monotonic() + предел
        while time.monotonic() < конец:
            прогон = self.клиент.get("/api/scenario/status").get_json()["run"]
            if прогон and прогон["готово"]:
                return прогон
            time.sleep(0.05)
        self.fail("сценарий не завершился за отведённое время")

    def test_сценарий_запускается_фоном_и_сразу_отдаёт_страницу(self):
        # Пять шагов идут минуту и дольше. Если держать на это время один
        # HTTP-запрос, страница молчит и отличить работу от зависания нельзя —
        # именно так первая версия и выглядела.
        заглушка, прежний = self._без_сети()
        try:
            пуск = self.клиент.post("/api/scenario",
                                    json={"name": "оцени задачу", "query": "оцени задачу"})
            self.assertEqual(пуск.status_code, 200)
            self.assertIn("run_id", пуск.get_json())
            прогон = self._дождаться()
            self.assertFalse(прогон["ошибка"], прогон["ошибка"])
            self.assertEqual(len(прогон["шаги"]), прогон["всего"])
            self.assertIsNotNone(прогон["state"], "в конце состояние памяти не отдано")
        finally:
            self._вернуть(прежний)

    def test_во_время_прогона_другие_действия_отклоняются(self):
        заглушка, прежний = self._без_сети()
        try:
            self.клиент.post("/api/scenario",
                             json={"name": "оцени задачу", "query": "оцени задачу"})
            # Агент один на процесс, и вести две задачи сразу он не может.
            коды = {
                self.клиент.post("/api/ask", json={"question": "вопрос"}).status_code,
                self.клиент.post("/api/user", json={"user": "кто-то"}).status_code,
            }
            self._дождаться()
            self.assertTrue(коды <= {409, 200},
                            f"неожиданные коды во время прогона: {коды}")
        finally:
            self._вернуть(прежний)

    def test_ошибка_прогона_не_теряется(self):
        # При синхронном запросе сбой возвращался кодом ответа. Теперь прогон
        # идёт в потоке, и ошибку надо донести до страницы отдельно.
        class Падающий(_ЗаглушкаКлиента):
            def call(self, model_key, messages, **kwargs):
                from agent.llm import LLMError
                raise LLMError("провайдер недоступен")

        прежний = self._подменить_клиента(Падающий(""))
        try:
            self.клиент.post("/api/scenario",
                             json={"name": "оцени задачу", "query": "оцени задачу"})
            прогон = self._дождаться()
            self.assertIn("недоступен", прогон["ошибка"])
        finally:
            self._вернуть(прежний)

    def test_статус_без_прогона(self):
        свежий = self.web.app.test_client()
        self.web._прогон.clear()
        self.assertIsNone(свежий.get("/api/scenario/status").get_json()["run"])

    def test_состояние_задачи_отдаётся_страницей(self):
        self.клиент.post("/api/task", json={"action": "создать", "task_id": "сост",
                                            "title": "проверка"})
        состояние = self.состояние()["task_state"]
        self.assertTrue(состояние["есть"])
        for поле in ("этап", "шаг_словами", "ожидание", "ожидание_текст", "пауза"):
            self.assertIn(поле, состояние)
        self.клиент.post("/api/task", json={"action": "отпустить"})

    def test_пауза_и_продолжение_через_страницу(self):
        self.клиент.post("/api/task", json={"action": "создать", "task_id": "пауза-веб",
                                            "title": "проверка"})
        пауза = self.клиент.post("/api/task", json={"action": "пауза"})
        self.assertEqual(пауза.status_code, 200)
        self.assertTrue(пауза.get_json()["state"]["task_state"]["пауза"])
        дальше = self.клиент.post("/api/task", json={"action": "продолжить"})
        self.assertFalse(дальше.get_json()["state"]["task_state"]["пауза"])
        self.клиент.post("/api/task", json={"action": "отпустить"})

    def test_пауза_разрешена_во_время_прогона(self):
        # В этом и смысл кнопки: остановить то, что идёт прямо сейчас. Если
        # блокировать её наравне с остальными действиями, паузы нет вовсе.
        заглушка, прежний = self._без_сети()
        try:
            self.клиент.post("/api/scenario",
                             json={"name": "оцени задачу", "query": "оцени задачу"})
            ответ = self.клиент.post("/api/task", json={"action": "пауза"})
            self._дождаться()
            self.assertIn(ответ.status_code, (200, 400),
                          "пауза во время прогона не должна отклоняться как 409")
        finally:
            self._вернуть(прежний)

    def test_продолжение_сценария_со_страницы(self):
        заглушка, прежний = self._без_сети(
            "Требования собраны.\nНУЖНЫ СВЕДЕНИЯ: какой SRID?")
        try:
            пуск = self.клиент.post(
                "/api/scenario", json={"name": "оцени задачу", "query": "оцени задачу"})
            self.assertEqual(пуск.status_code, 200)
            прогон = self._дождаться()
            self.assertTrue(прогон["на_паузе"], "сценарий не встал на вопросе шага")
            self.assertEqual(прогон["ожидание"], "ответ-пользователя")

            self._вернуть(прежний)
            заглушка2, прежний = self._без_сети("Готово.")
            task_id = self.состояние()["task_state"]["task_id"]
            продолжение = self.клиент.post(
                "/api/scenario/resume",
                json={"task_id": task_id, "answer": "SRID 3857"})
            self.assertEqual(продолжение.status_code, 200)
            итог = self._дождаться()
            self.assertFalse(итог["ошибка"], итог["ошибка"])
        finally:
            self._вернуть(прежний)

    def test_продолжение_учитывает_выбор_страницы(self):
        # «Продолжить» раньше не применяло настройки страницы вовсе: прогон
        # уходил на модель по роли, хотя в шапке выбрана другая. Заметно это
        # становилось после перезапуска сервера, когда агент о выборе человека
        # уже ничего не знал.
        # Задача нарочно несуществующая: тогда ручка отвечает отказом сразу, не
        # запуская фонового прогона, — а настройки страницы к этому моменту уже
        # применены, что и проверяется.
        ответ = self.клиент.post("/api/scenario/resume",
                                 json={"task_id": "нет-такой-задачи", "model": "ds-flash"})
        self.assertEqual(ответ.status_code, 400)
        self.assertEqual(self.web.agent.model_key, "ds-flash")
        self.web.agent.model_key = ""

    def test_запрещённый_переход_задачи_отклоняется(self):
        self.клиент.post("/api/task", json={"action": "создать", "task_id": "проба-веб",
                                            "title": "проверка"})
        ответ = self.клиент.post("/api/task", json={"action": "стадия", "stage": "done"})
        self.assertEqual(ответ.status_code, 400)
        тело = ответ.get_json()
        # Отказ приходит не строкой, а разбором: страница рисует из него правило,
        # обоснование и то, чего не хватает.
        self.assertTrue(тело["refusal"]["текст"])
        self.assertEqual(тело["refusal"]["куда"], "done")
        self.assertEqual(тело["refusal"]["причина"], "в жизненном цикле нет такого перехода")
        # Состояние приходит вместе с отказом — в нём уже видна попытка.
        self.assertEqual(len(тело["state"]["task_state"]["отказы"]), 1)
        self.клиент.post("/api/task", json={"action": "отпустить"})

    def test_ворота_задачи_видны_в_состоянии(self):
        self.клиент.post("/api/task", json={"action": "создать", "task_id": "ворота-веб",
                                            "title": "ворота"})
        состояние = self.состояние()
        переходы = состояние["task_state"]["переходы"]
        self.assertEqual(len(переходы), len(состояние["stages"]))
        закрыт = next(п for п in переходы if п["стадия"] == "execution")
        self.assertFalse(закрыт["можно"])
        self.assertTrue(закрыт["чего_не_хватает"])
        # Условия перехода тоже уходят на страницу: без них редактор не нарисуешь.
        self.assertTrue(состояние["conditions"])
        self.assertTrue(состояние["condition_checks"])
        self.клиент.post("/api/task", json={"action": "отпустить"})

    def test_утверждение_плана_и_проверка_со_страницы(self):
        self.клиент.post("/api/task", json={"action": "создать", "task_id": "цикл-веб",
                                            "title": "цикл"})
        # Плана нет — утверждать нечего, и страница получает внятный отказ.
        пусто = self.клиент.post("/api/task", json={"action": "утвердить-план"})
        self.assertEqual(пусто.status_code, 400)

        self.web.agent.task.set_plan(["разобрать схему", "написать модель"])
        self.web.agent.save_task()
        ответ = self.клиент.post("/api/task", json={"action": "утвердить-план"})
        self.assertEqual(ответ.status_code, 200)
        self.assertEqual(ответ.get_json()["approved"]["пунктов"], 2)

        стадия = self.клиент.post("/api/task", json={"action": "стадия",
                                                     "stage": "execution"})
        self.assertEqual(стадия.status_code, 200)
        проверка = self.клиент.post("/api/task", json={"action": "валидация",
                                                       "ревизор": False})
        self.assertEqual(проверка.status_code, 200)
        отчёт = проверка.get_json()["report"]
        self.assertIn(отчёт["вердикт"], ("прошла", "не прошла"))
        self.клиент.post("/api/task", json={"action": "отпустить"})

    def test_шаг_закрывается_со_страницы(self):
        self.клиент.post("/api/task", json={"action": "создать", "task_id": "шаги-веб",
                                            "title": "шаги"})
        self.web.agent.task.set_plan(["первый", "второй"])
        self.web.agent.save_task()
        self.клиент.post("/api/task", json={"action": "утвердить-план"})
        self.клиент.post("/api/task", json={"action": "стадия", "stage": "execution"})
        закрыт = self.клиент.post("/api/task", json={"action": "закрыть-шаг",
                                                     "value": "сделано"})
        self.assertEqual(закрыт.status_code, 200)
        состояние = закрыт.get_json()["state"]["task_state"]
        self.assertEqual(состояние["шаги"][0]["состояние"], "готов")
        self.assertEqual(состояние["шаг"], 2)
        self.клиент.post("/api/task", json={"action": "отпустить"})

    def test_личное_условие_заводится_и_снимается_со_страницы(self):
        ответ = self.клиент.post("/api/condition", json={
            "action": "добавить", "код": "нужна-ссылка",
            "откуда": "validation", "куда": "done",
            "что": "есть-в-собранном", "значение": "репозиторий",
            "правило": "в готово — только со ссылкой на репозиторий",
        })
        self.assertEqual(ответ.status_code, 200)
        коды = {у["код"] for у in ответ.get_json()["state"]["conditions"]}
        self.assertIn("нужна-ссылка", коды)

        # Базовое условие подменить нельзя — даже со страницы.
        занято = self.клиент.post("/api/condition", json={
            "action": "добавить", "код": "валидация-пройдена",
            "что": "нет-открытых-вопросов", "правило": "ничего не требую"})
        self.assertEqual(занято.status_code, 400)

        снято = self.клиент.post("/api/condition", json={"action": "удалить",
                                                         "код": "нужна-ссылка"})
        self.assertEqual(снято.status_code, 200)
        коды = {у["код"] for у in снято.get_json()["state"]["conditions"]}
        self.assertNotIn("нужна-ссылка", коды)


# --- разметка страницы --------------------------------------------------------

class КонсольЗавершается(unittest.TestCase):
    """Команда, которая что-то сделала, не должна открывать диалог.

    Ловушка, стоившая зависшего прогона: ключи этого дня (--утвердить-план,
    --валидация, --закрыть-шаг, --условие) отрабатывали и проваливались в
    диалоговый режим, где cli.py молча ждёт ввода. В терминале это выглядит как
    зависание, в скрипте — как повисший процесс.
    """

    ДЕЙСТВИЯ = [
        ["--новая-задача", "проба"],
        ["--стадия", "execution"],
        ["--шаг", "ключ=значение"],
        ["--запомни", "знания", "текст"],
        ["--заготовка", "тимлид"],
        ["--настройка", "формат/длина=кратко"],
        ["--инвариант", "код=правило"],
        ["--снять-инвариант", "код"],
        ["--возвести", "1"],
        ["--утвердить-план"],
        ["--снять-утверждение"],
        ["--валидация"],
        ["--закрыть-шаг"],
        ["--условие", "код"],
        ["--снять-условие", "код"],
    ]

    def test_после_действия_диалог_не_открывается(self):
        import cli
        разбор = cli.build_parser()
        for ключи in self.ДЕЙСТВИЯ:
            аргументы = разбор.parse_args(ключи)
            self.assertTrue(cli.меняет_состояние(аргументы),
                            f"после «{' '.join(ключи)}» cli.py уйдёт в диалог и повиснет")

    def test_показывающие_команды_действиями_не_считаются(self):
        # Они и так возвращают результат сами, но список не должен разрастаться
        # до «любая команда завершает работу»: без вопроса и без действия
        # диалог открыться обязан.
        import cli
        разбор = cli.build_parser()
        self.assertFalse(cli.меняет_состояние(разбор.parse_args([])))
        self.assertFalse(cli.меняет_состояние(разбор.parse_args(["--трейс"])))


class СтраницаЦела(unittest.TestCase):
    """Структурные проверки скрипта страницы.

    Появились после поломки, которую не поймал ни один прежний тест: при
    рефакторинге был снят не тот заголовок функции, и «запуститьСценарий»
    оказался объявлен ВНУТРИ «нарисоватьТрейс». Синтаксис при этом остался
    корректным — `node --check` молчал, — а обработчик кнопки падал с
    ReferenceError, и сценарий не запускался вовсе. Проверки Python-кода такого
    не видят в принципе, поэтому нужна отдельная.
    """

    @classmethod
    def setUpClass(cls) -> None:
        import re
        разметка = pathlib.Path(
            os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "templates", "index.html")
        ).read_text(encoding="utf-8")
        найдено = re.search(r"<script>(.*?)</script>", разметка, re.DOTALL)
        assert найдено, "в шаблоне нет блока <script>"
        cls.js = найдено.group(1)
        cls.разметка = разметка

    @staticmethod
    def _без_литералов(строка: str) -> str:
        import re
        return re.sub(r"'[^']*'|\"[^\"]*\"|`[^`]*`|//.*", "", строка)

    def _объявления(self):
        """Имена функций и глубина вложенности, на которой они объявлены."""
        import re
        глубина, итог = 0, []
        for строка in self.js.split("\n"):
            найдено = re.match(r"\s*(async\s+)?function\s+([А-Яа-яёA-Za-z_]+)", строка)
            if найдено:
                итог.append((найдено.group(2), глубина))
            без = self._без_литералов(строка)
            глубина += без.count("{") - без.count("}")
        return итог

    def test_скобки_сходятся(self):
        глубина = 0
        for строка in self.js.split("\n"):
            без = self._без_литералов(строка)
            глубина += без.count("{") - без.count("}")
        self.assertEqual(глубина, 0, "скобки в скрипте страницы не сходятся")

    def test_все_функции_объявлены_на_верхнем_уровне(self):
        вложенные = [(имя, г) for имя, г in self._объявления() if г != 0]
        self.assertEqual(вложенные, [],
                         f"функции объявлены внутри других: {вложенные}")

    def test_обработчики_видят_нужные_функции(self):
        """Всё, что зовут обработчики, должно быть объявлено на верхнем уровне."""
        объявлены = {имя for имя, г in self._объявления() if г == 0}
        обязательные = {
            "запуститьСценарий", "следитьЗаПрогоном", "продолжитьЗадачу",
            "нарисоватьИнварианты", "правитьИнвариант",
            "нарисоватьСостояние", "открытьРедактор", "нарисоватьРедактор",
            "нарисоватьПрофиль", "нарисоватьМастер", "нарисоватьСценарии",
            "нарисоватьСлои", "нарисоватьТрейс", "применить", "спросить",
            "перейтиКПользователю", "правитьПрофиль", "действиеЗадачи",
            "добавить", "запрос", "экранировать",
            # день 16 — панель MCP
            "загрузитьMCP", "осмотретьMCP", "нарисоватьMCP", "секундыMCP",
            "нарисоватьСерверMCP", "нарисоватьИнструментMCP",
        }
        self.assertEqual(обязательные - объявлены, set(),
                         "обработчики зовут функции, которых нет на верхнем уровне")

    def test_каждый_id_из_скрипта_есть_в_разметке(self):
        """$('имя') должно находить элемент, иначе обработчик молча не навесится."""
        import re
        имена = set(re.findall(r"\$\('([^']+)'\)", self.js))
        # Эти элементы рисуются самим скриптом, в статической разметке их нет.
        рисуемые = {"мастер-сохранить", "новый-сценарий", "сц-имя", "сц-описание",
                    "сц-триггеры", "сц-добавить", "сц-сохранить", "сц-отмена",
                    "mcp-все"}
        в_разметке = set(re.findall(r'id="([^"]+)"', self.разметка))
        пропавшие = имена - в_разметке - рисуемые
        self.assertEqual(пропавшие, set(), f"в разметке нет элементов: {пропавшие}")


# --- контролируемые переходы (день 15) ----------------------------------------

class УсловияПерехода(unittest.TestCase):
    """Сами условия: описание, проверка описания, хранение, слияние уровней."""

    def setUp(self) -> None:
        self.каталог = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.каталог, ignore_errors=True)

    def test_базовые_покрывают_оба_примера_задания(self):
        коды = {у.код for у in БАЗОВЫЕ}
        self.assertIn("план-утверждён", коды)
        self.assertIn("валидация-пройдена", коды)
        план = next(у for у in БАЗОВЫЕ if у.код == "план-утверждён")
        self.assertEqual((план.откуда, план.куда), (PLANNING, EXECUTION))
        финал = next(у for у in БАЗОВЫЕ if у.код == "валидация-пройдена")
        self.assertEqual((финал.откуда, финал.куда), (VALIDATION, DONE))

    def test_у_каждого_базового_есть_обоснование_и_выход(self):
        # Отказ состоит из правила, обоснования и подсказки. Условие без них
        # даёт отказ «так нельзя», то есть бесполезный.
        for условие in БАЗОВЫЕ:
            self.assertTrue(условие.правило, условие.код)
            self.assertTrue(условие.почему, условие.код)
            self.assertTrue(условие.вместо, условие.код)

    def test_описание_проверяется(self):
        with self.assertRaises(TransitionConfigError):
            Условие(код="", правило="п").validate()
        with self.assertRaises(TransitionConfigError):
            Условие(код="к", правило="п", что="выдумка").validate()
        with self.assertRaises(TransitionConfigError):
            Условие(код="к", правило="п", откуда="нетакой").validate()
        with self.assertRaises(TransitionConfigError):
            # Проверка «есть в собранном» без ключа проверяет пустоту и всегда
            # проходит: это хуже отсутствующего условия.
            Условие(код="к", правило="п", что=tr.ЕСТЬ_В_СОБРАННОМ).validate()
        Условие(код="к", правило="п", что=tr.ЕСТЬ_В_СОБРАННОМ, значение="ссылка").validate()

    def test_звёздочка_подходит_всем_переходам_кроме_пустого(self):
        любое = Условие(код="л", правило="п", что=tr.НЕТ_ОТКРЫТЫХ_ВОПРОСОВ)
        self.assertTrue(любое.подходит(PLANNING, EXECUTION))
        self.assertTrue(любое.подходит(VALIDATION, DONE))
        # Переход в ту же стадию — не переход, и условие на нём не срабатывает.
        self.assertFalse(любое.подходит(EXECUTION, EXECUTION))

    def test_личное_условие_хранится_и_снимается(self):
        хранилище = ConditionStore(os.path.join(self.каталог, "conditions.json"))
        self.assertEqual(хранилище.all(), [])
        хранилище.add(Условие(код="ссылка", откуда=VALIDATION, куда=DONE,
                              что=tr.ЕСТЬ_В_СОБРАННОМ, значение="репозиторий",
                              правило="в готово — только со ссылкой"))
        self.assertEqual(len(хранилище.all()), 1)
        self.assertEqual(хранилище.get("ссылка").уровень, ЛИЧНЫЙ)
        self.assertTrue(хранилище.remove("ссылка"))
        self.assertFalse(хранилище.remove("ссылка"))

    def test_личное_не_подменяет_базовое(self):
        хранилище = ConditionStore(os.path.join(self.каталог, "conditions.json"))
        with self.assertRaises(TransitionConfigError):
            # Совпадение кода — единственный способ отменить базовое условие,
            # и поэтому он закрыт.
            хранилище.add(Условие(код="валидация-пройдена", правило="ничего не требую",
                                  что=tr.НЕТ_ОТКРЫТЫХ_ВОПРОСОВ))

    def test_слияние_отдаёт_приоритет_базовым(self):
        своё = Условие(код="план-утверждён", правило="подменить", что=tr.НЕТ_ОТКРЫТЫХ_ВОПРОСОВ)
        общие = tr.merge(list(БАЗОВЫЕ), [своё])
        план = [у for у in общие if у.код == "план-утверждён"]
        self.assertEqual(len(план), 1)
        self.assertEqual(план[0].уровень, tr.БАЗОВЫЙ)


class ВоротаПерехода(unittest.TestCase):
    """Проверка перехода: граф, условия, отказ и журнал попыток."""

    def _задача(self, **поля) -> TaskState:
        состояние = TaskState(task_id="проба", title="проба")
        for имя, значение in поля.items():
            setattr(состояние, имя, значение)
        return состояние

    def _готовая_к_проверке(self) -> TaskState:
        состояние = self._задача()
        состояние.set_plan(["разобрать схему", "написать модель"])
        состояние.утвердить_план("человек")
        состояние.transition(EXECUTION, "проба")
        for _ in состояние.шаги:
            состояние.начать_шаг()
            состояние.закончить_шаг("сделано")
        состояние.transition(VALIDATION, "проба")
        return состояние

    def test_маршрут_считается_по_графу(self):
        self.assertEqual(Ворота.маршрут(PLANNING, DONE),
                         [PLANNING, EXECUTION, VALIDATION, DONE])
        self.assertEqual(Ворота.маршрут(VALIDATION, PLANNING),
                         [VALIDATION, EXECUTION, PLANNING])
        # Из done не ведёт ни одна стрелка: задача завершена.
        self.assertEqual(Ворота.маршрут(DONE, PLANNING), [])

    def test_прыжок_через_этап_отклоняется_по_графу(self):
        вердикт = Ворота().проверить(self._задача(), DONE)
        self.assertFalse(вердикт.можно)
        self.assertEqual(вердикт.отказ.причина, tr.НЕТ_СТРЕЛКИ)
        # В отказе есть и законный маршрут, и вердикт по ближайшему шагу.
        self.assertEqual(вердикт.отказ.маршрут[1], EXECUTION)
        self.assertFalse(вердикт.отказ.следующий["можно"])

    def test_реализация_без_утверждённого_плана_закрыта(self):
        состояние = self._задача()
        состояние.set_plan(["шаг"])
        вердикт = Ворота().проверить(состояние, EXECUTION)
        self.assertFalse(вердикт.можно)
        self.assertEqual(вердикт.отказ.причина, tr.НЕ_ВЫПОЛНЕНО)
        self.assertEqual([п.код for п in вердикт.отказ.невыполненные], ["план-утверждён"])
        состояние.утвердить_план("человек")
        self.assertTrue(Ворота().проверить(состояние, EXECUTION).можно)

    def test_правка_плана_снимает_утверждение(self):
        состояние = self._задача()
        состояние.set_plan(["шаг"])
        состояние.утвердить_план("человек")
        self.assertTrue(состояние.утверждение_актуально)
        состояние.set_plan(["шаг", "ещё шаг"])
        # Подпись осталась, но относится к другому плану — значит, не действует.
        self.assertTrue(состояние.план_утверждён)
        self.assertFalse(состояние.утверждение_актуально)
        self.assertFalse(Ворота().проверить(состояние, EXECUTION).можно)

    def test_финал_без_проверки_закрыт(self):
        состояние = self._готовая_к_проверке()
        вердикт = Ворота().проверить(состояние, DONE)
        self.assertFalse(вердикт.можно)
        self.assertEqual([п.код for п in вердикт.отказ.невыполненные],
                         ["валидация-пройдена"])
        состояние.записать_валидацию({"вердикт": "прошла", "пункты": [
            {"пункт": "всё на месте", "итог": "прошло"}]})
        self.assertTrue(Ворота().проверить(состояние, DONE).можно)

    def test_красный_пункт_держит_задачу_незавершённой(self):
        состояние = self._готовая_к_проверке()
        состояние.записать_валидацию({"вердикт": "не прошла", "пункты": [
            {"пункт": "слой отдаётся", "итог": "не прошло", "пояснение": "нет тайлов"}]})
        self.assertFalse(Ворота().проверить(состояние, DONE).можно)

    def test_непроверенный_пункт_переход_не_запирает(self):
        # «Не проверено» — это сбой ревизора, а не дефект работы. Человек не
        # может починить чужой провайдер, и вечно незавершаемая задача хуже.
        состояние = self._готовая_к_проверке()
        состояние.записать_валидацию({"вердикт": "прошла", "пункты": [
            {"пункт": "по смыслу", "итог": "не проверено", "пояснение": "ревизор молчит"}]})
        self.assertTrue(Ворота().проверить(состояние, DONE).можно)

    def test_отчёт_устаревает_когда_работа_поменялась(self):
        состояние = self._готовая_к_проверке()
        состояние.записать_валидацию({"вердикт": "прошла", "пункты": []})
        self.assertTrue(Ворота().проверить(состояние, DONE).можно)
        состояние.remember("новый результат", "переделали слой")
        self.assertFalse(состояние.валидация_актуальна)
        self.assertFalse(Ворота().проверить(состояние, DONE).можно)

    def test_шаги_считаются_по_текущей_стадии(self):
        # Задача по сценарию держит в одном списке шаги всех стадий. Если
        # считать все подряд, стадию исполнения нельзя закрыть, пока не сделан
        # шаг ревьюера, который сам живёт на стадии проверки, — то есть условие
        # запирает сценарий на его же последнем шаге.
        состояние = self._задача()
        состояние.set_steps([
            TaskStep(номер=1, имя="backend", источник=ИЗ_СЦЕНАРИЯ, стадия=EXECUTION),
            TaskStep(номер=2, имя="ревьюер", источник=ИЗ_СЦЕНАРИЯ, стадия=VALIDATION),
        ], сценарий="проба")
        состояние.set_plan(["backend", "ревьюер"])
        состояние.утвердить_план("запуск сценария")
        состояние.transition(EXECUTION, "проба")
        состояние.начать_шаг()
        состояние.закончить_шаг("код готов")
        self.assertTrue(Ворота().проверить(состояние, VALIDATION).можно)

    def test_открытый_вопрос_запирает_любой_переход(self):
        состояние = self._задача()
        состояние.set_plan(["шаг"])
        состояние.утвердить_план("человек")
        состояние.остановить(НЕТ_СВЕДЕНИЙ, ОТВЕТ, "шаг «аналитик» спрашивает: какой SRID?")
        вердикт = Ворота().проверить(состояние, EXECUTION)
        self.assertFalse(вердикт.можно)
        self.assertIn("нет-открытых-вопросов", [п.код for п in вердикт.отказ.невыполненные])
        состояние.ответить("SRID 3857")
        self.assertTrue(Ворота().проверить(состояние, EXECUTION).можно)

    def test_личное_условие_ужесточает_переход(self):
        своё = Условие(код="ссылка", откуда=VALIDATION, куда=DONE,
                       что=tr.ЕСТЬ_В_СОБРАННОМ, значение="репозиторий",
                       правило="в готово — только со ссылкой на репозиторий")
        ворота = Ворота(lambda: tr.merge(list(БАЗОВЫЕ), [своё]))
        состояние = self._готовая_к_проверке()
        состояние.записать_валидацию({"вердикт": "прошла", "пункты": []})
        self.assertFalse(ворота.проверить(состояние, DONE).можно)
        состояние.remember("репозиторий проекта", "git@example")
        состояние.записать_валидацию({"вердикт": "прошла", "пункты": []})
        self.assertTrue(ворота.проверить(состояние, DONE).можно)

    def test_отклонённая_попытка_ложится_в_журнал(self):
        состояние = self._задача()
        ворота = Ворота()
        ворота.перевести(состояние, DONE, МОДЕЛЬ)
        self.assertEqual(len(состояние.отказы), 1)
        запись = состояние.отказы[0]
        self.assertEqual(запись["кто"], МОДЕЛЬ)
        self.assertEqual(запись["куда"], DONE)
        self.assertEqual(состояние.stage, PLANNING)

    def test_состоявшийся_переход_помнит_чем_заслужен(self):
        состояние = self._задача()
        состояние.set_plan(["шаг"])
        состояние.утвердить_план("человек")
        вердикт = Ворота().перевести(состояние, EXECUTION, ЧЕЛОВЕК)
        self.assertTrue(вердикт.выполнен)
        последний = состояние.transitions[-1]
        self.assertEqual(последний["кто"], ЧЕЛОВЕК)
        self.assertIn("план-утверждён", [у["код"] for у in последний["условия"]])

    def test_обзор_показывает_все_стадии(self):
        обзор = Ворота().обзор(self._задача())
        self.assertEqual([с["стадия"] for с in обзор], list(STAGES))
        текущая = [с for с in обзор if с["текущая"]]
        self.assertEqual(len(текущая), 1)
        self.assertEqual(текущая[0]["стадия"], PLANNING)

    def test_отказ_словами_содержит_всё_нужное(self):
        отказ = Ворота().проверить(self._задача(), DONE).отказ
        текст = отказ.текст()
        self.assertIn("планирование", текст)
        self.assertIn("маршрут", текст.lower())
        self.assertIn("Стадию задачи меняет код", текст)

    def test_маркер_просьбы_разбирается_и_убирается(self):
        ответ = "Всё сделано, слой отдаётся.\n\nПЕРЕХОД: done"
        self.assertEqual(tr.просьба(ответ), "done")
        self.assertEqual(tr.убрать_маркер(ответ), "Всё сделано, слой отдаётся.")
        self.assertEqual(tr.просьба("просто ответ без маркера"), "")
        # Несколько просьб — берётся последняя: она про итог работы.
        self.assertEqual(tr.просьба("ПЕРЕХОД: execution\nтекст\nПЕРЕХОД: validation"),
                         "validation")


class ПереходыАгента(unittest.TestCase):
    """Ворота внутри агента: отказ, утверждение, проверка, просьба модели."""

    ПЛАН = "1. Разобрать схему\n2. Написать модель\n3. Отдать слой"

    def setUp(self) -> None:
        self.каталог = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.каталог, ignore_errors=True)

    def _агент(self, ответы: list[str], **kwargs):
        from agent import MemoryAgent
        kwargs.setdefault("require_self_report", False)
        kwargs.setdefault("judge_semantic", False)
        агент = MemoryAgent(base_dir=self.каталог, router_mode=OFF, **kwargs)
        клиент = _Сценарная(ответы)
        агент.client = клиент
        агент.memory.client = клиент
        агент.memory.router.client = клиент
        агент.validator.client = клиент
        агент.заглушка = клиент
        return агент

    def test_прыжок_отклоняется_и_объясняется(self):
        агент = self._агент(["ответ"])
        try:
            агент.start_task("проба", "слой")
            with self.assertRaises(ПереходОтклонён) as поймано:
                агент.transition(DONE)
            self.assertIn("нет такого перехода", str(поймано.exception))
            self.assertEqual(агент.task.stage, PLANNING)
            self.assertEqual(len(агент.task.отказы), 1)
        finally:
            агент.close()

    def test_вердикт_без_перехода_ничего_не_меняет(self):
        агент = self._агент(["ответ"])
        try:
            агент.start_task("проба", "слой")
            вердикт = агент.check_transition(EXECUTION)
            self.assertFalse(вердикт.можно)
            # Проверка — не попытка: журнал отказов остаётся пустым.
            self.assertEqual(агент.task.отказы, [])
        finally:
            агент.close()

    def test_полный_жизненный_цикл_проходится(self):
        агент = self._агент([self.ПЛАН, "код готов",
                             '{"заголовок":"И","решение":"р","причина":"п"}'])
        try:
            агент.start_task("проба", "слой")
            агент.plan()
            with self.assertRaises(ПереходОтклонён):
                агент.transition(EXECUTION)
            агент.approve_plan("Максим")
            агент.transition(EXECUTION)
            for _ in агент.task.шаги:
                агент.task.начать_шаг()
                агент.task.закончить_шаг("сделано")
            агент.transition(VALIDATION)
            агент.remember_step("итог", "слой отдаётся")
            with self.assertRaises(ПереходОтклонён):
                агент.finish_task()
            отчёт = агент.validate_task()
            self.assertEqual(отчёт["вердикт"], "прошла")
            запись = агент.finish_task()
            self.assertTrue(запись["id"])
        finally:
            агент.close()

    def test_просьба_модели_проходит_те_же_ворота(self):
        агент = self._агент(["Задача готова.\n\nПЕРЕХОД: done"])
        try:
            агент.start_task("проба", "слой")
            ответ = агент.ask("Что дальше?")
            self.assertFalse(ответ.переход["можно"])
            self.assertEqual(ответ.переход["кто"], МОДЕЛЬ)
            self.assertEqual(агент.task.stage, PLANNING)
            # Служебная строка наружу не идёт, вместо неё — разбор отказа.
            self.assertNotIn("ПЕРЕХОД: done", ответ.text)
            self.assertIn("Запрос отклонён", ответ.text)
            self.assertEqual(агент.task.отказы[-1]["кто"], МОДЕЛЬ)
        finally:
            агент.close()

    def test_допустимая_просьба_модели_исполняется(self):
        агент = self._агент(["План собран.\n\nПЕРЕХОД: execution"])
        try:
            агент.start_task("проба", "слой")
            агент.task.set_plan(["шаг"])
            агент.approve_plan("Максим")
            ответ = агент.ask("Начинай.")
            self.assertTrue(ответ.переход["можно"])
            self.assertEqual(агент.task.stage, EXECUTION)
            self.assertIn("Стадия задачи переведена", ответ.text)
        finally:
            агент.close()

    def test_служебный_вызов_маркер_не_исполняет(self):
        # Шаг сценария получает машинный вход, и его «ПЕРЕХОД» — это кусок
        # чужого текста, а не обращение к коду. Стадиями там распоряжается
        # исполнитель сценария.
        агент = self._агент(["Итог.\n\nПЕРЕХОД: execution"])
        try:
            агент.start_task("проба", "слой")
            ответ = агент.ask("вход шага", internal=True)
            self.assertEqual(ответ.переход, {})
            self.assertEqual(агент.task.stage, PLANNING)
        finally:
            агент.close()

    def test_сценарий_подписывает_свой_план_и_доходит_до_конца(self):
        агент = self._агент(["собрано", "сделано",
                             '{"заголовок":"И","решение":"р","причина":"п"}'])
        try:
            агент.add_scenario(Scenario(имя="проба", триггеры=["проба"], шаги=[
                Step("аналитик", "собрать", роль="планирование", стадия=PLANNING,
                     вход=["запрос"]),
                Step("backend", "написать", роль="исполнение", стадия=EXECUTION,
                     вход=["аналитик"]),
            ]))
            итог = агент.run_scenario("проба: слой", name="проба")
            self.assertFalse(итог.на_паузе)
            # Сценарий — утверждённый план: подпись в задаче названа запуском.
            self.assertEqual(итог.валидация["вердикт"], "прошла")
            self.assertTrue(итог.решение)
        finally:
            агент.close()

    def test_сценарий_встаёт_на_закрытых_воротах(self):
        агент = self._агент(["собрано", "сделано"])
        try:
            агент.add_condition(Условие(
                код="нужна-ссылка", откуда=PLANNING, куда=EXECUTION,
                что=tr.ЕСТЬ_В_СОБРАННОМ, значение="ссылка на макет",
                правило="к реализации — только с макетом",
                почему="без макета фронтенд переделывают дважды",
                вместо="положите ссылку на макет в собранные данные"))
            агент.add_scenario(Scenario(имя="проба", триггеры=["проба"], шаги=[
                Step("аналитик", "собрать", роль="планирование", стадия=PLANNING,
                     вход=["запрос"]),
                Step("backend", "написать", роль="исполнение", стадия=EXECUTION,
                     вход=["аналитик"]),
            ]))
            итог = агент.run_scenario("проба: слой", name="проба")
            self.assertTrue(итог.на_паузе)
            self.assertEqual(итог.причина_паузы, ЗАКРЫТ_ПЕРЕХОД)
            self.assertEqual(итог.ожидание, РЕШЕНИЕ)
            self.assertIn("нужна-ссылка", итог.отказ_перехода["невыполненные"])
            self.assertEqual(агент.task.stage, PLANNING)
        finally:
            агент.close()

    def test_после_снятия_препятствия_сценарий_продолжается(self):
        # Корректность продолжения после паузы — третья проверка задания дня.
        агент = self._агент(["собрано", "сделано",
                             '{"заголовок":"И","решение":"р","причина":"п"}'])
        try:
            агент.add_condition(Условие(
                код="нужна-ссылка", откуда=PLANNING, куда=EXECUTION,
                что=tr.ЕСТЬ_В_СОБРАННОМ, значение="ссылка на макет",
                правило="к реализации — только с макетом"))
            агент.add_scenario(Scenario(имя="проба", триггеры=["проба"], шаги=[
                Step("аналитик", "собрать", роль="планирование", стадия=PLANNING,
                     вход=["запрос"]),
                Step("backend", "написать", роль="исполнение", стадия=EXECUTION,
                     вход=["аналитик"]),
            ]))
            итог = агент.run_scenario("проба: слой", name="проба")
            self.assertTrue(итог.на_паузе)
            сделано_до = len(итог.шаги)
            агент.remember_step("ссылка на макет", "figma://макет")
            итог2 = агент.resume_scenario(итог.task_id)
            self.assertFalse(итог2.на_паузе)
            # Пройденный шаг не переигрывается: продолжили с того же места.
            self.assertEqual(сделано_до, 1)
            self.assertEqual(len(итог2.шаги), 1)
            self.assertEqual(агент.task, None)
        finally:
            агент.close()

    def test_шаг_задачи_закрывается_руками(self):
        # Задачу, заведённую руками, никто не ведёт по шагам: исполнитель
        # сценария тут не участвует. Без ручного закрытия условие
        # «шаги-доведены» из интерфейса не выполнить, и переход к проверке
        # остался бы закрытым навсегда.
        агент = self._агент(["ответ"])
        try:
            агент.start_task("проба", "слой")
            агент.task.set_plan(["разобрать схему", "написать модель"])
            агент.approve_plan("Максим")
            агент.transition(EXECUTION)
            self.assertFalse(агент.check_transition(VALIDATION).можно)
            агент.close_step("схема разобрана")
            агент.close_step("модель написана")
            self.assertTrue(агент.task.шаги_пройдены)
            self.assertTrue(агент.check_transition(VALIDATION).можно)
            from agent import AgentError
            with self.assertRaises(AgentError):
                агент.close_step()          # открытых шагов больше нет
        finally:
            агент.close()

    def test_условия_берутся_вызовом_а_не_снимком(self):
        агент = self._агент(["ответ"])
        try:
            агент.start_task("проба", "слой")
            агент.task.set_plan(["шаг"])
            агент.approve_plan("Максим")
            self.assertTrue(агент.check_transition(EXECUTION).можно)
            # Условие заводится посреди работы — следующий переход его видит.
            агент.add_condition(Условие(
                код="нужна-ссылка", откуда=PLANNING, куда=EXECUTION,
                что=tr.ЕСТЬ_В_СОБРАННОМ, значение="макет",
                правило="к реализации — только с макетом"))
            self.assertFalse(агент.check_transition(EXECUTION).можно)
        finally:
            агент.close()


# --- MCP (день 16) ---------------------------------------------------------------
#
# Все тесты этого раздела без сети. Настоящее соединение проверяется на своём
# сервере mcp_server.py — он поднимается и по stdio, и по HTTP на свободном
# порту, — а сбои изображают заглушки: команда, которой нет, процесс, который
# падает на старте, сервер, который молчит, и HTTP-сервер, отвечающий 401 и 404.

import json as _json
import socket as _socket
import types
import subprocess as _subprocess
import threading as _threading
from http.server import BaseHTTPRequestHandler as _Обработчик, ThreadingHTTPServer as _HTTPСервер

from unittest import mock

import agent.mcp as amcp
from agent import AgentError, MemoryAgent
from agent.llm import Reply, _разобрать_вызовы as разобрать_вызовы
from agent.mcp import client as mcp_client
from agent.memory.calls import ВЫПОЛНЕНА, ОТКЛОНЕНА, CallStoreError

КОРЕНЬ_ДНЯ = os.path.dirname(os.path.abspath(__file__))
ИНСТРУМЕНТЫ_СВОЕГО = {"list_users", "list_tasks", "get_task", "list_invariants",
                      "list_transition_conditions", "list_decisions"}


def _файл_серверов(каталог: str, серверы: dict, env_файл: str = "") -> str:
    путь = os.path.join(каталог, "mcp-servers.json")
    with open(путь, "w", encoding="utf-8") as файл:
        _json.dump({"mcpServers": серверы}, файл, ensure_ascii=False)
    if env_файл:
        with open(os.path.join(каталог, ".env"), "w", encoding="utf-8") as файл:
            файл.write(env_файл)
    return путь


def _свой_сервер(память: str, **поля) -> dict:
    описание = {"command": "${PYTHON}", "args": [os.path.join(КОРЕНЬ_ДНЯ, "mcp_server.py")],
                "env": {"MEMORY_DIR": память}, "таймаут": 60}
    описание.update(поля)
    return описание


def _свободный_порт() -> int:
    with _socket.socket() as с:
        с.bind(("127.0.0.1", 0))
        return с.getsockname()[1]


def _наполнить_память(каталог: str) -> None:
    рабочая = WorkingMemory(os.path.join(каталог, "working"))
    рабочая.create("перенос-моделей", "схема gissys в GeoDjango",
                   plan=["описать модели", "перенести права"])
    InvariantStore(os.path.join(каталог, "invariants.json")).add(Invariant(
        код="только-django", правило="Бэкенд — только Django", вид=inv.СТЕК,
        тип=inv.ЗАПРЕТ_СЛОВ, значения=["Laravel"], почему="так решили", вместо="Django"))


class КонфигурацияMCP(unittest.TestCase):
    """mcp-servers.json: формат mcpServers, подстановка секретов, фильтр."""

    def setUp(self) -> None:
        self.каталог = tempfile.mkdtemp(prefix="mcp-конфиг-")

    def tearDown(self) -> None:
        shutil.rmtree(self.каталог, ignore_errors=True)

    def загрузить(self, серверы: dict, env_файл: str = "") -> list:
        return amcp.load(_файл_серверов(self.каталог, серверы, env_файл))

    def test_транспорт_по_полям_как_в_стандарте(self):
        серверы = self.загрузить({
            "a": {"command": "npx", "args": ["-y", "пакет"]},
            "b": {"url": "https://example.org/mcp"},
            "c": {"type": "streamable-http", "url": "https://example.org/mcp"},
            "d": {"type": "stdio", "command": "srv"},
        })
        self.assertEqual([с.транспорт for с in серверы], [amcp.STDIO, amcp.HTTP, amcp.HTTP, amcp.STDIO])
        self.assertEqual(серверы[0].аргументы, ["-y", "пакет"])

    def test_нет_файла_пустой_список(self):
        self.assertEqual(amcp.load(os.path.join(self.каталог, "нет.json")), [])

    def test_секрет_подставляется_но_наружу_не_уходит(self):
        сервер, = self.загрузить(
            {"gh": {"type": "http", "url": "https://example.org/mcp",
                    "headers": {"Authorization": "Bearer ${TEST_MCP_TOKEN}"}}},
            env_файл="TEST_MCP_TOKEN=сверхсекрет\n")
        self.assertEqual(сервер.заголовки["Authorization"], "Bearer сверхсекрет")
        self.assertTrue(сервер.готов)
        self.assertNotIn("сверхсекрет", _json.dumps(сервер.to_dict(), ensure_ascii=False))
        self.assertEqual(сервер.to_dict()["заголовки"], ["Authorization"])

    def test_правка_env_видна_без_перезапуска(self):
        """.env главнее окружения: агент сам загрузил его при старте, и правка
        токена при открытой странице иначе не действовала бы."""
        from unittest import mock
        описание = {"gh": {"url": "https://example.org/mcp",
                           "headers": {"Authorization": "Bearer ${TEST_MCP_TOKEN}"}}}
        with mock.patch.dict(os.environ, {"TEST_MCP_TOKEN": "прежний"}):
            сервер, = self.загрузить(описание, env_файл="TEST_MCP_TOKEN=новый\n")
            self.assertEqual(сервер.заголовки["Authorization"], "Bearer новый")
            # пустая строка в .env (как в .env.example) окружение не затирает
            сервер, = self.загрузить(описание, env_файл="TEST_MCP_TOKEN=\n")
            self.assertEqual(сервер.заголовки["Authorization"], "Bearer прежний")

    def test_нет_переменной_сервер_не_готов(self):
        сервер, = self.загрузить({"gh": {"url": "https://example.org/mcp",
                                          "headers": {"Authorization": "Bearer ${MISSING_MCP_TOKEN_XYZ}"}}})
        self.assertFalse(сервер.готов)
        self.assertEqual(сервер.не_хватает, ["MISSING_MCP_TOKEN_XYZ"])
        self.assertIn("MISSING_MCP_TOKEN_XYZ", сервер.почему_не_готов)

    def test_запасное_значение_переменной(self):
        сервер, = self.загрузить({"a": {"command": "srv", "args": ["${MISSING_MCP_TOKEN_XYZ:-запасное}"]}})
        self.assertEqual(сервер.аргументы, ["запасное"])
        self.assertTrue(сервер.готов)

    def test_встроенные_переменные_и_каталог(self):
        сервер, = self.загрузить({"a": {"command": "${PYTHON}", "args": ["${PROJECT_DIR}/s.py"]}})
        self.assertEqual(сервер.команда, sys.executable)
        self.assertEqual(сервер.аргументы, [os.path.join(self.каталог, "s.py")])
        self.assertEqual(сервер.каталог, self.каталог)
        # В показе — как написано: путь к интерпретатору на экране ни к чему.
        self.assertEqual(сервер.куда, "${PYTHON} ${PROJECT_DIR}/s.py")

    def test_относительная_команда_считается_от_файла(self):
        сервер, = self.загрузить({"a": {"command": "./bin/srv"}})
        self.assertEqual(сервер.команда, os.path.join(self.каталог, "bin", "srv"))

    def test_ошибки_описания_понятны(self):
        случаи = {
            "sse": ({"a": {"type": "sse", "url": "https://x/sse"}}, "Streamable HTTP"),
            "тип": ({"a": {"type": "websocket", "url": "https://x"}}, "неизвестный транспорт"),
            "команда": ({"a": {"type": "stdio"}}, "command"),
            "адрес": ({"a": {"type": "http", "url": "ftp://x"}}, "url"),
            "имя": ({"сервер": {"command": "x"}}, "кириллица"),
            "аргументы": ({"a": {"command": "x", "args": [1, 2]}}, "списком строк"),
            "таймаут": ({"a": {"command": "x", "таймаут": -1}}, "таймаут"),
            # кириллица в имени переменной ушла бы на сервер буквальным «${ТОКЕН}»
            "переменная": ({"a": {"url": "https://x/mcp",
                                  "headers": {"Authorization": "Bearer ${ТОКЕН}"}}}, "латиницей"),
        }
        for название, (серверы, фраза) in случаи.items():
            with self.subTest(название):
                with self.assertRaises(amcp.MCPConfigError) as ошибка:
                    self.загрузить(серверы)
                self.assertIn(фраза, str(ошибка.exception))

    def test_битый_файл_и_чужой_формат(self):
        путь = os.path.join(self.каталог, "битый.json")
        pathlib.Path(путь).write_text("{не json", encoding="utf-8")
        with self.assertRaises(amcp.MCPConfigError):
            amcp.load(путь)
        pathlib.Path(путь).write_text('{"servers": {}}', encoding="utf-8")
        with self.assertRaises(amcp.MCPConfigError) as ошибка:
            amcp.load(путь)
        self.assertIn("mcpServers", str(ошибка.exception))

    def test_фильтр_запрет_сильнее_разрешения(self):
        сервер, = self.загрузить({"fs": {"command": "x", "разрешить": ["read_*", "list_*"],
                                          "запретить": ["read_secret*"]}})
        self.assertEqual(сервер.доступ("read_file"), (True, ""))
        self.assertFalse(сервер.доступ("write_file")[0])
        self.assertIn("разрешить", сервер.доступ("write_file")[1])
        закрыт, почему = сервер.доступ("read_secret_key")
        self.assertFalse(закрыт)
        self.assertIn("read_secret*", почему)

    def test_без_фильтра_открыто_всё(self):
        сервер, = self.загрузить({"a": {"command": "x"}})
        self.assertTrue(сервер.доступ("что_угодно")[0])

    def test_отключённый_не_готов(self):
        сервер, = self.загрузить({"a": {"command": "x", "отключён": True}})
        self.assertFalse(сервер.готов)
        self.assertIn("отключён", сервер.почему_не_готов)

    def test_файл_проекта_читается(self):
        """Настоящий mcp-servers.json дня описан верно и секретов в себе не держит."""
        серверы = amcp.load(os.path.join(КОРЕНЬ_ДНЯ, "mcp-servers.json"))
        имена = [с.имя for с in серверы]
        self.assertEqual(имена, ["tracker", "tracker-real", "agent-state", "filesystem",
                                 "everything", "deepwiki", "github"])
        текст = pathlib.Path(КОРЕНЬ_ДНЯ, "mcp-servers.json").read_text(encoding="utf-8")
        self.assertIn("${GITHUB_TOKEN}", текст)
        self.assertIn("${TRACKER_TOKEN}", текст)
        # Ни ключа GitHub, ни OAuth-токена Яндекса в файле быть не может: в нём
        # только ссылки на переменные окружения.
        self.assertNotRegex(текст, r"gh[pous]_[A-Za-z0-9]{20,}|github_pat_|y0__[A-Za-z0-9]{10,}")


class ИнструментMCP(unittest.TestCase):
    """Запись tools/list глазами агента: параметры, доступ, имя и цена для модели."""

    @staticmethod
    def инструмент(**поля):
        import mcp_types
        поля.setdefault("name", "read_file")
        поля.setdefault("inputSchema", {"type": "object", "properties": {}})
        return mcp_types.Tool.model_validate(поля)

    def сервер(self, **поля):
        return amcp.Server(имя="fs", транспорт=amcp.STDIO, команда="x", **поля)

    def test_параметры_типы_и_обязательность(self):
        схема = {"type": "object", "required": ["path"], "properties": {
            "tail": {"type": "integer", "description": "последние строки"},
            "path": {"type": "string", "description": "путь к файлу"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "mode": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "kind": {"enum": ["a", "b"]},
        }}
        и = amcp.Tool.from_sdk(self.инструмент(inputSchema=схема), self.сервер())
        параметры = и.parameters()
        self.assertEqual(параметры[0].имя, "path")          # обязательные — вперёд
        self.assertTrue(параметры[0].обязательный)
        типы = {п.имя: п.тип for п in параметры}
        self.assertEqual(типы, {"path": "string", "tail": "integer", "tags": "array<string>",
                                "mode": "string", "kind": "enum"})
        self.assertEqual(next(п for п in параметры if п.имя == "kind").варианты, ["a", "b"])

    def test_доступ_по_пометкам_сервера(self):
        случаи = [
            (None, "не заявлено"),
            ({"readOnlyHint": True}, "только чтение"),
            ({"readOnlyHint": False, "destructiveHint": False}, "меняет данные"),
            ({"idempotentHint": True}, "может удалять"),   # destructiveHint по умолчанию истинно
        ]
        for пометки, ожидаем in случаи:
            with self.subTest(пометки):
                поля = {"annotations": пометки} if пометки else {}
                и = amcp.Tool.from_sdk(self.инструмент(**поля), self.сервер())
                self.assertEqual(и.доступ, ожидаем)

    def test_фильтр_сервера_применяется_к_инструменту(self):
        сервер = self.сервер(разрешить=["list_*"])
        открыт = amcp.Tool.from_sdk(self.инструмент(name="list_dir"), сервер)
        закрыт = amcp.Tool.from_sdk(self.инструмент(name="write_file"), сервер)
        self.assertTrue(открыт.разрешён)
        self.assertFalse(закрыт.разрешён)
        self.assertTrue(закрыт.почему_закрыт)

    def test_имя_для_модели_без_недопустимых_знаков(self):
        self.assertEqual(amcp.model_name("github", "get.file"), "github__get_file")
        self.assertLessEqual(len(amcp.model_name("s" * 40, "t" * 60)), 64)
        и = amcp.Tool.from_sdk(self.инструмент(name="get-annotated-message"), self.сервер())
        описание = и.for_model()
        self.assertEqual(описание["type"], "function")
        self.assertRegex(описание["function"]["name"], r"^[A-Za-z0-9_-]{1,64}$")

    def test_цена_растёт_вместе_с_описанием(self):
        коротко = amcp.Tool.from_sdk(self.инструмент(description="Читает файл."), self.сервер())
        длинно = amcp.Tool.from_sdk(self.инструмент(description="Читает файл. " * 40), self.сервер())
        self.assertGreater(коротко.tokens(), 0)
        # Обвязка схемы у обоих одна, разница — ровно в тридцати девяти повторах.
        self.assertGreater(длинно.tokens() - коротко.tokens(), 100)


class ПостраничныйСписок(unittest.TestCase):
    """tools/list может прийти частями — собрать нужно все страницы."""

    class _Страницы:
        def __init__(self, страниц: int, бесконечно: bool = False):
            self.страниц, self.бесконечно, self.курсоры = страниц, бесконечно, []

        async def list_tools(self, cursor=None):
            from types import SimpleNamespace
            self.курсоры.append(cursor)
            номер = len(self.курсоры)
            следующая = None if (номер >= self.страниц and not self.бесконечно) else f"с{номер}"
            return SimpleNamespace(tools=[f"инструмент-{номер}"], next_cursor=следующая)

    def test_все_страницы_по_курсору(self):
        import anyio
        клиент = self._Страницы(3)
        инструменты, страниц = anyio.run(mcp_client._все_инструменты, клиент)
        self.assertEqual(страниц, 3)
        self.assertEqual(инструменты, ["инструмент-1", "инструмент-2", "инструмент-3"])
        self.assertEqual(клиент.курсоры, [None, "с1", "с2"])

    def test_бесконечный_курсор_не_вешает(self):
        import anyio
        _, страниц = anyio.run(mcp_client._все_инструменты, self._Страницы(1, бесконечно=True))
        self.assertEqual(страниц, mcp_client.ПРЕДЕЛ_СТРАНИЦ)


class СвойСерверMCP(unittest.TestCase):
    """mcp_server.py: инструменты только читают и не пускают за пределы памяти."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.каталог = tempfile.mkdtemp(prefix="mcp-память-")
        _наполнить_память(cls.каталог)
        cls.прежняя = os.environ.get("MEMORY_DIR")
        os.environ["MEMORY_DIR"] = cls.каталог
        import mcp_server
        cls.модуль = mcp_server

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.прежняя is None:
            os.environ.pop("MEMORY_DIR", None)
        else:
            os.environ["MEMORY_DIR"] = cls.прежняя
        shutil.rmtree(cls.каталог, ignore_errors=True)

    def вызвать(self, имя: str, аргументы: dict | None = None):
        import anyio
        from mcp import Client

        async def вызов():
            async with Client(self.модуль.сервер) as клиент:
                return await клиент.call_tool(имя, аргументы or {})

        return anyio.run(вызов)

    def test_список_инструментов_и_пометки(self):
        import anyio
        from mcp import Client

        async def список():
            async with Client(self.модуль.сервер) as клиент:
                return (await клиент.list_tools()).tools

        инструменты = anyio.run(список)
        self.assertEqual({и.name for и in инструменты}, ИНСТРУМЕНТЫ_СВОЕГО)
        for и in инструменты:
            with self.subTest(и.name):
                self.assertTrue(и.annotations.read_only_hint)
                self.assertFalse(и.annotations.destructive_hint)
                self.assertTrue(и.description)

    def test_задачи_и_состояние_задачи(self):
        итог = self.вызвать("list_tasks")
        self.assertFalse(итог.is_error)
        self.assertEqual([з["task_id"] for з in итог.structured_content["задачи"]], ["перенос-моделей"])
        задача = self.вызвать("get_task", {"task_id": "перенос-моделей"}).structured_content
        self.assertEqual(задача["стадия"], PLANNING)
        закрытые = {п["стадия"]: п for п in задача["переходы"]}
        self.assertFalse(закрытые[EXECUTION]["можно"])     # план не подписан
        self.assertIn("план-утверждён", [у["код"] for у in закрытые[EXECUTION]["чего_не_хватает"]])

    def test_инварианты_проекта(self):
        итог = self.вызвать("list_invariants").structured_content
        self.assertIn("только-django", [и["код"] for и in итог["инварианты"]])

    def test_условия_переходов_включают_базовые(self):
        итог = self.вызвать("list_transition_conditions").structured_content
        self.assertTrue({у.код for у in БАЗОВЫЕ} <= {у["код"] for у in итог["условия"]})

    def test_имя_из_запроса_не_выводит_за_память(self):
        """«../../.env» вместо имени — та самая «логическая бомба» из лекции."""
        for имя in ("../../.env", "a/b", ""):
            with self.subTest(имя):
                итог = self.вызвать("list_decisions", {"user": имя})
                if имя:
                    self.assertTrue(итог.is_error)
                    self.assertIn("Недопустимое имя", итог.content[0].text)
                else:
                    self.assertFalse(итог.is_error)     # пусто — пользователь по умолчанию

    def test_чужая_задача_ошибка_а_не_падение(self):
        итог = self.вызвать("get_task", {"task_id": "нет-такой"})
        self.assertTrue(итог.is_error)

    def test_сервер_ничего_не_создаёт(self):
        пустой = tempfile.mkdtemp(prefix="mcp-пусто-")
        try:
            os.environ["MEMORY_DIR"] = пустой
            self.assertEqual(self.вызвать("list_tasks").structured_content, {"задачи": []})
            self.assertEqual(self.вызвать("list_users").structured_content["пользователи"], [])
            self.assertEqual(os.listdir(пустой), [])
        finally:
            os.environ["MEMORY_DIR"] = self.каталог
            shutil.rmtree(пустой, ignore_errors=True)


class СоединениеMCP(unittest.TestCase):
    """Настоящее соединение: процесс stdio и Streamable HTTP на своём сервере."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.каталог = tempfile.mkdtemp(prefix="mcp-соединение-")
        cls.память = os.path.join(cls.каталог, "memory")
        _наполнить_память(cls.память)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.каталог, ignore_errors=True)

    def сервер(self, **поля) -> "amcp.Server":
        сервер, = amcp.load(_файл_серверов(self.каталог, {"agent-state": _свой_сервер(self.память, **поля)}))
        return сервер

    def test_stdio_рукопожатие_и_список(self):
        осмотр = amcp.inspect(self.сервер())
        self.assertTrue(осмотр.ок, f"{осмотр.этап}: {осмотр.ошибка}\n{осмотр.журнал}")
        р = осмотр.рукопожатие
        self.assertEqual(р.имя, "agent-state")
        self.assertTrue(р.протокол)
        self.assertIn(р.способ, ("server/discover", "initialize"))
        self.assertIn("tools", р.возможности)
        self.assertEqual({и.имя for и in осмотр.инструменты}, ИНСТРУМЕНТЫ_СВОЕГО)
        self.assertTrue(all(и.доступ == "только чтение" for и in осмотр.инструменты))
        self.assertGreaterEqual(осмотр.страниц, 1)
        self.assertGreater(осмотр.токенов, 0)

    def test_список_по_stdio_совпадает_с_тем_что_сервер_объявил(self):
        """Через транспорт пришло ровно то, что сервер объявил у себя, со схемами."""
        import anyio
        from mcp import Client
        import mcp_server

        async def у_себя():
            async with Client(mcp_server.сервер) as клиент:
                return (await клиент.list_tools()).tools

        объявлено = {и.name: и.input_schema for и in anyio.run(у_себя)}
        пришло = {и.имя: и.входная_схема for и in amcp.inspect(self.сервер()).инструменты}
        self.assertEqual(пришло, объявлено)

    def test_http_транспорт(self):
        порт = _свободный_порт()
        процесс = _subprocess.Popen(
            [sys.executable, os.path.join(КОРЕНЬ_ДНЯ, "mcp_server.py"), "--http", str(порт),
             "--память-в", self.память],
            stdout=_subprocess.DEVNULL, stderr=_subprocess.DEVNULL, stdin=_subprocess.DEVNULL)
        try:
            предел = time.monotonic() + 30
            while time.monotonic() < предел:
                try:
                    _socket.create_connection(("127.0.0.1", порт), timeout=0.5).close()
                    break
                except OSError:
                    time.sleep(0.2)
            сервер, = amcp.load(_файл_серверов(self.каталог, {
                "agent-http": {"type": "http", "url": f"http://127.0.0.1:{порт}/mcp"}}))
            осмотр = amcp.inspect(сервер)
            self.assertTrue(осмотр.ок, осмотр.ошибка)
            self.assertEqual(сервер.транспорт, amcp.HTTP)
            self.assertEqual({и.имя for и in осмотр.инструменты}, ИНСТРУМЕНТЫ_СВОЕГО)
        finally:
            процесс.terminate()
            процесс.wait(timeout=10)

    def test_сеанс_переживает_несколько_запросов(self):
        with amcp.Session(self.сервер()) as сеанс:
            первый, _ = сеанс.tools()
            второй, _ = сеанс.tools()
        self.assertEqual([и.имя for и in первый], [и.имя for и in второй])

    def test_фильтр_закрывает_но_показывает(self):
        осмотр = amcp.inspect(self.сервер(разрешить=["list_*"]))
        закрытые = {и.имя for и in осмотр.инструменты if not и.разрешён}
        self.assertEqual(закрытые, {"get_task"})
        self.assertEqual(len(осмотр.инструменты), len(ИНСТРУМЕНТЫ_СВОЕГО))
        self.assertLess(осмотр.токенов, осмотр.токенов_всех)


class _Заглушка(_Обработчик):
    """HTTP-сервер, который отвечает отказом: 401 с WWW-Authenticate или 404."""

    статус = 401

    def do_POST(self):  # noqa: N802 — имя требует http.server
        self.send_response(self.статус)
        if self.статус == 401:
            self.send_header("WWW-Authenticate",
                             'Bearer error="invalid_token", error_description="Token expired"')
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"nope")

    do_GET = do_DELETE = do_POST

    def log_message(self, *args):
        pass


class СбоиMCP(unittest.TestCase):
    """Каждый сбой — понятная причина и подсказка, и ни один не вешает агента."""

    def setUp(self) -> None:
        self.каталог = tempfile.mkdtemp(prefix="mcp-сбои-")

    def tearDown(self) -> None:
        shutil.rmtree(self.каталог, ignore_errors=True)

    def осмотр(self, описание: dict):
        сервер, = amcp.load(_файл_серверов(self.каталог, {"s": описание}))
        return amcp.inspect(сервер)

    def заглушка(self, статус: int):
        класс = type("З", (_Заглушка,), {"статус": статус})
        сервер = _HTTPСервер(("127.0.0.1", 0), класс)
        _threading.Thread(target=сервер.serve_forever, daemon=True).start()
        self.addCleanup(сервер.shutdown)
        return f"http://127.0.0.1:{сервер.server_address[1]}/mcp"

    def test_нет_команды(self):
        о = self.осмотр({"command": "нет-такой-команды-xyz"})
        self.assertFalse(о.ок)
        self.assertEqual(о.этап, mcp_client.ЗАПУСК)
        self.assertIn("не найдена команда", о.ошибка)

    def test_процесс_падает_на_старте_и_виден_его_журнал(self):
        о = self.осмотр({"command": sys.executable,
                         "args": ["-c", "import sys; sys.stderr.write('упал на старте\\n'); sys.exit(3)"]})
        self.assertFalse(о.ок)
        self.assertIn("закрыл соединение", о.ошибка)
        self.assertIn("упал на старте", о.журнал)

    def test_молчащий_сервер_упирается_в_таймаут(self):
        начало = time.monotonic()
        о = self.осмотр({"command": sys.executable, "args": ["-c", "import time; time.sleep(60)"],
                         "таймаут": 1.5})
        self.assertFalse(о.ок)
        self.assertIn("не ответил за 1.5 с", о.ошибка)
        self.assertLess(time.monotonic() - начало, 15, "таймаут не сработал — агент повис бы")

    def test_закрытый_порт(self):
        о = self.осмотр({"type": "http", "url": f"http://127.0.0.1:{_свободный_порт()}/mcp",
                         "таймаут": 5})
        self.assertFalse(о.ок)
        self.assertIn("нет соединения", о.ошибка)

    def test_отказ_авторизации_назван_прямо(self):
        о = self.осмотр({"type": "http", "url": self.заглушка(401), "таймаут": 5})
        self.assertFalse(о.ок)
        self.assertIn("отклонил авторизацию (HTTP 401: Token expired)", о.ошибка)
        self.assertIn("токен", о.подсказка)

    def test_ключи_агента_не_уходят_стороннему_серверу(self):
        """stdio-сервер получает только безопасный минимум окружения и своё env.

        Агент держит в окружении ключи провайдеров (load_dotenv), а в списке
        серверов бывают чужие пакеты из npm. У эталонного сервера есть даже
        инструмент get-env, который отдаёт окружение модели целиком.
        """
        from unittest import mock
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "проверка"}):
            о = self.осмотр({"command": sys.executable, "env": {"SERVER_OWN": "1"}, "args": [
                "-c", "import os, sys; sys.stderr.write(' '.join(sorted(os.environ))); sys.exit(1)"]})
        окружение = set(о.журнал.split())
        self.assertIn("SERVER_OWN", окружение)
        self.assertIn("PATH", окружение)
        self.assertNotIn("DEEPSEEK_API_KEY", окружение)
        self.assertFalse({и for и in окружение if и.endswith("_API_KEY")})

    def test_кириллица_в_токене_названа_прямо(self):
        о = self.осмотр({"type": "http", "url": self.заглушка(401), "таймаут": 5,
                         "headers": {"Authorization": "Bearer токен-по-русски"}})
        self.assertFalse(о.ок)
        self.assertIn("не-латинские символы", о.ошибка)
        self.assertIn(".env", о.подсказка)

    def test_не_тот_адрес(self):
        о = self.осмотр({"type": "http", "url": self.заглушка(404), "таймаут": 5})
        self.assertFalse(о.ок)
        self.assertIn("HTTP 404", о.ошибка)

    def test_не_настроенный_даже_не_подключается(self):
        о = self.осмотр({"url": "https://example.org/mcp",
                         "headers": {"Authorization": "Bearer ${MISSING_MCP_TOKEN_XYZ}"}})
        self.assertTrue(о.пропущен)
        self.assertLess(о.всего_с, 0.5)

    def test_реестр_не_обрывается_на_сломанном(self):
        память = os.path.join(self.каталог, "memory")
        путь = _файл_серверов(self.каталог, {
            "agent-state": _свой_сервер(память),
            "broken": {"command": "нет-такой-команды-xyz"},
            "no-token": {"url": "https://example.org/mcp", "headers": {"X": "${MISSING_MCP_TOKEN_XYZ}"}},
        })
        реестр = amcp.Registry(путь)
        осмотры = реестр.inspect()
        self.assertEqual([о.сервер.имя for о in осмотры], ["agent-state", "broken", "no-token"])
        итог = amcp.summary(осмотры)
        self.assertEqual((итог["подключено"], итог["сбоев"], итог["пропущено"]), (1, 1, 1))
        self.assertEqual(итог["инструментов"], len(ИНСТРУМЕНТЫ_СВОЕГО))
        with self.assertRaises(amcp.MCPConfigError):
            реестр.server("нет-такого")


class КонсольMCP(unittest.TestCase):
    """cli.py --mcp: настоящий процесс, закрытый stdin, диалог не открывается."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.каталог = tempfile.mkdtemp(prefix="mcp-консоль-")
        cls.файл = _файл_серверов(cls.каталог, {
            "agent-state": _свой_сервер(os.path.join(cls.каталог, "memory")),
            "broken": {"command": "нет-такой-команды-xyz"},
            # Токен есть, значит сервер готов и к нему подключатся. Адрес поэтому
            # локальный и закрытый: сети в этих тестах нет.
            "gh": {"url": f"http://127.0.0.1:{_свободный_порт()}/mcp", "таймаут": 5,
                   "headers": {"Authorization": "Bearer ${TEST_MCP_TOKEN}"}},
        }, env_файл="TEST_MCP_TOKEN=сверхсекрет\n")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.каталог, ignore_errors=True)

    def консоль(self, *ключи: str):
        итог = _subprocess.run(
            [sys.executable, os.path.join(КОРЕНЬ_ДНЯ, "cli.py"), "--mcp-файл", self.файл, *ключи],
            capture_output=True, text=True, stdin=_subprocess.DEVNULL, timeout=120,
            env={**os.environ, "MEMORY_DIR": os.path.join(self.каталог, "memory")})
        вывод = итог.stdout + итог.stderr
        self.assertNotIn("Вы:", вывод, "команда открыла диалог")
        return итог.returncode, вывод

    def test_ключи_разбираются(self):
        import cli
        разбор = cli.build_parser()
        self.assertEqual(разбор.parse_args(["--mcp"]).mcp, "*")
        self.assertEqual(разбор.parse_args(["--mcp", "deepwiki"]).mcp, "deepwiki")
        self.assertEqual(разбор.parse_args([]).mcp, "")

    def test_список_серверов_без_подключения_и_без_секрета(self):
        код, вывод = self.консоль("--mcp-серверы")
        self.assertEqual(код, 0, вывод)
        for имя in ("agent-state", "broken", "gh"):
            self.assertIn(имя, вывод)
        self.assertNotIn("сверхсекрет", вывод)

    def test_один_сервер_соединение_и_инструменты(self):
        код, вывод = self.консоль("--mcp", "agent-state")
        self.assertEqual(код, 0, вывод)
        self.assertIn("Соединение: установлено", вывод)
        for имя in ИНСТРУМЕНТЫ_СВОЕГО:
            self.assertIn(имя, вывод)
        self.assertIn("task_id*", вывод)
        self.assertIn("Подключено 1 из 1", вывод)

    def test_схема_по_ключу(self):
        код, вывод = self.консоль("--mcp", "agent-state", "--mcp-схема")
        self.assertEqual(код, 0, вывод)
        self.assertIn('"properties"', вывод)

    def test_сбой_виден_и_даёт_код_ошибки(self):
        код, вывод = self.консоль("--mcp")
        self.assertEqual(код, 1, вывод)
        self.assertIn("НЕ установлено", вывод)
        self.assertIn("не найдена команда", вывод)
        self.assertIn("Подключено 1 из 3", вывод)
        self.assertIn("сбоев 2", вывод)
        self.assertNotIn("сверхсекрет", вывод)

    def test_неизвестный_сервер(self):
        код, вывод = self.консоль("--mcp", "нет-такого")
        self.assertEqual(код, 1)
        self.assertIn("нет-такого", вывод)


class ВебMCP(unittest.TestCase):
    """Панель MCP на странице: те же возможности, что у --mcp в консоли."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.каталог = tempfile.mkdtemp(prefix="mcp-веб-")
        cls.файл = _файл_серверов(cls.каталог, {
            "agent-state": _свой_сервер(os.path.join(cls.каталог, "memory")),
            "broken": {"command": "нет-такой-команды-xyz"},
            # Токен есть, значит сервер готов и к нему подключатся. Адрес поэтому
            # локальный и закрытый: сети в этих тестах нет.
            "gh": {"url": f"http://127.0.0.1:{_свободный_порт()}/mcp", "таймаут": 5,
                   "headers": {"Authorization": "Bearer ${TEST_MCP_TOKEN}"}},
        }, env_файл="TEST_MCP_TOKEN=сверхсекрет\n")
        os.environ["MEMORY_DIR"] = os.path.join(cls.каталог, "memory")
        os.environ["MCP_CONFIG"] = cls.файл
        import importlib
        import web as модуль
        cls.web = importlib.reload(модуль)
        cls.клиент = cls.web.app.test_client()

    @classmethod
    def tearDownClass(cls) -> None:
        os.environ.pop("MEMORY_DIR", None)
        os.environ.pop("MCP_CONFIG", None)
        shutil.rmtree(cls.каталог, ignore_errors=True)

    def test_страница_дня_17(self):
        html = self.клиент.get("/").get_data(as_text=True)
        self.assertIn("<title>Агент миграции ГИС — свой инструмент MCP</title>", html)
        self.assertIn('id="mcp-панель"', html)
        self.assertIn('id="заявки-панель"', html)
        self.assertIn('id="инструменты-вкл"', html)
        self.assertIn("mcp-servers.json", html)

    def test_список_серверов(self):
        ответ = self.клиент.get("/api/mcp")
        self.assertEqual(ответ.status_code, 200)
        данные = ответ.get_json()
        self.assertEqual([с["имя"] for с in данные["servers"]], ["agent-state", "broken", "gh"])
        self.assertNotIn("сверхсекрет", ответ.get_data(as_text=True))

    def test_осмотр_одного_сервера(self):
        данные = self.клиент.post("/api/mcp/inspect", json={"server": "agent-state"}).get_json()
        осмотр, = данные["inspections"]
        self.assertTrue(осмотр["ок"], осмотр["ошибка"])
        self.assertEqual({и["имя"] for и in осмотр["инструменты"]}, ИНСТРУМЕНТЫ_СВОЕГО)
        self.assertEqual(осмотр["рукопожатие"]["имя"], "agent-state")
        self.assertGreater(данные["summary"]["токенов"], 0)

    def test_осмотр_всех_со_сбоем_не_ошибка_запроса(self):
        ответ = self.клиент.post("/api/mcp/inspect", json={})
        self.assertEqual(ответ.status_code, 200)
        итог = ответ.get_json()["summary"]
        self.assertEqual((итог["подключено"], итог["сбоев"], итог["пропущено"]), (1, 2, 0))
        self.assertNotIn("сверхсекрет", ответ.get_data(as_text=True))

    def test_неизвестный_сервер_и_битый_файл(self):
        self.assertEqual(self.клиент.post("/api/mcp/inspect", json={"server": "нет"}).status_code, 400)
        битый = os.path.join(self.каталог, "битый.json")
        pathlib.Path(битый).write_text("{", encoding="utf-8")
        os.environ["MCP_CONFIG"] = битый
        try:
            self.assertEqual(self.клиент.get("/api/mcp").status_code, 400)
        finally:
            os.environ["MCP_CONFIG"] = self.файл



# --- День 17: свой инструмент MCP вокруг API ----------------------------------

ИНСТРУМЕНТЫ_ТРЕКЕРА = {"list_queues", "list_issues", "get_issue"}
МЕНЯЮЩИЕ_ТРЕКЕРА = {"add_comment", "move_issue"}


def _трекер_клиент(каталог: str, **поля):
    """Мок-API трекера как WSGI-приложение: без порта и без сети."""
    import tracker_api

    поля.setdefault("данные", os.path.join(каталог, "tracker-data.json"))
    поля.setdefault("сброс", True)
    return tracker_api.создать(**поля)


def _трекер(приложение, **поля):
    """Клиент MCP-сервера к моку — через WSGI-транспорт httpx, в этом же процессе."""
    import httpx
    import tracker_server

    поля.setdefault("токен", "mock-token")
    поля.setdefault("организация", "mock-org")
    http = httpx.Client(transport=httpx.WSGITransport(app=приложение),
                        base_url="http://tracker.local")
    return tracker_server.Трекер(адрес="http://tracker.local", http=http, **поля)


def _вызвать(сервер, имя: str, аргументы: dict | None = None):
    """Вызов инструмента через настоящий клиент SDK, но без транспорта."""
    import anyio
    from mcp import Client

    async def вызов():
        async with Client(сервер) as клиент:
            return await клиент.call_tool(имя, аргументы or {})

    return anyio.run(вызов)


def _инструменты(сервер) -> list:
    import anyio
    from mcp import Client

    async def список():
        async with Client(сервер) as клиент:
            return (await клиент.list_tools()).tools

    return anyio.run(список)


def _текст(итог) -> str:
    return итог.content[0].text if итог.content else ""


class МокТрекера(unittest.TestCase):
    """tracker_api.py: чужой API, вокруг которого построен MCP-сервер дня.

    Проверяется именно то, чем API отличается от файла: авторизация, коды
    ответов, постраничность и жизненный цикл статусов. Если мок будет вести
    себя иначе, чем настоящий Трекер, обёртка окажется проверенной впустую.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.каталог = tempfile.mkdtemp(prefix="трекер-мок-")
        cls.приложение = _трекер_клиент(cls.каталог)
        cls.клиент = cls.приложение.test_client()
        cls.заголовки = {"Authorization": "OAuth mock-token", "X-Cloud-Org-ID": "mock-org"}

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.каталог, ignore_errors=True)

    def test_без_токена_401(self):
        ответ = self.клиент.get("/v3/myself")
        self.assertEqual(ответ.status_code, 401)
        self.assertIn("Unauthorized", ответ.get_json()["errorMessages"])

    def test_чужая_организация_403(self):
        ответ = self.клиент.get("/v3/myself", headers={
            "Authorization": "OAuth mock-token", "X-Cloud-Org-ID": "чужая"})
        self.assertEqual(ответ.status_code, 403)

    def test_оба_заголовка_организации_годятся(self):
        """У Яндекс 360 организация приходит в X-Org-ID, у Облака — в X-Cloud-Org-ID."""
        for заголовок in ("X-Org-ID", "X-Cloud-Org-ID"):
            with self.subTest(заголовок):
                ответ = self.клиент.get("/v3/myself", headers={
                    "Authorization": "OAuth mock-token", заголовок: "mock-org"})
                self.assertEqual(ответ.status_code, 200)

    def test_поиск_по_фильтру_и_счётчик(self):
        ответ = self.клиент.post("/v3/issues/_search", headers=self.заголовки,
                                 json={"filter": {"queue": "MIG", "status": "open"}})
        ключи = [з["key"] for з in ответ.get_json()]
        self.assertTrue(ключи)
        self.assertTrue(all(к.startswith("MIG-") for к in ключи))
        self.assertEqual(int(ответ.headers["X-Total-Count"]), len(ключи))

    def test_поиск_по_тексту_ищет_и_в_описании(self):
        ответ = self.клиент.post("/v3/issues/_search", headers=self.заголовки,
                                 json={"query": "ST_AsMVT"})
        self.assertEqual([з["key"] for з in ответ.get_json()], ["MIG-3"])

    def test_постранично(self):
        первая = self.клиент.post("/v3/issues/_search", headers=self.заголовки,
                                  json={"filter": {}}, query_string={"perPage": 3, "page": 1})
        вторая = self.клиент.post("/v3/issues/_search", headers=self.заголовки,
                                  json={"filter": {}}, query_string={"perPage": 3, "page": 2})
        self.assertEqual(len(первая.get_json()), 3)
        self.assertTrue(вторая.get_json())
        self.assertNotEqual([з["key"] for з in первая.get_json()],
                            [з["key"] for з in вторая.get_json()])
        self.assertGreater(int(первая.headers["X-Total-Count"]), 3)

    def test_задачи_нет_404(self):
        ответ = self.клиент.get("/v3/issues/MIG-404", headers=self.заголовки)
        self.assertEqual(ответ.status_code, 404)
        self.assertIn("MIG-404", ответ.get_json()["errorMessages"][0])

    def test_комментарий_добавляется_и_виден(self):
        добавлен = self.клиент.post("/v3/issues/MIG-7/comments", headers=self.заголовки,
                                    json={"text": "проверка"})
        self.assertEqual(добавлен.status_code, 201)
        тексты = [к["text"] for к in
                  self.клиент.get("/v3/issues/MIG-7/comments", headers=self.заголовки).get_json()]
        self.assertIn("проверка", тексты)

    def test_пустой_комментарий_отклонён(self):
        ответ = self.клиент.post("/v3/issues/MIG-7/comments", headers=self.заголовки,
                                 json={"text": "   "})
        self.assertEqual(ответ.status_code, 422)

    def test_переход_меняет_статус_и_пишет_комментарий(self):
        ответ = self.клиент.post("/v3/issues/MIG-6/transitions/to_inProgress/_execute",
                                 headers=self.заголовки, json={"comment": "взяли"})
        self.assertEqual(ответ.status_code, 200)
        задача = self.клиент.get("/v3/issues/MIG-6", headers=self.заголовки).get_json()
        self.assertEqual(задача["status"]["key"], "inProgress")
        self.assertEqual(задача["statusType"]["key"], "inProgress")
        тексты = [к["text"] for к in
                  self.клиент.get("/v3/issues/MIG-6/comments", headers=self.заголовки).get_json()]
        self.assertIn("взяли", тексты)

    def test_недопустимый_переход_называет_доступные(self):
        ответ = self.клиент.post("/v3/issues/MIG-7/transitions/to_closed/_execute",
                                 headers=self.заголовки, json={})
        self.assertEqual(ответ.status_code, 422)
        self.assertIn("to_inProgress", ответ.get_json()["errorMessages"][0])

    def test_лимит_запросов(self):
        каталог = tempfile.mkdtemp(prefix="трекер-лимит-")
        try:
            клиент = _трекер_клиент(каталог, лимит=2).test_client()
            коды = [клиент.get("/v3/myself", headers=self.заголовки).status_code
                    for _ in range(4)]
            self.assertEqual(коды[:2], [200, 200])
            self.assertEqual(коды[2], 429)
            ответ = клиент.get("/v3/myself", headers=self.заголовки)
            self.assertEqual(ответ.headers.get("Retry-After"), "60")
        finally:
            shutil.rmtree(каталог, ignore_errors=True)


class СерверТрекера(unittest.TestCase):
    """tracker_server.py: регистрация инструментов, входные параметры, результат."""

    @classmethod
    def setUpClass(cls) -> None:
        import tracker_server

        cls.каталог = tempfile.mkdtemp(prefix="трекер-mcp-")
        cls.приложение = _трекер_клиент(cls.каталог)
        cls.модуль = tracker_server
        cls.сервер = tracker_server.создать_сервер(_трекер(cls.приложение), запись=True)
        cls.только_чтение = tracker_server.создать_сервер(_трекер(cls.приложение), запись=False)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.каталог, ignore_errors=True)

    # --- регистрация инструмента ---------------------------------------------

    def test_инструменты_зарегистрированы_с_пометками(self):
        инструменты = {и.name: и for и in _инструменты(self.сервер)}
        self.assertEqual(set(инструменты), ИНСТРУМЕНТЫ_ТРЕКЕРА | МЕНЯЮЩИЕ_ТРЕКЕРА)
        for имя in ИНСТРУМЕНТЫ_ТРЕКЕРА:
            self.assertTrue(инструменты[имя].annotations.read_only_hint, имя)
        for имя in МЕНЯЮЩИЕ_ТРЕКЕРА:
            self.assertFalse(инструменты[имя].annotations.read_only_hint, имя)
            # Инструмент ходит в чужую систему — это и есть «открытый мир».
            self.assertTrue(инструменты[имя].annotations.open_world_hint, имя)
        for инструмент in инструменты.values():
            self.assertTrue(инструмент.description, инструмент.name)
            self.assertTrue(инструмент.title, инструмент.name)

    def test_без_разрешения_меняющих_инструментов_нет(self):
        """Тот же сервер у настоящего Трекера отдаёт список короче — это и защита."""
        имена = {и.name for и in _инструменты(self.только_чтение)}
        self.assertEqual(имена, ИНСТРУМЕНТЫ_ТРЕКЕРА)

    # --- описание входных параметров -----------------------------------------

    def test_схема_входа_описывает_параметры(self):
        схемы = {и.name: и.input_schema for и in _инструменты(self.сервер)}
        задача = схемы["get_issue"]
        self.assertEqual(задача["required"], ["key"])
        self.assertIn("MIG-2", задача["properties"]["key"]["description"])
        комментарии = задача["properties"]["comments"]
        self.assertEqual((комментарии["minimum"], комментарии["maximum"]), (0, 20))
        список = схемы["list_issues"]["properties"]
        self.assertNotIn("required", схемы["list_issues"])   # все параметры необязательны
        self.assertIn("inProgress", список["status"]["description"])
        self.assertEqual((список["limit"]["minimum"], список["limit"]["maximum"]), (1, 50))
        for имя, поле in список.items():
            self.assertTrue(поле.get("description"), имя)

    def test_предел_параметра_проверяет_sdk(self):
        итог = _вызвать(self.сервер, "list_issues", {"limit": 99})
        self.assertTrue(итог.is_error)
        self.assertIn("less than or equal to 50", _текст(итог))

    # --- возврат результата ---------------------------------------------------

    def test_список_задач_фильтруется(self):
        итог = _вызвать(self.сервер, "list_issues", {"queue": "MIG", "status": "open"})
        self.assertFalse(итог.is_error)
        данные = итог.structured_content
        self.assertEqual(данные["показано"], len(данные["задачи"]))
        self.assertTrue(все := данные["задачи"])
        self.assertTrue(all(з["статус_код"] == "open" for з in все))
        self.assertTrue(all(з["очередь"] == "MIG" for з in все))

    def test_задача_целиком_с_комментариями_и_переходами(self):
        данные = _вызвать(self.сервер, "get_issue",
                          {"key": "MIG-3", "comments": 5}).structured_content
        self.assertEqual(данные["ключ"], "MIG-3")
        self.assertTrue(данные["описание"])
        self.assertTrue(данные["комментарии"])
        self.assertIn("статус", данные["можно_перевести_в"][0])

    def test_ключ_задачи_можно_писать_как_угодно(self):
        данные = _вызвать(self.сервер, "get_issue", {"key": " mig-3 "}).structured_content
        self.assertEqual(данные["ключ"], "MIG-3")

    def test_выжимка_короче_сырого_ответа_api(self):
        """Модели отдаётся выжимка, а не ответ API: лишнее — деньги в каждом запросе."""
        сырой = self.приложение.test_client().get(
            "/v3/issues/MIG-1",
            headers={"Authorization": "OAuth mock-token", "X-Cloud-Org-ID": "mock-org"})
        выжимка = _текст(_вызвать(self.сервер, "get_issue", {"key": "MIG-1", "comments": 0}))
        self.assertLess(len(выжимка), len(сырой.get_data(as_text=True)))
        self.assertNotIn("statusStartTime", выжимка)

    def test_длинное_описание_обрезается(self):
        import tracker_server

        длинное = "ф" * (tracker_server.ОПИСАНИЕ + 500)
        каталог = tempfile.mkdtemp(prefix="трекер-длина-")
        try:
            путь = os.path.join(каталог, "tracker-data.json")
            приложение = _трекер_клиент(каталог)
            данные = _json.loads(pathlib.Path(tracker_server.КОРЕНЬ, "tracker-seed.json")
                                 .read_text(encoding="utf-8"))
            данные["задачи"][0]["description"] = длинное
            pathlib.Path(путь).write_text(_json.dumps(данные, ensure_ascii=False),
                                          encoding="utf-8")
            сервер = tracker_server.создать_сервер(_трекер(приложение), запись=False)
            итог = _вызвать(сервер, "get_issue", {"key": "MIG-1", "comments": 0})
            описание = итог.structured_content["описание"]
            self.assertLess(len(описание), len(длинное))
            self.assertIn("всего", описание)
        finally:
            shutil.rmtree(каталог, ignore_errors=True)

    # --- изменяющие инструменты ----------------------------------------------

    def test_комментарий_доходит_до_api(self):
        итог = _вызвать(self.сервер, "add_comment", {"key": "MIG-4", "text": "из инструмента"})
        self.assertFalse(итог.is_error, _текст(итог))
        задача = _вызвать(self.сервер, "get_issue",
                          {"key": "MIG-4", "comments": 5}).structured_content
        self.assertIn("из инструмента", [к["текст"] for к in задача["комментарии"]])

    def test_перевод_статуса_и_недопустимый_переход(self):
        текущий = _вызвать(self.сервер, "get_issue", {"key": "MIG-8"}).structured_content
        self.assertEqual(текущий["статус_код"], "open")
        отказ = _вызвать(self.сервер, "move_issue", {"key": "MIG-8", "status": "closed"})
        self.assertTrue(отказ.is_error)
        self.assertIn("inProgress", _текст(отказ))
        итог = _вызвать(self.сервер, "move_issue",
                        {"key": "MIG-8", "status": "inProgress", "comment": "взяли в работу"})
        self.assertFalse(итог.is_error, _текст(итог))
        self.assertEqual(итог.structured_content["статус_код"], "inProgress")

    # --- ошибки чужого API становятся понятными -------------------------------

    def test_ключ_из_модели_проверяется_до_запроса(self):
        """«../../etc/passwd» вместо ключа — та самая логическая бомба из лекции."""
        for ключ in ("НЕТ-1", "../../etc/passwd", "MIG 2", ""):
            with self.subTest(ключ):
                итог = _вызвать(self.сервер, "get_issue", {"key": ключ})
                self.assertTrue(итог.is_error)
                self.assertIn("не похоже на ключ задачи", _текст(итог))

    def test_нет_задачи_объяснено(self):
        итог = _вызвать(self.сервер, "get_issue", {"key": "MIG-999"})
        self.assertTrue(итог.is_error)
        self.assertIn("404", _текст(итог))

    def test_токен_не_принят(self):
        import tracker_server

        сервер = tracker_server.создать_сервер(
            _трекер(self.приложение, токен="wrong-token"), запись=False)
        итог = _вызвать(сервер, "list_queues")
        self.assertTrue(итог.is_error)
        self.assertIn("TRACKER_TOKEN", _текст(итог))

    def test_чужая_организация_объяснена(self):
        import tracker_server

        сервер = tracker_server.создать_сервер(
            _трекер(self.приложение, организация="other-org"), запись=False)
        итог = _вызвать(сервер, "list_issues")
        self.assertTrue(итог.is_error)
        self.assertIn("X-Org-ID", _текст(итог))

    def test_кириллица_в_токене_объяснена(self):
        import tracker_server

        сервер = tracker_server.создать_сервер(
            _трекер(self.приложение, токен="токен"), запись=False)
        итог = _вызвать(сервер, "list_queues")
        self.assertTrue(итог.is_error)
        self.assertIn("не-латинские", _текст(итог))

    def test_трекер_не_отвечает(self):
        import tracker_server

        сервер = tracker_server.создать_сервер(
            tracker_server.Трекер(адрес=f"http://127.0.0.1:{_свободный_порт()}"), запись=False)
        итог = _вызвать(сервер, "list_queues")
        self.assertTrue(итог.is_error)
        self.assertIn("tracker_api.py", _текст(итог))

    def test_лимит_запросов_объяснён(self):
        import tracker_server

        каталог = tempfile.mkdtemp(prefix="трекер-429-")
        try:
            приложение = _трекер_клиент(каталог, лимит=1)
            сервер = tracker_server.создать_сервер(_трекер(приложение), запись=False)
            _вызвать(сервер, "list_queues")
            итог = _вызвать(сервер, "list_queues")
            self.assertTrue(итог.is_error)
            self.assertIn("429", _текст(итог))
        finally:
            shutil.rmtree(каталог, ignore_errors=True)


class ВызовЧерезСоединение(unittest.TestCase):
    """Session.call_tool: настоящий tools/call по stdio и разбор ответа."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.каталог = tempfile.mkdtemp(prefix="mcp-вызов-")
        cls.память = os.path.join(cls.каталог, "memory")
        _наполнить_память(cls.память)
        cls.описание, = amcp.load(_файл_серверов(
            cls.каталог, {"agent-state": _свой_сервер(cls.память)}))

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.каталог, ignore_errors=True)

    def test_вызов_возвращает_данные_и_время(self):
        with amcp.Session(self.описание) as сеанс:
            итог = сеанс.call_tool("list_tasks", {})
        self.assertTrue(итог.ок)
        self.assertEqual(итог.полное_имя, "agent-state__list_tasks")
        self.assertEqual([з["task_id"] for з in итог.данные["задачи"]], ["перенос-моделей"])
        self.assertIn("перенос-моделей", итог.текст)
        self.assertGreater(итог.блоков, 0)
        self.assertGreaterEqual(итог.секунд, 0)

    def test_несколько_вызовов_в_одном_сеансе(self):
        """Сервер запускается один раз: второй вызов идёт по тому же соединению."""
        with amcp.Session(self.описание) as сеанс:
            первый = сеанс.call_tool("list_tasks", {})
            второй = сеанс.call_tool("get_task", {"task_id": "перенос-моделей"})
        self.assertTrue(первый.ок and второй.ок)
        self.assertEqual(второй.данные["стадия"], PLANNING)

    def test_ошибка_инструмента_это_результат_а_не_исключение(self):
        with amcp.Session(self.описание) as сеанс:
            итог = сеанс.call_tool("get_task", {"task_id": "нет-такой"})
        self.assertFalse(итог.ок)
        self.assertTrue(итог.текст)

    def test_вызов_без_соединения(self):
        сеанс = amcp.Session(self.описание)
        with self.assertRaises(amcp.MCPClientError):
            сеанс.call_tool("list_tasks", {})

    def test_длинный_ответ_обрезается(self):
        """Ответ чужого сервера может быть каким угодно; в промпт идёт не всё."""
        from agent.mcp import client as mcp_client

        class _Блок:
            type = "text"
            text = "я" * (mcp_client.ПРЕДЕЛ_ОТВЕТА + 1000)

        class _Итог:
            content = [_Блок()]
            structured_content = None
            is_error = False

        сеанс = amcp.Session(self.описание)
        сеанс._клиент = types.SimpleNamespace(call_tool=lambda *а, **к: None)
        сеанс._вызвать = lambda *а, **к: _Итог()
        итог = сеанс.call_tool("что-угодно", {})
        self.assertTrue(итог.обрезан)
        self.assertLess(len(итог.текст), mcp_client.ПРЕДЕЛ_ОТВЕТА + 200)
        self.assertIn("обрезан", итог.текст)


class ИнструментарийАгента(unittest.TestCase):
    """Toolbox: общий список инструментов, имена для модели и вызов по имени."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.каталог = tempfile.mkdtemp(prefix="mcp-ящик-")
        cls.память = os.path.join(cls.каталог, "memory")
        _наполнить_память(cls.память)
        cls.файл = _файл_серверов(cls.каталог, {
            "agent-state": _свой_сервер(cls.память),
            "broken": {"command": "нет-такой-команды-xyz"},
        })

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.каталог, ignore_errors=True)

    def test_имена_для_модели_и_цена(self):
        with amcp.Toolbox(["agent-state"], self.файл) as ящик:
            имена = {и["function"]["name"] for и in ящик.для_модели()}
            сводка = ящик.сводка()
        self.assertEqual(имена, {f"agent-state__{и}" for и in ИНСТРУМЕНТЫ_СВОЕГО})
        self.assertEqual(сводка["читающих"], len(ИНСТРУМЕНТЫ_СВОЕГО))
        self.assertEqual(сводка["меняющих"], 0)
        self.assertGreater(сводка["токенов"], 0)

    def test_вызов_по_полному_имени(self):
        with amcp.Toolbox(["agent-state"], self.файл) as ящик:
            итог = ящик.вызвать("agent-state__list_tasks", {})
        self.assertTrue(итог.ок)
        self.assertIn("перенос-моделей", итог.текст)

    def test_выдуманное_имя_названо_ошибкой(self):
        with amcp.Toolbox(["agent-state"], self.файл) as ящик:
            with self.assertRaises(amcp.ToolboxError) as ошибка:
                ящик.вызвать("agent-state__drop_database", {})
        self.assertIn("Доступны", str(ошибка.exception))

    def test_закрытый_фильтром_объясняет_причину(self):
        # Файл серверов пишется в отдельный каталог: общий на класс тест бы
        # переписал, и соседние проверки увидели бы чужую конфигурацию.
        каталог = tempfile.mkdtemp(prefix="mcp-фильтр-")
        self.addCleanup(shutil.rmtree, каталог, True)
        файл = _файл_серверов(каталог, {
            "agent-state": _свой_сервер(self.память, разрешить=["list_*"])})
        with amcp.Toolbox(["agent-state"], файл) as ящик:
            with self.assertRaises(amcp.ToolboxError) as ошибка:
                ящик.вызвать("agent-state__get_task", {"task_id": "перенос-моделей"})
        self.assertIn("закрыт настройками", str(ошибка.exception))

    def test_недоступный_сервер_не_отменяет_остальные(self):
        with amcp.Toolbox(["agent-state", "broken"], self.файл) as ящик:
            сводка = ящик.сводка()
            итог = ящик.вызвать("agent-state__list_tasks", {})
        self.assertTrue(итог.ок)
        self.assertEqual(сводка["подключено"], 1)
        self.assertEqual([н["сервер"] for н in сводка["недоступны"]], ["broken"])
        self.assertIn("не найдена команда", сводка["недоступны"][0]["причина"])

    def test_меняющим_считается_всё_кроме_явного_чтения(self):
        """Пометкам сервера верят только в сторону осторожности."""
        with amcp.Toolbox(["agent-state"], self.файл) as ящик:
            self.assertFalse(ящик.меняет("agent-state__list_tasks"))
            ящик.инструменты[0].пометки = {}          # сервер ничего не заявил
            self.assertTrue(ящик.меняет(ящик.инструменты[0].полное_имя))
            self.assertTrue(ящик.меняет("выдуманный__инструмент"))


class ЗаявкиНаИзменение(unittest.TestCase):
    """memory/tool-calls.json: заявка переживает процесс и решается один раз."""

    def setUp(self):
        self.каталог = tempfile.mkdtemp(prefix="заявки-")
        self.память = MemoryManager(base_dir=self.каталог, user_id="инженер")

    def tearDown(self):
        shutil.rmtree(self.каталог, ignore_errors=True)

    def заявка(self, **поля):
        поля.setdefault("инструмент", "tracker__add_comment")
        поля.setdefault("аргументы", {"key": "MIG-2", "text": "готово"})
        поля.setdefault("сервер", "tracker")
        поля.setdefault("зачем", "отметь в трекере")
        return self.память.request_call(**поля)

    def test_заявка_заводится_и_ждёт(self):
        заявка = self.заявка()
        self.assertEqual(заявка.номер, 1)
        self.assertTrue(заявка.ждёт)
        self.assertEqual([з.номер for з in self.память.pending_calls()], [1])
        self.assertIn("MIG-2", заявка.словами())

    def test_заявка_видна_другому_процессу(self):
        """Ответ пришёл в одном процессе, подтверждение придёт в другом."""
        self.заявка()
        другая = MemoryManager(base_dir=self.каталог, user_id="инженер")
        self.assertEqual([з.инструмент for з in другая.pending_calls()],
                         ["tracker__add_comment"])

    def test_решается_один_раз(self):
        заявка = self.заявка()
        self.память.resolve_call(заявка.номер, ОТКЛОНЕНА, почему="не сейчас")
        self.assertEqual(self.память.pending_calls(), [])
        with self.assertRaises(CallStoreError):
            self.память.resolve_call(заявка.номер, ВЫПОЛНЕНА)

    def test_журнал_помнит_и_заявку_и_решение(self):
        заявка = self.заявка()
        self.память.resolve_call(заявка.номер, ВЫПОЛНЕНА, результат={"ок": True})
        записи = [з for з in self.память.journal(10) if з["правило"] == "вызов-инструмента"]
        self.assertEqual([з["применено"] for з in записи], [False, True])

    def test_нет_такой_заявки(self):
        with self.assertRaises(CallStoreError):
            self.память.resolve_call(42, ВЫПОЛНЕНА)

    def test_старые_заявки_не_копятся_без_предела(self):
        from agent.memory import calls as модуль_заявок

        предел = модуль_заявок.ПРЕДЕЛ
        for номер in range(предел + 5):
            self.заявка(аргументы={"key": f"MIG-{номер}"})
        self.assertEqual(len(self.память.calls.all()), предел)

    def test_вызов_попадает_в_журнал(self):
        self.память.log_tool_call(amcp.ToolResult(
            сервер="tracker", инструмент="list_issues", полное_имя="tracker__list_issues",
            аргументы={"status": "open"}, ок=True, текст="{}"), зачем="что в работе")
        запись = self.память.journal(1)[0]
        self.assertEqual(запись["правило"], "вызов-инструмента")
        self.assertTrue(запись["применено"])
        self.assertIn("list_issues", запись["текст"])


class _ЯщикДляАгента:
    """Инструментарий-заглушка: проверяем цикл агента, а не транспорт MCP."""

    def __init__(self, ответ=None, сбой: str = ""):
        self.вызовы: list[tuple[str, dict]] = []
        self.ответ = ответ or {"задачи": ["MIG-2"]}
        self.сбой = сбой
        self.имена = ["tracker"]
        self.инструменты = [
            _Инструмент("tracker", "list_issues", "только чтение"),
            _Инструмент("tracker", "add_comment", "меняет данные"),
        ]
        self.закрыт = False

    def открыть(self):
        return []

    def сводка(self):
        return {"серверов": 1, "подключено": 1, "серверы": ["tracker"], "недоступны": [],
                "инструментов": 2, "читающих": 1, "меняющих": 1, "токенов": 100,
                "повторы_имён": []}

    def для_модели(self):
        return [и.for_model() for и in self.инструменты]

    def найти(self, имя):
        for инструмент in self.инструменты:
            if инструмент.полное_имя == имя:
                return инструмент
        return None

    def меняет(self, имя):
        инструмент = self.найти(имя)
        return инструмент is None or инструмент.доступ != "только чтение"

    def вызвать(self, имя, аргументы=None):
        self.вызовы.append((имя, dict(аргументы or {})))
        if self.сбой:
            raise amcp.ToolboxError(self.сбой)
        return amcp.ToolResult(сервер="tracker", инструмент=имя.split("__")[-1],
                               полное_имя=имя, аргументы=dict(аргументы or {}),
                               ок=True, текст=_json.dumps(self.ответ, ensure_ascii=False),
                               данные=self.ответ, секунд=0.01, блоков=1)

    def close(self):
        self.закрыт = True


def _Инструмент(сервер: str, имя: str, доступ: str):
    пометки = {"readOnlyHint": True} if доступ == "только чтение" else {"destructiveHint": False}
    return amcp.Tool(сервер=сервер, имя=имя, описание=f"инструмент {имя}",
                     входная_схема={"type": "object", "properties": {}}, пометки=пометки)


class ЦиклИнструментов(unittest.TestCase):
    """Просьба модели → вызов агентом → результат → ответ. Модель — заглушка."""

    def setUp(self):
        self.каталог = tempfile.mkdtemp(prefix="цикл-")
        self.агент = MemoryAgent(base_dir=self.каталог, judge_semantic=False,
                                 require_self_report=False, router_mode="выкл",
                                 seed_project=False)
        self.ящик = _ЯщикДляАгента()
        self.агент.toolbox = self.ящик
        self.запросы: list[dict] = []

    def tearDown(self):
        self.агент.close()
        shutil.rmtree(self.каталог, ignore_errors=True)

    def модель(self, *ответы):
        """Подменяет вызовы модели заранее заданными ответами."""
        очередь = list(ответы)

        def вызов(ключ, сообщения, **кв):
            self.запросы.append({"сообщения": сообщения, "tools": кв.get("tools")})
            return очередь.pop(0) if очередь else Reply(text="всё", model_key="тест")

        return mock.patch.object(self.агент.client, "call", side_effect=вызов)

    @staticmethod
    def просьба(имя, аргументы, ид="c1", текст=""):
        сырые = аргументы if isinstance(аргументы, str) else _json.dumps(аргументы)
        return Reply(
            text=текст, model_key="тест",
            tool_calls=разобрать_вызовы([
                {"id": ид, "function": {"name": имя, "arguments": сырые}}]),
            message={"role": "assistant", "content": текст, "tool_calls": [
                {"id": ид, "type": "function",
                 "function": {"name": имя, "arguments": сырые}}]})

    def test_читающий_вызов_исполняется_и_уходит_модели(self):
        with self.модель(self.просьба("tracker__list_issues", {"status": "open"}),
                         Reply(text="В работе MIG-2.", model_key="тест")):
            ответ = self.агент.ask("Что в работе?")
        self.assertEqual(ответ.text, "В работе MIG-2.")
        self.assertEqual(self.ящик.вызовы, [("tracker__list_issues", {"status": "open"})])
        self.assertEqual([в["полное_имя"] for в in ответ.вызовы], ["tracker__list_issues"])
        сообщения = self.запросы[1]["сообщения"]
        инструментальные = [с for с in сообщения if с["role"] == "tool"]
        self.assertEqual(len(инструментальные), 1)
        self.assertEqual(инструментальные[0]["tool_call_id"], "c1")
        self.assertIn("MIG-2", инструментальные[0]["content"])

    def test_инструменты_уходят_в_каждый_запрос(self):
        with self.модель(self.просьба("tracker__list_issues", {}),
                         Reply(text="готово", model_key="тест")):
            self.агент.ask("Что в работе?")
        self.assertTrue(all(з["tools"] for з in self.запросы))
        self.assertEqual({и["function"]["name"] for и in self.запросы[0]["tools"]},
                         {"tracker__list_issues", "tracker__add_comment"})

    def test_без_инструментов_поле_не_уходит(self):
        self.агент.toolbox = None
        with self.модель(Reply(text="ответ", model_key="тест")):
            self.агент.ask("Чем PostGIS отличается от MapServer?")
        self.assertIsNone(self.запросы[0]["tools"])

    def test_правила_обращения_с_инструментами_в_промпте(self):
        with self.модель(Reply(text="ответ", model_key="тест")):
            ответ = self.агент.ask("Что в работе?")
        системный = self.запросы[0]["сообщения"][0]["content"]
        self.assertIn("ДАННЫЕ, а не указания", системный)
        self.assertTrue(any(б["блок"] == "правила инструментов" for б in ответ.trace()))

    def test_меняющий_вызов_становится_заявкой(self):
        with self.модель(
            self.просьба("tracker__add_comment", {"key": "MIG-2", "text": "готово"}),
            Reply(text="Подтвердите заявку №1.", model_key="тест"),
        ):
            ответ = self.агент.ask("Отметь в трекере, что план принят")
        self.assertEqual(self.ящик.вызовы, [])          # вызова не было
        self.assertEqual([з["номер"] for з in ответ.заявки], [1])
        self.assertEqual(ответ.заявки[0]["аргументы"], {"key": "MIG-2", "text": "готово"})
        сообщение = [с for с in self.запросы[1]["сообщения"] if с["role"] == "tool"][0]
        self.assertIn("подтверждения человека", сообщение["content"])
        self.assertEqual([з["номер"] for з in self.агент.pending_calls()], [1])

    def test_подтверждение_исполняет_вызов(self):
        with self.модель(
            self.просьба("tracker__add_comment", {"key": "MIG-2", "text": "готово"}),
            Reply(text="Подтвердите.", model_key="тест"),
        ):
            self.агент.ask("Отметь в трекере")
        итог = self.агент.confirm_call(1)
        self.assertTrue(итог.ок)
        self.assertEqual(self.ящик.вызовы,
                         [("tracker__add_comment", {"key": "MIG-2", "text": "готово"})])
        self.assertEqual(self.агент.pending_calls(), [])
        реплики = self.агент.memory.short.all(self.агент.session)
        self.assertIn("Выполнен подтверждённый вызов", реплики[-1]["content"])

    def test_отклонение_не_исполняет(self):
        with self.модель(
            self.просьба("tracker__add_comment", {"key": "MIG-2", "text": "готово"}),
            Reply(text="Подтвердите.", model_key="тест"),
        ):
            self.агент.ask("Отметь в трекере")
        решена = self.агент.reject_call(1, "статус меняет тимлид")
        self.assertEqual(решена["состояние"], ОТКЛОНЕНА)
        self.assertEqual(self.ящик.вызовы, [])
        with self.assertRaises(AgentError):
            self.агент.confirm_call(1)

    def test_без_подтверждения_вызов_идёт_сразу(self):
        self.агент.confirm_writes = False
        with self.модель(
            self.просьба("tracker__add_comment", {"key": "MIG-2", "text": "готово"}),
            Reply(text="Добавил.", model_key="тест"),
        ):
            ответ = self.агент.ask("Отметь в трекере")
        self.assertEqual(len(self.ящик.вызовы), 1)
        self.assertEqual(ответ.заявки, [])

    def test_кривые_аргументы_объяснены_модели(self):
        with self.модель(self.просьба("tracker__list_issues", "{сломано"),
                         Reply(text="Извини, перепишу.", model_key="тест")):
            ответ = self.агент.ask("Что в работе?")
        self.assertEqual(self.ящик.вызовы, [])
        сообщение = [с for с in self.запросы[1]["сообщения"] if с["role"] == "tool"][0]
        self.assertIn("не JSON", сообщение["content"])
        self.assertEqual(ответ.вызовы, [])

    def test_сбой_вызова_не_роняет_ответ(self):
        self.агент.toolbox = _ЯщикДляАгента(сбой="Сервер «tracker» не выполнил вызов")
        with self.модель(self.просьба("tracker__list_issues", {}),
                         Reply(text="Трекер недоступен.", model_key="тест")):
            ответ = self.агент.ask("Что в работе?")
        self.assertEqual(ответ.text, "Трекер недоступен.")
        self.assertEqual([в["ок"] for в in ответ.вызовы], [False])
        сообщение = [с for с in self.запросы[1]["сообщения"] if с["role"] == "tool"][0]
        self.assertIn("Вызов не выполнен", сообщение["content"])

    def test_предел_кругов_вызовов(self):
        """Модель, которая только и делает, что зовёт инструменты, не разорит."""
        просьбы = [self.просьба("tracker__list_issues", {}, ид=f"c{н}") for н in range(10)]
        with self.модель(*просьбы):
            ответ = self.агент.ask("Что в работе?")
        self.assertEqual(len(self.ящик.вызовы), self.агент.tool_rounds)
        self.assertIsNone(self.запросы[-1]["tools"])     # последний запрос — без инструментов
        # Модель и тут просит вызов, а не отвечает. Пустой текст наружу не выходит.
        self.assertIn("запрашивала инструменты", ответ.text)

    def test_вызовы_попадают_в_журнал_памяти(self):
        with self.модель(self.просьба("tracker__list_issues", {"status": "open"}),
                         Reply(text="готово", model_key="тест")):
            self.агент.ask("Что в работе?")
        записи = [з for з in self.агент.memory.journal(20) if з["правило"] == "вызов-инструмента"]
        self.assertTrue(записи)
        self.assertIn("list_issues", записи[-1]["текст"])

    def test_ручной_вызов_не_спрашивает_подтверждения(self):
        итог = self.агент.call_tool("tracker__add_comment", {"key": "MIG-2", "text": "вручную"})
        self.assertTrue(итог.ок)
        self.assertEqual(len(self.ящик.вызовы), 1)
        self.assertEqual(self.агент.pending_calls(), [])

    def test_закрытие_агента_закрывает_соединения(self):
        self.агент.close()
        self.assertTrue(self.ящик.закрыт)


class КонсольИнструментов(unittest.TestCase):
    """cli.py --инструменты/--вызвать/--заявки: настоящий процесс, stdin закрыт."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.каталог = tempfile.mkdtemp(prefix="инструменты-консоль-")
        cls.память = os.path.join(cls.каталог, "memory")
        _наполнить_память(cls.память)
        cls.файл = _файл_серверов(cls.каталог, {
            "agent-state": _свой_сервер(cls.память),
            "broken": {"command": "нет-такой-команды-xyz"},
        })

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.каталог, ignore_errors=True)

    def консоль(self, *ключи: str):
        итог = _subprocess.run(
            [sys.executable, os.path.join(КОРЕНЬ_ДНЯ, "cli.py"),
             "--mcp-файл", self.файл, "--память-в", self.память, *ключи],
            capture_output=True, text=True, stdin=_subprocess.DEVNULL, timeout=120,
            env={**os.environ, "MEMORY_DIR": self.память})
        вывод = итог.stdout + итог.stderr
        self.assertNotIn("Вы:", вывод, "команда открыла диалог")
        return итог.returncode, вывод

    def test_ключ_не_съедает_вопрос(self):
        """«--инструменты tracker "вопрос"» — вопрос должен остаться вопросом."""
        import cli

        разбор = cli.build_parser()
        аргументы = разбор.parse_args(["--инструменты", "agent-state", "что в работе?"])
        self.assertEqual(аргументы.tools, "agent-state")
        self.assertEqual(аргументы.вопрос, ["что в работе?"])
        self.assertIsNone(разбор.parse_args([]).tools)
        self.assertEqual(разбор.parse_args(["--инструменты"]).tools, "")
        self.assertEqual(cli.разобрать_серверы("a, b"), ["a", "b"])
        self.assertIsNone(cli.разобрать_серверы(None))

    def test_список_инструментов_без_модели(self):
        код, вывод = self.консоль("--инструменты", "agent-state")
        self.assertEqual(код, 0, вывод)
        self.assertIn("agent-state__list_tasks", вывод)
        self.assertIn("только чтение", вывод)
        self.assertIn("в каждом запросе", вывод)

    def test_недоступный_сервер_назван(self):
        код, вывод = self.консоль("--инструменты", "agent-state,broken")
        self.assertEqual(код, 0, вывод)
        self.assertIn("broken", вывод)
        self.assertIn("не найдена команда", вывод)

    def test_ручной_вызов(self):
        код, вывод = self.консоль("--вызвать", "agent-state__list_tasks")
        self.assertEqual(код, 0, вывод)
        self.assertIn("перенос-моделей", вывод)

    def test_ручной_вызов_с_аргументами(self):
        код, вывод = self.консоль("--вызвать", "agent-state__get_task",
                                  "--аргументы", '{"task_id": "перенос-моделей"}')
        self.assertEqual(код, 0, вывод)
        self.assertIn("planning", вывод)

    def test_кривые_аргументы_не_уходят_на_сервер(self):
        код, вывод = self.консоль("--вызвать", "agent-state__get_task", "--аргументы", "{нет")
        self.assertEqual(код, 1)
        self.assertIn("не JSON", вывод)

    def test_ошибка_инструмента_даёт_код_возврата(self):
        код, вывод = self.консоль("--вызвать", "agent-state__get_task",
                                  "--аргументы", '{"task_id": "нет-такой"}')
        self.assertEqual(код, 1, вывод)
        self.assertIn("ОШИБКА", вывод)

    def test_заявок_нет(self):
        код, вывод = self.консоль("--заявки")
        self.assertEqual(код, 0, вывод)
        self.assertIn("Ждущих заявок нет", вывод)

    def test_заявка_подтверждается_из_другого_процесса(self):
        """Заявку завёл один процесс, подтверждает другой — как паузу в Дне 13."""
        каталог = tempfile.mkdtemp(prefix="заявка-процесс-")
        try:
            память = MemoryManager(base_dir=каталог, user_id="инженер")
            память.request_call(инструмент="agent-state__list_tasks", аргументы={},
                                сервер="agent-state", зачем="проверка")
            итог = _subprocess.run(
                [sys.executable, os.path.join(КОРЕНЬ_ДНЯ, "cli.py"), "--mcp-файл", self.файл,
                 "--память-в", каталог, "--подтвердить", "1"],
                capture_output=True, text=True, stdin=_subprocess.DEVNULL, timeout=120,
                env={**os.environ, "MEMORY_DIR": каталог})
            вывод = итог.stdout + итог.stderr
            self.assertEqual(итог.returncode, 0, вывод)
            self.assertIn("исполнена", вывод)
            self.assertEqual(MemoryManager(base_dir=каталог).pending_calls(), [])
        finally:
            shutil.rmtree(каталог, ignore_errors=True)


class ВебИнструментов(unittest.TestCase):
    """Страница умеет то же, что консоль: включить, вызвать, решить заявку."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.каталог = tempfile.mkdtemp(prefix="инструменты-веб-")
        cls.память = os.path.join(cls.каталог, "memory")
        _наполнить_память(cls.память)
        cls.файл = _файл_серверов(cls.каталог, {"agent-state": _свой_сервер(cls.память)})
        cls.прежние = {к: os.environ.get(к) for к in ("MEMORY_DIR", "MCP_CONFIG")}
        os.environ["MEMORY_DIR"] = cls.память
        os.environ["MCP_CONFIG"] = cls.файл
        import importlib
        import web
        cls.web = importlib.reload(web)
        cls.клиент = cls.web.app.test_client()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.web.agent.close()
        for ключ, значение in cls.прежние.items():
            if значение is None:
                os.environ.pop(ключ, None)
            else:
                os.environ[ключ] = значение
        shutil.rmtree(cls.каталог, ignore_errors=True)

    def tearDown(self):
        self.клиент.post("/api/tools", json={"tools": []})

    def test_включение_и_выключение(self):
        данные = self.клиент.post("/api/tools", json={"tools": ["agent-state"]}).get_json()
        self.assertTrue(данные["enabled"])
        self.assertEqual({и["имя"] for и in данные["tools"]}, ИНСТРУМЕНТЫ_СВОЕГО)
        self.assertGreater(данные["summary"]["токенов"], 0)
        self.assertTrue(данные["confirm_writes"])
        выключено = self.клиент.post("/api/tools", json={"tools": []}).get_json()
        self.assertFalse(выключено["enabled"])
        self.assertIsNone(self.web.agent.toolbox)

    def test_ручной_вызов(self):
        ответ = self.клиент.post("/api/mcp/call",
                                 json={"tool": "agent-state__list_tasks", "args": {}})
        self.assertEqual(ответ.status_code, 200)
        результат = ответ.get_json()["result"]
        self.assertTrue(результат["ок"])
        self.assertIn("перенос-моделей", результат["текст"])

    def test_выдуманный_инструмент_это_ошибка_запроса(self):
        ответ = self.клиент.post("/api/mcp/call",
                                 json={"tool": "agent-state__drop", "args": {}})
        self.assertEqual(ответ.status_code, 400)
        self.assertIn("нет", ответ.get_json()["error"])

    def test_аргументы_должны_быть_объектом(self):
        ответ = self.клиент.post("/api/mcp/call",
                                 json={"tool": "agent-state__list_tasks", "args": "строка"})
        self.assertEqual(ответ.status_code, 400)

    def test_заявка_подтверждается(self):
        self.web.agent.memory.request_call(
            инструмент="agent-state__list_tasks", аргументы={}, сервер="agent-state",
            зачем="проверка")
        список = self.клиент.get("/api/calls").get_json()["calls"]
        номер = список[-1]["номер"]
        ответ = self.клиент.post("/api/calls", json={"номер": номер, "действие": "подтвердить"})
        self.assertEqual(ответ.status_code, 200)
        данные = ответ.get_json()
        self.assertTrue(данные["result"]["ок"])
        self.assertNotIn(номер, [з["номер"] for з in данные["calls"]])

    def test_заявка_отклоняется(self):
        заявка = self.web.agent.memory.request_call(
            инструмент="agent-state__list_tasks", аргументы={}, сервер="agent-state",
            зачем="проверка")
        ответ = self.клиент.post("/api/calls", json={
            "номер": заявка.номер, "действие": "отклонить", "почему": "не нужно"})
        self.assertEqual(ответ.status_code, 200)
        self.assertEqual(ответ.get_json()["rejected"]["состояние"], ОТКЛОНЕНА)

    def test_неизвестное_действие(self):
        ответ = self.клиент.post("/api/calls", json={"номер": 1, "действие": "стереть"})
        self.assertEqual(ответ.status_code, 400)

# --- живые проверки -----------------------------------------------------------

@unittest.skipUnless(ЖИВЫЕ, "нужен ключ API; запускать с --живые")
class ЖивыеПроверки(unittest.TestCase):

    def test_маршрутизатор_отличает_вопрос_от_факта(self):
        from agent.llm import Client
        from agent.memory.router import Router
        клиент = Client()
        try:
            маршрутизатор = Router(клиент)
            вопрос = маршрутизатор.classify("А как в GeoDjango сделать индекс по геометрии?")
            факт = маршрутизатор.classify("У нас в схеме gisdata 37 таблиц")
            self.assertFalse(вопрос.wants_write, f"вопрос принят за факт: {вопрос.to_dict()}")
            self.assertTrue(факт.wants_write or факт.failed, факт.to_dict())
        finally:
            клиент.close()

    def test_агент_отвечает_и_не_нарушает_инвариантов(self):
        from agent import MemoryAgent
        каталог = tempfile.mkdtemp()
        агент = MemoryAgent(base_dir=каталог, router_mode=OFF, temperature=0.0)
        try:
            ответ = агент.ask("Какой ORM использовать для геометрии в новой системе?")
            self.assertTrue(ответ.text)
            self.assertFalse(ответ.blocked, [str(н) for н in ответ.violations])
            self.assertIn(LONG, ответ.layers())
        finally:
            агент.close()
            shutil.rmtree(каталог, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
