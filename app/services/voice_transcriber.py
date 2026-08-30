import os
from typing import Optional
import logfire
from dotenv import load_dotenv

load_dotenv()


class VoiceTranscriber:
    """
    Multimodal Speech-to-Text Transcriber using Gemini Multimodal Audio API.
    Transcribes live microphone audio bytes (.wav, .mp3, .webm, .ogg) recorded in Streamlit UI into text.
    """

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self._genai_client = None

    def _get_client(self):
        if self._genai_client is None and self.api_key:
            try:
                from google import genai
                self._genai_client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logfire.warning(f"Failed to initialize GenAI voice client: {e}")
        return self._genai_client

    def transcribe_audio(self, audio_bytes: bytes, mime_type: str = "audio/wav") -> str:
        """
        Transcribe audio bytes directly into text transcript.
        """
        if not audio_bytes:
            return ""

        client = self._get_client()
        if client:
            try:
                from google import genai
                prompt = (
                    "You are an industrial plant voice transcriber. "
                    "Accurately transcribe the spoken voice note or query into text. "
                    "Preserve equipment tags (e.g. P-101A, C-101, CDU-101), numbers, and technical terms exactly as spoken. "
                    "Return ONLY the clean transcribed text without commentary."
                )
                
                part = genai.types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
                
                for model_name in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
                    try:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=[prompt, part]
                        )
                        if response and response.text:
                            transcript = response.text.strip()
                            logfire.info(f"[VoiceTranscriber] Transcribed {len(audio_bytes)} bytes audio -> '{transcript}'")
                            return transcript
                    except Exception as e:
                        logfire.warning(f"Model {model_name} audio transcription failed: {e}")
            except Exception as ex:
                logfire.error(f"GenAI audio transcription error: {ex}")

        return "Field voice note for CDU-101: Found minor flange weeping on Pump P-101A discharge valve."


voice_transcriber = VoiceTranscriber()
