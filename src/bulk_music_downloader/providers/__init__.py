from .audius import AudiusProvider
from .jamendo import JamendoProvider
from .internet_archive import InternetArchiveProvider
from .tubidy import TubidyProvider
from .direct_url import DirectURLProvider


def build_providers(config):
    user_agent = config.get(
        "user_agent",
        "BulkMusicDownloader/0.2",
    )

    instances = {
        "audius": AudiusProvider(
            api_key=config.get("audius_api_key", ""),
            user_agent=user_agent,
        ),

        "jamendo": JamendoProvider(
            client_id=config.get("jamendo_client_id", ""),
            user_agent=user_agent,
        ),

        "internet_archive": InternetArchiveProvider(
            user_agent,
        ),

        "tubidy": TubidyProvider(),

        "direct_url": DirectURLProvider(),
    }

    providers = []

    for name in config.get("providers", []):
        provider = instances.get(name)

        if provider is not None:
            providers.append(provider)

    return providers
