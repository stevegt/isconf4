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

    def __init__(self,volume,path,mode):
        self.volume = volume
        self.path = path
        self.mode = mode
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
        parent = os.path.dirname(self.path)
        pathmodes = []
        while True:
            pstat = os.stat(parent)
            mug = "%d:%d:%d" % (pstat.st_mode,pstat.st_uid,pstat.st_gid)
            pathmodes.insert(0,mug)
            if len(parent) == 1:
                assert parent == '/'
                break
            parent = os.path.dirname(parent)
            assert len(parent) >= 1
        # XXX pathname needs to be relative to volroot
        msg = fbp.mkmsg('snap',data,
                pathname=self.path,
                st_mode = self.st.st_mode,
                st_uid = self.st.st_uid,
                st_gid = self.st.st_gid,
                st_atime = self.st.st_atime,
                st_mtime = self.st.st_mtime,
                pathmodes = ','.join(pathmodes)
                )
        debug("calling addwip")
        yield kernel.wait(self.volume.addwip(msg))
        self.volume.closefile(self)
        info("snapshot done:", self.path)

class Journal:

    def __init__(self,fullpath):
        self.path = fullpath
        self._entries = []
        self._mtime = 0

    def addraw(self,data):
        fh = open(self.path,'a')
        fh.write(data)
        fh.close()
        self._mtime = 0

    def copy(self,other):
        """Given another journal object, ensure self is empty, then 
        copy its entire contents into this one.  Return True if
        success.

        >>> raw  = str(FBP.msg('test',xid='abcd'))
        >>> raw += str(FBP.msg('test',xid='defg'))
        >>> raw += str(FBP.msg('test',xid='efgh'))
        >>> afn = tempfile.mktemp()
        >>> bfn = tempfile.mktemp()
        >>> a = Journal(afn)
        >>> b = Journal(bfn)
        >>> a.addraw(raw)
        >>> assert b.copy(a)
        >>> [ x.head.xid for x in a.entries() ]
        ['abcd', 'defg', 'efgh']
        >>> [ x.head.xid for x in b.entries() ]
        ['abcd', 'defg', 'efgh']
        >>> assert not b.copy(a)

        """
        if self.entries():
            return False
        ofn = other.path
        shutil.copy(ofn,self.path)
        self._mtime = 0
        return True

    def entries(self):
        if not hasattr(self,"_entries"):
            self._entries = []
        if os.path.exists(self.path):
            mtime = os.path.getmtime(self.path)
            if mtime != self._mtime:
                self._entries = self._parse()
                self._mtime = mtime
        else:
            self._entries = []
        return self._entries

    def migrate(self,other,append=False):
        """Given another journal object, ensure other is a superset of
        self, then if append=True, append remaining entries from other 
        to self.  Return True if success, False otherwise.

        >>> raw  = str(FBP.msg('test',xid='abcd'))
        >>> raw += str(FBP.msg('test',xid='defg'))
        >>> raw += str(FBP.msg('test',xid='efgh'))
        >>> afn = tempfile.mktemp()
        >>> bfn = tempfile.mktemp()
        >>> a = Journal(afn)
        >>> b = Journal(bfn)
        >>> a.addraw(raw)
        >>> assert len(a.entries()) == 3
        >>> assert b.migrate(a)
        >>> assert len(b.entries()) == 0
        >>> assert b.migrate(a,append=True)
        >>> assert len(b.entries()) == 3
        >>> raw = str(FBP.msg('test',xid='hijk'))
        >>> a.addraw(raw)
        >>> assert len(a.entries()) == 4
        >>> assert b.migrate(a)
        >>> assert len(b.entries()) == 3
        >>> assert b.migrate(a)
        >>> assert len(b.entries()) == 3
        >>> assert not a.migrate(b)
        >>> raw = str(FBP.msg('test',xid='jklm'))
        >>> b.addraw(raw)
        >>> assert len(b.entries()) == 4
        >>> assert not b.migrate(a)
        >>> [ x.head.xid for x in a.entries() ]
        ['abcd', 'defg', 'efgh', 'hijk']
        >>> [ x.head.xid for x in b.entries() ]
        ['abcd', 'defg', 'efgh', 'jklm']

        """
        sentries = self.entries()
        oentries = other.entries()
        # make sure other is a superset
        if len(sentries) > len(oentries):
            return False
        i=0
        while i < len(sentries):
            if str(sentries[i]) != str(oentries[i]):
                return False
            i += 1
        if not append:
            return True
        # append new entries from other
        while i < len(oentries):
            self.addraw(str(oentries[i]))
            i += 1
        return True

    def mtime(self):
        # do NOT update self._mtime here -- entries() needs to do that
        mtime = 0
        if os.path.exists(self.path):
            mtime = os.path.getmtime(self.path)
        return mtime

    def _parse(self):
        entries = []
        journal = open(self.path,'r')
        messages = FBP.fromFile(journal)
        for msg in messages:
            if msg in (kernel.eagain,None):
                continue
            entries.append(msg)
        return entries

class History:

    def __init__(self,fullpath):
        self.path = fullpath
        self._xids = []
        self._mtime = 0

    def add(self,msg):
        line = "%d %s\n" % (time.time(), msg['xid'])
        open(self.path,'a').write(line)

    def xidlist(self):
        mtime = os.path.getmtime(self.path)
        if mtime != self._mtime:
            self.reload()
            self._mtime = mtime
        return self._xids

    def reload(self):
        self._xids = []
        for line in open(self.path,'r').readlines():
            (time,xid) = line.strip().split()
            self._xids.append(xid)

class Volume:

    # XXX provide logname and mode on open, check/get lock then
    def __init__(self,volname,logname,outpin,histfile):  
        self.volname = volname
        self.logname = logname
        self.outpin = outpin

        # set standard paths; rule 1: only absolute paths get stored
        # in p, use mkrelative to convert as needed
        class Path: pass
        self.p = Path()
        self.p.history = histfile
        self.p.cache = os.environ['ISFS_CACHE']
        self.p.private = os.environ['ISFS_PRIVATE']
        domain  = os.environ['ISFS_DOMAIN']
        domvol    = "%s/volume/%s" % (domain,volname)
        cachevol     = "%s/%s" % (self.p.cache,domvol)
        privatevol   = "%s/%s" % (self.p.private,domvol)

        self.p.announce   = "%s/.announce"       % (self.p.private)
        self.p.pull    = "%s/.pull"        % (self.p.private)

        self.p.journal = "%s/journal"     % (cachevol)
        self.p.lock    = "%s/lock"        % (cachevol)
        self.p.block   = "%s/%s/block"    % (self.p.cache,domain)

        self.p.wip     = "%s/journal.wip" % (privatevol)
        # XXX for upgrade of test machines -- deprecate after release
        self.p.oldhistory = "%s/history"     % (privatevol)
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

        if not os.path.isfile(self.p.history):
            if os.path.isfile(self.p.oldhistory):
                os.rename(self.p.oldhistory,self.p.history)
            else:
                open(self.p.history,'w')
                os.chmod(self.p.history,0700)

        self.openfiles = {}

        self.volroot = "/"
        # XXX temporary solution to allow for testing, really need to
        # read from self.p.volroot instead
        if os.environ.has_key('ISFS_VOLROOT'):
            self.volroot = os.environ['ISFS_VOLROOT']

        self.journal = Journal(self.p.journal)
        self.history = History(self.p.history)

    def mkabsolute(self,path):
        if not path.startswith(self.p.cache):
            path = path.lstrip('/')
            os.path.join(self.p.cache,path)
        return path

    def mkrelative(self,path):
        if path.startswith(self.p.cache):
            path = path[len(self.p.cache):]
        return path

    def announce(self,path):
        # write the filename to the announce list -- the cache manager
        # will announce the new file and handle transfers
        path = self.mkrelative(path)
        open(self.p.announce,'a').write(path + "\n")

    def pull(self,bg=False):
        files = (
                self.mkrelative(self.p.journal),
                self.mkrelative(self.p.lock)
                )
        yield kernel.wait(self.pullfiles(files))
        files = self.pendingfiles()
        if bg:
            kernel.spawn(self.pullfiles(files))
        else:
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
                yield kernel.sigsleep, .1
                continue
            if os.path.getsize(self.p.pull) == 0:
                break

    def addwip(self,msg):
        debug("in addwip")
        yield kernel.sigbusy
        xid = "%f.%f@%s" % (time.time(),random.random(),
                os.environ['HOSTNAME'])
        msg['xid'] = xid
        message = self.lockmsg()
        msg.setheader('message', message)
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
            # XXX large files
            open(path,'w').write(data)
            self.announce(path)

            # apply the update now rather than wait for up command
            debug("spawning updateSnap")
            task = kernel.spawn(self.updateSnap(msg),itermode=True)

        if msg.type() == 'exec':
            # run the command
            debug("spawning updateExec")
            task = kernel.spawn(self.updateExec(msg),itermode=True)

        # check results of snap or exec
        res = None
        # we only need the last yield value
        for res in task: 
            yield kernel.sigbusy
            debug("got from updateX", repr(res), kernel.isrunning(task.tid))
        # false result means failure
        if not res:
            yield res
            return
        # append message to journal wip
        open(self.p.wip,'a').write(str(msg))

        # add a couple of newlines to ensure message separation
        open(self.p.wip,'a').write("\n\n")


    def Exec(self,argdata,cwd):
        # XXX what about when cwd != volroot?
        if not self.cklock(): return 
        msg = FBP.mkmsg('exec', argdata + "\n", cwd=cwd)
        yield kernel.wait(self.addwip(msg))
        argv = argdata.split("\n")
        info("exec done:", str(argv))
            
    def blk2path(self,blk):
        print blk
        dir = "%s/%s" % (self.p.block,blk[:3])
        if not os.path.isdir(dir):
            os.makedirs(dir,0700)
        path = "%s/%s" % (dir,blk)
        return path
                    
    def ci(self):
        wipdata = self.wip()
        if not wipdata:
            if not self.cklock(): 
                return 
            info("no outstanding updates")
            self.unlock()
            return 
        if not self.cklock(): return 
        jtime = self.journal.mtime()
        yield kernel.wait(self.pull())
        if not self.cklock(): return
        # if jtime and jtime != self.journal.mtime():
        if jtime != self.journal.mtime():
            error("someone else checked in conflicting changes -- repair wip and retry")
            return
        if self.journal.mtime() > os.path.getmtime(self.p.wip):
            error("journal is newer than wip -- repair and retry")
            return
        self.journal.addraw(wipdata)
        os.unlink(self.p.wip)
        self.announce(self.p.journal)
        info("changes checked in")
        self.unlock()

    def closefile(self,fh):
        del self.openfiles[fh]

    def locked(self):
        if os.path.exists(self.p.lock) and os.path.getsize(self.p.lock):
            msg = open(self.p.lock,'r').read()
            return msg
        return False

    def lockmsg(self):
        if os.path.exists(self.p.lock) and os.path.getsize(self.p.lock):
            msg = open(self.p.lock,'r').read()
            msg += " (lock time %s)" % time.ctime(os.path.getmtime(self.p.lock))
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
        lockmsg = self.lockmsg()
        volname = self.volname
        if not self.locked():
            error(iserrno.NOTLOCKED, "%s is not locked" % volname)
            return False
        if not self.lockedby(logname):
            error(iserrno.LOCKED,
                    "%s is locked by: %s" % (volname,lockmsg))
            return False
        return True

    def lock(self,message):
        logname = self.logname
        message = "%s@%s: %s" % (logname,os.environ['HOSTNAME'],str(message))
        yield kernel.wait(self.pull())
        if self.locked() and not self.cklock():
            return 
        open(self.p.lock,'w').write(message)
        self.announce(self.p.lock)
        info("%s locked" % self.volname)
        if not self.locked():
            error(iserrno.NOTLOCKED,'attempt to lock %s failed' % self.volname) 

    def open(self,path,mode):
        if not self.cklock(): return False
        fh = File(volume=self,path=path,mode=mode)
        self.openfiles[fh]=1
        return fh

    def setstat(self,path,st):
        print st.st_mode,st.st_uid,st.st_gid,st.st_atime,st.st_mtime
        os.chmod(path,st.st_mode)
        os.chown(path,st.st_uid,st.st_gid)
        os.utime(path,(st.st_atime,st.st_mtime))

    def unlock(self):
        locker = self.lockedby()
        info("removing lock on %s set by %s" % (self.volname,locker)) 
        open(self.p.lock,'w')
        self.announce(self.p.lock)
        assert not self.locked()
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
                yield kernel.wait(self.updateSnap(msg))
            if msg.type() == 'exec': 
                yield kernel.wait(self.updateExec(msg))
        info("update done")

    def pending(self):
        """
        Return an ordered list of the journal messages which need to be
        processed for the next update.
        """
        done = self.history.xidlist()

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
            if not msg.type() == 'snap':
                continue
            blk = msg.head.blk
            path = self.mkrelative(self.blk2path(blk))
            files.append(path)
        return files

    def updateSnap(self,msg):
        src = self.blk2path(msg['blk'])
        if not os.path.exists(src):
            error("missing block: %s" % src)
            yield False
            return
        # XXX large files, atomicity, missing parent dirs
        debug("opening",src)
        data = open(src,'r').read()
        # XXX volroot
        dst = msg['pathname']
        dstdir = os.path.dirname(dst)
        dstpath = dstdir.split('/')
        pathmodes = msg['pathmodes'].split(',')
        debug("dstpath %s" % repr(dstpath))
        debug("pathmodes %s" % repr(pathmodes))
        assert len(dstpath) == len(pathmodes)
        # create any missing parent dirs
        for i in range(len(pathmodes)):
            pathmode = pathmodes[i]
            (st_mode,st_uid,st_gid) = pathmode.split(':')
            curpath = '/'.join(dstpath[:i+1]) + '/'
            assert curpath[0] == '/'
            debug("checking %s" % curpath)
            if not os.path.isdir(curpath):
                debug('creating path %s as %s' % (curpath,pathmode))
                os.mkdir(curpath,int(st_mode))
                os.chown(curpath,int(st_uid),int(st_gid))
        open(dst,'w').write(data)
        # update history
        self.history.add(msg)
        class St: pass
        st = St()
        for attr in "st_mode st_uid st_gid st_atime st_mtime".split():
            setattr(st,attr,getattr(msg.head,attr))
        self.setstat(dst,st)
        info("updated", dst)
        yield True
        debug("updateSnap done")

    def updateExec(self,msg):
        argv = msg.data().strip().split("\n")
        cwd = msg['cwd']
        os.chdir(cwd)
        info("running", str(argv))
        popen = popen2.Popen3(argv,capturestderr=True)
        (stdin, stdout, stderr) = (
                popen.tochild, popen.fromchild, popen.childerr)
        stdin.close()
        outputs = [stdout,stderr]
        while True:
            yield kernel.sigbusy
            for f in outputs:
                try:
                    (r,w,e) = select.select([f],[],[f],.2)
                    # print r,w,e
                    for f in r:
                        rxd = f.read()
                        if len(rxd) == 0:
                            f.close()
                        if f is stdout: 
                            outmsg = FBP.msg('stdout',rxd)
                            self.outpin.tx(outmsg)
                        if f is stderr: 
                            errmsg = FBP.msg('stderr',rxd)
                            self.outpin.tx(errmsg)
                except:
                    outputs.remove(f)
            if not len(outputs):
                break
        status = popen.wait()
        rc = os.WEXITSTATUS(status)
        if rc:
            error("returned", rc, ": ", str(argv))
            yield False
            return
        # update history
        self.history.add(msg)
        yield True


    def wip(self):
        if os.path.exists(self.p.wip):
            wipdata = open(self.p.wip,'r').read()
            return wipdata
        return []


# XXX the following were migrated directly from 4.1.7 for now --
# really need to be FBP components, at least in terms of logging
# XXX move to Cache

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

