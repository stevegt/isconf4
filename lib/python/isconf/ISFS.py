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
from isconf.Globals import *

# XXX the following were migrated directly from 4.1.7 for now --
# really need to be FBP components, at least in terms of logging

def httpServer(port,dir):
    from BaseHTTPServer import HTTPServer
    from SimpleHTTPServer import SimpleHTTPRequestHandler
    from SocketServer import ForkingMixIn
    
    if not os.path.isdir(dir):
        os.makedirs(dir,0700)
    os.chdir(dir)

    class ForkingServer(ForkingMixIn,HTTPServer): pass

    serveraddr = ('',port)
    svr = ForkingServer(serveraddr,SimpleHTTPRequestHandler)
    svr.socket.setblocking(0)
    debug("HTTP server serving %s on port %d" % (dir,port))
    while True:
        yield None
        try:
            request, client_address = svr.get_request()
        except socket.error:
            # includes EAGAIN
            continue
        # XXX filter request -- e.g. do we need directory listings?
        try:
            # process_request does the fork...  For now we're going to
            # say that it's okay that the Kernel and other tasks fork
            # with it; since process_request does not yield, nothing
            # else will run in the child before it exits.
            os.chdir(dir)
            svr.process_request(request, client_address)
        except:
            svr.handle_error(request, client_address)
            svr.close_request(request)


def udpServer(udpport,httpport,dir):
    from SocketServer import UDPServer
    from isconf.fbp822 import fbp822, Error822

    if not os.path.isdir(dir):
        os.makedirs(dir,0700)

    debug("UDP server serving %s on port %d" % (dir,udpport))
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
    sock.setblocking(0)
    sock.bind(('',udpport))     
    # laddr = sock.getsockname()
    # localip = os.environ['HOSTNAME']
    while True:
        yield None
        try:
            data,addr = sock.recvfrom(8192)
            debug("from %s: %s" % (addr,data))
            factory = fbp822()
            msg = factory.parse(data)
            type = msg.type()
            if type == 'whohas':
                fname = msg['file']
                tell = msg['tell']
                newer = int(msg.get('newer',None))
                # security checks
                os.chdir(dir)
                ok=True
                if fname != os.path.normpath(fname): 
                    ok=False
                if dir != os.path.commonprefix((dir,os.path.abspath(fname))):
                    ok=False
                if not ok:
                    error("unsafe request from %s: %s" % (addr,fname))
                    continue
                if not os.path.isfile(fname):
                    debug("from %s: not found: %s" % (addr,fname))
                    continue
                if newer is not None and newer > os.path.getmtime(fname):
                    debug("from %s: not newer: %s" % (addr,fname))
                    continue
                # url = "http://%s:%d/%s" % (localip,httpport,fname)
                reply = factory.mkmsg('ihave',
                        file=fname,port=httpport,scheme='http')
                sock.sendto(str(reply),0,addr)
                continue
            # cache flood listener 
            if type == 'ihave':
                fname = msg['file']
                kernel.spawn(pull(fname))
            error("unsupported message type from %s: %s" % (addr,type))
        except socket.error:
            continue
        except Exception, e:
            error("%s from %s: %s" % (e,addr,data))
            continue


def announce(relpath):
    pass

def pull(relpath,tmp=None):
    pass

class Journal:

    def __init__(self,cache,private,domvol):
        self.relpath = "%s/journal" % (domvol)
        self.abspath = "%s/%s" % (cache,  self.relpath)
        self.absnew  = "%s/%s.new" % (private,self.relpath)
        debug("journal abspath", self.abspath)
        debug("journal absnew", self.absnew)
    
    def XXXentries(self):
        if self.lock.locked():
            return False
        pull(self.relpath)
        
class Lock:

    def __init__(self,cache,domvol):
        self.relpath = "%s/lock" % (domvol)
        self.abspath = "%s/%s" % (cache,self.relpath)
        debug("lock abspath", self.abspath)
    
    def locked(self):
        pull(self.relpath)
        if os.path.exists(self.abspath):
            msg = open(self.abspath,'r').read()
            msg += ": " + time.ctime(os.path.getmtime(self.abspath))
            return msg
        return False

    def lockedby(self,logname=None):
        msg = self.locked()
        if not msg:
            return None
        m = re.match('(\S+@\S+):',msg)
        if not m:
            return None
        actual = m.group(1)
        if logname:
            wanted = "%s@%s" % (logname,os.environ['HOSTNAME'])
            debug("wanted", wanted, "actual", actual)
            if wanted == actual:
                return wanted
        else:
            return actual
        
    def lock(self,logname,msg):
        msg = "%s@%s: %s" % (logname,os.environ['HOSTNAME'],str(msg))
        if self.locked() and not self.lockedby(logname):
            return False
        if not msg:
            return False
        open(self.abspath,'w').write(msg)
        announce(self.relpath)
        return self.locked()

    def unlock(self):
        locker = self.lockedby()
        if locker:
            os.unlink(self.abspath)
        if self.locked():
            return False
        return True

class Volume:

    def __init__(self,volume):
        cache   = os.environ['ISFS_CACHE']
        private = os.environ['ISFS_PRIVATE']
        domain  = os.environ['ISFS_DOMAIN']
        self.domvol    = "%s/volume/%s" % (domain,volume)
        self.cache     = cache
        self.private   = private
        for dir in (self.cache,self.private):
            if not os.path.isdir(dir):
                os.makedirs(dir,0700)
        self.lock    = Lock(self.cache,self.domvol)
        self.journal = Journal(self.cache,self.private,self.domvol)
        debug("volume cache", self.cache)

