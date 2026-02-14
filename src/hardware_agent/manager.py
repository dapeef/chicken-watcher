from hardware_agent.beam_break_sensor import BeamSensor
from hardware_agent.camera import USBCamera
from hardware_agent.rfid_reader import RFIDReader
from hardware_agent.handlers import (
    report_status,
    handle_tag_read,
    handle_camera_frame,
    handle_beam_break,
)


class HardwareManager:
    def __init__(self):
        self.sensors = []

    def add_rfid_reader(self, name: str, port: str):
        if not port:
            print(f"[HardwareManager] Skipping RFID reader '{name}': No port provided")
            report_status(f"rfid_{name}", False, "No port configured")
            return

        reader = RFIDReader(name, port)
        self.sensors.append(reader)
        reader.start_reading(
            handle_tag_read,
            status_callback=lambda n, c, m="": report_status(f"rfid_{n}", c, m),
        )

    def add_camera(self, name: str, device: str):
        if not device:
            print(f"[HardwareManager] Skipping camera '{name}': No device provided")
            report_status(f"camera_{name}", False, "No device configured")
            return

        camera = USBCamera(name, device=device, fps=1)
        self.sensors.append(camera)
        camera.start_capturing(
            handle_camera_frame,
            status_callback=lambda n, c, m="": report_status(f"camera_{n}", c, m),
        )

    def add_beam_sensor(self, name: str, gpio: str, pin_factory):
        if not pin_factory:
            print(
                f"[HardwareManager] Skipping beam sensor '{name}': No pin factory available"
            )
            report_status(f"beam_{name}", False, "LGPIO not available")
            return

        if not gpio:
            print(f"[HardwareManager] Skipping beam sensor '{name}': No GPIO provided")
            report_status(f"beam_{name}", False, "No GPIO configured")
            return

        try:
            pin = int(gpio)
        except (ValueError, TypeError):
            print(f"[HardwareManager] Skipping beam sensor '{name}': Invalid GPIO '{gpio}'")
            report_status(f"beam_{name}", False, f"Invalid GPIO: {gpio}")
            return

        beam = BeamSensor(name, pin, pin_factory=pin_factory)
        self.sensors.append(beam)
        beam.start_reading(
            handle_beam_break,
            status_callback=lambda n, c, m="": report_status(f"beam_{n}", c, m),
        )
