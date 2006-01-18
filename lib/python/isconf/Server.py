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
from isconf import ISconf, ISFS, Socket, Cache
from isconf.Globals import *
from isconf.GPG import GPG
from isconf.Kernel import kernel, Bus


class Server:

    def __init__(self):
        self.ishome = os.environ['IS_HOME']
        self.port = int(os.environ['IS_PORT'])
        self.httpport = int(os.environ['IS_HTTP_PORT'])
        self.confdir = "%s/conf" % self.ishome
        self.ctlpath = "%s/conf/.ctl" % self.ishome
        self.pidpath = "%s/conf/.pid" % self.ishome

    def start(self):
        """be a server forever"""
        if not os.path.isdir(self.confdir):
            os.makedirs(self.confdir,0700)
        open(self.pidpath,'w').write("%d\n" % os.getpid())
        # XXX bug #20: not enough entropy
        # self.gpgsetup()
        kernel.run(self.init())
        return 0

    def stop(self):
        """stop a running server"""
        # XXX should we instead ask it politely first?
        try:
            pid = int(open(self.pidpath,'r').read().strip())
            os.kill(pid,signal.SIGINT)
            time.sleep(1)
            try:
                os.kill(pid,signal.SIGKILL)
            except:
                pass
        except IOError, e:
            if e.errno == 2:
                info("no pid file found")
                return 1
        except OSError, e:
            if e.errno == 3:
                info("already stopped")
                return 0
            raise
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
                # if msg.type() == 'debug' and not hasattr(os.environ,'DEBUG'):
                #     continue
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

        cache = Cache.Cache(udpport=self.port,httpport=self.httpport)
        # XXX attach to CLIServerFactory
        kernel.spawn(cache.run())

        cli = ISconf.CLIServerFactory(socks=unixsocks)
        kernel.spawn(cli.run())

        # XXX Cache and CLIServerFactory need dirs passed to them as
        # well, rather than them digging it out of env and redundantly
        # defining paths
        # XXX should probably do all directory creation here as well
        cachedir = os.path.join(self.ishome,"fs/cache")
        kernel.spawn(Cache.httpServer(port=self.httpport,dir=cachedir))

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
            debug("mark: HZ =", kernel.HZ)
            # import pprint
            # pprint.pprint(kernel.ps())
            yield kernel.sigsleep, 10
            # XXX check all buffers for unbounded growth

    def gpgsetup(self):
        gnupghome = "%s/.gnupg" % self.ishome
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


