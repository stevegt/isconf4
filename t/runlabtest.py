
# import coverage
import doctest
import os
import popen2
import re
import shutil
import sys
import time
import unittest

sys.path.append("t")

class Result:
    def __init__(self,rc,stdout,stderr):
        self.rc = rc
        self.stdout = stdout.read()
        self.stderr = stderr.read()
    def __str__(self):
        return self.stdout.strip()
    def verbose(self):
        out  = "stdout: %s" % self.stdout
        out += "stderr: %s" % self.stderr
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
        status = popen.wait()
        rc = os.WEXITSTATUS(status)
        res = Result(rc, stdout, stderr)
        assert res.rc == 0
        return res
    def ssh(self,args,wantrc=0):
        cmd = "ssh root@%s %s" % (self._hostname,args)
        print "#", cmd
        popen = popen2.Popen3(cmd,capturestderr=True)
        (stdin, stdout, stderr) = (
                popen.tochild, popen.fromchild, popen.childerr)
        stdin.close()
        status = popen.wait()
        rc = os.WEXITSTATUS(status)
        res = Result(rc, stdout, stderr)
        t.rc(res,wantrc)
        return res
    def isconf(self,args):
        args = "%s/t/isconf %s" % (self._dir,args)
        self.ssh(args)

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
    def test(self,got,want,equal=True):
        if equal:
            if want == got: 
                self.passed()
            else:
                self.failed("%s == %s" % (got,want))
        else:
            if want == got: 
                self.failed("%s == %s" % (got,want))
            else:
                self.passed()

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
    a = Host(host[0],dir)
    b = Host(host[1],dir)
    # c = Host(host[2],dir)
    assert str(a.hostname()) == host[0]
    assert str(b.hostname()) == host[1]
    # assert str(c.hostname()) == host[2]

    # a.isconf("restart")
    # b.isconf("restart")
    restart(a)
    restart(b)

    a.isconf("up")
    b.isconf("up")



    t.results()



if __name__ == "__main__":
    main()

