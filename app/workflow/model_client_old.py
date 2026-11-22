import os
import yaml
import logging
import requests

class ModelClient:
    def __init__(self, config_path="config/models.yaml"):
        self.config_path = config_path
        self.config = self._load_config()
        self.nodes = {n['name']: n for n in self.config.get('routing', {}).get('nodes', [])}
        
    def _load_config(self):
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logging.error(f"Failed to load model config: {e}")
            return {}

    def call_model(self, node_name: str, prompt: str) -> str:
        node_config = self.nodes.get(node_name)
        if not node_config:
            raise ValueError(f"Unknown node configuration: {node_name}")
            
        default_model = node_config.get('default_model')
        fallback_model = node_config.get('fallback_model')
        
        try:
            response = self._invoke(default_model, prompt)
            if response:
                return response
        except Exception as e:
            logging.warning(f"Default model {default_model} failed: {e}")
            
        try:
            logging.info(f"Trying fallback {fallback_model}")
            response = self._invoke(fallback_model, prompt)
            if response:
                return response
        except Exception as e:
            logging.warning(f"Fallback model {fallback_model} failed: {e}")
            
        raise Exception(f"All models failed for node {node_name}")

    def _invoke(self, model_id: str, prompt: str) -> str:
        gemini_key = os.getenv("GEMINI_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")
        
        if not gemini_key and not openai_key:
            raise Exception("No API keys configured.")
            
        if "gemini" in model_id.lower():
            if not gemini_key:
                raise Exception("GEMINI_API_KEY is missing.")
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={gemini_key}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                return r.json()['candidates'][0]['content']['parts'][0]['text']
            else:
                raise Exception(f"Gemini API returned {r.status_code}: {r.text}")
                
        elif "gpt" in model_id.lower():
            if not openai_key:
                raise Exception("OPENAI_API_KEY is missing.")
                
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {openai_key}"}
            payload = {"model": model_id, "messages": [{"role": "user", "content": prompt}]}
            r = requests.post(url, headers=headers, json=payload, timeout=10)
            if r.status_code == 200:
                return r.json()['choices'][0]['message']['content']
            else:
                raise Exception(f"OpenAI API returned {r.status_code}: {r.text}")
                
        raise Exception(f"Unsupported model provider for {model_id}")