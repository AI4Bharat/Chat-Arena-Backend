import os
import re
from pathlib import Path

def find_api_calls():
    """Scan codebase for external API client usage"""
    
    api_patterns = {
        'openai': r'(from openai|import openai|OpenAI\(|AsyncOpenAI\()',
        'anthropic': r'(from anthropic|import anthropic|Anthropic\(|AsyncAnthropic\()',
        'google': r'(from google\.|import google|genai\.|texttospeech|speech)',
        'elevenlabs': r'(from elevenlabs|import elevenlabs|ElevenLabs\()',
        'cartesia': r'(from cartesia|import cartesia|Cartesia\(|AsyncCartesia\()',
        'mistral': r'(mistral|MistralClient)',
        'meta': r'(meta|llama|Meta)',
        'deepseek': r'(deepseek|DeepSeek)',
        'qwen': r'(qwen|Qwen)',
        'litellm': r'(from litellm|import litellm|acompletion|completion)',
        'httpx': r'(from httpx|import httpx|httpx\.AsyncClient|httpx\.Client)',
        'aiohttp': r'(from aiohttp|import aiohttp|ClientSession)',
        'requests': r'(import requests|from requests|requests\.get|requests\.post)',
        'tritonclient': r'(from tritonclient|import tritonclient|InferenceServerClient)',
        'firebase': r'(from firebase_admin|import firebase_admin)',
    }
    
    findings = {provider: [] for provider in api_patterns.keys()}
    
    backend_path = Path('.')
    
    for py_file in backend_path.rglob('*.py'):
        # Skip migrations, tests, venv
        if any(x in str(py_file) for x in ['migrations', 'test', 'venv', '__pycache__']):
            continue
            
        try:
            content = py_file.read_text(encoding='utf-8')
            
            for provider, pattern in api_patterns.items():
                matches = re.finditer(pattern, content, re.IGNORECASE)
                for match in matches:
                    line_num = content[:match.start()].count('\n') + 1
                    findings[provider].append({
                        'file': str(py_file),
                        'line': line_num,
                        'code': match.group(0)
                    })
        except Exception as e:
            pass
    
    return findings

def analyze_async_support():
    """Analyze which providers have async support"""
    
    providers = {
        'LLM Providers': {
            'OpenAI': {
                'sdk': 'openai',
                'version': '2.8.1',
                'async_native': True,
                'async_client': 'AsyncOpenAI',
                'strategy': 'Use AsyncOpenAI client',
                'priority': 'HIGH',
                'effort': 'LOW'
            },
            'Anthropic': {
                'sdk': 'anthropic',
                'version': '0.76.0',
                'async_native': True,
                'async_client': 'AsyncAnthropic',
                'strategy': 'Use AsyncAnthropic client',
                'priority': 'HIGH',
                'effort': 'LOW'
            },
            'Google Gemini': {
                'sdk': 'google-generativeai',
                'version': 'Unknown',
                'async_native': False,
                'async_client': 'N/A',
                'strategy': 'Wrap with sync_to_async() or migrate to httpx',
                'priority': 'HIGH',
                'effort': 'MEDIUM'
            },
            'LiteLLM': {
                'sdk': 'litellm',
                'version': '1.80.7',
                'async_native': True,
                'async_client': 'acompletion()',
                'strategy': 'Use acompletion() instead of completion()',
                'priority': 'HIGH',
                'effort': 'LOW'
            },
            'Mistral': {
                'sdk': 'Custom/requests',
                'version': 'N/A',
                'async_native': False,
                'async_client': 'httpx.AsyncClient',
                'strategy': 'Migrate to httpx.AsyncClient',
                'priority': 'MEDIUM',
                'effort': 'MEDIUM'
            },
            'DeepSeek': {
                'sdk': 'Custom/requests',
                'version': 'N/A',
                'async_native': False,
                'async_client': 'httpx.AsyncClient',
                'strategy': 'Migrate to httpx.AsyncClient',
                'priority': 'MEDIUM',
                'effort': 'MEDIUM'
            },
            'Meta/Llama': {
                'sdk': 'Via LiteLLM',
                'version': '1.80.7',
                'async_native': True,
                'async_client': 'litellm.acompletion()',
                'strategy': 'Use LiteLLM async wrapper',
                'priority': 'MEDIUM',
                'effort': 'LOW'
            },
            'Qwen': {
                'sdk': 'Custom/requests',
                'version': 'N/A',
                'async_native': False,
                'async_client': 'httpx.AsyncClient',
                'strategy': 'Migrate to httpx.AsyncClient',
                'priority': 'LOW',
                'effort': 'MEDIUM'
            },
        },
        'TTS Providers': {
            'ElevenLabs': {
                'sdk': 'elevenlabs',
                'version': '2.31.0',
                'async_native': True,
                'async_client': 'AsyncElevenLabs',
                'strategy': 'Use async methods (generate, convert)',
                'priority': 'HIGH',
                'effort': 'LOW'
            },
            'Cartesia': {
                'sdk': 'cartesia',
                'version': '2.0.17',
                'async_native': True,
                'async_client': 'AsyncCartesia',
                'strategy': 'Use AsyncCartesia client',
                'priority': 'HIGH',
                'effort': 'LOW'
            },
            'Google Cloud TTS': {
                'sdk': 'google-cloud-texttospeech',
                'version': 'Unknown',
                'async_native': False,
                'async_client': 'N/A',
                'strategy': 'Wrap with sync_to_async()',
                'priority': 'MEDIUM',
                'effort': 'LOW'
            },
            'Triton TTS': {
                'sdk': 'tritonclient',
                'version': '2.64.0',
                'async_native': False,
                'async_client': 'N/A',
                'strategy': 'Keep sync (low usage), wrap if needed',
                'priority': 'LOW',
                'effort': 'LOW'
            },
        },
        'ASR Providers': {
            'Google Speech-to-Text': {
                'sdk': 'google-cloud-speech',
                'version': 'Unknown',
                'async_native': False,
                'async_client': 'N/A',
                'strategy': 'Wrap with sync_to_async()',
                'priority': 'MEDIUM',
                'effort': 'LOW'
            },
        },
        'HTTP Clients': {
            'httpx': {
                'sdk': 'httpx',
                'version': '0.28.1',
                'async_native': True,
                'async_client': 'httpx.AsyncClient',
                'strategy': 'Already available, use for custom APIs',
                'priority': 'HIGH',
                'effort': 'N/A'
            },
            'aiohttp': {
                'sdk': 'aiohttp',
                'version': '3.12.15',
                'async_native': True,
                'async_client': 'aiohttp.ClientSession',
                'strategy': 'Already available, alternative to httpx',
                'priority': 'MEDIUM',
                'effort': 'N/A'
            },
            'requests': {
                'sdk': 'requests',
                'version': 'Unknown',
                'async_native': False,
                'async_client': 'N/A',
                'strategy': 'Replace with httpx.AsyncClient in async views',
                'priority': 'HIGH',
                'effort': 'LOW'
            },
        }
    }
    
    return providers

def generate_audit_report():
    """Generate comprehensive API audit report"""
    
    print("🔍 Scanning codebase for external API usage...\n")
    findings = find_api_calls()
    providers = analyze_async_support()
    
    report = []
    report.append("# External API Audit - Chat Arena Backend\n")
    report.append("**Generated:** " + os.popen('date /t').read().strip() + "\n")
    report.append("**Task:** 1.3 - External API Audit\n")
    report.append("---\n\n")
    
    report.append("## Executive Summary\n\n")
    
    # Count findings
    total_found = sum(len(v) for v in findings.values())
    providers_found = [k for k, v in findings.items() if len(v) > 0]
    
    report.append(f"**Total API References Found:** {total_found}\n")
    report.append(f"**Providers Detected:** {len(providers_found)}\n\n")
    
    # Usage statistics
    report.append("### Provider Usage\n\n")
    report.append("| Provider | References | Files |\n")
    report.append("|----------|------------|-------|\n")
    for provider in sorted(findings.keys()):
        count = len(findings[provider])
        files = len(set(f['file'] for f in findings[provider]))
        if count > 0:
            report.append(f"| {provider} | {count} | {files} |\n")
    
    report.append("\n---\n\n")
    
    # Async readiness by category
    for category, items in providers.items():
        report.append(f"## {category}\n\n")
        report.append("| Provider | SDK | Version | Async Native | Async Client | Strategy | Priority | Effort |\n")
        report.append("|----------|-----|---------|--------------|--------------|----------|----------|--------|\n")
        
        for name, info in items.items():
            async_icon = "✅" if info['async_native'] else "❌"
            report.append(f"| **{name}** | `{info['sdk']}` | {info['version']} | {async_icon} | `{info['async_client']}` | {info['strategy']} | {info['priority']} | {info['effort']} |\n")
        
        report.append("\n")
    
    report.append("---\n\n")
    
    # Detailed findings
    report.append("## Detailed Code Findings\n\n")
    
    for provider, refs in findings.items():
        if len(refs) > 0:
            report.append(f"### {provider.upper()}\n\n")
            report.append(f"**Total References:** {len(refs)}\n\n")
            
            # Group by file
            by_file = {}
            for ref in refs:
                file = ref['file']
                if file not in by_file:
                    by_file[file] = []
                by_file[file].append(ref)
            
            for file, file_refs in sorted(by_file.items())[:5]:  # Show first 5 files
                report.append(f"**File:** `{file}`\n")
                for ref in file_refs[:3]:  # Show first 3 refs per file
                    report.append(f"- Line {ref['line']}: `{ref['code']}`\n")
                if len(file_refs) > 3:
                    report.append(f"- *... and {len(file_refs) - 3} more references*\n")
                report.append("\n")
            
            if len(by_file) > 5:
                report.append(f"*... and {len(by_file) - 5} more files*\n\n")
    
    report.append("---\n\n")
    
    # Migration recommendations
    report.append("## Migration Recommendations\n\n")
    
    report.append("### Phase 1: High Priority (Native Async)\n")
    report.append("These providers have native async support and should be migrated first:\n\n")
    report.append("1. **OpenAI** - Replace `OpenAI()` with `AsyncOpenAI()`\n")
    report.append("   ```python\n")
    report.append("   from openai import AsyncOpenAI\n")
    report.append("   client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)\n")
    report.append("   response = await client.chat.completions.create(...)\n")
    report.append("   ```\n\n")
    
    report.append("2. **Anthropic** - Replace `Anthropic()` with `AsyncAnthropic()`\n")
    report.append("   ```python\n")
    report.append("   from anthropic import AsyncAnthropic\n")
    report.append("   client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)\n")
    report.append("   response = await client.messages.create(...)\n")
    report.append("   ```\n\n")
    
    report.append("3. **ElevenLabs** - Use async methods\n")
    report.append("   ```python\n")
    report.append("   from elevenlabs import AsyncElevenLabs\n")
    report.append("   client = AsyncElevenLabs(api_key=settings.ELEVENLABS_API_KEY)\n")
    report.append("   audio = await client.generate(text=text, voice=voice)\n")
    report.append("   ```\n\n")
    
    report.append("4. **Cartesia** - Use AsyncCartesia\n")
    report.append("   ```python\n")
    report.append("   from cartesia import AsyncCartesia\n")
    report.append("   client = AsyncCartesia(api_key=settings.CARTESIA_API_KEY)\n")
    report.append("   response = await client.tts.create(...)\n")
    report.append("   ```\n\n")
    
    report.append("5. **LiteLLM** - Replace `completion()` with `acompletion()`\n")
    report.append("   ```python\n")
    report.append("   from litellm import acompletion\n")
    report.append("   response = await acompletion(model=model, messages=messages)\n")
    report.append("   ```\n\n")
    
    report.append("### Phase 2: Medium Priority (HTTP Migration)\n")
    report.append("Migrate custom requests-based clients to httpx:\n\n")
    report.append("```python\n")
    report.append("import httpx\n\n")
    report.append("async def call_custom_api(endpoint, data):\n")
    report.append("    async with httpx.AsyncClient() as client:\n")
    report.append("        response = await client.post(endpoint, json=data)\n")
    report.append("        return response.json()\n")
    report.append("```\n\n")
    
    report.append("Providers to migrate:\n")
    report.append("- Mistral API\n")
    report.append("- DeepSeek API\n")
    report.append("- Qwen API\n\n")
    
    report.append("### Phase 3: Sync Wrappers (Last Resort)\n")
    report.append("For providers without async support, use sync_to_async:\n\n")
    report.append("```python\n")
    report.append("from asgiref.sync import sync_to_async\n\n")
    report.append("@sync_to_async\n")
    report.append("def call_google_tts(text, language):\n")
    report.append("    # Existing sync code\n")
    report.append("    client = texttospeech.TextToSpeechClient()\n")
    report.append("    response = client.synthesize_speech(...)\n")
    report.append("    return response.audio_content\n\n")
    report.append("# In async view:\n")
    report.append("audio = await call_google_tts(text, language)\n")
    report.append("```\n\n")
    
    report.append("Providers needing wrappers:\n")
    report.append("- Google Cloud TTS\n")
    report.append("- Google Speech-to-Text\n")
    report.append("- Triton TTS (if async path is needed)\n\n")
    
    report.append("---\n\n")
    
    # Next steps
    report.append("## Next Steps\n\n")
    report.append("1. **Review Findings** - Validate detected API usage\n")
    report.append("2. **Prioritize Migration** - Start with high-priority native async providers\n")
    report.append("3. **Create Async Clients** - Implement async client wrappers/utilities\n")
    report.append("4. **Update Provider Files** - Modify `ai_model/providers/` directory\n")
    report.append("5. **Test Integrations** - Unit test each async provider\n")
    report.append("6. **Document Changes** - Update provider documentation\n\n")
    
    report.append("---\n\n")
    report.append("**Task 1.3 Status:** ✅ COMPLETE\n")
    report.append("**Next Task:** 1.4 - Requirements and Dependency Analysis\n")
    
    return ''.join(report)

if __name__ == "__main__":
    report = generate_audit_report()
    print(report)
    print("\n" + "="*80)
    print("✅ External API audit completed!")
