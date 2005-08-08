PREFIX=/var/isconf
tmpdir=/tmp/isconf-make.tmp
version=$(shell cat version)

all:

install:
	# XXX this is all wrong -- use setup.py
	mkdir -p $(PREFIX)
	find . | cpio -pudvm $(PREFIX)/
	ln -fs $(PREFIX)/bin/isconf /usr/bin/isconf
	ln -fs $(PREFIX)/etc/rc.isconf /etc/init.d/isconf
	# XXX not portable
	ln -fs /etc/init.d/isconf /etc/rc2.d/S19isconf

start:
	/etc/init.d/isconf stop
	sleep 1
	/etc/init.d/isconf start
	sleep 5

ctags:
	# requires Exuberant ctags 
	# ctags --language-force=python bin/isconf
	cd bin; ctags --language-force=python isconf

tar:
	rm -rf $(tmpdir)
	mkdir -p $(tmpdir)
	cp -a . $(tmpdir)/isconf-$(version)
	cd $(tmpdir); tar --exclude=cache -czvf /tmp/isconf-$(version).tar.gz .
	rm -rf $(tmpdir)

mtatest:
	- killall isconf
	- bin/isconf -v selftest -p
	sleep 5
	# GNUPGHOME=/tmp/`ls -rt /tmp | tail -1`/foo/.gnupg; cd mta; make
	# export GNUPGHOME=`ls -rtd /tmp/[0-9]*/A/.gnupg | tail -1`; \
	export GNUPGHOME=/tmp/isconf-test/A/var/isconf/.gnupg; $(MAKE) -C mta all


