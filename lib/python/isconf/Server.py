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
import socket
import sys
import time

import isconf
from isconf import ISconf, ISFS, Socket
from isconf.Globals import *
from isconf.GPG import GPG
from isconf.Kernel import kernel, Bus


class EchoTest:

    def __init__(self,transport):
        self.transport=transport

    def run(self,*args,**kwargs):
        info("starting EchoTest.run")
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
        self.port = int(os.environ['ISFS_PORT'])
        self.httpport = int(os.environ['ISFS_HTTP_PORT'])
        self.ctlpath = "%s/.ctl" % self.varisconf
        self.pidpath = "%s/.pid" % self.varisconf

    def start(self):
        """be a server forever"""
        if not os.path.isdir(self.varisconf):
            os.makedirs(self.varisconf,0700)
        open(self.pidpath,'w').write("%d\n" % os.getpid())
        # XXX bug #20: not enough entropy
        # self.gpgsetup()
        kernel.run(self.init())
        return 0

    def stop(self):
        """stop a running server"""
        # XXX should we instead ask it politely first?
        pid = int(open(self.pidpath,'r').read().strip())
        os.kill(pid,signal.SIGKILL)
        return 0

    def logger(self,bus):
        # XXX syslog
        log = open("/tmp/isconf.log",'w')
        while True:
            mlist=[]
            yield bus.rx(mlist)
            for msg in mlist:
                if msg in (kernel.eagain,None):
                    continue
                if msg is kernel.eof:
                    log.close()
                    return
                log.write("%f %s: %s\n" % (time.time(), msg.type(),msg.data()))
                log.flush()
            

    def init(self):
        """parent of all server tasks"""
        # set up FBP netlist 
        BUS.log = Bus()
        unixsocks = Bus()
        tcpsocks = Bus()

        # spawn BUS.log -> syslog sender
        kernel.spawn(self.logger(bus=BUS.log))

        unix = Socket.UNIXServerFactory(path=self.ctlpath)
        kernel.spawn(unix.run(out=unixsocks))

        # tcp = Socket.TCPServerFactory(port=self.port)
        # kernel.spawn(tcp.run(out=tcpsocks))

        cachedir = os.environ['ISFS_CACHE']

        mesh = ISFS.UDPmesh(
                udpport=self.port,httpport=self.httpport,dir=cachedir)
        # XXX attach to CLIServerFactory
        kernel.spawn(mesh.run())

        cli = ISconf.CLIServerFactory(socks=unixsocks)
        kernel.spawn(cli.run())

        kernel.spawn(ISFS.httpServer(port=self.httpport,dir=cachedir))

        # kernel.spawn(UXmgr(frsock=clin,tosock=clout))
        # kernel.spawn(ISconf(cmd=clin,res=clout,fsreq=tofs,fsres=frfs))
        # kernel.spawn(ISFS(cmd=tofs,res=frfs,careq=toca,cares=frca))
        # cache = Cache(cmd=toca,res=frca,
        #         bcast=bcast,ucast=ucast,frnet=frnet
        #     )
        # kernel.spawn(cache)
        # kernel.spawn(UDPmgr(cmd=toca,res=frca,tonet=tonet,frnet=frnet))

        while True:
            yield None
            # periodic housekeeping
            debug("mark")
            # debug(kernel.ps())
            yield kernel.sigsleep, 10
            # XXX check all buffers for unbounded growth

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


