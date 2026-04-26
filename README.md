# Student Codex Learning Agent MVP

MVP учебного агента для студентов, которые работают через Codex.

Идея: студент получает приватный GitHub-репозиторий из этого шаблона, открывает его в Codex и запускает онбординг. Агент спрашивает, как его назвать, каким он должен быть, какую роль играть, как помогать и что запоминать. После этого он ведёт студента по курсу, пишет дневные логи, напоминает о домашних заданиях по расписанию и периодически выполняет dreaming — сжимает накопившуюся память в устойчивые выводы.

## Что нового в v0.4

- Добавлен skill `$homework-submission`.
- Агент умеет искать домашние задания в `course/Module_*` по русским и английским маркерам.
- SessionStart hook сверяется с системной датой, расписанием курса и ближайшим занятием.
- Добавлена отправка готового Markdown-отчёта в Homework Submission API.
- Токен API не хранится в репозитории: используется `HOMEWORK_API_TOKEN` или локальный `.env`.
- Добавлены `homework/drafts/` и `homework/submissions/` для черновиков и receipts.

## Важно про hooks

В v0.2 hook-команда зависела от `git rev-parse --show-toplevel`. Это работало только внутри git-репозитория и ломалось, если шаблон был просто распакован как папка. Начиная с v0.3 hooks больше не зависят от git: команда идёт вверх от текущей папки, ищет `.codex/hooks/dreaming.py` и запускает его.

Поэтому `git init` не требуется. Если Codex уже запущен со старой конфигурацией hooks, перезапусти сессию Codex после обновления файлов.

## Файлы MVP

- `AGENTS.md` — главный bootloader и правила поведения.
- `SOUL.md` — имя, характер, стиль и модель пользы агента.
- `STUDENT.md` — профиль, цели, границы помощи, прогресс и статусы домашних заданий.
- `COURSE.md` — источник правды по курсу `sekachev/agentic_ai`, расписанию и Homework API.
- `MEMORY.md` — долгосрочная память и состояние dreaming.
- `logs/daily/` — ежедневные логи, которые не загружаются все подряд.
- `homework/drafts/` — черновики Markdown-отчётов.
- `homework/submissions/` — receipts успешных отправок.
- `.agents/skills/onboarding/SKILL.md` — первый запуск и настройка агента.
- `.agents/skills/homework-submission/SKILL.md` — поиск, оформление и отправка домашек.
- `.codex/hooks/` — автоматические подсказки Codex для загрузки памяти, dreaming и homework reminders.

## Быстрый старт для студента

1. Создать приватный репозиторий из этого шаблона или распаковать папку локально.
2. Открыть **корень** репозитория/папки в Codex, то есть папку, где лежит `AGENTS.md`.
3. Доверить проекту `.codex/`-конфигурацию, если Codex попросит подтверждение. Это нужно для автоматического dreaming и homework reminders через hooks.
4. Написать:

```text
Начнём онбординг
```

## Проверка hooks

Из корня проекта можно выполнить:

```bash
python3 .codex/hooks/smoke_test.py
```

Ожидаемый результат:

```text
ok: direct session-start
ok: direct stop
ok: configured session-start from root
ok: configured stop from root
ok: configured session-start from subdir
ok: configured stop from subdir
```

Smoke-test не требует `.git`, проверяет и сам скрипт, и команды из `hooks.json`, и не меняет файлы памяти.

Проверка homework-скриптов без сети и токена:

```bash
python3 .agents/skills/homework-submission/scripts/homework_smoke_test.py
```

Ожидаемый результат:

```text
ok: submit dry-run
ok: discover missing/empty course
```

## Как подключить курс

Вариант 1: склонировать курс внутрь репозитория агента:

```bash
git clone https://github.com/sekachev/agentic_ai.git course
```

Вариант 2: подключить как submodule:

```bash
git submodule add https://github.com/sekachev/agentic_ai.git course
```

Курс уже прописан в `COURSE.md`. Актуальный маршрут находится в корне репозитория курса; `archive/` используется как справочник прошлых потоков.

## Как работает поиск домашек

Запуск вручную:

```bash
python3 .agents/skills/homework-submission/scripts/discover_homework.py --course-dir course --format markdown
```

Для конкретного модуля:

```bash
python3 .agents/skills/homework-submission/scripts/discover_homework.py --course-dir course --module Module_03 --format markdown
```

Скрипт ищет в `.md`, `.txt`, `.canvas` файлах по маркерам вроде `домаш`, `ДЗ`, `задание`, `практика`, `homework`, `assignment`, `task`, `practice`. Он не решает, что является домашкой окончательно; он показывает кандидатов, а агент и студент подтверждают.

## Как настроить Homework Submission API

Скопировать пример окружения:

```bash
cp .env.example .env
```

В `.env` указать реальный токен:

```bash
HOMEWORK_API_URL=https://hw.sekachev.ee
HOMEWORK_API_TOKEN=...
```

`.env` добавлен в `.gitignore`. Не коммить токен в репозиторий.

Проверить доступность API:

```bash
python3 .agents/skills/homework-submission/scripts/submit_homework.py --health
```

Dry run отправки:

```bash
python3 .agents/skills/homework-submission/scripts/submit_homework.py \
  --assignment-id lesson-01 \
  --student-id student-7 \
  --student-name "Ada Lovelace" \
  --agent-name "homework-agent" \
  --content-file homework/drafts/lesson-01.md \
  --dry-run
```

Реальная отправка:

```bash
python3 .agents/skills/homework-submission/scripts/submit_homework.py \
  --assignment-id lesson-01 \
  --student-id student-7 \
  --student-name "Ada Lovelace" \
  --agent-name "homework-agent" \
  --content-file homework/drafts/lesson-01.md \
  --save-receipt
```

После успешной отправки агент обновляет `STUDENT.md`, сегодняшний дневной лог и показывает путь к receipt в `homework/submissions/`.

## Как работает память

- В течение дня агент пишет `logs/daily/YYYY-MM-DD.md`.
- В начале сессии агент загружает только `MEMORY.md` и последние несколько дневных логов.
- Старые логи остаются архивом и читаются только при необходимости.
- Dreaming переносит устойчивые выводы из логов в `MEMORY.md`, прогресс и статусы домашек — в `STUDENT.md`, а изменения характера — в `SOUL.md`.

## Как работает dreaming

Dreaming запускается автоматически через Codex hooks, если:

- прошло 7+ дней с последнего dreaming;
- накопилось 3+ новых дневных лога;
- студент попросил выполнить dreaming.

Хук не суммаризирует сам. Он только сообщает Codex, что пора выполнить dreaming-протокол из `AGENTS.md`.

## Почему мало файлов

MVP придерживается правила одного источника правды:

- характер агента — только `SOUL.md`;
- студент, прогресс и домашки — только `STUDENT.md`;
- курс, расписание и Homework API — только `COURSE.md`;
- долгосрочная память — только `MEMORY.md`;
- сырые события — только `logs/daily/`.

Новые skills создаются не заранее, а когда агент и студент обнаружили повторяемую полезную процедуру. Исключение v0.4 — `$homework-submission`, потому что это внешняя интеграция с API и её лучше держать отдельным skill.
