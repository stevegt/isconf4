
import unittest
import rpc822

class Test(unittest.TestCase):

    def testLoad(self):
        self.failUnless(rpc822.rpc822())

    def testAgain(self):
        self.failUnless(rpc822.rpc822())

if __name__ == '__main__':
    unittest.main()


