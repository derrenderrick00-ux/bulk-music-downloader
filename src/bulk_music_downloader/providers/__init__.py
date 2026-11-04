from .internet_archive import InternetArchiveProvider
from .tubidy import TubidyProvider
from .direct_url import DirectURLProvider

def build_providers(config):
    instances = {
        "internet_archive": InternetArchiveProvider(config["user_agent"]),
        "tubidy": TubidyProvider(),
        "direct_url": DirectURLProvider(),
    }
    return [instances[name] for name in config["providers"] if name in instances]
