# Проверочные задания: Git и GitHub

## Assessment A1. Локальная история Git

- Course: Course A
- Skill IDs: git_repository_model, git_status_diff, git_commit_quality
- Type: practical repository task

Студент получает папку с небольшим текстовым проектом. Нужно инициализировать Git repository, сделать серию commits и подготовить отчет.

Критерии:

- repository содержит не менее пяти логических commits;
- каждый commit имеет понятный message;
- перед каждым commit студент проверяет `git status` и staged diff;
- в отчете объясняется различие working tree, staging area и commit history.

## Assessment A2. Branch и merge conflict

- Course: Course A
- Skill IDs: git_branching, git_merge_conflict_resolution
- Type: conflict resolution lab

Студент создает feature branch, меняет документ, затем получает изменение в main, которое конфликтует с feature branch. Нужно выполнить merge, разрешить конфликт вручную и завершить merge commit.

Критерии:

- feature branch создана от актуального main;
- conflict markers удалены корректно;
- итоговый файл сохраняет полезные изменения из обеих веток;
- студент объясняет, почему возник конфликт.

## Assessment A3. Безопасная отмена изменений

- Course: Course A
- Skill IDs: git_restore_revert_reset
- Type: recovery exercise

Студент получает repository с ошибочным commit и незакоммиченным изменением. Нужно восстановить файл через `git restore`, отменить опубликованный commit через `git revert` и объяснить, почему destructive reset не подходит.

Критерии:

- unstaged change восстановлен безопасно;
- ошибочный commit отменен отдельным revert commit;
- история остается читаемой;
- в отчете описан выбор команды.

## Assessment B1. Remote synchronization

- Course: Course B
- Skill IDs: github_remote_sync, git_status_diff
- Type: remote workflow task

Студент связывает локальный repository с GitHub remote, отправляет feature branch, выполняет fetch и объясняет состояние локальной branch относительно `origin/main`.

Критерии:

- remote `origin` настроен корректно;
- branch опубликована на GitHub;
- студент отличает fetch от pull;
- отчет содержит вывод `git branch --all` или аналогичное объяснение.

## Assessment B2. Issue и Pull Request

- Course: Course B
- Skill IDs: github_issue_planning, github_pull_request_workflow, git_commit_quality
- Type: collaboration task

Студент создает issue с acceptance criteria, делает feature branch, открывает pull request и связывает PR с issue.

Критерии:

- issue содержит problem statement и acceptance criteria;
- PR содержит problem, solution и test evidence;
- commits в PR небольшие и осмысленные;
- PR можно проверить по diff.

## Assessment B3. Code Review

- Course: Course B
- Skill IDs: github_code_review, github_pull_request_workflow
- Type: peer review

Студент проверяет чужой pull request и оставляет review comments по correctness, tests и documentation.

Критерии:

- comments привязаны к конкретным строкам diff;
- замечания сформулированы уважительно;
- хотя бы одно замечание связано с acceptance criteria;
- автор PR отвечает на comments.

## Assessment B4. GitHub Actions и branch protection

- Course: Course B
- Skill IDs: github_actions_ci, github_branch_protection, github_repository_security
- Type: CI and repository policy task

Студент добавляет workflow `.github/workflows/test.yml`, включает branch protection и проверяет, что PR нельзя merge без зеленого check.

Критерии:

- workflow запускается на `pull_request`;
- failed check объяснен и исправлен;
- main защищен от direct push;
- secrets не публикуются в repository, а используются через GitHub Actions secrets.

## Cross-course diagnostic task

- Course: Both
- Skill IDs: git_branching, github_pull_request_workflow, github_actions_ci
- Type: integration reflection

Студент объясняет, какие навыки из локального Git-курса являются prerequisites для GitHub workflow.

Критерии:

- явно указана связь branch -> remote branch -> pull request;
- объяснено, почему хорошие commits помогают code review;
- объяснено, почему локальный conflict resolution важен перед merge PR;
- указано, какие темы отсутствуют в Course A, но нужны для Course B: remote sync, PR review, CI.
