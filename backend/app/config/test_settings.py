from app.config.settings import get_settings


settings = get_settings()

print("Application:", settings.app_name)
print("Version:", settings.app_version)
print("Environment:", settings.app_environment)
print("LLM Provider:", settings.llm_provider)
print("LLM Model:", settings.llm_model)
print("STT Provider:", settings.stt_provider)
print("TTS Provider:", settings.tts_provider)
print("Languages:", settings.supported_language_list)
print("Agent Mode:", settings.default_mode)
print("Confidence:", settings.confidence_threshold)
print("Development:", settings.is_development)