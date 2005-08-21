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
from isconf.fbp822 import fbp822, Error822


# XXX kill this -- using fbp822 instead
#
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

def client(transport,argv,kwopt):

    """
    A unix-domain client of an isconf server.  This client is very
    thin -- all the smarts are on the server side.

    argv is e.g. ('snap', '/tmp/foo') 
    """
    def clierr(macro,msg=''):
        msg = "%s: %s" % (macro[1], msg)
        print >>sys.stderr, msg
        return macro[0]

    fbp = fbp822()
    payload = "\n".join(argv) + "\n"
    msg = fbp.mkmsg('cmd',payload,**kwopt)

    # this is a blocking write...
    transport.write(str(msg))

    stream = fbp.fromStream(transport)
    # process one message each time through loop
    while True:
        try:
            msg = stream.next()
        except StopIteration:
            return clierr(UNKNOWN_RC)
        except Error822, e:
            return clierr(BAD_RECORD,e)
        if msg in (kernel.eagain,None):
            continue
        rectype = msg.type()
        data = msg.payload()
        if rectype == 'rc':
            code = int(data)
            return code
        elif rectype == 'stdout': sys.stdout.write(data)
        elif rectype == 'stderr': sys.stderr.write(data)
        elif rectype == 'reqstdin':
            for line in sys.stdin:
                msg = fbp.mkmsg('stdin',line)
                transport.write(str(msg))
            transport.shutdown()
        else:
            return clierr(INVALID_RECTYPE, rectype)
        
class CLIServerFactory:

    def __init__(self,socks):
        self.socks = socks

    def run(self):
        while True:
            yield self.socks.wait()
            sock = self.socks.rx()
            server = CLIServer(sock=sock)
            kernel.spawn(server.run())

class CLIServer:

    def __init__(self,sock):
        self.transport=sock

    def run(self):
        debug("CLIServer running")
        # process one message each time through loop
        fbp = fbp822()
        stream = kernel.spawn(fbp.fromStream(self.transport),step=True)
        while True:
            yield None
            try:
                msg = stream.next()
            except StopIteration:
                return
            except Error822, e:
                error("from client:", e)
                return
            if msg in (kernel.eagain,None):
                continue
            if self.transport.state == 'down':
                return
            rectype = msg.type()
            data = msg.payload()
            if rectype == 'cmd':
                debug("from client:", str(msg))
                # XXX migrate from 4.1.7 starting here

                

                if False:   # XXX
                    cmd = ' '.join(data.split("\n"))
                    print "cmd:", cmd
                    stdout = os.popen(cmd,'r')
                    for line in stdout:
                        yield None
                        self.transport.write("o:%d:%s" % (len(line), line))
                    self.transport.write("r:2:10\n")
                    self.transport.close()
                    return
            elif rectype == 'stdin':
                # XXX stdin from client arrives here
                pass
            else:
                self.srverr(INVALID_RECTYPE, rectype)
            rxd = ''
            size = 1

    def srverr(self,macro,msg=''):
        msg = "%s: %s" % (macro[1], msg)
        strerrno = str(macro[0])
        self.transport.write("e:%d:%s" % (len(msg), msg))
        self.transport.write("r:%d:%s" % (len(strerrno), strerrno))
        self.transport.close()

def branch(val=None):
    varisconf = os.environ['VARISCONF']
    fname = "%s/branch" % varisconf
    if val is not None:
        open(fname,'w').write(val)
    val = open(fname,'r').read()
    return val

