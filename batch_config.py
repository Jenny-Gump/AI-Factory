"""
Batch Processor Configuration
Настройки для последовательной обработки списка тем
"""

import os

# Основные настройки батч-процессора
BATCH_CONFIG = {
    # Таймауты
    "max_topic_timeout": 1800,  # 30 минут на одну тему максимум
    "wordpress_verification_timeout": 120,  # 2 минуты ожидания публикации
    "memory_check_interval": 300,  # Проверка памяти каждые 5 минут
    
    # Лимиты ресурсов
    "max_memory_mb": 2048,  # Максимальное использование памяти
    "max_concurrent_requests": 5,  # Максимум одновременных HTTP запросов
    
    # Retry политика
    "retry_failed_topics": 2,  # Количество повторов для неудачных тем
    "retry_delay_seconds": 60,  # Задержка между повторами
    
    # Безопасность и надежность
    "autosave_interval": 300,  # Автосохранение каждые 5 минут
    "enable_memory_monitoring": True,  # Мониторинг памяти
    "graceful_shutdown_timeout": 30,  # Время на graceful shutdown
    
    # Логирование
    "detailed_progress_logging": True,  # Детальное логирование прогресса
    "save_failed_topics_log": True,  # Сохранять лог неудачных тем
    
    # WordPress проверки
    "verify_publication_before_next": True,  # Обязательная проверка публикации
    "wordpress_api_timeout": 30,  # Таймаут для WordPress API
}

# Типы контента с их настройками
CONTENT_TYPES = {
    "prompt_collection": {
        "prompts_folder": "prompts/prompt_collection",
        "description": "Articles about AI prompts and prompt engineering",
        "default_topics_file": "topics_prompts.txt",
        "output_prefix": "prompts_",
        "wordpress_category": "prompts"
    },
    "business_ideas": {
        "prompts_folder": "prompts/business_ideas",
        "description": "Business ideas and entrepreneurship content",
        "default_topics_file": "topics_business_ideas.txt", 
        "output_prefix": "business_",
        "wordpress_category": "business"
    },
    "marketing_content": {
        "prompts_folder": "prompts/marketing_content",
        "description": "Marketing and advertising content",
        "default_topics_file": "topics_marketing.txt",
        "output_prefix": "marketing_",
        "wordpress_category": "marketing"
    },
    "educational_content": {
        "prompts_folder": "prompts/educational_content",
        "description": "Educational and tutorial content",
        "default_topics_file": "topics_educational.txt",
        "output_prefix": "edu_",
        "wordpress_category": "education"
    },
    "basic_articles": {
        "prompts_folder": "prompts/basic_articles",
        "description": "Basic informational articles with FAQ and sources",
        "default_topics_file": "topics_basic_articles.txt",
        "output_prefix": "article_",
        "wordpress_category": "articles"
    }
}

# Пути файлов
BATCH_PATHS = {
    "progress_file_template": ".batch_progress_{content_type}.json",
    "failed_topics_log": "batch_failed_topics.log",
    "batch_statistics": "batch_stats.json",
    "lock_file_template": ".batch_lock_{content_type}.pid"
}

# Настройки очистки памяти
MEMORY_CLEANUP = {
    "force_gc_between_topics": True,  # Принудительный garbage collection
    "clear_llm_caches": True,  # Очистка кэшей LLM клиентов
    "reset_token_tracker": True,  # Сброс token tracker между темами
    "close_http_connections": True,  # Закрытие HTTP соединений
    "clear_firecrawl_cache": True,  # Очистка кэша Firecrawl
}

# Уведомления (для будущего расширения)
NOTIFICATIONS = {
    "enable_console_notifications": True,  # Уведомления в консоль
    "enable_email_notifications": False,  # Email уведомления (не реализовано)
    "enable_webhook_notifications": False,  # Webhook уведомления (не реализовано)
}

def get_content_type_config(content_type: str) -> dict:
    """Получить конфигурацию для определенного типа контента"""
    if content_type not in CONTENT_TYPES:
        raise ValueError(f"Unknown content type: {content_type}. Available: {list(CONTENT_TYPES.keys())}")
    
    return CONTENT_TYPES[content_type]

def get_progress_file_path(content_type: str) -> str:
    """Получить путь к файлу прогресса для типа контента"""
    return BATCH_PATHS["progress_file_template"].format(content_type=content_type)

def get_lock_file_path(content_type: str) -> str:
    """Получить путь к lock файлу для типа контента"""
    return BATCH_PATHS["lock_file_template"].format(content_type=content_type)

def validate_content_type(content_type: str) -> bool:
    """Проверить существует ли тип контента"""
    return content_type in CONTENT_TYPES

def ensure_prompts_folder_exists(content_type: str) -> None:
    """Убедиться что папка с промптами существует"""
    config = get_content_type_config(content_type)
    prompts_folder = config["prompts_folder"]
    
    if not os.path.exists(prompts_folder):
        os.makedirs(prompts_folder, exist_ok=True)
        
        # Создаем placeholder файлы для будущих промптов
        placeholder_extract = os.path.join(prompts_folder, "01_extract.txt")
        placeholder_generate = os.path.join(prompts_folder, "01_generate_wordpress_article.txt")
        
        if not os.path.exists(placeholder_extract):
            with open(placeholder_extract, 'w') as f:
                f.write(f"# Placeholder for {content_type} extraction prompts\n# TODO: Add specific prompts for this content type\n")
        
        if not os.path.exists(placeholder_generate):
            with open(placeholder_generate, 'w') as f:
                f.write(f"# Placeholder for {content_type} generation prompts\n# TODO: Add specific prompts for this content type\n")