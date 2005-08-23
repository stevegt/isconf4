# vim:set expandtab:
# vim:set foldmethod=indent:
# vim:set shiftwidth=4:
# vim:set tabstop=4:

from __future__ import generators
import ConfigParser
import copy
import email.Message
import email.Parser
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
from isconf.Errno import iserrno
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
                busexit(iserrno.EINVAL, 
                    "first message must be cmd, got %s" % rectype)
                return
            verb = msg['verb']
            if verb == 'exec': verb = 'Exec' # sigh
            args=[]
            if len(data):
                data = data.strip()
                args = data.split('\n')
            ops = Ops()
            try:
                func = getattr(ops,verb)
            except AttributeError:
                busexit(outpin,iserrno.EINVAL,verb)
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

    def ci(self,opt,args,data,inpin,outpin):
        fbp=fbp822()
        yield None
        volname = branch()
        volume = ISFS.Volume(volname)
        if not cklock(outpin,volname,opt['logname']):
            return
        volume.ci()
        busexit(outpin,iserrno.OK) 

    def Exec(self,opt,args,data,inpin,outpin):
        fbp=fbp822()
        yield None
        volname = branch()
        volume = ISFS.Volume(volname)
        if not cklock(outpin,volname,opt['logname']):
            return
        message = opt['message']
        if message is not None:
            if not volume.lock(opt['logname'],message):
                busexit(outpin,iserrno.NOTLOCKED,
                        'failed relocking %s' % volname) 
                return
        else:
            message=''
        if not len(args):
            busexit(outpin,iserrno.EINVAL,"missing exec command")
            return
        cwd = opt['cwd']
        # XXX this should be a generator, show progressive stdout, stderr
        (rc,stdout,stderr) = volume.Exec(args,cwd)
        outpin.tx(str(fbp.mkmsg('stdout',stdout)))
        outpin.tx(str(fbp.mkmsg('stderr',stderr)))
        outpin.tx(str(fbp.mkmsg('rc',rc)))
        outpin.close()

    def lock(self,opt,args,data,inpin,outpin):
        fbp=fbp822()
        yield None
        volname = branch()
        volume = ISFS.Volume(volname)
        if volume.locked() and not cklock(outpin,volname,opt['logname']):
            return
        if not opt['message']:
            busexit(outpin,iserrno.NEEDMSG,'did not lock %s' %
                    volname)
            return
        if volume.lock(opt['logname'],opt['message']):
            busexit(outpin,iserrno.OK) 
            return
        busexit(outpin,iserrno.NOTLOCKED,'attempt to lock %s failed' % volname) 


    def snap(self,opt,args,data,inpin,outpin):
        fbp=fbp822()
        yield None
        volname = branch()
        volume = ISFS.Volume(volname)
        if not cklock(outpin,volname,opt['logname']):
            return
        message = opt['message']
        if message is not None:
            if not volume.lock(opt['logname'],message):
                busexit(outpin,iserrno.NOTLOCKED,'failed relocking %s' %
                        volname) 
                return
        else:
            message=''
        if not len(args):
            busexit(outpin,iserrno.EINVAL,"missing snapshot pathname")
            return
        if len(args) > 1:
            busexit(outpin,iserrno.EINVAL,
                    "can only snapshot one file at a time (for now)")
            return
        path = args[0]
        cwd = opt['cwd']
        path = os.path.join(cwd,path)
        if not os.path.exists(path):
            busexit(outpin,iserrno.ENOENT,path)
            return
        if not os.path.isfile(path):
            busexit(outpin,iserrno.EINVAL,"%s is not a file" % path)
            return
        st = os.stat(path)
        src = open(path,'r')
        dst = volume.open(path,'w',message=message)
        dst.setstat(st)
        while True:
            data = src.read(1024 * 1024 * 1)
            if not len(data):
                break
            dst.write(data)
        src.close()
        dst.close()
        busexit(outpin,iserrno.OK) 



    def unlock(self,opt,args,data,inpin,outpin):
        fbp=fbp822()
        yield None
        volname = branch()
        locker = volume.lockedby()
        if locker:
            if not volume.unlock():
                busexit(outpin,iserrno.LOCKED,'attempt to unlock %s failed' %
                        volname) 
                return
            outpin.tx(fbp.mkmsg('stderr',
                "broke %s lock -- please notify %s\n" % (volname,locker))
                )
        busexit(outpin,iserrno.OK) 
        
    def up(self,opt,args,data,inpin,outpin):
        fbp=fbp822()
        yield None
        volname = branch()
        volume = ISFS.Volume(volname)
        volume.update()
        busexit(outpin,iserrno.OK) 

            
def branch(val=None):
    varisconf = os.environ['VARISCONF']
    fname = "%s/branch" % varisconf
    if not os.path.exists(fname):
        val = 'generic'
    if val is not None:
        open(fname,'w').write(val)
    val = open(fname,'r').read()
    return val

def busexit(errpin,code,msg=''):
    desc = iserrno.strerror(code)
    if str or msg:
        msg = "%s: %s\n" % (str(msg), desc)
    fbp=fbp822()
    if msg and code:
        error(msg)
        msg = "isconf: error: " + msg
        errpin.tx(str(fbp.mkmsg('stderr',msg)))
    errpin.tx(str(fbp.mkmsg('rc',code)))
    errpin.close()

# XXX this should really be moved to ISFS Volume
def cklock(errpin,volname,logname):
    """ensure that volume is locked, and locked by logname"""
    volume = ISFS.Volume(volname)
    lockmsg = volume.locked()
    if not lockmsg:
        busexit(errpin,iserrno.NOTLOCKED, "%s branch is not locked" % volname)
        return False
    if not volume.lockedby(logname):
        busexit(errpin,iserrno.LOCKED,
                "%s branch is locked by %s" % (volname,lockmsg))
        return False
    return True

def client(transport,argv,kwopt):

    """
    A unix-domain client of an isconf server.  This client is very
    thin -- all the smarts are on the server side.

    argv is e.g. ('snap', '/tmp/foo') 
    """
    def clierr(code,msg=''):
        desc = iserrno.strerror(code)
        msg = "%s: %s" % (msg, desc)
        print >>sys.stderr, msg
        return code

    fbp = fbp822()
    verb = argv.pop(0)
    if len(argv):
        payload = "\n".join(argv) + "\n"
    else:
        payload = ''
    logname = os.environ['LOGNAME']
    cwd = os.getcwd()
    msg = fbp.mkmsg('cmd',payload,verb=verb,logname=logname,cwd=cwd,**kwopt)

    # this is a blocking write...
    transport.write(str(msg))

    stream = fbp.fromStream(transport)
    # process one message each time through loop
    while True:
        try:
            msg = stream.next()
        except StopIteration:
            return clierr(iserrno.ECONNRESET)
        except Error822, e:
            return clierr(iserrno.EBADMSG,e)
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
            return clierr(iserrno.EINVAL, rectype)
        
