import os
import json
import http.client
from typing import Dict, List, Tuple


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
    sentence = config.get('sentence', {})
    category = sentence.get('category', '')
    instruction = sentence.get('sub_domain_instruction', '')
    description = sentence.get('description', '')
    subs, err = generate_sub_domains(category, instruction, 10, description)
    if err:
        return {}, err
    return { 'sub_domains': { f'sub_domain_{i}': s for i, s in enumerate(subs) } }, ''


def sample_topic_and_persona_handler(config: Dict, prompt_config: Dict) -> Tuple[Dict, str]:
    sentence = config.get('sentence', {})
    category = sentence.get('category', '')
    tp_instruction = sentence.get('topic_persona_instruction', '')
    description = sentence.get('description', '')
    sub_domains = prompt_config.get('sub_domains', {})
    topics: Dict[str, Dict] = {}
    personas: Dict[str, Dict] = {}

    t_idx = 0
    p_idx = 0
    for sd_key, sd_value in sub_domains.items():
        topic_list, err = generate_topics(category, sd_value, tp_instruction, 2, description)
        if err:
            return {}, err
        persona_list, err = generate_personas(category, sd_value, tp_instruction, 2, description)
        if err:
            return {}, err
        for t in topic_list:
            topics[f'topic_{t_idx}'] = {'topic': t, 'sub_domain': sd_key}
            t_idx += 1
        for p in persona_list:
            personas[f'persona_{p_idx}'] = {'persona': p, 'sub_domain': sd_key}
            p_idx += 1

    out = { 'sub_domains': sub_domains, 'topics': topics, 'personas': personas }
    return out, ''


def sample_scenario_handler(config: Dict, prompt_config: Dict) -> Tuple[Dict, str]:
    sentence = config.get('sentence', {})
    category = sentence.get('category', '')
    sc_instruction = sentence.get('scenario_instruction', '')
    description = sentence.get('description', '')

    sub_domains = prompt_config.get('sub_domains', {})
    topics = prompt_config.get('topics', {})
    personas = prompt_config.get('personas', {})

    scenarios: Dict[str, Dict] = {}
    s_idx = 0
    for t_key, p_key in zip(topics.keys(), personas.keys()):
        t_val = topics[t_key]
        p_val = personas[p_key]
        sd_key = t_val.get('sub_domain')
        sd_value = sub_domains.get(sd_key)
        topic = t_val.get('topic')
        persona = p_val.get('persona')
        sc_list, err = generate_scenarios(category, sd_value, persona, topic, sc_instruction, 2, description)
        if err:
            return {}, err
        for sc in sc_list:
            scenarios[f'scenario_{s_idx}'] = {
                'scenario': sc,
                'topic': t_key,
                'persona': p_key,
                'sub_domain': sd_key,
            }
            s_idx += 1

    out = {
        'sub_domains': sub_domains,
        'topics': topics,
        'personas': personas,
        'scenarios': scenarios,
    }
    return out, ''


def sample_sentence_handler(config: Dict, prompt_config: Dict) -> Tuple[List[str], str]:
    sentence = config.get('sentence', {})
    language = config.get('language', '')
    description = sentence.get('description', '')

    sub_domains = prompt_config.get('sub_domains', {})
    topics = prompt_config.get('topics', {})
    personas = prompt_config.get('personas', {})
    scenarios = prompt_config.get('scenarios', {})

    all_sentences: List[str] = []
    for sc in scenarios.values():
        sc_text = sc.get('scenario', '')
        t_key = sc.get('topic')
        p_key = sc.get('persona')
        sd_key = sc.get('sub_domain')

        topic = topics.get(t_key, {}).get('topic', '')
        persona = personas.get(p_key, {}).get('persona', '')
        sub_domain = sub_domains.get(sd_key, '')

        prompt = f'''
You are an expert text generator for ASR training data. Generate sentences based on the following configurations.
Language: {language}
Persona: {persona}
Sub-Domain: {sub_domain}
Topic: {topic}
Scenario: {sc_text}.

Task: Generate 3 unique sentences in {language} that this persona would actually say in this specific situation. {_build_description(description)}
'''
        sents, err = _gemini_request(prompt, seed=500)
        if err:
            return [], err
        all_sentences.extend(sents)

    return all_sentences, ''
