
import unittest
import os
import re

class Test(unittest.TestCase):

    def testHelp(self):
        coverage = os.environ.get('COVERAGE','')
        (stdin, stdout, stderr) = os.popen3(
                '%s ../bin/isconf -c simple.conf' % coverage,'r')
        out = ''.join(stderr.readlines())
        ref = ''.join(open('dat/clihelp','r').readlines())
        self.assertEqual(out,ref)

if __name__ == '__main__':
    unittest.main()


