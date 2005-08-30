
# import coverage
import doctest
import os
import popen2
import re
import select
import shutil
import sys
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
    ...     def ssh(self,args):
    ...         print "ssh foo", args
    ... 
    >>> c = Cmd("echo",host())
    >>> c("hi")
    ssh foo echo hi
    >>> c = Cmd("echo hello",host())
    >>> c()
    ssh foo echo hello

    """
    
    def __init__(self,cmd,host):
        self.cmd = cmd
        self.host = host
    def __call__(self,args=''):
        return self.host.ssh("%s %s" % (self.cmd,args))

class Host:
    """

    >>> a = Host("localhost")
    >>> print a.ssh("echo hi")
    # ssh localhost echo hi
    hi
    >>> a.ssh("ps > /tmp/1").rc
    # ssh localhost ps > /tmp/1
    0
    >>> a.date().rc
    # ssh localhost date 
    0
    >>> print a.echo("hi")
    # ssh localhost echo hi
    hi
    >>> print a.echo("hi > /tmp/1")
    # ssh localhost echo hi > /tmp/1
    >>> a("/tmp/1")
    # ssh localhost cat /tmp/1
    'hi\\n'
    >>> print a.ssh("'echo hi there > /tmp/1'")
    # ssh localhost 'echo hi there > /tmp/1'
    >>> a("/tmp/1")
    # ssh localhost cat /tmp/1
    'hi there\\n'
    >>> print a.put('foo &!%#()',"/tmp/1")
    # ssh localhost 'cat > /tmp/1'
    >>> a("/tmp/1")
    # ssh localhost cat /tmp/1
    'foo &!%#()'

    """

    def __init__(self,hostname,dir=None):
        self._dir = dir
        self._hostname = hostname
    def __call__(self,args):
        res = self.cat(args)
        if not res.rc == 0:
            raise CatError(path)
        return res.stdout
    def __getattr__(self,cmd):
        return Cmd(cmd,self)
    def put(self,data,file):
        args = "'cat > %s'" % file
        cmd = "ssh root@%s %s" % (self._hostname,args)
        print "#", cmd
        popen = popen2.Popen3(cmd,capturestderr=True)
        (stdin, stdout, stderr) = (
                popen.tochild, popen.fromchild, popen.childerr)
        stdin.write(data)
        stdin.close()
        res = self.getres(popen,stdout,stderr)
        assert res.rc == 0
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
    def isconf(self,args="",rc=0,blind=False):
        args = "%s/t/isconf %s" % (self._dir,args)
        self.ssh(args,rc=rc,blind=blind)
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

def restart(host):
    if os.fork():
        time.sleep(7)
        return
    host.isconf("restart")
    sys.exit(0)

def main():
    dir = sys.argv[1]
    host = sys.argv[2:5]
    tdir = "/tmp/labtest"
    vdir = "/tmp/var"
    journal = "%s/isfs/cache/example.com/volume/generic/journal" % vdir
    a = Host(host[0],dir)
    b = Host(host[1],dir)
    # c = Host(host[2],dir)
    assert str(a.hostname()).strip() == host[0]
    assert str(b.hostname()).strip() == host[1]
    # assert str(c.hostname()) == host[2]


    # start with clean tree
    a.isconf("stop",blind=True)
    b.isconf("stop",blind=True)
    a.ssh("rm -rf /tmp/var")
    b.ssh("rm -rf /tmp/var")
    a.ssh("rm -rf " + tdir)
    b.ssh("rm -rf " + tdir)
    a.ssh("mkdir -p " + tdir)
    b.ssh("mkdir -p " + tdir)

    # ordinary start 
    a.isconf("start")
    b.isconf("start")
    a.isconf("up")
    b.isconf("up")

    # restart
    restart(a)
    restart(b)
    a.isconf("up")
    b.isconf("up")

    # lock
    a.put("hello\n", "%s/1" % tdir)
    out = a.cat("%s/1" % tdir)
    t.test(out,"hello\n")
    a.isconf("snap %s/1" % tdir, rc=221)
    a.isconf("snap foo",rc=2)
    a.isconf("-m 'test' lock")

    # snap
    a.isconf("snap %s/1" % tdir)

    # exec
    txt = """#!/bin/sh
    echo $* > %s/2.out
    """ % tdir
    a.put(txt,"%s/2" % tdir)
    a.ssh("exec chmod +x %s/2" % tdir)
    a.isconf("snap %s/2" % tdir)
    # a.isconf("""exec %s/2 \'hey "there" world!\'""" % tdir)
    a.isconf("exec %s/2 'hey there world!'" % tdir)
    out = a.cat("%s/2.out" % tdir)
    t.test(out,"hey there world!\n")

    # ci
    b.isconf("up")
    b.ssh("test -f %s/1" % tdir, rc=1)
    b.ssh("test -f %s/2.out" % tdir, rc=1)
    a.isconf("ci")
    b.isconf("up")
    out = b.cat("%s/1" % tdir)
    t.test(out,"hello\n")
    out = b.cat("%s/2.out" % tdir)
    t.test(out,"hey there world!\n")

    # lock message
    out = b.ssh("grep message: %s | grep test | wc -l" % journal)
    t.test(out,"3\n")

    
    


    
    


    rc = t.results()
    sys.exit(rc)



if __name__ == "__main__":
    main()

