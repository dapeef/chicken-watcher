from gpiozero.pins.lgpio import LGPIOFactory

print("Creating factory...")
factory = LGPIOFactory(chip=0)
print(f"Factory created: {factory}")
