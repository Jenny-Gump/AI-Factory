import time
import sys
import os
import json
import re
import argparse
from src.logger_config import logger
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
from src.config import LLM_MODELS
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

def save_html_with_proper_newlines(content: str, path: str, filename: str):
    """
    Сохраняет HTML контент с правильными переносами строк в code блоках.
    Преобразует литеральные \n в настоящие переносы ТОЛЬКО внутри <pre><code> тегов.
    """
    os.makedirs(path, exist_ok=True)
    filepath = os.path.join(path, filename)

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

    # Сохраняем результат
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(fixed_content)

    logger.info(f"Saved HTML with proper newlines to {filepath}")

async def basic_articles_pipeline(topic: str, publish_to_wordpress: bool = True, content_type: str = "basic_articles"):
    """
    Simplified pipeline for generating basic articles with FAQ and sources.
    Improved pipeline with configurable content type for different prompt sets.
    Этапы: 1-6 поиск/очистка → 7 структуры → 8 ультимативная → 9 генерация → 9.5 факт-чек → 10 редактура → 11 ссылки → 12 публикация
    """
    logger.info(f"--- Starting Basic Articles Pipeline for topic: '{topic}' ---")

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
        "links": os.path.join(base_output_path, "11_link_processing"),
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
                    content_type=content_type
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
        {"topic": topic, "article_text": json.dumps(all_structures, indent=2)}
    )

    response_obj, actual_model = _make_llm_request_with_retry(
        stage_name="create_structure",
        model_name=active_models.get("create_structure"),
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
        request_id="ultimate_structure"
    )

    ultimate_structure = _parse_json_from_response(content)
    save_artifact(ultimate_structure, paths["ultimate_structure"], "ultimate_structure.json")

    if not ultimate_structure:
        logger.error("Could not create ultimate structure. Exiting.")
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
        content_type=content_type
    )

    save_artifact(wordpress_data, paths["final_article"], "wordpress_data.json")

    if isinstance(wordpress_data, dict) and "raw_response" in wordpress_data:
        logger.info(f"Generated article data ready for fact-checking")
    else:
        logger.error("Invalid WordPress data structure returned")
        return

    # --- Этап 9.5: Fact-checking секций ---
    logger.info("Starting fact-checking of generated sections...")

    generated_sections = wordpress_data.get("generated_sections", [])
    if not generated_sections:
        logger.error("No generated sections found for fact-checking. Exiting.")
        return

    fact_checked_sections = fact_check_sections(
        sections=generated_sections,
        topic=topic,
        base_path=paths["fact_check"],
        token_tracker=token_tracker,
        model_name=active_models.get("fact_check"),
        content_type=content_type
    )

    save_artifact(fact_checked_sections, paths["fact_check"], "fact_checked_sections.json")

    # Merge fact-checked sections
    from src.llm_processing import merge_sections
    merged_content = merge_sections(fact_checked_sections, topic, ultimate_structure)
    save_artifact(merged_content, paths["fact_check"], "merged_fact_checked_content.json")

    # Update wordpress_data with fact-checked content
    wordpress_data["raw_response"] = json.dumps(merged_content, ensure_ascii=False)

    logger.info(f"Fact-checking completed: {len([s for s in fact_checked_sections if s.get('status') == 'fact_checked'])} sections fact-checked")

    # --- Этап 10: Editorial Review ---
    logger.info("Starting editorial review and cleanup...")
    raw_response = wordpress_data.get("raw_response", "")
    wordpress_data_final = editorial_review(
        raw_response=raw_response,
        topic=topic,
        base_path=paths["editorial_review"],
        token_tracker=token_tracker,
        model_name=active_models.get("editorial_review"),
        content_type=content_type
    )

    save_artifact(wordpress_data_final, paths["editorial_review"], "wordpress_data_final.json")

    if isinstance(wordpress_data_final, dict) and "content" in wordpress_data_final:
        save_html_with_proper_newlines(wordpress_data_final["content"], paths["editorial_review"], "article_content_final.html")
        logger.info(f"Editorial review completed: {wordpress_data_final.get('title', 'No title')}")
    else:
        logger.warning("Editorial review returned invalid structure, using original data")
        wordpress_data_final = wordpress_data

    # --- Этап 11: Link Processing ---
    from src.config import LINK_PROCESSING_ENABLED
    if LINK_PROCESSING_ENABLED and isinstance(wordpress_data_final, dict) and "content" in wordpress_data_final:
        logger.info("=== Starting Link Processing Stage ===")
        try:
            from src.link_processor import LinkProcessor
            logger.info("Используем импортированный LinkProcessor...")
            logger.info("✅ LinkProcessor доступен")

            logger.info("Создаем экземпляр LinkProcessor...")
            link_processor = LinkProcessor()
            logger.info("✅ LinkProcessor создан успешно")

            logger.info("Запускаем process_links...")
            wordpress_data_with_links = link_processor.process_links(
                wordpress_data=wordpress_data_final,
                topic=topic,
                base_path=paths["links"],
                token_tracker=token_tracker,
                active_models=active_models,
                content_type=content_type
            )
            logger.info("✅ process_links завершен успешно")

            # Use processed data for WordPress publication
            wordpress_data_final = wordpress_data_with_links

            # Save updated content and wordpress_data_final
            if "content" in wordpress_data_final:
                save_artifact(wordpress_data_final["content"], paths["editorial_review"], "article_content_final_with_links.html")
                # CRITICAL: Save updated wordpress_data_final.json with links
                save_artifact(wordpress_data_final, paths["editorial_review"], "wordpress_data_final.json")
                logger.info("Link processing completed successfully")

        except Exception as e:
            logger.error(f"Link processing failed, continuing with original data: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            import traceback
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            # Continue with original wordpress_data_final
    else:
        if not LINK_PROCESSING_ENABLED:
            logger.info("Link processing disabled in config")
        else:
            logger.warning("Link processing skipped - no valid content in wordpress_data_final")

    # --- Этап 12 (опциональный): WordPress Publication ---
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

    # Token usage report
    token_summary = token_tracker.get_session_summary()
    logger.info(f"Total tokens used: {token_summary['session_summary']['total_tokens']}")
    token_report_path = os.path.join(base_output_path, "token_usage_report.json")
    token_tracker.save_token_report(base_output_path)
    logger.info(f"Token usage report: {token_report_path}")

async def run_single_stage(topic: str, stage: str, content_type: str = "basic_articles", publish_to_wordpress: bool = True):
    """
    Запускает pipeline с конкретного этапа, используя существующие данные.

    Args:
        topic: Тема статьи (используется для поиска существующей папки output)
        stage: Этап для запуска ('editorial_review', 'link_processing', 'publication')
        content_type: Тип контента
        publish_to_wordpress: Публиковать ли в WordPress
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
        "fact_check": os.path.join(base_output_path, "09_fact_check"),
        "editorial_review": os.path.join(base_output_path, "10_editorial_review"),
        "link_processing": os.path.join(base_output_path, "11_link_processing"),
        "publication": os.path.join(base_output_path, "12_publication")
    }

    if stage == "editorial_review":
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
            content_type=content_type
        )

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

    else:
        logger.error(f"Stage '{stage}' not implemented yet")
        logger.info("Available stages: editorial_review")

async def main_flow(topic: str, model_overrides: Dict = None, publish_to_wordpress: bool = True, content_type: str = "basic_articles"):
    """Async wrapper function for batch processor compatibility"""
    return await basic_articles_pipeline(topic, publish_to_wordpress, content_type)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Content Factory Pipeline')
    parser.add_argument('topic', help='Topic for content generation')
    parser.add_argument('--content-type', choices=list(CONTENT_TYPES.keys()),
                       default='basic_articles', help='Type of content to generate')
    parser.add_argument('--skip-publication', action='store_true',
                       help='Skip WordPress publication')
    parser.add_argument('--start-from-stage', choices=['editorial_review', 'link_processing', 'publication'],
                       help='Start pipeline from specific stage (requires existing output folder)')

    args = parser.parse_args()

    # Validate content type
    try:
        content_config = get_content_type_config(args.content_type)
        logger.info(f"Using content type: {args.content_type} - {content_config['description']}")
    except ValueError as e:
        logger.error(f"Invalid content type: {e}")
        sys.exit(1)

    publish_to_wordpress = not args.skip_publication

    import asyncio

    # Проверить флаг --start-from-stage
    if args.start_from_stage:
        logger.info(f"Starting from stage: {args.start_from_stage}")
        logger.info(f"Topic: {args.topic}")
        logger.info(f"Content type: {args.content_type}")

        try:
            asyncio.run(run_single_stage(args.topic, args.start_from_stage, args.content_type, publish_to_wordpress))
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
            asyncio.run(basic_articles_pipeline(args.topic, publish_to_wordpress, args.content_type))
            logger.info("✅ Pipeline completed successfully")
        except KeyboardInterrupt:
            logger.info("\\n🛑 Pipeline interrupted by user")
            sys.exit(130)
        except Exception as e:
            logger.error(f"💥 Pipeline failed: {e}")
            sys.exit(1)