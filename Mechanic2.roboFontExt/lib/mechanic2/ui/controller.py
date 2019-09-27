import json
import logging
import time
import vanilla

from urllib.parse import urlparse

from Foundation import NSObject, NSString, NSUTF8StringEncoding
from AppKit import NSToolbarFlexibleSpaceItemIdentifier, NSPredicate
from AppKit import NSEvent, NSAlternateKeyMask

from mojo.events import addObserver
from mojo.extensions import getExtensionDefault, setExtensionDefault

from defconAppKit.windows.baseWindow import BaseWindowController

from mechanic2.ui.cells import MCExtensionCirleCell, MCImageTextFieldCell
from mechanic2.ui.formatters import MCExtensionDescriptionFormatter
from mechanic2.ui.settings import Settings, extensionStoreDataURL
from mechanic2.extensionItem import ExtensionRepository, ExtensionStoreItem
from mechanic2.extensionItem import ExtensionYamlItem, EXTENSION_ICON_DID_LOAD_EVENT_KEY

from urlreader import URLReader


logger = logging.getLogger("Mechanic")


class MCExtensionListItem(NSObject):

    def __new__(cls, *args, **kwargs):
        return cls.alloc().init()

    def __init__(self, extensionObject=None):
        self._extensionObject = extensionObject

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

        self.w = vanilla.Window((600, 300), "Mechanic 2.0", minSize=(550, 200))

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

        self.w.checkForUpdates = vanilla.Button((10, -30, 160, 22), "Check For Updates", callback=self.checkForUpdatesCallback, sizeStyle="small")

        self.w.purchaseButton = vanilla.Button((10, -30, 100, 22), "Purchase", callback=self.purchaseCallback)
        self.w.installButton = vanilla.Button((10, -30, 100, 22), "Install", callback=self.installCallback)
        self.w.uninstallButton = vanilla.Button((10, -30, 120, 22), "Uninstall", callback=self.uninstallCallback)
        self.w.updateButton = vanilla.Button((10, -30, 110, 22), "Update", callback=self.updateCallback)
        allButtons = [self.w.purchaseButton, self.w.installButton, self.w.uninstallButton, self.w.updateButton]
        for button in allButtons:
            button.show(False)

        self.w.extensionList.setSelection([])
        self.w.open()

        self._checkForUpdates = checkForUpdates
        self._didCheckForUpdates = False
        self._progress = None
        self._extensionRepositoriesLoaded = False
        self._extensionStoreItemsLoaded = False
        self._canLoadSingleExtensions = True
        self._wrappedItems = []
        self._iconURLs = set()
        self._iconURLsForVisibleRows = set()

        addObserver(self, 'iconDidLoad', EXTENSION_ICON_DID_LOAD_EVENT_KEY)

        if shouldLoad:
            self.loadExtensions()

    def _makeExtensionItem(self, extensionData, itemClass, url):
        try:
            item = MCExtensionListItem(
                itemClass(extensionData, checkForUpdates=self._checkForUpdates)
            )
            self._wrappedItems.append(item)
        except Exception as e:
            logger.error("Creating extension item '%s' from url '%s' failed." % (extensionData.get("extensionName", "unknown"), url))
            logger.error(e)

    def _decodeData(self, url, data, error):
        if error:
            logger.error("Cannot read url '%s'" % url)
            logger.error("Error '%s'" % error)

        data = NSString.alloc().initWithData_encoding_(data, NSUTF8StringEncoding)
        try:
            extensionData = json.loads(data.strip())
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
                self._makeExtensionItem(extensionData, ExtensionRepository, url)
        self._extensionRepositoriesLoaded = True
        self._checkExtensionsDidLoad()

    def _checkExtensionsDidLoad(self):
        if self._extensionRepositoriesLoaded and self._extensionStoreItemsLoaded:
            if self._canLoadSingleExtensions:
                self._canLoadSingleExtensions = False
                self._loadSingleExtensions()

    def _loadSingleExtensions(self):
        for singleExtension in getExtensionDefault("com.mechanic.singleExtensionItems"):
            try:
                item = MCExtensionListItem(
                    ExtensionYamlItem(singleExtension, checkForUpdates=self._checkForUpdates)
                )
                self._wrappedItems.append(item)
            except Exception as e:
                logger.error("Creating single extension item '%s' failed." % singleExtension.get("extensionName", "unknow"))
                logger.error(e)

        self._progress.update("Setting Extensions...")

        # sort items by repo, YAML and leave store for last as before...
        _wrappedItemsOrder = [
            ExtensionRepository,
            ExtensionYamlItem,
            ExtensionStoreItem,
        ]
        self._wrappedItems.sort(key=lambda x: _wrappedItemsOrder.index(type(x.extensionObject())))

        # figure out which extensionItems have objects which need updating
        extensionsItemsToUpdate = []
        for item in self._wrappedItems:
            if item.extensionObject().extensionNeedsUpdate():
                extensionsItemsToUpdate.append(item)

        if len(extensionsItemsToUpdate) > 0:
            # bring items that need updating to the top of the list...
            self._wrappedItems.sort(key=lambda x: x.extensionObject().extensionNeedsUpdate(), reverse=True)

        # actually try to set the list with the current _wrappedItems
        try:
            self.w.extensionList.set(self._wrappedItems)
        except Exception as e:
            logger.error("Cannot set items in mechanic list.")
            logger.error(e)

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

        # after the items are set...
        if len(extensionsItemsToUpdate) > 0:
            # ...scroll to the top of the list if there are items which need updating
            self.w.extensionList.getNSTableView().scrollRowToVisible_(0)
            # ...and select them for easy, one-click update all by the user
            extensionItemsToUpdateIndices = [self.w.extensionList.index(x) for x in extensionsItemsToUpdate]
            self.w.extensionList.setSelection(extensionItemsToUpdateIndices)

        if self._checkForUpdates:
            self._progress.update("Checking for updates...")
            self._progress.setTickCount(len(self._wrappedItems))
            for item in self._wrappedItems:
                self._progress.update()
                item.extensionObject().extensionNeedsUpdate()
            self._progress.setTickCount(None)
            now = time.time()
            setExtensionDefault("com.mechanic.lastUpdateCheck", now)
            title = time.strftime("Checked at %H:%M", time.localtime(now))
            self.w.checkForUpdates.setTitle(title)
            self._didCheckForUpdates = True

        if self._progress is not None:
            self._progress.close()
            self._progress = None

    def loadExtensions(self):
        self._wrappedItems = []
        self._canLoadSingleExtensions = True
        self._progress = self.startProgress("Loading extensions...")

        streams = getExtensionDefault("com.mechanic.urlstreams")
        for urlStream in streams:
            urlreader = URLReader(force_https=True)
            parsedExtensionStoreDataURL = urlparse(extensionStoreDataURL)
            parsedUrlStream = urlparse(urlStream)
            if parsedUrlStream.hostname == parsedExtensionStoreDataURL.hostname:
                urlreader.fetch(urlStream, self._makeExtensionStoreItems)
            else:
                urlreader.fetch(urlStream, self._makeExtensionRepositories)

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
        items = self.getSelection()
        multiSelection = len(items) > 1
        for item in items:
            item.openRemoteURL(multiSelection)

    # buttons

    def checkForUpdatesCallback(self, sender):

        def _checkForUpdatesCallback(value):
            if value:
                if NSEvent.modifierFlags() & NSAlternateKeyMask:
                    # only check the selected items
                    items = self.getSelection()
                    progress = self.startProgress("Updating %s extensions..." % len(items))
                    progress.setTickCount(len(items))
                    for item in items:
                        self._progress.update()
                        item.checkForUpdates()
                    progress.setTickCount(None)
                    progress.close()
                    self.reloadData()
                    self.extensionListSelectionCallback(self.w.extensionList)
                else:
                    # load all extension and check for updates
                    self._checkForUpdates = True
                    self.loadExtensions()

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
        if not items:
            return
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
        if not items:
            return
        self._extensionAction(items=items, message="Updating extensions...", action="remoteInstall")

    def reloadData(self):
        # reload the underlying NSTableView data, which also triggers a repaint
        self.w.extensionList.getNSTableView().reloadData()

    def iconDidLoad(self, info):
        iconURL = info.get('iconURL', None)
        if iconURL:

            if iconURL in self._iconURLs:
                self._iconURLs.remove(iconURL)

            # call reloadData() for every icon that shows loads in the visible area
            # this avoids the situation where most icons have loaded but we’re waiting
            # for one way down the tableview, when the user is still at the top of the list
            if iconURL in self._iconURLsForVisibleRows:
                self.reloadData()

        # call setNeedsDisplay_(True) on the tableView once, when all the icons have loaded
        if len(self._iconURLs) == 0:
            self.w.extensionList.getNSTableView().setNeedsDisplay_(True)

    def _extensionAction(self, items, message, action, **kwargs):
        multiSelection = len(items) > 1
        progress = self.startProgress(message)
        if multiSelection:
            progress.setTickCount(len(items))
        foundErrors = False
        for item in items:
            callback = getattr(item, action)
            try:
                callback(**kwargs)
            except Exception as e:
                print("Could not execute: '%s'. \n\n%s" % (action, e))
                foundErrors = True
            progress.update()
        progress.close()
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
