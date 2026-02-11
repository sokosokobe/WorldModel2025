from typing import Any

import tiktoken
from transformers import LlamaTokenizer  # type: ignore


class Tokenizer(object):
    def __init__(self, provider: str, model_name: str) -> None:
        if provider == "openai":
            try:
                # まずはモデル名で解決を試みる
                self.tokenizer = tiktoken.encoding_for_model(model_name)
            except KeyError:
                # gpt-5.2 などの未知のモデルなら、GPT-4o用の 'o200k_base' を強制使用する
                print(
                    f"⚠️ Warning: Model '{model_name}' not found in tiktoken. Falling back to 'o200k_base'."
                )
                try:
                    self.tokenizer = tiktoken.get_encoding("o200k_base")
                except:
                    # 古いtiktokenの場合は gpt-4用の 'cl100k_base' にする
                    self.tokenizer = tiktoken.get_encoding("cl100k_base")
        elif provider == "huggingface":
            self.tokenizer = LlamaTokenizer.from_pretrained(model_name)
            # turn off adding special tokens automatically
            self.tokenizer.add_special_tokens = False  # type: ignore[attr-defined]
            self.tokenizer.add_bos_token = False  # type: ignore[attr-defined]
            self.tokenizer.add_eos_token = False  # type: ignore[attr-defined]
        elif provider == "google":
            self.tokenizer = None  # Not used for input length computation, as Gemini is based on characters
        else:
            raise NotImplementedError

    def encode(self, text: str) -> list[int]:
        return self.tokenizer.encode(text)

    def decode(self, ids: list[int]) -> str:
        return self.tokenizer.decode(ids)

    def __call__(self, text: str) -> list[int]:
        return self.tokenizer.encode(text)
