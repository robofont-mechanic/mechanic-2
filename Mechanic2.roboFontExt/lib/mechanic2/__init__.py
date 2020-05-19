from urlreader import URLReader, URLReaderError
from urlreader import USER_CACHE_DIRECTORY_URL


OFFLINE_CACHE_URL = USER_CACHE_DIRECTORY_URL.\
    URLByAppendingPathComponent_isDirectory_(
        'com.robofontmechanic.OfflineCache', True)


# Two singletons for URLReaders with slightly different behavior.
# Both quote the URL path component by default and force connections 
# over HTTPS to comply with App Transport Security policy requirements.

# The default URLReader, uses standard HTTP caching policies.
DefaultURLReader = URLReader(force_https=True, timeout=60)

# An URLReader that caches more aggressively and tries to serve 
# responses from its own cache first before hitting the remote source.
CachingURLReader = URLReader(force_https=True, timeout=60, 
    use_cache=True, cache_location=OFFLINE_CACHE_URL)
