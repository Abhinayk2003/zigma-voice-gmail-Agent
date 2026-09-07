from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageInfo:
    """
    Normalized language information used by the voice pipeline.
    """

    code: str
    name: str
    locale: str


class LanguageService:
    """
    Central language configuration for the voice agent.

    The service converts different language representations
    into one consistent internal format.
    """

    LANGUAGES: dict[str, LanguageInfo] = {
        "en": LanguageInfo(
            code="en",
            name="English",
            locale="en-IN",
        ),
        "hi": LanguageInfo(
            code="hi",
            name="Hindi",
            locale="hi-IN",
        ),
        "te": LanguageInfo(
            code="te",
            name="Telugu",
            locale="te-IN",
        ),
        "ta": LanguageInfo(
            code="ta",
            name="Tamil",
            locale="ta-IN",
        ),
        "kn": LanguageInfo(
            code="kn",
            name="Kannada",
            locale="kn-IN",
        ),
        "ml": LanguageInfo(
            code="ml",
            name="Malayalam",
            locale="ml-IN",
        ),
    }

    ALIASES: dict[str, str] = {
        "english": "en",
        "en-in": "en",
        "en_india": "en",

        "hindi": "hi",
        "hi-in": "hi",
        "hi_india": "hi",

        "telugu": "te",
        "te-in": "te",
        "te_india": "te",

        "tamil": "ta",
        "ta-in": "ta",
        "ta_india": "ta",

        "kannada": "kn",
        "kn-in": "kn",
        "kn_india": "kn",

        "malayalam": "ml",
        "ml-in": "ml",
        "ml_india": "ml",
    }

    # ========================================================
    # Normalize
    # ========================================================

    @classmethod
    def normalize(
        cls,
        language: str | None,
    ) -> str | None:
        """
        Convert a language name/code into the internal code.

        Examples:

            English  -> en
            english  -> en
            en-IN    -> en
            Telugu   -> te
            te-IN    -> te
        """

        if not language:
            return None

        value = (
            str(language)
            .strip()
            .lower()
        )

        if not value:
            return None

        if value in cls.LANGUAGES:
            return value

        return cls.ALIASES.get(value)

    # ========================================================
    # Information
    # ========================================================

    @classmethod
    def get(
        cls,
        language: str | None,
    ) -> LanguageInfo | None:
        """
        Return normalized language information.
        """

        code = cls.normalize(language)

        if code is None:
            return None

        return cls.LANGUAGES.get(code)

    # ========================================================
    # Supported languages
    # ========================================================

    @classmethod
    def is_supported(
        cls,
        language: str | None,
    ) -> bool:
        """
        Return True when the language is supported.
        """

        return cls.normalize(language) is not None

    @classmethod
    def supported_codes(
        cls,
    ) -> list[str]:
        """
        Return all supported internal language codes.
        """

        return list(
            cls.LANGUAGES.keys()
        )

    @classmethod
    def supported_locales(
        cls,
    ) -> list[str]:
        """
        Return all supported locale codes.
        """

        return [
            language.locale
            for language in cls.LANGUAGES.values()
        ]

    # ========================================================
    # Display name
    # ========================================================

    @classmethod
    def display_name(
        cls,
        language: str | None,
    ) -> str:
        """
        Return a human-readable language name.
        """

        info = cls.get(language)

        if info is None:
            return "Unknown"

        return info.name

    # ========================================================
    # Locale
    # ========================================================

    @classmethod
    def locale(
        cls,
        language: str | None,
    ) -> str | None:
        """
        Return the BCP-47 locale for a language.
        """

        info = cls.get(language)

        if info is None:
            return None

        return info.locale


# ============================================================
# Shared language service
# ============================================================

language_service = LanguageService()
