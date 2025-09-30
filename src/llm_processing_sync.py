def clean_llm_tokens(text: str) -> str:
    """Remove LLM-specific tokens from generated content."""
    if not text:
        return text

    # Токены для удаления (специфичные для разных LLM)
    tokens_to_remove = [
        '<｜begin▁of▁sentence｜>',
        '<|begin_of_sentence|>',
        '<｜end▁of▁sentence｜>',
        '<|end_of_sentence|>',
        '<|im_start|>',
        '<|im_end|>',
        '<|end|>',
        '<<SYS>>',
        '<</SYS>>',
        '[INST]',
        '[/INST]'
    ]

    cleaned = text
    for token in tokens_to_remove:
        cleaned = cleaned.replace(token, '')

    # Убираем лишние пробелы и переводы строк
    return cleaned.strip()

def generate_article_by_sections(structure: List[Dict], topic: str, base_path: str = None,
                                 token_tracker: TokenTracker = None, model_name: str = None) -> Dict[str, Any]:
    """Generates WordPress article by processing sections SEQUENTIALLY.

    Args:
        structure: Ultimate structure with sections to generate
        topic: The topic for the article
        base_path: Path to save LLM interactions
        token_tracker: Token usage tracker
        model_name: Override model name (uses config default if None)

    Returns:
        Dict with raw_response containing merged sections and metadata
    """
    logger.info(f"Starting SEQUENTIAL section-by-section article generation for topic: {topic}")

    # Parse actual ultimate_structure format with SMART DETECTION
    actual_sections = []

    if isinstance(structure, dict) and "article_structure" in structure:
        # НОВЫЙ ПРАВИЛЬНЫЙ ФОРМАТ - объект ultimate_structure
        actual_sections = structure["article_structure"]
        logger.info(f"✅ Found {len(actual_sections)} sections in ultimate_structure object")
    elif isinstance(structure, list) and len(structure) > 0:
        if isinstance(structure[0], dict) and "article_structure" in structure[0]:
            # СТАРЫЙ ФОРМАТ - массив с объектом
            actual_sections = structure[0]["article_structure"]
            logger.info(f"Found {len(actual_sections)} sections in article_structure (legacy format)")
        else:
            # ПРЯМОЙ МАССИВ СЕКЦИЙ
            actual_sections = structure
            logger.info(f"Using raw structure with {len(actual_sections)} sections")
    else:
        logger.error(f"Invalid structure format: {type(structure)}")
        actual_sections = []

    if not actual_sections:
        logger.error("No sections found in structure")
        return {"raw_response": json.dumps({"error": "No sections in structure"}, ensure_ascii=False)}

    total_sections = len(actual_sections)
    logger.info(f"Extracted {total_sections} sections from article_structure")

    # Create sections directory
    sections_path = None
    if base_path:
        sections_path = os.path.join(base_path, "sections")
        os.makedirs(sections_path, exist_ok=True)

    # Generate sections SEQUENTIALLY
    generated_sections = []

    for idx, section in enumerate(actual_sections, 1):
        section_num = f"section_{idx}"
        section_title = section.get('section_title', f'Section {idx}')

        logger.info(f"📝 Generating section {idx}/{total_sections}: {section_title}")

        # Prepare section path first
        section_path = None
        if sections_path:
            section_path = os.path.join(sections_path, section_num)
            os.makedirs(section_path, exist_ok=True)

        for attempt in range(1, SECTION_MAX_RETRIES + 1):
            try:
                logger.info(f"🔄 Section {idx} attempt {attempt}/{SECTION_MAX_RETRIES}: {section_title}")

                # Prepare section-specific prompt
                messages = _load_and_prepare_messages(
                    "basic_articles",
                    "01_generate_section",
                    {
                        "topic": topic,
                        "section_title": section.get("section_title", ""),
                        "section_structure": json.dumps(section, indent=2, ensure_ascii=False)
                    },
                    variables_manager=variables_manager,
                    stage_name="generate_section"
                )

                # Make SYNCHRONOUS request
                response_obj, actual_model = _make_llm_request_with_retry_sync(
                    stage_name="generate_article",
                    model_name=model_name or LLM_MODELS.get("generate_article", DEFAULT_MODEL),
                    messages=messages,
                    token_tracker=token_tracker,
                    base_path=section_path,
                    temperature=0.3
                )

                section_content = response_obj.choices[0].message.content
                section_content = clean_llm_tokens(section_content)  # Очищаем токены LLM

                # Validate content
                if not section_content or len(section_content.strip()) < 50:
                    logger.warning(f"⚠️ Section {idx} attempt {attempt} returned insufficient content")
                    if attempt < SECTION_MAX_RETRIES:
                        time.sleep(3)  # Wait 3 seconds before retry
                        continue
                    else:
                        raise Exception("All attempts returned insufficient content")

                # Save section interaction
                if section_path:

                    save_llm_interaction(
                        base_path=section_path,
                        stage_name="generate_section",
                        messages=messages,
                        response=section_content,
                        extra_params={
                            "topic": topic,
                            "section_num": idx,
                            "section_title": section.get("section_title", ""),
                            "model": actual_model,
                            "attempt": attempt
                        }
                    )

                logger.info(f"✅ Successfully generated section {idx}/{total_sections}: {section_title}")

                result = {
                    "section_num": idx,
                    "section_title": section.get("section_title", ""),
                    "content": section_content,
                    "status": "success",
                    "attempts": attempt
                }

                generated_sections.append(result)
                break  # Success, exit retry loop

            except Exception as e:
                logger.error(f"❌ Section {idx} attempt {attempt} failed: {e}")
                if attempt < SECTION_MAX_RETRIES:
                    wait_time = attempt * 5  # Progressive backoff: 5s, 10s, 15s
                    logger.info(f"⏳ Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"💥 Section {idx} failed after {SECTION_MAX_RETRIES} attempts")
                    result = {
                        "section_num": idx,
                        "section_title": section.get("section_title", ""),
                        "content": f"<p>Не удалось сгенерировать раздел '{section_title}' после {SECTION_MAX_RETRIES} попыток. Последняя ошибка: {str(e)}</p>",
                        "status": "failed",
                        "error": str(e),
                        "attempts": SECTION_MAX_RETRIES
                    }
                    generated_sections.append(result)
                    break  # Give up on this section

    # Report generation status
    successful_sections = [s for s in generated_sections if s["status"] == "success"]
    failed_sections = [s for s in generated_sections if s["status"] == "failed"]

    logger.info("=" * 60)
    logger.info("📊 SECTION GENERATION REPORT:")
    logger.info(f"✅ Completed: {len(successful_sections)}/{total_sections} sections")
    if failed_sections:
        logger.warning(f"❌ Failed: {len(failed_sections)} sections")
        for failed in failed_sections:
            logger.warning(f"  - Section {failed['section_num']}: {failed.get('error', 'Unknown error')}")
    logger.info(f"📈 Success rate: {len(successful_sections)/total_sections*100:.1f}%")
    logger.info("=" * 60)

    # Merge all sections
    merged_content = merge_sections(generated_sections, topic, structure)

    # Save merged content
    if base_path:
        with open(os.path.join(base_path, "merged_content.json"), 'w', encoding='utf-8') as f:
            json.dump({
                "sections": generated_sections,
                "merged": merged_content
            }, f, indent=2, ensure_ascii=False)

        # Save HTML version of merged content
        with open(os.path.join(base_path, "article_content.html"), 'w', encoding='utf-8') as f:
            f.write(merged_content.get("content", ""))

    logger.info(f"🎉 Article generation COMPLETE: {len(successful_sections)}/{total_sections} sections generated successfully")

    return {"raw_response": json.dumps(merged_content, ensure_ascii=False), "topic": topic}