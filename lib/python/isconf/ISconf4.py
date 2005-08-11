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


class ISconf4:
    """ISconf protocol version 4"""

    def __init__(self,transport):
        self.transport=transport

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
    def client(self,argv):
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
        self.transport.write(txd)
        expect = 'isconf4\n'
        rxd = ''
        while len(rxd) < len(expect):
            rxd += self.transport.read(1)
        if rxd != expect:
            return self.clierr(PROTOCOL_MISMATCH, rxd)

        rxd = ''
        size = 1
        # process one message each time through loop
        while True:
            # this is a blocking read...
            rxd += self.transport.read(size)
            (rectype,data) = self.parsemsg(rxd)
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
                    self.transport.write(txd)
                    self.socket.shutdown(1)
            elif rectype == BAD_RECORD:
                return self.clierr(rectype, data)
            else:
                return self.clierr(INVALID_RECTYPE, data)
            rxd = ''
            size = 1
                
    # XXX move kernel.error to module globals, refactor to work on
    # either client or server, kill this
    def clierr(self,macro,msg=''):
        msg = "%s: %s" % (macro[1], msg)
        print >>sys.stderr, msg
        return macro[0]

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

    def run(self):
        kernel.info("starting ISconf4.run")

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

class UNIXClientSocket:
    """a blocking UNIX domain client socket"""

    def __init__(self, varisconf, chunksize=4096):
        self.chunksize = chunksize
        self.ctl = "%s/.ctl" % varisconf
        self.role = 'client'
        self.state = 'up'
        self.txd = ''
        self.rxd = ''
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.setblocking(1)
        # print self.ctl
        self.sock.connect(self.ctl)

    def close(self):
        self.sock.close()

    def read(self,size):
        rxd = ''
        while len(rxd) < size:
            newrxd = self.sock.recv(size - len(rxd))
            if not newrxd:
                return rxd
            rxd += newrxd
        return rxd

    def write(self,txd):
        sent = 0
        while sent < len(txd):
            sent += self.sock.send(txd[sent:])
        return sent

