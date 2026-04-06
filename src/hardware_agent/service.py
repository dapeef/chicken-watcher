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

    manager.add_rfid_reader("left", os.environ.get("RFID_PORT_BY_ID_LEFT"))
    manager.add_rfid_reader("right", os.environ.get("RFID_PORT_BY_ID_RIGHT"))

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
