# UML-диаграммы Course Connector

Ниже приведены основные диаграммы проекта в формате Mermaid. Они описывают текущий MVP: локальный CLI-инструмент, который принимает файлы двух курсов, справочник навыков, материалы оценивания и конфигурацию, затем строит preprocessing-контекст, обращается к LLM provider и сохраняет отчетные файлы.

## Use Case

```mermaid
flowchart LR
    Teacher[Преподаватель / методист]
    Integrator[Интегратор учебных данных]

    subgraph System[Course Connector CLI]
        Run[Запустить сравнение двух курсов]
        Load[Загрузить входные файлы]
        Validate[Проверить формат и полноту входов]
        Preprocess[Подготовить preprocessing-контекст]
        Analyze[Найти relation-кандидаты]
        Report[Сформировать Markdown-отчет]
        Json[Сформировать JSON-результат]
        Diagnostics[Сохранить диагностические artifacts]
        HandleErrors[Получить понятные warnings / provider_error]
    end

    Teacher --> Run
    Integrator --> Run
    Run --> Load
    Load --> Validate
    Validate --> Preprocess
    Preprocess --> Analyze
    Analyze --> Report
    Analyze --> Json
    Preprocess --> Diagnostics
    Analyze --> HandleErrors

    Teacher --> Report
    Integrator --> Json
    Integrator --> Diagnostics
```

## Context Diagram

```mermaid
flowchart TB
    User[Преподаватель / методист]
    Integrator[Интеграционный сценарий]

    subgraph LocalMachine[Локальная среда пользователя]
        CLI[Course Connector CLI]
        InputFiles[(Course A, Course B,\nSkill Dictionary,\nAssessments, Config)]
        OutputFiles[(report.md, result.json,\npreprocessing artifacts)]
        LocalEmbeddings[Optional local\nsentence-transformers]
    end

    subgraph ExternalServices[Внешние LLM-сервисы]
        OpenAI[OpenAI API]
        OpenRouter[OpenRouter API]
        RouterAI[RouterAI API]
    end

    User -->|запускает course-connector run| CLI
    Integrator -->|вызывает CLI в automation| CLI
    CLI -->|читает| InputFiles
    CLI -->|пишет| OutputFiles
    CLI -.->|если embeddings.enabled=true| LocalEmbeddings
    CLI -.->|если provider=openai| OpenAI
    CLI -.->|если provider=openrouter| OpenRouter
    CLI -.->|если provider=routerai| RouterAI
    CLI -.->|если provider=mock| CLI
```

## Component Diagram

```mermaid
flowchart TB
    CLI[cli.py\nargparse entry point]
    Loader[input_layer.loader\nload_input_payload]
    Pipeline[pipeline.py\nrun_pipeline_with_progress]
    PreConfig[preprocessing_layer.config\nPreprocessingConfig]
    PreFacade[preprocessing_layer.facade\nprepare_analysis_context]
    Chunking[chunking.py\nbuild_chunks]
    Retrieval[retrieval.py\nretrieve_pairs]
    BatchPlanner[batch_planner.py\nplan_skill_batches]
    LLMAnalyzer[llm_layer.analyzer / batch_analyzer]
    ProviderFactory[llm_layer.providers.factory\ncreate_provider]
    Providers[Mock / OpenAI / OpenRouter / RouterAI providers]
    Reports[report_layer\nrender_markdown_report / build_json_result]
    Outputs[(output directory)]

    CLI --> Loader
    CLI --> Pipeline
    Pipeline --> PreConfig
    Pipeline --> PreFacade
    PreFacade --> Chunking
    PreFacade --> Retrieval
    PreFacade --> BatchPlanner
    Pipeline --> LLMAnalyzer
    LLMAnalyzer --> ProviderFactory
    ProviderFactory --> Providers
    Pipeline --> Reports
    Reports --> Outputs
    PreFacade --> Outputs
```

## Sequence Diagram: основной запуск CLI

```mermaid
sequenceDiagram
    actor User as Пользователь
    participant CLI as course-connector CLI
    participant Input as Input Layer
    participant Pipeline as Pipeline
    participant Pre as Preprocessing Layer
    participant LLM as LLM Layer
    participant Provider as LLM Provider
    participant Report as Report Layer
    participant FS as Output Directory

    User->>CLI: course-connector run --course-a ... --output-dir ...
    CLI->>Input: load_input_payload(...)
    Input-->>CLI: input_payload или InputLayerError
    CLI->>Pipeline: run_pipeline_with_progress(input_payload)
    Pipeline->>Pre: prepare_analysis_context(input_payload)
    Pre-->>Pipeline: analysis_context, metrics, warnings
    Pipeline->>LLM: analyze_courses(...) или analyze_batches(...)
    LLM->>Provider: generate analysis response
    Provider-->>LLM: relations или provider error
    LLM-->>Pipeline: normalized analysis
    Pipeline->>Report: render_markdown_report(...)
    Pipeline->>Report: build_json_result(...)
    Pipeline->>FS: write report.md, result.json, artifacts
    Pipeline-->>CLI: PipelineResult
    CLI-->>User: paths to report.md and result.json
```

## Activity Diagram: обработка данных

```mermaid
flowchart TD
    Start([Старт])
    Args[Прочитать CLI-аргументы]
    Load[Загрузить course_a, course_b,\nskill_dictionary, assessments, config]
    Validate{Входные данные валидны?}
    Error[Завершить с ошибкой CLI code 2]
    PreEnabled{preprocessing.enabled?}
    FullInput[Использовать full_input context]
    Chunks[Построить chunks и course profiles]
    Mode{analysis_mode}
    Retrieval[Подобрать retrieved_pairs\nи selected_chunks]
    SmartBatch[Сформировать skill_batches]
    LLM[Выполнить LLM-анализ]
    ProviderOk{Provider вернул ответ?}
    ProviderError[Сформировать provider_error\nс warnings и пустыми relations]
    Normalize[Нормализовать relations]
    Write[Записать report.md, result.json\nи intermediate outputs]
    End([Готово])

    Start --> Args --> Load --> Validate
    Validate -- нет --> Error --> End
    Validate -- да --> PreEnabled
    PreEnabled -- нет --> FullInput --> LLM
    PreEnabled -- да --> Chunks --> Mode
    Mode -- full_input / retrieval --> Retrieval --> LLM
    Mode -- smart_batch --> SmartBatch --> LLM
    LLM --> ProviderOk
    ProviderOk -- нет --> ProviderError --> Write
    ProviderOk -- да --> Normalize --> Write
    Write --> End
```

## Deployment Diagram

```mermaid
flowchart LR
    subgraph Workstation[Рабочая станция пользователя]
        Python[Python 3.11+ environment]
        Package[course-connector package]
        DataDir[(data/examples или пользовательские файлы)]
        Config[(configs/default.yaml или custom config)]
        Outputs[(outputs/...)]
        Docker[Optional Docker / docker compose]
    end

    subgraph Network[Сеть, если выбран внешний provider]
        OpenAI[OpenAI API]
        OpenRouter[OpenRouter API]
        RouterAI[RouterAI API]
    end

    Python --> Package
    Package --> DataDir
    Package --> Config
    Package --> Outputs
    Docker -.-> Package
    Package -.-> OpenAI
    Package -.-> OpenRouter
    Package -.-> RouterAI
```
