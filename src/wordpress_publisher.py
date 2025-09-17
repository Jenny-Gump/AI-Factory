"""
WordPress Publisher Service for Content Generator
Handles publishing generated content to WordPress with Yoast SEO support
Adapted from AI News Publisher system
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
import requests
from requests.auth import HTTPBasicAuth
from transliterate import translit
import re

from src.logger_config import logger


class WordPressPublisher:
    """Service for publishing Content Generator articles to WordPress"""
    
    def __init__(self, config_env_path: str = ".env"):
        """Initialize WordPress Publisher with config from .env file"""
        self.config = self._load_config(config_env_path)
        self._validate_config()
    
    def _load_config(self, env_path: str) -> Dict[str, Any]:
        """Load configuration from .env file"""
        config = {}
        
        # Default values
        defaults = {
            'WORDPRESS_API_URL': 'https://ailynx.ru/wp-json/wp/v2',
            'WORDPRESS_USERNAME': 'PetrovA',
            'WORDPRESS_APP_PASSWORD': '',
            'USE_CUSTOM_META_ENDPOINT': 'true',
            'CUSTOM_POST_META_API_KEY': '',
            'WORDPRESS_CATEGORY': 'prompts',
            'WORDPRESS_STATUS': 'draft'
        }
        
        # Try to load from .env file
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        defaults[key.strip()] = value.strip()
        
        # Load from environment variables (override .env)
        for key in defaults:
            config[key.lower()] = os.getenv(key, defaults[key])
        
        return config
    
    def _validate_config(self):
        """Validate WordPress configuration"""
        required_fields = [
            'wordpress_api_url', 
            'wordpress_username', 
            'wordpress_app_password'
        ]
        
        missing_fields = []
        for field in required_fields:
            if not self.config.get(field):
                missing_fields.append(field)
        
        if missing_fields:
            raise ValueError(f"Missing WordPress configuration: {', '.join(missing_fields)}")
        
        logger.info("WordPress Publisher configuration validated successfully")
    
    def publish_article(self, wordpress_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Publish article to WordPress from Content Generator output
        
        Args:
            wordpress_data: Dictionary with article data from Content Generator
        
        Returns:
            Dictionary with publication results
        """
        logger.info(f"Starting WordPress publication for article: {wordpress_data.get('title', 'No title')}")
        
        result = {
            'success': False,
            'wordpress_id': None,
            'error': None,
            'url': None
        }
        
        try:
            # Prepare post data for WordPress
            wp_post_data = self._prepare_post_data(wordpress_data)
            
            # Create WordPress post
            wp_post_id = self._create_wordpress_post(wp_post_data)
            
            if wp_post_id:
                result['success'] = True
                result['wordpress_id'] = wp_post_id
                result['url'] = f"https://ailynx.ru/wp-admin/post.php?post={wp_post_id}&action=edit"
                
                logger.info(f"✅ Successfully published article with WordPress ID: {wp_post_id}")
                logger.info(f"📝 Article URL: {result['url']}")
            else:
                result['error'] = "Failed to create WordPress post"
                logger.error("❌ Failed to create WordPress post")
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"❌ Error publishing article: {str(e)}")
        
        return result
    
    def _prepare_post_data(self, wordpress_data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare WordPress post data from Content Generator output"""
        
        # Base post data
        post_data = {
            'title': wordpress_data.get('title', ''),
            'content': wordpress_data.get('content', ''),
            'excerpt': wordpress_data.get('excerpt', ''),
            'slug': wordpress_data.get('slug', ''),
            'status': self.config.get('wordpress_status', 'draft'),
        }
        
        # Categories - always use 'prompts'
        categories = wordpress_data.get('categories', ['prompts'])
        if isinstance(categories, str):
            categories = [categories]
        post_data['categories'] = self._get_category_ids(categories)
        
        # Meta fields for Yoast SEO
        meta = {}
        
        # Yoast SEO fields
        if wordpress_data.get('_yoast_wpseo_title'):
            meta['_yoast_wpseo_title'] = wordpress_data['_yoast_wpseo_title']
        
        if wordpress_data.get('_yoast_wpseo_metadesc'):
            meta['_yoast_wpseo_metadesc'] = wordpress_data['_yoast_wpseo_metadesc']
        
        if wordpress_data.get('focus_keyword'):
            meta['_yoast_wpseo_focuskw'] = wordpress_data['focus_keyword']
        
        if meta:
            post_data['meta'] = meta
        
        return post_data
    
    def _get_category_ids(self, category_names: List[str]) -> List[int]:
        """Get WordPress category IDs by names"""
        category_ids = []
        
        for category_name in category_names:
            try:
                # Get categories from WordPress
                url = f"{self.config['wordpress_api_url']}/categories"
                auth = HTTPBasicAuth(
                    self.config['wordpress_username'], 
                    self.config['wordpress_app_password']
                )
                
                params = {'search': category_name, 'per_page': 100}
                response = requests.get(url, auth=auth, params=params, timeout=30)
                
                if response.status_code == 200:
                    categories = response.json()
                    for cat in categories:
                        # Match by name or slug
                        if (cat['name'].lower() == category_name.lower() or 
                            cat['slug'].lower() == category_name.lower()):
                            category_ids.append(cat['id'])
                            logger.info(f"Found category '{category_name}' with ID {cat['id']}")
                            break
                    else:
                        # If search didn't work, try getting all categories
                        all_categories_response = requests.get(f"{self.config['wordpress_api_url']}/categories", 
                                                             auth=auth, params={'per_page': 100}, timeout=30)
                        if all_categories_response.status_code == 200:
                            all_categories = all_categories_response.json()
                            for cat in all_categories:
                                if (cat['name'].lower() == category_name.lower() or 
                                    cat['slug'].lower() == category_name.lower()):
                                    category_ids.append(cat['id'])
                                    logger.info(f"Found category '{category_name}' with ID {cat['id']} (fallback search)")
                                    break
                            else:
                                logger.warning(f"Category '{category_name}' not found, skipping")
                        else:
                            logger.warning(f"Category '{category_name}' not found, skipping")
                else:
                    logger.error(f"Failed to fetch categories: {response.status_code}")
                    
            except Exception as e:
                logger.error(f"Error fetching category '{category_name}': {str(e)}")
        
        # Default to 'Uncategorized' if no categories found
        if not category_ids:
            category_ids = [1]  # WordPress default uncategorized category
            logger.warning("No categories found, using default 'Uncategorized'")
        
        return category_ids
    
    def _create_wordpress_post(self, post_data: Dict[str, Any]) -> Optional[int]:
        """Create a post in WordPress via REST API or Custom Endpoint"""
        
        use_custom_endpoint = self.config.get('use_custom_meta_endpoint', 'false').lower() == 'true'
        
        if use_custom_endpoint and self.config.get('custom_post_meta_api_key'):
            logger.info("Using Custom Post Meta Endpoint for publishing")
            return self._create_wordpress_post_via_custom_endpoint(post_data)
        else:
            logger.info("Using standard WordPress REST API for publishing")
            return self._create_wordpress_post_standard(post_data)
    
    def _create_wordpress_post_standard(self, post_data: Dict[str, Any]) -> Optional[int]:
        """Create a post in WordPress via standard REST API"""
        try:
            url = f"{self.config['wordpress_api_url']}/posts"
            
            # Prepare authentication
            auth = HTTPBasicAuth(
                self.config['wordpress_username'], 
                self.config['wordpress_app_password']
            )
            
            # Make the request
            response = requests.post(
                url,
                json=post_data,
                auth=auth,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            if response.status_code == 201:
                wp_post = response.json()
                logger.info(f"Post created successfully via standard API: {wp_post.get('id')}")
                return wp_post.get('id')
            else:
                logger.error(f"WordPress API error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating WordPress post via standard API: {str(e)}")
            return None
    
    def _create_wordpress_post_via_custom_endpoint(self, post_data: Dict[str, Any]) -> Optional[int]:
        """Create post via Custom Post Meta Endpoint plugin"""
        try:
            # Get meta data
            meta = post_data.get('meta', {})
            
            # Transform data for custom endpoint
            custom_data = {
                'title': post_data['title'],
                'content': post_data['content'],
                'excerpt': post_data.get('excerpt', ''),
                'slug': post_data['slug'],
                'status': post_data.get('status', 'draft'),
                'categories': post_data.get('categories', []),
            }
            
            # Add SEO fields without restrictions
            if meta.get('_yoast_wpseo_title'):
                custom_data['seo_title'] = meta['_yoast_wpseo_title']
            
            if meta.get('_yoast_wpseo_metadesc'):
                custom_data['seo_description'] = meta['_yoast_wpseo_metadesc']
            
            if meta.get('_yoast_wpseo_focuskw'):
                custom_data['focus_keyword'] = meta['_yoast_wpseo_focuskw']
            
            # Remove None values
            custom_data = {k: v for k, v in custom_data.items() if v is not None}
            
            # Custom endpoint URL
            url = "https://ailynx.ru/wp-json/custom-post-meta/v1/posts/"
            
            # Authentication
            auth = HTTPBasicAuth(
                self.config['wordpress_username'], 
                self.config['wordpress_app_password']
            )
            
            # Headers with API key
            headers = {
                'Content-Type': 'application/json',
                'X-API-Key': self.config['custom_post_meta_api_key']
            }
            
            logger.info(f"Sending request to Custom Post Meta Endpoint")
            logger.debug(f"Custom data keys: {list(custom_data.keys())}")
            
            # Make the request
            response = requests.post(
                url,
                json=custom_data,
                auth=auth,
                headers=headers,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                result = response.json()
                # Handle different response formats
                post_id = result.get('post_id') or result.get('id')
                logger.info(f"Post created successfully via custom endpoint: {post_id}")
                return post_id
            else:
                logger.error(f"Custom endpoint error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating WordPress post via custom endpoint: {str(e)}")
            return None
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Get configuration summary for debugging"""
        return {
            'api_url': self.config['wordpress_api_url'],
            'username': self.config['wordpress_username'],
            'has_password': bool(self.config['wordpress_app_password']),
            'use_custom_endpoint': self.config.get('use_custom_meta_endpoint', 'false'),
            'has_custom_key': bool(self.config.get('custom_post_meta_api_key')),
            'default_category': self.config.get('wordpress_category', 'prompts'),
            'default_status': self.config.get('wordpress_status', 'draft')
        }


def test_wordpress_connection() -> bool:
    """Test WordPress connection and authentication"""
    try:
        publisher = WordPressPublisher()
        
        logger.info("Testing WordPress connection...")
        logger.info(f"Config: {publisher.get_config_summary()}")
        
        # Test basic authentication
        url = f"{publisher.config['wordpress_api_url']}/users/me"
        auth = HTTPBasicAuth(
            publisher.config['wordpress_username'], 
            publisher.config['wordpress_app_password']
        )
        
        response = requests.get(url, auth=auth, timeout=10)
        
        if response.status_code == 200:
            user_data = response.json()
            logger.info(f"✅ WordPress connection successful! User: {user_data.get('name')}")
            return True
        else:
            logger.error(f"❌ WordPress authentication failed: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ WordPress connection test failed: {str(e)}")
        return False


if __name__ == "__main__":
    # Test the connection
    test_wordpress_connection()