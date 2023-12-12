- クレジット
    - [VOICEVOX ENGINE](https://github.com/VOICEVOX/voicevox_engine)
- 起動
    ```bash
    docker-compose up -d
    python main.py
    ```

- 環境構築(windows)
    1. Pythonのインストール
        ```powershell
        pyenv local 3.11.6
        python -m venv venv
        .\venv\Scripts\activate
        pip install -r requirements.txt
        ```
    1. `.env`ファイルを作成してDiscordのbotのトークンをセットする
        ```
        DISCORD_BOT_TOKEN=""
        ```