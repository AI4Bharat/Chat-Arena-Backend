# API Migration Strategy Matrix

## Quick Reference

| Provider | Current Status | Async Ready | Action Required | Estimated Effort |
|----------|----------------|-------------|-----------------|------------------|
| OpenAI | Sync | ✅ Yes | Replace with AsyncOpenAI | 1-2 hours |
| Anthropic | Sync | ✅ Yes | Replace with AsyncAnthropic | 1-2 hours |
| ElevenLabs | Sync | ✅ Yes | Use async methods | 1-2 hours |
| Cartesia | Sync | ✅ Yes | Replace with AsyncCartesia | 1-2 hours |
| LiteLLM | Sync | ✅ Yes | Use acompletion() | 1 hour |
| Google Gemini | Sync | ⚠️ Partial | Test async or wrap | 2-4 hours |
| Google TTS | Sync | ❌ No | Wrap with sync_to_async | 1 hour |
| Google STT | Sync | ❌ No | Wrap with sync_to_async | 1 hour |
| Mistral | Sync (requests) | ❌ No | Migrate to httpx | 2-3 hours |
| DeepSeek | Sync (requests) | ❌ No | Migrate to httpx | 2-3 hours |
| Qwen | Sync (requests) | ❌ No | Migrate to httpx | 2-3 hours |
| Meta/Llama | Via LiteLLM | ✅ Yes | Use litellm.acompletion | 1 hour |
| Triton | Sync | ❌ No | Keep sync (low priority) | N/A |

## Total Estimated Effort
- **High Priority (Native Async):** 8-12 hours
- **Medium Priority (HTTP Migration):** 6-9 hours  
- **Low Priority (Wrappers):** 2-3 hours
- **Total:** 16-24 hours

## Implementation Order

### Week 1: Native Async (Core LLMs)
1. OpenAI → AsyncOpenAI
2. Anthropic → AsyncAnthropic
3. LiteLLM → acompletion()

### Week 2: Native Async (TTS)
4. ElevenLabs → async methods
5. Cartesia → AsyncCartesia

### Week 3: HTTP Migration
6. Mistral → httpx.AsyncClient
7. DeepSeek → httpx.AsyncClient
8. Qwen → httpx.AsyncClient

### Week 4: Wrappers & Testing
9. Google TTS → sync_to_async
10. Google STT → sync_to_async
11. Integration testing
12. Load testing

---

**Status:** Ready for Phase 3 (Async Code Conversion)
