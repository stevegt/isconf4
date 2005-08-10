#!/usr/bin/python2.3

import unittest
import rpc822

class Test(unittest.TestCase):

    def testLoad(self):
        self.failUnless(rpc822.rpc822())

    def testAgain(self):
        self.failUnless(rpc822.rpc822())

def main():
    unittest.main()

if __name__ == '__main__':
    main()


