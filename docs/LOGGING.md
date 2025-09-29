# Система логирования Content Factory

Интеллектуальная система логирования с двумя режимами: тихий (обычный) и детальный (verbose).

## 🔧 Режимы работы

### Обычный режим (по умолчанию)
Показывает только ключевые этапы пайплайна без лишних деталей.

```bash
python main.py "Ваша тема"
python batch_processor.py topics.txt
```

**Что показывается:**
- Начало и завершение основных этапов
- Количественные результаты (найдено источников, успешно обработано)
- Критические предупреждения и ошибки
- Финальный результат

**Пример вывода:**
```
2025-09-29 00:42:08,414 [INFO] - --- Starting Basic Articles Pipeline for topic: 'test topic' ---
2025-09-29 00:42:08,415 [INFO] - Starting broad search for topic: 'test topic' using API v2
2025-09-29 00:42:09,440 [INFO] - Found 20 results from Firecrawl search.
2025-09-29 00:42:09,445 [INFO] - Finished URL filtering. 19 URLs remaining.
2025-09-29 00:42:50,650 [INFO] - Successfully scraped 18 out of 19 URLs.
2025-09-29 00:42:51,123 [INFO] - Selected top 5 sources.
2025-09-29 00:42:52,456 [INFO] - ✅ Pipeline completed successfully
```

### Verbose режим
Показывает все детали для отладки и мониторинга.

```bash
python main.py "Ваша тема" --verbose
python batch_processor.py topics.txt --verbose
```

**Что добавляется:**
- Детальная информация о каждом шаге
- URL каждого источника при обработке
- Информация о попытках retry
- Техническая информация о моделях LLM
- Подробности об ошибках

**Пример вывода:**
```
2025-09-29 00:36:16,949 [INFO] src.logger_config:621 - --- Starting Basic Articles Pipeline for topic: 'test topic' ---
2025-09-29 00:36:16,950 [DEBUG] src.firecrawl_client:69 - Scraping URL: https://example.com/article1
2025-09-29 00:36:16,951 [DEBUG] src.firecrawl_client:69 - Scraping URL: https://example.com/article2
2025-09-29 00:36:16,952 [INFO] src.llm_processing:905 - 📝 Generating section 1/5: Introduction
2025-09-29 00:36:17,123 [INFO] src.llm_processing:909 - 🔄 Section 1 attempt 1/3: Introduction
```

## 🎯 Фильтрация сообщений

### Ключевые паттерны (показываются всегда)
- Начало этапов: "Starting Basic Articles Pipeline", "Starting broad search"
- Результаты: "Found", "Successfully scraped", "Selected top 5 sources"
- Завершение: "Pipeline completed", "✅", "🎉"
- Предупреждения: "⚠️", "❌", "🔥", "CRITICAL"

### Детальная информация (только в verbose)
- Индивидуальные URL при скрапинге
- Попытки retry для секций
- Технические детали LLM запросов
- Debug информация о scoring

## ⚠️ Предупреждения о факт-чеке

При провале факт-чека система показывает яркие предупреждения:

```
🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥
⚠️  CRITICAL: FACT-CHECK FAILED
Failed groups: 2/4
Failed sections: Introduction, Conclusion, Best Practices
Article contains UNVERIFIED CONTENT - Manual review required!
🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥
```

Предупреждение появляется:
1. Сразу после провала факт-чека
2. В финальном отчете пайплайна

## 🗂️ Логи в файлах

Все логи (включая verbose) всегда сохраняются в файл `app.log` независимо от режима консоли.

## 🔧 Техническая реализация

### QuietModeFilter
Специальный фильтр в `src/logger_config.py` анализирует каждое сообщение и пропускает только ключевые в обычном режиме.

### Конфигурация
```python
# Обычный режим
configure_logging(verbose=False)  # Применяется QuietModeFilter

# Verbose режим
configure_logging(verbose=True)   # Без фильтрации, все сообщения
```

### Подавление шумных библиотек
В обычном режиме подавляются логи от:
- urllib3
- requests
- httpx
- openai

## 💡 Рекомендации

### Для разработки:
```bash
python main.py "test topic" --verbose --skip-publication
```

### Для продакшена:
```bash
python batch_processor.py topics.txt  # Тихий режим
```

### Для отладки проблем:
```bash
python main.py "проблемная тема" --verbose > debug.log 2>&1
```

Это позволит сохранить весь verbose вывод в файл для анализа.

## 🚀 Совместимость

Система логирования совместима со всеми режимами запуска:
- ✅ Одиночная генерация
- ✅ Batch обработка
- ✅ Запуск отдельных этапов (`--start-from-stage`)
- ✅ Все типы контента (`--content-type`)