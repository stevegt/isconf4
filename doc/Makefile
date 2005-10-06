VERSION=$(shell cat ../version).$(shell cat ../revision)

all: isconf.8 isconf.html

isconf.t2t: isconf.t2t.in ../revision
	perl -pne "s/__VERSION__/$(VERSION)/" isconf.t2t.in > $@

isconf.8: isconf.t2t
	txt2tags -o $@ -t man isconf.t2t 

isconf.html: isconf.t2t
	txt2tags -o $@ --toc -t html $?

