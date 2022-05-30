import yaml
import logging
import time

from vanilla.dialogs import message, BaseMessageDialog

from mojo.tools import registerFileExtension

from mojo.events import addObserver
from mojo.extensions import setExtensionDefault, getExtensionDefault

from mechanic2.extensionItem import ExtensionYamlItem
from mechanic2.ui.controller import MechanicController


logger = logging.getLogger("Mechanic")

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
                    item = yaml.safe_load(f.read())
            except Exception as e:
                logger.error("Cannot read '%s' file" % path)
                logger.error(e)
            try:
                ExtensionYamlItem(item)
                if item not in singleItems:
                    singleItems.append(item)
                    setExtensionDefault("com.mechanic.singleExtensionItems", singleItems)
                    title = "Opening Mechanic file."
                    text = "Added '%s' to Mechanic" % path
                else:
                    title = "Duplicate Mechanic file."
                    text = "The extension '%s' was not added to Mechanic" % path
            except Exception as e:
                logger.error("Cannot parse the file '%s'" % path)
                logger.error(e)
                title = "Failed to read the file '%s'." % path
                text = "See the output window for a detailed traceback."
            message(title, text)
            fileHandler["opened"] = True

    def applicationDidFinishLaunching(self, notification):
        shouldCheckForUpdates = getExtensionDefault("com.mechanic.checkForUpdate")
        if not shouldCheckForUpdates:
            return
        lastCheck = getExtensionDefault("com.mechanic.lastUpdateCheck")
        oneDay = 60 * 60 * 24
        now = time.time()
        if lastCheck + oneDay < now:
            messageText = "Mechanic would like to check for updates."
            informativeText = "Updating might take some time, you can check for updates later by opening the Mechanic extension."

            alert = BaseMessageDialog.alloc().initWithMessageText_informativeText_alertStyle_buttonTitlesValues_window_resultCallback_(
                messageText=messageText,
                informativeText=informativeText,
                buttonTitlesValues=[("Now", 1), ("Later", 0)]
            )
            if alert._value:
                MechanicController(checkForUpdates=True)

            setExtensionDefault("com.mechanic.lastUpdateCheck", now)


MechanicObservers()
