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
from ai_model.error_logging import log_and_raise
from cartesia import Cartesia
from elevenlabs.client import ElevenLabs
import tritonclient.http as http_client
from tritonclient.utils import np_to_triton_dtype
import numpy as np
import librosa
from scipy.io.wavfile import write as scipy_wav_write
import io

misc_tts_url = os.getenv("MISC_TTS_API_URL")
indo_aryan_tts_url = os.getenv("INDO_ARYAN_TTS_API_URL")
dravidian_tts_url = os.getenv("DRAVIDIAN_TTS_API_URL")
dhruva_key = os.getenv("DHRUVA_KEY")
elevenlabs_api_url = os.getenv("ELEVENLABS_API_URL")
parler_api_url = os.getenv("PARLER_API_URL")
openai_api_key = os.getenv("OPENAI_API_KEY_GPT_5")
minimax_api_key = os.getenv("MINIMAX_API_KEY")
cartesia_api_key = os.getenv("CARTESIA_API_KEY")
indicf5_api_key = os.getenv("INDICF5_API_KEY")
elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")

def get_tts_url(language):
    if language in ["brx", "en", "mni"]:
        return misc_tts_url
    elif language in ["as", "gu", "hi", "mr", "or", "pa", "bn"]:
        return indo_aryan_tts_url
    elif language in ["kn", "ml", "ta", "te"]:
        return dravidian_tts_url
    else:
        return None

def get_dhruva_output(tts_input, lang, gender, log_context=None):
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
        log_and_raise(e, model_code='dhruva_tts', provider='dhruva', log_context=log_context)

def get_sarvam_tts_output(tts_input, lang, model, gender, log_context=None):
    client = SarvamAI(api_subscription_key=os.getenv("SARVAM_API_KEY_BULBUL"))
    speakerV2Female = ["anushka", "vidya", "manisha", "arya"]
    speakerV2Male = ["abhilash", "karun", "hitesh"]
    speakerV3Female = ["ritu", "priya", "neha", "pooja", "simran", "kavya", "ishita", "shreya", "roopa"]
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
        log_and_raise(e, model_code=model, provider='sarvam', log_context=log_context)

def get_gemini_output(tts_input, lang, model, gender, log_context=None):
    PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
    speakerMale = ["Achird", "Algenib", "Algieba", "Alnilam", "Charon", "Enceladus", "Fenrir", "Iapetus", "Orus", "Puck", "Rasalgethi", "Sadachbia", "Sadaltager", "Schedar", "Umbriel", "Zubenelgenubi"]
    speakerFemale = ["Achernar", "Aoede", "Autonoe", "Callirrhoe", "Despina", "Erinome", "Gacrux", "Kore", "Laomedeia", "Leda", "Pulcherrima", "Sulafat", "Vindemiatrix", "Zephyr"]
    lang = "kok" if lang == "gom" else lang
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
        log_and_raise(e, model_code=model, provider='google', log_context=log_context)

def get_elevenlabs_output(tts_input, lang, gender, log_context=None):
    """
    Generate TTS using ElevenLabs API
    Note: This model only supports pre-synthesized sentences and should be used in academic mode only.
    API accepts either 'name' or 'gender' parameter
    """
    # ElevenLabs Speaker Mapping (Gender -> List of Speaker Names)
    ELEVENLABS_GENDER_MAP = {
        "male": ["Adam", "Bill"],
        "female": ["Alice"]
    }
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
        log_and_raise(e, model_code='elevenlabs', provider='elevenlabs', custom_message=f"ElevenLabs TTS error: {str(e)}", log_context=log_context)

def get_elevenlabs_tts_output(tts_input, model, gender, log_context=None):
    ELEVENLABS_VOICE_MAP = {
        "male": [
            "JBFqnCBsd6RMkjVDRZzb",  # George
            "TX3LPaxmHKxFdv7VOQHJ",  # Liam
            "pqHfZKP75CvOlQylNhV4",  # Bill
        ],
        "female": [
            "EXAVITQu4vr4xnSDxMaL",  # Sarah
            "XB0fDUnXU5powFXDhCwa",  # Charlotte
            "Xb7hH8MSUJpSbSDYk0k2",  # Alice
        ]
    }

    try:
        client = ElevenLabs(api_key=elevenlabs_api_key)
        voice_id = random.choice(ELEVENLABS_VOICE_MAP.get(gender.lower(), ELEVENLABS_VOICE_MAP["male"]))

        audio_generator = client.text_to_speech.convert(
            text=tts_input,
            voice_id=voice_id,
            model_id=model,
            output_format="pcm_24000"
        )
        audio_bytes = b"".join(audio_generator)
        pcm_array = np.frombuffer(audio_bytes, dtype=np.int16)
        wav_buffer = io.BytesIO()
        scipy_wav_write(wav_buffer, 24000, pcm_array)

        audio_base64 = base64.b64encode(wav_buffer.getvalue()).decode("utf-8")
        return upload_tts_audio(audio_base64)

    except Exception as e:
        log_and_raise(e, model_code=model, provider='elevenlabs', custom_message=f"ElevenLabs TTS error: {str(e)}", log_context=log_context)

def get_parler_output(tts_input, lang, gender, log_context=None):
    """
    Generate TTS using IndicParlerTTS API
    Note: This model only supports pre-synthesized sentences and should be used in academic mode only.
    API accepts either 'name' or 'gender' parameter
    """
    # Parler Speaker Mapping (Gender -> List of Speaker Names)
    PARLER_GENDER_MAP = {
        "male": ["Rohit"],
        "female": ["Divya"]
    }
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
        log_and_raise(e, model_code='indicparlertts', provider='ai4bharat', custom_message=f"IndicParlerTTS error: {str(e)}", log_context=log_context)

def get_openai_tts_output(tts_input, model, gender, log_context=None):
    OPENAI_VOICE_MAP = {
        "male": ["onyx", "echo", "ash", "fable", "verse"],
        "female": ["nova", "shimmer", "coral", "alloy", "sage", "ballad"]
    }

    INSTRUCTIONS = (
        "Speak clearly and naturally with a warm, conversational tone. "
        "Pronounce Indian names, places, and words accurately with proper emphasis. "
        "Maintain a steady, moderate pace suitable for easy comprehension."
    )

    try:
        voice = random.choice(OPENAI_VOICE_MAP.get(gender.lower(), OPENAI_VOICE_MAP["male"]))

        payload = {
            "model": model,
            "input": tts_input,
            "voice": voice,
            "response_format": "wav",
            "instructions": INSTRUCTIONS
        }

        response = requests.post(
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {openai_api_key}",
                "Content-Type": "application/json"
            },
            json=payload
        )
        response.raise_for_status()

        audio_base64 = base64.b64encode(response.content).decode("utf-8")
        audio = upload_tts_audio(audio_base64)
        return audio

    except Exception as e:
        log_and_raise(e, model_code=model, provider='openai', custom_message=f"OpenAI TTS error: {str(e)}", log_context=log_context)

def get_minimax_tts_output(tts_input, model, gender, log_context=None):
    """
    Generate TTS using MiniMax HTTP API (speech-2.8-hd)
    Documentation: https://platform.minimax.io/docs/api-reference/speech-t2a-http
    """
    MINIMAX_VOICE_MAP = {
        "male": ["male-qn-qingse", "male-qn-jingying", "male-qn-badao", "male-qn-daxuesheng"],
        "female": ["female-shaonv", "female-yujie", "female-chengshu", "female-tianmei"]
    }

    MINIMAX_API_URL = "https://api.minimax.io/v1/t2a_v2"

    try:
        voice_id = random.choice(MINIMAX_VOICE_MAP.get(gender.lower(), MINIMAX_VOICE_MAP["male"]))

        headers = {
            "Authorization": f"Bearer {minimax_api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "text": tts_input,
            "stream": False,
            "output_format": "hex",
            "voice_setting": {
                "voice_id": voice_id,
                "speed": 1.0,
                "vol": 1.0,
                "pitch": 0
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "wav",
                "channel": 1
            }
        }

        response = requests.post(MINIMAX_API_URL, headers=headers, json=payload)
        response.raise_for_status()

        response_data = response.json()

        # Check for API errors
        if response_data.get("base_resp", {}).get("status_code", 0) != 0:
            error_msg = response_data.get("base_resp", {}).get("status_msg", "Unknown error")
            raise Exception(f"MiniMax API error: {error_msg}")

        # Get audio hex and convert to bytes
        audio_hex = response_data["data"]["audio"]
        audio_bytes = bytes.fromhex(audio_hex)

        # Convert to base64 and upload
        audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
        audio = upload_tts_audio(audio_base64)
        return audio

    except Exception as e:
        log_and_raise(e, model_code=model, provider='minimax', custom_message=f"MiniMax TTS error: {str(e)}", log_context=log_context)

def get_cartesia_tts_output(tts_input, model, gender, log_context=None):
    CARTESIA_VOICE_MAP = {
        "male": [
            "c961b81c-a935-4c17-bfb3-ba2239de8c2f",  # Kyle
            "a0e99841-438c-4a64-b679-ae501e7d6091",  # Barbershop Man
        ],
        "female": [
            "6ccbfb76-1fc6-48f7-b71d-91ac6298247b",  # Tessa
            "f9836c6e-a0bd-460e-9d3c-f7299fa60f94",  # Default Female
        ]
    }

    try:
        client = Cartesia(api_key=cartesia_api_key)
        voice_id = random.choice(CARTESIA_VOICE_MAP.get(gender.lower(), CARTESIA_VOICE_MAP["male"]))

        output_format = {
            "container": "wav",
            "sample_rate": 44100,
            "encoding": "pcm_f32le"
        }

        audio_chunks = client.tts.bytes(
            model_id=model,
            transcript=tts_input,
            voice={"mode": "id", "id": voice_id},
            output_format=output_format
        )

        audio_bytes = b"".join(audio_chunks)

        audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
        audio = upload_tts_audio(audio_base64)
        return audio

    except Exception as e:
        log_and_raise(e, model_code=model, provider='cartesia', custom_message=f"Cartesia TTS error: {str(e)}", log_context=log_context)

def get_indicf5_tts_output(tts_input, model, gender, log_context=None):
    INDICF5_ENDPOINT = os.getenv("INDICF5_ENDPOINT")
    TARGET_SAMPLING_RATE = 24000

    REF_AUDIO = {
        "male": os.getenv("INDICF5_REF_AUDIO_MALE"),
        "female": os.getenv("INDICF5_REF_AUDIO_FEMALE")
    }
    REF_TRANSCRIPT = {
        "male": os.getenv("INDICF5_REF_TRANSCRIPT_MALE", ""),
        "female": os.getenv("INDICF5_REF_TRANSCRIPT_FEMALE", "")
    }

    try:
        ref_audio_path = REF_AUDIO.get(gender.lower())
        ref_transcript = REF_TRANSCRIPT.get(gender.lower(), "")

        if not ref_audio_path:
            raise Exception(f"No reference audio configured for gender: {gender}")

        import gevent.ssl
        triton_client = http_client.InferenceServerClient(
            url=INDICF5_ENDPOINT,
            verbose=False,
            ssl=True,
            ssl_context_factory=gevent.ssl._create_default_https_context,
        )

        def make_string_input(value, name):
            arr = np.array([value], dtype="object")
            inp = http_client.InferInput(name, arr.shape, np_to_triton_dtype(arr.dtype))
            inp.set_data_from_numpy(arr)
            return inp

        def make_audio_input(path, name):
            audio, _ = librosa.load(path, sr=TARGET_SAMPLING_RATE)
            audio = audio.astype(np.float32)
            inp = http_client.InferInput(name, audio.shape, "FP32")
            inp.set_data_from_numpy(audio)
            return inp

        inputs = [
            make_string_input(tts_input, "INPUT_TEXT"),
            make_audio_input(ref_audio_path, "AUDIO_PROMPT"),
            make_string_input(ref_transcript, "TEXT_PROMPT"),
        ]

        response = triton_client.infer(
            model_name="tts",
            model_version="1",
            inputs=inputs,
            outputs=[http_client.InferRequestedOutput("OUTPUT_GENERATED_AUDIO")],
            headers={"Authorization": f"Bearer {indicf5_api_key}"},
        )

        generated_audio = response.as_numpy("OUTPUT_GENERATED_AUDIO")
        if generated_audio.ndim > 1:
            generated_audio = generated_audio.squeeze()

        wav_buffer = io.BytesIO()
        scipy_wav_write(wav_buffer, TARGET_SAMPLING_RATE, generated_audio)

        audio_base64 = base64.b64encode(wav_buffer.getvalue()).decode("utf-8")
        return upload_tts_audio(audio_base64)

    except Exception as e:
        log_and_raise(e, model_code=model, provider='ai4bharat', custom_message=f"IndicF5 TTS error: {str(e)}", log_context=log_context)

def get_tts_output(tts_input, lang, model, gender="male", **kwargs):
    log_context = kwargs.get('context')
    out = ""
    if model == "ai4bharat_tts":
        out = get_dhruva_output(tts_input, lang, gender, log_context=log_context)
    elif model.startswith("bulbul"):
        out = get_sarvam_tts_output(tts_input, lang, model, gender, log_context=log_context)
    elif model.startswith("gemini"):
        out = get_gemini_output(tts_input, lang, model, gender, log_context=log_context)
    elif model == "elevenlabs":
        out = get_elevenlabs_output(tts_input, lang, gender, log_context=log_context)
    elif model == "indicparlertts":
        out = get_parler_output(tts_input, lang, gender, log_context=log_context)
    elif model.startswith("gpt"):
        out = get_openai_tts_output(tts_input, model, gender, log_context=log_context)
    elif model.startswith("speech-"):
        out = get_minimax_tts_output(tts_input, model, gender, log_context=log_context)
    elif model.startswith("sonic"):
        out = get_cartesia_tts_output(tts_input, model, gender, log_context=log_context)
    elif model.startswith("indicf5"):
        out = get_indicf5_tts_output(tts_input, model, gender, log_context=log_context)
    elif model.startswith("eleven"):
        out = get_elevenlabs_tts_output(tts_input, model, gender, log_context=log_context)
    return out
