import os
import io
import requests
import base64
from openai import OpenAI
from rest_framework.response import Response
from rest_framework import status
from ai_model.error_logging import log_and_raise

LANG_CODE_TO_NAME = {
    "hi": "Hindi", "mr": "Marathi", "ta": "Tamil", "te": "Telugu",
    "kn": "Kannada", "gu": "Gujarati", "pa": "Punjabi", "bn": "Bengali",
    "ml": "Malayalam", "as": "Assamese", "brx": "Bodo", "doi": "Dogri",
    "ks": "Kashmiri", "mai": "Maithili", "mni": "Manipuri", "ne": "Nepali",
    "or": "Odia", "sd": "Sindhi", "si": "Sinhala", "ur": "Urdu",
    "sat": "Santali", "sa": "Sanskrit", "gom": "Konkani", "en": "English",
}

def get_gemini_asr_output(audio_url, lang, model, log_context=None):
    try:
        audio_response = requests.get(audio_url, timeout=60)
        audio_response.raise_for_status()
        audio_data = audio_response.content
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')

        language_name = LANG_CODE_TO_NAME.get(lang, lang)

        transcription_prompt = f"Transcribe the following audio accurately. The audio is in {language_name} language. Return only the transcription text without any additional commentary, explanations, or formatting."

        client = OpenAI(
            api_key=os.getenv("GOOGLE_API_KEY"),
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )

        user_content = [
            {"type": "text", "text": transcription_prompt},
            {"type": "input_audio", "input_audio": {"data": audio_base64, "format": "wav"}}
        ]

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": user_content}],
            temperature=0.1,
        )

        transcript = response.choices[0].message.content.strip()
        return transcript

    except Exception as e:
        log_and_raise(e, model_code=model, provider='google', custom_message=f"Gemini ASR error: {str(e)}", log_context=log_context)


def get_openai_asr_output(audio_url, lang, model, log_context=None):
    api_key = os.getenv("OPENAI_API_KEY_GPT_5", "")

    try:
        audio_response = requests.get(audio_url, timeout=60)
        audio_response.raise_for_status()
        audio_data = audio_response.content

        audio_file = io.BytesIO(audio_data)
        audio_file.name = "audio.wav"

        client = OpenAI(api_key=api_key)

        transcription = client.audio.transcriptions.create(
            model=model,
            file=audio_file,
            language=lang if lang != "en" else None,
            response_format="text"
        )

        return transcription.strip() if isinstance(transcription, str) else transcription.text.strip()

    except Exception as e:
        log_and_raise(e, model_code=model, provider='openai', custom_message=f"OpenAI ASR error: {str(e)}", log_context=log_context)


def get_sarvam_asr_output(audio_url, lang, model, log_context=None):
    api_key = os.getenv("SARVAM_M_API_KEY", "")
    try:
        audio_response = requests.get(audio_url, timeout=60)
        audio_response.raise_for_status()
        audio_data = audio_response.content

        lang_code = "od" if lang == "or" else lang
        language_code = f"{lang_code}-IN"

        files = {
            "file": ("audio.wav", audio_data, "audio/wav")
        }
        data = {
            "model": model,
            "language_code": language_code
        }

        response = requests.post(
            "https://api.sarvam.ai/speech-to-text",
            headers={"api-subscription-key": api_key},
            files=files,
            data=data,
            timeout=120
        )
        response.raise_for_status()

        result = response.json()
        transcript = result.get("transcript", "").strip()
        return transcript

    except Exception as e:
        log_and_raise(e, model_code=model, provider='sarvam', custom_message=f"Sarvam ASR error: {str(e)}", log_context=log_context)


def get_dhruva_output(audio_url, lang, log_context=None):
    chunk_data = {
        "config": {
            "serviceId": os.getenv("DHRUVA_SERVICE_ID") if lang != "en" else os.getenv("DHRUVA_SERVICE_ID_EN"),
            "language": {"sourceLanguage": lang},
            "transcriptionFormat": {"value": "transcript"}
            },
        "audio": [{
                "audioUri": audio_url
            }]
        }
    try:
        response = requests.post(os.getenv("DHRUVA_API_URL"),
            headers={"authorization": os.getenv("DHRUVA_KEY")},
            json=chunk_data,
            )
        transcript = response.json()["output"][0]["source"]
        return transcript
    except Exception as e:
        log_and_raise(e, model_code='dhruva_asr', provider='dhruva', log_context=log_context)


def get_asr_output(audio_url, lang, model="DHRUVA_ASR", log_context=None):
    out = ""
    if model.startswith("google-asr"):
        out = get_gemini_asr_output(audio_url, lang, model.replace("google-asr/", ""), log_context=log_context)
    elif model.startswith("gpt") or model.startswith("whisper"):
        out = get_openai_asr_output(audio_url, lang, model, log_context=log_context)
    elif model.startswith("saarika"):
        out = get_sarvam_asr_output(audio_url, lang, model, log_context=log_context)
    else:
        out = get_dhruva_output(audio_url, lang, log_context=log_context)
    return out