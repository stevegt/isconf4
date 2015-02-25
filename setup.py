#!/usr/bin/env python

from distutils.core import setup
# import sys

ver=open("version").read().strip()
rev=open("revision").read().strip()
version="%s.%s" % (ver,rev)

setup(name="isconf",
        version=version,
        description="Infrastructure configuration management tool",
        author="Steve Traugott",
        author_email="stevegt@t7a.org",
		url="https://github.com/stevegt/isconf4",
        package_dir = {'': 'lib/python'},
        packages=['isconf'],
        scripts=['bin/isconf'],
		classifiers=[
				'Development Status :: 5 - Production/Stable',
				'Environment :: Console',
				'Environment :: No Input/Output (Daemon)',
				'Intended Audience :: Developers',
				'Intended Audience :: Information Technology',
				'Intended Audience :: System Administrators',
				'License :: OSI Approved :: GNU General Public License v2 (GPLv2)',
				'Operating System :: POSIX',
				'Operating System :: POSIX :: Linux',
				'Programming Language :: Python',
				'Programming Language :: Python :: 2.7',
				'Topic :: Software Development :: Build Tools',
				'Topic :: Software Development :: Quality Assurance',
				'Topic :: Software Development :: Testing',
				'Topic :: Software Development :: Version Control',
				'Topic :: System :: Clustering',
				'Topic :: System :: Distributed Computing',
				'Topic :: System :: Installation/Setup',
				'Topic :: System :: Recovery Tools',
				'Topic :: System :: Software Distribution',
				'Topic :: System :: Systems Administration',
				'Topic :: Utilities',
			],
    )

