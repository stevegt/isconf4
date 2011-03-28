import os
import re
import sys

import isconf.fbp822
from isconf.Errno import iserrno

RE = {
    'newline': '\n',
    'size': '(\d+)\s*\n',
    # 'pgpkey': '-----BEGIN PGP PUBLIC KEY BLOCK-----\n',
    # 'pgpmessage': '-----BEGIN PGP MESSAGE-----\n',
    # 'headers': '-----BEGIN ((.|\n)*?)\n\n((.|\n)*?)\n\n',
    'headbody': '^\n*((.|\n)*?\n)\n([\s\S]*)$',
}

# replace uncompiled patterns with compiled ones
for (name,expr) in RE.items():
    RE[name] = re.compile(expr)

# try to make 2.2's old booleans look like 2.3+ so doctest output is
# consistent
# if str(True) is '1':
#     class _True:
#         def __str__(self): return 'True'
#         def __int__(self): return 1
#     class _False:
#         def __str__(self): return 'False'
#         def __int__(self): return 0
#     True = _True()
#     False = _False()
# 
# print True 
# print False 
# 
# if True: print "True ok"
# if False: print "False bad"

# wow.  named buses.  gee.
class _BusSet(dict):
    def XXX__init__(self):
        self._bus = {}
    def XXX__getattr__(self,name):
        self._bus.setdefault(name,None)
        return self._bus[name]
    def __getattr__(self,name):
        self[name]=None
        return self[name]
    def XXX__setattr__(self,name,val):
        if name.startswith("_"):
            pass
        self._bus[name] = val

BUS = _BusSet()

FBP = isconf.fbp822.fbp822()

# XXX this whole thing is ridiculously crufty 
# XXX make these all uppercase
def debug(*msg):
    _log('debug',msg=msg)
def info(*msg):
    _log('info',msg=msg)
def warn(*msg):
    _log('warning',msg=msg)
def error(rc,*msg):
    # causes client to exit; server only logs it
    if isinstance(rc,int):
        desc = iserrno.strerror(rc)
        if msg:
            msg = mkstring(msg)
            if not msg.endswith(desc):
                msg = "%s: %s" % (msg, desc)
    else:
        msg = [rc] + mklist(msg)
        rc = 1 # EPERM 
    _log('error',msg=msg,rc=rc)
def XXXpanic(rc,*msg):
    # doesn't work yet -- what we want this to do is notify client,
    # then restart server
    _log('panic',msg=msg,rc=rc)
def _log(type,msg,rc=None):
    if BUS.log:
        if os.environ.has_key('DEBUG'):
            print >>sys.stderr, type, rc, msg
        if not isinstance(msg,isconf.fbp822.Message):
            msg = mkstring(msg)
            if rc:
                fbpmsg = FBP.msg(type,msg,rc=rc)
            else:
                fbpmsg = FBP.msg(type,msg)
        BUS.log.tx(fbpmsg)
        return
    msg = mkstring(msg)
    if type == 'debug' and not os.environ.has_key('DEBUG'): return
    if type == 'info' and not os.environ.has_key('VERBOSE'): return
    out = "isconf: %s: %s" % (type,msg)
    print >>sys.stderr, out
    if rc and not BUS.log:
        sys.exit(rc)

def getmtime_int(path):
    mtime = os.path.getmtime(path)
    mtime = int(mtime)
    return mtime

def mklist(data):
    if len(data) == 1 or isinstance(data,str):
        data = [data]
    try:
        data = list(data)
    except:
        data = [data]
    return data

def mkstring(data):
    if len(data) == 1:
        data = str(data[0])
    if len(data) > 1 and not isinstance(data,str):
        try:
            data = ' '.join(data)
        except:
            data = str(data)
    return data

# because dict() doesn't do this until 2.3...
def mkdict(**kwargs): return kwargs

