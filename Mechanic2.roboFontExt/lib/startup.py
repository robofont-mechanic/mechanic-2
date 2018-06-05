import yaml

from vanilla.dialogs import message, askYesNo

from mojo.tools import registerFileExtension
from mojo.events import addObserver
from mojo.extensions import setExtensionDefault, getExtensionDefault

from mechanic2.extensionItem import ExtensionYamlItem
from mechanic2.ui.controller import MechanicController

fileExtension = "mechanic"

registerFileExtension(fileExtension)


class MechanicObservers(object):

    def __init__(self):
        addObserver(self, "applicationOpenFile", "applicationOpenFile")
        addObserver(self, "applicationDidFinishLaunching", "applicationDidFinishLaunching")

    def applicationOpenFile(self, notification):
        path = notification["path"]
        ext = notification["ext"]
        fileHandler = notification["fileHandler"]
        if ext == ".%s" % fileExtension:
            singleItems = list(getExtensionDefault("com.mechanic.singleExtensionItems"))
            try:
                with open(path, "rb") as f:
                    item = yaml.load(f.read())

                ExtensionYamlItem(item)
                if item not in singleItems:
                    singleItems.append(item)
                    setExtensionDefault("com.mechanic.singleExtensionItems", singleItems)
                    title = "Opening mechanic file."
                    text = "Added '%s' to mechanic" % path
                else:
                    title = "Duplicated mechanic file."
                    text = "The extension '%s' is not to mechanic" % path
            except Exception as e:
                print(e)
                title = "Reading '%s' failed." % path
                text = "See the output window for a detailed traceback."
            message(title, text)
            fileHandler["opened"] = True

    def applicationDidFinishLaunching(self, notification):
        shouldCheckForUpdates = getExtensionDefault("com.mechanic.checkForUpdate")
        if shouldCheckForUpdates:
            result = askYesNo(
                messageText="Mechanic would like to check for updates.",
                informativeText="This will take some time. Opening Mechanic will also perform a check for updates.")
            if result:
                MechanicController()


MechanicObservers()
