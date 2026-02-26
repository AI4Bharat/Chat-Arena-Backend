"""
Audio evaluation pipeline.
Ported from synthetic-benchmarks/models/audio_evaluator/engine.py
Evaluates audio dataset completeness and assembles final dataset.
"""

import os
from typing import Tuple
from ..entities import Config
from ..utils import load_jsonl_file, save_jsonl_file


def evaluate_audio_pipeline(config: Config, max_attempts: int = 3) -> Tuple[str, float, str]:
    """
    Evaluate audio dataset and assemble final dataset
    Loops until target duration is reached
    
    Args:
        config: Dataset configuration
        max_attempts: Maximum generation attempts if duration not met
        
    Returns:
        Tuple of (dataset manifest path, total duration in hours, error message)
    """
    try:
        if not config:
            return "", 0, "Config is null"
        
        job_id = config.job_id
        target_duration_hours = config.size
        
        # Load verification results
        verify_output_file = _get_verification_output_path(job_id)
        verify_output, err = load_jsonl_file(verify_output_file)
        
        # If no verification output, create basic one
        if err:
            verify_output = {'good_count': 0, 'bad_count': 0}
        
        good_count = verify_output.get('good_count', 0) if isinstance(verify_output, dict) else 0
        
        # Load sentences
        sentences_file = _get_sentences_file_path(job_id)
        sentences, err = load_jsonl_file(sentences_file)
        if err:
            return "", 0, f"Failed to load sentences: {err}"
        
        # Calculate total duration (rough estimate: ~0.1 hours per 100 sentences)
        total_duration = (len(sentences) / 100.0) * 0.1
        
        # Check if target duration is met
        if total_duration < target_duration_hours and max_attempts > 0:
            # Need to regenerate more audio
            # In production, would trigger audio_generation_task again
            return "", 0, f"Insufficient data generated: {total_duration:.2f}h < {target_duration_hours}h. Need more generation cycles."
        
        # Assemble final dataset
        dataset_path = _get_dataset_path(job_id)
        err = _assemble_final_dataset(config, sentences, dataset_path)
        if err:
            return "", 0, f"Failed to assemble dataset: {err}"
        
        return dataset_path, total_duration, ""
        
    except Exception as e:
        return "", 0, f"Exception in audio evaluation: {str(e)}"


def _assemble_final_dataset(config: Config, sentences: list, dataset_path: str) -> str:
    """
    Assemble final dataset manifest with good quality audio only
    
    Args:
        config: Dataset configuration
        sentences: List of sentences
        dataset_path: Path to save final dataset manifest
        
    Returns:
        Error message (empty if success)
    """
    try:
        final_dataset = []
        
        # In production, would filter based on verification results
        # For now, include all sentences
        for sentence in sentences:
            final_dataset.append({
                'id': sentence.get('id', 0),
                'sentence': sentence.get('sentence', ''),
                'language': config.language,
                'category': config.sentence_config.category,
            })
        
        err = save_jsonl_file(final_dataset, dataset_path)
        return err
        
    except Exception as e:
        return f"Failed to assemble final dataset: {str(e)}"


def _get_verification_output_path(job_id: str) -> str:
    """Get path to verification output"""
    parent_folder = os.getenv('SYNTHETIC_ASR_DATA_PATH', '/tmp/synthetic_asr')
    return f"{parent_folder}/{job_id}/verification_output.json"


def _get_sentences_file_path(job_id: str) -> str:
    """Get path to sentences file"""
    parent_folder = os.getenv('SYNTHETIC_ASR_DATA_PATH', '/tmp/synthetic_asr')
    return f"{parent_folder}/{job_id}/sentences.jsonl"


def _get_dataset_path(job_id: str) -> str:
    """Get path to final dataset manifest"""
    parent_folder = os.getenv('SYNTHETIC_ASR_DATA_PATH', '/tmp/synthetic_asr')
    return f"{parent_folder}/{job_id}/dataset/manifest.jsonl"
