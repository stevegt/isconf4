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
from isconf import ISFS
from isconf.Kernel import kernel, Bus
from isconf.fbp822 import fbp822, Error822

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
            opt = dict(msg.items())
            if opt['message'] == 'None':
                opt['message'] = None
            debug(opt)
            # get cmd from client
            if rectype != 'cmd':
                busexit(INVALID_RECTYPE, 
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
                busexit(outpin,INVALID_VERB,verb)
                return
            # start command processor
            kernel.spawn(
                func(opt=opt,args=args,data=data,inpin=inpin,outpin=outpin)
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

class Ops:
    """ISconf server-side operations"""

    def lock(self,opt,args,data,inpin,outpin):
        fbp=fbp822()
        yield None
        volume = branch()
        lock = ISFS.Volume(volume).lock
        if lock.locked() and not cklock(outpin,volume,opt['logname']):
            return
        if not opt['message']:
            busexit(outpin,MESSAGE_REQUIRED,'did not lock %s' % volume)
            return
        if lock.lock(opt['logname'],opt['message']):
            busexit(outpin,NORMAL) 
            return
        busexit(outpin,NOTLOCKED,'attempt to lock %s failed' % volume) 

    def snap(self,opt,args,data,inpin,outpin):
        fbp=fbp822()
        yield None
        volume = branch()
        if not cklock(outpin,volume,opt['logname']):
            return
        if opt['message']:
            if not lock.lock(opt['logname'],opt['message']):
                busexit(outpin,NOTLOCKED,'failed relocking %s' % volume) 
                return
            
    def unlock(self,opt,args,data,inpin,outpin):
        fbp=fbp822()
        yield None
        volume = branch()
        lock = ISFS.Volume(volume).lock
        locker = lock.lockedby()
        if locker:
            if not lock.unlock():
                busexit(outpin,LOCKED,'attempt to unlock %s failed' % volume) 
                return
            outpin.tx(fbp.mkmsg('stderr',
                "broke %s lock -- please notify %s\n" % (volume,locker))
                )
        busexit(outpin,NORMAL) 
        
            
            



def branch(val=None):
    varisconf = os.environ['VARISCONF']
    fname = "%s/branch" % varisconf
    if not os.path.exists(fname):
        val = 'generic'
    if val is not None:
        open(fname,'w').write(val)
    val = open(fname,'r').read()
    return val

def cklock(errpin,volume,logname):
    lock = ISFS.Volume(volume).lock
    lockmsg = lock.locked()
    if not lockmsg:
        busexit(errpin,NOTLOCKED, "%s branch is not locked" % volume)
        return False
    if not lock.lockedby(logname):
        busexit(errpin,LOCKED,"%s branch is locked by %s" % (volume,lockmsg))
        return False
    return True

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
    logname = os.environ['LOGNAME']
    msg = fbp.mkmsg('cmd',payload,verb=verb,logname=logname,**kwopt)

    # this is a blocking write...
    transport.write(str(msg))

    stream = fbp.fromStream(transport)
    # process one message each time through loop
    while True:
        try:
            msg = stream.next()
        except StopIteration:
            return clierr(SERVER_CLOSE)
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
        
def busexit(errpin,macro,msg=''):
        if macro[1] or msg:
            msg = "%s: %s\n" % (macro[1], str(msg))
        fbp=fbp822()
        if msg and macro[0]:
            error(msg)
            msg = "error: " + msg
            errpin.tx(str(fbp.mkmsg('stderr',msg)))
        strerrno = str(macro[0])
        errpin.tx(str(fbp.mkmsg('rc',strerrno)))
        errpin.close()




