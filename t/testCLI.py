
import unittest
import os
import popen2
import random
import re
import shutil
import sys
import time

from isconf.Errno import iserrno

volroot = os.environ['IS_VOLROOT'] 

class Test(unittest.TestCase):

    def isconf(self,args='',quiet=True,rc=None):
        coverage = os.environ.get('COVERAGE','')
        cmd = '%s ../bin/isconf -c simple.conf -q %s' % (coverage,args)
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
        (rc, stdin, stdout, stderr) = self.isconf(quiet=False,rc=iserrno.EINVAL)
        out = ''.join(stderr.readlines())
        ref = ''.join(open('dat/clihelp','r').readlines())
        self.assertEqual(out,ref)

    def testsnap(self):
        file = volroot + "/tmp1"
        content = str(random.random())
        open(file,'w').write(content)
        self.failUnless(os.path.exists(file))
        self.isconf('-m "testing snap" lock')
        self.isconf("snap " + file)
        os.unlink(file)
        self.failIf(os.path.exists(file))

if __name__ == '__main__':
    unittest.main()


