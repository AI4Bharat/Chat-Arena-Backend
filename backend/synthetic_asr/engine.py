import os
import json
import http.client
from typing import Dict, List, Tuple
from urllib.parse import urlparse

# External API configuration - PAI server (ngrok tunnel)
PAI_SERVER_URL = os.getenv('SYNTHETIC_ASR_PAI_SERVER_URL', '')
if not PAI_SERVER_URL:
    raise ValueError("SYNTHETIC_ASR_PAI_SERVER_URL environment variable not set")

parsed_url = urlparse(PAI_SERVER_URL)
PAI_HOST = parsed_url.netloc
PAI_SCHEME = parsed_url.scheme  # 'http' or 'https'
PAI_BASE_PATH = '/pai'


def _call_pai_server(endpoint: str, payload: Dict) -> Tuple[Dict, str]:
    """
    Call PAI server (ngrok tunnel to synthetic-benchmarks).
    """
    try:
        # Use HTTP or HTTPS based on URL scheme
        if PAI_SCHEME == 'https':
            conn = http.client.HTTPSConnection(PAI_HOST)
        else:
            conn = http.client.HTTPConnection(PAI_HOST)
        
        headers = {
            'Content-Type': 'application/json',
            'ngrok-skip-browser-warning': 'true'  # CRITICAL for ngrok tunnels
        }
        
        body = json.dumps(payload)
        path = f'{PAI_BASE_PATH}{endpoint}'
        
        conn.request('POST', path, body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        
        if resp.status != 200:
            error_text = data.decode('utf-8')
            return {}, f'PAI server error ({resp.status}): {error_text}'
        
        result = json.loads(data.decode('utf-8'))
        return result, ''
    except Exception as e:
        return {}, f'Error calling PAI server: {str(e)}'


def _gemini_request(prompt: str, seed: int) -> Tuple[List[str], str]:
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        return [], 'Api key for gemini is not defined'

    body: Dict = {
        'contents': [{
            'parts': [ {'text': prompt} ]
        }],
        'generationConfig': {
            'seed': seed,
            'responseMimeType': 'application/json',
            'responseJsonSchema': {
                'type': 'object',
                'properties': {
                    'sentences': {
                        'type': 'array',
                        'items': {'type': 'string'}
                    }
                },
                'required': ['sentences']
            }
        }
    }

    try:
        conn = http.client.HTTPSConnection('generativelanguage.googleapis.com')
        headers = {'x-goog-api-key': api_key, 'Content-Type': 'application/json'}
        conn.request('POST', '/v1beta/models/gemini-2.5-flash:generateContent', body=json.dumps(body), headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        if resp.status != 200:
            return [], f'Gemini error: {resp.status} {resp.reason}'
        output = json.loads(data.decode('utf-8'))
    except Exception as e:
        return [], f'Error occured while making request, {e}'

    sentences: List[str] = []
    candidates = output.get('candidates') or []
    for cand in candidates:
        content = cand.get('content') or {}
        parts = content.get('parts') or []
        for part in parts:
            text_str = part.get('text')
            if not text_str:
                continue
            try:
                obj = json.loads(text_str)
                sentences.extend(obj.get('sentences') or [])
            except Exception:
                continue
    return sentences, ''


def _build_description(desc: str) -> str:
    return f'- Additional context: "{desc}".' if desc else ''


def generate_sub_domains(category: str, instruction: str, n: int = 10, description: str = '') -> Tuple[List[str], str]:
    """
    Generate sub-domains using Gemini when available.
    If GEMINI_API_KEY is missing, fall back to a deterministic local generator to unblock demos.
    """
    # Fallback path when API key is not available
    if not os.getenv('GEMINI_API_KEY'):
        base = (category or 'General').strip().lower()
        presets = {
            'agriculture': [
                'Crop Management', 'Soil Health', 'Irrigation Techniques', 'Pest Control', 'Post-Harvest Handling',
                'Farm Machinery', 'Organic Farming', 'Supply Chain Logistics', 'Market Prices', 'Weather Advisory'
            ],
            'healthcare': [
                'Primary Care', 'Diagnostics', 'Telemedicine', 'Pharmacy Services', 'Emergency Care',
                'Maternal Health', 'Chronic Disease Management', 'Mental Health', 'Lab Services', 'Insurance Claims'
            ],
            'finance': [
                'Retail Banking', 'Digital Payments', 'Loans & Credit', 'Insurance', 'Investments',
                'Fraud Prevention', 'Customer Support', 'KYC & Compliance', 'Wealth Management', 'Microfinance'
            ],
            'education': [
                'Admissions', 'Examinations', 'Online Classes', 'Homework Help', 'Scholarships',
                'Parent Communication', 'Library Services', 'Career Guidance', 'Attendance', 'Transport Services'
            ],
            'technology': [
                'Cloud Services', 'Cybersecurity', 'DevOps', 'AI & ML', 'IoT Platforms',
                'Mobile Apps', 'Web Development', 'Data Analytics', 'Edge Computing', 'APIs & Integration'
            ],
        }
        subs = presets.get(base, [
            'Customer Support', 'Billing & Payments', 'Account Management', 'Technical Assistance', 'Product Information',
            'Feedback & Complaints', 'Service Requests', 'Appointment Scheduling', 'Order Tracking', 'FAQ & Help'
        ])
        return subs[:n], ''

    prompt = f'''
You are helping design a large-scale synthetic speech dataset for Automatic Speech Recognition (ASR). Your task is to generate subdomains related to {category}.

Given:
- Domain / category: {category}

Task:
Generate a diverse set of subdomains related to this domain. {instruction}

Rules:
{_build_description(description)}
- Sub-domain must be meaningfully different from each other
- Avoid vague or generic labels
- Each sub-domain should be specific enough to guide sentence generation
- Do NOT include explanations or commentary

Output format:
Return {n} sub domain, each on a new line.
'''
    return _gemini_request(prompt, seed=42)


def generate_topics(category: str, sub_domain: str, instruction: str, n: int = 2, description: str = '') -> Tuple[List[str], str]:
    prompt = f'''
You are helping design a large-scale synthetic speech dataset for Automatic Speech Recognition (ASR) in {category}. Your task is to generate topics related to the sub-domain {sub_domain}.

Given:
- Domain: {category}
- Sub-Domain / category: {sub_domain}

Task:
Generate a diverse set of real-world topics related to this domain. {instruction}

Rules:
{_build_description(description)}
- Topics must be meaningfully different from each other
- Avoid vague or generic labels
- Each topic should be specific enough to guide sentence generation
- Do NOT include explanations or commentary

Output format:
Return {n} topics, each on a new line.
'''
    return _gemini_request(prompt, seed=100)


def generate_personas(category: str, sub_domain: str, instruction: str, n: int = 2, description: str = '') -> Tuple[List[str], str]:
    prompt = f'''
You are helping design a large-scale synthetic speech dataset for Automatic Speech Recognition (ASR) in {category}. Your task is to generate personas/characters related to the subdomain {sub_domain}.

Given:
- Domain: {category}
- Sub-Domain / category: {sub_domain}

Task:
Generate a diverse set of real-world personas/characters related to this domain. {instruction}

Rules:
{_build_description(description)}
- Personas must be meaningfully different from each other
- Avoid vague or generic labels
- Each persona should be specific enough to guide sentence generation
- Do NOT include explanations or commentary

Output format:
Return {n} personas, each on a new line.
'''
    return _gemini_request(prompt, seed=200)


def generate_scenarios(category: str, sub_domain: str, persona: str, topic: str, instruction: str, n: int = 2, description: str = '') -> Tuple[List[str], str]:
    prompt = f'''
You are helping design a large-scale synthetic speech dataset for Automatic Speech Recognition (ASR) in {category}. Your task is to generate situations or intents that a {persona} on the topic {topic} will talk about within the sub-domain {sub_domain}.

Given:
- Domain / category: {category}

Task:
Generate a diverse set of real-world scenarios. {instruction}

Rules:
{_build_description(description)}
- Avoid vague or generic labels
- Each situation/intent should be specific enough to guide sentence generation
- Do NOT include explanations or commentary

Output format:
Return {n} personas, each on a new line.
'''
    return _gemini_request(prompt, seed=300)


def sample_sub_domain_handler(config: Dict, body: Dict) -> Tuple[Dict, str]:
    """
    Stage 1: Generate sub-domains
    Calls PAI server with the exact payload structure it expects
    """
    # PAI server expects: {"config": {...}}
    payload = {"config": config}
    result, err = _call_pai_server('/sample/sub_domain', payload)
    if err:
        return {}, err
    return result, ''


def sample_topic_and_persona_handler(config: Dict, prompt_config: Dict) -> Tuple[Dict, str]:
    """
    Stage 2: Generate topics and personas
    Calls PAI server with config + prompt_config
    """
    # PAI server expects: {"config": {...}, "prompt_config": {...}}
    payload = {
        "config": config,
        "prompt_config": prompt_config
    }
    result, err = _call_pai_server('/sample/topic_and_persona', payload)
    if err:
        return {}, err
    return result, ''


def sample_scenario_handler(config: Dict, prompt_config: Dict) -> Tuple[Dict, str]:
    """
    Stage 3: Generate scenarios
    Calls PAI server with config + prompt_config
    """
    payload = {
        "config": config,
        "prompt_config": prompt_config
    }
    result, err = _call_pai_server('/sample/scenario', payload)
    if err:
        return {}, err
    return result, ''


def sample_sentence_handler(config: Dict, prompt_config: Dict) -> Tuple[List[str], str]:
    """
    Stage 4: Generate sample sentences
    Calls PAI server with config + prompt_config
    Returns list of sentences (not dict)
    """
    payload = {
        "config": config,
        "prompt_config": prompt_config
    }
    result, err = _call_pai_server('/sample/sentence', payload)
    if err:
        return [], err
    
    # PAI server returns {"sentences": {...}}
    # Extract to list format
    sentences_dict = result.get('sentences', {})
    sentences_list = list(sentences_dict.values())
    return sentences_list, ''
