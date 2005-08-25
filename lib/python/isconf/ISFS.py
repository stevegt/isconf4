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
import tempfile
import time
import urllib2

import isconf
from isconf.Errno import iserrno
from isconf.Globals import *
from isconf.fbp822 import fbp822
from isconf.Kernel import kernel

class XXXFile:
    # XXX This version stores one block per write -- this is the way
    # we want to go.  The thing missing here is that we need to nest
    # block write messages inside of one outer message, and
    # write the whole thing to wip when we close.  Store blocks as they
    # arrive, don't clean cache while volume is locked. 

    # XXX only support complete file overwrite for now -- no seek, no tell

    def __init__(self,volume,path,mode,message=None):
        self.volume = volume
        self.path = path
        self.mode = mode
        self.message = message
        self.st = None
        self._tell = 0

    def setstat(self,st):
        if self.mode != 'w':
            return False
        self.st = st
        return True

    def write(self,data):
        if self.mode != 'w':
            raise Exception("not opened for write")
        tmp = tempfile.TemporaryFile()
        tmp.write(data)
        # build journal transaction message
        fbp = fbp822()
        msg = fbp.mkmsg('write',data,
                pathname=self.path,
                message=self.message,
                seek=self._tell,
                )
        self.volume.addwip(msg)
        self._tell += len(data)

    def close(self):
        fbp = fbp822()
        # XXX only support complete file overwrite for now 
        msg = fbp.mkmsg('truncate',
            pathname=path,message=message,seek=self._tell)
        self.volume.addwip(msg)
        self.volume.closefile(self)

class File:

    # XXX only support complete file overwrite for now -- no seek, no tell

    def __init__(self,volume,path,mode,message=None):
        self.volume = volume
        self.path = path
        self.mode = mode
        self.message = message
        self.st = None
        self.tmp = tempfile.TemporaryFile()

    def setstat(self,st):
        if self.mode != 'w':
            return False
        self.st = st
        return True

    def write(self,data):
        if self.mode != 'w':
            raise Exception("not opened for write")
        self.tmp.write(data)

    def close(self):
        # build journal transaction message
        self.tmp.seek(0)
        data = self.tmp.read() # XXX won't work with large files
        fbp = fbp822()
        # XXX pathname needs to be relative to volroot
        msg = fbp.mkmsg('snap',data,
                pathname=self.path,
                message=self.message,
                st_mode = self.st.st_mode,
                st_uid = self.st.st_uid,
                st_gid = self.st.st_gid,
                st_atime = self.st.st_atime,
                st_mtime = self.st.st_mtime,
                )
        self.volume.addwip(msg)
        self.volume.closefile(self)
        info("snapshot done:", self.path)

class Journal:

    def __init__(self,fullpath):
        self.path = fullpath
        self._entries = []
        self.mtime = 0

    def entries(self):
        mtime = os.path.getmtime(self.path)
        if mtime != self.mtime:
            self.reload()
            self.mtime = mtime
        return self._entries

    def reload(self):
        journal = open(self.path,'r')
        messages = FBP.fromFile(journal)
        self._entries = []
        while True:
            try:
                msg = messages.next()
            except StopIteration:
                break
            except Error822, e:
                raise
            if msg in (kernel.eagain,None):
                continue
            self._entries.append(msg)

class Volume:

    # XXX provide logname and mode on open, check/get lock then
    def __init__(self,volname,logname):  
        self.volname = volname
        self.logname = logname

        # set standard paths; rule 1: only absolute paths get stored
        # in p, use mkrelative to convert as needed
        class Path: pass
        self.p = Path()
        self.p.cache = os.environ['ISFS_CACHE']
        self.p.private = os.environ['ISFS_PRIVATE']
        domain  = os.environ['ISFS_DOMAIN']
        domvol    = "%s/volume/%s" % (domain,volname)
        cachevol     = "%s/%s" % (self.p.cache,domvol)
        privatevol   = "%s/%s" % (self.p.private,domvol)

        self.p.journal = "%s/journal"     % (cachevol)
        self.p.lock    = "%s/lock"        % (cachevol)
        self.p.block   = "%s/block"       % (cachevol)

        self.p.wip     = "%s/journal.wip" % (privatevol)
        self.p.history = "%s/history"     % (privatevol)
        self.p.volroot = "%s/volroot"     % (privatevol)
        self.p.dirty   = "%s/dirty"       % (privatevol)
        self.p.pull    = "%s/pull"        % (privatevol)

        debug("isfs cache", self.p.cache)
        debug("journal abspath", self.p.journal)
        debug("journal abswip", self.p.wip)
        debug("journal abshist", self.p.history)
        debug("lock abspath", self.p.lock)
        debug("blockabs", self.p.block)

        for dir in (cachevol,privatevol,self.p.block):
            if not os.path.isdir(dir):
                os.makedirs(dir,0700)

        for fn in (self.p.journal,self.p.history):
            if not os.path.isfile(fn):
                open(fn,'w')
                os.chmod(fn,0700)

        self.openfiles = {}

        self.volroot = "/"
        # XXX temporary solution to allow for testing, really need to
        # read from self.p.volroot instead
        if os.environ.has_key('ISFS_VOLROOT'):
            self.volroot = os.environ['ISFS_VOLROOT']

        self.journal = Journal(self.p.journal)

    def mkabsolute(self,path):
        if not path.startswith(self.p.cache):
            path = path.lstrip('/')
            os.path.join(self.p.cache,path)
        return path

    def mkrelative(self,path):
        if path.startswith(self.p.cache):
            path = path[len(self.p.cache):]
        return path

    def dirty(self,path):
        # write the filename to the dirty list -- the cache manager
        # will announce the new file and handle transfers
        path = self.mkrelative(path)
        open(self.p.dirty,'a').write(path + "\n")

    def pull(self):
        files = (self.p.journal,self.p.lock)
        yield kernel.wait(self.pullfiles(files))
        files = self.pendingfiles()
        yield kernel.wait(self.pullfiles(files))

    def pullfiles(self,files):
        if files:
            txt = '\n'.join(files) + "\n"
            # add filename(s) to the pull list
            open(self.p.pull,'a').write(txt)
        while True:
            yield None
            # wait for cache manager to finish pull -- CM will remove
            # list during pull, then touch it zero-length after pull
            if not os.path.exists(self.p.pull):
                # still working
                continue
            if os.path.getsize(self.p.pull) == 0:
                break

    def addwip(self,msg):
        xid = "%f.%f@%s" % (time.time(),random.random(),
                os.environ['HOSTNAME'])
        msg['xid'] = xid
        message = self.lockmsg()
        msg['message'] = message
        msg.setheader('time',int(time.time()))
        if msg.type() == 'snap':
            data = msg.data()
            s = sha.new(data)
            m = md5.new(data)
            blk = "%s-%s-1" % (s.hexdigest(),m.hexdigest())
            msg['blk'] = blk
            msg.payload('')
            
            path = self.blk2path(blk)
            # XXX check for collisions

            # copy to block tree
            open(path,'w').write(data)

            # run the update now rather than wait for up command
            if not self.updateSnap(msg):
                return False

            # append message to journal wip
            open(self.p.wip,'a').write(str(msg))

        if msg.type() == 'exec':
            # run the command
            if not self.updateExec(msg):
                return False
            # append message to journal wip
            open(self.p.wip,'a').write(str(msg))

    def Exec(self,args,cwd,message):
        # XXX what about when cwd != volroot?
        cmd = ' '.join(map(lambda a: "'%s'" % a,args))
        if not self.cklock(): return 
        if message is None:
            message = self.lockmsg()
        msg = FBP.mkmsg('exec', cmd=cmd, cwd=cwd, message=message)
        self.addwip(msg)
        info("exec done:", ' '.join(map(lambda a: "'%s'" % a,args)))
            
    def blk2path(self,blk):
        debug(blk)
        dir = "%s/%s" % (self.p.block,blk[:4])
        if not os.path.isdir(dir):
            os.makedirs(dir,0700)
        path = "%s/%s" % (dir,blk)
        return path
                    
    def ci(self):
        wipdata = self.wip()
        if not wipdata:
            info("no outstanding updates")
            return 
        if not self.cklock(): return 
        jtime = os.path.getmtime(self.p.journal)
        yield kernel.wait(self.pull())
        if not self.cklock(): return
        if jtime != os.path.getmtime(self.p.journal):
            error("someone else checked in conflicting changes -- repair wip and retry")
            return
        if os.path.getmtime(self.p.journal) > os.path.getmtime(self.p.wip):
            error("journal is newer than wip -- repair and retry")
            return
        journal = open(self.p.journal,'a')
        journal.write(wipdata)
        journal.close()
        os.unlink(self.p.wip)
        self.dirty(self.p.journal)
        info("changes checked in")
        self.unlock()

    def closefile(self,fh):
        del self.openfiles[fh]

    def locked(self):
        if os.path.exists(self.p.lock):
            msg = open(self.p.lock,'r').read()
            msg += ": " + time.ctime(os.path.getmtime(self.p.lock))
            return msg
        return False

    def lockmsg(self):
        if os.path.exists(self.p.lock):
            msg = open(self.p.lock,'r').read()
            return msg
        return 'none'

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
        
    def cklock(self):
        """ensure that volume is locked, and locked by logname"""
        logname = self.logname
        lockmsg = self.locked()
        volname = self.volname
        if not lockmsg:
            error(iserrno.NOTLOCKED, "%s branch is not locked" % volname)
            return False
        if not self.lockedby(logname):
            error(iserrno.LOCKED,
                    "%s branch is locked by %s" % (volname,lockmsg))
            return False
        return True

    def lock(self,message):
        logname = self.logname
        message = "%s@%s: %s" % (logname,os.environ['HOSTNAME'],str(message))
        yield kernel.wait(self.pull())
        if self.locked() and not self.volume.cklock():
            return 
        open(self.p.lock,'w').write(message)
        self.dirty(self.p.lock)
        info("%s locked" % self.volname)
        if not self.locked():
            error(iserrno.NOTLOCKED,'attempt to lock %s failed' % self.volname) 

    def open(self,path,mode,message=None):
        if not self.cklock(): return False
        fh = File(volume=self,path=path,mode=mode,message=message)
        self.openfiles[fh]=1
        return fh

    def setstat(path,st):
        os.chmod(path,st.st_mode)
        os.chown(path,st.st_uid,st.st_gid)
        os.utime(path,(st.st_atime,st.st_mtime))

    def unlock(self):
        locker = self.lockedby()
        if locker:
            os.unlink(self.p.lock)
        if self.locked():
            error(iserrno.LOCKED,'attempt to unlock %s failed' % self.volname) 
            return False
        return True


    def update(self):
        fbp = fbp822()
        if self.wip():
            error("local changes not checked in")
            return 
        info("checking for updates")
        yield kernel.wait(self.pull())
        pending = self.pending()
        if not len(pending):
            info("no new updates")
            return
        for msg in pending:
            debug(msg['pathname'],time.time())
            if msg.type() == 'snap': 
                if not self.updateSnap(msg):
                    error("aborting update")
                    return 
            if msg.type() == 'exec': 
                if not self.updateExec(msg):
                    error("aborting update")
                    return 
        info("update done")

    def pending(self):
        """
        Return an ordered list of the journal messages which need to be
        processed for the next update.
        """
        done = open(self.p.history,'r').readlines()
        done = map(lambda xid: xid.strip(),done)

        msgs = self.journal.entries()
        pending = []
        for msg in msgs:
            # compare history with journal
            if msg['xid'] in done:
                continue
            pending.append(msg)
        return pending

    def pendingfiles(self):
        files = []
        for msg in self.pending():
            files.append(msg.head.pathname)
        return files

    def updateSnap(self,msg):
        path = self.blk2path(msg['blk'])
        # XXX large files, atomicity, missing parent dirs
        # XXX volroot
        data = open(path,'r').read()
        path = msg['pathname']
        open(path,'w').write(data)
        # update history
        open(self.p.history,'a').write(msg['xid'] + "\n")
        info("updated", path)
        # XXX setstat
        return True

    def updateExec(self,msg):
        cmd = msg['cmd']
        cwd = msg['cwd']
        os.chdir(cwd)
        info("running", cmd)
        popen = popen2.Popen3(cmd,capturestderr=True)
        (stdin, stdout, stderr) = (
                popen.tochild, popen.fromchild, popen.childerr)
        # XXX poll, generate messages
        status = popen.wait()
        rc = os.WEXITSTATUS(status)
        out = stdout.read()
        err = stderr.read()
        info(out)
        info(err)
        if rc:
            error("returned", rc, ": ", cmd)
            return False
        # update history
        open(self.p.history,'a').write(msg['xid'] + "\n")
        return True


    def wip(self):
        if os.path.exists(self.p.wip):
            wipdata = open(self.p.wip,'r').read()
            return wipdata
        return []


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

class UDPmesh:

    def __init__(self,udpport,httpport,dir):
        self.req = {}
        self.udpport = udpport
        self.httpport = httpport
        self.dir = dir
        self.lastSend = 0
        self.sock = None
        if not os.path.isdir(dir):
            os.makedirs(dir,0700)


    def announce(self,path):
        path = path.lstrip('/')
        fullpath = os.path.join(self.dir,path)
        mtime = 0
        if not os.path.exists(fullpath):
            warn("file gone: %s" % fullpath)
            return
        mtime = os.path.getmtime(fullpath)
        # XXX HMAC
        reply = FBP.msg('ihave',
                file=path,mtime=mtime,port=self.httpport,scheme='http')
        self.sock.sendto(str(reply),0,('<broadcast>',self.udpport))

    def announceRx(self,msg,ip):
        scheme = msg['scheme']
        port = msg['port']
        path = msg['file']
        mtime = msg.head.mtime
        url = "%s://%s:%s/%s" % (scheme,ip,port,path)
        # XXX HMAC
        path = path.lstrip('/')
        fullpath = os.path.join(self.dir,path)
        mymtime = 0
        if os.path.exists(fullpath):
            mymtime = os.path.getmtime(fullpath)
        if mtime > mymtime:
            self.pull(path,url)
            self.announce(path)
        if mtime < mymtime:
            self.announce(path)

    def find(self,path,timeout=5):
        path = path.lstrip('/')
        fullpath = os.path.join(self.dir,path)
        mtime = 0
        if os.path.exists(fullpath):
            mtime = os.path.getmtime(fullpath)
        req = FBP.msg('whohas',file=path,newer=mtime)
        # XXX HMAC
        start = time.time()
        self.req.setdefault(path,{})
        self.req[path]['msg'] = req
        self.req[path]['expires'] = time.time() + timeout

    def pull(self,path,url):
        # XXX will hang entire server while running -- needs to be a
        # generator
        path = path.lstrip('/')
        fullpath = os.path.join(self.dir,path)
        (dir,file) = os.path.split(fullpath)
        mtime = 0
        if os.path.exists(fullpath):
            mtime = os.path.getmtime(fullpath)
        u = urllib2.urlopen(url)
        info = u.info()
        (mod,size) = (info.get('last-modified'), info.get('content-size'))
        debug(url,size,mod)
        # XXX show progress
        # XXX large files
        data = u.read()
        tmp = os.path.join(dir,"...%s.tmp" % file)
        open(tmp,'w').write(data)
        os.chmod(tmp,0600)
        os.rename(tmp,fullpath)

    def resend(self):
        """(re)send outstanding requests"""
        if time.time() < self.lastSend + 1:
            return
        self.lastSend = time.time()
        paths = self.req.keys()
        for path in paths:
            if time.time() > self.req[path]['expires']:
                del self.req[path]
                continue
            req = self.req[path]['msg']
            debug(req)
            self.sock.sendto(str(req),0,('<broadcast>',self.udpport))

    def run(self):
        from SocketServer import UDPServer
        from isconf.fbp822 import fbp822, Error822

        dir = self.dir
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
            self.resend()
            try:
                data,addr = sock.recvfrom(8192)
                debug("from %s: %s" % (addr,data))
                factory = fbp822()
                msg = factory.parse(data)
                type = msg.type()
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
                        debug("from %s: not found: %s" % (addr,fullpath))
                        continue
                    if newer is not None and newer > os.path.getmtime(
                            fullpath):
                        debug("from %s: not newer: %s" % (addr,fullpath))
                        continue
                    # url = "http://%s:%d/%s" % (localip,httpport,path)
                    self.announce(path)
                    continue
                if type == 'ihave':
                    ip = addr[0]
                    self.announceRx(msg,ip)
                    continue
                warn("unsupported message type from %s: %s" % (addr,type))
            except socket.error:
                continue
            except Exception, e:
                warn("%s from %s: %s" % (e,addr,data))
                continue


