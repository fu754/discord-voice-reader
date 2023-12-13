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