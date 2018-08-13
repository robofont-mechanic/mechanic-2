import os
import ssl
from urllib.request import urlopen


class ExtensionRepoError(Exception):
    pass


def getDataFromURL(url, formatter=None):
    url = url.replace(" ", "%20")
    context = ssl._create_unverified_context()
    response = urlopen(url, timeout=5, context=context)
    data = response.read()
    if formatter:
        data = formatter(data)
    response.close()
    return data


def findExtensionInRoot(name, path):
    """
    return the path of the extension with a given file name in a given directory.
    """
    for root, dirs, files in os.walk(path):
        if name in dirs:
            return os.path.join(root, name)
    return None


remembered = []


def clearRemembered(*args):
    [m.reset(args) for m in remembered]


def remember(function):
    """
    A decorator caching the result of a method.
    """
    memo = {}

    def wrapper(*args):
        if args in memo:
            return memo[args]
        else:
            rv = function(*args)
            memo[args] = rv
            return rv

    def _reset(args):
        if not args:
            memo.clear()
        else:
            for key in list(memo):
                found = True
                for arg in args:
                    if arg not in key:
                        found = False
                        break
                if found:
                    del memo[key]
    wrapper.reset = _reset
    remembered.append(wrapper)
    return wrapper
