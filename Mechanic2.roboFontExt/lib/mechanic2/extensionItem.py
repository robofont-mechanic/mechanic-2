import AppKit
from distutils.version import LooseVersion
import zipfile
import tempfile
import shutil
import os
from io import BytesIO
from urllib.parse import urlparse

from ufoLib.plistlib import readPlistFromString

from mojo.extensions import ExtensionBundle

from .mechacnicTools import remember, clearRemembered, findExtensionInRoot, getDataFromURL, ExtensionRepoError


class BaseExtensionItem(object):

    def __init__(self, data):
        valid, report = self.validateData(data)
        if not valid:
            raise ExtensionRepoError(report)
        self._data = data
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

    @remember
    def extensionIcon(self):
        imageURL = self._data.get("icon", None)
        if imageURL:
            data = getDataFromURL(imageURL)
            if data is None:
                return None
            data = AppKit.NSData.dataWithBytes_length_(data, len(data))
            image = AppKit.NSImage.alloc().initWithData_(data)
            return image
        return None

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
            " ".join(self.extensionTags())
        ]])

    # updates

    @remember
    def extensionVersion(self):
        bundle = self.extensionBundle()
        # compare the bundle with the version from the repository
        if bundle.bundleExists():
            return LooseVersion(bundle.version)
        return None

    @remember
    def extensionNeedsUpdate(self):
        """
        Return bool if the extension needs an update.
        """
        # get the version from the repository
        remoteVersion = self.remoteVersion()
        if remoteVersion is None:
            # could be None if it fails
            return False
        extensionVersion = self.extensionVersion()
        if extensionVersion is None:
            # could be None if it fails
            return False
        return extensionVersion < remoteVersion

    # download and install

    def remoteInstall(self, forcedUpdate=False):
        """
        Install the extension from the remote. This will call `extensionNeedsUpdate()`

        Optional set `forcedUpdate` to `True` if its needed to install the extension anyhow
        """
        if self.isExtensionInstalled() and not self.extensionNeedsUpdate() and not forcedUpdate:
            # dont download and install if the current intall is newer (only when it forced)
            return
        # get the zip path
        zipPath = self.remoteZipPath()

        try:
            # try to download the zip file
            # and fail silently with a custom error message
            contents = getDataFromURL(zipPath)
        except Exception as message:
            print(message)
            raise ExtensionRepoError("Could not download the extension zip file for: '%s'" % self.extensionName)
        # create a temp folder
        tempFolder = tempfile.mkdtemp()
        try:
            # try to extract the zip
            # and fail silently with a custom message
            with zipfile.ZipFile(BytesIO(contents)) as z:
                z.extractall(tempFolder)
        except Exception as message:
            print(message)
            raise ExtensionRepoError("Could not extract the extension zip file for: '%s'" % self.extensionName)
        # find the extension path
        extensionPath = findExtensionInRoot(os.path.basename(self.extensionPath), tempFolder)
        if extensionPath:
            # if found get the bundle and install it
            bundle = ExtensionBundle(path=extensionPath)
            bundle.install()
            self.resetRemembered()
        else:
            # raise an custom error when the extension is not found in the zip
            raise ExtensionRepoError("Could not find the extension: '%s'" % self.extensionPath)
        # remove the temp folder with the extracted zip
        shutil.rmtree(tempFolder)

    def remoteZipPath(self):
        # subclass must overwrite this method
        raise NotImplementedError

    def remoteVersion(self):
        # subclass must overwrite this method
        raise NotImplementedError

    def remoteURL(self):
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
        bundleName = self.extensionName()
        # get the bundle
        return ExtensionBundle(bundleName)

    def extensionUninstall(self):
        bundle = self.extensionBundle()
        if bundle.bundleExists():
            bundle.deinstall()
            self.resetRemembered()

    def openUrl(self, url):
        ws = AppKit.NSWorkspace.sharedWorkspace()
        ws.openURL_(AppKit.NSURL.URLWithString_(url))

    def openRemoteURL(self):
        url = self.remoteURL()
        self.openUrl(url)


class ExtensionRepository(BaseExtensionItem):

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

        if "extensionName" not in self._data:
            self._data["extensionName"] = self.extensionPath.split("/")[-1]

        self.repositoryParsedURL = urlparse(self.repository)

    # collection of supported services

    urlFormatters = dict(
        github=dict(
            zipPath="https://github.com{repositoryPath}/archive/master.zip",
            infoPlistPath="https://raw.githubusercontent.com{repositoryPath}/master/{extensionPath}/info.plist"
        ),
        gitlab=dict(
            zipPath="https://gitlab.com{repositoryPath}/-/archive/master/{repositoryName}-master.zip",
            infoPlistPath="https://gitlab.com{repositoryPath}/raw/master/{extensionPath}/info.plist"
        ),
        bitbucket=dict(
            zipPath="https://bitbucket.org{repositoryPath}/get/master.zip",
            infoPlistPath="https://bitbucket.org{repositoryPath}/src/master/{extensionPath}/info.plist"
        )
    )

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
            self._remoteZipPath = self._remoteZipPath.replace(" ", "%20")
        return self._remoteZipPath

    # info path

    def remoteInfoPath(self):
        """
        Return the url to the info.plist file based on the formatters and supported services.
        If a `remoteInfoPath` is given this will be returned.
        """
        if self._remoteInfoPath is None:
            # get the formattter base ont he service
            formatter = self.urlFormatters[self.service()]["infoPlistPath"]
            # format the with given data
            self._remoteInfoPath = formatter.format(
                repositoryPath=self.repositoryParsedURL.path,
                repositoryName=self.extensionName(),
                extensionPath=self.extensionPath
            )
        return self._remoteInfoPath.replace(" ", "%20")

    def remoteURL(self):
        return self.repository

    @remember
    def remoteVersion(self):
        """
        Return the version of the repository, retrieved from the `info.plist`.
        """
        # get the info.plist path
        path = self.remoteInfoPath()
        infoContents = ""
        try:
            # try to download the info.plist
            # and fail silently with a custom message
            infoContents = getDataFromURL(path)
        except Exception as message:
            # can not get the contens of the info.plist file
            print(message)
            return None
        try:
            # try to parse the info.plist from string
            # and fail silently with a custom message
            info = readPlistFromString(infoContents)
        except Exception as message:
            # can not parse the plist
            print("%s for '%s'" % (message, path))
            return None
        # get the version
        version = info.get("version")
        # the version must be set
        if version is None:
            return None
        # return the version from the info
        return LooseVersion(version)

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
        ("date", str)
    ]

    def _init(self):
        # set the extension
        self.extensionPath = "%s.roboFontExt" % self.extensionName()

    def remoteURL(self):
        return self._data["link"]

    def remoteVersion(self):
        return self._data["version"]

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
        extensionStoreKey = bundle.getInfo("com.roboFont.extenionsStore")
        return extensionStoreKey

    def remotePurchageURL(self):
        return self._data["purchaseURL"]

    def openRemotePurchageURL(self):
        url = self.remotePurchageURL()
        self.openUrl(url)


class ExtensionYamlItem(ExtensionRepository):

    def __init__(self, data):
        if "tags" in data:
            data["tags"] = list(data["tags"])
        super(ExtensionYamlItem, self).__init__(data)

