
import unittest
import os
import re

class Test(unittest.TestCase):

    def testHelp(self):
        (stdin, stdout, stderr) = os.popen3('../bin/isconf -c simple.conf','r')
        out = ''.join(stderr.readlines())
        ref = ''.join(open('dat/clihelp','r').readlines())
        self.assertEqual(out,ref)

if __name__ == '__main__':
    unittest.main()


