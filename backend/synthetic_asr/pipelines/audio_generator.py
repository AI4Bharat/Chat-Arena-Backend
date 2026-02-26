"""
Audio generation pipeline.
Ported from synthetic-benchmarks/models/audio_generator/engine.py
Generates audio from sentences using TTS service.
"""

import os
from typing import Tuple
from ..entities import Config
from ..utils import save_jsonl_file, load_jsonl_file, http_utils


def generate_audio_pipeline(config: Config) -> Tuple[str, int, str]:
    """
    Generate audio files from sentences
    
    Args:
        config: Dataset configuration with audio settings
        
    Returns:
        Tuple of (manifest file path, audio count, error message)
    """
    try:
        if not config:
            return "", 0, "Config is null"
        
        if not config.audio_config:
            return "", 0, "Audio config is missing"
        
        job_id = config.job_id
        
        # Load sentences
        sentences_file = _get_sentences_file_path(job_id)
        sentences, err = load_jsonl_file(sentences_file)
        if err:
            return "", 0, f"Failed to load sentences: {err}"
        
        if not sentences:
            return "", 0, "No sentences found to generate audio"
        
        # Create audio generation manifest
        manifest_file = _get_audio_manifest_path(job_id)
        err = _create_audio_manifest(config, sentences, manifest_file)
        if err:
            return "", 0, f"Failed to create manifest: {err}"
        
        # Call TTS service
        audio_count, err = _call_tts_service(config, manifest_file)
        if err:
            return "", 0, f"TTS service failed: {err}"
        
        if audio_count == 0:
            return "", 0, "No audio files were generated"
        
        return manifest_file, audio_count, ""
        
    except Exception as e:
        return "", 0, f"Exception in audio generation: {str(e)}"


def _create_audio_manifest(config: Config, sentences: list, manifest_file: str) -> str:
    """
    Create manifest for TTS service with sentence and audio config
    
    Args:
        config: Dataset configuration
        sentences: List of sentences
        manifest_file: Path to save manifest
        
    Returns:
        Error message (empty if success)
    """
    try:
        manifest_data = []
        
        for idx, sentence in enumerate(sentences):
            sent_text = sentence.get('sentence', '')
            if not sent_text:
                continue
            
            # Create manifest entry for TTS
            entry = {
                'id': idx,
                'text': sent_text,
                'language': config.language,
                'genders': config.audio_config.gender,
                'age_groups': config.audio_config.age_group,
                'accents': config.audio_config.accent,
            }
            manifest_data.append(entry)
        
        err = save_jsonl_file(manifest_data, manifest_file)
        return err
        
    except Exception as e:
        return f"Failed to create manifest: {str(e)}"


def _call_tts_service(config: Config, manifest_file: str) -> Tuple[int, str]:
    """
    Call external TTS service to generate audio
    
    Args:
        config: Dataset configuration
        manifest_file: Path to manifest file
        
    Returns:
        Tuple of (audio file count, error message)
    """
    try:
        # TTS service is expected to run on port 8001
        tts_host = os.getenv('TTS_SERVICE_HOST', 'localhost')
        tts_port = int(os.getenv('TTS_SERVICE_PORT', '8001'))
        
        body = {
            'manifest_location': manifest_file,
            'job_id': config.job_id,
            'language': config.language,
        }
        
        headers = {'Content-Type': 'application/json'}
        
        result, err = http_utils.make_local_post_request(
            tts_host,
            '/generate',
            headers,
            body,
            port=tts_port,
            timeout=7200  # 2 hour timeout for TTS
        )
        
        if err:
            return 0, f"TTS service error: {err}"
        
        # Service should return audio count
        if isinstance(result, dict):
            audio_count = result.get('audio_count', 0)
            return audio_count, ""
        
        # Default: count sentences as approximation
        sentences, err = load_jsonl_file(manifest_file)
        return len(sentences) if not err else 0, ""
        
    except Exception as e:
        return 0, f"Exception calling TTS service: {str(e)}"


def _get_sentences_file_path(job_id: str) -> str:
    """Get path to sentences file"""
    parent_folder = os.getenv('SYNTHETIC_ASR_DATA_PATH', '/tmp/synthetic_asr')
    return f"{parent_folder}/{job_id}/sentences.jsonl"


def _get_audio_manifest_path(job_id: str) -> str:
    """Get path to audio manifest"""
    parent_folder = os.getenv('SYNTHETIC_ASR_DATA_PATH', '/tmp/synthetic_asr')
    return f"{parent_folder}/{job_id}/audio_manifest.jsonl"
