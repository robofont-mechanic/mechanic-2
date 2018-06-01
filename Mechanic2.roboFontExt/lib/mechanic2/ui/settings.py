import vanilla
from defconAppKit.windows.baseWindow import BaseWindowController


class Settings(BaseWindowController):

    def __init__(self, parentWindow):

        self.w = vanilla.Sheet((300, 200), parentWindow=parentWindow)

        y = 10
        # update shedule and timing

        # adding urls

        # self.w.urls =

        self.w.cancelButton = vanilla.Button((-170, -30, -80, 20), "Cancel", callback=self.closeCallback, sizeStyle="small")
        self.w.cancelButton.bind(".", ["command"])
        self.w.cancelButton.bind(chr(27), [])

        self.w.okButton = vanilla.Button((-70, -30, -10, 20), "OK", callback=self.okCallback, sizeStyle="small")
        self.w.setDefaultButton(self.w.okButton)

        self.w.open()

    def okCallback(self, sender):
        self.closeCallback(sender)

    def closeCallback(self, sender):
        self.w.close()

