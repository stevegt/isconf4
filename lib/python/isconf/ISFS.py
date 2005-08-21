# vim:set expandtab:
# vim:set foldmethod=indent:
# vim:set shiftwidth=4:
# vim:set tabstop=4:

from __future__ import generators
import ConfigParser
import copy
import email.Message
import email.Parser
import errno
import inspect
import md5
import os
import popen2
import random
import re
import select
import sha
import shutil
import socket
import sys
import time
from isconf.Globals import *

class Client:
    """The ISFS client library.

    For use by application code (e.g. the ISconf server).  Makes no
    assumptions about how the application code is structured or
    scheduled (asyncore, isconf.Kernel, etc.), but does use generators
    for read and write to the server, to effectively make all I/O
    non-blocking.

    Talks to ISFS server using messages formatted by the Message
    class.  Uses UNIX domain socket in order to allow privilege
    separation between ISconf and ISFS.  These messages 
    make their way to the Server class via isconf.Server.ServerSocket.

    """
    pass


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
    debug("HTTP server serving %s on port %d" % (dir,port))
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


def udpServer(udpport,httpport,dir):
    from SocketServer import UDPServer
    from isconf.fbp822 import fbp822, Error822

    if not os.path.isdir(dir):
        os.makedirs(dir,0700)
    os.chdir(dir)

    debug("UDP server serving %s on port %d" % (dir,udpport))
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
    sock.setblocking(0)
    sock.bind(('',udpport))     
    # laddr = sock.getsockname()
    # localip = os.environ['HOSTNAME']
    while True:
        yield None
        try:
            data,addr = sock.recvfrom(8192)
            debug("from %s: %s" % (addr,data))
            factory = fbp822()
            msg = factory.parse(data)
            type = msg.type()
            if type == 'whohas':
                fname = msg['file']
                tell = msg['tell']
                newer = int(msg.get('newer',None))
                # security checks
                ok=True
                if fname != os.path.normpath(fname): 
                    ok=False
                if dir != os.path.commonprefix((dir,os.path.abspath(fname))):
                    ok=False
                if not ok:
                    error("unsafe request from %s: %s" % (addr,fname))
                    continue
                if not os.path.isfile(fname):
                    debug("from %s: not found: %s" % (addr,fname))
                    continue
                if newer is not None and newer > os.path.getmtime(fname):
                    debug("from %s: not newer: %s" % (addr,fname))
                    continue
                # url = "http://%s:%d/%s" % (localip,httpport,fname)
                reply = factory.mkmsg('ihave',
                        file=fname,port=httpport,scheme='http')
                sock.sendto(str(reply),0,addr)
                continue
            # cache flood listener 
            if type == 'ihave':
                fname = msg['file']
                kernel.spawn(updateFile(fname))
            error("unsupported message type from %s: %s" % (addr,type))
        except socket.error:
            continue
        except Exception, e:
            error("%s from %s: %s" % (e,addr,data))
            continue


def updateFile(fname):
    pass

    
