
from __future__ import generators
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

class fbp822:
    """Flow-based messages via simple RFC-822-like format.  

    Provides a faster and more binary-data-friendly mechanism than
    BoulderIO, XML, or MIME.  Message type goes in _type header,
    string parms go in other headers, binary payload goes in message
    body.  Obviously, this only gives us one payload, but that's the
    price we pay for speed and simplicity.  If you want multipart (and
    slower), then nest multiple fbp822 messages in the same payload,
    or (even slower) use XML or MIME.

    Optionally does HMAC -- see the following examples.

    For more information on how fbp822 can be used, Google for "flow
    based programming" and "data flow programming".

    >>> factory = fbp822()
    >>> msg = factory.mkmsg('apple')
    >>> 
    >>> msg.hmac_claimed()
    >>> msg.get_payload()
    ''
    >>> factory.parse(str(msg)).get_payload()
    ''
    >>> msg.hmacset('somekey')
    '5528934b82b37f57600eb8b2fb37cc9d591033a1'
    >>> assert msg.hmacok('somekey')
    >>> factory = fbp822(authkey='somekey')
    >>> msg = factory.mkmsg('puke green',apple='red')
    >>> assert not msg.hmacok('foo')
    >>> assert msg.hmacok('somekey')
    >>> assert msg['apple'] == 'red'

    """


    def __init__(self,authkey=None):
        self.parser = email.Parser.Parser(Message)
        self.authkey = authkey

    def mkmsg(self,type,_payload='',**kwargs):
        msg = Message()
        msg.add_header('_type',type)
        if _payload is not None:
            msg.set_payload(_payload)
        msg.add_header('_size',str(len(_payload)))
        for (var,val) in kwargs.items():
            if var.startswith("_"):
                raise Error822("parameter names can't start with '_'")
            # XXX convert and identify non-string types
            msg.add_header(var,val)
        if self.authkey:
            msg.hmacset(self.authkey)
        return msg

    def parse(self,txt,trial=False,maxheaderlen=65536):
        """Parse an fbp822 message.
        
        Returns the message object itself.
        
        This parser is intended to be used to test messages for
        completeness: 'trial', if True, means throw Incomplete822 if
        the message isn't all there, otherwise only throw exceptions
        in case of messages which are complete but bad.  
        
        >>> factory = fbp822()
        >>> msg = factory.mkmsg('apple','abc\\n123\\nxyz\\n',color='red')
        >>> factory.__class__.__name__
        'fbp822'
        >>> toolong = 'x' * 65537
        >>> factory.parse(toolong)
        Traceback (most recent call last):
            (...doctest ignores traceback detail...)
        Error822: unable to parse
        >>> factory.parse(toolong,trial=True)
        Traceback (most recent call last):
            (...doctest ignores traceback detail...)
        Error822: headers too long: maxheaderlen exceeded
        >>> blankline = str(msg).find('\\n\\n')
        >>> partial = str(msg)[:blankline-1]
        >>> factory.parse(partial)
        Traceback (most recent call last):
            (...doctest ignores traceback detail...)
        Error822: payload size mismatch: stated 12, actual 0
        >>> factory.parse(partial,trial=True)
        Traceback (most recent call last):
            (...doctest ignores traceback detail...)
        Incomplete822: 1
        >>> partial = str(msg)[:blankline+1]
        >>> factory.parse(partial,trial=True)
        Traceback (most recent call last):
            (...doctest ignores traceback detail...)
        Incomplete822: 1
        >>> partial = str(msg)[:blankline+2]
        >>> factory.parse(partial,trial=True)
        Traceback (most recent call last):
            (...doctest ignores traceback detail...)
        Incomplete822: 12
        >>> partial = str(msg)[:blankline+4]
        >>> factory.parse(partial,trial=True)
        Traceback (most recent call last):
            (...doctest ignores traceback detail...)
        Incomplete822: 10
        >>> partial = str(msg)[:blankline+14]
        >>> factory.parse(partial,trial=True).get_payload()
        'abc\\n123\\nxyz\\n'

        """

        txt = str(txt) # in case we were passed e.g. a StringIO() instance
        msg = self.parser.parsestr(txt)
        if not msg and txt.find('\n\n') > 0:
            raise Error822("malformed headers")
        try:
            if not msg:
                raise Error822("unable to parse")
            if not msg.has_key('_type'):
                raise Error822("missing _type header")
            type = msg['_type']
            if not type:
                raise Error822("empty _type header")
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

    def fromStream(self,stream):
        """generates message objects from a file or isconf.Socket"""
        rxd = ''
        wanted = 1
        # read one message each time through complete loop
        factory = fbp822()
        while True:
            yield kernel.eagain
            if hasattr(stream,'state') and stream.state == 'down':
                break
            newrxd = stream.read(wanted)
            if isinstance(stream,file) and not len(newrxd):
                # at EOF
                break
            rxd += newrxd
            # discard leading newlines
            if rxd == '\n':
                rxd = ''
                continue
            # try to parse a message
            try:
                msg = factory.parse(rxd,trial=True)
            except Incomplete822, e:
                # nope, didn't get it all
                wanted = e
                continue
            # yay. got it all
            yield msg
            rxd = ''
            wanted = 1
        if rxd:
            # hmm.  junk at end of stream.  this is probably going to
            # blow up, but let's try anyway...
            msg = factory.parse(rxd)
            yield msg



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

    def type(self):
        return self['_type']

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

