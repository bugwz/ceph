#!/usr/bin/env bash

set -e

mydir=$(dirname $0)

wget http://download.ceph.com/qa/ffsb.tar.bz2
tar jxvf ffsb.tar.bz2
cd ffsb-6.0-rc2
patch -p1 <$mydir/ffsb.patch
./configure
make
cd ..
mkdir tmp
cd tmp

for f in $mydir/*.ffsb; do
	../ffsb-*/ffsb $f
done
cd ..
rm -r tmp ffsb*
