import os
import io
import zipfile
import tempfile
import shutil
import logging
import plistlib
import yaml

from packaging.version import Version
from urllib.parse import urlparse

from Foundation import NSString, NSUTF8StringEncoding
from AppKit import NSImage, NSWorkspace, NSWorkspaceLaunchDefault
from AppKit import NSWorkspaceLaunchWithoutActivation, NSURL
from AppKit import NSColor, NSBezierPath

from mojo.extensions import ExtensionBundle
from mojo.events import postEvent

from mechanic2 import DefaultURLReader, CachingURLReader, URLReaderError
from mechanic2.mechanicTools import remember, clearRemembered, findExtensionInRoot
from mechanic2.mechanicTools import ExtensionRepoError


logger = logging.getLogger("Mechanic")


EXTENSION_ICON_DID_LOAD_EVENT_KEY = 'com.robofontmechanic.extensionIconDidLoad'
EXTENSION_DID_CHECK_FOR_UPDATES_EVENT_KEY = 'com.robofontmechanic.extensionDidCheckForUpdates'
EXTENSION_DID_REMOTE_INSTALL_EVENT_KEY = 'com.robofontmechanic.extensionDidRemoteInstall'
EXTENSION_DID_UNINSTALL_EVENT_KEY = 'com.robofontmechanic.extensionDidUninstall'


class BaseExtensionItem(object):

    def __init__(self, data, checkForUpdates=True):
        valid, report = self.validateData(data)
        if not valid:
            raise ExtensionRepoError(report)
        self._data = data
        self._shouldCheckForUpdates = checkForUpdates
        self._needsUpdate = False
        self._extensionIcon = None
        self._showMessages = False
        self._remoteVersion = None
        self._init()

    def _init(self):
        pass

    def resetRemembered(self):
        clearRemembered(self)

    @remember
    def isExtensionInstalled(self):
        bundle = self.extensionBundle()
        # return if the bundle exists
        return bundle.bundleExists()

    def extensionName(self):
        """
        Return the extension bundle name.
        """
        return self._data["extensionName"]

    def extensionDeveloper(self):
        """
        Return the extension developer.
        (not required)
        """
        return self._data.get("developer", "")

    def extensionDeveloperURL(self):
        """
        Return the extension developer url.
        (not required)
        """
        return self._data.get("developerURL", "")

    def extensionDescription(self):
        """
        Return the extension desciption.
        """
        return self._data["description"]

    def extensionTags(self):
        """
        Return the extension tags.
        (not required).
        """
        return self._data.get("tags", [])

    def extensionPrice(self):
        """
        Return the extension price.
        (not required).
        """
        return self._data.get("price", "")

    def isExtensionFromStore(self):
        """
        Return if the extension is hosted in the extension store
        """
        return False

    def _processExtensionIcon(self, url, data, error):
        if error is None and len(data) > 0:
            image = NSImage.alloc().initWithData_(data)
            self._extensionIcon = image
            postEvent(EXTENSION_ICON_DID_LOAD_EVENT_KEY, item=self, iconURL=self.extensionIconURL())

    def _fetchExtensionIcon(self, iconURL):
        CachingURLReader.fetch(iconURL, self._processExtensionIcon)

    @remember
    def extensionIconPlaceholder(self):
        width = 200
        height = 200
        image = NSImage.alloc().initWithSize_((width, height))
        image.lockFocus()
        path = NSBezierPath.bezierPathWithOvalInRect_(((0, 0), (width, height)))
        color1 = NSColor.disabledControlTextColor()
        color1.set()
        path.fill()
        image.unlockFocus()
        return image

    def extensionIcon(self):
        if self._extensionIcon is None:
            iconURL = self.extensionIconURL()
            if iconURL is not None:
                self._fetchExtensionIcon(iconURL)
                self._extensionIcon = self.extensionIconPlaceholder()
        return self._extensionIcon

    def extensionIconURL(self):
        """
        Return the URL to the extension icon.
        (not required).
        """
        return self._data.get("icon", None)

    @remember
    def extensionSearchString(self):
        """
        Return the extension search string.
        (not required).
        """
        return " ".join([i.lower() for i in [
            self.extensionName(),
            self.extensionDeveloper(),
            self.extensionDescription(),
            ("", "?update?")[self.extensionNeedsUpdate()],
            ("", "?installed?")[self.isExtensionInstalled()],
            ("", "?not_installed?")[not self.isExtensionInstalled()],
            " ".join(self.extensionTags())
        ]])

    # updates

    @remember
    def extensionVersion(self):
        bundle = self.extensionBundle()
        # check if the bundle exists
        if bundle.bundleExists():
            return bundle.version
        return None

    def extensionNeedsUpdate(self):
        """
        Return bool if the extension needs an update.
        """
        return self._needsUpdate

    def hasInstallErrors(self):
        return "installErrors" in self._data

    def installErrors(self):
        return self._data.get("installErrors", None)

    # download and install

    def _remoteInstallCallback(self, url, data, error):

        if "installErrors" in self._data:
            del self._data["installErrors"]

        def reportError(message, error=None):
            self._data["installErrors"] = message
            logger.error(message)
            if error:
                logger.error(error)
            postEvent(EXTENSION_DID_REMOTE_INSTALL_EVENT_KEY, item=self)
            raise ExtensionRepoError(message)

        if error:
            message = "Could not download the extension zip file for: '%s' at url: '%s'" % (self.extensionName(), url)
            reportError(message, error)

        # create a temp folder
        tempFolder = tempfile.mkdtemp()
        try:
            # try to extract the zip
            # and fail silently with a custom message
            with zipfile.ZipFile(io.BytesIO(data.bytes())) as z:
                z.extractall(tempFolder)
        except Exception as e:
            message = "Could not extract the extension zip file for: '%s' at url: '%s'" % (self.extensionName(), url)
            reportError(message, e)

        # find the extension path
        extensionPath = findExtensionInRoot(os.path.basename(self.extensionPath), tempFolder)
        if extensionPath:
            # if found get the bundle and install it
            bundle = ExtensionBundle(path=extensionPath)
            succes, installMessage = bundle.install(showMessages=self._showMessages)
            if not succes:
                # raise an custom error when the extension cannot be installed
                reportError(installMessage)
            self.resetRemembered()
        else:
            # raise an custom error when the extension is not found in the zip
            message = "Could not find the extension: '%s'" % self.extensionPath
            reportError(message)

        # remove the temp folder with the extracted zip
        shutil.rmtree(tempFolder)

        # clear the cache for this extension icon so it may be reloaded
        if self.extensionIconURL():
            CachingURLReader.invalidate_cache_for_url(self.extensionIconURL())
            self._extensionIcon = None

        self._needsUpdate = False
        postEvent(EXTENSION_DID_REMOTE_INSTALL_EVENT_KEY, item=self)

    def remoteInstall(self, forcedUpdate=False, showMessages=False):
        """
        Install the extension from the remote. This will call `extensionNeedsUpdate()`

        Optional set `forcedUpdate` to `True` if its needed to install the extension anyhow
        """
        self._showMessages = showMessages

        if self.isExtensionInstalled() and not self.extensionNeedsUpdate() and not forcedUpdate:
            # dont download and install if the current intall is newer (only when it forced)
            return

        # get the zip path
        zipPath = self.remoteZipPath()

        # performing the background URL fetching operation
        DefaultURLReader.fetch(zipPath, self._remoteInstallCallback)

    def remoteZipPath(self):
        # subclass must overwrite this method
        raise NotImplementedError

    def remoteVersion(self):
        # subclass must overwrite this method
        raise NotImplementedError

    def remoteIsBeta(self):
        return "b" in self.remoteVersion()

    def remoteURL(self):
        # subclass must overwrite this method
        raise NotImplementedError

    def releasesURL(self):
        # subclass must overwrite this method
        raise NotImplementedError

    def releaseJsonURL(self):
        # subclass must overwrite this method
        raise NotImplementedError

    def checkForUpdates(self):
        # subclass must overwrite this method
        raise NotImplementedError

    validationRequiredKeys = []
    validationNotRequiredKeys = []

    def validateData(self, data):
        # subclass can overwrite this method
        report = []
        valid = []

        def _validateKeys(keys, isRequired=True):
            for key, clss in keys:
                if isRequired and key not in data:
                    valid.append(False)
                    report.append("'%s' key is required" % key)
                elif key in data and not isinstance(data[key], clss):
                    valid.append(False)
                    if isinstance(clss, tuple):
                        clssName = " or ".join([c.__name__ for c in clss])
                    else:
                        clssName = clss.__name__
                    report.append("'%s' key must be a '%s', a '%s' is given." % (key, clssName, data[key].__class__.__name__))

        _validateKeys(self.validationRequiredKeys, isRequired=True)
        _validateKeys(self.validationNotRequiredKeys, isRequired=False)

        valid = all(valid)
        if report:
            report = "Incoming data not valid: %s." % ", ".join(report)
        return valid, report

    # helpers

    def extensionBundle(self):
        # get the bundleName
        bundleName = self.extensionPath.split("/")[-1]
        # get the bundle
        return ExtensionBundle(bundleName)

    def extensionUninstall(self):
        bundle = self.extensionBundle()
        if bundle.bundleExists():
            if self.extensionIconURL():
                CachingURLReader.invalidate_cache_for_url(self.extensionIconURL())
                self._extensionIcon = None
            bundle.deinstall()
            self.resetRemembered()
            postEvent(EXTENSION_DID_UNINSTALL_EVENT_KEY, item=self)

    def openUrl(self, url, background=False):
        ws = NSWorkspace.sharedWorkspace()
        option = NSWorkspaceLaunchDefault
        if background:
            option = NSWorkspaceLaunchWithoutActivation
        ws.openURL_options_configuration_error_(
            NSURL.URLWithString_(url),
            option,
            dict(),
            None
        )

    def openRemoteURL(self, background=False):
        if self.hasInstallErrors():
            url = self.releasesURL()
            if url is None:
                # fallback to the remote url
                url = self.remoteURL()
        else:
            url = self.remoteURL()

        self.openUrl(url, background=background)


class ExtensionRepositoryItem(BaseExtensionItem):

    validationRequiredKeys = [
        ("repository", str),
        ("extensionPath", str),
    ]
    validationNotRequiredKeys = [
        ("infoPath", str),
        ("zipPath", str),
        ("extensionName", str),
        ("developer", str),
        ("developerURL", str),
        ("description", str),
        ("tags", (list, tuple)),
    ]

    def _init(self):
        self.repository = self._data["repository"]
        self.extensionPath = self._data["extensionPath"]
        # optionally direct parts to online zip and info.plist
        self._remoteZipPath = self._data.get("zipPath")
        self._remoteInfoPath = self._data.get("infoPath")
        self._releasesPath = self._data.get("releasesPath")
        self._releaseJsonURL = self._data.get("releaseJsonURL")

        if "extensionName" not in self._data:
            self._data["extensionName"] = self.extensionPath.split("/")[-1]

        self.repositoryParsedURL = urlparse(self.repository)

        if self._shouldCheckForUpdates:
            self.checkForUpdates()

    # collection of supported services

    urlFormatters = dict(
        github=dict(
            zipPath="https://api.github.com/repos{repositoryPath}/zipball",
            infoPlistPath="https://raw.githubusercontent.com{repositoryPath}/master/{extensionPath}/info.plist",
            releasesPath="https://github.com{repositoryPath}/releases",
            releasesJsonPath="https://api.github.com/repos{repositoryPath}/releases",
        ),
        gitlab=dict(
            zipPath="https://gitlab.com{repositoryPath}/-/archive/master/{repositoryName}-master.zip",
            infoPlistPath="https://gitlab.com{repositoryPath}/raw/master/{extensionPath}/info.plist",
            releasesPath="https://gitlab.com{repositoryPath}/-/releases",
            releasesJsonPath=""
        ),
        bitbucket=dict(
            zipPath="https://bitbucket.org{repositoryPath}/get/master.zip",
            infoPlistPath="https://bitbucket.org{repositoryPath}/src/master/{extensionPath}/info.plist",
            releasesPath="https://bitbucket.org{repositoryPath}/downloads/?tab=tags",
            releasesJsonPath=""
        )
    )

    def _checkForUpdatesCallback(self, url, data, error):
        if error:
            # cannot get the contents of the info.plist file
            logger.error("Cannot read '%s' for '%s'" % (url, self.extensionName()))
            logger.error(error)

        try:
            # try to parse the info.plist from string
            # and fail silently with a custom message
            data = bytes(data)
            pathExtension = url.pathExtension()
            if pathExtension in ("yaml", "yml"):
                info = yaml.safe_load(data)
            else:
                info = plistlib.loads(data)

        except Exception as e:
            # cannot parse the plist
            info = {}
            logger.error("Cannot parse '%s' for '%s'" % (url, self.extensionName()))
            logger.error(e)

        # set the version
        self._remoteVersion = info.get("version", "0.0")
        if self._remoteVersion is not None:
            # flag the extension as needing an update
            extensionVersion = self.extensionVersion()
            if extensionVersion is None:
                self._needsUpdate = False
            else:
                self._needsUpdate = Version(extensionVersion) < Version(self.remoteVersion())

        postEvent(EXTENSION_DID_CHECK_FOR_UPDATES_EVENT_KEY, item=self)

    def checkForUpdates(self):
        DefaultURLReader.fetch(self.remoteInfoPath(), self._checkForUpdatesCallback)

    def remoteZipPath(self):
        """
        Return the url to the zip file based on the formatters and supported services.
        If a `remoteZipPath` is given this will be returned.
        """
        if self._remoteZipPath is None:
            # get the formattter base on the service
            formatter = self.urlFormatters[self.service()]["zipPath"]
            # format the with given data
            self._remoteZipPath = formatter.format(
                repositoryPath=self.repositoryParsedURL.path,
                repositoryName=self.extensionName(),
                extensionPath=self.extensionPath
            )
        return self._remoteZipPath

    # info path

    def remoteInfoPath(self):
        """
        Return the url to the info.plist file based on the formatters and supported services.
        If a `remoteInfoPath` is given this will be returned.
        """
        if self._remoteInfoPath is None:
            # get the formatter base on the service
            formatter = self.urlFormatters[self.service()]["infoPlistPath"]
            # format the info with the given data
            self._remoteInfoPath = formatter.format(
                repositoryPath=self.repositoryParsedURL.path,
                repositoryName=self.extensionName(),
                extensionPath=self.extensionPath
            )
        return self._remoteInfoPath

    def remoteURL(self):
        return self.repository

    def releasesURL(self):
        if self._releasesPath is None:
            formatter = self.urlFormatters[self.service()].get("releasesPath")
            # format the info with the given data
            self._releasesPath = formatter.format(
                repositoryPath=self.repositoryParsedURL.path,
                repositoryName=self.extensionName(),
                extensionPath=self.extensionPath
            )
        return self._releasesPath

    def releaseJsonURL(self):
        if self._releaseJsonURL is None:
            formatter = self.urlFormatters[self.service()].get("releasesJsonPath")
            # format the info with the given data
            self._releaseJsonURL = formatter.format(
                repositoryPath=self.repositoryParsedURL.path,
                repositoryName=self.extensionName(),
                extensionPath=self.extensionPath
            )
        return self._releaseJsonURL

    def remoteVersion(self):
        """
        Return the version of the repository, retrieved from the `info.plist`.
        """
        return self._remoteVersion

    # helpers

    @remember
    def service(self):
        """
        Return the service. Raise an error is there is unsupported service.
        """
        if self.isGithub():
            return "github"
        elif self.isGitlab():
            return "gitlab"
        elif self.isBitbucket():
            return "bitbucket"
        raise ExtensionRepoError("Unsupported service: '%s'" % self.repositoryParsedURL.netloc)

    def isGithub(self):
        return "github.com/" in self.repository

    def isGitlab(self):
        return "gitlab.com/" in self.repository

    def isBitbucket(self):
        return "bitbucket.org/" in self.repository


class ExtensionStoreItem(BaseExtensionItem):

    validationRequiredKeys = [
        ("version", str),
        ("link", str),
        ("purchaseURL", str),
    ]

    validationNotRequiredKeys = [
        ("extensionName", str),
        ("developer", str),
        ("developerURL", str),
        ("description", str),
        ("tags", list),
        ("date", str),
        ("releasesURL", str),
        ("releaseJsonURL", str),
    ]

    def _init(self):
        # set the extension
        self.extensionPath = "%s.roboFontExt" % self.extensionName()

    def remoteURL(self):
        return self._data["link"]

    def releasesURL(self):
        return self._data.get("releasesURL")

    def releaseJsonURL(self):
        return self._data.get("releaseJsonURL")

    def remoteVersion(self):
        return self._data["version"]

    def service(self):
        return "Extension Store"

    def checkForUpdates(self):
        if self.remoteVersion() is not None:
            # flag the extension as needing an update
            extensionVersion = self.extensionVersion()
            if extensionVersion is None:
                self._needsUpdate = False
            else:
                self._needsUpdate = Version(extensionVersion) < Version(self.remoteVersion())
        postEvent(EXTENSION_DID_CHECK_FOR_UPDATES_EVENT_KEY, item=self)

    @remember
    def remoteZipPath(self):
        extensionStoreKey = self.extensionStoreKey()
        if extensionStoreKey is None:
            # not an extension coming from the extension store
            return None
        url = "%s/%s.zip" % (self.remoteURL() + extensionStoreKey, self.extensionPath)
        return url

    # store

    def isExtensionFromStore(self):
        """
        Return if the extension is hosted in the extension store
        """
        return True

    @remember
    def extensionStoreKey(self):
        bundle = self.extensionBundle()
        extensionStoreKey = bundle.getInfo("com.roboFont.extensionStore")
        if extensionStoreKey is None:
            # this was a typo but some extension will have this...
            extensionStoreKey = bundle.getInfo("com.roboFont.extenionsStore")
        return extensionStoreKey

    def remotePurchaseURL(self):
        return self._data["purchaseURL"]

    def openRemotePurchaseURL(self, background=False):
        url = self.remotePurchaseURL()
        self.openUrl(url, background=background)


class ExtensionYamlItem(ExtensionRepositoryItem):

    def __init__(self, data, checkForUpdates=True):
        if "tags" in data:
            data["tags"] = list(data["tags"])
        super(ExtensionYamlItem, self).__init__(data, checkForUpdates)
