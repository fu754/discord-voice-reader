# Discordテキストチャット読み上げbot
## クレジット
- [VOICEVOX ENGINE](https://github.com/VOICEVOX/voicevox_engine)

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