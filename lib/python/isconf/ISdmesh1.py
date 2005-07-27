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
from isconf.Protocol import Protocol
from isconf.Kernel import kernel

class ISdmesh1Message(email.Message.Message):
    """
    a mesh message

    >>> msg = ISdmesh1Message()
    >>> msg['foo'] = 'bar'
    >>> msg.set_payload('hello\\n')
    >>> str(msg)
    'foo: bar\\n\\nhello\\n'
    >>> msg['foo']
    'bar'
    >>> msg['asfdsad']
    >>> id = msg['id']
    >>> assert id == msg['id']
    >>> assert '@' in msg['id']
    >>> msg['id'] = 'apple'
    >>> assert '@' in str(msg.get_all('id'))
    >>> assert str(msg.get_all('id')).index('apple')
    >>> del msg['id']
    >>> msg['id'] = 'apple'
    >>> msg['id']
    'apple'
    

    >>> msg = ISdmesh1Message()
    >>> msg.returnpath
    []
    >>> str(msg.returnpath)
    ''
    >>> msg['returnpath']
    ''
    >>> msg['returnpath'] = 'x,y,z'
    >>> str(msg.returnpath)
    'x,\\n\\ty,\\n\\tz'
    >>> msg['returnpath']
    'x,\\n\\ty,\\n\\tz'
    >>> msg['topath'] = 'a,b,c,d,c,f,g'
    >>> msg['topath']
    'a,\\n\\tb,\\n\\tc,\\n\\td,\\n\\tc,\\n\\tf,\\n\\tg'
    >>> msg.returnpath.extend('me')
    >>> msg['returnpath']
    'me,\\n\\tx,\\n\\ty,\\n\\tz'
    >>> msg.topath.shortcut('c')
    >>> msg['topath']
    'f,\\n\\tg'
    >>> str(msg)
    'topath: f,\\n\\tg\\nreturnpath: me,\\n\\tx,\\n\\ty,\\n\\tz\\n\\n'
    >>> str(msg)
    'topath: f,\\n\\tg\\nreturnpath: me,\\n\\tx,\\n\\ty,\\n\\tz\\n\\n'
    
    
    """

    def __init__(self):
        email.Message.Message.__init__(self)
        self.func = mkdict(returnpath=self._path,topath=self._path)

    def _getpayload(self): return self.get_payload()
    def _setpayload(self,val): self.set_payload(val)
    payload = property(_getpayload,_setpayload) 

    def _path(self,op,var,val=None):
        if op == 'getattr':
            # no attr -- text is authoritative
            if self.superget(var):
                # get from text
                val = self.superget(var)
                # store in attr
                self.__dict__[var] = MeshPath(str=val)
            else:
                # init
                self.__dict__[var] = MeshPath()
            return self.__dict__[var]
        if op == 'getitem':
            # attr is authoritative
            if self.__dict__.has_key(var):
                # have attr
                val = str(self.__dict__[var])
                # store in text
                self.superdel(var)
                self.superset(var,val)
                return val
            else:
                # missing attr -- punt
                return self.superget(var)
        if op == 'setitem':
            # attr is authoritative -- set it first
            self.__dict__[var] = MeshPath(str=val)
            # then set text
            self.superdel(var)
            self.superset(var,val)
            return self.superget(var)
        assert False

    def __getattr__(self,var):
        if var in self.func: 
            return self.func[var]('getattr',var)
        return getattr(email.Message.Message,var)

    def __getitem__(self,var):
        if var in self.func: 
            return self.func[var]('getitem',var)
        if not self.superget(var):
            self['id'] = "%20.10f@%s" % (time.time(), socket.gethostname())
        return self.superget(var)
        
    def __setitem__(self,var,val):
        if var in self.func: 
            return self.func[var]('setitem',var,val)
        return self.superset(var,val)

    def __str__(self):
        for var in self.func:
            # touch these just to exercise __getitem__
            self[var]
        return self.as_string()

    def superdel(self,var):
        return ISdmesh1Message.__delitem__(self,var)

    def superget(self,var):
        return ISdmesh1Message.get(self,var)

    def superset(self,var,val):
        return ISdmesh1Message.add_header(self,var,val)

    def transit(self,node):
        """

        >>> msg = ISdmesh1Message()
        >>> msg['returnpath'] = 'x,y,z'
        >>> msg['topath'] = 'a,b,c,d,c,f,g'
        >>> msg.transit('c')
        >>> str(msg)
        'topath: f,\\n\\tg\\nreturnpath: c,\\n\\tx,\\n\\ty,\\n\\tz\\n\\n'
        

        """
        self.returnpath.extend(node)
        self.topath.shortcut(node)

class ISdmesh1(Protocol):
    """
    protocol controller -- one instance per message 

    """
    
    Message = ISdmesh1Message
    
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
        >>> def proto():
        ...     while True:
        ...         yield kernel.sigalias, 'isfs1'
        ... 
        >>> t = transport()
        >>> mesh = isconf.ISdmesh1.ISdmesh1(transport=t)
        >>> isconf.ISdmesh1.dispatch = dispatch
        >>> mesh.rx("id: 123\\ncontent: isfs1\\n\\nhello\\n")
        Traceback (most recent call last):
          File "<stdin>", line 1, in ?
          File "lib/python/isconf/ISdmesh1.py", line 227, in rx
            raise "unhandled content: %s" % content
        unhandled content: isfs1
        >>> 
        >>> p = kernel.spawn(proto())
        >>> kernel.run(steps=10)
        >>> mesh.rx("id: 124\\ncontent: isfs1\\n\\nhello\\n")
        >>> mesh.rx("id: 124\\n\\nhello\\n")
        closing
        
        
        """
        msg = self.parser.parsestr(rxd)
        id = msg['id']
        if self.route(id):
            # it's a duplicate -- drop it on the floor and drop
            # connection to peer
            kernel.info("dropping dup %s" % id)
            self.transport.close()
            return
        self.route(id,self)
        content = msg.get('content',None)
        if not content:
            raise "missing content header: %s" % id
        if not kernel.event(content,msg.payload):
            raise "unhandled content: %s" % content

    def _mkmsg(cls,msg=None,payload=None,replyto=None):
        """
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
            msg = Message()

        if payload:
            msg.set_payload(payload)
        if not msg.get_payload():
            msg.set_payload('content: noop\n\nnoop\n')
        
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

        # XXX

        for fingerprint in dst:
            transport = routes[fingerprint]
            controller = cls(transport=transport)
            controller.tx(msg)
        return True

    # XXX send = classmethod(send)

class MeshPath(list):
    """
    a from or to path

    >>> path = MeshPath(str="a, b, c, d, e, c, f, g")
    >>> path
    ['a', 'b', 'c', 'd', 'e', 'c', 'f', 'g']
    >>> str(path)
    'a,\\n\\tb,\\n\\tc,\\n\\td,\\n\\te,\\n\\tc,\\n\\tf,\\n\\tg'
    >>> path.extend('me')
    >>> path
    ['me', 'a', 'b', 'c', 'd', 'e', 'c', 'f', 'g']
    >>> path.shortcut('b',keep=True)
    >>> path
    ['b', 'c', 'd', 'e', 'c', 'f', 'g']
    >>> path.shortcut('c')
    >>> path
    ['f', 'g']
    >>> path = MeshPath()
    >>> path
    []
    >>> str(path)
    ''
    
    
    """

    def __init__(self,str=None,delim=",",*args):
        if str: args = self._str2list(str,delim)
        list.__init__(self,args)

    def _str2list(self,str,delim):
        lst = str.split(delim)
        lst = [s.strip() for s in lst]
        return lst

    def __str__(self,delim=',\n\t'):
        return delim.join(self)

    def extend(self,node):
        self.insert(0,node)

    def shortcut(self,node,keep=False):
        scratch = self[:]
        scratch.reverse()
        dlen = len(scratch) - scratch.index(node)
        if keep: dlen -= 1
        dlen = max(dlen,0)
        del self[0:dlen]
        
