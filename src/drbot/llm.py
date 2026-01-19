from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Optional
from .Regi import Regi
from .log import log

# Estimated costs per 1k tokens (USD). 
# Using GPT-4o pricing as a default baseline: $5.00 / 1M input, $15.00 / 1M output
# So $0.005 / 1k input, $0.015 / 1k output.
# These act as defaults but really we should probably config them if model changes.
# For now hardcoding reasonable defaults for "standard" high quality models.
COST_PER_1K_INPUT = 0.005
COST_PER_1K_OUTPUT = 0.015

class LLMService(Regi):
    """
    A service that provides LLM capabilities to Botlings.
    Handles configuration, rate limiting, and cost tracking.
    """
    
    default_settings = {
        "model": "gpt-4o",
        "openai_api_key": "",
        "daily_cap": 1.0,
        "monthly_cap": 10.0,
        "system_prompt_default": "You are a helpful assistant."
    }

    def __init__(self) -> None:
        super().__init__("Service", "LLM")

    @property
    def storage(self) -> dict[str, Any]:
        return self.DR.storage

    @property
    def settings(self) -> dict[str, Any]:
        return self.DR.settings

    def setup(self) -> None:
        # Initialize storage for usage if not present
        if "usage" not in self.DR.storage:
            self.DR.storage["usage"] = {
                "total_cost": 0.0,
                "daily_cost": 0.0,
                "daily_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "monthly_cost": 0.0,
                "monthly_date": datetime.now(timezone.utc).strftime("%Y-%m"),
            }

    def _update_caps(self) -> None:
        # Reset counters if period changed
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        month = now.strftime("%Y-%m")
        
        usage = self.DR.storage["usage"]
        
        if usage.get("daily_date") != today:
            usage["daily_cost"] = 0.0
            usage["daily_date"] = today
            
        if usage.get("monthly_date") != month:
            usage["monthly_cost"] = 0.0
            usage["monthly_date"] = month

    def check_caps(self) -> bool:
        self._update_caps()
        usage = self.DR.storage["usage"]
        llm_settings = self.DR.global_settings.get("llm", {})
        daily_cap = llm_settings.get("daily_cap", 1.0)
        monthly_cap = llm_settings.get("monthly_cap", 10.0)
        
        if usage["daily_cost"] >= daily_cap:
            log.warning(f"LLM daily spending cap reached (${usage['daily_cost']:.2f} >= ${daily_cap:.2f}).")
            return False
        if usage["monthly_cost"] >= monthly_cap:
            log.warning(f"LLM monthly spending cap reached (${usage['monthly_cost']:.2f} >= ${monthly_cap:.2f}).")
            return False
        return True

    def track_cost(self, input_tokens: int, output_tokens: int) -> None:
        cost = (input_tokens / 1000 * COST_PER_1K_INPUT) + (output_tokens / 1000 * COST_PER_1K_OUTPUT)
        usage = self.DR.storage["usage"]
        
        usage["total_cost"] = usage.get("total_cost", 0.0) + cost
        usage["daily_cost"] = usage.get("daily_cost", 0.0) + cost
        usage["monthly_cost"] = usage.get("monthly_cost", 0.0) + cost
        
        log.debug(f"LLM usage: {input_tokens} in, {output_tokens} out. Est cost: ${cost:.5f}. Total today: ${usage['daily_cost']:.4f}")
        
        # Save occasionally? DrBot autosaves on schedule, but we might want to force save if cost is high? 
        # Rely on DrBot's periodic save for now as costs are essentially metadata.

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> str | None:
        """
        Generate a response from the LLM.
        Returns the response string or None if generation failed or was blocked.
        """
        llm_settings = self.DR.global_settings.get("llm", {})
        api_key = llm_settings.get("_openai_api_key")
        if not api_key:
            log.error("No OpenAI API key configured for LLMService.")
            return None
            
        if not self.check_caps():
            return None
            
        model = llm_settings.get("model", "gpt-4o")
        sys_prompt = system_prompt or "You are a helpful assistant."

        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            
            # Using chat completions
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": prompt}
                ],
                response_format=response_format,
            )
            
            content = response.choices[0].message.content
            
            if response.usage:
                self.track_cost(response.usage.prompt_tokens, response.usage.completion_tokens)
                
            return content

        except Exception as e:
            log.error(f"LLM generation failed: {e}")
            return None
