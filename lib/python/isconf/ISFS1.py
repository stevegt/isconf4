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



