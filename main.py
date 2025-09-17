import asyncio
import sys
import os
import json
import re
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
    generate_wordpress_article,
    editorial_review,
    _load_and_prepare_messages,
    _make_llm_request_with_retry,
    save_llm_interaction,
    _parse_json_from_response
)
from src.wordpress_publisher import WordPressPublisher
from src.token_tracker import TokenTracker
from src.config import LLM_MODELS
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

async def basic_articles_pipeline(topic: str, publish_to_wordpress: bool = True):
    """
    Simplified pipeline for generating basic articles with FAQ and sources.
    Этапы: 1-6 поиск/очистка → 7 структуры → 8 ультимативная → 9 генерация → 10 редактура
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
        "editorial_review": os.path.join(base_output_path, "09_editorial_review"),
        "links": os.path.join(base_output_path, "10_link_processing"),
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

    # --- Этап 7: Извлечение структур ---
    logger.info(f"Starting structure extraction from {len(cleaned_sources)} sources...")
    all_structures = []
    extraction_stats = []

    for i, source in enumerate(cleaned_sources):
        source_id = f"source_{i+1}"
        logger.info(f"Extracting structure from {source_id}...")

        structures = extract_prompts_from_article(
            article_text=source['cleaned_content'],
            topic=topic,
            base_path=paths["structure_extraction"],
            source_id=source_id,
            token_tracker=token_tracker,
            model_name=active_models.get("extract_prompts")
        )

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

    save_artifact(all_structures, paths["structure_extraction"], "all_structures.json")

    if not all_structures:
        logger.error("No structures could be extracted from the sources. Exiting.")
        return

    # --- Этап 8: Создание ультимативной структуры ---
    logger.info("Creating ultimate structure from extracted structures...")

    messages = _load_and_prepare_messages(
        "basic_articles",
        "02_create_ultimate_structure",
        {"topic": topic, "article_text": json.dumps(all_structures, indent=2)}
    )

    response_obj, actual_model = _make_llm_request_with_retry(
        stage_name="create_structure",
        model_name=active_models.get("create_structure"),
        messages=messages,
        token_tracker=token_tracker,
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

    # --- Этап 9: Генерация WordPress статьи ---
    logger.info("Generating WordPress-ready article from ultimate structure...")
    wordpress_data = generate_wordpress_article(
        prompts=ultimate_structure,
        topic=topic,
        base_path=paths["final_article"],
        token_tracker=token_tracker,
        model_name=active_models.get("generate_article")
    )

    save_artifact(wordpress_data, paths["final_article"], "wordpress_data.json")

    if isinstance(wordpress_data, dict) and "raw_response" in wordpress_data:
        logger.info(f"Generated article data ready for editorial review")
    else:
        logger.error("Invalid WordPress data structure returned")

    # --- Этап 10: Editorial Review ---
    logger.info("Starting editorial review and cleanup...")
    raw_response = wordpress_data.get("raw_response", "")
    wordpress_data_final = editorial_review(
        raw_response=raw_response,
        topic=topic,
        base_path=paths["editorial_review"],
        token_tracker=token_tracker,
        model_name=active_models.get("editorial_review")
    )

    save_artifact(wordpress_data_final, paths["editorial_review"], "wordpress_data_final.json")

    if isinstance(wordpress_data_final, dict) and "content" in wordpress_data_final:
        save_artifact(wordpress_data_final["content"], paths["editorial_review"], "article_content_final.html")
        logger.info(f"Editorial review completed: {wordpress_data_final.get('title', 'No title')}")
    else:
        logger.warning("Editorial review returned invalid structure, using original data")
        wordpress_data_final = wordpress_data

    # --- Этап 10.5: Link Processing ---
    from src.config import LINK_PROCESSING_ENABLED
    if LINK_PROCESSING_ENABLED and isinstance(wordpress_data_final, dict) and "content" in wordpress_data_final:
        logger.info("=== Starting Link Processing Stage ===")
        try:
            logger.info("Импортируем LinkProcessor...")
            from src.link_processor import LinkProcessor
            logger.info("✅ LinkProcessor импортирован успешно")

            logger.info("Создаем экземпляр LinkProcessor...")
            link_processor = LinkProcessor()
            logger.info("✅ LinkProcessor создан успешно")

            logger.info("Запускаем process_links...")
            wordpress_data_with_links = await link_processor.process_links(
                wordpress_data=wordpress_data_final,
                topic=topic,
                base_path=paths["links"],
                token_tracker=token_tracker,
                active_models=active_models
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

    # Token usage report
    token_summary = token_tracker.get_session_summary()
    logger.info(f"Total tokens used: {token_summary['session_summary']['total_tokens']}")
    token_report_path = os.path.join(base_output_path, "token_usage_report.json")
    token_tracker.save_token_report(base_output_path)
    logger.info(f"Token usage report: {token_report_path}")

async def main_flow(topic: str, model_overrides: Dict = None, publish_to_wordpress: bool = True):
    """Wrapper function for batch processor compatibility"""
    return await basic_articles_pipeline(topic, publish_to_wordpress)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python main.py \"Your topic here\"")
        print("Example: python main.py \"Best AI tools for content creation in 2024\"")
        sys.exit(1)

    topic = sys.argv[1]
    logger.info(f"Starting pipeline for topic: {topic}")

    try:
        asyncio.run(basic_articles_pipeline(topic))
        logger.info("✅ Pipeline completed successfully")
    except KeyboardInterrupt:
        logger.info("\\n🛑 Pipeline interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"💥 Pipeline failed: {e}")
        sys.exit(1)