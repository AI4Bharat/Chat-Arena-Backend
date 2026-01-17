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

def get_gemini_output(system_prompt, user_prompt, history, model, image_url=None, context):
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
        log_and_raise(e, model_code=model, provider='google', custom_message=message, context=context)

def get_gpt5_output(system_prompt, user_prompt, history, model, image_url=None, context):
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
        log_and_raise(e, model_code=model, provider='openai', custom_message=message, context=context)

def get_gpt4_output(system_prompt, user_prompt, history, model, context):
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
        log_and_raise(e, model_code=model, provider='openai', custom_message=message, context=context)

def get_gpt3_output(system_prompt, user_prompt, history, context):
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
        log_and_raise(e, model_code='gpt-3.5-turbo', provider='openai', custom_message=message, context=context)

def get_llama2_output(system_prompt, conv_history, user_prompt, context):
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
        log_and_raise(e, model_code='llama-2-70b', provider='meta', context=context)

def get_sarvam_m_output(system_prompt, conv_history, user_prompt, context):
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
        log_and_raise(e, model_code='sarvam-m', provider='sarvam', custom_message=f"Sarvam API request failed: {e}", context=context)
    except (KeyError, IndexError) as e:
        from ai_model.error_logging import log_and_raise
        print(f"Error parsing the API response: {e}")
        print(f"Full response data: {response_data}")
        log_and_raise(e, model_code='sarvam-m', provider='sarvam', custom_message=f"Sarvam API response parsing error: {e}", context=context)

def get_deepinfra_output(system_prompt, user_prompt, history, model, image_url=None, context):
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
        log_and_raise(e, model_code=model, provider='deepinfra', custom_message=message, context=context)
    
def get_ibm_output(system_prompt, user_prompt, history, model, context):
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
        log_and_raise(e, model_code=model, provider='ibm', custom_message=message, context=context)
    
def get_model_output(system_prompt, user_prompt, history, model=GPT4OMini, image_url=None, audio_url=None, **kwargs):
    # Assume that translation happens outside (and the prompt is already translated)
    # audio_url parameter reserved for future native audio API integration
    context = kwargs.get('context')
    out = ""
    if model == GPT35:
        out = get_gpt3_output(system_prompt, user_prompt, history, context=context)
    elif model.startswith("gpt"):
        out = get_gpt5_output(system_prompt, user_prompt, history, model, image_url=image_url, context=context)
    elif model == LLAMA2:
        out = get_llama2_output(system_prompt, history, user_prompt, context=context)
    elif model == SARVAM_M:
        out = get_sarvam_m_output(system_prompt, history, user_prompt, context=context)
    elif model.startswith("gemini"):
        out = get_gemini_output(system_prompt, user_prompt, history, model, image_url=image_url, context=context)
    elif model.startswith("ibm"):
        out = get_ibm_output(system_prompt, user_prompt, history, model, context=context)
    else:
        out = get_deepinfra_output(system_prompt, user_prompt, history, model, image_url=image_url, context=context)
    return out

def get_all_model_output(system_prompt, user_prompt, history, models_to_run, context):
    results = {}

    for model in models_to_run:
        model_history = next(
            (entry["interaction_json"] for entry in history if entry.get("model_name") == model),
            []
        )
        if model == GPT35:
            results[model] = get_gpt3_output(system_prompt, user_prompt, model_history, context=context)
        elif model in [GPT4, GPT4O, GPT4OMini]:
            results[model] = get_gpt4_output(system_prompt, user_prompt, model_history, model, context=context)
        elif model == "GPT5":
            results[model] = get_gpt5_output(system_prompt, user_prompt, model_history, context=context)
        elif model == LLAMA2:
            results[model] = get_llama2_output(system_prompt, model_history, user_prompt, context=context)
        elif model == SARVAM_M:
            results[model] = get_sarvam_m_output(system_prompt, model_history, user_prompt, context=context)
        else:
            results[model] = get_deepinfra_output(system_prompt, user_prompt, model_history, model, context=context)

    return results