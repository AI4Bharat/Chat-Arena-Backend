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
elevenlabs_api_url = os.getenv("ELEVENLABS_API_URL")
parler_api_url = os.getenv("PARLER_API_URL")

# ElevenLabs Speaker Mapping (Gender -> List of Speaker Names)
ELEVENLABS_GENDER_MAP = {
    "male": ["Adam", "Bill"],
    "female": ["Alice"]
}

# Parler Speaker Mapping (Gender -> List of Speaker Names)
PARLER_GENDER_MAP = {
    "male": ["Rohit"],
    "female": ["Divya"]
}

# Pre-synthesized sentences for ElevenLabs and IndicParlerTTS
# These models ONLY work with these specific sentences
# Add more sentences as they become available from the API provider
PRESYNTHESIZED_SENTENCES = {
    "hi": [
        "चलो, शुभ काम में देरी कैसी? मार्केट बंद होने से पहले आज ही डील फाइनल कर लेते हैं।",
    ],
    # Add more languages and sentences as they become available
}

# Models that require pre-synthesized sentences
PRESYNTHESIZED_MODELS = ['elevenlabs', 'indicparlertts']

def get_presynthesized_sentence(language):
    """Get a random pre-synthesized sentence for the given language"""
    sentences = PRESYNTHESIZED_SENTENCES.get(language, [])
    if sentences:
        return random.choice(sentences)
    return None

def has_presynthesized_sentences(language):
    """Check if there are pre-synthesized sentences available for this language"""
    return language in PRESYNTHESIZED_SENTENCES and len(PRESYNTHESIZED_SENTENCES[language]) > 0

def is_presynthesized_model(model_code):
    """Check if a model requires pre-synthesized sentences"""
    return model_code in PRESYNTHESIZED_MODELS

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
    lang = "od" if lang == "or" else lang
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
    lang = "od" if lang == "or" else "kok" if lang == "gom" else lang
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

def get_elevenlabs_output(tts_input, lang, gender):
    """
    Generate TTS using ElevenLabs API
    Note: This model only supports pre-synthesized sentences and should be used in academic mode only.
    API accepts either 'name' or 'gender' parameter
    """
    try:
        # Select random speaker based on gender
        speaker = random.choice(ELEVENLABS_GENDER_MAP.get(gender.lower(), ELEVENLABS_GENDER_MAP["male"]))
        
        # API request - can use name or gender
        params = {
            "sentence": tts_input,
            "name": speaker
        }
        
        response = requests.get(elevenlabs_api_url, params=params)
        response.raise_for_status()
        
        # Expected response: {model, filename, speaker_found, audio_base64}
        response_data = response.json()
        audio_base64 = response_data["audio_base64"]
        
        # Upload and return in standard format
        audio = upload_tts_audio(audio_base64)
        return audio
        
    except Exception as e:
        raise Exception(f"ElevenLabs TTS error: {str(e)}")

def get_parler_output(tts_input, lang, gender):
    """
    Generate TTS using IndicParlerTTS API
    Note: This model only supports pre-synthesized sentences and should be used in academic mode only.
    API accepts either 'name' or 'gender' parameter
    """
    try:
        # Select random speaker based on gender
        speaker = random.choice(PARLER_GENDER_MAP.get(gender.lower(), PARLER_GENDER_MAP["male"]))
        
        # API request - can use name or gender
        params = {
            "sentence": tts_input,
            "name": speaker
        }
        
        response = requests.get(parler_api_url, params=params)
        response.raise_for_status()
        
        # Expected response: {model, filename, speaker_found, audio_base64}
        response_data = response.json()
        audio_base64 = response_data["audio_base64"]
        
        # Upload and return in standard format
        audio = upload_tts_audio(audio_base64)
        return audio
        
    except Exception as e:
        raise Exception(f"IndicParlerTTS error: {str(e)}")

def get_tts_output(tts_input, lang, model, gender="male"):
    out = ""
    if model == "ai4bharat_tts":
        out = get_dhruva_output(tts_input, lang, gender)
    elif model.startswith("bulbul"):
        out = get_sarvam_tts_output(tts_input, lang, model, gender)
    elif model.startswith("gemini"):
        out = get_gemini_output(tts_input, lang, model, gender)
    elif model == "elevenlabs":
        out = get_elevenlabs_output(tts_input, lang, gender)
    elif model == "indicparlertts":
        out = get_parler_output(tts_input, lang, gender)
    return out