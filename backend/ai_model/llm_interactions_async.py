"""
Async LLM Interactions Module
Async versions of all LLM provider interactions for use with ASGI
"""

import os
import json
from typing import AsyncGenerator, Dict, List, Optional
from openai import AsyncOpenAI
import anthropic
import httpx

# Model constants
GPT35 = "GPT3.5"
GPT4 = "GPT4"
LLAMA2 = "LLAMA2"
GPT4OMini = "GPT4OMini"
GPT4O = "GPT4O"
GEMMA = "GEMMA"
SARVAM_M = "SARVAM_M"


def process_history(history):
    """Process conversation history - sync helper function"""
    messages = []
    for turn in history:
        user_side = {"role": "user", "content": turn["prompt"]}
        messages.append(user_side)
        system_side = {"role": "assistant", "content": turn["output"]}
        messages.append(system_side)
    return messages


# ============================================================================
# GEMINI (GOOGLE) - ASYNC
# ============================================================================

async def get_gemini_output_async(
    system_prompt: str,
    user_prompt: str,
    history: List[Dict],
    model: str,
    image_url: Optional[str] = None,
    log_context: Optional[Dict] = None
) -> AsyncGenerator[str, None]:
    """Async Gemini output streaming"""
    
    client = AsyncOpenAI(
        api_key=os.getenv("GOOGLE_API_KEY"),
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
    )

    input_items = [{"role": "system", "content": system_prompt}]
    input_items.extend(history)

    # Handle multimodal input (text + image)
    if image_url:
        user_content = [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": image_url}}
        ]
        input_items.append({"role": "user", "content": user_content})
    else:
        input_items.append({"role": "user", "content": user_prompt})

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=input_items,
            stream=True,
        )

        async for chunk in response:
            delta = chunk.choices[0].delta
            if delta and getattr(delta, "content", None):
                yield delta.content

    except Exception as e:
        from ai_model.error_logging import log_and_raise

        err_msg = str(e)
        if "InvalidRequestError" in err_msg:
            message = "Prompt violates LLM policy. Please enter a new prompt."
        elif "KeyError" in err_msg:
            message = "Invalid response from the LLM."
        else:
            message = f"An error occurred while interacting with Gemini LLM: {err_msg}"

        log_and_raise(e, model_code=model, provider='google', custom_message=message, log_context=log_context)

    finally:
        await client.close()


# ============================================================================
# GPT-5 - ASYNC
# ============================================================================

async def get_gpt5_output_async(
    system_prompt: str,
    user_prompt: str,
    history: List[Dict],
    model: str,
    image_url: Optional[str] = None,
    log_context: Optional[Dict] = None
) -> AsyncGenerator[str, None]:
    """Async GPT-5 output streaming"""
    
    client = AsyncOpenAI(
        api_key=os.getenv("OPENAI_API_KEY_GPT_5")
    )

    input_items = [{"role": "system", "content": system_prompt}]
    input_items.extend(history)

    # Handle multimodal input (text + image)
    if image_url:
        user_content = [
            {"type": "input_text", "text": user_prompt},
            {"type": "input_image", "image_url": image_url}
        ]
        input_items.append({"role": "user", "content": user_content})
    else:
        input_items.append({"role": "user", "content": user_prompt})

    request_args = {
        "model": model,
        "input": input_items,
        "text": {"verbosity": "medium"},
        "stream": True,
    }

    if model.startswith("gpt-5"):
        if model == "gpt-5-pro":
            request_args["reasoning"] = {"effort": "high"}
        else:
            request_args["reasoning"] = {"effort": "medium"}
            request_args["text"] = {"verbosity": "medium"}
    else:
        request_args["temperature"] = 0.7
        request_args["top_p"] = 0.95
        request_args["text"] = {"verbosity": "medium"}

    try:
        response = await client.responses.create(**request_args)

        async for event in response:
            if event.type == "response.output_text.delta":
                yield event.delta
            elif event.type == "response.completed":
                break

    except Exception as e:
        from ai_model.error_logging import log_and_raise

        err_msg = str(e)
        if "InvalidRequestError" in err_msg:
            message = "Prompt violates LLM policy. Please enter a new prompt."
        elif "KeyError" in err_msg:
            message = "Invalid response from the LLM."
        else:
            message = f"An error occurred while interacting with LLM: {err_msg}"

        log_and_raise(e, model_code=model, provider='openai', custom_message=message, log_context=log_context)

    finally:
        await client.close()


# ============================================================================
# GPT-4 / GPT-4O / GPT-4O-MINI - ASYNC
# ============================================================================

async def get_gpt4_output_async(
    system_prompt: str,
    user_prompt: str,
    history: List[Dict],
    model: str,
    log_context: Optional[Dict] = None
) -> AsyncGenerator[str, None]:
    """Async GPT-4 output streaming"""
    
    if model == "GPT4":
        deployment = os.getenv("LLM_INTERACTIONS_OPENAI_ENGINE_GPT_4")
    elif model == "GPT4O":
        deployment = os.getenv("LLM_INTERACTIONS_OPENAI_ENGINE_GPT_4O")
    elif model == "GPT4OMini":
        deployment = os.getenv("LLM_INTERACTIONS_OPENAI_ENGINE_GPT_4O_MINI")
    else:
        deployment = model

    client = AsyncOpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=f"{os.getenv('LLM_INTERACTIONS_OPENAI_API_BASE')}openai/deployments/{deployment}"
    )

    history_messages = history
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history_messages)
    messages.append({"role": "user", "content": user_prompt})

    try:
        response = await client.chat.completions.create(
            model=deployment,
            messages=messages,
            temperature=0.7,
            max_tokens=2048,
            top_p=0.95,
            frequency_penalty=0,
            presence_penalty=0,
            stream=True,
            extra_query={"api-version": os.getenv("LLM_INTERACTIONS_OPENAI_API_VERSION")},
        )

        async for chunk in response:
            if hasattr(chunk, 'choices') and chunk.choices:
                if hasattr(chunk.choices[0], 'delta') and hasattr(chunk.choices[0].delta, 'content'):
                    content = chunk.choices[0].delta.content
                    if content is not None:
                        yield content

    except Exception as e:
        from ai_model.error_logging import log_and_raise

        err_msg = str(e)
        if "InvalidRequestError" in err_msg:
            message = "Prompt violates LLM policy. Please enter a new prompt."
        elif "KeyError" in err_msg:
            message = "Invalid response from the LLM"
        else:
            message = f"An error occurred while interacting with LLM: {err_msg}"

        log_and_raise(e, model_code=model, provider='openai', custom_message=message, log_context=log_context)

    finally:
        await client.close()


# ============================================================================
# GPT-3.5 - ASYNC
# ============================================================================

async def get_gpt3_output_async(
    system_prompt: str,
    user_prompt: str,
    history: List[Dict],
    log_context: Optional[Dict] = None
) -> AsyncGenerator[str, None]:
    """Async GPT-3.5 output streaming"""
    
    model = os.getenv("LLM_INTERACTIONS_OPENAI_ENGINE_GPT35")

    client = AsyncOpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=f"{os.getenv('LLM_INTERACTIONS_OPENAI_API_BASE')}openai/deployments/{model}"
    )

    history_messages = history
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history_messages)
    messages.append({"role": "user", "content": user_prompt})

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=2048,
            top_p=0.95,
            frequency_penalty=0,
            presence_penalty=0,
            stream=True,
            extra_query={"api-version": os.getenv("LLM_INTERACTIONS_OPENAI_API_VERSION")},
        )

        async for chunk in response:
            if hasattr(chunk, 'choices') and chunk.choices:
                if hasattr(chunk.choices[0], 'delta') and hasattr(chunk.choices[0].delta, 'content'):
                    content = chunk.choices[0].delta.content
                    if content is not None:
                        yield content

    except Exception as e:
        from ai_model.error_logging import log_and_raise

        err_msg = str(e)
        if "InvalidRequestError" in err_msg:
            message = "Prompt violates LLM policy. Please enter a new prompt."
        elif "KeyError" in err_msg:
            message = "Invalid response from the LLM"
        else:
            message = f"An error occurred while interacting with LLM: {err_msg}"

        log_and_raise(e, model_code='gpt-3.5-turbo', provider='openai', custom_message=message, log_context=log_context)

    finally:
        await client.close()


# ============================================================================
# ANTHROPIC (CLAUDE) - ASYNC
# ============================================================================

async def get_anthropic_output_async(
    system_prompt: str,
    user_prompt: str,
    history: List[Dict],
    model: str,
    image_url: Optional[str] = None,
    log_context: Optional[Dict] = None
) -> AsyncGenerator[str, None]:
    """Async Anthropic Claude output streaming"""
    
    client = anthropic.AsyncAnthropic(
        api_key=os.getenv("ANTHROPIC_API_KEY")
    )
    
    enable_thinking = model.endswith("-thinking")
    api_model = model.replace("-thinking", "") if enable_thinking else model

    messages = []
    messages.extend(history)

    if image_url:
        user_content = [
            {"type": "text", "text": user_prompt},
            {
                "type": "image",
                "source": {
                    "type": "url",
                    "url": image_url
                }
            }
        ]
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": user_prompt})

    try:
        stream_params = {
            "model": api_model,
            "system": system_prompt,
            "messages": messages,
        }

        if enable_thinking:
            stream_params["max_tokens"] = 16384
            stream_params["thinking"] = {
                "type": "enabled",
                "budget_tokens": 8192
            }
        else:
            stream_params["max_tokens"] = 8192

        async with client.messages.stream(**stream_params) as stream:
            in_thinking_block = False
            async for event in stream:
                if event.type == "content_block_start":
                    if hasattr(event.content_block, 'type') and event.content_block.type == "thinking":
                        in_thinking_block = True
                        yield "<think>"
                elif event.type == "content_block_stop":
                    if in_thinking_block:
                        yield "</think>"
                        in_thinking_block = False
                elif event.type == "content_block_delta":
                    if hasattr(event.delta, 'thinking'):
                        yield event.delta.thinking
                    elif hasattr(event.delta, 'text'):
                        yield event.delta.text

    except Exception as e:
        from ai_model.error_logging import log_and_raise

        err_msg = str(e)
        if "invalid_request_error" in err_msg.lower():
            message = "Prompt violates LLM policy. Please enter a new prompt."
        elif "KeyError" in err_msg:
            message = "Invalid response from the LLM"
        else:
            message = f"An error occurred while interacting with Anthropic LLM: {err_msg}"

        log_and_raise(e, model_code=model, provider='anthropic', custom_message=message, log_context=log_context)

    finally:
        await client.close()


# ============================================================================
# DEEPINFRA - ASYNC
# ============================================================================

async def get_deepinfra_output_async(
    system_prompt: str,
    user_prompt: str,
    history: List[Dict],
    model: str,
    image_url: Optional[str] = None,
    log_context: Optional[Dict] = None
) -> AsyncGenerator[str, None]:
    """Async DeepInfra output streaming"""
    
    client = AsyncOpenAI(
        api_key=os.getenv("DEEPINFRA_API_KEY"),
        base_url=os.getenv("DEEPINFRA_BASE_URL")
    )

    history_messages = history
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history_messages)

    # Handle multimodal input (text + image)
    if image_url:
        user_content = [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": image_url}}
        ]
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": user_prompt})

    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=2048,
            stream=True,
        )

        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content is not None:
                yield content

    except Exception as e:
        from ai_model.error_logging import log_and_raise

        err_msg = str(e)
        if "InvalidRequestError" in err_msg:
            message = "Prompt violates LLM policy. Please enter a new prompt."
        elif "KeyError" in err_msg:
            message = "Invalid response from the LLM"
        else:
            message = f"An error occurred while interacting with LLM: {err_msg}"

        log_and_raise(e, model_code=model, provider='deepinfra', custom_message=message, log_context=log_context)

    finally:
        await client.close()


# ============================================================================
# LLAMA2 - ASYNC (using httpx)
# ============================================================================

async def get_llama2_output_async(
    system_prompt: str,
    conv_history: List[Dict],
    user_prompt: str,
    log_context: Optional[Dict] = None
) -> str:
    """Async Llama2 output (non-streaming)"""
    
    api_base = os.getenv("LLM_INTERACTION_LLAMA2_API_BASE")
    token = os.getenv("LLM_INTERACTION_LLAMA2_API_TOKEN")
    url = f"{api_base}/chat/completions"

    history = process_history(conv_history)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_prompt})

    body = {
        "model": "meta-llama/Llama-2-70b-chat-hf",
        "messages": messages,
        "temperature": 0.2,
        "max_new_tokens": 500,
        "top_p": 1,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                json=body
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
    
    except Exception as e:
        from ai_model.error_logging import log_and_raise
        log_and_raise(e, model_code='llama-2-70b', provider='meta', log_context=log_context)


# ============================================================================
# SARVAM-M - ASYNC (using httpx)
# ============================================================================

async def get_sarvam_m_output_async(
    system_prompt: str,
    conv_history: List[Dict],
    user_prompt: str,
    log_context: Optional[Dict] = None
) -> str:
    """Async Sarvam-M output (non-streaming)"""
    
    api_base = os.getenv("SARVAM_M_API_BASE")
    api_key = os.getenv("SARVAM_M_API_KEY")
    url = f"{api_base}/chat/completions"

    headers = {
        "api-subscription-key": api_key,
        "Content-Type": "application/json"
    }

    history = conv_history
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    
    if type(user_prompt) == list:
        messages.append({"role": "user", "content": user_prompt[0]['text']})
    else:
        messages.append({"role": "user", "content": user_prompt})

    body = {
        "model": "sarvam-m",
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 2048,
        "top_p": 1,
    }
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()
            response_data = response.json()
            return response_data["choices"][0]["message"]["content"].strip()
    
    except httpx.RequestError as e:
        from ai_model.error_logging import log_and_raise
        print(f"An error occurred during the API request: {e}")
        log_and_raise(e, model_code='sarvam-m', provider='sarvam', custom_message=f"Sarvam API request failed: {e}", log_context=log_context)
    
    except (KeyError, IndexError) as e:
        from ai_model.error_logging import log_and_raise
        print(f"Error parsing the API response: {e}")
        log_and_raise(e, model_code='sarvam-m', provider='sarvam', custom_message=f"Sarvam API response parsing error: {e}", log_context=log_context)


# ============================================================================
# IBM WATSONX - ASYNC (using litellm - needs async wrapper)
# ============================================================================

async def get_ibm_output_async(
    system_prompt: str,
    user_prompt: str,
    history: List[Dict],
    model: str,
    log_context: Optional[Dict] = None
) -> AsyncGenerator[str, None]:
    """Async IBM WatsonX output streaming"""
    
    # Note: litellm doesn't have native async support for streaming
    # We'll use asyncio to wrap it
    from litellm import completion
    import asyncio

    history_messages = history
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history_messages)
    messages.append({"role": "user", "content": user_prompt})

    try:
        # Run litellm in thread pool since it's sync
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: completion(
                model="watsonx/" + model,
                project_id=os.getenv("IBM_WATSONX_PROJECT_ID"),
                messages=messages,
                stream=True,
            )
        )

        for chunk in response:
            if hasattr(chunk, 'choices') and chunk.choices:
                if hasattr(chunk.choices[0], 'delta') and hasattr(chunk.choices[0].delta, 'content'):
                    content = chunk.choices[0].delta.content
                    if content is not None:
                        yield content

    except Exception as e:
        from ai_model.error_logging import log_and_raise

        err_msg = str(e)
        if "InvalidRequestError" in err_msg:
            message = "Prompt violates LLM policy. Please enter a new prompt."
        elif "KeyError" in err_msg:
            message = "Invalid response from the LLM"
        else:
            message = f"An error occurred while interacting with LLM: {err_msg}"

        log_and_raise(e, model_code=model, provider='ibm', custom_message=message, log_context=log_context)


# ============================================================================
# MAIN ASYNC ROUTER FUNCTION
# ============================================================================

async def get_model_output_async(
    system_prompt: str,
    user_prompt: str,
    history: List[Dict],
    model: str = GPT4OMini,
    image_url: Optional[str] = None,
    audio_url: Optional[str] = None,
    **kwargs
) -> AsyncGenerator[str, None]:
    """
    Main async router function for all LLM providers
    
    Usage:
        async for chunk in get_model_output_async(system_prompt, user_prompt, history, model):
            print(chunk, end='', flush=True)
    """
    
    log_context = kwargs.get('context')
    
    if model == GPT35:
        async for chunk in get_gpt3_output_async(system_prompt, user_prompt, history, log_context=log_context):
            yield chunk
    
    elif model.startswith("gpt"):
        async for chunk in get_gpt5_output_async(system_prompt, user_prompt, history, model, image_url=image_url, log_context=log_context):
            yield chunk
    
    elif model == LLAMA2:
        # Non-streaming
        result = await get_llama2_output_async(system_prompt, history, user_prompt, log_context=log_context)
        yield result
    
    elif model == SARVAM_M:
        # Non-streaming
        result = await get_sarvam_m_output_async(system_prompt, history, user_prompt, log_context=log_context)
        yield result
    
    elif model.startswith("gemini"):
        async for chunk in get_gemini_output_async(system_prompt, user_prompt, history, model, image_url=image_url, log_context=log_context):
            yield chunk
    
    elif model.startswith("ibm"):
        async for chunk in get_ibm_output_async(system_prompt, user_prompt, history, model, log_context=log_context):
            yield chunk
    
    elif model.startswith("claude"):
        async for chunk in get_anthropic_output_async(system_prompt, user_prompt, history, model, image_url=image_url, log_context=log_context):
            yield chunk
    
    else:
        # Default to DeepInfra
        async for chunk in get_deepinfra_output_async(system_prompt, user_prompt, history, model, image_url=image_url, log_context=log_context):
            yield chunk


# ============================================================================
# BATCH ASYNC FUNCTION (for model comparison)
# ============================================================================

async def get_all_model_output_async(
    system_prompt: str,
    user_prompt: str,
    history: List[Dict],
    models_to_run: List[str],
    log_context: Optional[Dict] = None
) -> Dict[str, str]:
    """
    Run multiple models concurrently and return results
    
    Usage:
        results = await get_all_model_output_async(
            system_prompt, user_prompt, history,
            models_to_run=["GPT4O", "claude-3-opus", "gemini-pro"]
        )
    """
    import asyncio
    
    async def get_single_model_output(model: str) -> tuple:
        """Helper to get output from single model"""
        model_history = next(
            (entry["interaction_json"] for entry in history if entry.get("model_name") == model),
            []
        )
        
        full_output = ""
        try:
            async for chunk in get_model_output_async(
                system_prompt, user_prompt, model_history, model, context=log_context
            ):
                full_output += chunk
        except Exception as e:
            full_output = f"Error: {str(e)}"
        
        return (model, full_output)
    
    # Run all models concurrently
    tasks = [get_single_model_output(model) for model in models_to_run]
    results_list = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Convert to dict
    results = {}
    for item in results_list:
        if isinstance(item, tuple):
            model, output = item
            results[model] = output
        else:
            # Handle exception
            results["error"] = str(item)
    
    return results
