
import unittest
import os
import re
import time

class Test(unittest.TestCase):

    def setUp(self):
        coverage = os.environ.get('COVERAGE','')
        self.cmd = '%s ../bin/isconf -c simple.conf' % coverage
    
    def testHelp(self):
        cmd = self.cmd 
        print "running", cmd
        (stdin, stdout, stderr) = os.popen3(cmd,'r')
        out = ''.join(stderr.readlines())
        ref = ''.join(open('dat/clihelp','r').readlines())
        self.assertEqual(out,ref)

    def teststartstop(self):
        cmd = self.cmd + " start"
        print "running", cmd
        (stdin, stdout, stderr) = os.popen3(cmd,'r')
        time.sleep(3)
        cmd = self.cmd + " stop"
        print "running", cmd
        (stdin, stdout, stderr) = os.popen3(cmd,'r')
        out = ''.join(stderr.readlines())
        ref = ''.join(open('dat/stop','r').readlines())
        self.assertEqual(out,ref)

if __name__ == '__main__':
    unittest.main()


