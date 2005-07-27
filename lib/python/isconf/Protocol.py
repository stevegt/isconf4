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
import isconf
from isconf.Globals import *
from isconf.Kernel import kernel

class Protocol:
    """
    XXX this is good, migrate more into here

    Rather than thinking in terms of protocol stacks, this design uses
    protocol pipelines; both inbound and outbound messages traverse
    through a protocol controller (a child of this class) via the same
    code path.  

    Pipelines are built dynamically by process(), when it specifies
    the msg.nextcls attribute.  Each class is responsible for routing 

    Call tree for both inbound and outbound messages:

        prev.dispatch(msg,prev)
            cls.rx(rxd,prev)
                rxmsg = cls.parse(rxd)
                rxmsg.prev = prev
                self = cls.getctl(rxmsg)
                    if rxmsg.refid:
                        return cls.route(rxmsg.refid)
                    return cls()
                newmsgs = self.process(rxmsg)
                    mkmsg(replyto=rxmsg)
                for msg in newmsgs:
                    self.dispatch(msg)
                        msg.next.rx(msg.payload,self)

    Generating outbound messages:

        prev.whatever()
            cls.tx(txd,prev)
                
    XXX try that again... inbound:
                
        prev.dispatch(msg,prev)
            cls.rx(rxd,prev)
                rxmsg = cls.parse(rxd)
                rxmsg.prev = prev
                self = cls.getctl(rxmsg)
                newmsgs = self.process(rxmsg)
                    self.mkmsg(replyto=rxmsg)
                for msg in newmsgs:
                    self.dispatch(msg)
                        nextcls.rx(msg.payload,self)


    XXX let's try it with a real example:

        isconf._update(path)
            fs = ISFS1(basedir)
            file = fs.open(path=worklist)
                who = fs.whohas(path=worklist)
                    msg = fs.mkmsg(op='whohas',path=worklist)
                    mesh = ISdmesh1(content='ISFS1')
                    mesh.mcast(payload=str(msg))
                        mmsg = mesh.mkmsg(mode='mcast',payload=payload)
                        for link in mesh.peers():
                            mesh.tx(mmsg,link)
                                link.write(str(mmsg))
                    reply = mesh.read()
                        mesh.waitfor(XXX)


        replies = link.dispatch(msg)
        XXX sync or async?
            ISdmesh1.rx(rxd=msg.payload)
                rxmsg = ISdmesh1.parse(rxd)
                rxmsg.prev = prev
                self = cls.getctl(rxmsg)
                newmsgs = self.process(rxmsg)
                    self.mkmsg(replyto=rxmsg)
                for msg in newmsgs:
                    self.dispatch(msg)
                        nextcls.rx(msg.payload,self)


    XXX once again, with tasks and news:



        

        isconf._update(path)
            fs = ISFS1(basedir)
            fh = fs.open(path=worklist)
                who = fs.whohas(path=worklist)
                    msg = fs.mkmsg(op='whohas',path=worklist,tell=123)
                    rdr = kernel.newsreader(123,fs)
                    kernel.newspost('mcast',msg)
                    yield kernel.siguntil, kernel.newsck(123,fs)
                    msg = rdr.next()

                        mesh.mcast(payload=str(msg))
                            mmsg = mesh.mkmsg(mode='mcast',payload=payload)
                            for link in mesh.peers():
                                mesh.tx(mmsg,link)
                                    link.write(str(mmsg))
                        reply = mesh.read()
                            mesh.waitfor(XXX)



                    

                

        
    """

    routes = {}
    Message =  email.Message.Message

    def __init__(self,transport):
        self.transport = transport
        self.parser = email.Parser.HeaderParser(self.Message)
        self.time = time.time()

    def dispatch(self,protocol,payload):
        """
        primarily a hook point for unit testing right now
        XXX kill off overrides in ISdlink etc.

        """
        self.protocol=protocol
        self.protocol(transport=self).rx(payload)
        # XXX catch exceptions

    def reaper(self,key,*args,**kwargs):
        """Delete old routes.

        >>> p = Protocol(transport=None)
        >>> assert p.route('a',p)
        >>> assert kernel.ps()
        >>> kernel.run(steps=100)
        >>> assert kernel.ps().index('timedout')
        

        """
        yield kernel.siguntil, self.timedout
        self.route(key,None)

    def route(cls,key=None,obj=False):
        """

        >>> class proto(Protocol):
        ...     pass
        ... 
        >>> proto.routes = {} # doctest bug?
        >>> p = proto(transport=None)
        >>> p.route('a')
        >>> assert p.route('a',p)
        >>> assert p.route('a')
        >>> assert proto.route('a')
        >>> assert p.route('a',None)
        >>> p.route('a')
        >>> proto.route('a')
        
        
        """
        hit = cls.routes.has_key(key)
        if obj:
            # add/replace
            cls.routes[key] = obj
            if hasattr(obj,'reaper'):
                # retire old routes
                kernel.spawn(obj.reaper(key))
            return cls.routes[key]
        if hit and obj is None:
            # delete
            obj = cls.routes[key]
            del cls.routes[key]
            return obj
        if hit:
            # get
            return cls.routes[key]
        if key is None:
            # get all
            return cls.routes
        return None

    route = classmethod(route)
    
    def timedout(self,timeout=60):
        # timeout in N seconds
        return time.time() - self.time > timeout

    def _tx(self,msg):
        txd = str(msg)
        self.transport.write(txd)

    def write(self,payload,replyto=None):
        """
        called by higher-level protocol
        replyto is one of our own messages
        """
        msg = _mkmsg(payload=payload,replyto=replyto)
        self._tx(msg)

