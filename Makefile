PREFIX=/var/isconf
tmpdir=/tmp/isconf-make.tmp
version=`cat version`
revision=`cat revision`
tarname=isconf-$(version).$(revision)
tarball=/tmp/$(tarname).tar.gz

all:

XXXinstall:
	# XXX this is all wrong -- need a setup.py
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
	./update-revision
	rm -rf $(tmpdir)
	mkdir -p $(tmpdir)/$(tarname)
	cp -a . $(tmpdir)/$(tarname)
	tar -C $(tmpdir) --exclude=*.pyc --exclude=*.swp --exclude=*.swo --exclude=.coverage -czvf $(tarball) $(tarname)
	rm -rf $(tmpdir)

ship: tar
	scp $(tarball) root@trac.t7a.org:/var/trac/isconf/pub

test:
	cd t && time make

systest:
	cd t && time make runsystest.py

umlsync:
	rsync -PHaSvuz --exclude=*.pyc . root@isconf10:/tmp/isconftest
	rsync -PHaSvuz --exclude=*.pyc . root@isconf11:/tmp/isconftest
	rsync -PHaSvuz --exclude=*.pyc . root@isconf12:/tmp/isconftest
	rsync -PHaSvuz --exclude=*.pyc . root@isconf13:/tmp/isconftest

umltest: umlsync
	cd t && time python2.2 runlabtest.py /tmp/isconftest \
		isconf10 isconf11 isconf12 isconf13

labsync:
	rsync -PHaSvuz --exclude=*.pyc . root@test1:/tmp/isconftest
	rsync -PHaSvuz --exclude=*.pyc . root@test2:/tmp/isconftest
	rsync -PHaSvuz --exclude=*.pyc . root@test3:/tmp/isconftest
	rsync -PHaSvuz --exclude=*.pyc . root@test4:/tmp/isconftest

labtest: labsync
	cd t && time python2.2 runlabtest.py /tmp/isconftest \
		test1 test2 test3 test4

tarsync:
	t/tarsync $(tarname) test1 test2 test3

tartest: tarsync
	time python2.2 t/runlabtest.py /tmp/$(tarname) \
		test1 test2 test3

mtatest:
	- killall isconf
	- bin/isconf -v selftest -p
	sleep 5
	# GNUPGHOME=/tmp/`ls -rt /tmp | tail -1`/foo/.gnupg; cd mta; make
	# export GNUPGHOME=`ls -rtd /tmp/[0-9]*/A/.gnupg | tail -1`; \
	export GNUPGHOME=/tmp/isconf-test/A/var/isconf/.gnupg; $(MAKE) -C mta all

