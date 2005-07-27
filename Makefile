PREFIX=/var/isconf
tmpdir=/tmp/isconf-make.tmp
version=$(shell cat version)
patchlevel:=$(shell cat patchlevel)
var=$(PREFIX)/$(version)

all:

isconf.man:
	txt2tags isconf.t2t

install:
	PREFIX=$(PREFIX) ./bin/upgrade $(version) $(patchlevel)

XXXinstall:
	[ ! -f /usr/bin/isconf ]
	mkdir -p $(var)
	cp -a . $(var)/
	ln -fs $(var)/bin/isconf /usr/bin/isconf
	ln -fs $(var)/etc/rc.isconf /etc/init.d/isconf
	ln -fs /etc/init.d/isconf /etc/rc2.d/S19isconf
	mkdir -p $(var)/cache
	touch -t 198001010101 /var/isconf/cache/worklist 

XXXupgrade:
	./bin/upgrade

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
	cp -a . $(tmpdir)/isconf-$(version).$(patchlevel)
	cd $(tmpdir); tar --exclude=cache -czvf /tmp/isconf-$(version).$(patchlevel).tar.gz .
	rm -rf $(tmpdir)
	echo $$(( $(patchlevel) + 1 )) > patchlevel

test: tar
	tests/install $(version) $(patchlevel)
	tests/upgrade $(version) $(patchlevel)

mtatest:
	- killall isconf
	- bin/isconf -v selftest -p
	sleep 5
	# GNUPGHOME=/tmp/`ls -rt /tmp | tail -1`/foo/.gnupg; cd mta; make
	# export GNUPGHOME=`ls -rtd /tmp/[0-9]*/A/.gnupg | tail -1`; \
	export GNUPGHOME=/tmp/isconf-test/A/var/isconf/.gnupg; $(MAKE) -C mta all

