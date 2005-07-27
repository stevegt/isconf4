from cStringIO import StringIO
from email.Generator import Generator
import email.Message
import email.Parser
import email.Utils
import hmac
import inspect
import re
import sha
import sys

class rpc822:
    """RPC via simple RFC-822 style messages.  

    Provides a faster and more binary-data-friendly mechanism than
    XML-RPC or MIME-RPC.  Method name goes in _method header, parms go
    in other headers, payload goes in message body.  Obviously, this
    only gives us one payload, but that's the price we pay for speed
    and simplicity.  If you want multipart (and slower), then see
    xmlrpclib or S. Alexander Jacobson's mimerpc python library.

    For simplicity, the only way to register methods on the server is
    in an instance.  XXX Note that the only difference between an rpc822
    client and server are whether an instance has been passed to the
    constructor; it's perfectly valid, for example, to pass an
    instance on both ends and wind up with two servers talking to each
    other.  If both servers are passed instances of the same class,
    then congratulations, you've created a peer-to-peer application.

    One difference between normal RPC and this class is in the
    response; rather than return raw data, we return a response object
    which contains, among other things, the request object, a status
    attribute, and the raw data.  The main reason we do this is to
    allow for async operation -- the response object's status will be
    EAGAIN until a response has been received.

    >>> import random
    >>> import time
    >>> class myclass:
    ...     colors = {'apple': 'red', 'berry': 'blue'}
    ...     authkeys = {}
    ...     def _auth(self,method,fromid):
    ...         # server always checks here before calling a method
    ...         if method not in self.authkeys:
    ...             # default to no permission
    ...             return False
    ...         if self.authkeys[method] is None:
    ...             # no auth required
    ...             return True
    ...         # auth required, return an HMAC key
    ...         return self.authkeys[method].get(fromid,self._mkkey())
    ...     def _mkkey(self):
    ...         # you might want more entropy than this...
    ...         random.Random("%s%f" % (repr(self),time.time())).random()
    ...     authkeys['getcolor'] = None
    ...     def getcolor(self,name):
    ...         try:
    ...             return self.colors[name]
    ...         except:
    ...             raise Exception("not food: %s" % name)
    ...     authkeys['getname'] = {'someaddr': 'somekey'}
    ...     def getname(self,color):
    ...         for (name,c) in self.colors.items():
    ...             if c == color: return name
    ...         raise Exception("color not edible: %s" % color)
    ...     authkeys['getall'] = {'someaddr': 'somekey'}
    ...     def getall(self):
    ...         return self.colors
    ... 
    >>> cli = rpc822()
    >>> svr = rpc822()
    >>> svr.register('myproto',myclass())
    >>> call = cli.call('myproto')
    >>> 
    >>> req = call.getcolor('apple')
    >>> res = svr.respond(req)
    >>> assert res.ok()
    >>> res.hmac_claimed()
    >>> res.get_payload()
    'red'
    >>> cli.parse(svr.respond(str(call.getcolor('apple')))).get_payload()
    'red'
    >>> res = svr.respond(call.getname('blue'))
    Error822: permission denied
    >>> req = call.getname('blue')
    >>> req.hmacset('somekey')
    'adf0e2ded9d4bc192dcce92cf67e435c07524cf2'
    >>> res = svr.respond(req,context='someaddr')
    >>> assert res.ok()
    >>> assert res.hmacok('somekey')
    >>> call = cli.call('myproto',authkey='somekey')
    >>> reqtxt = str(call.getname('puke green'))
    >>> res = svr.respond(reqtxt)
    Error822: permission denied
    >>> res = svr.respond(reqtxt,context='someaddr')
    Exception: color not edible: puke green
    >>> res = cli.parse(str(res))
    >>> res.method()
    'exception'
    >>> assert not res.ok()
    >>> assert not res.hmacok('foo')
    >>> assert res.hmacok('somekey')
    >>> req = call.authkeys()
    >>> res = svr.respond(req)
    AttributeError: myclass instance has no attribute 'authkeys'
    >>> req = call.getall()
    >>> res = svr.respond(req,context='someaddr')
    >>> assert res.ok()
    >>> assert res['apple'] == 'red'


    """


    def __init__(self):
        self.parser = email.Parser.Parser(Message)
        class exception_protocol: pass
        self.protocols = {'Exception': exception_protocol()}

    def call(self,protocol,**kwargs):
        return Call(protocol,**kwargs)
    
    def parse(self,txt,trial=False,maxheaderlen=65536):
        """Parse an rpc822 message.
        
        Returns the message object itself.
        
        Trial means only throw exceptions in case of known bad
        messages.  But do throw Incomplete822 if the message isn't all
        there.
        
        >>> cli = rpc822()
        >>> cli.__class__.__name__
        'rpc822'
        >>> call = cli.call('myproto')
        >>> toolong = 'x' * 65537
        >>> cli.parse(toolong)
        Traceback (most recent call last):
            (...doctest ignores traceback detail...)
        HeaderParseError: Not a header, not a continuation
        >>> cli.parse(toolong,trial=True)
        Traceback (most recent call last):
            (...doctest ignores traceback detail...)
        HeaderParseError: Not a header, not a continuation
        >>> req = call.getcolor('apple')
        >>> blankline = str(req).find('\\n\\n')
        >>> partial = str(req)[:blankline-1]
        >>> cli.parse(partial)
        Traceback (most recent call last):
            (...doctest ignores traceback detail...)
        Error822: invalid _size value
        >>> partial = str(req)[:blankline]
        >>> cli.parse(partial)
        Traceback (most recent call last):
            (...doctest ignores traceback detail...)
        Error822: invalid _size value
        >>> cli.parse(partial,trial=True)
        Traceback (most recent call last):
            (...doctest ignores traceback detail...)
        Incomplete822: 1
        >>> partial = str(req)[:blankline+1]
        >>> cli.parse(partial,trial=True)
        Traceback (most recent call last):
            (...doctest ignores traceback detail...)
        Incomplete822: 1
        >>> partial = str(req)[:blankline+2]
        >>> cli.parse(partial,trial=True)
        Traceback (most recent call last):
            (...doctest ignores traceback detail...)
        Incomplete822: 5
        >>> partial = str(req)[:blankline+4]
        >>> cli.parse(partial,trial=True)
        Traceback (most recent call last):
            (...doctest ignores traceback detail...)
        Incomplete822: 3

        """

        txt = str(txt) # in case we were passed e.g. a StringIO() instance
        msg = self.parser.parsestr(txt)
        if not msg and txt.find('\n\n') > 0:
            raise Error822("malformed headers")
        try:
            if not msg:
                raise Error822("unable to parse")
            if not msg.has_key('_method'):
                raise Error822("missing _method header")
            method = msg['_method']
            if not method:
                raise Error822("empty _method header")
            if method.startswith("_"):
                raise Error822("method names can't start with '_'")
            if '.' in method:
                raise Error822("method names can't contain '.'")
            if not msg.has_key('_size'):
                raise Error822("missing _size header")
            try:
                size = int(msg['_size'])
            except:
                raise Error822("invalid _size value")
            if size < 0: 
                raise Error822("invalid _size value")
        except Error822, e:
            if trial:
                if len(txt) > maxheaderlen:
                    raise Error822("headers too long: maxheaderlen exceeded")
                raise Incomplete822(1)
            raise Error822(e)
        payload = msg.get_payload()
        actsize = len(payload)
        if trial:
            if txt.find('\n\n') <= 0:
                raise Incomplete822(1)
            if actsize < size:
                raise Incomplete822(size - actsize)
        if actsize != size:
            # print repr(payload)
            raise Error822(
                "payload size mismatch: stated %d, actual %s" %
                (size,actsize)
                )
        return msg

    def respond(self,req,context=None,maxheaderlen=65536):
        """accepts either a Message object or a string"""
        protocol = None
        method = None
        parms = {}
        key = False
        try:
            if isinstance(req,str):
                req = self.parse(req,maxheaderlen=maxheaderlen)
            protocol = req.get('_protocol',None)
            instance = self.protocols.get(protocol,None)
            if not instance:
                raise Error822("unsupported protocol: %s" % protocol)
            method = req['_method']
            payload = req.get_payload()
            parms = req.parms()

            func = getattr(instance,method)
            if not inspect.ismethod(func):
                # hmm...  they tried to go after a class variable
                # instead of a method -- make it look like it 
                # just doesn't exist
                raise AttributeError("%s instance has no attribute '%s'" %
                    (instance.__class__.__name__,method)
                )
                
            # check permissions, get key
            if hasattr(instance,'_auth'):
                authfunc = getattr(instance,'_auth')
                key = authfunc(method,context)
                if not key:
                    raise Error822("permission denied")
                if isinstance(key,str):
                    # key required
                    if not req.hmacok(key):
                        raise Error822("bad key")

            if payload:
                respayload = func(payload,**parms)
            else:
                respayload = func(**parms)
            if isinstance(respayload,dict):
                res = self.call(protocol).response(_status='ok',**respayload)
            else:
                res = self.call(protocol).response(respayload,_status='ok')
        except Exception, e:
            if not protocol:
                protocol == 'Exception'
            name = e.__class__.__name__.split('.')[-1]
            payload = str(req)[:1024]
            res = self.call(protocol).exception(
                payload,
                type=name,
                message=str(e),
                wasmethod=method,
                _status='exception',
                comment='payload contains first 1024 bytes of failed request',
            )
            # XXX better logging
            print >>sys.stdout, "%s: %s" % (name, e)
        except:
            # XXX handle string exceptions
            # for now just drop on floor
            return None
        if isinstance(key,str):
            res.hmacset(key)
        # print res.get_unixfrom()
        return res

    def register(self,protocol,instance):
        self.protocols[protocol] = instance

class Call:

    def __init__(self,protocol,authkey=None):
        self.protocol = protocol
        self.msg = None
        self.authkey = authkey

    def __getattr__(self,method):
        if method.startswith("_"):
            raise Error822("method names can't start with '_'")
        self.msg = Message()
        self.msg.add_header('_method',method)
        return self._build

    def _build(self,_payload='',**kwargs):
        if _payload is not None:
            self.msg.set_payload(_payload)
            self.msg.add_header('_protocol',self.protocol)
            self.msg.add_header('_size',str(len(_payload)))
        for (var,val) in kwargs.items():
            # if var.startswith("_"):
            #     raise Error822("parameter names can't start with '_'")
            # XXX convert and identify non-string types
            self.msg.add_header(var,val)
        if self.authkey:
            self.msg.hmacset(self.authkey)
        return self.msg

class Message(email.Message.Message):

    def __init__(self):
        email.Message.Message.__init__(self)
        date = email.Utils.formatdate()
        self.set_unixfrom('From nobody %s' % (date))

    def data(self):
        return self.get_payload()

    def ok(self):
        return self['_status'] == 'ok'

    def parms(self):
        parms = dict(self.items())
        keys = parms.keys() # avoid "dictionary changed size" error
        for key in keys:
            if key.startswith('_'):
                del parms[key]
        return parms

    def size(self):
        return self['_size']

    def method(self):
        return self['_method']

    def hmac_calculated(self,key):
        h = hmac.new(key,msg=self.as_string(),digestmod=sha)
        digest = h.hexdigest()
        return digest

    def hmac_claimed(self):
        fromline = self.get_unixfrom()
        # print repr(self),fromline
        match = re.search("HMAC=([a-f0-9]+)",fromline)
        if not match:
            return None
        return match.group(1)

    def hmacok(self,key):
        claimed = self.hmac_claimed()
        wanted = self.hmac_calculated(key)
        return wanted == claimed

    def hmacset(self,key):
        digest = self.hmac_calculated(key)
        date = email.Utils.formatdate()
        self.set_unixfrom('From nobody (HMAC=%s) %s' % (digest,date))
        return digest

    def as_string(self, unixfrom=0):
        """Return the entire formatted message as a string.
        Optional `unixfrom' when true, means include the Unix From_ envelope
        header.

        Overridden from email.Message in order to turn off
        mangle_from_.
        """
        fp = StringIO()
        g = Generator(fp,mangle_from_=False)
        g(self, unixfrom=unixfrom)
        return fp.getvalue()

class Error822(Exception): pass
class Incomplete822(Exception): pass

