#!/usr/bin/env python3
"""
Тест фактчекинга статьи о Claude Code CLI через Gemini 2.5
"""

import os
import openai
from dotenv import load_dotenv

load_dotenv()

def load_article():
    """Загрузка статьи для проверки"""
    article_path = "/Users/skynet/Desktop/AI DEV/Content-factory/output/claude_code_cli_step_by_step_guide_for_beginners/10_link_processing/article_with_links.html"
    with open(article_path, 'r', encoding='utf-8') as f:
        return f.read()

def fact_check_with_gemini(article_text):
    """Отправка статьи на фактчекинг через Gemini 2.5"""

    # Настройка клиента OpenRouter
    client = openai.OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )

    prompt = """
    Проанализируй эту статью о Claude Code CLI на предмет фактической точности.

    ПРОВЕРЬ И ИСПРАВЬ:
    1. Команды установки (npm пакеты)
    2. Названия API endpoints
    3. Конфигурационные файлы
    4. Примеры кода и команд
    5. Технические спецификации

    УКАЖИ ЧТО ИМЕННО ИСПРАВИЛ в начале ответа в формате:
    ИСПРАВЛЕНИЯ:
    - [что было] → [что стало]

    Затем выведи исправленную версию статьи в том же HTML формате.

    СТАТЬЯ ДЛЯ ПРОВЕРКИ:
    """

    try:
        response = client.chat.completions.create(
            model="google/gemini-2.5-flash-lite-preview-06-17",
            messages=[
                {"role": "user", "content": prompt + article_text}
            ],
            max_tokens=8000,
            temperature=0.1
        )

        return response.choices[0].message.content

    except Exception as e:
        print(f"Ошибка при запросе к Gemini: {e}")
        return None

def main():
    print("🔍 Загружаю статью для фактчекинга...")
    article = load_article()
    print(f"✅ Статья загружена: {len(article)} символов")

    print("\n🤖 Отправляю на проверку фактов в Gemini 2.5...")
    result = fact_check_with_gemini(article)

    if result:
        print("\n📝 Результат фактчекинга:")
        print("=" * 50)
        print(result)

        # Сохранение результата
        with open("/Users/skynet/Desktop/AI DEV/Content-factory/factcheck_result.txt", 'w', encoding='utf-8') as f:
            f.write(result)
        print("\n💾 Результат сохранен в factcheck_result.txt")
    else:
        print("❌ Ошибка при фактчекинге")

if __name__ == "__main__":
    main()