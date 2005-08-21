import os
import re
import sys

verbose = False

# return codes/messages 
NORMAL            = (0,  "")
LOCKED            = (20, "resource is locked")
NOTLOCKED         = (21, "resource is not locked")
MESSAGE_REQUIRED  = (22, "changelog/lock message (-m) required")
SHORT_READ        = (54, "message truncated, data contains missing byte count")
EXCEPTION         = (92, "server-side exception")
INVALID_VERB      = (93, "invalid subcommand verb")
SERVER_CLOSE      = (94, "server closed socket")
BAD_RECORD        = (95, "bad record")
INVALID_RECTYPE   = (96, "invalid record type")
PROTOCOL_MISMATCH = (97, "protocol mismatch")
PANIC             = (99, "unable to continue")

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

def debug(*msg):
    if not os.environ.has_key('DEBUG'):
        return
    _stderr('debug:',*msg)
def info(*msg):
    if not os.environ.has_key('VERBOSE'):
        return
    _stderr('info:',*msg)
def error(*msg):
    _stderr('error:',*msg)
def panic(*msg):
    _stderr('panic:',*msg)
    sys.exit(PANIC[0])
def _stderr(*msg):
    for m in msg:
        print >>sys.stderr, m,
    print >>sys.stderr, "\n"

