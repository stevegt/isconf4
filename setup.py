#!/usr/bin/env python

from distutils.core import setup

setup(name="ISconf",
        version="4.2.6",
        description="Infrastructure configuration management tool",
        author="Steve Traugott",
        author_email="stevegt@infrastructures.org",
        url="http://www.isconf.org",
        package_dir = {'': 'lib/python'},
        packages=['isconf'],
        scripts=['bin/isconf'],
    )

