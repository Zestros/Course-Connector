# Сценарий: Git -> GitHub

Этот сценарий показывает пользу Course Connector без запуска программы.

## Контекст

Есть два курса:

- Course A: Git для локального контроля версий.
- Course B: GitHub для совместной разработки.

Course A учит:

- working tree;
- staging area;
- commits;
- branches;
- merge conflicts;
- restore, revert, reset.

Course B требует:

- remote repository;
- issues;
- pull requests;
- code review;
- GitHub Actions;
- branch protection;
- repository security.

## Проблема

Преподаватель Course B может считать, что студенты уже готовы к GitHub workflow, потому что они проходили Git. Но локальный Git и командная работа через GitHub - разные уровни навыков.

Например, студент может уметь делать commit, но не понимать:

- как связать branch с issue;
- как оформить pull request;
- как пройти review;
- как исправить failed CI check;
- почему нельзя хранить secret в repository.

## Что делает Course Connector

Программа читает:

- два курса;
- skill dictionary;
- assessments;
- config.

Затем она строит chunks, связывает их со skill ids и ищет relation candidates.

## Какой вывод полезен

Пример candidate:

```text
Type: probable_gap
Skill: github_pull_request_workflow

Course A дает базу по commits и branches.
Course B ожидает pull request workflow.
Явного обучения pull request в Course A нет.
```

Методический смысл:

- это не ошибка Course A;
- это сигнал, что перед Course B может понадобиться bridge material;
- можно добавить вводное занятие, checklist или подготовительное задание.

## Как читать отчет

Методист смотрит не только на label `probable_gap`, но и на evidence:

- какой фрагмент Course A найден как подготовка;
- какой фрагмент Course B требует новый навык;
- какое assessment проверяет этот навык.

После этого relation candidate получает ручной статус:

- `confirmed` - пробел реальный;
- `rejected` - в курсе есть подготовка, но она плохо распознана;
- `requires_discussion` - нужно обсудить с преподавателями.

## Польза

Course Connector экономит время на первичном сравнении курсов. Он не принимает решение за методиста, но быстро показывает места, где стоит проверить согласованность программы.
