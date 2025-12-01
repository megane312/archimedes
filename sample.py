"""
sample.py

MD10Cモータードライバを使ってRaspberry Piでモーターを動かす簡易スクリプト。
このファイルは以下を改善しています:
- RPi.GPIO が無い環境向けのフェイクGPIOを追加して、デスクトップ上でも構文チェック・動作確認が可能
- 実行時の権限チェックと丁寧なエラーメッセージ
- `__main__` ガードと引数パーサで実行方法を選べる

注意: 実機で動かすときは `sudo` で実行してください。
"""

import time
import os
import argparse

# Try pigpio first (works with pigpiod daemon and supports newer Pi platforms)
try:
    import pigpio
    _HAS_PIGPIO = True
except Exception:
    _HAS_PIGPIO = False

try:
    import RPi.GPIO as GPIO
    _HAS_RPI = True
except Exception:
    _HAS_RPI = False

try:
    import gpiod
    _HAS_GPIOD = True
except Exception:
    _HAS_GPIOD = False


class _FakePWM:
    def __init__(self, pin, freq):
        self.pin = pin
        self.freq = freq
        self.duty = 0

    def start(self, duty):
        self.duty = duty
        print(f"[FAKE PWM] start pin={self.pin} freq={self.freq} duty={duty}")

    def ChangeDutyCycle(self, duty):
        self.duty = duty
        print(f"[FAKE PWM] ChangeDutyCycle pin={self.pin} -> duty={duty}")

    def stop(self):
        print(f"[FAKE PWM] stop pin={self.pin}")


class _FakeGPIO:
    BCM = 'BCM'
    OUT = 'OUT'
    IN = 'IN'
    HIGH = 1
    LOW = 0

    def __init__(self):
        self._mode = None
        self._setup = {}

    def setmode(self, mode):
        self._mode = mode
        print(f"[FAKE GPIO] setmode({mode})")

    def setup(self, pin, mode):
        self._setup[pin] = mode
        print(f"[FAKE GPIO] setup(pin={pin}, mode={mode})")

    def output(self, pin, value):
        print(f"[FAKE GPIO] output(pin={pin}, value={value})")

    def PWM(self, pin, freq):
        return _FakePWM(pin, freq)

    def cleanup(self):
        print("[FAKE GPIO] cleanup()")


class _SysfsPWM:
    def __init__(self, gpio, pin, freq):
        self.gpio = gpio
        self.pin = pin
        self.freq = freq
        self._duty = 0
        self._running = False
        self._thread = None

    def start(self, duty):
        self._duty = max(0, min(100, duty))
        self._running = True
        self._thread = __import__('threading').Thread(target=self._run)
        self._thread.daemon = True
        self._thread.start()
        print(f"[SYSFS PWM] start pin={self.pin} freq={self.freq} duty={duty}")

    def ChangeDutyCycle(self, duty):
        self._duty = max(0, min(100, duty))
        print(f"[SYSFS PWM] ChangeDutyCycle pin={self.pin} -> duty={duty}")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.5)
        # ensure pin low
        try:
            self.gpio.output(self.pin, 0)
        except Exception:
            pass
        print(f"[SYSFS PWM] stop pin={self.pin}")

    def _run(self):
        import time
        value_path = f"/sys/class/gpio/gpio{self.pin}/value"
        period = 1.0 / max(1.0, float(self.freq))
        try:
            with open(value_path, 'w') as f:
                while self._running:
                    duty = self._duty
                    if duty <= 0:
                        f.write('0')
                        f.flush()
                        time.sleep(period)
                        continue
                    if duty >= 100:
                        f.write('1')
                        f.flush()
                        time.sleep(period)
                        continue
                    on_time = period * (duty / 100.0)
                    off_time = period - on_time
                    f.write('1')
                    f.flush()
                    time.sleep(on_time)
                    f.write('0')
                    f.flush()
                    time.sleep(off_time)
        except Exception:
            return


class _SysfsGPIO:
    BCM = 'BCM'
    OUT = 'OUT'
    IN = 'IN'
    HIGH = 1
    LOW = 0

    def __init__(self):
        self._export_path = '/sys/class/gpio/export'
        self._unexport_path = '/sys/class/gpio/unexport'
        self._dirs = {}

    def _export(self, pin):
        gpio_dir = f"/sys/class/gpio/gpio{pin}"
        if not __import__('os').path.exists(gpio_dir):
            try:
                with open(self._export_path, 'w') as f:
                    f.write(str(pin))
            except Exception:
                pass

    def setmode(self, mode):
        print(f"[SYSFS GPIO] setmode({mode})")

    def setup(self, pin, mode):
        self._export(pin)
        gpio_dir = f"/sys/class/gpio/gpio{pin}"
        direction_path = gpio_dir + '/direction'
        # wait for gpio to appear
        import time, os
        for _ in range(10):
            if os.path.exists(direction_path):
                break
            time.sleep(0.01)
        try:
            with open(direction_path, 'w') as f:
                if mode == self.OUT:
                    f.write('out')
                else:
                    f.write('in')
        except Exception:
            pass

    def output(self, pin, value):
        value_path = f"/sys/class/gpio/gpio{pin}/value"
        try:
            with open(value_path, 'w') as f:
                f.write('1' if value else '0')
        except Exception as e:
            print(f"[SYSFS GPIO] write error pin={pin}: {e}")

    def PWM(self, pin, freq):
        self._export(pin)
        return _SysfsPWM(self, pin, freq)

    def cleanup(self):
        print('[SYSFS GPIO] cleanup()')


# pigpio backend wrapper: map required methods to pigpio.Pi()
class _PigpioPWM:
    def __init__(self, pig, pin):
        self.pig = pig
        self.pin = pin

    def start(self, duty):
        # pigpio uses 0-255 for duty cycle for hardware PWM on some pins
        val = int(max(0, min(100, duty)) * 255 / 100)
        self.pig.set_PWM_dutycycle(self.pin, val)
        print(f"[PIGPIO PWM] start pin={self.pin} duty={duty}")

    def ChangeDutyCycle(self, duty):
        val = int(max(0, min(100, duty)) * 255 / 100)
        self.pig.set_PWM_dutycycle(self.pin, val)
        print(f"[PIGPIO PWM] ChangeDutyCycle pin={self.pin} -> duty={duty}")

    def stop(self):
        self.pig.set_PWM_dutycycle(self.pin, 0)
        print(f"[PIGPIO PWM] stop pin={self.pin}")


class _PigpioGPIO:
    BCM = 'BCM'
    OUT = 'OUT'
    IN = 'IN'
    HIGH = 1
    LOW = 0

    def __init__(self, pig):
        self.pig = pig

    def setmode(self, mode):
        # pigpio doesn't need mode sets; no-op
        print(f"[PIGPIO GPIO] setmode({mode})")

    def setup(self, pin, mode):
        if mode == self.OUT:
            self.pig.set_mode(pin, pigpio.OUTPUT)
        else:
            self.pig.set_mode(pin, pigpio.INPUT)
        print(f"[PIGPIO GPIO] setup(pin={pin}, mode={mode})")

    def output(self, pin, value):
        self.pig.write(pin, 1 if value else 0)
        print(f"[PIGPIO GPIO] output(pin={pin}, value={value})")

    def PWM(self, pin, freq):
        # pigpio allows setting PWM frequency per-pin
        try:
            self.pig.set_PWM_frequency(pin, freq)
        except Exception:
            pass
        return _PigpioPWM(self.pig, pin)

    def cleanup(self):
        # pigpio cleanup is handled by stopping PWM and disconnecting if needed
        print("[PIGPIO GPIO] cleanup()")


# libgpiod backend (uses character device gpiochip interface)
class _LibgpiodPWM:
    def __init__(self, req, offset, freq):
        self.req = req
        self.offset = offset
        self.freq = freq
        self._duty = 0
        self._running = False
        self._thread = None

    def start(self, duty):
        self._duty = max(0, min(100, duty))
        self._running = True
        import threading
        self._thread = threading.Thread(target=self._run)
        self._thread.daemon = True
        self._thread.start()
        print(f"[GPIOD PWM] start line duty={duty} freq={self.freq}")

    def ChangeDutyCycle(self, duty):
        self._duty = max(0, min(100, duty))
        print(f"[GPIOD PWM] ChangeDutyCycle -> duty={duty}")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.5)
        try:
            self.line.set_value(0)
        except Exception:
            pass
        print("[GPIOD PWM] stop")

    def _run(self):
        import time
        period = 1.0 / max(1.0, float(self.freq))
        try:
            while self._running:
                duty = self._duty
                if duty <= 0:
                    self.req.set_value(self.offset, gpiod.line.Value.INACTIVE)
                    time.sleep(period)
                    continue
                if duty >= 100:
                    self.req.set_value(self.offset, gpiod.line.Value.ACTIVE)
                    time.sleep(period)
                    continue
                on_time = period * (duty / 100.0)
                off_time = period - on_time
                self.req.set_value(self.offset, gpiod.line.Value.ACTIVE)
                time.sleep(on_time)
                self.req.set_value(self.offset, gpiod.line.Value.INACTIVE)
                time.sleep(off_time)
        except Exception:
            return


class _LibgpiodGPIO:
    BCM = 'BCM'
    OUT = 'OUT'
    IN = 'IN'
    HIGH = 1
    LOW = 0

    def __init__(self):
        self._chips = []  # list of (dev_path, base, ngpio)
        self._lines = {}  # pin -> (chip, line, offset)
        self._scan_chips()

    def _scan_chips(self):
        # read /sys/class/gpio/gpiochip* to discover base/ngpio and map to /dev/gpiochipN
        import glob
        for chip_path in glob.glob('/sys/class/gpio/gpiochip*'):
            try:
                base = int(open(chip_path + '/base').read().strip())
                ngpio = int(open(chip_path + '/ngpio').read().strip())
                name = chip_path.split('/')[-1]
                # find corresponding /dev entry
                dev = '/dev/' + name
                self._chips.append((dev, base, ngpio))
            except Exception:
                continue

    def _find_chip_for_pin(self, pin):
        for dev, base, ngpio in self._chips:
            if base <= pin < base + ngpio:
                return dev, pin - base
        # fallback: try gpiochip0
        return '/dev/gpiochip0', pin

    def setmode(self, mode):
        print(f"[GPIOD GPIO] setmode({mode})")

    def setup(self, pin, mode):
        dev, offset = self._find_chip_for_pin(pin)
        try:
            chip = gpiod.Chip(dev)
            settings = gpiod.LineSettings()
            settings.direction = gpiod.line.Direction.OUTPUT
            settings.output_value = gpiod.line.Value.INACTIVE
            req = chip.request_lines({offset: settings}, consumer='sample', output_values={offset: gpiod.line.Value.INACTIVE})
            self._lines[pin] = (chip, req, offset)
            print(f"[GPIOD GPIO] setup(pin={pin}, offset={offset} on {dev})")
        except Exception as e:
            print(f"[GPIOD GPIO] setup failed for pin={pin}: {e}")

    def output(self, pin, value):
        try:
            chip, req, offset = self._lines[pin]
            req.set_value(offset, gpiod.line.Value.ACTIVE if value else gpiod.line.Value.INACTIVE)
            print(f"[GPIOD GPIO] output(pin={pin}, value={value})")
        except Exception as e:
            print(f"[GPIOD GPIO] output failed pin={pin}: {e}")

    def PWM(self, pin, freq):
        # ensure line requested
        if pin not in self._lines:
            self.setup(pin, self.OUT)
        _, req, offset = self._lines.get(pin, (None, None, None))
        return _LibgpiodPWM(req, offset, freq)

    def cleanup(self):
        for pin, (chip, req, offset) in list(self._lines.items()):
            try:
                req.set_value(offset, gpiod.line.Value.INACTIVE)
                req.release()
            except Exception:
                pass
        print('[GPIOD GPIO] cleanup()')


_BACKEND = None

# pigpio -> RPi.GPIO -> FAKE の優先順位でバックエンドを選択
if _HAS_PIGPIO:
    try:
        _pig = pigpio.pi()
        if _pig.connected:
            GPIO = _PigpioGPIO(_pig)
            _BACKEND = 'pigpio'
        else:
            print('[INFO] pigpio module present but pigpiod not running; skipping pigpio backend')
            _HAS_PIGPIO = False
    except Exception as e:
        print(f"[INFO] pigpio init failed: {e}; skipping pigpio backend")
        _HAS_PIGPIO = False

# Try libgpiod character-device backend if available
if _BACKEND is None and _HAS_GPIOD:
    try:
        gpiod_gpio = _LibgpiodGPIO()
        # quick smoke test
        try:
            gpiod_gpio.setup(4, gpiod_gpio.OUT)
            gpiod_gpio.cleanup()
            GPIO = gpiod_gpio
            _BACKEND = 'gpiod'
            print('[INFO] using libgpiod backend')
        except Exception as e:
            print(f'[INFO] libgpiod runtime test failed: {e}')
            _HAS_GPIOD = False
    except Exception as e:
        print(f'[INFO] libgpiod init failed: {e}')
        _HAS_GPIOD = False

if _BACKEND is None and _HAS_RPI:
    if os.name == 'posix' and hasattr(os, 'geteuid') and os.geteuid() != 0:
        print('[INFO] RPi.GPIO imported but not running as root; switching to FAKE GPIO for safety.')
        GPIO = _FakeGPIO()
        _HAS_RPI = False
    else:
        # 実行時にピンセットアップが可能か試す
        try:
            GPIO.setmode(GPIO.BCM)
            test_pin = 4
            GPIO.setup(test_pin, GPIO.OUT)
            GPIO.cleanup()
            _BACKEND = 'rpi_gpio'
        except Exception as e:
            print(f"[INFO] GPIO runtime verification failed: {e}; switching to FAKE GPIO.")
            GPIO = _FakeGPIO()
            _HAS_RPI = False

if _BACKEND is None:
    GPIO = _FakeGPIO()
    _BACKEND = 'fake'

print(f"[INFO] using GPIO backend: {_BACKEND}")


DIR_PIN = 17
PWM_PIN = 18  # PWMに推奨ピン (BCM番号)

# If previous backends failed, try sysfs GPIO (/sys/class/gpio) for real pin control.
if _BACKEND == 'fake':
    try:
        if os.path.exists('/sys/class/gpio/export'):
            sysfs_gpio = _SysfsGPIO()
            # quick smoke test: export pins and set direction
            try:
                sysfs_gpio.setmode(sysfs_gpio.BCM)
                sysfs_gpio.setup(DIR_PIN, sysfs_gpio.OUT)
                sysfs_gpio.setup(PWM_PIN, sysfs_gpio.OUT)
                GPIO = sysfs_gpio
                _BACKEND = 'sysfs'
                print('[INFO] switched to SYSFS GPIO backend')
            except Exception as e:
                pass
    except Exception:
        pass


def motor_run(gpio, pwm, direction, duty):
    gpio.output(DIR_PIN, GPIO.HIGH if direction else GPIO.LOW)
    pwm.ChangeDutyCycle(max(0, min(100, duty)))  # duty 0〜100 (%)


def ensure_root():
    if os.name == 'posix' and hasattr(os, 'geteuid') and os.geteuid() != 0:
        print('Warning: Running without root. On Raspberry Pi you usually need sudo to access GPIO.')


def demo_sequence(gpio):
    gpio.setmode(GPIO.BCM)
    gpio.setup(DIR_PIN, GPIO.OUT)
    gpio.setup(PWM_PIN, GPIO.OUT)

    pwm = gpio.PWM(PWM_PIN, 1000)
    pwm.start(0)

    try:
        print("正転 50%")
        motor_run(gpio, pwm, True, 50)
        time.sleep(2)

        print("停止")
        motor_run(gpio, pwm, True, 0)
        time.sleep(1)

        print("逆転 80%")
        motor_run(gpio, pwm, False, 80)
        time.sleep(2)

        print("停止")
        motor_run(gpio, pwm, True, 0)
    finally:
        pwm.stop()
        gpio.cleanup()


def main():
    parser = argparse.ArgumentParser(description='MD10C Motor demo for Raspberry Pi')
    parser.add_argument('--demo', action='store_true', help='Run the built-in demo sequence')
    parser.add_argument('--dir', choices=['forward', 'backward'], default='forward', help='Direction for single run')
    parser.add_argument('--duty', type=int, default=50, help='Duty cycle for single run (0-100)')
    parser.add_argument('--duration', type=float, default=2.0, help='Duration in seconds for single run')

    args = parser.parse_args()

    ensure_root()

    if args.demo:
        demo_sequence(GPIO)
        return

    # 単発実行
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(DIR_PIN, GPIO.OUT)
    GPIO.setup(PWM_PIN, GPIO.OUT)

    pwm = GPIO.PWM(PWM_PIN, 1000)
    pwm.start(0)

    try:
        direction = True if args.dir == 'forward' else False
        print(f"Running direction={args.dir} duty={args.duty} duration={args.duration}s")
        motor_run(GPIO, pwm, direction, args.duty)
        time.sleep(args.duration)
        print("Stopping motor")
        motor_run(GPIO, pwm, True, 0)
    finally:
        pwm.stop()
        GPIO.cleanup()


if __name__ == '__main__':
    main()
