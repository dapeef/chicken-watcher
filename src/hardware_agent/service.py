import logging
import os
import signal

try:
    from gpiozero.pins.lgpio import LGPIOFactory
except ImportError:
    LGPIOFactory = None

from hardware_agent.manager import HardwareManager

logger = logging.getLogger(__name__)


def run_agent():
    manager = HardwareManager()

    # Each nesting box supports up to 4 RFID readers, identified by
    # RFID_PORT_LEFT_1 … RFID_PORT_LEFT_4 and RFID_PORT_RIGHT_1 … RFID_PORT_RIGHT_4.
    # Missing or empty variables are skipped gracefully.
    for box in ("left", "right"):
        for n in range(1, 5):
            port = os.environ.get(f"RFID_PORT_{box.upper()}_{n}")
            manager.add_rfid_reader(f"{box}_{n}", port)

    manager.add_camera("cam", os.environ.get("CAMERA_DEVICE_BY_ID"))

    if LGPIOFactory is None:
        logger.warning("lgpio is not available; GPIO/beam sensors will be disabled")
        pin_factory = None
    else:
        try:
            pin_factory = LGPIOFactory(chip=0)
        except Exception as e:
            logger.warning("Could not initialize LGPIOFactory: %s", e)
            pin_factory = None

    manager.add_beam_sensor("left", os.environ.get("BEAM_BREAK_GPIO_LEFT"), pin_factory)
    manager.add_beam_sensor(
        "right", os.environ.get("BEAM_BREAK_GPIO_RIGHT"), pin_factory
    )

    logger.info("Hardware Manager started. Sensors are connecting in background.")

    signal.pause()


if __name__ == "__main__":
    run_agent()
