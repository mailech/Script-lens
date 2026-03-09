"""
Multi-Agent LLM Manager with Fallback Chain
Priority: OpenAI GPT-4o-mini → Groq Llama3 → Gemini 1.5 Flash
"""

import os
import json
import logging
from typing import Optional, Tuple
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
#  Agent Definitions
# ─────────────────────────────────────────

class GeminiAgent:
    name = "Gemini 1.5 Flash"
    provider = "google"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key != "your_gemini_api_key_here")

    def test_connection(self) -> Tuple[bool, str]:
        if not self.is_configured():
            return False, "API key not configured"
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel("gemini-flash-latest")
            response = model.generate_content("Say 'API OK' in exactly those words.")
            return True, f"Connected! Response: {response.text.strip()}"
        except Exception as e:
            return False, str(e)

    def generate(self, prompt: str) -> str:
        import google.generativeai as genai
        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel("gemini-flash-latest")
        response = model.generate_content(prompt)
        return response.text


class GroqAgent:
    name = "Groq Llama3-8B"
    provider = "groq"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "")

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key != "your_groq_api_key_here")

    def test_connection(self) -> Tuple[bool, str]:
        if not self.is_configured():
            return False, "API key not configured"
        try:
            from groq import Groq
            client = Groq(api_key=self.api_key)
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": "Say 'API OK' in exactly those words."}],
                max_tokens=10
            )
            return True, f"Connected! Response: {response.choices[0].message.content.strip()}"
        except Exception as e:
            return False, str(e)

    def generate(self, prompt: str) -> str:
        from groq import Groq
        client = Groq(api_key=self.api_key)
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096
        )
        return response.choices[0].message.content


class OpenAIAgent:
    name = "OpenAI GPT-4o-mini"
    provider = "openai"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key != "your_openai_api_key_here")

    def test_connection(self) -> Tuple[bool, str]:
        if not self.is_configured():
            return False, "API key not configured"
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Say 'API OK' in exactly those words."}],
                max_tokens=10
            )
            return True, f"Connected! Response: {response.choices[0].message.content.strip()}"
        except Exception as e:
            return False, str(e)

    def generate(self, prompt: str) -> str:
        from openai import OpenAI
        client = OpenAI(api_key=self.api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096
        )
        return response.choices[0].message.content


class ClaudeAgent:
    name = "Anthropic Claude 3.5 Sonnet"
    provider = "anthropic"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key != "your_claude_api_key_here")

    def test_connection(self) -> Tuple[bool, str]:
        if not self.is_configured():
            return False, "API key not configured"
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=self.api_key)
            response = client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=10,
                messages=[{"role": "user", "content": "Say 'API OK' in exactly those words."}]
            )
            return True, f"Connected! Response: {response.content[0].text.strip()}"
        except Exception as e:
            return False, str(e)

    def generate(self, prompt: str) -> str:
        from anthropic import Anthropic
        client = Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text


# ─────────────────────────────────────────
#  Multi-Agent Router with Fallback
# ─────────────────────────────────────────

class MultiAgentRouter:
    def __init__(self, api_keys: dict = None):
        keys = api_keys or {}
        self.agents = [
            OpenAIAgent(keys.get("openai")),
            GroqAgent(keys.get("groq")),
            GeminiAgent(keys.get("gemini")),
            ClaudeAgent(keys.get("anthropic")),
        ]
        self.last_index = -1 
        self.cooldowns = {} # provider_name -> timestamp
        self.exhausted = set() # Agents that hit daily limits or are invalid

    def generate(self, prompt: str) -> Tuple[str, str]:
        """
        Try to rotate agents to distribute load. Skip agents on cooldown.
        """
        import time
        errors = []
        now = time.time()
        
        start_idx = (self.last_index + 1) % len(self.agents)
        
        for i in range(len(self.agents)):
            curr_idx = (start_idx + i) % len(self.agents)
            agent = self.agents[curr_idx]
            
            # Skip exhausted or invalid agents
            if agent.name in self.exhausted:
                continue

            # Check cooldown
            if agent.name in self.cooldowns:
                if now < self.cooldowns[agent.name]:
                    continue 
                else:
                    del self.cooldowns[agent.name]

            if not agent.is_configured():
                errors.append(f"{agent.name}: not configured")
                continue
                
            try:
                logger.info(f"Using agent: {agent.name}")
                result = agent.generate(prompt)
                self.last_index = curr_idx
                return result, agent.name
            except Exception as e:
                err_msg = str(e)
                
                # Handle Permanent Failures (Invalid Key or Daily Quota)
                if "401" in err_msg or "invalid_api_key" in err_msg.lower():
                    logger.error(f"Agent {agent.name} has an INVALID KEY. Disabling.")
                    self.exhausted.add(agent.name)
                elif "quota" in err_msg.lower() and ("day" in err_msg.lower() or "per project" in err_msg.lower()):
                    logger.error(f"Agent {agent.name} DAILY QUOTA EXHAUSTED. Disabling.")
                    self.exhausted.add(agent.name)
                
                # Handle Temporary Rate Limits
                elif "429" in err_msg or "rate_limit" in err_msg.lower():
                    # For Groq/Gemini temporary limits, put on short cooldown
                    wait_time = 30 # Default wait
                    logger.warning(f"Agent {agent.name} rate limited. 30s cooldown.")
                    self.cooldowns[agent.name] = now + wait_time
                
                errors.append(f"{agent.name}: {err_msg}")

        raise RuntimeError(
            f"All LLM agents failed or are on cooldown:\n" + "\n".join(f"  • {e}" for e in errors)
        )

    def get_configured_agents(self) -> list:
        return [{"name": a.name, "provider": a.provider, "configured": a.is_configured()}
                for a in self.agents]

    def test_all(self) -> list:
        results = []
        for agent in self.agents:
            ok, msg = agent.test_connection()
            results.append({
                "name": agent.name,
                "provider": agent.provider,
                "configured": agent.is_configured(),
                "success": ok,
                "message": msg
            })
        return results


def test_single_agent(provider: str, api_key: str) -> Tuple[bool, str]:
    """Test a single API key for the given provider."""
    agents = {
        "google": GeminiAgent,
        "groq": GroqAgent,
        "openai": OpenAIAgent,
        "anthropic": ClaudeAgent
    }
    AgentClass = agents.get(provider)
    if not AgentClass:
        return False, f"Unknown provider: {provider}"
    agent = AgentClass(api_key=api_key)
    return agent.test_connection()
