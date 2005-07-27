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
import isconf.Protocol
from isconf.Globals import *
from isconf.ISdmesh1 import ISdmesh1

proto = 'isfs1'

class Message(email.Message.Message):
    """An ISFS message.

    Messages might be signed, authenticated with HMAC, or clear.

    Signed messages are used for login, HMAC messages are used for
    open, read, write, and close.  Cleartext messages are used for
    data blocks.

    """
    pass


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

    XXX assume we're in a kernel task and just use events directly for
    now

    """
    pass

class ISFS1:
    """An ISFS server.  
    
    Listens on the 'isfs1' event alias for messages formatted by the
    Message class.  These messages could come from the local machine
    (via the Client class) or from a remote machine (via
    isconf.ISdmesh1).

    Client talks to ISFS server using rpc822.  These messages make
    their way to the server via isconf.Server.ServerSocket, which
    posts them to the 'isfs1' event alias.

    Server listens on the 'isfs1' event alias for messages.  These
    messages could come from the local machine (via the Client class)
    or from a remote machine (via isconf.ISdmesh1).

    Server will hear messages coming in from the UNIX domain socket
    via isconf.Server.ServerSocket.  This allows for privilege
    separation between independent ISconf and ISFS daemons.

    XXX skip UNIX socket for now, just assume client is in a kernel
    task and use events directly


    ... kernel.spawn(ISFS1().server())
    ... fs = ISFS1()
    ... fs.login(



    """
#     switch = mkdict(
#         login = _login,
#         open = _open,
#         read = _read,
#         write = _write,
#         close = _close,
#         whohas = _whohas,
#         ihave = _ihave,
#         sendme = _sendme,
#         hereis = _hereis,
#     )

    def server(self):
        """Listen for and dispatch isfs1 messages."""
        # XXX move to Protocol
        yield kernel.sigalias, proto
        while True:
            event = Event()
            yield kernel.sigwait, event
            rxd = event.data
            replyto = event.replyto
            msg = Message.parse(rxd)
            op = msg['op']
            if op in switch:
                switch[op](msg,replyto=replyto)

    def login(self,gnupghome,passphrase):
        pass


    def _login(self,msg,replyto):
        if not msg.sigok():
            kernel.event(replyto, self.error("login failed"))


class Junk(isconf.Protocol.Protocol):

    # def _ihave_tx(self,replyto):
    #     self.transport.

    def _whohas_rx(self,msg):
        path = msg['path']
        # XXX security checks
        # cd varisconf
        if os.exists(path) and not isdir(path):
            self._ihave_tx(msg)
    #       XXX


            

        
    
    def process(self,msg):
        func = mkdict(
            whohas  = self._whohas_rx,
            ihave   = self._ihave_rx,
            sendme  = self._sendme_rx,
            hereis  = self._hereis_rx
        )
        op = msg['op']
        if not op in func:
            raise "invalid op: " + op
        func[op](msg)
        

    def rx(self,rxd):
        """
        receive a message from the underlying layer

        >>> class transport:
        ...     def close(self):
        ...         print "closing"
        ... 
        >>> def dispatch(self,proto,payload):
        ...     print proto
        ...     print repr(payload)
        ... 
        >>> t = transport()
        >>> mesh = ISFS1(transport=t)
        >>> ISFS1.dispatch = dispatch
        >>> mesh.rx("path: /a/b\\n\\nhello\\n")
        isconf.ISconf4
        'hello\\n'
        
        
        """
        msg = self.parser.parsestr(rxd)
        path = msg['path']
        self.route(path,self)
        self.process(msg)
        # XXX get protocol from a callbacks table showing which apps
        # are interested in which paths
        protocol=ISconf4
        self.dispatch(protocol,msg.get_payload())

    def send(cls,msg=None,payload=None,replyto=None):
        """
        send a message given to us by higher layer
        
        msg is a new or forwarded message -- we'll create one if not
        given, using payload

        replyto is a message obj we're replying to -- otherwise
        forward or multicast

        payload will replace any existing payload in msg

        >>> class gpg:
        ...     def fingerprints(self,secret):
        ...         return ['me','a','b']
        ... 
        >>> class xport(Protocol):
        ...     def write(self,txd):
        ...         print repr(txd)
        ... 
        >>> g = kernel.shmget('gpg',gpg())
        >>> 
        >>> ISdlink1.route('a', xport(1)) and None
        >>> ISdlink1.route('b', xport(2)) and None
        >>> ISdlink1.route('c', xport(3)) and None
        >>> mesh = ISdmesh1(None)
        >>> msg = ISdmesh1Message()
        >>> msg['mode'] = 'ucast'
        >>> msg['returnpath'] = 'q,w,e,r,t,y'
        >>> msg['topath'] = 'z,x,me,v,b,i,m,n'
        >>> str(msg)
        'mode: ucast\\ntopath: z,\\n\\tx,\\n\\tme,\\n\\tv,\\n\\tb,\\n\\ti,\\n\\tm,\\n\\tn\\nreturnpath: q,\\n\\tw,\\n\\te,\\n\\tr,\\n\\tt,\\n\\ty\\n\\n'
        >>> assert mesh.send(msg=msg,payload='hello')
        'mode: ucast\\ntopath: b,\\n\\ti,\\n\\tm,\\n\\tn\\nreturnpath: me,\\n\\tq,\\n\\tw,\\n\\te,\\n\\tr,\\n\\tt,\\n\\ty\\n\\nhello'
        
        
        """
        if not msg:
            msg = ISdmesh1Message()

        if payload:
            msg.set_payload(payload)
        if not msg.get_payload():
             msg.set_payload('noop')
        
        # add ourselves to from
        gpg = kernel.shmget('gpg')
        fingerprints = gpg.fingerprints(secret=True)
        # ours should always be the first fingerprint on secring
        myprint = fingerprints[0]
        # alter return and to paths to show we've touched message
        msg.transit(myprint)

        # get all routes for all layers (returns a dict)
        routes = cls.route()

        if replyto:
            # unicast reply
            msg.topath = replyto.returnpath[:]

        # set of fingerprints we're going to send to
        dst = {}
        # set of fingerprints who are our direct peers
        peerprints = filter(routes.has_key, fingerprints)
        if myprint in peerprints: peerprints.remove(myprint)

        if msg['mode'] == 'ucast':
            # unicast reply or forward
            revpath = msg.topath[:]
            revpath.reverse()
            if not revpath:
                return -3
            # work backwards from end of 'to' path, looking for who to send
            # to next
            for fingerprint in revpath:
                if fingerprint == myprint:
                    # oops -- found ourselves before finding a peer
                    # XXX log
                    return -1
                if fingerprint in peerprints:
                    dst[fingerprint] = True
                    msg.topath.shortcut(fingerprint,keep=True)
                    break
        else:
            # multicast
            # send to all peer transports
            for fingerprint in peerprints:
                dst[fingerprint] = True

        if not dst:
            # XXX log
            return -2

        for fingerprint in dst:
            transport = routes[fingerprint]
            controller = cls(transport=transport)
            controller.tx(msg)
        return True

    send = classmethod(send)

