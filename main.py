import time
import sys
import os
import json
import re
import argparse
from src.logger_config import logger, configure_logging
from src.firecrawl_client import FirecrawlClient
from src.processing import (
    filter_urls,
    validate_and_prepare_sources,
    score_sources,
    select_best_sources,
    clean_content,
)
from src.llm_processing import (
    extract_prompts_from_article,
    generate_article_by_sections,  # NEW: for section-by-section generation
    fact_check_sections,  # NEW: for fact-checking individual sections
    editorial_review,
    _load_and_prepare_messages,
    _make_llm_request_with_retry,
    save_llm_interaction,
    _parse_json_from_response
)
from src.wordpress_publisher import WordPressPublisher
from src.token_tracker import TokenTracker
from src.config import LLM_MODELS, FALLBACK_MODELS
from batch_config import CONTENT_TYPES, get_content_type_config
from typing import Dict

def sanitize_filename(topic):
    """Sanitizes the topic to be used as a valid directory name."""
    return re.sub(r'[\\/*?:"<>|]', "_", topic).replace(" ", "_")

def save_artifact(data, path, filename):
    """Saves data to a file (JSON or text)."""
    os.makedirs(path, exist_ok=True)
    filepath = os.path.join(path, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        if isinstance(data, str):
            f.write(data)
        else:
            json.dump(data, f, indent=4, ensure_ascii=False)
    logger.info(f"Saved artifact to {filepath}")

def fix_content_newlines(content: str) -> str:
    """
    Исправляет экранированные переносы строк в code блоках.
    Преобразует литеральные \\n в настоящие переносы ТОЛЬКО внутри <pre><code> тегов.
    """
    if not content:
        return content

    # Функция для исправления блоков кода
    def fix_code_block(match):
        pre_tag = match.group(1)  # <pre> с возможными атрибутами
        code_opening = match.group(2)  # <code> с возможными атрибутами
        code_content = match.group(3)  # Содержимое блока кода
        code_closing = match.group(4)  # </code>
        pre_closing = match.group(5)  # </pre>

        # Заменяем литеральные \n на настоящие переносы строк
        fixed_content = code_content.replace('\\n', '\n')

        # Логирование для отладки
        if '\\n' in code_content:
            logger.debug(f"Fixed code block: replaced {code_content.count('\\n')} \\n occurrences")

        return f"{pre_tag}{code_opening}{fixed_content}{code_closing}{pre_closing}"

    # Регулярное выражение для поиска блоков <pre><code>...</code></pre>
    import re
    pattern = r'(<pre[^>]*>)(<code[^>]*>)(.*?)(</code>)(</pre>)'

    # Заменяем все блоки кода
    fixed_content = re.sub(pattern, fix_code_block, content, flags=re.DOTALL)

    return fixed_content


def save_html_with_proper_newlines(content: str, path: str, filename: str):
    """
    Сохраняет HTML контент с правильными переносами строк в code блоках.
    Использует общую функцию fix_content_newlines() для исправления переносов.
    """
    os.makedirs(path, exist_ok=True)
    filepath = os.path.join(path, filename)

    # Исправляем переносы строк
    fixed_content = fix_content_newlines(content)

    # Сохраняем результат
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(fixed_content)

    logger.info(f"Saved HTML with proper newlines to {filepath}")

async def basic_articles_pipeline(topic: str, publish_to_wordpress: bool = True, content_type: str = "basic_articles",
                                  verbose: bool = False, variables_manager=None):
    """
    Simplified pipeline for generating basic articles with FAQ and sources.
    Improved pipeline with configurable content type for different prompt sets.
    Этапы: 1-6 поиск/очистка → 7 структуры → 8 ультимативная → 9 генерация → 9.5 факт-чек → 10 редактура → 11 публикация

    Args:
        topic: Topic for content generation
        publish_to_wordpress: Whether to publish to WordPress
        content_type: Type of content to generate
        verbose: Enable verbose logging
        variables_manager: Optional VariablesManager instance with variables
    """
    logger.info(f"--- Starting Basic Articles Pipeline for topic: '{topic}' ---")

    # Log active variables if any
    if variables_manager:
        active_vars = variables_manager.get_active_variables_summary()
        if active_vars['active_count'] > 0:
            logger.info(f"Active variables: {active_vars['variables']}")

    # Initialize token tracker
    token_tracker = TokenTracker(topic=topic)

    # Use default models from config
    active_models = LLM_MODELS

    # --- Setup Directories ---
    sanitized_topic = sanitize_filename(topic)
    base_output_path = os.path.join("output", sanitized_topic)
    paths = {
        "search": os.path.join(base_output_path, "01_search"),
        "parsing": os.path.join(base_output_path, "02_parsing"),
        "scoring": os.path.join(base_output_path, "03_scoring"),
        "selection": os.path.join(base_output_path, "04_selection"),
        "cleaning": os.path.join(base_output_path, "05_cleaning"),
        "structure_extraction": os.path.join(base_output_path, "06_structure_extraction"),
        "ultimate_structure": os.path.join(base_output_path, "07_ultimate_structure"),
        "final_article": os.path.join(base_output_path, "08_article_generation"),
        "fact_check": os.path.join(base_output_path, "09_fact_check"),
        "editorial_review": os.path.join(base_output_path, "10_editorial_review"),
    }
    for path in paths.values():
        os.makedirs(path, exist_ok=True)

    # --- Этапы 1-6: Поиск, парсинг, очистка ---
    firecrawl_client = FirecrawlClient()

    search_results = await firecrawl_client.search(topic)
    save_artifact(search_results, paths["search"], "01_search_results.json")

    urls = [result['url'] for result in search_results if 'url' in result]
    if not urls:
        logger.error("No URLs found in search results. Exiting.")
        return
    save_artifact(urls, paths["search"], "02_extracted_urls.json")

    clean_urls = filter_urls(urls)
    save_artifact(clean_urls, paths["parsing"], "01_clean_urls.json")

    if not clean_urls:
        logger.error("No clean URLs left after filtering. Exiting.")
        return

    scraped_data = await firecrawl_client.scrape_urls(clean_urls)
    save_artifact(scraped_data, paths["parsing"], "02_scraped_data.json")

    valid_sources = validate_and_prepare_sources(scraped_data)
    save_artifact(valid_sources, paths["parsing"], "03_valid_sources.json")

    if not valid_sources:
        logger.error("No valid sources found after scraping and validation. Exiting.")
        return

    scored_sources = score_sources(valid_sources, topic)
    save_artifact(scored_sources, paths["scoring"], "scored_sources.json")

    top_sources = select_best_sources(scored_sources)
    save_artifact(top_sources, paths["selection"], "top_5_sources.json")

    if not top_sources:
        logger.error("Could not select any top sources. Exiting.")
        return

    cleaned_sources = clean_content(top_sources)
    save_artifact(cleaned_sources, paths["cleaning"], "final_cleaned_sources.json")

    # --- Этап 7: Извлечение структур (ПАРАЛЛЕЛЬНО) ---
    logger.info(f"Starting PARALLEL structure extraction from {len(cleaned_sources)} sources...")

    def extract_all_structures():
        """Extract structures from all sources sequentially"""
        results = []

        # Process sources sequentially with delays
        for i, source in enumerate(cleaned_sources):
            source_id = f"source_{i+1}"
            logger.info(f"🚀 Starting structure extraction for {source_id}")

            # Add delay between requests (except for first)
            if i > 0:
                delay = 5  # 5 seconds between requests
                logger.info(f"⏳ {source_id} waiting {delay}s before HTTP request...")
                time.sleep(delay)
                logger.info(f"✅ {source_id} finished waiting, starting HTTP request...")

            try:
                result = extract_prompts_from_article(
                    article_text=source['cleaned_content'],
                    topic=topic,
                    base_path=paths["structure_extraction"],
                    source_id=source_id,
                    token_tracker=token_tracker,
                    model_name=active_models.get("extract_prompts"),
                    content_type=content_type,
                    variables_manager=variables_manager
                )
                results.append(result)
            except Exception as e:
                results.append(e)

        # Process results
        all_structures = []
        extraction_stats = []

        for i, result in enumerate(results):
            source_id = f"source_{i+1}"
            source = cleaned_sources[i]

            if isinstance(result, Exception):
                logger.error(f"❌ {source_id} failed with exception: {result}")
                extraction_stats.append({
                    "source_id": source_id,
                    "url": source.get('url', 'Unknown'),
                    "structures_extracted": 0,
                    "error": str(result)
                })
            else:
                structures = result
                extraction_stats.append({
                    "source_id": source_id,
                    "url": source.get('url', 'Unknown'),
                    "structures_extracted": len(structures)
                })

                if len(structures) == 0:
                    logger.warning(f"⚠️  {source_id} extracted 0 structures - possible JSON parsing issue")
                else:
                    logger.info(f"✅ {source_id} extracted {len(structures)} structures")

                all_structures.extend(structures)

        return all_structures, extraction_stats

    # Run the sync extraction
    all_structures, extraction_stats = extract_all_structures()

    save_artifact(all_structures, paths["structure_extraction"], "all_structures.json")

    if not all_structures:
        logger.error("No structures could be extracted from the sources. Exiting.")
        return

    # --- Этап 8: Создание ультимативной структуры ---
    logger.info("Creating ultimate structure from extracted structures...")

    messages = _load_and_prepare_messages(
        content_type,
        "02_create_ultimate_structure",
        {"topic": topic, "article_text": json.dumps(all_structures, indent=2)},
        variables_manager=variables_manager,
        stage_name="create_structure"
    )

    # Try with primary model first, then fallback if JSON parsing fails
    ultimate_structure = None
    models_to_try = [
        active_models.get("create_structure"),
        FALLBACK_MODELS.get("create_structure")  # google/gemini-2.5-flash-lite-preview-06-17
    ]

    for model_idx, current_model in enumerate(models_to_try):
        if not current_model or (model_idx > 0 and current_model == models_to_try[0]):
            continue  # Skip if no fallback or same as primary

        model_label = "primary" if model_idx == 0 else "fallback"

        for attempt in range(1, 4):  # 3 attempts per model
            try:
                logger.info(f"🔄 Create structure attempt {attempt}/3 with {model_label} model: {current_model}")

                response_obj, actual_model = _make_llm_request_with_retry(
                    stage_name="create_structure",
                    model_name=current_model,
                    messages=messages,
                    token_tracker=token_tracker,
                    base_path=paths["ultimate_structure"],
                    temperature=0.3
                )

                content = response_obj.choices[0].message.content
                save_llm_interaction(
                    base_path=paths["ultimate_structure"],
                    stage_name="create_structure",
                    messages=messages,
                    response=content,
                    request_id=f"ultimate_structure_{model_label}_attempt{attempt}"
                )

                ultimate_structure = _parse_json_from_response(content)

                if ultimate_structure and ultimate_structure != []:
                    logger.info(f"✅ Successfully parsed structure with {current_model} on attempt {attempt}")
                    save_artifact(ultimate_structure, paths["ultimate_structure"], "ultimate_structure.json")
                    break
                else:
                    logger.warning(f"❌ Invalid JSON from {current_model} on attempt {attempt}")
                    if attempt < 3:
                        time.sleep(2)  # Small delay before retry
                    elif model_idx == 0 and models_to_try[1]:
                        logger.warning(f"🔄 Primary model failed, switching to fallback model...")

            except Exception as e:
                logger.error(f"Error with {current_model} on attempt {attempt}: {e}")
                if attempt < 3:
                    time.sleep(2)

        if ultimate_structure:
            break

    if not ultimate_structure or ultimate_structure == []:
        logger.error("Failed to create valid structure with all models and attempts. Exiting.")
        return

    # --- Этап 9: Генерация WordPress статьи по секциям ---
    logger.info("Generating WordPress-ready article from ultimate structure (section by section)...")

    # NEW: Use section-by-section generation
    wordpress_data = generate_article_by_sections(
        structure=ultimate_structure,
        topic=topic,
        base_path=paths["final_article"],
        token_tracker=token_tracker,
        model_name=active_models.get("generate_article"),
        content_type=content_type,
        variables_manager=variables_manager
    )

    save_artifact(wordpress_data, paths["final_article"], "wordpress_data.json")

    if isinstance(wordpress_data, dict) and "raw_response" in wordpress_data:
        logger.info(f"Generated article data ready for fact-checking")
    else:
        logger.error("Invalid WordPress data structure returned")
        return

    # --- Этап 9.5: Fact-checking секций ---
    logger.info("Starting grouped fact-checking of generated sections...")

    generated_sections = wordpress_data.get("generated_sections", [])
    if not generated_sections:
        logger.error("No generated sections found for fact-checking. Exiting.")
        return

    # Get combined fact-checked content and status
    fact_checked_content, fact_check_status = fact_check_sections(
        sections=generated_sections,
        topic=topic,
        base_path=paths["fact_check"],
        token_tracker=token_tracker,
        model_name=active_models.get("fact_check"),
        content_type=content_type,
        variables_manager=variables_manager
    )

    # Save the combined fact-checked content
    save_artifact({"content": fact_checked_content}, paths["fact_check"], "fact_checked_content.json")

    # Save fact-check status for reference
    save_artifact(fact_check_status, paths["fact_check"], "fact_check_status.json")

    # Check for fact-check failures and show warning
    fact_check_failed = not fact_check_status.get("success", True)
    if fact_check_failed:
        failed_groups = fact_check_status.get("failed_groups", 0)
        total_groups = fact_check_status.get("total_groups", 0)
        failed_sections = fact_check_status.get("failed_sections", [])

        # Display bright warning
        border = "🔥" * 60
        logger.warning(f"\n{border}")
        logger.warning(f"⚠️  CRITICAL: FACT-CHECK FAILED")
        logger.warning(f"Failed groups: {failed_groups}/{total_groups}")
        if failed_sections:
            logger.warning(f"Failed sections: {', '.join(failed_sections[:5])}")  # Show first 5 sections
            if len(failed_sections) > 5:
                logger.warning(f"... and {len(failed_sections) - 5} more sections")
        logger.warning(f"Article contains UNVERIFIED CONTENT - Manual review required!")
        logger.warning(f"{border}\n")
    else:
        logger.info(f"✅ Fact-checking passed: All {fact_check_status.get('total_groups', 0)} groups verified")

    # Create merged content structure for compatibility with editorial review
    merged_content = {
        "title": f"Статья по теме: {topic}",
        "content": fact_checked_content,
        "excerpt": f"Автоматически сгенерированная статья на тему: {topic}",
        "slug": topic.lower().replace(" ", "-")
    }
    save_artifact(merged_content, paths["fact_check"], "merged_fact_checked_content.json")

    # Update wordpress_data with fact-checked content
    wordpress_data["raw_response"] = json.dumps(merged_content, ensure_ascii=False)

    logger.info(f"Fact-checking completed: Combined content length: {len(fact_checked_content)} characters")

    # --- Этап 10: Editorial Review ---
    logger.info("Starting editorial review and cleanup...")
    raw_response = wordpress_data.get("raw_response", "")
    wordpress_data_final = editorial_review(
        raw_response=raw_response,
        topic=topic,
        base_path=paths["editorial_review"],
        token_tracker=token_tracker,
        model_name=active_models.get("editorial_review"),
        content_type=content_type,
        variables_manager=variables_manager
    )

    # Исправить переносы строк в контенте перед сохранением JSON
    if isinstance(wordpress_data_final, dict) and "content" in wordpress_data_final:
        wordpress_data_final["content"] = fix_content_newlines(wordpress_data_final["content"])
        logger.info("Fixed newlines in wordpress_data_final content for JSON compatibility")

    save_artifact(wordpress_data_final, paths["editorial_review"], "wordpress_data_final.json")

    if isinstance(wordpress_data_final, dict) and "content" in wordpress_data_final:
        save_html_with_proper_newlines(wordpress_data_final["content"], paths["editorial_review"], "article_content_final.html")
        logger.info(f"Editorial review completed: {wordpress_data_final.get('title', 'No title')}")
    else:
        logger.warning("Editorial review returned invalid structure, using original data")
        wordpress_data_final = wordpress_data

    # --- Этап 11 (опциональный): WordPress Publication ---
    if publish_to_wordpress:
        logger.info("Starting WordPress publication...")
        try:
            wp_publisher = WordPressPublisher()

            publication_result = wp_publisher.publish_article(wordpress_data_final)

            if publication_result["success"]:
                logger.info(f"✅ Article published successfully: {publication_result['url']}")
                save_artifact(publication_result, paths["editorial_review"], "wordpress_publication_result.json")
            else:
                logger.error(f"❌ WordPress publication failed: {publication_result.get('error', 'Unknown error')}")

        except Exception as e:
            logger.error(f"WordPress publication failed: {e}")
            save_artifact({
                "success": False,
                "error": str(e),
                "url": None
            }, paths["editorial_review"], "wordpress_publication_result.json")

    # --- Final Summary ---
    logger.info("=== PIPELINE COMPLETED ===")
    logger.info(f"Topic: {topic}")
    logger.info(f"Final article title: {wordpress_data_final.get('title', 'No title')}")

    # Show fact-check warning in final summary if needed
    if fact_check_failed:
        border = "🔥" * 60
        logger.warning(f"\n{border}")
        logger.warning(f"⚠️  FINAL WARNING: Article contains UNVERIFIED CONTENT")
        logger.warning(f"Fact-check failed for {fact_check_status.get('failed_groups', 0)} groups")
        logger.warning(f"Manual fact verification recommended before publication")
        logger.warning(f"{border}\n")

    # Token usage report
    token_summary = token_tracker.get_session_summary()
    logger.info(f"Total tokens used: {token_summary['session_summary']['total_tokens']}")
    token_report_path = os.path.join(base_output_path, "token_usage_report.json")
    token_tracker.save_token_report(base_output_path)
    logger.info(f"Token usage report: {token_report_path}")

async def run_single_stage(topic: str, stage: str, content_type: str = "basic_articles", publish_to_wordpress: bool = True, verbose: bool = False):
    """
    Запускает pipeline с конкретного этапа, используя существующие данные.

    Args:
        topic: Тема статьи (используется для поиска существующей папки output)
        stage: Этап для запуска ('fact_check', 'editorial_review', 'publication')
        content_type: Тип контента
        publish_to_wordpress: Публиковать ли в WordPress
        verbose: Включить детальное логирование
    """
    from src.llm_processing import editorial_review
    from src.config import LLM_MODELS
    from src.token_tracker import TokenTracker

    # Найти существующую папку output
    sanitized_topic = sanitize_filename(topic)
    base_output_path = f"output/_{sanitized_topic}_"

    if not os.path.exists(base_output_path):
        logger.error(f"Output folder not found: {base_output_path}")
        logger.error("Run full pipeline first to create the necessary data files")
        return

    logger.info(f"Using existing output folder: {base_output_path}")

    # Инициализация
    token_tracker = TokenTracker()
    active_models = LLM_MODELS

    # Создание путей к этапам
    paths = {
        "final_article": os.path.join(base_output_path, "08_article_generation"),
        "fact_check": os.path.join(base_output_path, "09_fact_check"),
        "editorial_review": os.path.join(base_output_path, "10_editorial_review")
    }

    # Initialize variables_manager for all stages
    from src.variables_manager import VariablesManager
    variables_manager = VariablesManager()

    if stage == "fact_check":
        logger.info("=== Starting Fact-Check Stage ===")

        # Load wordpress_data.json from 08_final_article
        wordpress_data_path = os.path.join(paths["final_article"], "wordpress_data.json")
        if not os.path.exists(wordpress_data_path):
            logger.error(f"Required file not found: {wordpress_data_path}")
            logger.error("Run full pipeline first to generate article sections")
            return

        with open(wordpress_data_path, 'r', encoding='utf-8') as f:
            wordpress_data = json.load(f)

        generated_sections = wordpress_data.get("generated_sections", [])
        if not generated_sections:
            logger.error("No generated sections found in wordpress_data.json")
            return

        logger.info(f"Found {len(generated_sections)} sections for fact-checking")

        # Run fact-checking
        from src.llm_processing import fact_check_sections

        fact_checked_content, fact_check_status = fact_check_sections(
            sections=generated_sections,
            topic=topic,
            base_path=paths["fact_check"],
            token_tracker=token_tracker,
            model_name=active_models.get("fact_check"),
            content_type=content_type,
            variables_manager=variables_manager
        )

        # Save results
        save_artifact({"content": fact_checked_content},
                     paths["fact_check"],
                     "fact_checked_content.json")
        save_artifact(fact_check_status,
                     paths["fact_check"],
                     "fact_check_status.json")

        # Create merged_fact_checked_content.json for editorial_review
        merged_content = {
            "title": wordpress_data.get("title", ""),
            "content": fact_checked_content,
            "excerpt": wordpress_data.get("excerpt", ""),
            "seo_title": wordpress_data.get("seo_title", ""),
            "meta_description": wordpress_data.get("meta_description", ""),
            "sources": wordpress_data.get("sources", []),
            "faq": wordpress_data.get("faq", [])
        }

        save_artifact(merged_content,
                     paths["fact_check"],
                     "merged_fact_checked_content.json")

        logger.info(f"✅ Fact-check stage completed successfully")

        # Show token statistics
        token_summary = token_tracker.get_session_summary()
        logger.info(f"Tokens used in this stage: {token_summary['session_summary']['total_tokens']}")

    elif stage == "editorial_review":
        logger.info("=== Starting Editorial Review Stage ===")

        # Загрузить данные после fact-check
        merged_content_path = os.path.join(paths["fact_check"], "merged_fact_checked_content.json")
        if not os.path.exists(merged_content_path):
            logger.error(f"Required file not found: {merged_content_path}")
            return

        with open(merged_content_path, 'r', encoding='utf-8') as f:
            merged_content = json.load(f)

        # Подготовить данные в формате, ожидаемом editorial_review
        raw_response = json.dumps(merged_content, ensure_ascii=False)

        # Запустить Editorial Review
        wordpress_data_final = editorial_review(
            raw_response=raw_response,
            topic=topic,
            base_path=paths["editorial_review"],
            token_tracker=token_tracker,
            model_name=active_models.get("editorial_review"),
            content_type=content_type,
            variables_manager=variables_manager
        )

        # Исправить переносы строк в контенте перед сохранением JSON
        if isinstance(wordpress_data_final, dict) and "content" in wordpress_data_final:
            wordpress_data_final["content"] = fix_content_newlines(wordpress_data_final["content"])
            logger.info("Fixed newlines in wordpress_data_final content for JSON compatibility")

        save_artifact(wordpress_data_final, paths["editorial_review"], "wordpress_data_final.json")

        if isinstance(wordpress_data_final, dict) and "content" in wordpress_data_final:
            save_html_with_proper_newlines(wordpress_data_final["content"], paths["editorial_review"], "article_content_final.html")
            logger.info(f"✅ Editorial review completed: {wordpress_data_final.get('title', 'No title')}")
        else:
            logger.warning("Editorial review returned invalid structure")
            return

        logger.info(f"Editorial Review stage completed successfully")

        # Показать статистику токенов
        token_summary = token_tracker.get_session_summary()
        logger.info(f"Tokens used in this stage: {token_summary['session_summary']['total_tokens']}")

    elif stage == "publication":
        logger.info("=== Starting WordPress Publication Stage ===")

        # Загрузить готовый wordpress_data_final.json
        wordpress_data_path = os.path.join(paths["editorial_review"], "wordpress_data_final.json")
        if not os.path.exists(wordpress_data_path):
            logger.error(f"Required file not found: {wordpress_data_path}")
            logger.error("Run editorial_review stage first to create wordpress_data_final.json")
            return

        with open(wordpress_data_path, 'r', encoding='utf-8') as f:
            wordpress_data_final = json.load(f)

        logger.info(f"Loaded WordPress data: {wordpress_data_final.get('title', 'No title')}")

        # Применить исправления переносов строк (на всякий случай)
        if isinstance(wordpress_data_final, dict) and "content" in wordpress_data_final:
            wordpress_data_final["content"] = fix_content_newlines(wordpress_data_final["content"])
            logger.info("Applied newline fixes to content")

        if publish_to_wordpress:
            logger.info("Starting WordPress publication...")
            try:
                from src.wordpress_publisher import WordPressPublisher
                wp_publisher = WordPressPublisher()

                publication_result = wp_publisher.publish_article(wordpress_data_final)

                if publication_result["success"]:
                    logger.info(f"✅ Article published successfully: {publication_result['url']}")
                    save_artifact(publication_result, paths["editorial_review"], "wordpress_publication_result.json")
                else:
                    logger.error(f"❌ Publication failed: {publication_result['error']}")
                    save_artifact(publication_result, paths["editorial_review"], "wordpress_publication_error.json")

            except Exception as e:
                logger.error(f"❌ WordPress publication error: {e}")
                return
        else:
            logger.info("WordPress publication skipped (--skip-publication)")

        logger.info(f"Publication stage completed successfully")

    else:
        logger.error(f"Stage '{stage}' not implemented yet")
        logger.info("Available stages: fact_check, editorial_review, publication")

async def main_flow(topic: str, model_overrides: Dict = None, publish_to_wordpress: bool = True, content_type: str = "basic_articles", verbose: bool = False, variables_manager=None):
    """Async wrapper function for batch processor compatibility"""
    return await basic_articles_pipeline(topic, publish_to_wordpress, content_type, verbose, variables_manager)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Content Factory Pipeline')
    parser.add_argument('topic', help='Topic for content generation')
    parser.add_argument('--content-type', choices=list(CONTENT_TYPES.keys()),
                       default='basic_articles', help='Type of content to generate')
    parser.add_argument('--skip-publication', action='store_true',
                       help='Skip WordPress publication')
    parser.add_argument('--start-from-stage', choices=['fact_check', 'editorial_review', 'publication'],
                       help='Start pipeline from specific stage (requires existing output folder)')
    parser.add_argument('--verbose', action='store_true',
                       help='Show detailed debug logs (default: show only key events)')

    # Variable arguments
    parser.add_argument('--article-length', type=int,
                       help='Target article length in characters')
    parser.add_argument('--author-style',
                       help='Author style for writing (e.g., "academic", "conversational", "technical")')
    parser.add_argument('--theme-focus',
                       help='Theme focus for the content (e.g., "business", "technology", "education")')
    parser.add_argument('--custom-requirements',
                       help='Additional requirements for content generation')
    parser.add_argument('--target-audience',
                       help='Target audience for the article (e.g., "beginners", "professionals", "students")')
    parser.add_argument('--tone-of-voice',
                       help='Tone of voice (e.g., "formal", "friendly", "authoritative")')
    parser.add_argument('--include-examples', action='store_true',
                       help='Include practical examples in each section')
    parser.add_argument('--seo-keywords',
                       help='SEO keywords to naturally include (comma-separated)')

    args = parser.parse_args()

    # Configure logging FIRST before any other operations
    configure_logging(verbose=args.verbose)

    # Re-import logger after configuration to get updated settings
    from src.logger_config import logger

    # Validate content type
    try:
        content_config = get_content_type_config(args.content_type)
        logger.info(f"Using content type: {args.content_type} - {content_config['description']}")
    except ValueError as e:
        logger.error(f"Invalid content type: {e}")
        sys.exit(1)

    publish_to_wordpress = not args.skip_publication

    import asyncio

    # Create variables manager from CLI arguments
    from src.variables_manager import VariablesManager
    variables_manager = VariablesManager.create_from_args(vars(args))

    if variables_manager.get_active_variables_summary()["active_count"] > 0:
        logger.info(f"Variables manager initialized with {variables_manager.get_active_variables_summary()['active_count']} variable(s)")
        for var_name, var_value in variables_manager.get_active_variables_summary()["variables"].items():
            logger.info(f"  - {var_name}: {var_value}")

    # Проверить флаг --start-from-stage
    if args.start_from_stage:
        logger.info(f"Starting from stage: {args.start_from_stage}")
        logger.info(f"Topic: {args.topic}")
        logger.info(f"Content type: {args.content_type}")

        try:
            asyncio.run(run_single_stage(args.topic, args.start_from_stage, args.content_type, publish_to_wordpress, args.verbose))
            logger.info(f"✅ Stage '{args.start_from_stage}' completed successfully")
        except KeyboardInterrupt:
            logger.info("\\n🛑 Stage interrupted by user")
            sys.exit(130)
        except Exception as e:
            logger.error(f"💥 Stage '{args.start_from_stage}' failed: {e}")
            sys.exit(1)
    else:
        logger.info(f"Starting full pipeline for topic: {args.topic}")
        logger.info(f"Content type: {args.content_type}")
        logger.info(f"WordPress publication: {'enabled' if publish_to_wordpress else 'disabled'}")

        try:
            asyncio.run(basic_articles_pipeline(args.topic, publish_to_wordpress, args.content_type, args.verbose, variables_manager))
            logger.info("✅ Pipeline completed successfully")
        except KeyboardInterrupt:
            logger.info("\\n🛑 Pipeline interrupted by user")
            sys.exit(130)
        except Exception as e:
            logger.error(f"💥 Pipeline failed: {e}")
            sys.exit(1)