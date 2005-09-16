#!/usr/bin/env python

from distutils.core import setup
import sys

ver=open("version").read().strip()
rev=open("revision").read().strip()
version="%s.%s" % (ver,rev)

setup(name="isconf",
        version=version,
        description="Infrastructure configuration management tool",
        author="Steve Traugott",
        author_email="stevegt@infrastructures.org",
        url="http://www.isconf.org",
        package_dir = {'': 'lib/python'},
        packages=['isconf'],
        scripts=['bin/isconf'],
    )

