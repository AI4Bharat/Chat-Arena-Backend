import os
import requests
from rest_framework.response import Response
from rest_framework import status

def get_dhruva_output(audio_url, lang, context):
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
        from ai_model.error_logging import log_and_raise
        log_and_raise(e, model_code='dhruva_asr', provider='dhruva', context=context)


def get_asr_output(audio_url, lang, model="DHRUVA_ASR", context):
    out = ""
    # if model == "DHRUVA_ASR":
    out = get_dhruva_output(audio_url, lang, context=context)
    return out