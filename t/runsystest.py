
# import coverage
import doctest
import os
import re
import sys
import unittest

libpath = "../lib/python"
sys.path.append(libpath)

def main():
    # coverage.erase()
    # coverage.start()

    # prodfiles = []
    # for dir,subdirs,files in os.walk(libpath):
    #     pyfiles = filter(re.compile("^.*\.py$").search, files)
    #     prodfiles += map(lambda f: os.path.join(dir, f), pyfiles)
    # print prodfiles

    result = systemTest()

    # coverage.stop()
    # for f in prodfiles:
    #     coverage.analysis(f)
    # coverage.report(prodfiles)

    return result

def systemTest():
    filenameToModuleName = lambda f: os.path.splitext(f)[0]
    load = unittest.defaultTestLoader.loadTestsFromModule  

    testfiles = os.listdir(os.curdir)                               
    # test = re.compile("^test.*\.py$", re.IGNORECASE)          
    test = re.compile("^test.*\.py$")
    testfiles = filter(test.search, testfiles)                     
    # print testfiles
    testNames = map(filenameToModuleName, testfiles)         
    testNames.sort()
    # print testNames
    tests = map(__import__, testNames)                 
    # print tests

    result = unittest.TestSuite(map(load, tests))          

    return result

if __name__ == "__main__":
    unittest.main(defaultTest="main")

