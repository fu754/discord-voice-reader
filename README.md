# Discordテキストチャット読み上げbot
身内サーバー向けに作ったbotです。
- VOICEVOX ENGINEとdiscord.pyを利用したテキストチャット読み上げ(TTS)を行います
- 
## クレジット
- [VOICEVOX/VOICEVOX ENGINE](https://github.com/VOICEVOX/voicevox_engine)
- [Rapptz/discord.py](https://github.com/Rapptz/discord.py)
- [dylanpdx/BetterTwitFix](https://github.com/dylanpdx/BetterTwitFix)

## 環境構築と起動
### 必要
- docker
- docker-compose
- ローカル環境で起動するとき
    - pyenv
    - ffmpeg
### 環境構築
1. `.env`ファイルを作成してDiscordのbotのトークンをセットする
    ```
    DISCORD_BOT_TOKEN=""
    ENV="prod"
    ```
1. ビルド
    ```bash
    docker-compose build
    ```
### 起動
```bash
docker-compose up -d
```
### Windowsのローカルで起動するとき
1. Pythonのインストール
    ```powershell
    pyenv local 3.11.6
    python -m venv venv
    .\venv\Scripts\activate
    pip install -r requirements.txt
    ```
1. `ENV="dev"`にする
1. `python main.py`

### Ubuntuのローカルで起動するとき
1. Pythonのインストール
    ```bash
    pyenv local 3.11.6
    python -m venv venv
    ./venv/bin/activate
    pip install -r requirements.txt
    ```
1. `ENV="dev"`にする
1. `python main.py`

## スラッシュコマンド
### `/start`
- botをVCに参加させ音声読み上げを開始する

### `/stop`
- botをVCから退席させ音声読み上げを終了する

### `/style_list`
- 音声のスタイル一覧を表示する
    ```txt
    スタイル一覧
    四国めたん
    2 : ノーマル
    0 : あまあま
    6 : ツンツン
    4 : セクシー
    36 : ささやき
    37 : ヒソヒソ
    ずんだもん
    3 : ノーマル
    1 : あまあま
    ...
    ```

### `/change_style`
- 音声のスタイルを変更する
- `/style_list`で表示されるIDを半角数字で指定する

### `/check_style`
- 現在の音声スタイルを確認する

### `/default_style`
- 春日部つむぎさん(ノーマル)(ID: 8)にスタイルを変更する

### `/ping`
- サーバーが生きていて応答を返すか確認する

### `/receive_test_start`
- VC音声の受信テストを開始する
- botがVC未接続なら、実行者と同じVCに受信対応クライアントとして参加する
- 開始から停止までに受信した音声をメモリに保持する（ユーザーごとに最大600秒）
- botが通常の`/start`でVCに接続済みの場合は、先に`/stop`で退席してから実行する

### `/receive_test_stop`
- 音声受信を停止し、受信した音声をユーザーごとのWAVファイルとして`recordings/<日時>_<サーバーID>/`に書き出す
- 書き出し先と、ユーザーごとの受信パケット数・録音秒数を実行者にだけ表示する
- 発話のない区間は無音で埋めるため、各WAVは開始時刻を基準に揃っている
- 他の参加者の声を録音するため、テスト前に参加者へ伝えること
- テストを終えてbotをVCから退席させる場合は、続けて`/stop`を実行する

### `/transcribe_start`
- VCの発話をローカルのWhisperで文字起こしし、コマンドを実行したチャンネルに`**ユーザー名**: 発話内容`の形式で投稿する
- botが未接続なら、実行者と同じVCに参加する
- 音声は保存しない。他の参加者の発話がテキスト化されるため、事前に伝えること
- 初回はモデルの読み込み(未取得ならダウンロード)に時間がかかる
- `/receive_test_start`とは同時に実行できない

### `/transcribe_stop`
- 文字起こしを終了する。処理待ちの発話は完了次第投稿される
- 次の場合は自動で終了し、開始したチャンネルに通知する
  - botがVCから切断された(`/stop`、キック、移動など)
  - VCにbot以外の参加者がいなくなった(botはVCに残る)

### `/judge_start`
- 文字起こし中(`/transcribe_start`の後)に実行すると、以降の発話をLM Studioに渡し、社会通念・ポリティカルコレクトネスの観点で問題度(0=問題なし〜10=重大)を採点する
- 結果は実行したチャンネルに`✅ 名前 問題度 N/10 - 理由`の形式で投稿される(`JUDGE_ALERT_THRESHOLD`以上は⚠️)
- 直前の3発話を文脈としてLM Studioに渡す。LM Studio側のモデルは、ロード済みのものが使われる

### `/judge_stop`
- 採点のみを終了する(文字起こしは継続)。`/transcribe_stop`、`/stop`、VC切断による自動終了でも止まる

## 文字起こしの設定
Apple Siliconのmacをネイティブで動かす場合は、`pip install mlx-whisper`で`mlx`が使われ、`openai`より速い(M4で`turbo`が1発話約0.9秒、`openai`のCPUは約2.1秒)。初回は`mlx`用モデルのダウンロード(約1.6GB)が発生する。Docker(Linux)では使えないため`openai`になる。
`.env`で次の値を設定できる(すべて省略可)。

| 変数 | 既定値 | 説明 |
| --- | --- | --- |
| `WHISPER_BACKEND` | `auto` | 推論の実装。`mlx`(Apple Silicon向けmlx-whisper)、`openai`(openai-whisper)、`auto`(mlx-whisperがインストール済みなら`mlx`) |
| `WHISPER_MODEL` | `turbo` | Whisperのモデル名(`small`、`medium`、`large-v3`など)。`mlx`では`mlx-community/`のモデルに自動変換され、`owner/repo`形式でHugging Faceのリポジトリを直接指定もできる |
| `WHISPER_DEVICE` | `cpu` | `openai`のみ有効。推論デバイス(`cpu`、`cuda`、`mps`) |
| `WHISPER_LANGUAGE` | `ja` | 認識する言語 |
| `WHISPER_BEAM_SIZE` | `5` | `openai`のみ有効(`mlx`はビームサーチ未対応で貪欲法)。ビームサーチの幅。`1`にすると速いが短い発話で不安定になりやすい |
| `VAD_RMS_THRESHOLD` | `300` | 発話とみなす音量(int16のRMS)。小声が拾われない場合は下げる |
| `JUDGE_ALERT_THRESHOLD` | `5` | 問題度がこの値以上のとき⚠️で表示する |
