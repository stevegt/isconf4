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
from isconf import ISconf4, Socket
from isconf.Globals import *
from isconf.GPG import GPG
# import isconf.ISFS1
from isconf.Kernel import kernel, Buffer


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
        self.port = int(os.environ['ISCONF_PORT'])
        self.httpport = int(os.environ['ISCONF_HTTP_PORT'])
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

    def init(self):
        """parent of all server tasks"""
        # set up FBP netlist 
        unixsocks = Buffer()
        tcpsocks = Buffer()

        unix = Socket.UNIXServerFactory(path=self.ctlpath)
        kernel.spawn(unix.run(out=unixsocks))

        # tcp = Socket.TCPServerFactory(port=self.port)
        # kernel.spawn(tcp.run(out=tcpsocks))

        cli = ISconf4.CLIServerFactory(socks=unixsocks)
        kernel.spawn(cli.run())

        cachedir = "%s/cache" % os.environ['VARISCONF']
        kernel.spawn(httpServer(port=self.httpport,dir=cachedir))
        kernel.spawn(udpServer(port=self.port,dir=cachedir))

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
            print "mark", time.time()
            info(kernel.ps())
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


# XXX the following were migrated directly from 4.1.7 for now --
# really need to be FBP components, at least in terms of logging


def httpServer(port,dir):
    from BaseHTTPServer import HTTPServer
    from SimpleHTTPServer import SimpleHTTPRequestHandler
    from SocketServer import ForkingMixIn
    
    if not os.path.isdir(dir):
        os.makedirs(dir,0700)
    os.chdir(dir)

    class ForkingServer(ForkingMixIn,HTTPServer): pass

    serveraddr = ('',port)
    svr = ForkingServer(serveraddr,SimpleHTTPRequestHandler)
    svr.socket.setblocking(0)
    info("HTTP server listening on port %d" % port)
    while True:
        yield None
        try:
            request, client_address = svr.get_request()
        except socket.error:
            # includes EAGAIN
            continue
        # XXX filter request -- e.g. do we need directory listings?
        try:
            # process_request does the fork...  For now we're going to
            # say that it's okay that the Kernel and other tasks fork
            # with it; since process_request does not yield, nothing
            # else will run before the child exits.
            svr.process_request(request, client_address)
        except:
            svr.handle_error(request, client_address)
            svr.close_request(request)


def udpServer(port,dir):
    from SocketServer import UDPServer
    from isconf.fbp822 import fbp822, Error822

    if not os.path.isdir(dir):
        os.makedirs(dir,0700)
    os.chdir(dir)

    info("UDP server listening on port %d" % port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
    sock.setblocking(0)
    sock.bind(('',port))     
    while True:
        yield None
        try:
            data,addr = sock.recvfrom(8192)
            info("from %s: %s" % (addr,data))
            factory = fbp822()
            try:
                msg = factory.parse(data)
            except Error822, e:
                error("%s from %s: %s" % (e,addr,data))
                continue
            if msg.type() != 'whohas':
                error(
                    "unsupported message type from %s: %s" % (addr,msg.type())
                    )
                continue
            sock.sendto("got %s" % msg, addr)
        except socket.error:
            continue




    
