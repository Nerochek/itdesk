# Запуск и объяснение аналитики ITDesk

Модуль выполняет пункты 6–15 плана практики ПМ 12. Откройте папку `C:\Users\Nero\Desktop\itdesk` в Visual Studio Code и выберите «Терминал → Создать терминал». Команды выполняются из этой папки.

## Что требуется

| Компонент | Для чего нужен | Состояние на этом компьютере |
| --- | --- | --- |
| Python и pip | Скрипты и библиотеки | Python 3.14.7 установлен |
| Visual Studio Code | Просмотр проекта и терминал | Установлен |
| MongoDB и PyMongo | Документы и запросы | MongoDB 9.0.8 в `.tools/mongodb`, PyMongo установлен |
| Pandas | Очистка и таблицы | Установлен |
| PySpark и Spark SQL | RDD, DataFrame и SQL | PySpark 4.3.0, вычисления проверены |
| Java JDK 17 | Среда выполнения Spark и Hadoop | В `.tools/java` |
| Apache Hadoop | Настоящий MapReduce | Архив 3.5.0 распакован, отсутствуют Windows native-компоненты |
| Matplotlib | Графики | Установлен |

Новые библиотеки перечислены в `requirements-analytics.txt`. Дополнительные СУБД и платформы для аналитики не используются. Java нужна для запуска Hadoop и Spark. Предупреждение PySpark о Pandas 3.x не препятствует проверенным здесь RDD/DataFrame/SQL; Pandas API on Spark не используется.

`.tools` занимает несколько гигабайт с архивами и не включается в Git. При переносе репозитория среды выполнения нужно установить или перенести отдельно. Интернет нужен для установки библиотек и импорта API.

## Быстрый запуск на этом компьютере

```powershell
cd C:\Users\Nero\Desktop\itdesk
python run_analytics.py doctor
python run_analytics.py full
```

`full` подключит или запустит MongoDB, создаст коллекции, загрузит учебные данные и заявки из `itdesk.db`, проверит CRUD и поиск, импортирует внешний API, выполнит Pandas, оптимизацию MongoDB, графики и Spark. При ошибке команда останавливается. Настоящий Hadoop запускается отдельно и требует завершения настройки Windows native-компонентов.

Результаты: `analytics_data/dashboard.png`, `dashboard.pdf`, `summary.csv`. Измерения: `spark_sql.json`, `mongo_explain.json`.

Без интернета, MongoDB и Java можно проверить Pandas, Matplotlib и алгоритм MapReduce:

```powershell
python run_analytics.py demo
```

`demo` перезаписывает очищенные файлы и графики набором из 10000 синтетических заявок. Для восстановления смешанного набора выполните `full` или повторите очистку из MongoDB, графики и Spark.

## Подготовка на другом компьютере

Установите Python, Visual Studio Code, MongoDB, JDK 17 и Apache Hadoop. Официальные источники: [MongoDB](https://www.mongodb.com/try/download/community), [Hadoop](https://hadoop.apache.org/releases), [OpenJDK Temurin](https://adoptium.net/temurin/releases/?version=17), [требования Spark](https://spark.apache.org/docs/latest/).

Hadoop 3.5 поддерживает Java 17, которая подходит и для Spark 4.x. Подготовьте Python-окружение без активации PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements-analytics.txt
.\venv\Scripts\python.exe run_analytics.py doctor
```

Далее `python` можно заменить на `.\venv\Scripts\python.exe`. Если Java и Hadoop установлены вне `.tools`, задайте пути в текущем терминале:

```powershell
$env:JAVA_HOME = 'C:\путь\к\jdk-17'
$env:HADOOP_HOME = 'C:\путь\к\hadoop-3.5.0'
```

`run_analytics.py` сам находит подготовленные `.tools/java` и `.tools/hadoop-3.5.0` и добавляет их в окружение своих процессов. MongoDB подключается к `127.0.0.1:27017`, база — `itdesk_analytics`. При установленной службе MongoDB запустите её; копию из `.tools/mongodb` запустит `start-mongo`. Другой адрес задаётся через `$env:ITDESK_MONGO_URI`, имя базы — `$env:ITDESK_MONGO_DB`.

## Объяснение выполненных пунктов

**6. MongoDB.** `init` создаёт `tickets_raw` для исходных заявок, `external_raw` для исходных ответов API, `tickets_clean` для очищенных данных, `crud_demo` для демонстрации удаления. Индекс `source + source_id` отличает одинаковые ID разных источников.

**7. CRUD.** Create — вставка документа; Read — чтение; Update — изменение; Delete — удаление. `crud` проверяет эти действия на собственном документе. `load` обновляет/добавляет JSON-документы пакетами. Повторная загрузка не создаёт дублей; исчезнувшие из источника документы автоматически из MongoDB не удаляются.

**8. PyMongo.** Python-драйвер подключается к MongoDB. `search` фильтрует по статусу и категории, сортирует по ID и ограничивает выдачу. Ошибка подключения имеет тайм-аут и завершает команду с ненулевым кодом.

**9. API.** `fetch` получает публичные учебные todo из JSONPlaceholder. Исходные ответы сохраняются отдельно; `completed` переводится в `resolved` или `new`. Дата создания у API неизвестна — она пустая. Это учебные данные, а не реальные обращения университета.

**10. Pandas.** `clean` проверяет положительные целые ID, удаляет пустые названия, пробелы и повторы, нормализует поля и даты. Неизвестные справочники заменяются на `other`, `new`, `medium`; неизвестные даты остаются пустыми. Даты без часового пояса при преобразовании считаются UTC. Создаются отсортированный набор и выборка активных заявок `active.csv`. Исходные документы остаются в `tickets_raw`.

**11. MapReduce.** Mapper читает JSONL и выдаёт `категория → 1` для активных заявок. Hadoop сортирует пары по ключу, reducer суммирует единицы. Combiner уменьшает объём передачи промежуточным суммированием. `local_check` проверяет алгоритм на Python и не заменяет Hadoop.

**12. Spark.** Одни заявки обрабатываются как RDD через `filter/map/reduceByKey` и как DataFrame через `filter/groupBy/count`. Результаты сравниваются. Python сохраняет небольшой агрегат из шести категорий; вычисления выполняет Spark.

**13. Spark SQL.** Создаются временные таблицы, выполняется SQL с фильтром и группировкой, затем ранняя проекция столбцов и кэширование. Сохраняются планы и медианы трёх измерений после прогрева. Время построения кэша учитывается отдельно: на одном небольшом запросе кэш может не окупиться.

**14. Производительность.** `benchmark` сравнивает полный просмотр MongoDB с индексом по статусу и категории. Результаты должны совпасть. Показатель `totalDocsExamined` показывает объём просмотра; миллисекунды на малых данных нестабильны. Существующие индексы не удаляются.

**15. Matplotlib.** `plot` строит три диаграммы в PNG/PDF и создаёт CSV со сводкой по источнику, категории и статусу.

## Отдельные команды

```powershell
python run_analytics.py start-mongo
python -m analytics.pipeline init
python -m analytics.pipeline seed --count 10000
python -m analytics.pipeline load
python -m analytics.pipeline crud
python -m analytics.pipeline search --status new --category network --limit 5
python -m analytics.pipeline export-itdesk
python -m analytics.pipeline load --input analytics_data/itdesk.jsonl
python -m analytics.pipeline fetch
python -m analytics.pipeline clean --to-mongo
python -m analytics.pipeline benchmark
python -m analytics.pipeline plot
python run_analytics.py spark
python -m analytics.mapreduce.local_check
```

`export-itdesk` читает существующую SQLite только для переноса заявок в аналитику. Пароли, токены, пользователи и комментарии не экспортируются. Аналитическая база не добавляет записи в окно ITDesk.

## Завершение настройки Hadoop

На этом Windows-компьютере настоящий запуск остановился на отсутствии `winutils.exe`. Нужна совместимая сборка Windows native-компонентов Hadoop. После её установки:

```powershell
python run_analytics.py hadoop
```

Режим Hadoop — standalone: локальная файловая система, один reducer, без HDFS/YARN-кластера. Успех — код 0, файл `_SUCCESS` и файлы `part-*` в `analytics_data/hadoop-output`. До этого пункт 11 не завершён. Статус: `hadoop_status.json`, журнал: `hadoop_attempt.log` в `analytics_data`.

При повторном запуске после успеха укажите новую выходную папку. Hadoop не перезаписывает существующую:

```powershell
python -m analytics.mapreduce.run --output analytics_data/hadoop-output-2
```

В новом терминале для этой отдельной команды задайте `JAVA_HOME`, `HADOOP_HOME` и добавьте Java в `PATH`, либо запускайте через `run_analytics.py`, который делает это автоматически. PowerShell может блокировать `.ps1`, поэтому основная инструкция использует Python.

Для Linux с установленными Java, Python и Hadoop подготовленные mapper/reducer запускаются обычным Streaming:

```sh
hadoop jar "$HADOOP_HOME"/share/hadoop/tools/lib/hadoop-streaming-*.jar -D mapreduce.framework.name=local -D fs.defaultFS=file:/// -files analytics/mapreduce/mapper.py,analytics/mapreduce/reducer.py -input analytics_data/clean.jsonl -output analytics_data/hadoop-output -mapper "python3 mapper.py" -reducer "python3 reducer.py" -combiner "python3 reducer.py" -numReduceTasks 1
```

## Исходное приложение ITDesk

Исходное окно заявок использует ранее существовавшие PyQt6, FastAPI и SQLite, которых нет в плане ПМ 12. Новая аналитика от них не зависит. Если нужно запускать именно исходное приложение, при отсутствии его зависимостей установите `python -m pip install -r requirements.txt` и `python -m pip install -e .`.

Откройте два терминала VS Code в папке проекта:

```powershell
# Терминал 1
python run_server.py
```

```powershell
# Терминал 2
python run_client.py
```

Сервер использует порт 8000, MongoDB — 27017. Учётные записи: `admin/admin123`, `tech/tech123`, если пароли ранее не менялись. Пользователь регистрируется в окне входа, сотрудник меняет статусы и видит статистику. Настройки — `config.ini`.

Чтобы аналитика увидела новые заявки, повторите экспорт ITDesk, загрузку `itdesk.jsonl`, очистку, графики и Spark. Исходная база на момент проверки пуста, поэтому для демонстрации использованы синтетические данные и внешний API.

Сервер останавливается Ctrl+C, клиент — закрытием окна. MongoDB остаётся отдельным локальным процессом; корректная остановка локальной базы проекта: `python -m analytics.stop_mongo`.

## Проверка

```powershell
python -m unittest analytics.test_pipeline -v
```

Проверяются неправильные ID, пустые поля, повторы, нормализация и MapReduce. Совпадение RDD/DataFrame/SQL проверяется при каждом запуске Spark. Таблица выполненного: `docs/practice-report.md` и `docs/practice-report.csv`.
