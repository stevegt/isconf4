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

class Volume:

    # XXX provide logname and mode on open, check/get lock then
    def __init__(self,volname):  
        self.volname = volname

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
        # read from self.p.volroot
        if os.environ.has_key('ISFS_VOLROOT'):
            self.volroot = os.environ['ISFS_VOLROOT']

    def mkabsolute(self,path):
        if not path.startswith(self.p.cache):
            os.path.join(self.p.cache,path)
        return path

    def mkrelative(self,path):
        if path.startswith(self.p.cache):
            path = path[len(self.p.cache):]
        return path

    def announce(self,path):
        path = self.mkrelative(path)
        udpAnnounce(path)

    def pull(self,path,test=False):
        path = self.mkrelative(path)
        # XXX spawn?
        udpPull(path)

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

    def Exec(self,args,cwd):
        # XXX what about when cwd != volroot?
        cmd = ' '.join(map(lambda a: "'%s'" % a,args))
        msg = FBP.mkmsg('exec', cmd=cmd, cwd=cwd)
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
        # XXX check for remote changes
        journal = open(self.p.journal,'a')
        journal.write(wipdata)
        journal.close()
        os.unlink(self.p.wip)
        self.announce(self.p.journal)
        info("changes checked in")
        self.unlock()

    def closefile(self,fh):
        del self.openfiles[fh]

    def locked(self):
        self.pull(self.p.lock)
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
        
    def lock(self,logname,msg):
        msg = "%s@%s: %s" % (logname,os.environ['HOSTNAME'],str(msg))
        if self.locked() and not self.lockedby(logname):
            return False
        if not msg:
            return False
        open(self.p.lock,'w').write(msg)
        self.announce(self.p.lock)
        info("%s locked" % self.volname)
        return self.locked()

    def open(self,path,mode,message=None):
        # XXX check lock
        if not self.wip():
            self.pull(self.p.journal)
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
            return False
        info("%s unlocked" % self.volname)
        return True

    def update(self):
        fbp = fbp822()

        if self.wip():
            error("local changes in progress")
            return False
        
        info("checking for updates")
        done = open(self.p.history,'r').readlines()
        done = map(lambda xid: xid.strip(),done)

        file = open(self.p.journal,'r')
        messages = fbp.fromFile(file)
        i=0
        while True:
            try:
                msg = messages.next()
            except StopIteration:
                break
            except Error822, e:
                raise
            if msg in (kernel.eagain,None):
                continue
            # compare history with journal
            if msg['xid'] in done:
                continue
            debug(msg['pathname'])
            i += 1
            if msg.type() == 'snap': 
                if not self.updateSnap(msg):
                    error("aborting update")
                    return False
            if msg.type() == 'exec': 
                if not self.updateExec(msg):
                    error("aborting update")
                    return False
        if not i:
            info("no new updates")
        info("update done")

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

def udpAnnounce(path):
    pass

def udpPull(path):
    pass

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
                    warn("unsafe request from %s: %s" % (addr,fname))
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
                kernel.spawn(udpPull(fname))
            warn("unsupported message type from %s: %s" % (addr,type))
        except socket.error:
            continue
        except Exception, e:
            warn("%s from %s: %s" % (e,addr,data))
            continue
