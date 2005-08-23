
import unittest
import os
import popen2
import re
import shutil
import sys
import time

from isconf.Errno import iserrno

class Test(unittest.TestCase):

    def start(self):
        volsrc  = "dat/volroot1"
        volroot = "tmp/volroot1"
        daemonout = "tmp/stdout"
        daemonerr = "tmp/stderr"
        self.volsrc  = volsrc
        self.volroot = volroot
        if os.path.exists(volroot):
            shutil.rmtree(volroot)
        shutil.copytree(volsrc,volroot)
        if os.fork(): return 0
        # XXX the server should be closing these and using syslog instead
        sys.stdin.close()
        sys.stdout.close()
        sys.stderr.close()
        sys.stdin = open("/dev/null",'r')
        sys.stdout = open(daemonout,'w')
        sys.stderr = open(daemonerr,'w')
        # os.setsid()
        if os.fork(): sys.exit(0)
        self.isconf('start',quiet=True)
        time.sleep(3)
        self.stop()

    def stop(self):
        self.isconf('stop',quiet=True)
        # system("killall isconf")

    def isconf(self,args=None,quiet=False,rc=None):
        coverage = os.environ.get('COVERAGE','')
        cmd = '%s ../bin/isconf -c simple.conf' % coverage
        if args is not None:
            if not isinstance(args,list):
                args = [args]
            for arg in args:
                cmd += " '%s'" % arg
        print cmd
        popen = popen2.Popen3(cmd,capturestderr=True)
        (stdin, stdout, stderr) = (
                popen.tochild, popen.fromchild, popen.childerr)
        status = popen.wait()
        realrc = os.WEXITSTATUS(status)
        if rc is not None:
            self.assertEquals(realrc,rc)
        if quiet:
            self.failUnless(self.quiet((realrc, stdin, stdout, stderr)))
        return (realrc, stdin, stdout, stderr)
    
    def quiet(self,res):
        (rc, stdin, stdout, stderr) = res
        out = ''
        for fh in (stdout, stderr):
            out += ''.join(stderr.readlines())
        if len(out):
            print out
            self.fail("not quiet")
        self.assertEquals(rc,0)
        return not len(out)
    
    def testHelp(self):
        (rc, stdin, stdout, stderr) = self.isconf(rc=iserrno.EINVAL)
        out = ''.join(stderr.readlines())
        ref = ''.join(open('dat/clihelp','r').readlines())
        self.assertEqual(out,ref)

    def teststartstop(self):
        self.start()
        time.sleep(3)
        self.stop()

if __name__ == '__main__':
    unittest.main()


