# Troubleshooting - Решение проблем

Часто задаваемые вопросы и решение типичных проблем при работе с Content Factory.

---

## 📋 Содержание

1. [FAQ - Частые вопросы](#faq---частые-вопросы)
2. [Ошибки API](#ошибки-api)
3. [Проблемы с LLM](#проблемы-с-llm)
4. [Проблемы с публикацией](#проблемы-с-публикацией)
5. [Производительность](#производительность)
6. [Известные ограничения](#известные-ограничения)

---

## 💬 FAQ - Частые вопросы

### Q: Сколько времени занимает генерация одной статьи?

**A**: ~12-17 минут для полного пайплайна (14 этапов).

Можно ускорить:
```bash
# Без fact-check (~10-12 мин)
python3 main.py "тема" --fact-check-mode off

# Без link placement (~10-12 мин)
python3 main.py "тема" --link-placement-mode off

# Без обоих (~8-10 мин)
python3 main.py "тема" --fact-check-mode off --link-placement-mode off
```

### Q: Сколько токенов расходуется на статью?

**A**: ~45-55k tokens в среднем.

Распределение:
- Генерация: 30-40k tokens
- Fact-check: 10-15k tokens
- Editorial review: 5-10k tokens

### Q: Можно ли использовать только бесплатные модели?

**A**: Да! DeepSeek Chat v3.1 FREE используется по умолчанию.

**Обязательные платные API**:
- Firecrawl (поиск и парсинг контента)
- Google Gemini API (только для fact-check с веб-поиском)

### Q: Как отключить публикацию в WordPress?

**A**: Добавьте флаг `--skip-publication`:

```bash
python3 main.py "тема" --skip-publication
```

Результаты сохранятся в `output/{topic}/`, но публикация не произойдет.

### Q: Можно ли возобновить прерванную batch обработку?

**A**: Да, используйте флаг `--resume`:

```bash
python3 batch_processor.py topics.txt --resume
```

Система продолжит с места остановки.

### Q: Как запустить только определенный этап?

**A**: Используйте `--start-from-stage` для продолжения с конкретного этапа:

```bash
# 1. Генерация статьи (этап 8)
# Требуется: 07_ultimate_structure/ultimate_structure.json
python3 main.py "тема" --start-from-stage generate_article

# 2. Перевод (этап 9)
# Требуется: 08_article_generation/wordpress_data.json
python3 main.py "тема" --start-from-stage translation

# 3. Fact-check (этап 10)
# Требуется: 09_translation/translated_wordpress_data.json
python3 main.py "тема" --start-from-stage fact_check

# 4. Link placement (этап 11)
# Требуется: 10_fact_check/fact_checked_wordpress_data.json
python3 main.py "тема" --start-from-stage link_placement

# 5. Editorial review (этап 12)
# Требуется: 11_link_placement/link_placement_wordpress_data.json
python3 main.py "тема" --start-from-stage editorial_review

# 6. Публикация (этап 13)
# Требуется: 12_editorial_review/final_wordpress_data.json
python3 main.py "тема" --start-from-stage publication
```

**Важно**: Папка `output/{тема}/` должна уже существовать с выходными данными предыдущих этапов.

### Q: Как сменить язык генерации?

**A**: Используйте параметр `--language`:

```bash
# На английский
python3 main.py "тема" --language "english"

# На испанский
python3 main.py "тема" --language "spanish"

# На русский (по умолчанию)
python3 main.py "тема" --language "русский"
```

### Q: Fact-check не работает / возвращает ошибки

**A**: Проверьте:

1. Установлен ли `GEMINI_API_KEY` в `.env`
2. Не исчерпана ли квота API
3. Запустите с verbose для деталей:
   ```bash
   python3 main.py "тема" --verbose
   ```

### Q: Где найти сырые ответы LLM для отладки?

**A**: Все LLM запросы/ответы сохраняются:

```
output/{topic}/{stage}/
├── llm_requests/           # Что ушло в LLM
│   └── request_{timestamp}.txt
└── llm_responses_raw/      # Что пришло от LLM
    └── response_{timestamp}.txt
```

### Q: Как увеличить длину статьи?

**A**: Используйте `--article-length`:

```bash
python3 main.py "тема" --article-length 10000
```

Параметр применяется на этапе editorial_review.

### Q: Можно ли изменить стиль написания?

**A**: Да, используйте переменные:

```bash
python3 main.py "тема" \
  --author-style "technical" \
  --tone-of-voice "formal" \
  --target-audience "разработчики"
```

---

## 🔥 Ошибки API

### Ошибка: "Firecrawl API key not found"

**Причина**: Отсутствует `FIRECRAWL_API_KEY` в `.env`

**Решение**:
```bash
# Создайте .env файл в корне проекта
echo "FIRECRAWL_API_KEY=your_key" >> .env
```

### Ошибка: "OpenRouter API key not found"

**Причина**: Отсутствует `OPENROUTER_API_KEY` в `.env`

**Решение**:
```bash
echo "OPENROUTER_API_KEY=sk-or-v1-your_key" >> .env
```

**Важно**: OpenRouter нужен даже для DeepSeek FREE модели!

### Ошибка: "Gemini API key not found"

**Причина**: Отсутствует `GEMINI_API_KEY` в `.env`

**Решение**:
```bash
echo "GEMINI_API_KEY=AIzaSyAyour_key" >> .env
```

### Ошибка: "Rate limit exceeded"

**Причина**: Исчерпан лимит API запросов.

**Решение**:
1. Подождите несколько минут
2. Проверьте квоты в dashboards:
   - Firecrawl: https://firecrawl.dev/dashboard
   - OpenRouter: https://openrouter.ai/keys
   - Google AI: https://aistudio.google.com/apikey

### Ошибка: "Request timeout"

**Причина**: Слишком долгий запрос к API.

**Решение**:
1. Увеличьте таймауты в `src/config.py`:
   ```python
   MODEL_TIMEOUT = 120  # Было 60
   ```
2. Проверьте интернет соединение
3. Попробуйте снова

---

## 🤖 Проблемы с LLM

### Проблема: JSON parsing error "Expecting value"

**Причина**: LLM вернул некорректный JSON.

**Решение**:
1. Проверьте сырой ответ:
   ```
   output/{topic}/{stage}/llm_responses_raw/response_*.txt
   ```
2. Система автоматически пытается исправить (4 уровня parsing)
3. Если не помогает - используйте fallback модель

### Проблема: Контент обрезается / теряется

**Причина**: Gemini multi-part responses не склеиваются.

**Решение**: Проверьте логи на наличие:
```
🔍 Gemini returned X part(s) in response
📏 Total combined content: XXXX chars
```

Если проблема осталась - обновите до последней версии (2.3.0+).

### Проблема: Модель "забывает" тему статьи

**Причина**: LLM токены загрязняют контекст.

**Решение**: Система автоматически очищает токены (`clean_llm_tokens()`).

Если проблема осталась:
1. Проверьте версию (должна быть 2.1.2+)
2. Запустите с verbose для деталей

### Проблема: Спам-контент (символы "----" или "...")

**Причина**: LLM генерирует бракованный контент.

**Решение**: Система автоматически валидирует (`validate_content_quality()`).

Валидация включена на всех LLM этапах (версия 2.1.4+).

### Проблема: Статья получилась слишком короткой

**Решение**:
```bash
# Укажите целевую длину
python3 main.py "тема" --article-length 10000

# Добавьте больше деталей в requirements
python3 main.py "тема" --custom-requirements "Больше примеров и деталей"
```

---

## 📝 Проблемы с публикацией

### Ошибка: "WordPress authentication failed"

**Причина**: Неверные credentials в `.env`

**Решение**:
1. Проверьте `.env`:
   ```bash
   WORDPRESS_URL=https://your-site.com
   WORDPRESS_USERNAME=your_username
   WORDPRESS_APP_PASSWORD=xxxx xxxx xxxx xxxx
   ```
2. Убедитесь что используете **App Password**, не обычный пароль
3. Создайте App Password: WordPress Admin → Пользователи → Профиль → Пароли приложений

### Ошибка: "Post creation failed"

**Причина**: Проблемы с REST API или правами.

**Решение**:
1. Проверьте что REST API доступен:
   ```bash
   curl https://your-site.com/wp-json/wp/v2/posts
   ```
2. Убедитесь что у пользователя есть права публикации
3. Проверьте версию WordPress (5.0+)

### Проблема: Yoast SEO поля не заполняются

**Причина**: Нужен Custom Yoast endpoint.

**Решение**:
1. Установите Custom Yoast plugin (см. `docs/WORDPRESS_INTEGRATION.md`)
2. Проверьте endpoint:
   ```bash
   curl https://your-site.com/wp-json/custom-yoast/v1/
   ```

### Проблема: Code blocks отображаются неправильно

**Причина**: WordPress `wpautop` ломает `<pre>` блоки.

**Решение**: Система автоматически исправляет (`fix_content_newlines()`).

Если проблема осталась:
1. Проверьте версию (2.0.5+)
2. Отключите `wpautop` для постов в WordPress

---

## ⚡ Производительность

### Проблема: Pipeline выполняется слишком долго

**Ожидаемое время**: 12-17 минут

**Если дольше**:

1. Проверьте internet скорость
2. Уменьшите количество источников в `config.py`:
   ```python
   TOP_N_SOURCES = 3  # Было 5
   ```
3. Отключите тяжелые этапы:
   ```bash
   python3 main.py "тема" --fact-check-mode off --link-placement-mode off
   ```

### Проблема: Высокое использование памяти

**Batch processing**:

Система автоматически оптимизирует память (версия 2.0+):
- Garbage collection между темами
- Очистка HTTP connections
- Сброс token tracker

**Лимит**: 2GB на процесс

**Если превышается**:
1. Проверьте `batch_config.py`:
   ```python
   BATCH_CONFIG = {
       "max_memory_mb": 2048,
   }
   ```
2. Уменьшите `TOP_N_SOURCES` до 3
3. Запускайте batch processor с меньшими порциями тем

### Проблема: Fact-check занимает слишком много времени

**Причина**: Google Gemini выполняет 10+ поисковых запросов.

**Решение**:
1. Отключите fact-check если скорость критична:
   ```bash
   python3 main.py "тема" --fact-check-mode off
   ```
2. Или используйте fallback без веб-поиска (DeepSeek)

---

## ⚠️ Известные ограничения

### 1. Firecrawl Search Limit

**Ограничение**: Максимум 20 результатов поиска.

**Обход**: Система автоматически выбирает топ-5 лучших.

### 2. Gemini Rate Limits

**Ограничение**: 60 запросов в минуту (free tier).

**Обход**: Fact-check разбит на группы с задержками 3 секунды.

### 3. DeepSeek FREE Limits

**Ограничение**: Общая квота на всех пользователей.

**Обход**: Автоматический fallback на Gemini при лимитах.

### 4. Token Context Limits

**Ограничение**:
- DeepSeek: 64K context
- Gemini: 32K context (в некоторых версиях)

**Обход**: Система разбивает на секции если контент превышает лимит.

### 5. WordPress REST API

**Ограничение**: Некоторые хостинги блокируют REST API.

**Обход**:
1. Убедитесь что REST API включен
2. Добавьте в `.htaccess`:
   ```apache
   # Allow REST API
   <IfModule mod_rewrite.c>
   RewriteRule ^wp-json/ - [L]
   </IfModule>
   ```

### 6. Batch Processing Memory

**Ограничение**: Python может занимать >2GB при длительной обработке.

**Обход**: Система автоматически очищает память между темами.

---

## 🛠️ Диагностика шаг за шагом

### Если что-то пошло не так:

#### Шаг 1: Проверьте verbose логи

```bash
python3 main.py "тема" --verbose
```

Ищите WARNING и ERROR сообщения.

#### Шаг 2: Проверьте сырые LLM ответы

```bash
cat output/{topic}/{stage}/llm_responses_raw/response_*.txt
```

Читайте что ТОЧНО вернула модель.

#### Шаг 3: Проверьте промпты

```bash
cat prompts/{content_type}/{stage}.txt
```

Убедитесь что промпт корректный.

#### Шаг 4: Проверьте API ключи

```bash
cat .env | grep API_KEY
```

Убедитесь что все ключи установлены.

#### Шаг 5: Проверьте конфигурацию

```bash
cat src/config.py | grep LLM_MODELS
```

Убедитесь что модели настроены правильно.

---

## 📞 Получить помощь

Если проблема не решена:

1. **Проверьте документацию**:
   - [GUIDE.md](GUIDE.md) - руководство пользователя
   - [TECHNICAL.md](TECHNICAL.md) - техническая документация

2. **Проверьте changelog**:
   - [../CHANGELOG.md](../CHANGELOG.md) - возможно проблема уже исправлена

3. **Соберите диагностическую информацию**:
   - Verbose логи
   - Сырые LLM ответы
   - Версия проекта
   - Команда которую запускали

---

**Версия**: 2.3.0 | **Статус**: ✅ Production Ready
