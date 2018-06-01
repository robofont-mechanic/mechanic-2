from AppKit import *
import json

from urllib.request import urlopen

import vanilla
from vanilla.vanillaBase import VanillaCallbackWrapper
from defconAppKit.windows.baseWindow import BaseWindowController
from defconAppKit.windows.progressWindow import ProgressWindow

from mojo.extensions import getExtensionDefault

from mechanic2.ui.cells import MCExtensionCirleCell, MCImageTextFieldCell
from mechanic2.ui.formatters import MCExtensionDescriptionFormatter
from mechanic2.ui.settings import Settings
from mechanic2.extensionItem import ExtensionRepository, ExtensionStoreItem

from lib.tools.debugTools import ClassNameIncrementer


class MCExtensionListItem(NSObject, metaclass=ClassNameIncrementer):

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
        response = urlopen(url)
        extensionData = json.loads(response.read())
    except Exception as e:
        extensionData = dict()
        print(e)
    return extensionData.get("extensions", [])


extensionStoreDataURL = "http://extensionstore.robofont.com/data.json"
mechanicDataURL = "https://robofont-mechanic.github.io/mechanic2/api/extensions.json"


class MechanicController(BaseWindowController):

    def __init__(self, shouldLoad=True):

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

        columnDescriptions = columnDescriptions = [
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
            allowsMultipleSelection=False,
            rowHeight=39
        )

        self.w.button = vanilla.Button((-150, -30, -10, 22), "Install", callback=self.buttonCallback)
        self.w.uninstall = vanilla.Button((-280, -30, -160, 22), "Uninstall", callback=self.uninstallCallback)

        self.w.extensionList.setSelection([])
        self.w.open()

        if shouldLoad:
            progress = self.startProgress("Loading extensions...")

            try:
                sources = [
                    (extensionStoreDataURL, ExtensionStoreItem),
                    (mechanicDataURL, ExtensionRepository),
                ]
                for externalSources in getExtensionDefault("com.mechanic.externalURLs", []):
                    sources.append((externalSources, ExtensionRepository))

                progress.update("Parsing Extensions...")

                wrappedItems = []
                for url, itemClass in sources:
                    for data in getExtensionData(url):
                        item = MCExtensionListItem(itemClass(data))
                        wrappedItems.append(item)

                progress.update("Setting Extensions...")
                self.w.extensionList.set(wrappedItems)
            except Exception as error:
                print(error)

            progress.close()

    def extensionListSelectionCallback(self, sender):
        item = self.getSelection()
        if item is None:
            self.w.button.setTitle("Install")
            self.w.button.enable(False)
            self.w.uninstall.enable(False)
        else:
            self.w.button.enable(True)
            self.w.uninstall.enable(item.isExtensionInstalled())

            if item.isExtensionFromStore():
                self.w.button.setTitle("Purchase")
            else:
                self.w.button.setTitle("Install")

    def extensionListDoubleClickCallback(self, sender):
        item = self.getSelection()
        if item:
            item.openRemoteURL()

    # buttons

    def buttonCallback(self, sender):
        item = self.getSelection()
        if item is None:
            return

        if item.isExtensionFromStore():
            item.openRemotePurchageURL()
        else:
            item.remoteInstall()
            self.w.extensionList.getNSTableView().reloadData()

    def uninstallCallback(self, sender):
        item = self.getSelection()
        if item is None:
            return
        item.extensionUninstall()
        self.w.extensionList.getNSTableView().reloadData()

    # toolbar

    def toolbarSettings(self, sender):
        Settings(self.w)

    def toolbarSearch(self, sender):
        search = sender.get()
        arrayController = self.w.extensionList.getNSTableView().dataSource()
        if not search:
            arrayController.setFilterPredicate_(None)
        else:
            search = 'extensionSearchString CONTAINS "%s"' % search.lower()
            predicate = NSPredicate.predicateWithFormat_(search)
            arrayController.setFilterPredicate_(predicate)

    # helpers

    def getSelection(self):
        arrayController = self.w.extensionList.getNSTableView().dataSource()
        selection = arrayController.selectedObjects()
        if selection:
            return selection[0].extensionObject()
        return None
