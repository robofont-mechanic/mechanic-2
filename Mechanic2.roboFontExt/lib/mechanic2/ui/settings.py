import json
import yaml
import logging
import vanilla

import AppKit
from Foundation import NSString, NSUTF8StringEncoding

from defconAppKit.windows.baseWindow import BaseWindowController

from mojo.extensions import getExtensionDefault, setExtensionDefault, registerExtensionDefaults, removeExtensionDefault
from mojo.UI import setPassword, getPassword, deletePassword

from mechanic2 import DefaultURLReader, GithubDefaultURLReader
from mechanic2.extensionItem import ExtensionYamlItem


logger = logging.getLogger("Mechanic")


genericListPboardType = "mechanicListPBoardType"


extensionStoreDataURL = "https://extensionstore.robofont.com/data.json"
mechanicDataURL = "https://robofontmechanic.com/api/v2/registry.json"


def registerMechanicDefaults(reset=False):
    defaults = {
        "com.mechanic.urlstreams": [extensionStoreDataURL, mechanicDataURL],
        "com.mechanic.checkForUpdate": True,
        "com.mechanic.singleExtensionItems": [],
        "com.mechanic.lastUpdateCheck": 0,
    }
    if reset:
        for key in defaults:
            removeExtensionDefault(key)
    registerExtensionDefaults(defaults)


registerMechanicDefaults()


class AddURLSheet(BaseWindowController):

    def __init__(self, parentWindow, callback, existingURLs):
        self._callback = callback
        self._existingURLs = existingURLs
        self._valid = False
        self._validation_report = ""

        self.w = vanilla.Sheet((350, 85), parentWindow=parentWindow)

        self.w.urlText = vanilla.TextBox((10, 22, -10, 22), "URL:")
        self.w.url = vanilla.EditText((60, 20, -10, 22))

        self.w.message = vanilla.TextBox((10, -25, -10, 22), "(A valid extension json stream)", sizeStyle="mini")

        self.w.addButton = vanilla.Button((-70, -30, -10, 20), "Add", callback=self.addCallback, sizeStyle="small")
        self.w.setDefaultButton(self.w.addButton)

        self.w.closeButton = vanilla.Button((-150, -30, -80, 20), "Cancel", callback=self.closeCallback, sizeStyle="small")
        self.w.closeButton.bind(".", ["command"])
        self.w.closeButton.bind(chr(27), [])

        self.w.open()

    def get(self):
        return self.w.url.get()

    def _checkURLCallback(self, url, data, error):
        self._valid = True
        self._validation_report = ""

        if error:
            self._valid = False
            self._validation_report = "Cannot load url '%s'" % url
            logger.error(self._validation_report)
            self.showMessage("Invalid URL", self._validation_report)
            return

        data = NSString.alloc().initWithData_encoding_(data, NSUTF8StringEncoding)
        try:
            _data = json.loads(data)
            extensionData = _data['extensions']
        except Exception as e:
            self._valid = False
            self._validation_report = "Cannot validate url '%s'" % url
            logger.error(self._validation_report)
            logger.error(e)
            self.showMessage("Invalid URL", self._validation_report)
            return

        if url in self._existingURLs:
            self._valid = False
            self._validation_report = "URL already existing"
            self.showMessage("Invalid URL", self._validation_report)
            return

        if not self._valid:
            self.showMessage("Not a valid extension json URL.", "The url '%s' is not a valid. \n\n%s" % (self.w.url.get(), self._validation_report))

        # everything’s valid, proceed with the add
        if self._callback:
            self._callback(self)

    def addCallback(self, sender):
        # check the URL before adding
        url = self.w.url.get()
        DefaultURLReader.fetch(url, self._checkURLCallback)
        return True

    def closeCallback(self, sender):
        self.w.close()


class Settings(BaseWindowController):

    def __init__(self, parentWindow, callback=None, debug=False):

        self._callback = callback
        self._shouldCallCallback = False

        if debug:
            self.w = vanilla.Window((400, 460))
        else:
            self.w = vanilla.Sheet((400, 460), parentWindow=parentWindow)

        y = 10
        self.w.checkForUpdate = vanilla.CheckBox((10, y, -10, 22), "Check for Updates on Startup.")
        y += 30

        self.w.h1 = vanilla.HorizontalLine((0, y, 0, 1))
        y += 10

        columnDescriptions = [
            dict(title="extensions json url stream", key="url")
        ]
        self.w.urls = vanilla.List((10, y, -10, 120),
            [],
            columnDescriptions=columnDescriptions,
            selfDropSettings=dict(type=genericListPboardType, operation=AppKit.NSDragOperationMove, callback=self.genericDropSelfCallback),
            dragSettings=dict(type=genericListPboardType, callback=self.genericDragCallback),
        )
        y += 130
        segmentDescriptions = [dict(title="+"), dict(title="-")]
        self.w.addURL = vanilla.SegmentedButton((12, y, 50, 20), segmentDescriptions, selectionStyle="momentary", callback=self.addDelURLCallback)
        #self.w.addURL.getNSSegmentedButton().setSegmentStyle_(AppKit.NSSegmentStyleSmallSquare)
        y += 30

        self.w.h2 = vanilla.HorizontalLine((0, y, 0, 1))
        y += 10

        columnDescriptions = [
            dict(title="single extension items", key="extensionName")
        ]
        self.w.singleExtenions = vanilla.List((10, y, -10, 120),
            [],
            columnDescriptions=columnDescriptions,
            selfDropSettings=dict(type=genericListPboardType, operation=AppKit.NSDragOperationMove, callback=self.genericDropSelfCallback),
            dragSettings=dict(type=genericListPboardType, callback=self.genericDragCallback),
        )
        y += 130
        segmentDescriptions = [dict(title="+"), dict(title="-")]
        self.w.addSingleExtenions = vanilla.SegmentedButton((12, y+2, 50, 20), segmentDescriptions, selectionStyle="momentary", callback=self.addDelSingleExtensionCallback)
        #self.w.addSingleExtenions.getNSSegmentedButton().setSegmentStyle_(AppKit.NSSegmentStyleSmallSquare)
        y += 30

        self.w.h3 = vanilla.HorizontalLine((0, y, 0, 1))
        y += 10

        self.w.githubTokenText = vanilla.TextBox((10, y, 100, 22), "Github Token:")
        self.w.githubToken = vanilla.SecureEditText((105, y, -10, 22))

        self.w.resetButton = vanilla.Button((10, -30, 60, 20), "Reset", callback=self.resetCallback, sizeStyle="small")

        self.w.cancelButton = vanilla.Button((-170, -30, -80, 20), "Cancel", callback=self.closeCallback, sizeStyle="small")
        self.w.cancelButton.bind(".", ["command"])
        self.w.cancelButton.bind(chr(27), [])

        self.w.okButton = vanilla.Button((-70, -30, -10, 20), "OK", callback=self.okCallback, sizeStyle="small")
        self.w.setDefaultButton(self.w.okButton)

        self.getFromDefaults()
        self.w.open()

    def getFromDefaults(self):
        # check for updates
        checkForUpdate = getExtensionDefault("com.mechanic.checkForUpdate")
        self.w.checkForUpdate.set(checkForUpdate)
        # urls
        urls = list(getExtensionDefault("com.mechanic.urlstreams"))
        urls = self.createURLItems(urls)
        self.w.urls.set(urls)
        # single items
        singleItems = list(getExtensionDefault("com.mechanic.singleExtensionItems"))
        self.w.singleExtenions.set(singleItems)
        # github token
        self.w.githubToken.set(getPassword(service="com.mechanic.githubToken", username=AppKit.NSUserName()))

    def saveToDefaults(self):
        # check for updates
        checkForUpdate = self.w.checkForUpdate.get()
        setExtensionDefault("com.mechanic.checkForUpdate", checkForUpdate)
        # urls
        urls = self.getURLItems()
        setExtensionDefault("com.mechanic.urlstreams", urls)
        # single items
        singleItems = list(self.w.singleExtenions.get())
        setExtensionDefault("com.mechanic.singleExtensionItems", singleItems)
        # github token
        githubToken = self.w.githubToken.get()
        setPassword(service="com.mechanic.githubToken", username=str(AppKit.NSUserName()), password=str(githubToken))
        if githubToken:
            GithubDefaultURLReader.setHeaders(dict(Authorization='token ' + githubToken))
        else:
            GithubDefaultURLReader.setHeaders(None)

    def createURLItems(self, urls):
        return [self.createURLItem(url) for url in urls]

    def createURLItem(self, url):
        return dict(url=url)

    def getURLItems(self):
        return [item["url"] for item in self.w.urls]

    def getSingleExtensionItems(self):
        return [item["url"] for item in self.w.singleExtenions]

    def addURL(self):
        def _addURL(sender):
            url = sender.get()
            if url:
                url = self.createURLItem(url)
                self.w.urls.append(url)
        AddURLSheet(parentWindow=self.w, callback=_addURL, existingURLs=self.getURLItems())

    def addDelURLCallback(self, sender):
        i = sender.get()
        if i == 0:
            self.addURL()
        elif i == 1:
            self.genericDelItem(self.w.urls)
        self._shouldCallCallback = True

    def addSingleExtension(self):
        def _increaseVersion(sourceName, checkList, count=None):
            if count is None:
                count = 0
            if count == 0:
                newName = sourceName
            else:
                newName = "%s (%s)" % (sourceName, count)
            if newName in checkList:
                return _increaseVersion(sourceName, checkList, count + 1)
            return newName

        def _addSingleExtension(paths):
            existingItems = list(self.w.singleExtenions)
            existingItemsTitle = [item["extensionName"] for item in existingItems]
            items = []
            for path in paths:
                item = None
                try:
                    with open(path, "rb") as f:
                        item = yaml.safe_load(f.read())
                except Exception as e:
                    logger.error("Cannot read single extension item '%s'" % path)
                    logger.error(e)
                if item is not None:
                    if item not in existingItems:
                        item["extensionName"] = _increaseVersion(item["extensionName"], existingItemsTitle)
                        ExtensionYamlItem(item)
                        items.append(item)
                    else:
                        self.showMessage("Single extension already active", "Please remove '%s', to be able to re-activate the extension item." % item["extensionName"])
            self.w.singleExtenions.extend(items)
        self.showGetFile(["mechanic"], callback=_addSingleExtension, allowsMultipleSelection=True)

    def addDelSingleExtensionCallback(self, sender):
        i = sender.get()
        if i == 0:
            self.addSingleExtension()
        elif i == 1:
            self.genericDelItem(self.w.singleExtenions)
        self._shouldCallCallback = True

    def resetCallback(self, sender):
        def _reset(value):
            if value:
                registerMechanicDefaults(reset=True)
                self.getFromDefaults()
                self._shouldCallCallback = True

        self.showAskYesNo("Resetting Mechanic 2 defaults", "This will remove existing data.", callback=_reset)

    def okCallback(self, sender):
        self.saveToDefaults()
        self.closeCallback(sender)
        if self._shouldCallCallback and self._callback:
            self._callback(self)

    def closeCallback(self, sender):
        self.w.close()

    def genericDelItem(self, listObj):
        for i in reversed(listObj.getSelection()):
            del listObj[i]

    def genericDropSelfCallback(self, sender, dropInfo):
        isProposal = dropInfo["isProposal"]

        if not isProposal:
            indexes = [int(i) for i in sorted(dropInfo["data"])]
            indexes.sort()
            rowIndex = dropInfo["rowIndex"]

            items = sender.get()

            toMove = [items[index] for index in indexes]

            for index in reversed(indexes):
                del items[index]

            rowIndex -= len([index for index in indexes if index < rowIndex])
            for font in toMove:
                items.insert(rowIndex, font)
                rowIndex += 1

            sender.set(items)
        return True

    def genericDragCallback(self, sender, indexes):
        return indexes


if __name__ == "__main__":
    Settings(None, debug=True)

