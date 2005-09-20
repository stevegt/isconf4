
from __future__ import generators
import os
import re
import select
import shutil
import socket
import sys
import time
import isconf
import isconf.ISdlink1
import isconf.ISFS1
import isconf.ISconf4
import isconf.rpc822stream
import rpc822
from isconf.Globals import *


class Test:

    def __init__(self):
        # create tmp space
        # self.tmp="/tmp/%s" % os.getpid()
        self.tmp="/tmp/isconf-test"
        if not os.path.isdir(self.tmp):
            os.makedirs(self.tmp,0700)
        self.specs = {
            'A':            {'port': 10001, 'pid': None},
            'B':            {'port': 10002, 'pid': None},
            'C':            {'port': 10003, 'pid': None},
            }
    
    def ckmatch(self,regex,txt):
        if not re.match(regex,txt):
            print >>sys.stderr, "ckmatch: " + regex + " != " + txt
            raise "ckmatch failed"

    def ckrecv(self,regex,sock,maxlen=None,search=False):
        if not maxlen: maxlen = len(regex)
        rxd = ''
        while True:
            newrxd = sock.recv(1)
            if not newrxd: 
                raise "ckrecv: short read: %s" % rxd
            rxd += newrxd
            if search:
                m = re.search(regex,rxd)
            else:
                m = re.match(regex,rxd)
            if m:
                return True
            if len(rxd) > maxlen:
                raise "ckrecv: %s != %s" % (regex,rxd)

    def doctest(self):
        import doctest, coverage
        # (f,t) = doctest.testmod(eval('isconf.Kernel'))
        # doctest.master.summarize()
        # sys.exit(f)

        modules = []
        olddir = os.getcwd()
        os.chdir('lib/python')
        os.path.walk('.',getmods,modules)
        os.chdir(olddir)
        print modules
        
        # modules=[rpc822]

        fail=0
        total=0
        coverage.erase()
        coverage.start()
        for mod in modules:
            (f,t) = doctest.testmod(mod,report=0)
            fail += f
            total += t
        doctest.master.summarize()
        coverage.stop()
        for mod in modules:
            coverage.analysis(mod)
        coverage.report(modules)
        sys.exit(fail)

    def mkserver(self,servername):
        if self.specs[servername]['pid']:
            return
        rootdir="%s/%s" % (self.tmp,servername)
        port = self.specs[servername]['port']
        flags = ''
        if verbose: flags += ' -v '
        os.system("%s %s -r %s server -p %d" % 
            (sys.argv[0], flags, rootdir, port)
        )
        time.sleep(5)
        pid = int(open("%s/%s/var/is/conf/.pid" % (self.tmp,servername),'r').readline())
        self.specs[servername]['pid'] = pid

    def selftest(self,**kwargs):

        # test protocol startup
        self.mkserver('A')

        if kwargs['persistent']:
            return

        self.testProtocolStart('A');

        # create a nodelist
        
        # fork more servers
        for servername in self.specs.keys():
            self.mkserver(servername)

        # be a client ourselves; send some messages and check connectivity
        # self.mkclient('A')

        # kill a server

        # check again

        # kill all clients and servers
        print "killing test daemons..."
        for name in self.specs.keys():
            self.kill(name)

        if kwargs['dirty']:
            return

        # clean up tmp
        print "cleaning up..."
        shutil.rmtree(self.tmp)

    def kill(self,name):
        pid = self.specs[name]['pid']
        print "killing %d" % pid
        if pid:
            try:
                os.kill(pid,9)
            except:
                pass


    def testProtocolStart(self,name):
        port = self.specs[name]['port']
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)     
        sock.connect(("localhost", port))
        sock.send('a' * 200)
        rxd = sock.recv(1024)
        self.ckmatch("subab ", rxd)
        print "PASS subab\n"
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)     
        sock.connect(("localhost", port))
        sock.send("lksajf\n")
        rxd = sock.recv(1024)
        self.ckmatch("supun ", rxd)
        print "PASS supun\n"

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)     
        sock.connect(("localhost", port))
        sock.send('echotest\n')
        sleep=0
        for i in range(1000):
            txd = str(i) + "\n"
            sock.send(txd)
            rxd = ''
            while '\n' not in rxd:
                rxd += sock.recv(1)
            # print rxd,
            assert txd == rxd
        print "PASS echotest\n"
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)     
        sock.connect(("localhost", port))
        sock.send('isdlink1\n')
        self.ckrecv("isdlink1\nsisek ",sock)
        self.ckrecv("\n",sock,maxlen=40,search=True)
        key = """-----BEGIN PGP PUBLIC KEY BLOCK-----
        Version: GnuPG v1.2.1 (GNU/Linux)

        mIsEQqfpUAEEANKWuPsujjxMu6GbGsFB+uww65e9JQb2fOVNeHr1QRNnhW2yj6bG
        1smZchQFrnUaMMwbmp23GyNsump/INaKS3Rp8yoBiKc/N/vBo/o0Q1o1nOFmnMzR
        LIgAwzDOuZg5z1MBiVaTzWxj6Ki3yDy6hSbOg+zlh8SDTPaUYyuXro5pAAYptDtJ
        U0ZTIFNlcnZlciBvbiBzcGlyaXQgKENyZWF0ZWQgYnkgYmluL2lzY29uZikgPGlz
        ZnNAc3Bpcml0PoivBBMBAgAZBQJCp+lQBAsHAwIDFQIDAxYCAQIeAQIXgAAKCRCD
        OLpumsbZwfTEBACTzSUTZv+dpRyOPJmMlS/rN/XkNByq5qOk9q3IAa9VsRSYBrer
        Dzr2tCQTisMPEQWwBcst3t6hGdzcND5so8c5KV5eeV3siON6nYtVXNeT3a0XnVKF
        ntzV199pOyvaqxPt/vDqU1fA9Uak4Pu2pJRseI/cf97UZiR0cHp9ikHjmg==
        =HYLm
        -----END PGP PUBLIC KEY BLOCK-----
        """
        sock.send("dahek\n%d\n%s\n" % (len(key),key))
        self.ckrecv("dahek ", sock)
        print "PASS dahek\n"

def getmods(modules,dirname,names):
    dirname = dirname.replace("./","")
    dirname = dirname.lstrip(".")
    dirpath = dirname.split('/')
    if not dirpath[0]: dirpath.pop(0)
    for name in names:
        path = dirpath[:]
        if re.match("__",name): 
            continue
        m = re.match("(.*)\.py$",name)
        if not m:
            continue
        name = m.group(1)
        path.append(name)
        pathname = '.'.join(path)
        print pathname
        mod = eval(pathname)
        modules.append(mod)

