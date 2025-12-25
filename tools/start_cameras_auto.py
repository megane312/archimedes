#!/usr/bin/env python3
import argparse
import glob
import os
import socket
import subprocess
import sys
import time
from typing import List, Tuple

REPO_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
SCRIPT_PATH = os.path.join(REPO_DIR, 'tools', 'camera_server.py')


def is_port_free(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(('0.0.0.0', port))
        return True
    except OSError:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def next_free_ports(start_port: int, count: int) -> List[int]:
    ports = []
    port = start_port
    while len(ports) < count:
        if is_port_free(port):
            ports.append(port)
        port += 1
    return ports


def list_video_devices() -> List[str]:
    devices = sorted(glob.glob('/dev/video[0-9]*'))
    # Prefer lower indices, but keep order
    return devices


def start_camera_process(device: str, port: int, width: int, height: int, fps: int, sudo: bool=False) -> subprocess.Popen:
    cmd = [
        sys.executable,
        SCRIPT_PATH,
        '--type', 'usb',
        '--device', device,
        '--port', str(port),
        '--width', str(width),
        '--height', str(height),
        '--fps', str(fps),
    ]
    if sudo:
        cmd = ['sudo'] + cmd
    # Start detached so this script can exit while servers continue
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def drain_start_output(p: subprocess.Popen, timeout_sec: float = 2.0) -> str:
    output_lines = []
    start = time.time()
    while time.time() - start < timeout_sec:
        if p.poll() is not None:
            # Process terminated; collect remaining output
            try:
                rest = p.stdout.read() if p.stdout else ''
            except Exception:
                rest = ''
            output_lines.append(rest)
            break
        try:
            line = p.stdout.readline() if p.stdout else ''
        except Exception:
            line = ''
        if line:
            output_lines.append(line.rstrip())
        else:
            time.sleep(0.05)
    return '\n'.join(output_lines)


def main():
    parser = argparse.ArgumentParser(description='USBカメラを自動検出してMJPEGサーバーを起動します')
    parser.add_argument('--start-port', type=int, default=8080, help='最初に試すポート番号（デフォルト: 8080）')
    parser.add_argument('--width', type=int, default=640, help='フレーム幅（デフォルト: 640）')
    parser.add_argument('--height', type=int, default=360, help='フレーム高さ（デフォルト: 360）')
    parser.add_argument('--fps', type=int, default=30, help='フレームレート（デフォルト: 30）')
    parser.add_argument('--limit', type=int, default=0, help='起動するカメラの最大数（0は全て）')
    parser.add_argument('--sudo', action='store_true', help='必要に応じてsudoで起動する')
    args = parser.parse_args()

    devices = list_video_devices()
    if not devices:
        print('カメラデバイスが見つかりませんでした (/dev/video*)')
        print('USBカメラを接続してから再実行してください。')
        sys.exit(1)

    if args.limit > 0:
        devices = devices[:args.limit]

    ports = next_free_ports(args.start_port, len(devices))

    print('自動起動を開始します:')
    print(f'  デバイス: {", ".join(devices)}')
    print(f'  割当ポート: {", ".join(map(str, ports))}')
    print(f'  解像度: {args.width}x{args.height}, FPS: {args.fps}')

    procs: List[Tuple[str, int, subprocess.Popen]] = []

    for device, port in zip(devices, ports):
        print(f'→ 起動: {device} on port {port} ...')
        p = start_camera_process(device, port, args.width, args.height, args.fps, sudo=args.sudo)
        procs.append((device, port, p))
        # Drain a bit of startup output for feedback
        out = drain_start_output(p, timeout_sec=2.0)
        if out:
            print(out)
        # If process exited early, warn
        if p.poll() is not None:
            print(f'  ⚠  {device} の起動に失敗しました（プロセス終了）。別の /dev/videoX を試してください。')

    print('\n起動サマリ:')
    for device, port, p in procs:
        status = 'running' if p.poll() is None else f'exited({p.returncode})'
        print(f'  - {device} → http://localhost:{port}/  [{status}]')

    print('\nブラウザから各URLにアクセスして映像を確認してください。')
    print('このスクリプトはサーバープロセスをバックグラウンドで起動します。')
    print('停止するには、各サーバーを起動したターミナルで Ctrl+C または、以下のコマンドを使用:')
    print('  pkill -f camera_server.py')


if __name__ == '__main__':
    main()
