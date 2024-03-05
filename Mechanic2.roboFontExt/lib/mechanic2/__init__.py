import AppKit
from mojo.UI import getPassword

from urlreader import URLReader, URLReaderError
from urlreader import USER_CACHE_DIRECTORY_URL


OFFLINE_CACHE_URL = USER_CACHE_DIRECTORY_URL.\
    URLByAppendingPathComponent_isDirectory_(
        'com.robofontmechanic.OfflineCache', True)


# Singletons for URLReaders with slightly different behavior.
# Both quote the URL path component by default and force connections
# over HTTPS to comply with App Transport Security policy requirements.

# The default URLReader, uses standard HTTP caching policies.
DefaultURLReader = URLReader(
    force_https=True,
    timeout=60
)

# Github URLReader if a token is set in the preferences.
githubToken = getPassword(service="com.mechanic.githubToken", username=AppKit.NSUserName())
if githubToken:
    GithubDefaultURLReader = URLReader(
        force_https=True,
        timeout=60,
        headers=dict(Authorization='token ' + githubToken)
    )
else:
    GithubDefaultURLReader = URLReader(
        force_https=True,
        timeout=60
    )


# An URLReader that caches more aggressively and tries to serve
# responses from its own cache first before hitting the remote source.
CachingURLReader = URLReader(
    force_https=True,
    timeout=60,
    use_cache=True,
    cache_location=OFFLINE_CACHE_URL
)
