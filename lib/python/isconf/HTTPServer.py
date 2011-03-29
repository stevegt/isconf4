"""Simple HTTP Server.

This module builds on BaseHTTPServer by implementing the standard GET
and HEAD requests in a fairly straightforward manner.

"""

__version__ = "0.0"

__all__ = ["SimpleHTTPRequestHandler"]

import email.Utils
import os
import posixpath
import BaseHTTPServer
import urllib
import cgi
import re
import shutil
import sys
import mimetypes
from StringIO import StringIO
import SimpleHTTPServer 

from isconf.Cache import HMAC
from isconf.Globals import getmtime_int


class SimpleHTTPRequestHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):

    """Simple HTTP request handler with GET and HEAD commands.

    This serves files from the current directory and any of its
    subdirectories.  It assumes that all files are plain text files
    unless they have the extension ".html" in which case it assumes
    they are HTML files.

    The GET and HEAD requests are identical except that the HEAD
    request omits the actual contents of the file.

    """

    server_version = "ISconfHTTP/" + __version__

    def send_head(self):
        """Common code for GET and HEAD commands.

        This sends the response code and MIME headers.

        Return value is either a file object (which has to be copied
        to the outputfile by the caller unless the command was HEAD,
        and must be closed by the caller under all circumstances), or
        None, in which case the caller has nothing further to do.

        """
        path = self.translate_path(self.path)
        # get args
        m = re.match('(.*)\?(.*)',path)
        args = {}
        if m:
            path = m.group(1)
            arglist = re.findall('(.*?)=([^=&]*)&*',m.group(2))
            for (var,val) in arglist:
                args[var]=val
        # sys.argv[0] = "[serving %s]" % path
        # get HMAC challenge
        challenge = args.get('challenge',None)
        f = None
        if os.path.isdir(path):
            for index in "index.html", "index.htm":
                index = os.path.join(path, index)
                if os.path.exists(index):
                    path = index
                    break
            else:
                return self.list_directory(path)
        ctype = self.guess_type(path)
        if ctype.startswith('text/'):
            mode = 'r'
        else:
            mode = 'rb'
        try:
            f = open(path, mode)
        except IOError:
            self.send_error(404, "File not found")
            return None
        mtime = getmtime_int(path)
        size = os.path.getsize(path)
        lastmod = email.Utils.formatdate(mtime)
        self.send_response(200)
        self.send_header("Content-type", ctype)
        self.send_header("Last-Modified", lastmod)
        self.send_header("Content-Length", size)
        if challenge:
            hmacResponse = HMAC.response(challenge)
            self.send_header("X-HMAC", hmacResponse)
        self.end_headers()
        return f

def test(HandlerClass = SimpleHTTPRequestHandler,
                 ServerClass = BaseHTTPServer.HTTPServer):
        BaseHTTPServer.test(HandlerClass, ServerClass)

if __name__ == '__main__':
    test()
