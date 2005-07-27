import getopt
import re

# Environment variables:
#
# VARISCONF     dynamic data dir, defaults to /var/isconf
# GNUPGHOME     used only for user keys, not host keys
# 

verbose = False
peers = {}

# return codes/messages 
SHORT_READ        = (54, "message truncated, data contains missing byte count")
BAD_RECORD        = (95, "bad record")
INVALID_RECTYPE   = (96, "invalid record type")
PROTOCOL_MISMATCH = (97, "protocol mismatch")

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

def getkwopt(argv,opt={},help=False): 
    """
    Get command line options and positional arguments.

    Returns help text if help=True

    Returns (kwopt,args) otherwise.

    Sample input:

        opt = {
            'd': ('varisconf', "/var/isconf", "base of cache"),
            'p': ('port', 9999, "port to listen on"),
            'v': ('verbose', False, "verbose"),
        }
        
    Sample kwopt return value (with empty command line):

        kwopt = {
            'varisconf': "/var/isconf",
            'port': 9999,
            'verbose': False,
        }
    """
    kwopt = {}
    optstr = ''
    longopts = []
    if help and not opt:
        return ""
    usagetxt = "options:\n"
    for short in opt.keys():
        long    = opt[short][0]
        default = opt[short][1]
        desc    = opt[short][2]
        kwopt[long] = default
        optstr += short
        longopt = long
        opthelp = "  -%s, --%s" % (short,long)
        if default is not True and default is not False:
            optstr += ':'
            longopt += '='
            opthelp += '=' + str(default)
        longopts.append(longopt)
        sep=""
        if len(opthelp) > 20: 
            sep="\n" + " " * 22
        usagetxt += "%-22s%s%s\n" % (opthelp,sep,desc)
    if help:
        return usagetxt
    (opts, args) = getopt.getopt(argv, optstr, longopts)
    for (short,default) in opts:
        short = short[1:] # strip off '-'
        if default == '': 
            default = True
        long = opt[short][0] 
        kwopt[long] = default
    return (kwopt,args)

def mkdict(**kwargs):
    return dict(kwargs)

def mklist(str):
    return str.split()

