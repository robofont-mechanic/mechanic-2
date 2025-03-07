import AppKit
import logging


logger = logging.getLogger("Mechanic")


class MCExtensionDescriptionFormatter(AppKit.NSFormatter):

    def stringForObjectValue_(self, obj):
        if obj is None or isinstance(obj, AppKit.NSNull):
            return ''
        return obj

    def attributedStringForObjectValue_withDefaultAttributes_(self, controller, attrs):
        obj = controller.extensionObject()

        attrs = dict(attrs)

        paragraph = AppKit.NSMutableParagraphStyle.alloc().init()
        paragraph.setMinimumLineHeight_(20.0)
        attrs[AppKit.NSParagraphStyleAttributeName] = paragraph

        string = AppKit.NSMutableAttributedString.alloc().initWithString_attributes_('', attrs)

        try:
            name = AppKit.NSAttributedString.alloc().initWithString_attributes_(obj.extensionName() or '', attrs)
            string.appendAttributedString_(name)

            if obj.extensionPrice():
                priceColor = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.3, 0.7, 0, 1)
                attrs[AppKit.NSForegroundColorAttributeName] = priceColor
                price = AppKit.NSAttributedString.alloc().initWithString_attributes_(f'\u2003{obj.extensionPrice()}', attrs)
                string.appendAttributedString_(price)

            grayColor = AppKit.NSColor.colorWithCalibratedWhite_alpha_(0.6, 1)
            attrs[AppKit.NSForegroundColorAttributeName] = grayColor

            space = AppKit.NSAttributedString.alloc().initWithString_attributes_('\u2003', attrs)
            string.appendAttributedString_(space)

            author = AppKit.NSAttributedString.alloc().initWithString_attributes_(obj.extensionDeveloper() or '', attrs)
            string.appendAttributedString_(author)

            paragraph = AppKit.NSMutableParagraphStyle.alloc().init()
            paragraph.setLineBreakMode_(AppKit.NSLineBreakByTruncatingTail)
            paragraph.setMaximumLineHeight_(14.0)

            attrs[AppKit.NSParagraphStyleAttributeName] = paragraph
            attrs[AppKit.NSFontAttributeName] = AppKit.NSFont.systemFontOfSize_(10.0)

            cr = AppKit.NSAttributedString.alloc().initWithString_attributes_('\n', attrs)
            string.appendAttributedString_(cr)

            if obj.isExtensionInstalled() and obj.isExtensionFromStore() and obj.extensionStoreKey() is None:
                attrs[AppKit.NSForegroundColorAttributeName] = AppKit.NSColor.redColor()
                update = AppKit.NSAttributedString.alloc().initWithString_attributes_('Unofficial version installed ', attrs)
                string.appendAttributedString_(update)
                attrs[AppKit.NSForegroundColorAttributeName] = grayColor
            elif obj.hasInstallErrors():
                attrs[AppKit.NSForegroundColorAttributeName] = AppKit.NSColor.redColor()
                update = AppKit.NSAttributedString.alloc().initWithString_attributes_(f"{obj.installErrors()} ", attrs)
                string.appendAttributedString_(update)
                attrs[AppKit.NSForegroundColorAttributeName] = grayColor
            if obj.extensionNeedsUpdate():
                if obj.remoteIsBeta():
                    updateText = "Found beta update"
                    attrs[AppKit.NSForegroundColorAttributeName] = AppKit.NSColor.magentaColor()
                else:
                    updateText = "Found update"
                    attrs[AppKit.NSForegroundColorAttributeName] = AppKit.NSColor.orangeColor()
                update = AppKit.NSAttributedString.alloc().initWithString_attributes_(f'{updateText} {obj.extensionVersion()} \u2192 {obj.remoteVersion()}\u2003', attrs)
                string.appendAttributedString_(update)
                attrs[AppKit.NSForegroundColorAttributeName] = grayColor
            elif obj.isExtensionInstalled():
                version = AppKit.NSAttributedString.alloc().initWithString_attributes_(f'{obj.extensionVersion()}\u2003', attrs)
                string.appendAttributedString_(version)

            description = AppKit.NSAttributedString.alloc().initWithString_attributes_(obj.extensionDescription() or '\u2014', attrs)
            string.appendAttributedString_(description)
        except Exception as e:
            logger.error(f"Cannot format '{obj}'")
            logger.error(e)

        return string

    def objectValueForString_(self, string):
        return string
