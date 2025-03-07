import json
import logging
import time
import vanilla

from urllib.parse import urlparse

from Foundation import NSObject, NSString, NSUTF8StringEncoding
from AppKit import NSToolbarFlexibleSpaceItemIdentifier, NSPredicate
from AppKit import NSEvent, NSAlternateKeyMask

from mojo.events import addObserver, removeObserver
from mojo.extensions import getExtensionDefault, setExtensionDefault, ExtensionBundle

from defconAppKit.windows.baseWindow import BaseWindowController

from mechanic2 import DefaultURLReader, GithubDefaultURLReader, URLReaderError
from mechanic2.ui.cells import MCExtensionCirleCell, MCImageTextFieldCell
from mechanic2.ui.formatters import MCExtensionDescriptionFormatter
from mechanic2.ui.settings import Settings, extensionStoreDataURL
from mechanic2.extensionItem import ExtensionRepositoryItem, ExtensionStoreItem
from mechanic2.extensionItem import ExtensionYamlItem
from mechanic2.extensionItem import EXTENSION_ICON_DID_LOAD_EVENT_KEY
from mechanic2.extensionItem import EXTENSION_DID_CHECK_FOR_UPDATES_EVENT_KEY
from mechanic2.extensionItem import EXTENSION_DID_REMOTE_INSTALL_EVENT_KEY
from mechanic2.extensionItem import EXTENSION_DID_UNINSTALL_EVENT_KEY


logger = logging.getLogger("Mechanic")

mechanic2ExtensionBundle = ExtensionBundle("Mechanic2")


class MechanicListItemPopoverController:

    """
    releaseJsonURL spec:
    (github release json)

    [
        dict(
            name=...                       str
            tag_name=...                   str
            html_url=...                   str
            prerelease=..                  bool
            draft=..                       bool
            zipball_url=..                 str
            assets=[
                name=..                    str
                browser_download_url=..    str
            ]
        ),
        ...
    ]
    """

    def __init__(self, item, listView):
        tableView = listView.getNSTableView()
        relativeRect = tableView.rectOfRow_(tableView.selectedRow())
        self.item = item
        if item.releaseJsonURL() and item.isGithub():
            # for now only github is supported
            GithubDefaultURLReader.fetch(item.releaseJsonURL(), self._makeExtensionReleaseItems)

        self.w = vanilla.Popover((370, 260), behavior="semitransient")
        self.w.releases = vanilla.List(
            (10, 10, -10, -40),
            [],
            columnDescriptions=[
                dict(title=f"{item.extensionName()} Releases", key="releaseName", editable=False),
                dict(title="β", key="preRelease", width=25, editable=False),
                dict(title="✎", key="draft", width=25, editable=False),
            ],
            doubleClickCallback=self.releasesDoubleClickCallback
        )

        self.w.installRelease = vanilla.Button((-150, -30, -10, 22), "Install Release", callback=self.installReleaseCallback)
        self.w.installRelease.show(False)
        self.w.openInBrowser = vanilla.Button((10, -30, -170, 22), f"View on {self.item.service().title()}", callback=self.openInBrowserCallback)
        self.w.open(parentView=tableView, relativeRect=relativeRect, preferredEdge="bottom")

    def getPopover(self):
        return self.w

    def releasesDoubleClickCallback(self, sender):
        selection = self.w.releases.getSelection()
        if selection:
            index = selection[0]
            releaseItem = self.w.releases[index]
            self.item.openUrl(url=releaseItem["html_url"], background=True)

    def _makeExtensionReleaseItems(self, url, data, error):
        if error:
            # cannot get the contents of the releases
            logger.error("Cannot read '%s' for '%s'" % (url, self.item.extensionName()))
            logger.error(error)

        try:
            # try to parse the release json from string
            # and fail silently with a custom message
            data = bytes(data)
            releaseData = json.loads(data)

        except Exception as e:
            # cannot parse the plist
            releaseData = []
            logger.error("Cannot parse '%s' for '%s'" % (url, self.item.extensionName()))
            logger.error(e)

        try:
            releaseItems = []
            for data in releaseData:
                releaseName = data.get("name")
                if not releaseName:
                    releaseName = data.get("tag_name")
                releaseItems.append(
                    dict(
                        releaseName=releaseName,
                        preRelease="•" if data.get("prerelease", False) else "",
                        draft="•" if data.get("draft", False) else "",
                        data=data
                    )
                )
        except Exception as e:
            releaseItems = []
            logger.error(f"Cannot extract release items for '{self.item.extensionName()}'")
            logger.error(releaseData)
            logger.error(e)
            if "message" in releaseData:
                # show the github message
                vanilla.dialogs.message(
                    messageText=f"Cannot extract release items for '{self.item.extensionName()}'.",
                    informativeText=f"Set a Github token in the Mechanic settings.\n\n{releaseData['message']}"
                )

        self.w.installRelease.show(len(releaseItems))
        self.w.releases.set(releaseItems)

    def installReleaseCallback(self, sender):
        selection = self.w.releases.getSelection()
        if selection:
            index = selection[0]
            releaseItem = self.w.releases[index]
            data = releaseItem["data"]
            zipPath = data["zipball_url"]
            if data["assets"]:
                for asset in data["assets"]:
                    if asset["name"].lower().endswith(".robofontext.zip"):
                        zipPath = asset["browser_download_url"]
            GithubDefaultURLReader.fetch(zipPath, self.item._remoteInstallCallback)

    def openInBrowserCallback(self, sender):
        self.item.openRemoteURL(background=True)


class MCExtensionListItem(NSObject):

    def __new__(cls, *args, **kwargs):
        return cls.alloc().init()

    def __init__(self, extensionObject=None):
        self._extensionObject = extensionObject

    def length(self):
        return 0

    def copyWithZone_(self, zone):
        new = self.__class__.allocWithZone_(zone).init()
        new._extensionObject = self._extensionObject
        return new

    def extensionController(self):
        return self

    def extensionObject(self):
        return self._extensionObject

    def extensionSearchString(self):
        return self._extensionObject.extensionSearchString()


class MechanicController(BaseWindowController):

    def __init__(self, checkForUpdates=False, shouldLoad=True):

        self.w = vanilla.Window((600, 300), f"Mechanic {mechanic2ExtensionBundle.version}", minSize=(550, 200))

        # building toolbar
        self._toolbarSearch = vanilla.SearchBox((0, 0, 300, 0), callback=self.toolbarSearch)
        self._toolbarSearch.getNSSearchField().setFrame_(((0, 0), (300, 22)))

        toolbarItems = [
            dict(
                itemIdentifier="search",
                label="Search",
                view=self._toolbarSearch.getNSSearchField(),
            ),
            dict(itemIdentifier=NSToolbarFlexibleSpaceItemIdentifier),
            dict(
                itemIdentifier="settings",
                label="Settings",
                imageNamed="prefToolbarMisc",
                callback=self.toolbarSettings,
            ),
        ]

        self.w.addToolbar(toolbarIdentifier="MechanicToolbar", toolbarItems=toolbarItems, addStandardItems=False, displayMode="icon")

        # building extension list

        columnDescriptions = [
            dict(title="", key="extensionController", width=25, cell=MCExtensionCirleCell.alloc().init(), editable=False),
            dict(title="Extension", key="extensionController",
                cell=MCImageTextFieldCell.alloc().init(),
                formatter=MCExtensionDescriptionFormatter.alloc().init(),
                editable=False),
        ]

        self.w.extensionList = vanilla.List((0, 0, -0, -38),
            [],
            columnDescriptions=columnDescriptions,
            showColumnTitles=False,
            selectionCallback=self.extensionListSelectionCallback,
            doubleClickCallback=self.extensionListDoubleClickCallback,
            allowsMultipleSelection=True,
            rowHeight=39
        )

        self.w.checkForUpdates = vanilla.Button((10, -30, 130, 22), "Check For Updates", callback=self.checkForUpdatesCallback, sizeStyle="small")
        self.w.checkForUpdatesInfo = vanilla.TextBox((146, -26, 120, 22), "", sizeStyle="small")

        self.w.purchaseButton = vanilla.Button((10, -30, 100, 22), "Purchase", callback=self.purchaseCallback)
        self.w.installButton = vanilla.Button((10, -30, 100, 22), "Install", callback=self.installCallback)
        self.w.uninstallButton = vanilla.Button((10, -30, 120, 22), "Uninstall", callback=self.uninstallCallback)
        self.w.updateButton = vanilla.Button((10, -30, 110, 22), "Update", callback=self.updateCallback)
        allButtons = [self.w.purchaseButton, self.w.installButton, self.w.uninstallButton, self.w.updateButton]
        for button in allButtons:
            button.show(False)

        self.w.extensionList.setSelection([])

        self.w.bind("close", self._windowWillCloseCallback)
        self.w.open()

        # flags
        self._shouldCheckForUpdates = checkForUpdates
        self._didCheckForUpdates = False
        self._extensionRepositoryItemsLoaded = False
        self._extensionStoreItemsLoaded = False
        self._canLoadSingleExtensions = True

        # progress updaters
        self._progress = None

        self._wrappedItems = []
        self._extensionsToCheck = []
        self._numExtensionsChecked = 0
        self._extensionsToUpdate = []
        self._numExtensionsUpdated = 0
        self._iconURLs = set()
        self._iconURLsForVisibleRows = set()

        addObserver(self, 'extensionIconDidLoad', EXTENSION_ICON_DID_LOAD_EVENT_KEY)
        addObserver(self, 'extensionDidCheckForUpdates', EXTENSION_DID_CHECK_FOR_UPDATES_EVENT_KEY)
        addObserver(self, 'extensionDidRemoteInstall', EXTENSION_DID_REMOTE_INSTALL_EVENT_KEY)
        addObserver(self, 'extensionDidUninstall', EXTENSION_DID_UNINSTALL_EVENT_KEY)

        if shouldLoad:
            self.loadExtensions()

    def _windowWillCloseCallback(self, sender):
        removeObserver(self, EXTENSION_ICON_DID_LOAD_EVENT_KEY)
        removeObserver(self, EXTENSION_DID_CHECK_FOR_UPDATES_EVENT_KEY)
        removeObserver(self, EXTENSION_DID_REMOTE_INSTALL_EVENT_KEY)
        removeObserver(self, EXTENSION_DID_UNINSTALL_EVENT_KEY)

    def _makeExtensionItem(self, extensionData, itemClass, url):
        try:
            item = MCExtensionListItem(
                itemClass(extensionData)
            )
            self._wrappedItems.append(item)
        except Exception as e:
            logger.error("Creating extension item '%s' from url '%s' failed." % (extensionData.get("extensionName", "unknown"), url))
            logger.error(e)

    def _decodeData(self, url, data, error):
        if error:
            logger.error("Cannot read url '%s'" % url)
            logger.error("Error '%s'" % error)
            return

        data = NSString.alloc().initWithData_encoding_(data, NSUTF8StringEncoding)
        try:
            extensionData = json.loads(data)
            return extensionData.get('extensions', [])
        except json.JSONDecodeError as e:
            logger.error("Cannot decode extension data at '%s'" % url)
            logger.error("Error '%s'" % e)

    def _makeExtensionStoreItems(self, url, data, error):
        _data = self._decodeData(url, data, error)
        if _data is not None:
            for extensionData in _data:
                self._makeExtensionItem(extensionData, ExtensionStoreItem, url)
        self._extensionStoreItemsLoaded = True
        self._checkExtensionsDidLoad()

    def _makeExtensionRepositories(self, url, data, error):
        _data = self._decodeData(url, data, error)
        if _data is not None:
            for extensionData in _data:
                self._makeExtensionItem(extensionData, ExtensionRepositoryItem, url)
        self._extensionRepositoryItemsLoaded = True
        self._checkExtensionsDidLoad()

    def _checkExtensionsDidLoad(self):
        if self._extensionRepositoryItemsLoaded and self._extensionStoreItemsLoaded:
            if self._canLoadSingleExtensions:
                self._canLoadSingleExtensions = False
                self._loadSingleExtensions()

    def _loadSingleExtensions(self):
        # make extension items for single extensions
        for singleExtension in getExtensionDefault("com.mechanic.singleExtensionItems"):
            try:
                item = MCExtensionListItem(
                    ExtensionYamlItem(singleExtension)
                )
                self._wrappedItems.append(item)
            except Exception as e:
                logger.error("Creating single extension item '%s' failed." % singleExtension.get("extensionName", "unknow"))
                logger.error(e)

        self._finishSettingExtensions()

    def _finishSettingExtensions(self):
        if self._progress is not None:
            self._progress.update("Setting Extensions...")

        # sort items by repo, YAML and leave store for last as before...
        _wrappedItemsOrder = [
            ExtensionRepositoryItem,
            ExtensionYamlItem,
            ExtensionStoreItem,
        ]
        self._wrappedItems.sort(key=lambda x: _wrappedItemsOrder.index(type(x.extensionObject())))

        # actually try to set the list with the current _wrappedItems
        self.setItems(self._wrappedItems)

        # initialize the list of icon URLs we have to process
        self._iconURLs = set()

        # prioritize loading and caching the extension icons for the rows which are visible
        tableView = self.w.extensionList.getNSTableView()
        rect = tableView.visibleRect()
        visibleRows = tableView.rowsInRect_(rect)
        self._iconURLsForVisibleRows = set()

        # start processing the visible rows
        for row in range(visibleRows.location, visibleRows.location + visibleRows.length):
            item = self._wrappedItems[row].extensionObject()
            iconURL = item.extensionIconURL()
            if iconURL is None:
                continue

            item.extensionIcon()
            self._iconURLs.add(iconURL)
            self._iconURLsForVisibleRows.add(iconURL)

        # continue by loading all the other extension icons
        for item in self._wrappedItems:
            iconURL = item.extensionObject().extensionIconURL()

            # skip the ones we’ve already processed
            if iconURL is None or iconURL in self._iconURLsForVisibleRows:
                continue

            item.extensionObject().extensionIcon()
            self._iconURLs.add(iconURL)

        if self._progress is not None:
            self._progress.close()
            self._progress = None

        if self._shouldCheckForUpdates:
            self._shouldCheckForUpdates = False
            self.checkForUpdates()

    def loadExtensions(self):
        self._wrappedItems = []
        self._canLoadSingleExtensions = True
        self._progress = self.startProgress("Loading extensions...")

        streams = getExtensionDefault("com.mechanic.urlstreams")
        for urlStream in streams:
            parsedExtensionStoreDataURL = urlparse(extensionStoreDataURL)
            parsedUrlStream = urlparse(urlStream)
            if parsedUrlStream.hostname == parsedExtensionStoreDataURL.hostname:
                DefaultURLReader.fetch(urlStream, self._makeExtensionStoreItems)
            else:
                DefaultURLReader.fetch(urlStream, self._makeExtensionRepositories)

    def extensionDidRemoteInstall(self, info):
        self._numExtensionsUpdated += 1
        if self._numExtensionsUpdated < len(self._extensionsToUpdate):
            if self._progress is not None:
                self._progress.update()
            return

        if self._progress is not None:
            self._progress.close()
            self._progress = None

        self.extensionListSelectionCallback(None)
        self.reloadData()

    def extensionDidUninstall(self, info):
        self.extensionListSelectionCallback(None)
        self.reloadData()

    def extensionDidCheckForUpdates(self, info):
        self._numExtensionsChecked += 1

        if self._numExtensionsChecked < len(self._extensionsToCheck):
            # drop out early if we’re still in the middle of checking
            # for extension updates
            return

        if self._progress is not None:
            self._progress.update()

        # By this point, all selected extensions have finished checking.
        # The self._didCheckForUpdates flag just ensures this block doesn’t
        # get executed multiple times
        if not self._didCheckForUpdates:

            now = time.time()
            setExtensionDefault("com.mechanic.lastUpdateCheck", now)
            title = time.strftime("Checked at %H:%M", time.localtime(now))
            self.w.checkForUpdatesInfo.set(title)

            if self._progress is not None:
                self._progress.close()
                self._progress = None

            # figure out which extension items need updating
            extensionsItemsToUpdate = [x for x in self._wrappedItems if x.extensionObject().extensionNeedsUpdate()]
            if len(extensionsItemsToUpdate) > 0:
                # bring items that need updating to the top of the list
                self._wrappedItems.sort(key=lambda x: x.extensionObject().extensionNeedsUpdate(), reverse=True)

            # set the table view with the current _wrappedItems
            self.setItems(self._wrappedItems)

            # after the updated items are set...
            if len(extensionsItemsToUpdate) > 0:
                # ...scroll to the top of the list if there are items which need updating
                self.w.extensionList.getNSTableView().scrollRowToVisible_(0)
                # ...and select them for easy, one-click update all by the user
                extensionItemsToUpdateIndices = [self.w.extensionList.index(x) for x in extensionsItemsToUpdate if not x.extensionObject().remoteIsBeta()]
                self.w.extensionList.setSelection(extensionItemsToUpdateIndices)

            self._didCheckForUpdates = True

    def checkForUpdates(self, itemsToCheck=None):
        # reset the flag so we know we need to complete an update cycle
        self._didCheckForUpdates = False

        if itemsToCheck is None:
            self._extensionsToCheck = [x.extensionObject() for x in self._wrappedItems]
        else:
            self._extensionsToCheck = itemsToCheck

        numExtensionsToCheck = len(self._extensionsToCheck)
        self._numExtensionsChecked = 0

        self._progress = self.startProgress("Checking for updates...")
        self._progress.setTickCount(numExtensionsToCheck)

        for item in self._extensionsToCheck:
            # these get executed asyncronously and send extensionDidCheckForUpdates
            # notifications when they’re done
            item.checkForUpdates()

    def setItems(self, items):
        # set the list with the current _wrappedItems
        try:
            self.w.extensionList.set(items)
        except Exception as e:
            logger.error("Cannot set items in mechanic list.")
            logger.error(e)

    def extensionListSelectionCallback(self, sender):
        items = self.getSelection()
        multiSelection = len(items) > 1

        notInstalled = [item for item in items if not item.isExtensionInstalled()]
        installed = [item for item in items if item.isExtensionInstalled()]
        needsUpdate = [item for item in installed if item.extensionNeedsUpdate()]
        notInstalledStore = [item for item in notInstalled if item.isExtensionFromStore()]
        notInstalledNotStore = [item for item in notInstalled if not item.isExtensionFromStore()]

        buttons = []

        if notInstalledStore:
            title = "Purchase"
            if multiSelection:
                title += " (%s)" % len(notInstalledStore)
            buttons.append((title, self.w.purchaseButton))

        if notInstalledNotStore:
            title = "Install"
            if multiSelection:
                title += " (%s)" % len(notInstalledNotStore)
            buttons.append((title, self.w.installButton))

        if needsUpdate:
            title = "Update"
            if multiSelection:
                title += " (%s)" % len(needsUpdate)
            buttons.append((title, self.w.updateButton))

        if installed:
            title = "Uninstall"
            if multiSelection:
                title += " (%s)" % len(installed)
            buttons.append((title, self.w.uninstallButton))

        allButtons = [self.w.purchaseButton, self.w.installButton, self.w.uninstallButton, self.w.updateButton]

        left = -10
        for title, button in buttons:
            button.show(True)
            _, top, width, height = button.getPosSize()
            button.setPosSize((left - width, top, width, height))
            button.setTitle(title)
            left -= width + 10
            allButtons.remove(button)

        for button in allButtons:
            button.show(False)

    def extensionListDoubleClickCallback(self, sender):
        # open popover for the selected row (only the first one row in the selection)
        # show a button to open the repo in a browser
        # list all releases
        def popoverCloseCallback(sender):
            del self._mechanicListItemPopoverController

        items = self.getSelection()
        if items:
            # keep a reference
            self._mechanicListItemPopoverController = MechanicListItemPopoverController(items[0], sender)
            self._mechanicListItemPopoverController.getPopover().bind("did close", popoverCloseCallback)

    # buttons

    def checkForUpdatesCallback(self, sender):
        def _checkForUpdatesCallback(value):
            if value:
                if NSEvent.modifierFlags() & NSAlternateKeyMask:
                    # only check the selected items
                    selected = self.getSelection()
                    self.checkForUpdates(selected)
                else:
                    # only check for updates in items that are actually installed
                    installed = [item.extensionObject() for item in self._wrappedItems if item.extensionObject().isExtensionInstalled()]
                    self.checkForUpdates(installed)
                self.extensionListSelectionCallback(self.w.extensionList)

        if self._didCheckForUpdates:
            self.showAskYesNo("Check for updates, again?", "All extensions have been checked not so long ago.", callback=_checkForUpdatesCallback)
        else:
            _checkForUpdatesCallback(True)

    def purchaseCallback(self, sender):
        items = self.getSelection()
        multiSelection = len(items) > 1
        items = [item for item in items if item.isExtensionFromStore() and not item.isExtensionInstalled()]
        for item in items:
            item.openRemotePurchaseURL(multiSelection)

    def installCallback(self, sender):
        items = self.getSelection()
        items = [item for item in items if not item.isExtensionFromStore() and not item.isExtensionInstalled()]
        if not items: return
        self._extensionsToUpdate = items
        self._numExtensionsUpdated = 0
        self._extensionAction(items=items, message="Installing extensions...", action="remoteInstall")

    def uninstallCallback(self, sender):
        items = self.getSelection()
        items = [item for item in items if item.isExtensionInstalled()]
        if not items:
            return
        hasStoreItems = any([item.isExtensionFromStore() for item in items])
        if hasStoreItems:
            def callback(response):
                if response:
                    self._extensionAction(items=items, message="Uninstalling extensions...", action="extensionUninstall")
            purchasedItems = [item.extensionName() for item in items if item.isExtensionFromStore()]
            self.showAskYesNo("Uninstalling a purchased extension.", "Do you want to uninstall a purchased extensions: %s." % (", ".join(purchasedItems)), callback=callback)
        else:
            self._extensionAction(items=items, message="Uninstalling extensions...", action="extensionUninstall")

    def updateCallback(self, sender):
        items = self.getSelection()
        items = [item for item in items if item.isExtensionInstalled() and item.extensionNeedsUpdate()]
        if not items: return
        self._extensionsToUpdate = items
        self._numExtensionsUpdated = 0
        self._progress = self.startProgress("Updating extensions...")
        self._progress.setTickCount(len(items))
        self._extensionAction(items=items, message=None, action="remoteInstall")

    def reloadData(self):
        # reload the underlying NSTableView data, which also triggers a repaint
        self.w.extensionList.getNSTableView().reloadData()

    def extensionIconDidLoad(self, info):
        iconURL = info.get('iconURL', None)
        if iconURL:

            if iconURL in self._iconURLs:
                self._iconURLs.remove(iconURL)

            # Call reloadData() for every icon that shows up in the visible area.
            # This avoids the situation where most icons have loaded but we’re waiting
            # for one way down the tableview, when the user is still at the top of the list
            if iconURL in self._iconURLsForVisibleRows:
                self.reloadData()

        # call setNeedsDisplay_(True) on the tableView once, when all the icons have loaded
        if len(self._iconURLs) == 0:
            self.w.extensionList.getNSTableView().setNeedsDisplay_(True)

    def _extensionAction(self, items, message, action, **kwargs):
        multiSelection = len(items) > 1
        if message:
            progress = self.startProgress(message)
        if message and multiSelection:
            progress.setTickCount(len(items))
        foundErrors = False
        for item in items:
            callback = getattr(item, action)
            try:
                callback(**kwargs)
            except Exception as e:
                logger.error("Could not execute: '%s'. \n\n%s" % (action, e))
                foundErrors = True
            if message:
                progress.update()
        if message:
            progress.close()
            progress = None
        self.reloadData()
        self.extensionListSelectionCallback(self.w.extensionList)
        if foundErrors:
            self.showMessage(message, "Failed, see output window for details.")

    def settingsCallback(self, sender):
        self.loadExtensions()

    # toolbar

    def toolbarSettings(self, sender):
        Settings(self.w, callback=self.settingsCallback)

    def toolbarSearch(self, sender):
        search = sender.get()
        arrayController = self.w.extensionList.getNSTableView().dataSource()
        if not search:
            arrayController.setFilterPredicate_(None)
        else:
            searches = search.lower().strip().split(" ")
            query = []
            for search in searches:
                query.append('extensionSearchString CONTAINS "%s"' % search)
            query = " AND ".join(query)
            predicate = NSPredicate.predicateWithFormat_(query)
            arrayController.setFilterPredicate_(predicate)

    # helpers

    def getSelection(self):
        arrayController = self.w.extensionList.getNSTableView().dataSource()
        selection = arrayController.selectedObjects()
        if selection:
            return [item.extensionObject() for item in selection]
        return []
