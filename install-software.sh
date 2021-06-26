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
sudo apt update
sudo apt install -y wiringpi python3-pip python3-numpy python3-venv libopenjp2-7 libtiff5
python3 -m venv ~/py
source ~/py/bin/activate
pip3 install --upgrade pip
sudo perl -pi -e s/^#dtparam=spi=on/dtparam=spi=on/ /boot/config.txt
echo reboot now
