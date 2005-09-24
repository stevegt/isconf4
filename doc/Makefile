
all: isconf.8 isconf.html

isconf.8: isconf.t2t
	txt2tags isconf.t2t 
	mv isconf.man isconf.8

isconf.html: isconf.t2t
	txt2tags -o $@ --toc -t html $?

