#!/bin/bash

while true
do
perl -e 'alarm shift @ARGV; exec @ARGV' 86400 ss-server -k $2 -m aes-256-cfb -p $1 -s 0
done
