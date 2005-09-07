
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
    def __call__(self,args=''):
        return self.host.sess("%s %s" % (self.cmd,args))

class Host:
    """

    >>> a = Host("localhost")
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
    # scp /tmp/tmpVUdXmM root@localhost:/tmp/1
    >>> a("/tmp/1")
    localhost> cat /tmp/1
    'foo &!%#()'
    >>> a.sess("/bin/false").rc
    localhost> /bin/false
    FAIL '1' == '0'
    1

    """

    def __init__(self,hostname,dir=None):
        self._dir = dir
        self._hostname = hostname
        self.s = pexpect.spawn("ssh root@%s" % self._hostname)
        time.sleep(5)
        self.s.sendline("stty -echo")
        self.s.sendline("PS1=")
        self.s.expect(".")
        readblind(self.s)
        self.s.sendline("echo START")
        time.sleep(.1)
        self.s.expect("START\r\n")
        # self.s.expect(self.tag)
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
        print "#", cmd
        os.system(cmd)
        time.sleep(.1)
    def sess(self,args,rc=0,blind=False,timeout=-1):
        print "%s>" % self._hostname, args
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
        print "#", cmd
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
        print "FAIL", condition
    def results(self):
        total = self._passed + self._failed
        print "\n%d tests: %d failed, %d passed (%d%%)" % (
                total,
                self._failed, self._passed,
                (self._passed/float(total)) * 100
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

def readblind(child):
    out = ""
    while True:
        try:
            out += child.read_nonblocking(size=8192,timeout=1)
        except:
            break
    return out

def main():
    dir = sys.argv[1]
    host = sys.argv[2:6]
    tdir = "/tmp/labtest"
    vdir = "/tmp/var"
    journal = "%s/isfs/cache/example.com/volume/generic/journal" % vdir
    a = Host(host[0],dir)
    b = Host(host[1],dir)
    c = Host(host[2],dir)
    d = Host(host[3],dir)
    aname = str(a.hostname()).strip()
    bname = str(b.hostname()).strip()
    cname = str(c.hostname()).strip()
    dname = str(d.hostname()).strip()
    print "a.hostname", aname
    print "b.hostname", bname
    print "c.hostname", cname
    print "d.hostname", dname
    assert aname == host[0]
    assert bname == host[1]
    assert cname == host[2]
    assert dname == host[3]

    # start with clean tree
    for h in (a,b,c,d):
        h.isconf("stop",blind=True)
        h.sess("rm -rf /tmp/var")
        h.sess("rm -rf " + tdir)

    # ordinary start 
    for h in (a,b,c,d):
        h.isconf("start")
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

    # bug #49 -- new machines (not from same image) need to work
    # during evaluation
    b.isconf("stop")
    b.sess("rm -rf /tmp/var")
    b.sess("rm -rf " + tdir)
    b.isconf("start")
    time.sleep(7)
    b.isconf("up",timeout=90)
    out = b.cat("%s/2.out" % tdir)
    t.test(out,"hey there world!\n")
    # multiple checkins broken when fixing #49
    a.isconf("-m 'test multiple ci' lock")
    a.put("test multiple","%s/multiple" % tdir)
    a.isconf("snap %s/multiple" % tdir)
    a.isconf("ci")
    b.isconf("up",timeout=60)  # XXX why long timeout here?
    out = b.cat("%s/multiple" % tdir)
    t.test(out,"test multiple")
    
    # fork 
    c.isconf("up",timeout=60)
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
    a.isconf("up")
    b.isconf("up")

    rc = t.results()
    sys.exit(rc)



if __name__ == "__main__":
    main()

