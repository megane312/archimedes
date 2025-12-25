# MD10C + Raspberry Pi テスト手順

このドキュメントは `sample.py` を Raspberry Pi（Pi 5 等）で安全にテストするための手順をまとめています。

前提:
- `sample.py` は `DIR_PIN = 17`, `PWM_PIN = 18`（BCM）を使用します。配線は必要に応じて変更してください。
- 実機でGPIOにアクセスするには通常 root 権限が必要です（`sudo`）。

安全注意:
- 電源を入れる前に配線を必ず確認してください。
- モーターの電流が高い場合は外部電源を使用し、Pi とドライバのGNDを共通にしてください。
- モーターが空転しても周囲に危険がない状態でテストしてください。

配線（基本）:
- MD10C V+ : モータ用電源の + (Pi では供給しないでください)
- MD10C GND: モータ用電源の - と Raspberry Pi の GND を共通にする
- MD10C DIR: Raspberry Pi `GPIO17` (BCM 17)
- MD10C PWM: Raspberry Pi `GPIO18` (BCM 18)
- MD10C ENABLE（存在する場合）: 必要に応じて接続/制御

準備:
1. Pi に `sample.py` と同じディレクトリにある `run_test.sh` を転送済みであることを確認。
2. 必要な場合は `RPi.GPIO` をインストール:

```bash
sudo apt update
sudo apt install python3-rpi.gpio
# もしくは pip:
sudo pip3 install RPi.GPIO
```

実行手順（実機）:
1. 電源を切って配線を確認。
2. 電源を入れる。
3. `run_test.sh` に実行権限を付与して実行:

```bash
cd /home/archimedes/ドキュメント
chmod +x run_test.sh
sudo ./run_test.sh
```

ログは `sample_test_YYYYMMDD_HHMMSS.log` に保存され、最後の50行がターミナルに表示されます。

トラブルシュート:
- `Cannot determine SOC peripheral base address` のようなエラーが出る場合、`sudo` で実行しているか確認してください。
- `ImportError: No module named RPi.GPIO` の場合は上記インストール手順を実行してください。

結果を共有する際は生成されたログファイルの内容（特に例外トレース）を貼ってください。こちらで次の調整を案内します。

短い追記: コントローラ駆動・診断ツールについて
---------------------------------

このリポジトリにはコントローラ操作とハードウェア診断を補助するスクリプトを追加しています。簡単な使い方を以下に示します。

- コントローラ駆動モード (`robot_drive.py`):
	- ジョイスティックのハット（D-pad）を優先してモータ制御します。デフォルトで `hats[0]` の値で前進/後退/左右旋回を行います。
	- 起動方法（推奨: 非 root でまず試す）:
		```bash
		PYTHONPATH=. python3 robot_drive.py --controller
		# あるいは権限が必要な場合
		sudo PYTHONPATH=. python3 robot_drive.py --controller
		```
	- 軸インデックスを変える場合は `--axis7` / `--axis8` を指定します（既存の軸フォールバックが動作します）。
	- DIR 極性が逆の場合は `--invert-dir` を付けて反転できます。

- 診断ツール (`tools/`):
	- `tools/joy_inspect.py` : ジョイスティックの軸・ボタン・ハットのインデックスと値を時刻付きで表示します（コントローラの割当確認に便利）。
		```bash
		PYTHONPATH=. python3 tools/joy_inspect.py --duration 30
		```
	- `tools/pwm_probe.py` : 指定モータに対して時刻付きで PWM/DIR を出力するプローブ。マルチメータ/オシロで信号を観測する際に使います。
		```bash
		sudo PYTHONPATH=. python3 tools/pwm_probe.py
		```
	- `tools/dir_toggle.py` : 単純に DIR を切り替えながら PWM を出力する短い診断スクリプト。

	- ネットワーク経由での遠隔制御（送受信分離）:
		- `tools/drive_server.py` : Raspberry Pi 側で動作する UDP サーバ。JSON メッセージを受け取り、モータを制御します。
			```bash
			# Pi 側で実行
			sudo PYTHONPATH=. python3 tools/drive_server.py --bind 0.0.0.0 --port 5005
			```
		- `tools/joy_net_client.py` : ノートPC側で動作するクライアント。pygame でコントローラ入力を読み、UDP で Pi に送信します。
			```bash
			# ノートPC側で実行（--host に Pi のIP）
			PYTHONPATH=. python3 tools/joy_net_client.py --host 192.168.1.50 --port 5005
			```
		- プロトコル: シンプルな JSON。例: `{"type":"hat","value":[0,1]}` や `{"type":"axes","a7":1,"a8":0}`。

	- Alternate setup: Pi polls a PC server (Pi as client)
		- If your networking setup makes it easier for the Pi to poll the PC (for example when the PC is behind a VPN/NAT), you can run a lightweight HTTP server on the PC which exposes the controller state at `GET /state` and run a polling client on the Pi.
		- PC (server): `tools/joy_server.py` — reads joystick with pygame and serves JSON at `/state`.
			```bash
			PYTHONPATH=. python3 tools/joy_server.py --host 0.0.0.0 --port 8000
			```
		- Pi (client): `tools/drive_pull_client.py` — polls the PC `/state` endpoint and applies commands.
			```bash
			sudo PYTHONPATH=. python3 tools/drive_pull_client.py --url http://<PC_IP>:8000/state --interval 0.1
			```

		PC Setup (quick)
		-----------------

		If you want a quick reproducible environment on your laptop, run the provided setup script from the repository root. It will create a virtualenv at `~/archimedes/venv` and install the minimal dependencies.

		```bash
		cd /home/archimedes/ドキュメント
		bash tools/setup_pc.sh

		# Activate the virtualenv before running joystick tools:
		source ~/archimedes/venv/bin/activate

		# Start joystick HTTP server (allow Pi to poll):
		PYTHONPATH=. python3 tools/joy_server.py --host 0.0.0.0 --port 8000

		# Or run the UDP client to push to a Pi (replace <PI_IP>):
		PYTHONPATH=. python3 tools/joy_net_client.py --host <PI_IP> --port 5005
		```

		systemd service templates are included in `tools/systemd/` as examples for making the server/client persistent. Edit placeholders (`%USER%`, `%REPO_DIR%`, `<PC_IP>`) before installing to `/etc/systemd/system/`.



- テスト:
	- 単体のマッピング関数に対する簡易テストを `tests/test_compute_motor_commands.py` に追加しています。ワークスペースのルートで実行できます:
		```bash
		PYTHONPATH=. python3 tests/test_compute_motor_commands.py
		```

注意: モータドライバ（MD10C 等）やモータの電源仕様を必ず確認してください。高デューティで両モータを同時に駆動すると大電流が流れるため配線や電源容量に注意が必要です。



カメラストリーミング
---------------------------------

Raspberry Pi に接続したカメラの映像をWeb ブラウザでストリーミングするツールです。

### 使用方法

#### 1. カメラ接続の確認（重要）

まず、カメラが正しく接続・有効化されているか診断してください：

```bash
python3 tools/camera_server.py --diagnose
```

出力例：
```
=== Camera Diagnostic ===

1. Checking rpicam tools...
   Output: No cameras available!

2. Checking /dev/video* devices...
   ✓ Found: video0, video1, ...

3. Camera must be enabled in raspi-config
   Run: sudo raspi-config
   Go to: Interface Options > Camera > Enable

4. If camera was recently enabled, restart with:
   sudo reboot
```

**カメラが見つからない場合の対処:**
- CSI/DSI ポートにカメラを正しく接続
- `sudo raspi-config` を実行 → `Interface Options` → `Camera` → `Enable`
- `sudo reboot` でリスタート

#### 2. ストリーミング開始

カメラが接続されたら、サーバーを起動：

```bash
# 基本的な起動（ポート8080）
python3 tools/camera_server.py

# ポートをカスタマイズ
python3 tools/camera_server.py --port 8081

# 解像度やFPSをカスタマイズ
python3 tools/camera_server.py --width 800 --height 600 --fps 15
```

USB カメラ（例: `/dev/video0`）を使う場合は `--type usb` を指定します（`rpicam-hello` の "No cameras available!" は USB カメラでは正常です）：

```bash
# USB カメラで起動（デバイスを指定）
python3 tools/camera_server.py --type usb --device /dev/video0 --port 8081 --width 640 --height 360 --fps 30
```

#### 3. ブラウザでアクセス

ストリーミング開始後、以下のURLをブラウザで開きます：

```
http://localhost:8080/
```

ネットワーク上の別マシンからアクセスする場合：
```
http://<ラズベリーパイのIP>:8080/
```

例: `http://192.168.1.50:8080/`

#### 複数カメラの同時ストリーミング

異なるポートで複数起動：

```bash
# カメラ1: ポート8080
python3 tools/camera_server.py --port 8080 &

# カメラ2: ポート8081
python3 tools/camera_server.py --port 8081 &

# カメラ3: ポート8082
python3 tools/camera_server.py --port 8082 &
```

USB カメラを複数使う場合の例：

```bash
# /dev/video0 を 8080 で配信
python3 tools/camera_server.py --type usb --device /dev/video0 --port 8080 --width 640 --height 360 --fps 30 &

# /dev/video2 を 8081 で配信（存在する場合）
python3 tools/camera_server.py --type usb --device /dev/video2 --port 8081 --width 640 --height 360 --fps 30 &
```

自動検出でまとめて起動（推奨）
---------------------------------

USB カメラを自動検出し、空いているポートに割り当てて起動する補助スクリプトを用意しています。

```bash
# すべての /dev/video* を検出し、8080 から順番に起動
python3 tools/start_cameras_auto.py --start-port 8080 --width 640 --height 360 --fps 30

# 2台までに制限して起動
python3 tools/start_cameras_auto.py --start-port 8080 --limit 2

# 権限が必要な環境なら sudo を付ける
python3 tools/start_cameras_auto.py --sudo
```

起動後のアクセス例：

```
http://<Pi_IP>:8080/
http://<Pi_IP>:8081/
...（台数分）
```

### オプション

```bash
python3 tools/camera_server.py --help
```

利用可能なオプション：
- `--port PORT`: HTTPサーバーのポート（デフォルト: 8080）
- `--width WIDTH`: フレーム幅（デフォルト: 640）
- `--height HEIGHT`: フレーム高さ（デフォルト: 360）
- `--fps FPS`: フレームレート（デフォルト: 30）
- `--diagnose`: カメラ接続の診断のみ実行
- `--type {rpi,usb}`: カメラ種別の選択（CSI/libcamera または USB/V4L2）
- `--device /dev/videoX`: USB カメラデバイス（`--type usb` のとき使用）

### 停止方法

```bash
# サーバーターミナルで Ctrl+C を押すか：
pkill -f camera_server.py
```

### 必要な環境

- Raspberry Pi（Pi 4、Pi 5 等）
- CSI/DSI カメラ または USB カメラ
- CSI カメラ利用時: `rpicam-apps` インストール済み
- USB カメラ利用時: `ffmpeg` インストール済み

インストール：
```bash
sudo apt update
sudo apt install -y rpicam-apps ffmpeg
```

### トラブルシューティング

**ブラウザに「Camera Connection Error」が表示される：**
- カメラが物理的に接続されているか確認
- `python3 tools/camera_server.py --diagnose` で診断
- `sudo raspi-config` でカメラを有効化
- `sudo reboot` でリスタート

USB カメラ利用時の補足：
- `rpicam-hello --list-cameras` が "No cameras available!" を出すのは正常です（CSI カメラ検出用）
- `/dev/video*` が存在することを確認（例: `/dev/video0`）
- 起動例: `python3 tools/camera_server.py --type usb --device /dev/video0 --port 8081`

**ストリーミングが遅い：**
- 解像度を下げる: `--width 480 --height 270`
- FPSを下げる: `--fps 15`
- ネットワーク速度を確認

**ポートが使用中というエラー：**
```bash
# 既存のプロセスを停止
pkill -f camera_server
```

