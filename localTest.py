import os
import sys

for moduleName in list(sys.modules.keys()):
    if moduleName.startswith("mechanic2"):
        del sys.modules[moduleName]
        
path = os.path.join(os.path.dirname(__file__), "Mechanic2.roboFontExt", "lib")
if path not in sys.path:
    sys.path.insert(0, path)


from lib.tools.debugTools import ClassNameIncrementer
import objc

DEBUG = True

if DEBUG:
    metaclass = ClassNameIncrementer
else:
    metaclass = objc.objc_meta_class

### my class        
import AppKit
class MyNSObject(AppKit.NSObject, metaclass=metaclass):
    pass

print(MyNSObject.__class__)