#!/usr/bin/env python3
"""
Исправленный тест фактчекинга - выдает полностью исправленную статью
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
    """Фактчекинг и исправление статьи через Gemini 2.5"""

    client = openai.OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )

    prompt = """
Ты технический редактор. Исправь ВСЕ фактические ошибки в этой статье о Claude Code CLI.

ПРОБЛЕМЫ КОТОРЫЕ НУЖНО ИСПРАВИТЬ:
1. Неверная команда установки npm пакета
2. Несуществующие команды CLI
3. Неправильные пути к конфигурационным файлам
4. Выдуманные примеры использования

ЗАДАЧА:
- Найди все технические неточности
- Исправь команды установки и использования
- Исправь названия файлов и путей
- Убери несуществующие функции

ОТВЕТ:
Выведи ПОЛНОСТЬЮ исправленную статью в том же HTML формате. Сохрани структуру, стиль и объем, но исправь все фактические ошибки.

СТАТЬЯ:
"""

    try:
        response = client.chat.completions.create(
            model="google/gemini-2.5-flash-lite-preview-06-17",
            messages=[
                {"role": "user", "content": prompt + article_text}
            ],
            max_tokens=16000,  # Увеличил лимит
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

    print("\n🤖 Отправляю на исправление фактов в Gemini 2.5...")
    result = fact_check_with_gemini(article)

    if result:
        print("\n📝 Получена исправленная статья")
        print(f"Размер: {len(result)} символов")

        # Сохранение результата
        with open("/Users/skynet/Desktop/AI DEV/Content-factory/article_corrected.html", 'w', encoding='utf-8') as f:
            f.write(result)
        print("\n💾 Исправленная статья сохранена в article_corrected.html")

        # Показать первые 1000 символов
        print("\n📄 Начало исправленной статьи:")
        print("=" * 50)
        print(result[:1000] + "..." if len(result) > 1000 else result)
    else:
        print("❌ Ошибка при фактчекинге")

if __name__ == "__main__":
    main()