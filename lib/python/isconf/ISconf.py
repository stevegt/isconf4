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
from isconf.Kernel import kernel, Bus
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
    verb = argv.pop(0)
    if len(argv):
        payload = "\n".join(argv) + "\n"
    else:
        payload = ''
    msg = fbp.mkmsg('cmd',payload,verb=verb,**kwopt)

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
            slist = []
            yield self.socks.rx(slist)
            for sock in slist:
                server = CLIServer(sock=sock)
                kernel.spawn(server.run())

class CLIServer:

    def __init__(self,sock):
        self.transport=sock

    def run(self):
        yield kernel.sigbusy # speed things up a bit
        debug("CLIServer running")
        fbp = fbp822()

        # set up FBP buses
        frcli = Bus()
        tocli = Bus()

        # read messages from client
        str = kernel.spawn(fbp.fromStream(stream=self.transport,outpin=frcli))
        # process messages from client
        proc = kernel.spawn(self.process(inpin=frcli,outpin=tocli))
        # send messages to client
        res = kernel.spawn(self.respond(transport=self.transport,inpin=tocli))

    def process(self,inpin,outpin):
        while True:
            yield None
            mlist = []
            yield inpin.rx(mlist,timeout=0,count=1)
            msg = mlist[0]
            if msg in (kernel.eagain,None):
                continue
            if outpin.state == 'down':
                return
            if msg is kernel.eof:
                outpin.close()
                return
            debug("from client:", str(msg))
            rectype = msg.type()
            data = msg.payload()
            opts = msg.items()
            # get cmd from client
            if rectype != 'cmd':
                self.srverr(INVALID_RECTYPE, 
                    "first message must be cmd, got %s" % rectype)
                return
            verb = msg['verb']
            args=[]
            if len(data):
                args = data.split('\n')
            ops = Ops()
            try:
                func = getattr(ops,verb)
            except AttributeError:
                self.srverr(INVALID_VERB, verb)
                return
            # start command processor
            kernel.spawn(
                func(opts=opts,args=args,data=data,inpin=inpin,outpin=outpin)
                )
            break

    def respond(self,transport,inpin):
        while True:
            yield None
            mlist = []
            yield inpin.rx(mlist)
            for msg in mlist:
                if transport.state == 'down':
                    return
                if msg in (kernel.eagain,None):
                    continue
                if msg is kernel.eof:
                    transport.close()
                    return
                debug("to client:", str(msg))
                transport.write(str(msg))

    # XXX bypasses FBP
    def srverr(self,macro,msg=''):
        msg = "%s: %s\n" % (macro[1], str(msg))
        strerrno = str(macro[0])
        fbp=fbp822()
        error(msg)
        self.transport.write(str(fbp.mkmsg('stderr',msg)))
        self.transport.write(str(fbp.mkmsg('rc',strerrno)))
        self.transport.close()

class Ops:
    """ISconf server-side operations"""

    # XXX migrate from 4.1.7 to here

    def snap(self,opts,args,data,inpin,outpin):
        fbp=fbp822()
        yield None
        while not outpin.tx(fbp.mkmsg('rc',234)): yield None


def branch(val=None):
    varisconf = os.environ['VARISCONF']
    fname = "%s/branch" % varisconf
    if val is not None:
        open(fname,'w').write(val)
    val = open(fname,'r').read()
    return val

