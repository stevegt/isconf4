import os
import re
import sys

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

# XXX syslog on server side
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
    msg = ["isconf:"] + list(msg)
    for m in msg:
        print >>sys.stderr, m,
    print >>sys.stderr, "\n"

# because dict() doesn't do this until 2.3...
def mkdict(**kwargs): return kwargs

