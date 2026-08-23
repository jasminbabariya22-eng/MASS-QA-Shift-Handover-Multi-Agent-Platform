import os
import json
import logfire
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from PIL import Image

from app.config import settings


class VisionAnalyzer(ABC):
    """
    Abstract Base Class for Vision-Language Models analyzing document visuals.
    """
    @abstractmethod
    def analyze_image(self, image_path: str) -> str:
        """Generates a factual semantic description of a document image."""
        pass

    @abstractmethod
    def analyze_chart(self, image_path: str) -> Dict[str, Any]:
        """Extracts structured metadata and trend summary from a chart or graph."""
        pass

    @abstractmethod
    def analyze_diagram(self, image_path: str) -> Dict[str, Any]:
        """Extracts component and flow relationships from a diagram or flowchart."""
        pass


class StubVisionAnalyzer(VisionAnalyzer):
    """
    Fallback Vision Analyzer used when VISION_ENABLED=false or API is unavailable.
    """
    def analyze_image(self, image_path: str) -> str:
        return "Visual content could not be reliably interpreted."

    def analyze_chart(self, image_path: str) -> Dict[str, Any]:
        return {
            "chart_type": "unknown",
            "title": "Chart Image",
            "summary": "Numerical values could not be reliably extracted from this chart."
        }

    def analyze_diagram(self, image_path: str) -> Dict[str, Any]:
        return {
            "summary": "Visual diagram content could not be reliably interpreted.",
            "components": [],
            "relationships": []
        }


class GeminiVisionAnalyzer(VisionAnalyzer):
    """
    Gemini-powered Vision Analyzer using google.genai API.
    """
    def __init__(self, model_name: str = "gemini-3.6-flash"):
        self.model_name = settings.VISION_MODEL or model_name
        self.api_key = settings.GEMINI_API_KEY
        self._client = None
        
        if settings.VISION_ENABLED and self.api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
                logfire.info(f"👁️ Initialized Gemini Vision Analyzer ({self.model_name}).")
            except Exception as e:
                logfire.warning(f"Failed to initialize Gemini Vision Client: {e}")
                self._client = None
        else:
            logfire.info("👁️ Vision analysis disabled or GEMINI_API_KEY missing — using stub analyzer.")

    def _call_gemini(self, prompt: str, image_path: str) -> Optional[str]:
        if not self._client or not os.path.exists(image_path):
            return None

        try:
            pil_img = Image.open(image_path)
            # Try specified model, fallback to gemini-3.6-flash / gemini-3.7-flash if unavailable
            for model_id in [self.model_name, "gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.5-flash"]:
                try:
                    response = self._client.models.generate_content(
                        model=model_id,
                        contents=[prompt, pil_img]
                    )
                    if response and response.text:
                        return response.text.strip()
                except Exception as e:
                    logfire.warning(f"Gemini vision call on {model_id} failed: {e}")
                    continue
        except Exception as err:
            logfire.error(f"Error reading image for vision analysis {image_path}: {err}")

        return None

    def analyze_image(self, image_path: str) -> str:
        prompt = (
            "Analyze this document image in detail. Provide a concise, factual summary of the visual elements, "
            "objects, text labels, and overall meaning. Do NOT hallucinate information not visible."
        )
        res = self._call_gemini(prompt, image_path)
        return res if res else "Visual content could not be reliably interpreted."

    def analyze_chart(self, image_path: str) -> Dict[str, Any]:
        prompt = (
            "Analyze this chart/graph image in detail. Extract the chart title, chart type (bar, line, pie, scatter, etc.), "
            "x-axis label, y-axis label, units, key data points, and overall trend. "
            "Do NOT invent numerical values if they cannot be read clearly."
        )
        res = self._call_gemini(prompt, image_path)
        if not res:
            return {
                "chart_type": "unknown",
                "summary": "Numerical values could not be reliably extracted from this chart."
            }
        
        return {
            "chart_type": "detected_chart",
            "summary": res
        }

    def analyze_diagram(self, image_path: str) -> Dict[str, Any]:
        prompt = (
            "Analyze this technical diagram / flowchart image. Describe the key components, labels, process steps, "
            "sequence of flow, and relationships shown. Do NOT hallucinate relationships not visible."
        )
        res = self._call_gemini(prompt, image_path)
        if not res:
            return {
                "summary": "Visual diagram content could not be reliably interpreted.",
                "components": [],
                "relationships": []
            }

        return {
            "summary": res,
            "components": [],
            "relationships": []
        }
