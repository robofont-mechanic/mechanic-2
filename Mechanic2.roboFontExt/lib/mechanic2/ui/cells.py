import AppKit
from objc import super

from mechanic2.mechanicTools import remember


class MCExtensionCirleCell(AppKit.NSTextFieldCell):

    def drawWithFrame_inView_(self, frame, view):
        controller = self.objectValue()
        obj = controller.extensionObject()

        image = None
        if obj.hasInstallErrors():
            image = InstallErroIndicator()
        elif obj.isExtensionInstalled():
            if obj.isExtensionFromStore() and obj.extensionStoreKey() is None:
                image = NotBoughtIndicator()
            elif obj.extensionNeedsUpdate():
                image = UpdateIndicator(obj.remoteIsBeta())
            else:
                image = InstalledIndicator()

        if image is not None:
            size = image.size()
            x = frame.origin.x + (frame.size.width - size.width) / 2 + 2
            y = frame.origin.y + (frame.size.height - size.height) / 2 - 1
            image.drawAtPoint_fromRect_operation_fraction_(
                (x, y),
                ((0, 0), size),
                AppKit.NSCompositeSourceOver,
                1.0
            )


@remember
def InstallErroIndicator():
    width = 20
    height = 20
    image = AppKit.NSImage.alloc().initWithSize_((width, height))
    image.lockFocus()

    path = AppKit.NSBezierPath.bezierPathWithOvalInRect_(((8, 14), (4, 4)))
    path.appendBezierPathWithRect_(((8.5, 6), (3, 7)))

    path.fill()

    trianglePath = AppKit.NSBezierPath.bezierPath()
    trianglePath.moveToPoint_((0, 18))
    trianglePath.lineToPoint_((2, 20))

    trianglePath.lineToPoint_((18, 20))
    trianglePath.lineToPoint_((20, 18))

    trianglePath.lineToPoint_((11, 0))
    trianglePath.lineToPoint_((9, 0))
    trianglePath.closePath()
    trianglePath.addClip()

    color1 = AppKit.NSColor.redColor()
    color2 = AppKit.NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.1)
    color3 = AppKit.NSColor.whiteColor()

    color1.set()
    trianglePath.fill()

    color2.set()
    trianglePath.setLineWidth_(2)
    trianglePath.stroke()

    color3.set()
    path.fill()

    image.unlockFocus()

    return image


@remember
def NotBoughtIndicator():
    width = 9
    height = 9
    image = AppKit.NSImage.alloc().initWithSize_((width, height))
    image.lockFocus()

    path = AppKit.NSBezierPath.bezierPathWithOvalInRect_(((3, 6), (3, 3)))
    path.appendBezierPathWithRect_(((3.5, 0), (2, 5)))

    path.addClip()

    color1 = AppKit.NSColor.redColor()
    color2 = AppKit.NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.1)

    color1.set()
    path.fill()

    color2.set()
    path.setLineWidth_(2)
    path.stroke()

    image.unlockFocus()

    return image


@remember
def InstalledIndicator():
    width = 9
    height = 9
    image = AppKit.NSImage.alloc().initWithSize_((width, height))
    image.lockFocus()

    path = AppKit.NSBezierPath.bezierPathWithOvalInRect_(((0, 0), (9, 9)))
    path.addClip()

    color1 = AppKit.NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.4)
    color2 = AppKit.NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.1)

    color1.set()
    path.fill()

    color2.set()
    path.setLineWidth_(2)
    path.stroke()

    image.unlockFocus()

    return image


@remember
def UpdateIndicator(isBeta=False):
    width = 9
    height = 9
    image = AppKit.NSImage.alloc().initWithSize_((width, height))
    image.lockFocus()

    path = AppKit.NSBezierPath.bezierPathWithOvalInRect_(((0, 0), (9, 9)))
    path.addClip()
    if isBeta:
        color1 = AppKit.NSColor.magentaColor()
    else:
        color1 = AppKit.NSColor.orangeColor()

    color1.set()
    path.setLineWidth_(5)
    path.stroke()

    image.unlockFocus()

    return image


class MCImageTextFieldCell(AppKit.NSTextFieldCell):

    def drawWithFrame_inView_(self, frame, view):
        controller = self.objectValue()
        obj = controller.extensionObject()

        image = obj.extensionIcon()
        if image:
            rowHeight = view.rowHeight()
            imageFrame = frame.copy()
            imageFrame.size.width = rowHeight
            imageFrame.size.height = rowHeight
            frame.origin.x += rowHeight + 5
            frame.size.width -= rowHeight + 5
        super(MCImageTextFieldCell, self).drawWithFrame_inView_(frame, view)
        if image:
            image.drawInRect_(imageFrame)
