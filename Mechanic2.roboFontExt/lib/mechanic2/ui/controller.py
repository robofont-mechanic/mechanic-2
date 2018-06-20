from AppKit import *
import json
import logging
import time

import vanilla
from defconAppKit.windows.baseWindow import BaseWindowController

from mojo.extensions import getExtensionDefault, setExtensionDefault

from mechanic2.ui.cells import MCExtensionCirleCell, MCImageTextFieldCell
from mechanic2.ui.formatters import MCExtensionDescriptionFormatter
from mechanic2.ui.settings import Settings, extensionStoreDataURL
from mechanic2.extensionItem import ExtensionRepository, ExtensionStoreItem, ExtensionYamlItem
from mechanic2.mechacnicTools import getDataFromURL


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


def getExtensionData(url):
    try:
        extensionData = getDataFromURL(url, formatter=json.loads)
    except Exception as e:
        logger.error("Cannot read url '%s'" % url)
        logger.error(e)
        extensionData = dict()
    return extensionData.get("extensions", [])


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

        self._didCheckedForUpdates = False
        if shouldLoad:
            self.loadExtensions(checkForUpdates)

    def loadExtensions(self, checkForUpdates=False):
        progress = self.startProgress("Loading extensions...")

        wrappedItems = []
        for urlStream in getExtensionDefault("com.mechanic.urlstreams"):
            clss = ExtensionRepository
            if urlStream == extensionStoreDataURL:
                clss = ExtensionStoreItem
            for data in getExtensionData(urlStream):
                try:
                    item = MCExtensionListItem(clss(data, checkForUpdates=checkForUpdates))
                    wrappedItems.append(item)
                except Exception as e:
                    logger.error("Creating extension item '%s' from url '%s' failed." % (data.get("extensionName", "unknow"), urlStream))
                    logger.error(e)

        for singleExtension in getExtensionDefault("com.mechanic.singleExtensionItems"):
            try:
                item = MCExtensionListItem(ExtensionYamlItem(singleExtension, checkForUpdates=checkForUpdates))
                wrappedItems.append(item)
            except Exception as e:
                logger.error("Creating single extension item '%s' failed." % singleExtension.get("extensionName", "unknow"))
                logger.error(e)

        progress.update("Setting Extensions...")
        try:
            self.w.extensionList.set(wrappedItems)
        except Exception as e:
            logger.error("Cannot set items in mechanic list.")
            logger.error(e)

        if checkForUpdates:
            progress.update("Checking for updates...")
            progress.setTickCount(len(wrappedItems))
            for item in wrappedItems:
                progress.update()
                item.extensionObject().extensionNeedsUpdate()
            progress.setTickCount(None)
            now = time.time()
            setExtensionDefault("com.mechanic.lastUpdateCheck", now)
            title = time.strftime("Checked at %H:%M", time.gmtime(now))
            self.w.checkForUpdates.setTitle(title)
            self._didCheckedForUpdates = True
        progress.close()

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
                self.loadExtensions(True)

        if self._didCheckedForUpdates:
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
        multiSelection = len(items) > 1
        items = [item for item in items if not item.isExtensionFromStore() and not item.isExtensionInstalled()]
        if not items:
            return
        self._extensionAction(items=items, message="Installing extensions...", action="remoteInstall", showMessages=not multiSelection)
        if multiSelection:
            message = ", ".join([item.extensionName() for item in items])
            self.showMessage("Installing multiple extensions:", message)

    def uninstallCallback(self, sender):
        items = self.getSelection()
        items = [item for item in items if item.isExtensionInstalled()]
        if not items:
            return
        self._extensionAction(items=items, message="Uninstalling extensions...", action="extensionUninstall")

    def updateCallback(self, sender):
        items = self.getSelection()
        multiSelection = len(items) > 1
        items = [item for item in items if item.isExtensionInstalled() and item.extensionNeedsUpdate()]
        if not items:
            return
        self._extensionAction(items=items, message="Updating extensions...", action="remoteInstall", showMessages=not multiSelection)
        if multiSelection:
            message = ", ".join([item.extensionName() for item in items])
            self.showMessage("Updating multiple extensions:", message)

    def _extensionAction(self, items, message, action, **kwargs):
        multiSelection = len(items) > 1
        progress = self.startProgress(message)
        if multiSelection:
            progress.setTickCount(len(items))
        for item in items:
            callback = getattr(item, action)
            callback(**kwargs)
            progress.update()
        progress.close()
        self.w.extensionList.getNSTableView().reloadData()
        self.extensionListSelectionCallback(self.w.extensionList)

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
