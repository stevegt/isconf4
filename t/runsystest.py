
# import coverage
import doctest
import os
import re
import shutil
import sys
import time
import unittest

libpath = "../lib/python"
sys.path.append(libpath)

volsrc  = "dat/volroot1"
# daemonout = "tmp/stdout"
# daemonerr = "tmp/stderr"

def main():
    # coverage.erase()
    # coverage.start()

    # prodfiles = []
    # for dir,subdirs,files in os.walk(libpath):
    #     pyfiles = filter(re.compile("^.*\.py$").search, files)
    #     prodfiles += map(lambda f: os.path.join(dir, f), pyfiles)
    # print prodfiles

    volroot = os.path.join(os.getcwd(),"tmp/volroot1")
    startd(volroot)
    result = systemTest()
    # stopd()

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

def startd(volroot):
    os.environ['IS_VOLROOT'] = volroot
    if os.path.exists(volroot):
        shutil.rmtree(volroot)
    shutil.copytree(volsrc,volroot)
    # if os.fork(): 
    #     time.sleep(3)
    #     return 0
    # XXX the server should be closing these and using syslog instead
    # sys.stdin.close()
    # sys.stdout.close()
    # sys.stderr.close()
    # sys.stdin = open("/dev/null",'r')
    # sys.stdout = open(daemonout,'w')
    # sys.stderr = open(daemonerr,'w')
    # os.setsid()
    # if os.fork(): 
    #     sys.exit(0)
    isconf('start')
    time.sleep(3)

def stopd():
    isconf('stop')

def isconf(args):
    coverage = os.environ.get('COVERAGE','')
    cmd = '%s ../bin/isconf -c simple.conf %s' % (coverage,args)
    print cmd
    os.system(cmd)

if __name__ == "__main__":
    unittest.main(defaultTest="main")

