# Course B: GitHub для совместной разработки

## Описание курса

Курс посвящен использованию GitHub как платформы для совместной разработки, review, публикации изменений и автоматизации проверок. Студенты учатся работать с remote repository, issues, pull requests, code review, branch protection и GitHub Actions.

Курс предполагает, что студент уже понимает базовые операции Git: commit, branch, merge, diff и conflict resolution. Эти темы повторяются только в контексте совместной работы и публикации изменений.

## Цели курса

- Научить студентов связывать локальный Git repository с GitHub remote.
- Показать workflow через issues, branches и pull requests.
- Сформировать навыки code review и обсуждения изменений.
- Научить читать checks, исправлять CI failures и повторно отправлять изменения.
- Познакомить с branch protection и правилами командной работы.
- Показать основы GitHub Actions для тестов и lint.
- Разобрать безопасность: secrets, tokens, private/public repositories.

## Модуль 1. Remote repositories и синхронизация

### Теория

GitHub хранит удаленную копию repository и предоставляет интерфейс для совместной работы. Студенты изучают `origin`, `git remote -v`, `git push`, `git pull`, `git fetch`. Особое внимание уделяется различию между fetch и pull.

Разбираются вопросы:

- что такое remote tracking branch;
- почему локальная ветка может отставать от `origin/main`;
- когда безопаснее сначала выполнить fetch и посмотреть изменения;
- почему force push опасен в общей ветке.

### Практика

Студенты создают repository на GitHub, связывают его с локальным проектом и отправляют первую ветку. Затем имитируют изменение на GitHub и обновляют локальное состояние через fetch.

### Результаты обучения

- Подключать remote repository.
- Различать fetch, pull и push.
- Объяснять состояние локальной branch относительно origin.

## Модуль 2. Issues как постановка задач

### Теория

Issue описывает задачу, дефект, улучшение или вопрос. Хороший issue содержит контекст, ожидаемый результат, критерии приемки и links на связанные материалы. В учебной команде issue помогает связать изменение кода с причиной.

### Практика

Студенты создают issue для улучшения README, issue для исправления ошибки в конфигурации и issue для добавления проверки в CI. Для каждого issue нужно написать acceptance criteria.

### Результаты обучения

- Формулировать issue с понятной целью.
- Писать acceptance criteria.
- Связывать branch и pull request с issue.

## Модуль 3. Pull Request workflow

### Теория

Pull request — это предложение изменить target branch. Он показывает diff, commits, checks и discussion. Студенты изучают lifecycle pull request:

- создать branch от актуального main;
- внести изменения локально;
- push branch на GitHub;
- открыть pull request;
- дождаться checks;
- получить review;
- внести исправления;
- выполнить merge.

### Практика

Студенты открывают pull request по своему issue. В описании PR нужно указать problem, solution, test evidence и checklist. Отдельное внимание уделяется небольшому размеру PR.

### Результаты обучения

- Создавать pull request из feature branch.
- Читать diff в интерфейсе GitHub.
- Обновлять PR после замечаний.

## Модуль 4. Code review

### Теория

Code review — это не поиск виноватых, а проверка качества изменения. Студенты учатся оставлять конкретные comments, отличать blocking feedback от suggestion и проверять, что PR решает исходный issue.

Разбираются виды feedback:

- correctness;
- maintainability;
- tests;
- documentation;
- security;
- style.

### Практика

Студенты получают чужой PR и должны оставить не менее трех review comments: один про корректность, один про тесты, один про документацию. Затем автор PR отвечает и вносит исправления.

### Результаты обучения

- Проводить review без агрессивных формулировок.
- Обосновывать замечания ссылкой на diff.
- Проверять, закрывает ли PR acceptance criteria.

## Модуль 5. Checks и GitHub Actions

### Теория

GitHub Actions запускает workflow на событиях: push, pull_request, manual dispatch. В учебном проекте workflow обычно запускает tests, lint и basic validation. Студенты изучают структуру YAML workflow:

- `name`;
- `on`;
- `jobs`;
- `runs-on`;
- `steps`;
- checkout;
- setup runtime;
- install dependencies;
- run tests.

### Практика

Студенты добавляют `.github/workflows/test.yml`, который запускает тесты проекта. Затем намеренно ломают тест, видят failed check, исправляют ошибку и убеждаются, что PR снова зеленый.

### Результаты обучения

- Читать GitHub Actions workflow.
- Находить причину failed check.
- Исправлять PR до зеленого CI.

## Модуль 6. Branch protection и правила команды

### Теория

Branch protection помогает сохранить main стабильным. Студенты изучают правила:

- запрет direct push в main;
- обязательный PR;
- обязательные reviews;
- обязательные status checks;
- запрет merge при unresolved conversations.

### Практика

В учебном repository включаются protection rules. Студенты пытаются отправить изменение напрямую в main, видят отказ, затем проходят правильный PR workflow.

### Результаты обучения

- Объяснять, зачем нужны protected branches.
- Настраивать минимальные правила защиты main.
- Работать через PR без обхода процесса.

## Модуль 7. Безопасность GitHub repository

### Теория

GitHub repository часто содержит конфигурацию, CI и секреты. Студенты изучают:

- почему нельзя commit API keys;
- где хранить GitHub Actions secrets;
- как отличать public и private repositories;
- зачем нужен `.gitignore`;
- как реагировать, если секрет случайно попал в commit.

### Практика

Студенты настраивают repository secrets для workflow, добавляют `.gitignore`, проверяют PR на отсутствие ключей и обсуждают план ротации секрета при утечке.

### Результаты обучения

- Не публиковать secrets в repository.
- Использовать GitHub Actions secrets.
- Проверять PR на случайные sensitive files.

## Итоговый проект

Студенты работают в паре. Нужно:

1. Создать GitHub repository и issue backlog.
2. Для одной задачи создать feature branch.
3. Открыть pull request с описанием problem, solution и test evidence.
4. Добавить GitHub Actions workflow для запуска тестов.
5. Провести review чужого PR.
6. Исправить замечания и добиться зеленого check.
7. Выполнить merge по правилам protected branch.
8. Подготовить краткий отчет о collaboration workflow.

## Критерии успешности

- PR связан с issue и содержит понятное описание.
- Checks проходят перед merge.
- Review comments конкретны и полезны.
- Protected branch не обходится вручную.
- Secrets не публикуются в repository.
- Отчет объясняет, как локальная ветка, remote branch, PR и CI связаны в одном workflow.
