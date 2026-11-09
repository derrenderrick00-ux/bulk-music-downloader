from .audius import AudiusProvider
from .jamendo import JamendoProvider
from .freetouse import FreeToUseProvider
from .ccmixter import CcMixterProvider

from .internet_archive import InternetArchiveProvider
from .tubidy import TubidyProvider
from .direct_url import DirectURLProvider


def build_providers(config):
    user_agent = config.get(
        "user_agent",
        "BulkMusicDownloader/0.3",
    )

    instances = {
        "audius": AudiusProvider(
            api_key=config.get("audius_api_key", ""),
            user_agent=user_agent,
        ),

        "jamendo": JamendoProvider(
            client_id=config.get("jamendo_client_id", ""),
            client_ids=config.get("jamendo_client_ids", []),
            user_agent=user_agent,
        ),

        "freetouse": FreeToUseProvider(
            user_agent=user_agent,
        ),

        "ccmixter": CcMixterProvider(
            user_agent=user_agent,
        ),

        "internet_archive": InternetArchiveProvider(
            user_agent,
        ),

        # Retained for compatibility, but not enabled by default.
        "tubidy": TubidyProvider(),

        "direct_url": DirectURLProvider(),
    }

    providers = []

    for name in config.get("providers", []):
        provider = instances.get(name)

        if provider is not None:
            providers.append(provider)

    return providers
