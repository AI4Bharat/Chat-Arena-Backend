import base64
from typing import List, Dict, Optional, Set, Tuple
from django.core.cache import cache
from django.db.models import Q, F
import re
import json
import datetime
from message.models import Message
from google.cloud import storage
from django.conf import settings
import uuid
import os
import io

class MessageAnalyzer:
    """Analyze message content and patterns"""
    
    @staticmethod
    def extract_code_blocks(content: str) -> List[Dict[str, str]]:
        """Extract code blocks from message content"""
        code_pattern = r'```(\w+)?\n(.*?)```'
        matches = re.findall(code_pattern, content, re.DOTALL)
        
        code_blocks = []
        for language, code in matches:
            code_blocks.append({
                'language': language or 'plain',
                'code': code.strip()
            })
        
        return code_blocks
    
    @staticmethod
    def calculate_message_similarity(msg1: str, msg2: str) -> float:
        """Calculate similarity between two messages"""
        # Simple implementation using word overlap
        # In production, use more sophisticated methods like embeddings
        
        words1 = set(msg1.lower().split())
        words2 = set(msg2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)
    
    @staticmethod
    def detect_language(content: str) -> str:
        """Detect the primary language of the message"""
        # Simplified detection based on common patterns
        # In production, use a proper language detection library
        
        if re.search(r'[\u4e00-\u9fff]', content):
            return 'chinese'
        elif re.search(r'[\u0600-\u06ff]', content):
            return 'arabic'
        elif re.search(r'[\u3040-\u309f\u30a0-\u30ff]', content):
            return 'japanese'
        elif re.search(r'[\uac00-\ud7af]', content):
            return 'korean'
        
        return 'english'  # Default
    
    @staticmethod
    def analyze_conversation_quality(messages: List['Message']) -> Dict:
        """Analyze the quality of a conversation"""
        analysis = {
            'total_messages': len(messages),
            'avg_message_length': 0,
            'conversation_depth': 0,
            'question_count': 0,
            'code_blocks_count': 0,
            'language_diversity': set(),
            'response_quality_indicators': {
                'detailed_responses': 0,
                'short_responses': 0,
                'contains_examples': 0,
                'contains_references': 0
            }
        }
        
        total_length = 0
        max_depth = 0
        current_depth = 0
        
        for msg in messages:
            # Message length
            total_length += len(msg.content)
            
            # Questions
            if '?' in msg.content:
                analysis['question_count'] += 1
            
            # Code blocks
            code_blocks = MessageAnalyzer.extract_code_blocks(msg.content)
            analysis['code_blocks_count'] += len(code_blocks)
            
            # Language
            language = MessageAnalyzer.detect_language(msg.content)
            analysis['language_diversity'].add(language)
            
            # Response quality for assistant messages
            if msg.role == 'assistant':
                if len(msg.content) > 500:
                    analysis['response_quality_indicators']['detailed_responses'] += 1
                elif len(msg.content) < 50:
                    analysis['response_quality_indicators']['short_responses'] += 1
                
                if 'example' in msg.content.lower() or 'for instance' in msg.content.lower():
                    analysis['response_quality_indicators']['contains_examples'] += 1
                
                if 'http' in msg.content or 'source:' in msg.content.lower():
                    analysis['response_quality_indicators']['contains_references'] += 1
            
            # Conversation depth
            if msg.role == 'user':
                current_depth += 1
                max_depth = max(max_depth, current_depth)
            else:
                current_depth = 0
        
        analysis['avg_message_length'] = total_length / len(messages) if messages else 0
        analysis['conversation_depth'] = max_depth
        analysis['language_diversity'] = list(analysis['language_diversity'])
        
        return analysis


class MessagePathfinder:
    """Find paths between messages in conversation trees"""
    
    @staticmethod
    def find_shortest_path(start: 'Message', end: 'Message') -> List['Message']:
        """Find shortest path between two messages using BFS"""
        
        if start.session_id != end.session_id:
            return []
        
        # BFS to find path
        visited = set()
        queue = [(start, [start])]
        
        while queue:
            current, path = queue.pop(0)
            
            if current.id == end.id:
                return path
            
            if current.id in visited:
                continue
            
            visited.add(current.id)
            
            # Check children
            if current.child_ids:
                children = Message.objects.filter(id__in=current.child_ids)
                for child in children:
                    if child.id not in visited:
                        queue.append((child, path + [child]))
            
            # Check parents
            if current.parent_message_ids:
                parents = Message.objects.filter(id__in=current.parent_message_ids)
                for parent in parents:
                    if parent.id not in visited:
                        queue.append((parent, path + [parent]))
        
        return []
    
    @staticmethod
    def find_all_paths(start: 'Message', end: 'Message', max_depth: int = 10) -> List[List['Message']]:
        """Find all possible paths between two messages"""
        
        if start.session_id != end.session_id:
            return []
        
        all_paths = []
        
        def dfs(current, target, path, visited, depth):
            if depth > max_depth:
                return
            
            if current.id == target.id:
                all_paths.append(path)
                return
            
            visited.add(current.id)
            
            # Explore children
            if current.child_ids:
                children = Message.objects.filter(id__in=current.child_ids)
                for child in children:
                    if child.id not in visited:
                        dfs(child, target, path + [child], visited.copy(), depth + 1)
            
            # Explore parents
            if current.parent_message_ids:
                parents = Message.objects.filter(id__in=current.parent_message_ids)
                for parent in parents:
                    if parent.id not in visited:
                        dfs(parent, target, path + [parent], visited.copy(), depth + 1)
        
        dfs(start, end, [start], set(), 0)
        return all_paths


class MessageCache:
    """Cache manager for message data"""
    
    CACHE_PREFIX = 'message'
    
    @classmethod
    def cache_message_tree(cls, root_id: str, tree_data: Dict, timeout: int = 3600):
        """Cache message tree data"""
        key = f"{cls.CACHE_PREFIX}:tree:{root_id}"
        cache.set(key, tree_data, timeout)
    
    @classmethod
    def get_cached_tree(cls, root_id: str) -> Optional[Dict]:
        """Get cached message tree"""
        key = f"{cls.CACHE_PREFIX}:tree:{root_id}"
        return cache.get(key)
    
    @classmethod
    def invalidate_message_cache(cls, message_id: str):
        """Invalidate all cache entries for a message"""
        # Delete tree cache for this message and its ancestors
        
        try:
            message = Message.objects.get(id=message_id)
            
            # Invalidate this message's tree
            cache.delete(f"{cls.CACHE_PREFIX}:tree:{message_id}")
            
            # Invalidate parent trees
            if message.parent_message_ids:
                for parent_id in message.parent_message_ids:
                    cls.invalidate_message_cache(parent_id)
        except Message.DoesNotExist:
            pass


def format_message_for_export(message: 'Message', format_type: str = 'plain') -> str:
    """Format a message for export"""
    if format_type == 'plain':
        role = message.role.upper()
        model_info = f" ({message.model.display_name})" if message.model else ""
        return f"{role}{model_info}: {message.content}"
    
    elif format_type == 'markdown':
        role = message.role.capitalize()
        model_info = f" ({message.model.display_name})" if message.model else ""
        prefix = "**" if message.role == 'user' else "*"
        suffix = "**" if message.role == 'user' else "*"
        return f"{prefix}{role}{model_info}:{suffix} {message.content}"
    
    elif format_type == 'json':
        return json.dumps({
            'id': str(message.id),
            'role': message.role,
            'content': message.content,
            'model': message.model.display_name if message.model else None,
            'created_at': message.created_at.isoformat()
        })
    
    return message.content

def generate_signed_url(blob_name, expiration=900):
    """
    Generates a v4 signed URL for a blob.
    """
    try:
        if not blob_name:
            return None
            
        storage_client = storage.Client()
        bucket = storage_client.bucket(settings.GS_BUCKET_NAME)
        blob = bucket.blob(blob_name)

        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(seconds=expiration),
            method="GET",
        )
        return url
    except Exception as e:
        print(f"Error generating signed URL: {e}")
        return None

def upload_tts_audio(audio_base64, folder='tts-audios'):
    try:
        # Decode base64 string to bytes
        audio_bytes = base64.b64decode(audio_base64)

        # Create a file-like object
        audio_file = io.BytesIO(audio_bytes)

        # Upload to Google Cloud Storage
        client = storage.Client()
        bucket = client.bucket(settings.GS_BUCKET_NAME)
        blob_name = f"{folder}/{uuid.uuid4()}{'.wav'}"
        blob = bucket.blob(blob_name)
        blob.upload_from_file(audio_file, content_type="audio/wav")

        # Generate signed URL
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=15),
            method="GET",
        )

        return {
            'path': blob_name,
            'url': signed_url,
        }

    except Exception as e:
        raise Exception(f"Failed to upload audio: {str(e)}")