import os

# https://pypi.org/project/openai/
# import openai
# from django.http import JsonResponse
# from transformers import AutoTokenizer, AutoModelForSeq2SeqLM


# def generate_response_from_gpt(gpt_prompt):
#     messages = []
#     for prompt in gpt_prompt:
#         messages.append({"role": "user", "content": prompt})
#     organisation_key = os.getenv("organisation_key")
#     openai.api_key = os.getenv("api_key_gpt_3.5")
#     client = OpenAI(api_key=openai.api_key, organization=organisation_key)
#     response = client.chat.completions.create(
#         model="gpt-3.5-turbo",
#         messages=messages
#     )
#     return response.choices[0].message.content.strip()


# import langdetect
#
# def check_language_consistency(texts, target_language):
#     """
#     Checks if all paragraphs/sentences in the given text are in the same language.
#
#     Args:
#         texts (list): A list of paragraphs or sentences to check.
#         target_language (str): The language code to check against (e.g., 'en', 'fr', 'es').
#
#     Returns:
#         bool: True if all texts are in the target language, False otherwise.
#     """
#     try:
#         detected_languages = set(langdetect.detect(text) for text in texts)
#         return len(detected_languages) == 1 and target_language in detected_languages
#     except langdetect.lang_detect_exception.LangDetectException:
#         return False


import re
from openai import OpenAI
import anthropic
import requests
from rest_framework import status
from rest_framework.response import Response
from litellm import completion

GPT35 = "GPT3.5"
GPT4 = "GPT4"
LLAMA2 = "LLAMA2"
GPT4OMini = "GPT4OMini"
GPT4O = "GPT4O"
GEMMA = "GEMMA"
SARVAM_M = "SARVAM_M"

def process_history(history):
    messages = []
    for turn in history:
        user_side = {"role": "user", "content": turn["prompt"]}
        messages.append(user_side)
        system_side = {"role": "assistant", "content": turn["output"]}
        messages.append(system_side)
    return messages

def get_gemini_output(system_prompt, user_prompt, history, model, image_url=None, log_context=None):
    client = OpenAI(
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
        response = client.chat.completions.create(
            model=model,
            messages=input_items,
            stream=True,
        )

        for chunk in response:
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
        
        # Log to GCS before raising
        log_and_raise(e, model_code=model, provider='google', custom_message=message, log_context=log_context)

def get_gpt5_output(system_prompt, user_prompt, history, model, image_url=None, log_context=None):
    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY_GPT_5")
    )

    input_items = [{"role": "system", "content": system_prompt}]
    input_items.extend(history)
    
    # Handle multimodal input (text + image)
    if image_url:
        user_content = [
            {"type": "input_text", "text": user_prompt},
            {"type": "input_image", "image_url": image_url}  # Direct string, not object!
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
        response = client.responses.create(**request_args)

        for event in response:
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
        
        # Log to GCS before raising
        log_and_raise(e, model_code=model, provider='openai', custom_message=message, log_context=log_context)

def get_gpt4_output(system_prompt, user_prompt, history, model, log_context=None):
    if model == "GPT4":
        deployment = os.getenv("LLM_INTERACTIONS_OPENAI_ENGINE_GPT_4")
    elif model == "GPT4O":
        deployment = os.getenv("LLM_INTERACTIONS_OPENAI_ENGINE_GPT_4O")
    elif model == "GPT4OMini":
        deployment = os.getenv("LLM_INTERACTIONS_OPENAI_ENGINE_GPT_4O_MINI")
    else:
        deployment = model
    
    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=f"{os.getenv('LLM_INTERACTIONS_OPENAI_API_BASE')}openai/deployments/{deployment}"
    )

    history_messages = history
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history_messages)
    messages.append({"role": "user", "content": user_prompt})

    try:
        response = client.chat.completions.create(
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
        
        # Log to GCS before raising
        log_and_raise(e, model_code=model, provider='openai', custom_message=message, log_context=log_context)

def get_gpt3_output(system_prompt, user_prompt, history, log_context=None):
    model = os.getenv("LLM_INTERACTIONS_OPENAI_ENGINE_GPT35")

    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=f"{os.getenv('LLM_INTERACTIONS_OPENAI_API_BASE')}openai/deployments/{model}"
    )

    history_messages = history
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history_messages)
    messages.append({"role": "user", "content": user_prompt})

    try:
        response = client.chat.completions.create(
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
        
        # Log to GCS before raising
        log_and_raise(e, model_code='gpt-3.5-turbo', provider='openai', custom_message=message, log_context=log_context)

def get_llama2_output(system_prompt, conv_history, user_prompt, log_context=None):
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
    s = requests.Session()
    try:
        result = s.post(url, headers={"Authorization": f"Bearer {token}"}, json=body)
        return result.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        from ai_model.error_logging import log_and_raise
        log_and_raise(e, model_code='llama-2-70b', provider='meta', log_context=log_context)

def get_sarvam_m_output(system_prompt, conv_history, user_prompt, log_context=None):
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
        # "stream": True
    }
    
    try:
        s = requests.Session()
        response = s.post(url, headers=headers, json=body)
        response.raise_for_status() 
        response_data = response.json()
        return response_data["choices"][0]["message"]["content"].strip()
    except requests.exceptions.RequestException as e:
        from ai_model.error_logging import log_and_raise
        print(f"An error occurred during the API request: {e}")
        log_and_raise(e, model_code='sarvam-m', provider='sarvam', custom_message=f"Sarvam API request failed: {e}", log_context=log_context)
    except (KeyError, IndexError) as e:
        from ai_model.error_logging import log_and_raise
        print(f"Error parsing the API response: {e}")
        print(f"Full response data: {response_data}")
        log_and_raise(e, model_code='sarvam-m', provider='sarvam', custom_message=f"Sarvam API response parsing error: {e}", log_context=log_context)

def get_deepinfra_output(system_prompt, user_prompt, history, model, image_url=None, log_context=None):
    try:
        client = OpenAI(
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

        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=2048,
            stream=True,
        )

        for chunk in stream:
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
        
        # Log to GCS before raising
        log_and_raise(e, model_code=model, provider='deepinfra', custom_message=message, log_context=log_context)
    
def get_ibm_output(system_prompt, user_prompt, history, model, log_context=None):
    history_messages = history
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history_messages)
    messages.append({"role": "user", "content": user_prompt})

    try:
        response = completion(
            model="watsonx/"+model,
            project_id=os.getenv("IBM_WATSONX_PROJECT_ID"),
            messages=messages,
            stream=True,
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
        
        # Log to GCS before raising
        log_and_raise(e, model_code=model, provider='ibm', custom_message=message, log_context=log_context)

def get_anthropic_output(system_prompt, user_prompt, history, model, image_url=None, log_context=None):
    client = anthropic.Anthropic(
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

        with client.messages.stream(**stream_params) as stream:
            in_thinking_block = False
            for event in stream:
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

        # Log to GCS before raising
        log_and_raise(e, model_code=model, provider='anthropic', custom_message=message, log_context=log_context)
    
def get_model_output(system_prompt, user_prompt, history, model=GPT4OMini, image_url=None, audio_url=None, **kwargs):
    # Assume that translation happens outside (and the prompt is already translated)
    # audio_url parameter reserved for future native audio API integration
    log_context = kwargs.get('context')
    
    # Check if this is an image generation request
    is_generation_request = detect_image_generation_intent(user_prompt)
    
    if is_generation_request:
        # Route to image generation based on model provider
        if model.startswith("gpt-5") or model.startswith("gpt-4"):
            # Use GPT Responses API with image_generation tool
            return generate_image_with_gpt5(user_prompt, model=model, log_context=log_context)
        elif model.startswith("gemini"):
            # Use Gemini built-in generation
            return generate_image_with_gemini(user_prompt, model, history, log_context=log_context)
        elif "imagen" in model:
            # Use dedicated Imagen API
            return generate_image_with_imagen(user_prompt, model=model, log_context=log_context)
        else:
            # Model doesn't support generation - fallback to text response
            pass
    
    # Standard text generation (existing logic)
    out = ""
    if model == GPT35:
        out = get_gpt3_output(system_prompt, user_prompt, history, log_context=log_context)
    elif model.startswith("gpt"):
        out = get_gpt5_output(system_prompt, user_prompt, history, model, image_url=image_url, log_context=log_context)
    elif model == LLAMA2:
        out = get_llama2_output(system_prompt, history, user_prompt, log_context=log_context)
    elif model == SARVAM_M:
        out = get_sarvam_m_output(system_prompt, history, user_prompt, log_context=log_context)
    elif model.startswith("gemini"):
        out = get_gemini_output(system_prompt, user_prompt, history, model, image_url=image_url, log_context=log_context)
    elif model.startswith("ibm"):
        out = get_ibm_output(system_prompt, user_prompt, history, model, log_context=log_context)
    elif model.startswith("claude"):
        out = get_anthropic_output(system_prompt, user_prompt, history, model, image_url=image_url, log_context=log_context)
    else:
        out = get_deepinfra_output(system_prompt, user_prompt, history, model, image_url=image_url, log_context=log_context)
    return out

def get_all_model_output(system_prompt, user_prompt, history, models_to_run, log_context=None):
    results = {}

    for model in models_to_run:
        model_history = next(
            (entry["interaction_json"] for entry in history if entry.get("model_name") == model),
            []
        )
        if model == GPT35:
            results[model] = get_gpt3_output(system_prompt, user_prompt, model_history, log_context=log_context)
        elif model in [GPT4, GPT4O, GPT4OMini]:
            results[model] = get_gpt4_output(system_prompt, user_prompt, model_history, model, log_context=log_context)
        elif model == "GPT5":
            results[model] = get_gpt5_output(system_prompt, user_prompt, model_history, log_context=log_context)
        elif model == LLAMA2:
            results[model] = get_llama2_output(system_prompt, model_history, user_prompt, log_context=log_context)
        elif model == SARVAM_M:
            results[model] = get_sarvam_m_output(system_prompt, model_history, user_prompt, log_context=log_context)
        else:
            results[model] = get_deepinfra_output(system_prompt, user_prompt, model_history, model, log_context=log_context)

    return results


# ==================== IMAGE GENERATION FUNCTIONS ====================

def detect_image_generation_intent(prompt):
    """
    Detects if a user prompt is requesting image generation.
    Returns True if generation keywords are found.
    """
    generation_keywords = [
        'generate image', 'create image', 'make image', 'draw', 'paint', 
        'sketch', 'illustrate', 'design', 'render', 'visualize',
        'generate photo', 'create photo', 'make photo', 'picture of',
        'show me', 'image of', 'photo of', 'illustration of'
    ]
    prompt_lower = prompt.lower()
    return any(keyword in prompt_lower for keyword in generation_keywords)


def generate_image_with_gpt5(prompt, model='gpt-5', quality='auto', size='auto', format='png', log_context=None):
    """
    Generate images using OpenAI's GPT Image API.
    Routes any GPT model request to the appropriate image generation model.
    
    Args:
        prompt: Text description of image to generate (max 32000 chars for GPT image models)
        model: Model code (gpt-5, gpt-5.2, gpt-4, etc.) - will be mapped to gpt-image-1.5
        quality: 'high', 'medium', 'low', or 'auto' (default)
        size: '1024x1024', '1536x1024', '1024x1536', or 'auto' (default)
        format: 'png', 'jpeg', or 'webp' (output_format param NOT used for GPT image models - they always return b64)
        log_context: Error logging context
        
    Yields:
        Dict with 'type' and 'data' for final image
    """
    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY_GPT_5")
    )

    try:
        # Yield initial generating event to show loading UI
        yield {
            "type": "generating",
            "message": "Generating image..."
        }
        
        # Map chat models to GPT Image model (latest is gpt-image-1.5)
        image_model = "gpt-image-1.5"
        
        # Use OpenAI's Image API endpoint with correct parameters
        # NOTE: GPT image models ALWAYS return base64-encoded images, not URLs
        # output_format parameter is NOT supported for GPT image models (only for DALL-E)
        # They automatically return base64 encoded images
        response = client.images.generate(
            model=image_model,
            prompt=prompt,
            size=size if size != 'auto' else None,  # Let API choose if auto
            quality=quality if quality != 'auto' else None,  # Let API choose if auto
            n=1  # Generate 1 image
        )

        # Extract the base64 image from response
        if response.data and len(response.data) > 0:
            image_b64 = response.data[0].b64_json
            
            yield {
                "type": "final_image",
                "data": image_b64,  # Base64 encoded image
                "format": format,
                "size": size,
                "model_used": image_model,
                "is_base64": True,
            }
        else:
            yield {
                "type": "error",
                "message": "No image generated from API"
            }

    except Exception as e:
        # Yield error dict instead of raising - allows graceful handling in views.py
        error_message = str(e)
        print(f"Error generating image with GPT: {error_message}")
        yield {
            "type": "error",
            "message": error_message
        }


def generate_image_with_imagen(prompt, model='imagen-4.0-generate-001', number_of_images=1, 
                                 aspect_ratio='1:1', size='1K', log_context=None):
    """
    Generate images using Google Imagen 4 models.
    
    Args:
        prompt: Text description (max 480 tokens)
        model: 'imagen-4.0-generate-001', 'imagen-4.0-ultra-generate-001', 'imagen-4.0-fast-generate-001'
        number_of_images: 1-4 images per request
        aspect_ratio: '1:1', '3:4', '4:3', '9:16', '16:9'
        size: '1K' or '2K' (2K only for standard/ultra)
        log_context: Error logging context
        
    Yields:
        Dict with 'type' and 'data' for each generated image
    """
    try:
        # Using Vertex AI client
        from google.cloud import aiplatform
        from vertexai.preview import vision_models
        
        # Initialize with project credentials
        aiplatform.init(
            project=os.getenv("GOOGLE_CLOUD_PROJECT_ID"),
            location=os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
        )
        
        imagen_model = vision_models.ImageGenerationModel.from_pretrained(model)
        
        response = imagen_model.generate_images(
            prompt=prompt,
            number_of_images=number_of_images,
            aspect_ratio=aspect_ratio,
            safety_filter_level="block_some",
            person_generation="allow_adult"
        )
        
        for idx, image in enumerate(response.images):
            # Image objects have ._pil_image attribute
            yield {
                "type": "final_image",
                "data": image._pil_image,  # PIL Image object
                "index": idx,
                "model": model,
                "aspect_ratio": aspect_ratio
            }
            
    except Exception as e:
        from ai_model.error_logging import log_and_raise
        message = f"Error generating image with Imagen: {str(e)}"
        log_and_raise(e, model_code=model, provider='google', custom_message=message, log_context=log_context)


def generate_image_with_gemini(prompt, model, history, log_context=None):
    """
    Generate images using Google's Imagen 4 (dedicated image generation model).
    Although Gemini can generate images, we use Imagen 4 for specialized image generation.
    
    Args:
        prompt: Text description (max 480 tokens)
        model: Gemini model code (mapped to Imagen internally)
        history: Conversation history (not used for image generation)
        log_context: Error logging context
        
    Yields:
        Dict with 'type' and 'data' for each generated image
    """
    try:
        # Import Vertex AI
        import google.generativeai as genai
        
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        
        # Use Imagen 4 for specialized image generation
        imagen_model = genai.ImageGenerationModel("imagen-3.0-generate-001")
        
        response = imagen_model.generate_images(
            prompt=prompt,
            number_of_images=1,
            aspect_ratio="1:1",
            safety_filter_level="block_some",
        )
        
        for idx, image in enumerate(response.images):
            # Images are PIL Image objects
            yield {
                "type": "final_image",
                "data": image,  # PIL Image object
                "index": idx,
                "model": "imagen-3.0-generate-001",
            }
            
    except Exception as e:
        from ai_model.error_logging import log_and_raise
        message = f"Error generating image with Gemini/Imagen: {str(e)}"
        log_and_raise(e, model_code=model, provider='google', custom_message=message, log_context=log_context)