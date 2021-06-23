# pi-display
Simple Raspberry Pi-based e-Ink display for solar power system statusa

This project is for my own entertainment, but I make it public in case someone else finds something useful they can make use of.  I require no attribution, but if you do find my code useful I like to hear about it.  And if you find bugs, I like to hear about that too!

My setup looks something like this:

1. I have a Victron 100/20 MPPT solar charge controller, which is fed currently by a single 165W Furrion panel that came standard on my RV.
2. The battery being charged is a single Battle Born 100 Ah lithium iron phosphate battery.
3. Between the battery and the rest of the DC system is a Victron SmartShunt.
4. I created a faux Venus GX equivalent using a Raspberry Pi 3B (see also: https://github.com/victronenergy/venus/wiki/raspberrypi-install-venus-image) which connects to the solar charge controller and smart shunt using USB/VE.Direct cables.
5. Since that machine is Venus OS and can be updated online from Victron, it runs no general purpose software.  Instead, I have a second Raspberry Pi 3B that runs Grafana to visualize the data collected by the 'Venus GX'.  (see also: https://github.com/victronenergy/venus-docker-grafana)
6. The two RPis communicate using WiFi, with the general-purpose machine being located in the common area of the RV.
7. The general-purpose RPi has a Waveshare 2.7 inch e-Paper HAT, which is what this python code updates using data pulled out of InfluxDB.
