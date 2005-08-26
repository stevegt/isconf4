
import errno
import os

# because dict() doesn't do this until 2.3...
def mkdict(**kwargs): return kwargs

errset = mkdict(
OK                = (0,  ""),
LOCKED            = (220, "resource is locked"),
NOTLOCKED         = (221, "resource is not locked"),
NEEDMSG           = (222, "changelog/lock message (-m) required"),
PANIC             = (223, "unable to continue"),
EXCEPTION         = (224, "server-side exception"),
SHORTREAD         = (754, 
    "message truncated, data contains missing byte count"),
)

class Errno:

    def __init__(self):
        self.errorcode = {}
        self._strerror = {}
        self.errorcode.update(errno.errorcode)
        for name in errset.keys():
            (code,desc) = errset[name]
            if os.environ.has_key('DEBUG'):
                if hasattr(errno,name):
                    raise AssertionError(name)
                if self.errorcode.has_key(code):
                    raise AssertionError(code)
            self.errorcode[code] = name
            self._strerror[code] = desc

    def __getattr__(self,name):
        if errset.has_key(name):
            return errset[name][0]
        return getattr(errno,name)

    def strerror(self,code):
        if self._strerror.has_key(code):
            return self._strerror[code]
        return os.strerror(code)

iserrno = Errno()

