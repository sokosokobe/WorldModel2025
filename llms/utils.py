import argparse
import os
import base64
import io
from typing import Any, NamedTuple, Union, List
from PIL import Image

# --- 元のインポート（OpenAI/HuggingFace用） ---
from llms import (
    generate_from_huggingface_completion,
    generate_from_openai_chat_completion,
    generate_from_openai_completion,
    lm_config,
)

# --- Gemini用の新しいライブラリ ---
try:
    import google.generativeai as genai
    from google.generativeai.types import HarmCategory, HarmBlockThreshold

    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

# 型定義（他のファイルからの参照用）
APIInput = Union[str, List[Any], dict[str, Any]]


# --- 画像デコード用ヘルパー ---
def decode_image(image_data):
    """Base64文字列またはPIL.ImageをPIL.Imageに統一する"""
    if isinstance(image_data, Image.Image):
        return image_data
    if isinstance(image_data, str) and image_data.startswith("data:image"):
        try:
            base64_str = image_data.split(",")[1]
            img_bytes = base64.b64decode(base64_str)
            return Image.open(io.BytesIO(img_bytes))
        except Exception:
            return None
    return None


def call_llm(
    lm_config: lm_config.LMConfig,
    prompt: APIInput,
) -> str:
    response: str

    # =========================================================================
    # 1. OpenAI (元のロジックを維持)
    # =========================================================================
    if lm_config.provider == "openai":
        if lm_config.mode == "chat":
            assert isinstance(prompt, list)
            response = generate_from_openai_chat_completion(
                messages=prompt,
                model=lm_config.model,
                temperature=lm_config.gen_config["temperature"],
                top_p=lm_config.gen_config["top_p"],
                context_length=lm_config.gen_config["context_length"],
                max_tokens=lm_config.gen_config["max_tokens"],
                stop_token=None,
            )
        elif lm_config.mode == "completion":
            assert isinstance(prompt, str)
            response = generate_from_openai_completion(
                prompt=prompt,
                engine=lm_config.model,
                temperature=lm_config.gen_config["temperature"],
                max_tokens=lm_config.gen_config["max_tokens"],
                top_p=lm_config.gen_config["top_p"],
                stop_token=lm_config.gen_config["stop_token"],
            )
        else:
            raise ValueError(f"OpenAI models do not support mode {lm_config.mode}")
        return response

    # =========================================================================
    # 2. HuggingFace (元のロジックを維持)
    # =========================================================================
    elif lm_config.provider == "huggingface":
        assert isinstance(prompt, str)
        response = generate_from_huggingface_completion(
            prompt=prompt,
            model_endpoint=lm_config.gen_config["model_endpoint"],
            temperature=lm_config.gen_config["temperature"],
            top_p=lm_config.gen_config["top_p"],
            stop_sequences=lm_config.gen_config["stop_sequences"],
            max_new_tokens=lm_config.gen_config["max_new_tokens"],
        )
        return response

    # =========================================================================
    # 3. Google / Gemini (新しいロジックに差し替え)
    # =========================================================================
    elif lm_config.provider == "google":
        if not HAS_GEMINI:
            print(
                "❌ Error: google-generativeai not installed. Run `pip install google-generativeai`"
            )
            return "stop [ERROR: google-generativeai missing]"

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("❌ Error: GEMINI_API_KEY not set")
            return "stop [ERROR: GEMINI_API_KEY not set]"

        genai.configure(api_key=api_key)

        # --- OpenAI形式のメッセージをGemini形式に変換 ---
        gemini_contents = []
        system_instruction = None

        messages = (
            prompt
            if isinstance(prompt, list)
            else [{"role": "user", "content": prompt}]
        )

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            parts = []
            if isinstance(content, str):
                if content.strip():
                    parts.append(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, str):
                        if item.strip():
                            parts.append(item)
                    elif isinstance(item, dict):
                        if item.get("type") == "text":
                            text_val = item.get("text", "")
                            if text_val.strip():
                                parts.append(text_val)
                        elif item.get("type") == "image_url":
                            img_val = item.get("image_url", "")
                            if isinstance(img_val, dict):
                                img_val = img_val.get("url", "")
                            img = decode_image(img_val)
                            if img:
                                parts.append(img)
                    elif isinstance(item, Image.Image):
                        parts.append(item)

            if role == "system":
                # Systemプロンプトの抽出
                text_parts = [p for p in parts if isinstance(p, str)]
                if text_parts:
                    current_sys = "\n".join(text_parts)
                    system_instruction = (
                        (system_instruction + "\n" + current_sys)
                        if system_instruction
                        else current_sys
                    )
            elif role == "user" and parts:
                gemini_contents.append({"role": "user", "parts": parts})
            elif role == "assistant" and parts:
                gemini_contents.append({"role": "model", "parts": parts})

        # 会話履歴の正規化 (User/Model交互ルール対応)
        final_history = []
        if gemini_contents:
            current_msg = gemini_contents[0]
            for next_msg in gemini_contents[1:]:
                if current_msg["role"] == next_msg["role"]:
                    current_msg["parts"].extend(next_msg["parts"])
                else:
                    final_history.append(current_msg)
                    current_msg = next_msg
            final_history.append(current_msg)

        # システム指示の補強
        if not system_instruction:
            system_instruction = "You are an autonomous web agent. Output ONLY the action code inside ``` ``` blocks."
        else:
            system_instruction += "\n\nIMPORTANT: Output ONLY the action code inside ``` ``` blocks. Do not chat."

        try:
            model = genai.GenerativeModel(
                lm_config.model, system_instruction=system_instruction
            )
            safety = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }

            response_obj = model.generate_content(
                final_history,
                safety_settings=safety,
                generation_config={"temperature": 0.0},
            )

            if response_obj.text:
                return response_obj.text
            return "stop [ERROR: Empty response]"

        except Exception as e:
            return f"stop [ERROR: {e}]"

    else:
        raise NotImplementedError(f"Provider {lm_config.provider} not implemented")
