---
name: homework-submission
description: Найти домашние задания в локальном курсе, сверить их с расписанием и системной датой, помочь студенту подготовить Markdown-отчёт и отправить готовую домашку через Homework Submission API.
---

# Homework Submission Skill

Используй этот skill, когда:

- студент говорит “домашка”, “ДЗ”, “задание”, “практика”, “сдать”, “отправить”, “submit”, “assignment”; 
- нужно понять, какая домашка актуальна по расписанию курса;
- нужно найти домашнее задание в `course/Module_*`;
- нужно оформить Markdown-отчёт;
- нужно отправить готовую домашку в API.

## Принцип

Домашняя работа — это учебный артефакт. Не превращай skill в “сделай за меня”. Сначала помоги студенту понять задание и сделать попытку. Отправляй только готовый Markdown-отчёт и только когда намерение отправить явно выражено.

## Boot перед работой с домашкой

1. Прочитай `STUDENT.md`, `COURSE.md`, `SOUL.md`, `MEMORY.md`.
2. Проверь системную дату:

```bash
date '+%Y-%m-%d %A %Z'
```

3. Определи текущий/ближайший модуль:
   - по `STUDENT.md`;
   - по `course/SCHEDULE.md`, если курс склонирован;
   - по таблице календаря в `COURSE.md`, если локального курса ещё нет.
4. Проверь таблицу “Домашние задания” в `STUDENT.md`.
5. Если курс ещё не склонирован в `course/`, предложи:

```bash
git clone https://github.com/sekachev/agentic_ai.git course
```

## Поиск домашнего задания

Запусти discovery-скрипт:

```bash
python3 .agents/skills/homework-submission/scripts/discover_homework.py --course-dir course --format markdown
```

Для конкретного модуля:

```bash
python3 .agents/skills/homework-submission/scripts/discover_homework.py --course-dir course --module Module_03 --format markdown
```

Скрипт ищет:

- файлы и папки с маркерами `homework`, `assignment`, `task`, `practice`, `дз`, `домаш`, `задани`, `практик`;
- фрагменты Markdown/Canvas/TXT с этими маркерами;
- ближайшие занятия по `SCHEDULE.md`.

Если скрипт ничего не нашёл:

- не придумывай задание как факт;
- посмотри `README.md`, презентации и заметки модуля вручную;
- если всё ещё нет явного задания, скажи: “Явной домашки в материалах не нашёл. Могу помочь сформулировать вероятную практику, но её надо подтвердить у преподавателя”.

## Assignment ID

Выбери `assignment_id` так:

1. Если задание явно содержит `assignment_id`, используй его.
2. Если задание относится к занятию по расписанию — `lesson-01`, `lesson-02`, ...
3. Если задание относится к модулю — `module-01`, `module-02`, ...
4. Финальный проект — `final-project`.

Запиши выбранный `assignment_id` в `STUDENT.md`.

## Подготовка Markdown-отчёта

Рекомендуемый формат `content_md`:

```md
# Домашняя работа: <название>

## Студент
- Student ID: <student_id>
- Имя: <student_name или null>

## Assignment
- Assignment ID: <assignment_id>
- Модуль / занятие: <...>

## Что было сделано
...

## Ссылки / артефакты
- Репозиторий:
- Демо:
- Скриншоты / файлы:

## Краткое объяснение решения
...

## Что получилось
...

## Что не получилось / вопросы
...

## Самопроверка
- [ ] Я понимаю, что отправляю.
- [ ] Я проверил, что отчёт не содержит секретов.
- [ ] Я готов отправить эту работу.
```

Перед отправкой проверь:

```bash
python3 - <<'PY'
from pathlib import Path
p = Path('homework/drafts/lesson-01.md')
print(len(p.read_bytes()))
PY
```

Лимит API: 262144 байт.

## Отправка

Токен должен быть в переменной окружения `HOMEWORK_API_TOKEN` или в локальном `.env` в корне проекта. `.env` не коммитится. Не пиши токен в markdown-файлы и не сохраняй в память.

Проверить API:

```bash
python3 .agents/skills/homework-submission/scripts/submit_homework.py --health
```

Dry run без отправки:

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

Успешный ответ HTTP 201 содержит `id`, `filename`, `bytes`, `sha256`, `created_at`.

## После успешной отправки

1. Обнови `STUDENT.md`:
   - статус задания `submitted`;
   - дату/время отправки;
   - receipt path или API id.
2. Обнови сегодняшний `logs/daily/YYYY-MM-DD.md` в разделе “Домашка”.
3. Не записывай токен и Authorization header никуда.
4. Коротко скажи студенту:
   - что отправлено;
   - assignment_id;
   - байты / sha256;
   - где лежит receipt.

## Ошибки

- `HOMEWORK_API_TOKEN is not set`: попроси настроить переменную окружения или локальный `.env`.
- `content_md is too large`: помоги сжать отчёт.
- HTTP 401/403: токен неверный или не имеет доступа; не проси прислать токен в чат, лучше предложи обновить `.env`/секрет.
- HTTP 413: отчёт слишком большой.
- Любая другая ошибка: покажи статус, краткое тело ответа и следующий безопасный шаг.
