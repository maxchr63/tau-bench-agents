"""
Shared LiteLLM configuration for all tau-bench agents.
This MUST be imported before any other code that uses LiteLLM!
"""

import os
import litellm

# ============================================================================
# CENTRAL CONFIGURATION - Change provider here
# ============================================================================
USE_PROVIDER = os.environ.get("USE_PROVIDER", "openrouter")  # Options: "openai" or "openrouter"
# ============================================================================

# ============================================================================
# GLOBAL TIMEOUT CONFIGURATION - Prevent hanging LLM calls
# ============================================================================
# Set global request timeout for ALL LiteLLM calls (in seconds)
# This prevents zombie threads from LLM calls that never return
LLM_REQUEST_TIMEOUT = int(os.environ.get("LLM_REQUEST_TIMEOUT", "60"))
litellm.request_timeout = LLM_REQUEST_TIMEOUT

# Also set num_retries to limit retry storms
litellm.num_retries = 2

print(f"\n{'='*70}")
print(f"🔧 CONFIGURING LiteLLM - Provider: {USE_PROVIDER}")
print(f"   Request Timeout: {LLM_REQUEST_TIMEOUT}s, Max Retries: {litellm.num_retries}")
print(f"{'='*70}\n")

if USE_PROVIDER == "openrouter":
    # Configure for OpenRouter
    TAU_USER_MODEL = os.environ.get("TAU_USER_MODEL", "openrouter/anthropic/claude-haiku-4.5")  # Free tier model "openrouter/anthropic/claude-haiku-4.5". "openrouter/openai/gpt-5-nano" 
    TAU_USER_PROVIDER = os.environ.get("TAU_USER_PROVIDER", "openrouter") #openai
    
    # Set LiteLLM to use OpenRouter endpoint
    litellm.api_base = "https://openrouter.ai/api/v1"
    litellm.set_verbose = False
    
    # CRITICAL: GPT-5 models have strict parameter requirements
    # Drop unsupported params like temperature=0.0 (gpt-5 only supports temperature=1)
    litellm.drop_params = True
    
    # Get OpenRouter API key and set it as OPENAI_API_KEY
    # (tau-bench looks up keys by provider name, so "openai" provider needs OPENAI_API_KEY)
    OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
    if OPENROUTER_API_KEY:
        os.environ["OPENAI_API_KEY"] = OPENROUTER_API_KEY
        print(f"✅ LiteLLM configured for OpenRouter")
        print(f"   Model: {TAU_USER_MODEL}")
        print(f"   API Base: {litellm.api_base}")
        print(f"   API Key: {OPENROUTER_API_KEY[:20]}...")
    else:
        print("⚠️  WARNING: OPENROUTER_API_KEY not found in environment!")
        print("   Make sure your .env file has: OPENROUTER_API_KEY=sk-or-v1-...")
        
elif USE_PROVIDER == "openai":
    # Configure for OpenAI (default)
    TAU_USER_MODEL = os.environ.get("TAU_USER_MODEL", "gpt-4o-mini")
    TAU_USER_PROVIDER = os.environ.get("TAU_USER_PROVIDER", "openai")
    litellm.set_verbose = False
    
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    if OPENAI_API_KEY:
        print(f"✅ LiteLLM configured for OpenAI")
        print(f"   Model: {TAU_USER_MODEL}")
        print(f"   API Key: {OPENAI_API_KEY[:20]}...")
    else:
        print("⚠️  WARNING: OPENAI_API_KEY not found in environment!")
        
else:
    raise ValueError(f"Invalid USE_PROVIDER: {USE_PROVIDER}. Must be 'openai' or 'openrouter'")

print(f"\n{'='*70}\n")

# Export these for use by other modules
__all__ = ["USE_PROVIDER", "TAU_USER_MODEL", "TAU_USER_PROVIDER"]
