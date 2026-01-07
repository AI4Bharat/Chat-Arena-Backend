import os
import requests
from rest_framework.response import Response
from rest_framework import status
from message.utlis import upload_tts_audio
from sarvamai import SarvamAI
import random
from google.cloud import texttospeech
from google.api_core.client_options import ClientOptions
import base64

misc_tts_url = os.getenv("MISC_TTS_API_URL")
indo_aryan_tts_url = os.getenv("INDO_ARYAN_TTS_API_URL")
dravidian_tts_url = os.getenv("DRAVIDIAN_TTS_API_URL")
dhruva_key = os.getenv("DHRUVA_KEY")

def get_tts_url(language):
    if language in ["brx", "en", "mni"]:
        return misc_tts_url
    elif language in ["as", "gu", "hi", "mr", "or", "pa", "bn"]:
        return indo_aryan_tts_url
    elif language in ["kn", "ml", "ta", "te"]:
        return dravidian_tts_url
    else:
        return None

def get_dhruva_output(tts_input, lang, gender):
    tts_url = get_tts_url(lang)
    sentence_json_data = {
        "input": [{'source': tts_input}],
        "config": {
            "language": {"sourceLanguage": lang},
            "gender": gender.lower(),
        },
    }
    try:
        response = requests.post(tts_url,
            headers={"authorization": dhruva_key},
            json=sentence_json_data,
        )
        audioBase64 = response.json()["audio"][0]["audioContent"]
        audio = upload_tts_audio(audioBase64)
        return audio
    except Exception as e:
        raise Exception(str(e))

def get_sarvam_tts_output(tts_input, lang, model, gender):
    client = SarvamAI(api_subscription_key=os.getenv("SARVAM_API_KEY_BULBUL"))
    speakerV2Female = ["anushka", "vidya", "manisha", "arya"]
    speakerV2Male = ["abhilash", "karun", "hitesh"]
    speakerV3Female = ["ritu", "priya", "neha", "pooja", "simran", "kavya", "ishita", "shreya", "roopa", "amelia", "sophia"]
    speakerV3Male = ["aditya", "ashutosh", "rahul", "rohan", "amit", "dev", "ratan", "varun", "manan", "sumit", "kabir", "aayan", "shubh", "advait"]
    if model == "bulbul:v2":
        speaker = random.choice(speakerV2Female) if gender == "female" else random.choice(speakerV2Male)
    elif model == "bulbul:v3-beta":
        speaker = random.choice(speakerV3Female) if gender == "female" else random.choice(speakerV3Male)

    try:
        response = client.text_to_speech.convert(
            target_language_code=lang+"-IN",
            text=tts_input,
            model=model,
            speaker=speaker,
        )
        audioBase64 = response.audios[0]
        audio = upload_tts_audio(audioBase64)
        return audio
    except Exception as e:
        raise Exception(str(e))

def get_gemini_output(tts_input, lang, model, gender):
    PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
    speakerMale = ["Achird", "Algenib", "Algieba", "Alnilam", "Charon", "Enceladus", "Fenrir", "Iapetus", "Orus", "Puck", "Rasalgethi", "Sadachbia", "Sadaltager", "Schedar", "Umbriel", "Zubenelgenubi"]
    speakerFemale = ["Achernar", "Aoede", "Autonoe", "Callirrhoe", "Despina", "Erinome", "Gacrux", "Kore", "Laomedeia", "Leda", "Pulcherrima", "Sulafat", "Vindemiatrix", "Zephyr"]
    try:
        client = texttospeech.TextToSpeechClient(client_options=ClientOptions(api_endpoint="texttospeech.googleapis.com"))
        synthesis_input = texttospeech.SynthesisInput(text=tts_input, prompt="synthesize speech from input text")

        if gender == "female":
            speaker = random.choice(speakerFemale)
        else:
            speaker = random.choice(speakerMale)

        voice = texttospeech.VoiceSelectionParams(
            language_code=lang+"-IN",
            name=speaker,
            model_name=model,
        )

        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.LINEAR16)
        response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)

        audioBase64 = base64.b64encode(response.audio_content).decode("utf-8")
        audio = upload_tts_audio(audioBase64)
        return audio
    except Exception as e:
        raise Exception(str(e))

def get_tts_output(tts_input, lang, model, gender="male"):
    out = ""
    if model == "ai4bharat_tts":
        out = get_dhruva_output(tts_input, lang, gender)
    elif model.startswith("bulbul"):
        out = get_sarvam_tts_output(tts_input, lang, model, gender)
    elif model.startswith("gemini"):
        out = get_gemini_output(tts_input, lang, model, gender)
    return out