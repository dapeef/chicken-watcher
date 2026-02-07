import signal

from gpiozero import DigitalInputDevice

def beam_broken_2():
    print("Beam broken on GPIO2!")

sensor2 = DigitalInputDevice(2, pull_up=True)
sensor2.when_activated = beam_broken_2

def beam_broken_3():
    print("Beam broken on GPIO3!")

sensor3 = DigitalInputDevice(3, pull_up=True)
sensor3.when_activated = beam_broken_3

signal.pause()
