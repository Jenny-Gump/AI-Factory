"""
Batch Processor for Content Generator
Последовательная обработка списка тем с контролем потока и предотвращением зависаний
"""

import asyncio
import json
import os
import sys
import time
import gc
import signal
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
import psutil
import requests

from src.logger_config import logger
from batch_config import (
    BATCH_CONFIG, CONTENT_TYPES, BATCH_PATHS, MEMORY_CLEANUP,
    get_content_type_config, get_progress_file_path, get_lock_file_path,
    validate_content_type, ensure_prompts_folder_exists
)


@dataclass
class TopicStatus:
    """Статус обработки одной темы"""
    topic: str
    status: str  # 'pending', 'processing', 'completed', 'failed'
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    attempts: int = 0
    error_message: Optional[str] = None
    wordpress_id: Optional[int] = None
    wordpress_url: Optional[str] = None


@dataclass
class BatchProgress:
    """Прогресс выполнения батча"""
    content_type: str
    topics_file: str
    total_topics: int
    completed_topics: List[str]
    failed_topics: List[str]
    current_topic: Optional[str]
    start_time: str
    last_update_time: str
    topic_statuses: Dict[str, TopicStatus]


class BatchProcessorError(Exception):
    """Базовая ошибка батч-процессора"""
    pass


class TopicProcessingError(BatchProcessorError):
    """Ошибка обработки темы"""
    pass




class MemoryLimitError(BatchProcessorError):
    """Превышен лимит памяти"""
    pass


class BatchProcessor:
    """Класс для последовательной обработки списка тем"""
    
    def __init__(self, topics_file: str, content_type: str = "prompt_collection", 
                 model_overrides: Dict = None, resume: bool = False, 
                 skip_publication: bool = False):
        
        # Валидация параметров
        if not validate_content_type(content_type):
            raise ValueError(f"Unknown content type: {content_type}")
        
        if not os.path.exists(topics_file):
            raise FileNotFoundError(f"Topics file not found: {topics_file}")
        
        self.topics_file = topics_file
        self.content_type = content_type
        self.model_overrides = model_overrides or {}
        self.resume = resume
        self.skip_publication = skip_publication
        
        # Настройки
        self.config = get_content_type_config(content_type)
        self.progress_file = get_progress_file_path(content_type)
        self.lock_file = get_lock_file_path(content_type)
        
        # Состояние
        self.progress: Optional[BatchProgress] = None
        self.is_running = False
        self.shutdown_requested = False
        
        # Мониторинг памяти
        self.process = psutil.Process()
        self.last_memory_check = time.time()
        
        # Обработчики сигналов для graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Убедимся что папка с промптами существует
        ensure_prompts_folder_exists(content_type)
        
        logger.info(f"BatchProcessor initialized for content type: {content_type}")
    
    def _signal_handler(self, signum, frame):
        """Обработчик сигналов для graceful shutdown"""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.shutdown_requested = True
    
    async def process_batch(self) -> bool:
        """
        Главная функция: обрабатывает все темы из файла последовательно
        Возвращает True если все темы обработаны успешно
        """
        try:
            # Проверяем блокировку
            if self._is_locked() and not self.resume:
                logger.error(f"Batch processing already running for {self.content_type}. Use --resume to continue.")
                return False
            
            # Создаем блокировку
            self._create_lock()
            
            # Загружаем или создаем прогресс
            if self.resume and os.path.exists(self.progress_file):
                self._load_progress()
                logger.info("Resuming previous batch processing session...")
            else:
                self._initialize_progress()
                logger.info("Starting new batch processing session...")
            
            self.is_running = True
            
            # Получаем список тем для обработки
            pending_topics = self._get_pending_topics()
            
            if not pending_topics:
                logger.info("No pending topics found. Batch processing complete!")
                return True
            
            logger.info(f"Processing {len(pending_topics)} pending topics...")
            
            # Обрабатываем темы последовательно
            for topic in pending_topics:
                if self.shutdown_requested:
                    logger.info("Shutdown requested, stopping batch processing...")
                    break
                
                # Проверяем память перед обработкой темы
                self._check_memory_usage()
                
                # Обрабатываем одну тему
                success = await self._process_single_topic(topic)
                
                # Обновляем прогресс
                self._update_progress(topic, success)
                
                # Принудительная очистка памяти между темами
                self._cleanup_memory_between_topics()
                
                # Автосохранение прогресса
                self._save_progress()
                
                # Пауза между темами для стабильности
                if not self.shutdown_requested:
                    await asyncio.sleep(5)
            
            # Финальная статистика
            self._log_final_statistics()
            
            return len(self.progress.failed_topics) == 0
            
        except Exception as e:
            logger.error(f"Batch processing failed: {e}")
            return False
        finally:
            self._cleanup()
    
    async def _process_single_topic(self, topic: str) -> bool:
        """
        Обрабатывает одну тему с полным контролем потока
        КРИТИЧЕСКИ ВАЖНО: СТРОГО 1 тема за раз с блокировкой до подтверждения публикации
        """
        logger.info(f"📝 Starting topic: '{topic}'")
        
        # Обновляем статус
        topic_status = TopicStatus(
            topic=topic,
            status='processing',
            start_time=datetime.now().isoformat(),
            attempts=self.progress.topic_statuses.get(topic, TopicStatus(topic, 'pending')).attempts + 1
        )
        self.progress.topic_statuses[topic] = topic_status
        self.progress.current_topic = topic
        
        try:
            # Импортируем main_flow здесь чтобы избежать циклических импортов
            from main import main_flow
            
            # 1. Запускаем основной пайплайн
            logger.info(f"🚀 Executing main pipeline for: {topic}")
            
            # Timeout для всей обработки темы
            pipeline_task = asyncio.create_task(
                main_flow(
                    topic=topic,
                    model_overrides=self.model_overrides,
                    publish_to_wordpress=not self.skip_publication
                )
            )
            
            try:
                await asyncio.wait_for(pipeline_task, timeout=BATCH_CONFIG["max_topic_timeout"])
            except asyncio.TimeoutError:
                logger.error(f"⏰ Topic '{topic}' timed out after {BATCH_CONFIG['max_topic_timeout']} seconds")
                raise TopicProcessingError(f"Processing timeout for topic: {topic}")
            
            # 2. Успешное завершение - прямолинейная логика без проверок
            topic_status.status = 'completed'
            topic_status.end_time = datetime.now().isoformat()
            
            logger.info(f"🎉 Topic completed successfully: '{topic}'")
            return True
            
        except Exception as e:
            # Обработка ошибки
            topic_status.status = 'failed'
            topic_status.end_time = datetime.now().isoformat()
            topic_status.error_message = str(e)
            
            logger.error(f"❌ Topic failed: '{topic}' - {e}")
            
            # Retry логика
            max_retries = BATCH_CONFIG["retry_failed_topics"]
            if topic_status.attempts < max_retries:
                logger.info(f"🔄 Will retry topic '{topic}' (attempt {topic_status.attempts}/{max_retries})")
                topic_status.status = 'pending'  # Возвращаем в pending для retry
                
                # Пауза перед retry
                await asyncio.sleep(BATCH_CONFIG["retry_delay_seconds"])
                
                return await self._process_single_topic(topic)
            else:
                logger.error(f"💀 Topic '{topic}' failed permanently after {max_retries} attempts")
                return False
    
    def _check_memory_usage(self):
        """Проверяет использование памяти и выдает предупреждения"""
        if not BATCH_CONFIG["enable_memory_monitoring"]:
            return
        
        current_time = time.time()
        if current_time - self.last_memory_check < BATCH_CONFIG["memory_check_interval"]:
            return
        
        self.last_memory_check = current_time
        
        # Получаем информацию о памяти
        memory_info = self.process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        
        logger.info(f"🧠 Memory usage: {memory_mb:.1f}MB")
        
        if memory_mb > BATCH_CONFIG["max_memory_mb"]:
            logger.warning(f"⚠️  High memory usage: {memory_mb:.1f}MB (limit: {BATCH_CONFIG['max_memory_mb']}MB)")
            
            # Принудительная очистка памяти
            self._cleanup_memory_between_topics()
            
            # Проверяем снова
            memory_info_after = self.process.memory_info()
            memory_mb_after = memory_info_after.rss / 1024 / 1024
            
            if memory_mb_after > BATCH_CONFIG["max_memory_mb"] * 1.2:  # 20% превышение критично
                raise MemoryLimitError(f"Memory usage too high: {memory_mb_after:.1f}MB")
    
    def _cleanup_memory_between_topics(self):
        """Принудительная очистка памяти между темами"""
        logger.info("🧹 Cleaning up memory between topics...")
        
        if MEMORY_CLEANUP["force_gc_between_topics"]:
            # Принудительный garbage collection
            collected = gc.collect()
            logger.info(f"Garbage collection: {collected} objects collected")
        
        if MEMORY_CLEANUP["clear_llm_caches"]:
            # Очистка кэшей LLM клиентов (если есть)
            # TODO: Добавить очистку специфичных кэшей когда они появятся
            pass
        
        if MEMORY_CLEANUP["reset_token_tracker"]:
            # Сброс token tracker между темами
            # TODO: Реализовать если понадобится
            pass
        
        # Проверяем результат очистки
        memory_info = self.process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        logger.info(f"Memory after cleanup: {memory_mb:.1f}MB")
    
    def _load_topics(self) -> List[str]:
        """Загружает список тем из файла"""
        try:
            with open(self.topics_file, 'r', encoding='utf-8') as f:
                topics = []
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):  # Пропускаем пустые строки и комментарии
                        topics.append(line)
                return topics
        except Exception as e:
            raise BatchProcessorError(f"Failed to load topics from {self.topics_file}: {e}")
    
    def _get_pending_topics(self) -> List[str]:
        """Возвращает список тем которые еще нужно обработать"""
        all_topics = self._load_topics()
        
        if not self.progress:
            return all_topics
        
        # Фильтруем уже обработанные темы
        completed = set(self.progress.completed_topics)
        
        # Добавляем темы для retry (failed темы с количеством попыток меньше лимита)
        retry_topics = []
        for topic in all_topics:
            if topic in completed:
                continue
                
            topic_status = self.progress.topic_statuses.get(topic)
            if topic_status and topic_status.status == 'failed':
                if topic_status.attempts < BATCH_CONFIG["retry_failed_topics"]:
                    retry_topics.append(topic)
                continue
            
            # Это новая или pending тема
            if topic not in completed:
                retry_topics.append(topic)
        
        return retry_topics
    
    def _initialize_progress(self):
        """Инициализирует новый прогресс батча"""
        topics = self._load_topics()
        
        self.progress = BatchProgress(
            content_type=self.content_type,
            topics_file=self.topics_file,
            total_topics=len(topics),
            completed_topics=[],
            failed_topics=[],
            current_topic=None,
            start_time=datetime.now().isoformat(),
            last_update_time=datetime.now().isoformat(),
            topic_statuses={topic: TopicStatus(topic, 'pending') for topic in topics}
        )
        
        logger.info(f"Initialized batch processing for {len(topics)} topics")
    
    def _load_progress(self):
        """Загружает прогресс из файла"""
        try:
            with open(self.progress_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Конвертируем обратно в объекты
            topic_statuses = {}
            for topic, status_data in data['topic_statuses'].items():
                topic_statuses[topic] = TopicStatus(**status_data)
            
            self.progress = BatchProgress(
                content_type=data['content_type'],
                topics_file=data['topics_file'],
                total_topics=data['total_topics'],
                completed_topics=data['completed_topics'],
                failed_topics=data['failed_topics'],
                current_topic=data['current_topic'],
                start_time=data['start_time'],
                last_update_time=data['last_update_time'],
                topic_statuses=topic_statuses
            )
            
            logger.info(f"Loaded progress: {len(self.progress.completed_topics)}/{self.progress.total_topics} completed")
            
        except Exception as e:
            logger.error(f"Failed to load progress: {e}")
            self._initialize_progress()
    
    def _save_progress(self):
        """Сохраняет прогресс в файл"""
        if not self.progress:
            return
        
        try:
            # Конвертируем в словарь для JSON
            progress_dict = asdict(self.progress)
            
            # Конвертируем TopicStatus объекты
            progress_dict['topic_statuses'] = {
                topic: asdict(status) for topic, status in self.progress.topic_statuses.items()
            }
            
            progress_dict['last_update_time'] = datetime.now().isoformat()
            
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                json.dump(progress_dict, f, indent=2, ensure_ascii=False)
                
            logger.debug("Progress saved successfully")
            
        except Exception as e:
            logger.error(f"Failed to save progress: {e}")
    
    def _update_progress(self, topic: str, success: bool):
        """Обновляет прогресс после обработки темы"""
        if not self.progress:
            return
        
        if success:
            if topic not in self.progress.completed_topics:
                self.progress.completed_topics.append(topic)
            
            # Убираем из failed если была там
            if topic in self.progress.failed_topics:
                self.progress.failed_topics.remove(topic)
        else:
            if topic not in self.progress.failed_topics:
                self.progress.failed_topics.append(topic)
        
        self.progress.current_topic = None
        self.progress.last_update_time = datetime.now().isoformat()
    
    def _log_final_statistics(self):
        """Выводит финальную статистику выполнения"""
        if not self.progress:
            return
        
        total = self.progress.total_topics
        completed = len(self.progress.completed_topics)
        failed = len(self.progress.failed_topics)
        
        logger.info("📊 Batch Processing Statistics:")
        logger.info(f"   Total topics: {total}")
        logger.info(f"   Completed: {completed} ({completed/total*100:.1f}%)")
        logger.info(f"   Failed: {failed} ({failed/total*100:.1f}%)")
        
        if failed > 0:
            logger.info("❌ Failed topics:")
            for topic in self.progress.failed_topics:
                status = self.progress.topic_statuses.get(topic)
                if status and status.error_message:
                    logger.info(f"   - {topic}: {status.error_message}")
                else:
                    logger.info(f"   - {topic}")
        
        # Рассчитываем общее время выполнения
        start_time = datetime.fromisoformat(self.progress.start_time)
        total_duration = datetime.now() - start_time
        logger.info(f"⏱️  Total duration: {total_duration}")
        
        if completed > 0:
            avg_time_per_topic = total_duration / completed
            logger.info(f"📈 Average time per topic: {avg_time_per_topic}")
    
    def _is_locked(self) -> bool:
        """Проверяет есть ли блокировка процесса"""
        if not os.path.exists(self.lock_file):
            return False
        
        try:
            with open(self.lock_file, 'r') as f:
                pid = int(f.read().strip())
            
            # Проверяем существует ли процесс
            return psutil.pid_exists(pid)
        except:
            return False
    
    def _create_lock(self):
        """Создает файл блокировки"""
        with open(self.lock_file, 'w') as f:
            f.write(str(os.getpid()))
    
    def _remove_lock(self):
        """Удаляет файл блокировки"""
        if os.path.exists(self.lock_file):
            os.remove(self.lock_file)
    
    def _cleanup(self):
        """Финальная очистка ресурсов"""
        logger.info("🧹 Cleaning up batch processor...")
        
        self.is_running = False
        
        # Сохраняем финальный прогресс
        if self.progress:
            self._save_progress()
        
        # Удаляем блокировку
        self._remove_lock()
        
        # Финальная очистка памяти
        self._cleanup_memory_between_topics()
        
        logger.info("Batch processor cleanup completed")


# Функция для использования из командной строки
async def run_batch_processor(topics_file: str, content_type: str = "prompt_collection",
                             model_overrides: Dict = None, resume: bool = False,
                             skip_publication: bool = False) -> bool:
    """
    Запускает batch processor с заданными параметрами
    Возвращает True если все темы обработаны успешно
    """
    processor = BatchProcessor(
        topics_file=topics_file,
        content_type=content_type,
        model_overrides=model_overrides,
        resume=resume,
        skip_publication=skip_publication
    )
    
    return await processor.process_batch()


# CLI для тестирования
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Batch processor for Content Generator")
    parser.add_argument("topics_file", help="Path to file with topics (one per line)")
    parser.add_argument("--content-type", default="prompt_collection", 
                       choices=list(CONTENT_TYPES.keys()), help="Content type")
    parser.add_argument("--resume", action="store_true", help="Resume previous batch")
    parser.add_argument("--skip-publication", action="store_true", help="Skip WordPress publication")
    parser.add_argument("--extract-model", help="Override extraction model")
    parser.add_argument("--generate-model", help="Override generation model") 
    parser.add_argument("--editorial-model", help="Override editorial model")
    
    args = parser.parse_args()
    
    # Подготовка model_overrides
    model_overrides = {}
    if args.extract_model:
        model_overrides["extract_prompts"] = args.extract_model
    if args.generate_model:
        model_overrides["generate_article"] = args.generate_model
    if args.editorial_model:
        model_overrides["editorial_review"] = args.editorial_model
    
    # Запуск batch processor
    try:
        success = asyncio.run(run_batch_processor(
            topics_file=args.topics_file,
            content_type=args.content_type,
            model_overrides=model_overrides if model_overrides else None,
            resume=args.resume,
            skip_publication=args.skip_publication
        ))
        
        if success:
            print("✅ Batch processing completed successfully")
            sys.exit(0)
        else:
            print("❌ Batch processing completed with errors")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Batch processing interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"💥 Batch processing failed: {e}")
        sys.exit(1)