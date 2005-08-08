TO=$(shell gpg --list-keys --with-colons | grep : | cut -d: -f5 | head -1)
FR=$(shell GNUPGHOME=client/ \
   gpg --list-keys --with-colons | grep : | cut -d: -f5 | head -1)


all: stream connect

import: serverkey clientkey
	# gpg --import < clientkey
	GNUPGHOME=client/ gpg --import < serverkey

connect: 
	sleep 3
	nc localhost 10001 < stream

stream: clientkey crypt
	echo "isdlink1" > $@
	echo >> $@
	echo "dahek" >> $@
	wc -c clientkey | awk '{print $$1}' >> $@
	cat clientkey >> $@
	echo >> $@
	echo "datem" >> $@
	wc -c crypt | awk '{print $$1}' >> $@
	cat crypt >> $@
	echo >> $@
	echo sibye >> $@

serverkey: $(GNUPGHOME)/pubring.gpg
	sleep 2
	gpg -a --export > $@
	echo >> $@

clientkey: client/pubring.gpg
	GNUPGHOME=client/ gpg -a --export $(FR) > $@
	echo >> $@

crypt: message import
	GNUPGHOME=client/ gpg --always-trust -sear $(TO) < message > crypt

message: body
	cat body > $@

XXXheaders: body
	echo type: hereis > $@
	echo -n "size: " >> $@
	wc -c body | awk '{print $$1}' >> $@
	echo >> $@

# signed: body client/secring.gpg
# 	GNUPGHOME=client/ gpg --clearsign < body > signed

clean:
	rm -f stream clientkey serverkey crypt signed message headers
