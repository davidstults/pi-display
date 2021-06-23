#!/usr/bin/env bash

set -e

cd ~
wget http://www.airspayce.com/mikem/bcm2835/bcm2835-1.69.tar.gz
tar zxvf bcm2835-1.69.tar.gz 
cd bcm2835-1.69/
sudo ./configure
sudo make
sudo make check
sudo make install
sudo apt-get update
sudo apt-get install -y wiringpi python3-pip python3-pil python3-numpy
sudo pip3 install --upgrade pip
sudo pip3 install RPi.GPIO spidev
