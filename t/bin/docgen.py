#!/usr/bin/python2.3

import __future__
import os
import pexpect
import popen2
import re
import select
import sys
import time
import traceback

# swiped from doctest.py
class _SpoofOut:
    def __init__(self):
        self.clear()
    def write(self, s):
        self.buf.append(s)
    def get(self):
        guts = "".join(self.buf)
        # If anything at all was written, make sure there's a trailing
        # newline.  There's no way for the expected output to indicate
        # that a trailing newline is missing.
        if guts and not guts.endswith("\n"):
            guts = guts + "\n"
        # Prevent softspace from screwing up the next test case, in
        # case they used print with a trailing comma in an example.
        if hasattr(self, "softspace"):
            del self.softspace
        return guts
    def clear(self):
        self.buf = []
        if hasattr(self, "softspace"):
            del self.softspace
    def flush(self):
        # JPython calls flush
        pass


# Also shamelessly stolen from doctest.  Get the future-flags
# associated with the future features that have been imported into
# globs.
def _extract_future_flags(globs):
    flags = 0
    for fname in __future__.all_feature_names:
        feature = globs.get(fname, None)
        if feature is getattr(__future__, fname):
            flags |= feature.compiler_flag
    return flags

import getopt
def getkwopt(argv,opt={},help=False): 
    """
    Get command line options and positional arguments.

    Returns help text if help=True

    Returns (kwopt,args) otherwise.

    Sample input:

        opt = {
            'p': ('port', 9999, "port to listen on"),
            'v': ('verbose', False, "verbose"),
        }
        
    Sample kwopt return value (with empty command line):

        kwopt = {
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

class docgen:

    def main(self):

        opt = {
            'd': ('debug', False, "debug this script"),
            'h': ('help', False, "this text"),
            'p': ('libpath', "lib/python", "path to module under test"),
            'v': ('verbose', False, "debug the test case"),
        }
        if '-h' in sys.argv:
            print >>sys.stderr, getkwopt(sys.argv[1:],opt,help=True)
            sys.exit(1)
        (kwopt,args) = getkwopt(sys.argv[1:],opt)
        modulepath = args[0]

        libpath = kwopt['libpath']
        sys.path.append(libpath)

        m = re.match(".*%s/(.*).py" % libpath, modulepath)
        if not m:
            raise "libpath (%s) not in module path (%s)" % (libpath,modulepath)
        module = m.group(1).replace("/",".")

        input = sys.stdin.readlines()

        striplen = 0
        if input[0].lstrip().startswith('>>> '):
            striplen = 4
            # remove old output lines
            newinput = []
            for i in range(len(input)):
                line = input[i]
                if re.match('\s*>>>\s+',line) \
                        or re.match('\s*\.\.\.\s+',line):
                    newinput.append(line)
            input = newinput

        indent = 0
        firstline = True
        code = ''
        lastline = len(input) - 1
        BLOCKSTART, BLOCKCONT, BLOCKEND = range(3)
        state = BLOCKSTART

        self.realout = sys.stdout
        sys.stdout = fakeout = _SpoofOut()
        # realerr = sys.stderr
        # sys.stderr = fakeerr = _SpoofOut()
        exec "import %s" % module 
        exec "globs = %s.__dict__" % module
        compileflags = _extract_future_flags(globs)
                
        for i in range(len(input)):
            fakeout.clear()
            icode = input[i]

            lcode = icode.lstrip()

            # show code
            self.realout.write(icode)
            
            # clean up input
            if firstline:
                firstline = False
                indent = len(icode) - len(lcode)
                self.indentstr = ' ' * indent
            if kwopt['debug']: print >>sys.stderr, icode
            scode = icode[indent+striplen:].rstrip() 
            
            # collect one complete code block
            if state == BLOCKSTART:
                code = scode
            if state == BLOCKCONT:
                # this is an indented continuation line
                code += "\n" + scode 
            if i < lastline:
                nextcode = input[i+1][indent+striplen:]
                if nextcode and nextcode.startswith(' '):
                    # next line is continuation
                    state = BLOCKCONT
                    continue
            state = BLOCKSTART 

            # kill doubled backslashes
            code = eval(repr(code).replace('\\\\','\\'))
            if not code:
                continue
            code += "\n"

            # run it
            try:
                exec compile(code, "<string>", "single",
                     compileflags, 1) in globs
                code = ''
                out = fakeout.get()
            except:
                code = ''
                out = fakeout.get()
                if out:
                    self.wout(out)
                exc_info = sys.exc_info()
                exc_type, exc_val, tb = exc_info[:3]
                if kwopt['verbose']: 
                    out = traceback.format_exception(exc_type, exc_val, tb)
                    out = ''.join(out)
                    out = out.strip() + "\n"
                    self.wout(out)
                else:
                    out = "Traceback (most recent call last):\n"
                    self.wout(out)
                    out = "    (...doctest ignores traceback detail...)\n"
                    self.wout(out)
                    out = traceback.format_exception_only(exc_type, exc_val)[-1]
                    self.wout(out)
                continue
            if out: 
                self.wout(out)

    def wout(self,out):
        realout = self.realout
        indentstr = self.indentstr
        out = out.rstrip()
        # put the doubled backslashes back
        out = eval(repr(out).replace('\\\\','\\\\\\\\'))
        # restore indent
        out = out.replace('\n','\n' + indentstr)
        realout.write(indentstr + out + "\n")

dg = docgen()
dg.main()
