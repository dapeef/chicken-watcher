import os
import signal

from gpiozero.pins.lgpio import LGPIOFactory

from hardware_agent.manager import HardwareManager


def run_agent():
    manager = HardwareManager()

    manager.add_rfid_reader("left", os.environ.get("RFID_PORT_BY_ID_LEFT"))
    manager.add_rfid_reader("right", os.environ.get("RFID_PORT_BY_ID_RIGHT"))

    manager.add_camera("cam", os.environ.get("CAMERA_DEVICE_BY_ID"))

    try:
        pin_factory = LGPIOFactory(chip=0)
    except Exception as e:
        print(f"Could not initialize LGPIOFactory: {e}")
        pin_factory = None

    manager.add_beam_sensor("left", os.environ.get("BEAM_BREAK_GPIO_LEFT"), pin_factory)
    manager.add_beam_sensor(
        "right", os.environ.get("BEAM_BREAK_GPIO_RIGHT"), pin_factory
    )

    print("Hardware Manager started. Sensors are connecting in background.")

    signal.pause()


if __name__ == "__main__":
    run_agent()
