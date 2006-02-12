
# import coverage
import doctest
import os
import pexpect
import popen2
import random
import re
import select
import shutil
import sys
import tempfile
import time
import unittest

sys.path.append("t")
sys.path.append("lib/python")

from isconf.component import component

logfn="runlabtest.log"
logfh = open(logfn,'w')

TIMEOUT=30
if os.environ.get('COVERAGE',False):
    TIMEOUT=60

class Result:
    def __init__(self,rc,out,err):
        self.rc = rc
        self.out = out
        self.err = err
    def __str__(self):
        return self.out
    def verbose(self):
        out  = "stdout: %s" % self.out
        out += "stderr: %s" % self.err
        out += "return code: %d" % self.rc
        return out


class CatError(Exception): pass

class Cmd:
    # XXX this needs to be like IPC::Session

    """

    >>> class host:
    ...     def sess(self,args):
    ...         print "> foo", args
    ... 
    >>> c = Cmd("echo",host())
    >>> c("hi")
    > foo echo hi
    >>> c = Cmd("echo hello",host())
    >>> c()
    > foo echo hello

    """
    
    def __init__(self,cmd,host):
        self.cmd = cmd
        self.host = host
    def __call__(self,args='',rc=0):
        return self.host.sess("%s %s" % (self.cmd,args),rc=rc)

class Host:
    """

    >>> a = Host("localhost",'/tmp')
    localhost> cd /tmp
    >>> a.ssh("echo hi").rc
    # ssh root@localhost echo hi
    hi
    0
    >>> a.ssh("ps > /tmp/1").rc
    # ssh root@localhost ps > /tmp/1
    0
    >>> a.date().rc
    localhost> date 
    0
    >>> print a.echo("hi")
    localhost> echo hi
    hi
    >>> print a.echo("hi > /tmp/1")
    localhost> echo hi > /tmp/1
    >>> a("/tmp/1")
    localhost> cat /tmp/1
    'hi\\n'
    >>> a.ssh("'echo hi there > /tmp/1'").rc
    # ssh root@localhost 'echo hi there > /tmp/1'
    0
    >>> a("/tmp/1")
    localhost> cat /tmp/1
    'hi there\\n'
    >>> a.put('foo &!%#()',"/tmp/1")
    # scp /tmp/tmpuhTmWc root@localhost:/tmp/1
    >>> a("/tmp/1")
    localhost> cat /tmp/1
    'foo &!%#()'
    >>> a.sess("/bin/false").rc
    localhost> /bin/false
    FAIL '1' == '0'
    1
    >>> a.cat("/tmp/doesnotexistlaksjfd",rc=1)
    localhost> cat /tmp/doesnotexistlaksjfd
    <runlabtest.Result instance at 0x40233c4c>

    """

    def __init__(self,hostname,dir=None):
        self._dir = dir
        self._hostname = hostname
        self.s = pexpect.spawn("ssh root@%s" % self._hostname)
        self.s.timeout=TIMEOUT
        time.sleep(5)
        self.s.sendline("stty -echo")
        self.s.sendline("PS1=")
        self.s.expect(".")
        readblind(self.s)
        self.s.sendline("echo START")
        time.sleep(.1)
        self.s.expect("START\r\n")
        # self.s.expect(self.tag)
        self.sess("cd %s" % dir)
        if os.environ.get('COVERAGE',False):
            self.sess("COVERAGE=1; export COVERAGE")
    def __call__(self,args):
        res = self.cat(args)
        if not res.rc == 0:
            raise CatError(path)
        return res.out
    def __getattr__(self,cmd):
        return Cmd(cmd,self)
    def put(self,data,file):
        fn = tempfile.mktemp()
        open(fn,'w').write(data)
        cmd = "scp %s root@%s:%s" % (fn,self._hostname,file)
        log("#", cmd)
        os.system(cmd)
        time.sleep(.1)
    def sess(self,args,rc=0,blind=False,timeout=-1):
        log("%s>" % self._hostname, args)
        tag = str(random.random())
        self.s.sendline("%s; echo errno=$?,%s" % (args,tag))
        time.sleep(.1)
        self.s.expect("(.*)errno=(\d+),%s\r\n" % tag,timeout=timeout)
        m = self.s.match
        out = m.group(1)
        out = out.replace("\r\n","\n")
        realrc = int(m.group(2))
        res = Result(realrc,out,'')
        if not blind: t.rc(res,rc)
        return res
    def ssh(self,args,rc=0,blind=False):
        cmd = "ssh root@%s %s" % (self._hostname,args)
        if os.environ.get('COVERAGE',False):
            cmd = "COVERAGE=1 %s" % cmd
        log("#", cmd)
        popen = popen2.Popen3(cmd,capturestderr=True)
        (stdin, stdout, stderr) = (
                popen.tochild, popen.fromchild, popen.childerr)
        stdin.close()
        res = self.getres(popen,stdout,stderr,quiet=blind)
        if not blind: t.rc(res,rc)
        return res
    def isconf(self,args="",rc=0,blind=False,timeout=-1):
        args = "%s/t/isconf %s" % (self._dir,args)
        self.sess(args,rc=rc,blind=blind,timeout=timeout)
    def restart(self):
        if os.fork():
            time.sleep(7)
            return
        # host.isconf("restart")
        # XXX coverage
        self.ssh("%s/t/isconf restart" % self._dir)
        sys.exit(0)
    def getres(self,popen,stdout,stderr,quiet=False):
        outputs = [stdout,stderr]
        out = ''
        err = ''
        while True:
            for f in outputs:
                try:
                    (r,w,e) = select.select([f],[],[f],.1)
                    # print r,w,e
                    for f in r:
                        rxd = f.read()
                        if len(rxd) == 0:
                            f.close()
                        if f is stdout: 
                            out += rxd
                            if not quiet: sys.stdout.write(rxd)
                        if f is stderr: 
                            err += rxd
                            if not quiet: sys.stderr.write(rxd)
                except:
                    outputs.remove(f)
            if not len(outputs):
                break
        status = popen.wait()
        rc = os.WEXITSTATUS(status)
        res = Result(rc, out, err)
        return res

class Test:
    def __init__(self):
        self._passed = 0
        self._failed = 0
    def __call__(self,res):
        self.ok(res)
    def ok(self,res):
        self.test(res.rc,0)
    def nok(self,res):
        self.test(res.rc,0,equal=False)
    def rc(self,res,rc):
        self.test(res.rc,rc)
    def passed(self):
        self._passed += 1
        # print ".",
    def failed(self,condition):
        self._failed += 1
        log("FAIL", condition)
    def results(self):
        total = self._passed + self._failed
        log("\n%d tests: %d failed, %d passed (%d%%)" % (
                total,
                self._failed, self._passed,
                (self._passed/float(total)) * 100
            )
        )
        return self._failed
    def test(self,got,want,equal=True):
        passed=False
        if str(want) == str(got): 
            if equal: passed=True
        else:
            if not equal: passed=True
        if passed:
            self.passed()
        else:
            self.failed("%s == %s" % (repr(str(got)),repr(str(want))))

t = Test()

def log(*msg):
    if isinstance(msg,list) or isinstance(msg,tuple):
        msg = ' '.join(msg)
    print msg
    print >>logfh, msg

def readblind(child):
    out = ""
    while True:
        try:
            out += child.read_nonblocking(size=8192,timeout=1)
        except:
            break
    return out

def setup(h,tdir,vdir,python):
    h.sess("export PYTHON=%s" % python)
    h.sess("rm -rf /tmp/var")
    h.sess("rm -rf " + tdir)
    h.sess("mkdir -p %s/is/conf" % vdir)
    h.sess("echo example.com > %s/is/conf/domain" % vdir)
    h.sess("echo asamplekey > %s/is/hmac_keys" % vdir)

def main():
    run(python="python2.4")
    run(python="python2.3")
    rc = t.results()
    sys.exit(rc)

def run(python='python'):
    dir = sys.argv[1]
    host = sys.argv[2:6]
    tdir = "/tmp/labtest"
    vdir = "/tmp/var"
    journal = "%s/is/fs/cache/example.com/volume/generic/journal" % vdir
    a = Host(host[0],dir)
    b = Host(host[1],dir)
    c = Host(host[2],dir)
    d = Host(host[3],dir)
    aname = str(a.hostname()).strip()
    bname = str(b.hostname()).strip()
    cname = str(c.hostname()).strip()
    dname = str(d.hostname()).strip()
    log("a.hostname", aname)
    log("b.hostname", bname)
    log("c.hostname", cname)
    log("d.hostname", dname)
    assert aname == host[0]
    assert bname == host[1]
    assert cname == host[2]
    assert dname == host[3]

    # start with clean tree
    for h in (a,b,c,d):
        h.sess("isconf stop",blind=True)
        h.isconf("stop",blind=True)
        h.sess("killall isconf",blind=True)
        setup(h,tdir,vdir,python)

    # ordinary start 
    for h in (a,b,c,d):
        h.isconf("start")
    for h in (a,b,c,d):
        h.isconf("up")

    # lock
    a.sess("mkdir -p " + tdir)
    a.put("hello\n", "%s/1" % tdir)
    out = a.cat("%s/1" % tdir)
    t.test(out,"hello\n")
    a.isconf("snap %s/1" % tdir, rc=221)
    a.isconf("snap foo",rc=2)
    a.isconf("-m 'test' lock")
    a.isconf("exec mkdir -p " + tdir)

    # snap
    a.isconf("snap %s/1" % tdir)

    # exec
    txt = """#!/bin/sh
    echo $* > %s/2.out
    """ % tdir
    a.put(txt,"%s/2" % tdir)
    a.ssh("chmod +x %s/2" % tdir)
    a.isconf("snap %s/2" % tdir)
    # a.isconf("""exec %s/2 \'hey "there" world!\'""" % tdir)
    a.isconf("exec %s/2 'hey there world!'" % tdir)
    out = a.cat("%s/2.out" % tdir)
    t.test(out,"hey there world!\n")

    # ci
    b.isconf("up")
    b.sess("test -f %s/1" % tdir, rc=1)
    b.sess("test -f %s/2.out" % tdir, rc=1)
    a.isconf("ci")
    b.isconf("up")
    out = b.cat("%s/1" % tdir)
    t.test(out,"hello\n")
    out = b.cat("%s/2.out" % tdir)
    t.test(out,"hey there world!\n")

    # lock message
    out = b.sess("grep message: %s | grep test | wc -l" % journal)
    t.test(int(str(out)),4)

    # ensure update has happened before granting lock
    c.isconf("lock update check",rc=1)
    c.isconf("up",timeout=TIMEOUT*2)
    c.isconf("lock update check again")
    c.isconf("unlock")

    # (usually) insert new tests here

    # bug #40: HMAC
    # isolate a by giving it a new key
    a.sess("echo newkey > %s/is/hmac_keys" % vdir)
    time.sleep(11)
    a.isconf("lock test HMAC a")
    b.isconf("lock test HMAC b")
    a.isconf("unlock")
    b.isconf("unlock")
    # give a the old key as a secondary
    a.sess("echo asamplekey >> %s/is/hmac_keys" % vdir)
    # give b the new key as a secondary
    b.sess("echo newkey >> %s/is/hmac_keys" % vdir)
    time.sleep(11)
    # a and b should now be able to see each other
    a.isconf("lock test HMAC a")
    b.isconf("lock test HMAC b", rc=220)
    a.isconf("unlock")
    b.isconf("lock test HMAC b")
    a.isconf("lock test HMAC a", rc=220)
    # clean up
    b.isconf("unlock")
    # give the other hosts the new key 
    c.sess("echo newkey >> %s/is/hmac_keys" % vdir)
    d.sess("echo newkey >> %s/is/hmac_keys" % vdir)
    time.sleep(11)


    # bug #60 -- IS_NOBROADCAST
    a.sess("export IS_NOBROADCAST=1")
    b.sess("export IS_NOBROADCAST=1")
    a.sess("export IS_NETS=%s/t/nets.limbo" % dir)
    b.sess("export IS_NETS=%s/t/nets.limbo" % dir)
    for h in (a,b):
        h.isconf("restart")
    # a and b can't talk to anyone
    a.isconf("lock test IS_NOBROADCAST a")
    b.isconf("lock test IS_NOBROADCAST b")
    b.isconf("unlock")
    a.put("IS_NOBROADCAST test","%s/nobroadcast" % tdir)
    a.isconf("snap %s/nobroadcast" % tdir)
    a.isconf("ci")
    b.isconf("up")
    b.cat("%s/nobroadcast" % tdir,rc=1)
    # let a and b talk to all
    a.sess("export IS_NETS=%s/t/nets" % dir)
    b.sess("export IS_NETS=%s/t/nets" % dir)
    for h in (a,b):
        h.isconf("restart")
    # XXX why isn't this rc=220?
    b.isconf("lock test IS_NOBROADCAST b",rc=1)
    b.isconf("up")
    out = b.cat("%s/nobroadcast" % tdir)
    t.test(out,"IS_NOBROADCAST test")
    # IS_NOBROADCAST on a and b doesn't keep them from hearing
    # broadcast packets from c or d
    c.isconf("up")
    out = c.cat("%s/nobroadcast" % tdir)
    t.test(out,"IS_NOBROADCAST test")

    # bug #49 -- new machines (not from same image) need to work
    # during evaluation
    b.isconf("stop")
    setup(b,tdir,vdir,python)
    b.sess("echo newkey >> %s/is/hmac_keys" % vdir)
    b.isconf("start")
    # XXX why is there a long delay here?
    time.sleep(40)
    b.isconf("up",timeout=TIMEOUT*4)
    out = b.cat("%s/2.out" % tdir)
    t.test(out,"hey there world!\n")
    # multiple checkins broken when fixing #49
    a.isconf("-m 'test multiple ci' lock")
    a.put("test multiple","%s/multiple" % tdir)
    a.isconf("snap %s/multiple" % tdir)
    a.isconf("ci")
    b.isconf("up",timeout=TIMEOUT*2)  # XXX why long timeout here?
    out = b.cat("%s/multiple" % tdir)
    t.test(out,"test multiple")
    
    # large files
    largefile="%s/largefile" % tdir
    a.sess("dd if=/dev/zero of=%s bs=1M count=500" % largefile)
    a.isconf("lock large file")
    a.isconf("snap %s" % largefile,timeout=TIMEOUT*12)
    a.isconf("ci")
    b.isconf("up",timeout=TIMEOUT*12)
    out = b.sess("wc -c %s" % largefile,timeout=TIMEOUT*4)
    t.test(out,"524288000 /tmp/labtest/largefile\n")
    def up(h): h.ssh("%s/t/isconf up" % dir)
    comps = []
    for h in c,d:
        comps.append(component([up,h]))
    for comp in comps:
        comp.wait()
    for h in c,d:
        out = h.sess("wc -c %s" % largefile,timeout=TIMEOUT*4)
        t.test(out,"524288000 /tmp/labtest/largefile\n")

    # fork 
    c.isconf("up")
    c.isconf("fork branch2")
    c.isconf("up")
    c.isconf("-m 'test fork' lock")
    c.put("test fork","%s/fork" % tdir)
    c.isconf("snap %s/fork" % tdir)
    c.isconf("ci")
    # migrate
    d.isconf("migrate branch2")
    d.isconf("up")
    out = d.cat("%s/multiple" % tdir)
    t.test(out,"test multiple")
    out = d.cat("%s/fork" % tdir)
    t.test(out,"test fork")
    a.isconf("up")
    a.sess("test -f %s/fork" % tdir, rc=1)
    b.isconf("up")
    b.sess("test -f %s/fork" % tdir, rc=1)

    # restart
    a.restart()
    b.restart()
    time.sleep(3) # XXX do we really need this?
    a.isconf("up")
    b.isconf("up")

    # bug #46: missing parent dirs
    a.sess("mkdir %s/dira" % tdir)
    a.sess("mkdir %s/dira/dirb" % tdir)
    a.put("pdir","%s/dira/dirb/foo" % tdir)
    a.isconf("-m 'test missing parent dirs' lock")
    a.isconf("snap %s/dira/dirb/foo" % tdir)
    a.isconf("ci")
    b.isconf("up")
    out = b.cat("%s/dira/dirb/foo" % tdir)
    t.test(out,"pdir")

    # bug #35: large exec output
    b.sess("tar -C /tmp -czf /tmp/isconftest.tar.gz isconftest")
    b.isconf("-m 'large exec output' lock")
    b.isconf("snap /tmp/isconftest.tar.gz")
    b.sess("cd %s/dira" % tdir)
    # expect times out here, so redirect 
    b.isconf("exec tar -xzvf /tmp/isconftest.tar.gz > /tmp/tar.out",
            timeout=TIMEOUT*2)
    b.sess("cd -")
    b.isconf("ci")
    # expect times out here, so redirect
    a.isconf("up > /tmp/tar.out")
    out = a.cat("%s/dira/isconftest/t/isconf" % tdir)

    # bug #64: long-running exec with little output
    b.isconf("lock long running")
    b.isconf("exec %s/t/bin/sleeptest 120 y" % dir, timeout=130)
    b.isconf("ci")
    a.isconf("up", timeout=130)

    # bug #64: long-running exec with no output
    b.isconf("lock long running")
    b.isconf("exec %s/t/bin/sleeptest 120" % dir, timeout=130)
    b.isconf("ci")
    a.isconf("up", timeout=130)

if __name__ == "__main__":
    main()

