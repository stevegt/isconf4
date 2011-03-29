from __future__ import generators
import ConfigParser
import copy
import email.Message
import email.Parser
import email.Utils
import errno
import hmac
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
        # XXX kludge -- what we really need is a dict which
        # shows the "mirror list" of all known locations for
        # files, rather than self.req
        self.req = {}
        self.udpport = udpport
        self.httpport = httpport
        self.timeout = float(timeout)
        self.lastSend = 0
        self.sock = None
        self.fetched = {}
        self.nets = self.readnets()
        self.sendq = []

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
        mtime = getmtime_int(fullpath)
        reply = FBP.msg('ihave',tuid=self.tuid,
                file=path,mtime=mtime,port=self.httpport,scheme='http')
        HMAC.msgset(reply)
        self.bcast(str(reply))

    def bcast(self,msg):
        # XXX only udp supported so far
        debug("bcast")
        addrs = self.nets['udp']
        if not os.environ.get('IS_NOBROADCAST',None):
            addrs.append('<broadcast>')
        for addr in addrs:
            if len(self.sendq) > 20:
                debug("sendq overflow")
                return
            self.sendq.append((msg,addr,self.udpport))

    def sender(self):
        while True:
            yield None
            yield kernel.sigsleep, 1
            while len(self.sendq):
                msg,addr,udpport = self.sendq.pop(0)
                try:
                    debug("sendto", addr, msg)
                    self.sock.sendto(msg,0,(addr,udpport))
                except:
                    info("sendto failed: %s" % addr)
                    self.sendq.append((msg,addr,udpport))
                    yield kernel.sigsleep, 1
                yield kernel.sigsleep, self.timeout/5.0


    def ihaveRx(self,msg,ip):
        yield None
        scheme = msg['scheme']
        port = msg['port']
        path = msg['file']
        mtime = msg.head.mtime
        # XXX is python's pseudo-random good enough here?  
        #
        # probably, but for other cases, use 'gpg --gen-random 2 16'
        # to generate 128 bits of random data from entropy
        #
        challenge = str(random.random())
        url = "%s://%s:%s/%s?challenge=%s" % (scheme,ip,port,path,challenge)
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
            mymtime = getmtime_int(fullpath)
        if mtime > mymtime:
            debug("remote is newer:",url)
            if self.req.has_key(path):
                self.req[path]['state'] = SENDME
            yield kernel.wait(self.wget(path,url,challenge))
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
                    mtime = getmtime_int(fullpath)
                req = FBP.msg('whohas',file=path,newer=mtime,tuid=self.tuid)
                HMAC.msgset(req)
                self.req.setdefault(path,{})
                self.req[path]['msg'] = req
                self.req[path]['expires'] = time.time() + timeout
                self.req[path]['state'] = START
            while True:
                # send requests
                yield None
                debug("calling resend")
                self.resend()
                yield kernel.sigsleep, 1
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
            debug("resend", self.req[path]['expires'], path, self.req[path])
            if self.req[path]['state'] > START:
                # file is being fetched
                debug("resend fetching")
                pass
            elif time.time() > self.req[path]['expires']:
                # fetch never started
                debug("timeout",path)
                del self.req[path]
                continue
            req = self.req[path]['msg']
            debug("calling bcast")
            self.bcast(str(req))

    def flush(self):
        if not os.path.exists(self.p.announce):
            return
        tmp = "%s.tmp" % self.p.announce
        os.rename(self.p.announce,tmp)
        files = open(tmp,'r').read().strip().split("\n")
        for path in files:
            self.ihaveTx(path)

    def wget(self,path,url,challenge):
        """

        # >>> port=random.randrange(50000,60000)
        # >>> class fakesock:
        # ...     def sendto(self,msg,foo,bar): 
        # ...         print "sendto called"
        # >>> srcdir="/tmp/var/is/fs/cache/"
        # >>> pridir="/tmp/var/isdst/fs/private/"
        # >>> if not os.path.exists(srcdir):
        # ...     os.makedirs(srcdir)
        # >>> if not os.path.exists(pridir):
        # ...     os.makedirs(pridir)
        # >>> open(srcdir + "foo",  'w').write("lakfdsjl")
        # >>> open(pridir + ".pull",'w').write("foo\\n")
        # >>> h = kernel.spawn(httpServer(port=port,dir=srcdir))
        # >>> kernel.run(steps=1000)
        # >>> os.environ["HOSTNAME"] = "testhost"
        # >>> os.environ["IS_HOME"] = "/tmp/var/isdst"
        # >>> shutil.rmtree("/tmp/var/isdst",ignore_errors=True)
        # >>> cache = Cache(54321,port)
        # >>> assert cache
        # >>> cache.sock = fakesock()
        # >>> url = "http://localhost:%d/foo" % port
        # >>> w = kernel.spawn(cache.wget("foo",url,"abc"))
        # >>> kernel.run(steps=1000)
        # >>> open("/tmp/var/isdst/fs/cache/foo",'r').read()

        """
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
            mtime = getmtime_int(fullpath)
        if not os.path.exists(dir):
            os.makedirs(dir,0700)
        try:
            u = urllib2.urlopen(url)
        except:
            debug("HTTP failed opening %s" % url)
            return
        uinfo = u.info()
        response = uinfo.get('x-hmac')
        if not HMAC.ck(challenge,response):
            debug("HMAC failed, abort fetching: %s" % url)
            return
        mod = uinfo.get('last-modified')
        size = uinfo.get('content-length')
        mod_secs = email.Utils.mktime_tz(email.Utils.parsedate_tz(mod))
        if mod_secs <= mtime:
            warn("not newer:",url,mod,mod_secs,mtime)
            if self.req.has_key(path):
                del self.req[path]
            return
        debug(url,size,mod)
        tmp = os.path.join(dir,".%s.tmp" % file)
        # XXX set umask somewhere early
        # XXX use the following algorithm everywhere else as a more 
        # secure way of creating files that aren't world readable 
        # -- also see os.mkstemp()
        if os.path.exists(tmp): os.unlink(tmp)
        open(tmp,'w')
        os.chmod(tmp,0600)
        open(tmp,'w')  # what does this second open do?
        tmpfd = open(tmp,'a')
        while True:
            # XXX move timeout to here
            yield kernel.sigbusy
            try:
                (r,w,e) = select.select([u],[],[u],0)
                if e:
                    # XXX not sure if we should break or raise here
                    break
                if not r:
                    continue
            except:
                # python 2.4 throws a "no fileno attribute" exception if 
                # the entire page content has already arrived
                pass
            try:
                rxd = u.read(8192) 
            except:
                break
            if len(rxd) == 0:
                break
            # XXX show progress
            tmpfd.write(rxd)
        tmpfd.close()
        actual_size = os.stat(tmp).st_size
        if size is None:
            warn("""
            The host at %s is running an older version of
            ISconf; that older version does not send content-length
            headers, so we can't check the length of files it sends
            us; we might store a corrupt file as a result.  You should 
            upgrade that host to a more recent ISconf version soon.
            """)
        else:
            size = int(size)
            if size != actual_size:
                debug("size mismatch: wanted %d got %d, abort fetching: %s" % 
                        (size, actual_size, url))
                return
        meta = (mod_secs,mod_secs)
        os.rename(tmp,fullpath)
        os.utime(fullpath,meta)
        if self.req.has_key(path):
            del self.req[path]
        self.ihaveTx(path)

    def run(self):
        from SocketServer import UDPServer
        from isconf.fbp822 import fbp822, Error822

        kernel.spawn(self.puller())
        kernel.spawn(self.sender())

        # XXX most of the following should be broken out into a receiver() task

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
                # XXX check against addrs or nets
                debug("from %s: %s" % (addr,data))
                factory = fbp822()
                msg = factory.parse(data)
                type = msg.type().strip()
                if msg.head.tuid == self.tuid:
                    # debug("one of ours -- ignore",str(msg))
                    continue
                if not HMAC.msgck(msg):
                    debug("HMAC failed, dropping: %s" % msg)
                    continue
                if type == 'whohas':
                    path = msg['file']
                    path = path.lstrip('/')
                    fullpath = os.path.join(dir,path)
                    fullpath = os.path.normpath(fullpath)
                    newer = int(msg.get('newer',None))
                    # security checks
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
                    if newer is not None and newer >= getmtime_int(
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
    from SocketServer import ThreadingMixIn

    """

    # >>> port=random.randrange(50000,60000)
    # >>> srcdir="/tmp/var/is/fs/cache/"
    # >>> if not os.path.exists(srcdir):
    # >>>     os.makedirs(srcdir)
    # >>> open(srcdir + "foo",'w').write("lakfdsjl")
    # >>> pid = os.fork()
    # >>> if not pid:
    # >>>     kernel.run(httpServer(port=port,dir=srcdir))
    # >>> time.sleep(1)
    # >>> u = urllib2.urlopen("http://localhost:%d/foo" % port)
    # >>> k = u.info().keys()
    # >>> k.sort()
    # >>> k
    # ['content-length', 'content-type', 'date', 'last-modified', 'server']
    # >>> u.read()     
    # 'lakfdsjl'
    # >>> os.kill(pid,9)

    """

    # Note:  Switched from ForkingMixIn to ThreadingMixIn around
    # 4.2.8.206 in order to remove nasty race condition between the
    # waitpid() calls generated by the popen2 library in
    # ISFS.updateExec and by the SocketServer.ForkingMixIn.  The HTTP
    # server was sometimes reaping exec processes and stealing the
    # exit status...  ForkingMixIn is *not* thread-safe or
    # microtask-safe, because it calls waitpid(0, ...) rather than
    # using the child pid list it already has.  Argh.
    
    def logger(*args): 
        msg = str(args)
        open("/tmp/isconf.http.log",'a').write(msg+"\n")
    SimpleHTTPRequestHandler.log_message = logger
    
    if not os.path.isdir(dir):
        os.makedirs(dir,0700)
    os.chdir(dir)

    class ThreadingServer(ThreadingMixIn,HTTPServer): pass

    serveraddr = ('',port)
    svr = ThreadingServer(serveraddr,SimpleHTTPRequestHandler)
    svr.daemon_threads = True
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

class Hmac:
    '''HMAC key management

    >>> HMAC = Hmac(ckfreq=1)
    >>> keyfile = "/tmp/hmac_keys-test-case-data"
    >>> factory = fbp822()
    >>> msg = factory.mkmsg('red apple')
    >>> os.environ['IS_HMAC_KEYS'] = ""
    >>> msg.hmacset('foo')
    '8ca8301bb1a077358ce8c3e9a601d83a2643f33d'
    >>> HMAC.msgck(msg)
    True
    >>> os.environ['IS_HMAC_KEYS'] = keyfile
    >>> open(keyfile,'w').write("\\n\\n")
    >>> time.sleep(2)
    >>> msg.hmacset('foo')
    '8ca8301bb1a077358ce8c3e9a601d83a2643f33d'
    >>> HMAC.msgck(msg)
    True
    >>> open(keyfile,'w').write("someauthenticationkey\\nanotherkey\\n")
    >>> time.sleep(2)
    >>> HMAC.msgset(msg)
    '0abf42fd374fc75cdc4bd0284f4c9ec48f9e0569'
    >>> HMAC.msgck(msg)
    True
    >>> msg.hmacset('foo')
    '8ca8301bb1a077358ce8c3e9a601d83a2643f33d'
    >>> HMAC.msgck(msg)
    False
    >>> msg.hmacset('anotherkey')
    '51116aaa8bc9de5078850b9347aa95ada066b259'
    >>> HMAC.msgck(msg)
    True
    >>> msg.hmacset('someauthenticationkey')
    '0abf42fd374fc75cdc4bd0284f4c9ec48f9e0569'
    >>> HMAC.msgck(msg)
    True
    >>> res = HMAC.response('foo')
    >>> res
    '525a59615b881ab282ca60b2ab31e82aec7e31db'
    >>> HMAC.ck('foo',res)
    True
    >>> HMAC.ck('foo','afds')
    False
    >>> HMAC.ck('bar',res)
    False
    >>> open(keyfile,'a').write("+ANY+\\n")
    >>> time.sleep(2)
    >>> HMAC.msgset(msg)
    '0abf42fd374fc75cdc4bd0284f4c9ec48f9e0569'
    >>> HMAC.msgck(msg)
    True
    >>> msg.hmacset('foo')
    '8ca8301bb1a077358ce8c3e9a601d83a2643f33d'
    >>> HMAC.msgck(msg)
    True
    >>> HMAC.ck('foo','afds')
    True

    '''
    
    def __init__(self,ckfreq=10):
        self.expires = 0
        self.mtime = 0
        self.ckfreq = ckfreq
        self.reset()

    def reset(self):
        self._keys = []
        self.any = False

    def reload(self):
        path = os.environ.get('IS_HMAC_KEYS',None)
        if not path:
            return []
        if time.time() > self.expires \
                and os.path.exists(path) \
                and self.mtime < getmtime_int(path):
            self.expires = time.time() + self.ckfreq
            debug("reloading",path)
            self.mtime = getmtime_int(path)
            self.reset()
            for line in open(path,'r').readlines():
                line = line.strip()
                if line.startswith('#'):
                    continue
                if not len(line):
                    continue
                if line == '+ANY+':
                    self.any = True
                    continue
                self._keys.append(line)
        # debug('XXX keys',self._keys)
        return self._keys

    def msgck(self,msg):
        keys = self.reload()
        if not len(keys):
            return True
        if self.any:
            return True
        for key in keys:
            if msg.hmacok(key):
                return True
        return False

    def msgset(self,msg):
        keys = self.reload()
        if not len(keys):
            return
        key = keys[0]
        return msg.hmacset(key)

    def ck(self,challenge,response):
        debug('ck(): challenge',challenge)
        debug('ck(): response',response)
        keys = self.reload()
        if not len(keys):
            return True
        if self.any:
            return True
        for key in keys:
            h = hmac.new(key,msg=challenge,digestmod=sha)
            digest = h.hexdigest()
            if digest == response:
                debug('ck: response ok')
                debug('XXX ck(): key',key)
                return True
        debug('ck: bad response')
        return False

    def response(self,challenge):
        keys = self.reload()
        if not len(keys):
            return
        key = keys[0]
        h = hmac.new(key,msg=challenge,digestmod=sha)
        response = h.hexdigest()
        debug('response(): challenge',challenge)
        debug('response(): response',response)
        return response

HMAC = Hmac()



