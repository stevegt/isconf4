from __future__ import generators
import ConfigParser
import copy
import email.Message
import email.Parser
import email.Utils
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
import tempfile
import time
import urllib2

import isconf
from isconf.Errno import iserrno
from isconf.Globals import *
from isconf.fbp822 import fbp822
from isconf.Kernel import kernel

(START,IHAVE,SENDME) = range(3)

# XXX the following were migrated from 4.1.7 for now -- really need to
# be FBP components, at least in terms of logging

class Cache:
    """a combined cache manager and UDP mesh -- XXX needs to be split

    >>> pid = os.fork()
    >>> if not pid:
    ...     time.sleep(999)
    ...     sys.exit(0)
    >>> os.environ["HOSTNAME"] = "testhost"
    >>> os.environ["IS_HOME"] = "/tmp/var/is"
    >>> cache = Cache(54321,54322)
    >>> assert cache
    >>> os.kill(pid,9)

    """

    def __init__(self,udpport,httpport,timeout=2):
        self.req = {}
        self.udpport = udpport
        self.httpport = httpport
        self.timeout = timeout
        self.lastSend = 0
        self.sock = None
        self.fetched = {}
        self.nets = self.readnets()

        # temporary uid -- uniquely identifies host in non-persistent
        # packets.  If we want something permanent we should store it
        # somewhere under private.
        self.tuid = "%s@%s" % (random.random(),
                os.environ['HOSTNAME']) 

        class Path: pass
        self.p = Path()

        home = os.environ['IS_HOME']
        # XXX redundant with definitions in ISFS.py -- use a common lib?
        self.p.cache = os.path.join(home,"fs/cache")
        self.p.private = os.path.join(home,"fs/private")
        self.p.announce   = "%s/.announce"       % (self.p.private)
        self.p.pull    = "%s/.pull"        % (self.p.private)

        for d in (self.p.cache,self.p.private):
            if not os.path.isdir(d):
                os.makedirs(d,0700)

    def readnets(self):
        # read network list
        nets = {'udp': [], 'tcp': []}
        netsfn = os.environ.get('IS_NETS',None)
        debug("netsfn", netsfn)
        if netsfn and os.path.exists(netsfn):
            netsfd = open(netsfn,'r')
            for line in netsfd:
                (scheme,addr) = line.strip().split()
                nets[scheme].append(addr)
        debug("nets", str(nets))
        return nets

    def ihaveTx(self,path):
        path = path.lstrip('/')
        fullpath = os.path.join(self.p.cache,path)
        mtime = 0
        if not os.path.exists(fullpath):
            warn("file gone: %s" % fullpath)
            return
        mtime = os.path.getmtime(fullpath)
        # XXX HMAC
        reply = FBP.msg('ihave',tuid=self.tuid,
                file=path,mtime=mtime,port=self.httpport,scheme='http')
        self.bcast(str(reply))

    def bcast(self,msg):
        # XXX only udp supported so far
        for addr in ['<broadcast>'] + self.nets['udp']:
            self.sock.sendto(msg,0,(addr,self.udpport))

    def ihaveRx(self,msg,ip):
        yield None
        scheme = msg['scheme']
        port = msg['port']
        path = msg['file']
        mtime = msg.head.mtime
        url = "%s://%s:%s/%s" % (scheme,ip,port,path)
        # XXX HMAC
        path = path.lstrip('/')
        # simple check to ignore foreign domains 
        # XXX probably want to make this a list of domains
        domain  = os.environ['IS_DOMAIN']
        if not path.startswith(domain + '/'):
            debug("foreign domain, ignoring: %s" % path)
            return
        fullpath = os.path.join(self.p.cache,path)
        mymtime = 0
        debug("checking",url)
        if os.path.exists(fullpath):
            mymtime = os.path.getmtime(fullpath)
        if mtime > mymtime:
            debug("remote is newer:",url)
            if self.req.has_key(path):
                self.req[path]['state'] = SENDME
            yield kernel.wait(self.wget(path,url))
            self.ihaveTx(path)
        elif mtime < mymtime:
            debug("remote is older:",url)
            self.ihaveTx(path)
        else:
            debug("remote and local times are the same:",path,mtime,mymtime)


    def puller(self):
        tmp = "%s.tmp" % self.p.pull
        while True:
            timeout= self.timeout
            yield None
            # get list of files
            if not os.path.exists(self.p.pull):
                # hmm.  we must have died while pulling
                if os.path.exists(tmp):
                    old = open(tmp,'r').read()
                    open(self.p.pull,'a').write(old)
                open(self.p.pull,'a')
            os.rename(self.p.pull,tmp)
            # files = open(tmp,'r').read().strip().split("\n")
            data = open(tmp,'r').read()
            if not len(data):
                open(self.p.pull,'a')
                yield kernel.sigsleep, 1
                continue
            files = data.strip().split("\n")
            # create requests
            for path in files:
                path = path.lstrip('/')
                fullpath = os.path.join(self.p.cache,path)
                mtime = 0
                if os.path.exists(fullpath):
                    mtime = os.path.getmtime(fullpath)
                req = FBP.msg('whohas',file=path,newer=mtime,tuid=self.tuid)
                # XXX HMAC
                self.req.setdefault(path,{})
                self.req[path]['msg'] = req
                self.req[path]['expires'] = time.time() + timeout
                self.req[path]['state'] = START
            while True:
                # send requests
                yield None
                self.resend()
                yield kernel.sigsleep, timeout/5
                # see if they've all been filled or timed out
                # debug(str(self.req))
                if not self.req:
                    # okay, all done -- touch the file so ISFS knows
                    open(self.p.pull,'a')
                    break

    def resend(self):
        """(re)send outstanding requests"""
        if time.time() < self.lastSend + .5:
            return
        self.lastSend = time.time()
        paths = self.req.keys()
        for path in paths:
            debug("resend",path,self.req[path])
            if self.req[path]['state'] > START:
                # XXX kludge -- what we really need is a dict which
                # shows the "mirror list" of all known locations for
                # files, rather than self.req
                pass
            elif time.time() > self.req[path]['expires']:
                debug("timeout",path)
                del self.req[path]
                continue
            req = self.req[path]['msg']
            self.bcast(str(req))

    def flush(self):
        if not os.path.exists(self.p.announce):
            return
        tmp = "%s.tmp" % self.p.announce
        os.rename(self.p.announce,tmp)
        files = open(tmp,'r').read().strip().split("\n")
        for path in files:
            self.ihaveTx(path)

    def wget(self,path,url):
        yield None
        # XXX kludge to keep from beating up HTTP servers
        if self.fetched.get(url,0) > time.time() - 5:
            debug("toosoon",path,url)
            if self.req.has_key(path):
                del self.req[path]
            return
        self.fetched[path] = time.time()
        info("fetching", url)
        path = path.lstrip('/')
        fullpath = os.path.join(self.p.cache,path)
        (dir,file) = os.path.split(fullpath)
        # XXX security checks on pathname
        mtime = 0
        if os.path.exists(fullpath):
            mtime = os.path.getmtime(fullpath)
        if not os.path.exists(dir):
            os.makedirs(dir,0700)
        u = urllib2.urlopen(url)
        uinfo = u.info()
        (mod,size) = (uinfo.get('last-modified'), uinfo.get('content-size'))
        mod_secs = email.Utils.mktime_tz(email.Utils.parsedate_tz(mod))
        if mod_secs <= mtime:
            warn("not newer:",url,mod,mod_secs,mtime)
            if self.req.has_key(path):
                del self.req[path]
            return
        debug(url,size,mod)
        # XXX show progress
        # XXX large files
        data = u.read()
        tmp = os.path.join(dir,".%s.tmp" % file)
        # XXX set umask somewhere early
        # XXX use the following algorithm as a more secure way of creating
        # files that aren't world readable 
        if os.path.exists(tmp): os.unlink(tmp)
        open(tmp,'w')
        os.chmod(tmp,0600)
        open(tmp,'w')
        open(tmp,'a').write(data)
        meta = (mod_secs,mod_secs)
        os.rename(tmp,fullpath)
        os.utime(fullpath,meta)
        if self.req.has_key(path):
            del self.req[path]

    def run(self):
        from SocketServer import UDPServer
        from isconf.fbp822 import fbp822, Error822

        kernel.spawn(self.puller())

        dir = self.p.cache
        udpport = self.udpport

        debug("UDP server serving %s on port %d" % (dir,udpport))
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock = sock
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, True)
        sock.setblocking(0)
        sock.bind(('',udpport))     
        # laddr = sock.getsockname()
        # localip = os.environ['HOSTNAME']
        while True:
            yield None
            self.flush()
            yield None
            try:
                data,addr = sock.recvfrom(8192)
                # XXX check against addrs
                debug("from %s: %s" % (addr,data))
                factory = fbp822()
                msg = factory.parse(data)
                type = msg.type().strip()
                debug("gottype '%s'" % type)
                if msg.head.tuid == self.tuid:
                    # debug("one of ours -- ignore",str(msg))
                    continue
                if type == 'whohas':
                    path = msg['file']
                    path = path.lstrip('/')
                    fullpath = os.path.join(dir,path)
                    fullpath = os.path.normpath(fullpath)
                    newer = int(msg.get('newer',None))
                    # security checks
                    # XXX HMAC
                    bad=0
                    if fullpath != os.path.normpath(fullpath): 
                        bad += 1
                    if dir != os.path.commonprefix(
                            (dir,os.path.abspath(fullpath))):
                        print dir,os.path.commonprefix(
                            (dir,os.path.abspath(fullpath)))
                        bad += 2
                    if bad:
                        warn("unsafe request %d from %s: %s" % (
                            bad,addr,fullpath))
                        continue
                    if not os.path.isfile(fullpath):
                        debug("ignoring whohas from %s: not found: %s" % (addr,fullpath))
                        continue
                    if newer is not None and newer >= os.path.getmtime(
                            fullpath):
                        debug("ignoring whohas from %s: not newer: %s" % (addr,fullpath))
                        continue
                    # url = "http://%s:%d/%s" % (localip,httpport,path)
                    self.ihaveTx(path)
                    continue
                if type == 'ihave':
                    debug("gotihave:",str(msg))
                    ip = addr[0]
                    yield kernel.wait(self.ihaveRx(msg,ip))
                    continue
                warn("unsupported message type from %s: %s" % (addr,type))
            except socket.error:
                yield kernel.sigsleep, 1
                continue
            except Exception, e:
                warn("%s from %s: %s" % (e,addr,str(msg)))
                continue


def httpServer(port,dir):
    from BaseHTTPServer import HTTPServer
    from isconf.HTTPServer import SimpleHTTPRequestHandler
    from SocketServer import ForkingMixIn
    
    def logger(*args): 
        msg = str(args)
        open("/tmp/isconf.http.log",'a').write(msg+"\n")
    SimpleHTTPRequestHandler.log_message = logger
    
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
            yield kernel.sigsleep, .1
            # includes EAGAIN
            continue
        except Exception, e:
            debug("get_request exception:", str(e))
            yield kernel.sigsleep, 1
            continue
        # XXX filter request -- e.g. do we need directory listings?
        # XXX HMAC in path info
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

