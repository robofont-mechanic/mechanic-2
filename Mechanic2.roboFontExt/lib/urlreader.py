import objc
from urllib.parse import urlparse, urlunparse, quote

from PyObjCTools.AppHelper import callAfter
from Foundation import NSObject, NSData, NSMutableData
from Foundation import NSURL, NSURLSession, NSURLSessionConfiguration


# By default, requests time out after 10 seconds since they are first made.
# We are dealing with relatively small data, but this could be increased to
# support slower connections
DEFAULT_TIMEOUT = 10


def callback(url, data, error):
    """Prototype callback

    By providing a function with the same signature as this one to URLReader.fetch(),
    one can be notified when the background URL fetching operation has been completed
    and manipulate the resulting data.
    """
    if error is not None:
        print(error)
    else:
        print(f"{urlparse(url).hostname} fully loaded, size: {len(data)}")


class URLReader(object):

    def __init__(self, timeout=DEFAULT_TIMEOUT, quote_url_path=True, force_https=True):
        self._reader = _NSURLSessionBackgroundReader.alloc().init()
        self._reader.makeSessionWithTimeout_(timeout)
        self._quote_url_path = quote_url_path
        self._force_https = force_https

    @property
    def done(self):
        return self._reader.done()

    def quote_url_path(self, url):
        u = urlparse(url)
        return urlunparse(u._replace(path=quote(u.path)))

    def https_url_scheme(self, url):
        u = urlparse(url)
        if u.scheme == 'http':
            url = urlunparse(u._replace(scheme="https"))
        return url

    def fetch(self, url, callback):
        if self._quote_url_path:
            url = self.quote_url_path(url)
        if self._force_https:
            url = self.https_url_scheme(url)
        self._reader.fetchURLOnBackgroundThread_withCallback_(
            NSURL.URLWithString_(url),
            callback
        )


class _NSURLSessionBackgroundReader(NSObject):

    def init(self):
        self = objc.super(_NSURLSessionBackgroundReader, self).init()
        self._session = None
        self._task = None
        self._callback = None
        self._done = True
        self._data = NSMutableData.alloc().init()
        self._config = NSURLSessionConfiguration.defaultSessionConfiguration()
        self._config.setWaitsForConnectivity_(True)
        return self

    def setTimeout_(self, timeout):
        self._config.setTimeoutIntervalForResource_(timeout)

    def makeSessionWithTimeout_(self, timeout):
        self.setTimeout_(timeout)
        if self._session is None:
            self._session = NSURLSession.sessionWithConfiguration_delegate_delegateQueue_(
                self._config, self, None)

    def fetchURLOnBackgroundThread_withCallback_(self, url, callback):
        if self._done:
            self._task = self._session.dataTaskWithURL_(url)
            self._callback = callback
            self._done = False
            self._data = NSMutableData.alloc().init()
            self._task.resume()
        else:
            raise RuntimeError(
                "Cannot fetch {}, busy downloading: {}".format(
                    url, str(self._task.currentRequest().URL())
                )
            )

    def URLSession_dataTask_didReceiveData_(self, session, task, data):
        self._data.appendData_(data)

    def URLSession_task_didCompleteWithError_(self, session, task, error):
        if self._callback is not None:
            # callAfter gets executed on the main thread
            callAfter(
                self._callback,

                # no need to send over an NSURL, so we cast it to a string
                str(self._task.currentRequest().URL()),

                # @@we could turn this into some sort of Python byte array
                self._data,

                # @@it’d be nice if we could send something more Pythonic
                # than a raw NSError over, but for now this should do
                error
            )

            # @@calling finishTasksAndInvalidate will render the session unusable
            # for further processing, but not calling it could potentially lead
            # to memory leaks...
            # self._session.finishTasksAndInvalidate()
            self._done = True

    def done(self):
        return self._done
