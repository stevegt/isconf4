# vim:set expandtab:
# vim:set foldmethod=indent:
# vim:set shiftwidth=4:
# vim:set tabstop=4:

from __future__ import generators
import errno
import os
import re
import select
import signal
import sys
import time

import isconf
from isconf.Globals import *
from isconf.GPG import GPG
import isconf.ISFS1
from isconf.Kernel import kernel, Buffer
from isconf.Socket import UNIXServerFactory, TCPServerFactory


class EchoTest:

    def __init__(self,transport):
        self.transport=transport

    def run(self,*args,**kwargs):
        kernel.info("starting EchoTest.run")
        rxd = ''
        while True:
            yield None
            # rxd = self.transport.read(1)
            # self.transport.write(rxd)
            rxd += self.transport.read(1)
            if '\n' in rxd: 
                self.transport.write(rxd)
                rxd = ''
        return 

class Server:

    def __init__(self):
        self.varisconf = os.environ['VARISCONF']
        self.port = int(os.environ['ISCONF_PORT'])
        self.ctlpath = "%s/.ctl" % self.varisconf
        self.pidpath = "%s/.pid" % self.varisconf

    def start(self):
        """be a server forever"""
        if not os.path.isdir(self.varisconf):
            os.makedirs(self.varisconf,0700)
        open(self.pidpath,'w').write("%d\n" % os.getpid())
        self.gpgsetup()
        kernel.run(self.init())
        return 0

    def stop(self):
        """stop a running server"""
        # XXX should we instead ask it politely first?
        pid = int(open(self.pidpath,'r').read().strip())
        os.kill(pid,signal.SIGKILL)
        return 0

    def init(self):
        """parent of all tasks"""
        # set up FBP netlist 
        clin = Buffer()
        clout = Buffer()
        tofs = Buffer()
        frfs = Buffer()
        toca = Buffer()
        frca = Buffer()

        # XXX start cliserver, netserver

        # kernel.spawn(UXmgr(frsock=clin,tosock=clout))
        # kernel.spawn(ISconf(cmd=clin,res=clout,fsreq=tofs,fsres=frfs))
        # kernel.spawn(ISFS(cmd=tofs,res=frfs,careq=toca,cares=frca))
        # cache = Cache(cmd=toca,res=frca,
        #         bcast=bcast,ucast=ucast,frnet=frnet
        #     )
        # kernel.spawn(cache)
        # kernel.spawn(UDPmgr(cmd=toca,res=frca,tonet=tonet,frnet=frnet))

        unix = UNIXServerFactory(path=self.ctlpath)
        yield kernel.sigspawn, unix.run()
        tcp = TCPServerFactory(port=self.port)
        yield kernel.sigspawn, tcp.run()
        while True:
            # periodic housekeeping
            print "mark", time.time()
            kernel.info(kernel.ps())
            yield kernel.sigsleep, 10

    def gpgsetup(self):
        gnupghome = "%s/.gnupg" % self.varisconf
        gpg = GPG(gnupghome=gnupghome)
        if not gpg.list_keys(secret=True):
            host = os.environ['HOSTNAME']
            genkeyinput = """
                Key-Type: RSA
                Key-Length: 1024
                Name-Real: ISdlink Server on %s
                Name-Comment: Created by %s
                Name-Email: isdlink@%s
                Expire-Date: 0
                %%commit
            \n""" % (host, sys.argv[0], host)
            gpg.gen_key(genkeyinput)
