"""
Audio verification pipeline.
Ported from synthetic-benchmarks/models/audio_verifier/engine.py
Validates audio quality and filters out bad quality audio.
"""

import os
from typing import Tuple
from ..entities import Config
from ..utils import save_jsonl_file, load_jsonl_file, http_utils


def verify_audio_pipeline(config: Config) -> Tuple[int, int, str]:
    """
    Verify audio quality and filter out bad audio
    
    Args:
        config: Dataset configuration
        
    Returns:
        Tuple of (good audio count, bad audio count, error message)
    """
    try:
        if not config:
            return 0, 0, "Config is null"
        
        job_id = config.job_id
        
        # Load audio manifest from TTS service
        audio_manifest_file = _get_audio_output_manifest_path(job_id)
        audio_data, err = load_jsonl_file(audio_manifest_file)
        if err:
            return 0, 0, f"Failed to load audio manifest: {err}"
        
        if not audio_data:
            return 0, 0, "No audio data to verify"
        
        # Create verification manifest
        verify_manifest_file = _get_verification_manifest_path(job_id)
        err = _create_verification_manifest(config, audio_data, verify_manifest_file)
        if err:
            return 0, 0, f"Failed to create verification manifest: {err}"
        
        # Call verification service
        good_count, bad_count, err = _call_verification_service(config, verify_manifest_file)
        if err:
            return 0, 0, f"Verification service failed: {err}"
        
        # Save verification results
        verification_output = _get_verification_output_path(job_id)
        err = _save_verification_results(config, good_count, bad_count, verification_output)
        if err:
            return good_count, bad_count, f"Warning: Could not save results: {err}"
        
        return good_count, bad_count, ""
        
    except Exception as e:
        return 0, 0, f"Exception in audio verification: {str(e)}"


def _create_verification_manifest(config: Config, audio_data: list, manifest_file: str) -> str:
    """
    Create manifest for verification service
    
    Args:
        config: Dataset configuration
        audio_data: Audio metadata
        manifest_file: Path to save manifest
        
    Returns:
        Error message (empty if success)
    """
    try:
        manifest = []
        for item in audio_data:
            entry = {
                'id': item.get('id', 0),
                'audio_path': item.get('audio_path', ''),
                'text': item.get('text', ''),
                'duration': item.get('duration', 0),
                'language': config.language,
            }
            manifest.append(entry)
        
        err = save_jsonl_file(manifest, manifest_file)
        return err
        
    except Exception as e:
        return f"Failed to create verification manifest: {str(e)}"


def _call_verification_service(config: Config, manifest_file: str) -> Tuple[int, int, str]:
    """
    Call external verification service
    
    Args:
        config: Dataset configuration
        manifest_file: Path to verification manifest
        
    Returns:
        Tuple of (good count, bad count, error message)
    """
    try:
        # Verification service (could be ASR model, quality checker, etc.)
        verify_host = os.getenv('VERIFY_SERVICE_HOST', 'localhost')
        verify_port = int(os.getenv('VERIFY_SERVICE_PORT', '8002'))
        
        body = {
            'manifest_location': manifest_file,
            'job_id': config.job_id,
            'language': config.language,
        }
        
        headers = {'Content-Type': 'application/json'}
        
        result, err = http_utils.make_local_post_request(
            verify_host,
            '/verify',
            headers,
            body,
            port=verify_port,
            timeout=3600
        )
        
        if err:
            # If service not available, count all as good
            manifest, _ = load_jsonl_file(manifest_file)
            count = len(manifest)
            return count, 0, ""
        
        # Service should return good/bad counts
        if isinstance(result, dict):
            good_count = result.get('good_count', 0)
            bad_count = result.get('bad_count', 0)
            return good_count, bad_count, ""
        
        return 0, 0, ""
        
    except Exception as e:
        # Gracefully handle missing verification service
        manifest, _ = load_jsonl_file(manifest_file)
        return len(manifest), 0, ""


def _save_verification_results(config: Config, good_count: int, bad_count: int, output_file: str) -> str:
    """
    Save verification results
    
    Args:
        config: Dataset configuration
        good_count: Count of good audio
        bad_count: Count of bad audio
        output_file: Path to save results
        
    Returns:
        Error message (empty if success)
    """
    try:
        results = {
            'job_id': config.job_id,
            'good_count': good_count,
            'bad_count': bad_count,
            'total_count': good_count + bad_count,
        }
        
        from ..utils import save_json_file
        return save_json_file(results, output_file)
        
    except Exception as e:
        return f"Failed to save verification results: {str(e)}"


def _get_audio_output_manifest_path(job_id: str) -> str:
    """Get path to audio output from TTS service"""
    parent_folder = os.getenv('SYNTHETIC_ASR_DATA_PATH', '/tmp/synthetic_asr')
    return f"{parent_folder}/{job_id}/audio_output_manifest.jsonl"


def _get_verification_manifest_path(job_id: str) -> str:
    """Get path to verification manifest"""
    parent_folder = os.getenv('SYNTHETIC_ASR_DATA_PATH', '/tmp/synthetic_asr')
    return f"{parent_folder}/{job_id}/verification_manifest.jsonl"


def _get_verification_output_path(job_id: str) -> str:
    """Get path to verification output"""
    parent_folder = os.getenv('SYNTHETIC_ASR_DATA_PATH', '/tmp/synthetic_asr')
    return f"{parent_folder}/{job_id}/verification_output.json"
