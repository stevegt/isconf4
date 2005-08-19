# vim:set expandtab:
# vim:set foldmethod=indent:
# vim:set shiftwidth=4:
# vim:set tabstop=4:

from __future__ import generators
import ConfigParser
import copy
import email.Message
import email.Parser
import errno
import inspect
import md5
import os
import popen2
import random
import re
import select
import sha
import shutil
import socket
import sys
import time
import isconf
from isconf.Globals import *
from isconf.Kernel import kernel


# TO SERVER:
#
# commands:
# c:size:argv
#
# stdin:  
# i:size:content
#
# FROM SERVER:
#
# stdout:
# o:size:content
#
# stderr:
# e:size:content
#
# return code:
# r:size:return_code
# 
# tell client to fetch stdin:
# I:0:
#

class Client:
    
    def __init__(self,transport,argv):

        """
        A unix-domain client of an isconf server.  This client is very
        thin -- all the smarts are on the server side.

        argv is e.g. ('snap', '-v', '/tmp/foo') 
        """
        args = ''
        # if verbose: print >>sys.stderr, argv
        for arg in argv:
            if ' ' in arg:
                # escape embedded "'"
                arg.replace("'","\'")
                # wrap arg in "'"
                arg = "'%s'" % arg
            args += "%s " % arg
        args = args.rstrip()
        # if verbose: print >>sys.stderr, args

        txd = "isconf4\nc:%s:%s\n" % (len(args), args)
        # this is a blocking write...
        transport.write(txd)
        expect = 'isconf4\n'
        rxd = ''
        while len(rxd) < len(expect):
            rxd += transport.read(1)
        if rxd != expect:
            return self.clierr(PROTOCOL_MISMATCH, rxd)

        rxd = ''
        size = 1
        # process one message each time through loop
        while True:
            # this is a blocking read...
            rxd += transport.read(size)
            (rectype,data) = parsemsg(rxd)
            if rectype == SHORT_READ:
                size = int(data)
                continue
            elif rectype == 'r':
                code = int(data)
                return code
            elif rectype == 'o': sys.stdout.write(data)
            elif rectype == 'e': sys.stderr.write(data)
            elif rectype == 'I':
                for line in sys.stdin:
                    txd = "i:%s:%s" % (len(line), line)
                    transport.write(txd)
                transport.shutdown()
            elif rectype == BAD_RECORD:
                return self.clierr(rectype, data)
            else:
                return self.clierr(INVALID_RECTYPE, data)
            rxd = ''
            size = 1
            
    def clierr(self,macro,msg=''):
        msg = "%s: %s" % (macro[1], msg)
        print >>sys.stderr, msg
        return macro[0]

class ServerFactory:

    def __init__(self,socks):
        self.socks = socks

class CLIServerFactory(ServerFactory):

    def run(self):
        while True:
            yield self.socks.wait()
            sock = self.socks.rx()
            server = CLIserver(sock=sock)
            kernel.spawn(server.run())

class CLIServer:

    def __init__(self,sock):
        self.transport=sock

    def run(self):
        self.transport.write("isconf4\n")
        rxd = ''
        size = 1
        # process one message each time through loop
        while True:
            yield None
            if self.transport.state == 'down':
                return
            rxd += self.transport.read(size)
            (rectype,data) = self.parsemsg(rxd)
            if rectype == SHORT_READ:
                size = int(data)
                continue
            elif rectype == 'c':
                # XXX migrate from 4.1.7 starting here
                self.transport.write("got %s\n" % data)
                # print "got %s" % data
                stdout = os.popen(data,'r')
                for line in stdout:
                    yield None
                    print line
                    self.transport.write("o:%d:%s" % (len(line), line))
                self.transport.write("r:2:10")
                self.transport.close()
                return
            elif rectype == 'i':
                # XXX 
                pass
            elif rectype == BAD_RECORD:
                self.srverr(rectype, data)
            else:
                self.srverr(INVALID_RECTYPE, data)
            rxd = ''
            size = 1

    def srverr(self,macro,msg=''):
        msg = "%s: %s" % (macro[1], msg)
        strerrno = str(macro[0])
        self.transport.write("e:%d:%s" % (len(msg), msg))
        self.transport.write("r:%d:%s" % (len(strerrno), strerrno))
        self.transport.close()

def parsemsg(self,rxd):
    m = re.match("\n*(\w):(\d+):(.*)",rxd,re.S)
    if not m:
        if len(rxd) > 20 or rxd.count(':') > 1:
            return (BAD_RECORD, rxd)
        return (SHORT_READ, 1)
    rectype = m.group(1)
    size = int(m.group(2))
    data = m.group(3)
    if len(data) < size:
        return (SHORT_READ, size - len(data))
    return (rectype,data)

def branch(val=None):
    varisconf = os.environ['VARISCONF']
    fname = "%s/branch" % varisconf
    if val is not None:
        open(fname,'w').write(val)
    val = open(fname,'r').read()
    return val

