"""Joystick inspection tool

Prints connected joystick(s) info and continuously dumps axes, buttons and hats
values with timestamps so you can map controller inputs to indices.

Usage:
  PYTHONPATH=. python3 tools/joy_inspect.py [--duration SECS] [--interval SECS]

Examples:
  # run for 30 seconds (recommended when probing mappings)
  PYTHONPATH=. python3 tools/joy_inspect.py --duration 30

  # run interactively until Ctrl-C, print values every 0.2s
  PYTHONPATH=. python3 tools/joy_inspect.py

The script does not require root. Install pygame if missing:
  pip3 install --user pygame

"""
import time
import argparse

try:
    import pygame
except Exception:
    pygame = None


def ts():
    return time.strftime('%H:%M:%S') + f'.{int((time.time()%1)*1000):03d}'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--duration', type=float, default=None, help='Duration in seconds to run (default: run until Ctrl-C)')
    p.add_argument('--interval', type=float, default=0.2, help='Poll interval in seconds (default 0.2)')
    args = p.parse_args()

    if pygame is None:
        print('pygame is not installed. Install with: pip3 install pygame')
        return

    pygame.init()
    pygame.joystick.init()

    try:
        count = pygame.joystick.get_count()
        if count == 0:
            print('No joystick detected. Connect a controller and try again.')
            return

        print(f'Found {count} joystick(s)')
        joysticks = []
        for i in range(count):
            j = pygame.joystick.Joystick(i)
            j.init()
            info = {
                'id': i,
                'name': j.get_name(),
                'axes': j.get_numaxes(),
                'buttons': j.get_numbuttons(),
                'hats': j.get_numhats(),
                'obj': j,
            }
            joysticks.append(info)
            print(f"Joystick {i}: name='{info['name']}' axes={info['axes']} buttons={info['buttons']} hats={info['hats']}")

        print('\nStarting dump. Move sticks and press buttons to observe indices and values.')
        print('Press Ctrl-C to stop.')

        start = time.time()
        prev_states = [None] * len(joysticks)
        while True:
            pygame.event.pump()
            out_lines = []
            for idx, info in enumerate(joysticks):
                j = info['obj']
                axes = [round(j.get_axis(a), 3) for a in range(info['axes'])]
                buttons = [j.get_button(b) for b in range(info['buttons'])]
                hats = [j.get_hat(h) for h in range(info['hats'])]
                state = {'axes': axes, 'buttons': buttons, 'hats': hats}

                # print every poll (helps mapping), but avoid flooding if identical
                if prev_states[idx] != state:
                    out_lines.append(f"[{ts()}] Joystick {info['id']} '{info['name']}'")
                    if axes:
                        out_lines.append('  axes:   ' + ', '.join(f'{i}:{v:+.3f}' for i, v in enumerate(axes)))
                    if buttons:
                        out_lines.append('  buttons:' + ' '.join(f'{i}:{v}' for i, v in enumerate(buttons)))
                    if hats:
                        out_lines.append('  hats:   ' + ' '.join(f'{i}:{v}' for i, v in enumerate(hats)))
                    prev_states[idx] = state

            if out_lines:
                print('\n'.join(out_lines))

            # exit conditions
            if args.duration is not None and (time.time() - start) >= args.duration:
                print(f'[{ts()}] Duration elapsed ({args.duration}s). Exiting.')
                break

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print('\nInterrupted by user')
    finally:
        try:
            pygame.joystick.quit()
            pygame.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
