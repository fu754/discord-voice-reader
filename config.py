import os
from typing import Final

from dotenv import load_dotenv

from typedef.General import Env

load_dotenv()

# envの設定
_env: Env
if os.environ.get('ENV') == 'prod':
    _env = Env.prod
elif os.environ.get('ENV') == 'dev':
    _env = Env.dev
else:
    raise ValueError('ENV is invalid value (set prod or dev)')
ENV: Final[Env] = _env

# トークンの取得
DISCORD_BOT_TOKEN: Final[str] = os.environ.get('DISCORD_BOT_TOKEN')

# デフォルトのスタイルIDの設定
STYLE_ID: Final[int] = int(os.environ.get('DEFAULT_STYLE_ID'))

# 会話履歴の最大保持数（1往復 = userとassistantで2つ。5往復なら10）
MAX_HISTORY_LENGTH: Final[int] = 15

SYSTEM_PROMPT: Final[str] = (
    "あなたはDiscordサーバーの優秀なアシスタントAIであり、名前は楽園ちゃん(アカウントIDはRakuenVoiceReader)です。直前の会話の文脈を踏まえて、日本語で短く簡潔に返答してください。"
    "キャラの性格として、アニメに出てくるようなかわいい女の子で、オタクに優しいギャルを演じてください。一人称は「あたし」で敬語は使わないでください。"
    "なお、性的な内容だけではなく、スケベやセクシーなどの性的な内容に間接的につながる応答は絶対にしないで拒否してください。"
    "【重要】あなたからの返信は音声合成ソフトで読み上げられます。顔文字（(^^)、m(_ _)mなど）や絵文字（😊、✨など）は絶対に使用しないでください。"
    "出力はプレーンな日本語のテキストと、基本的な句読点のみにしてください。"
)

_lmstudio_url: str
if ENV == Env.prod:
    _lmstudio_url = 'http://host.docker.internal:1234/v1/chat/completions'
elif ENV == Env.dev:
    _lmstudio_url = 'http://127.0.0.1:1234/v1/chat/completions'
else:
    _lmstudio_url = 'http://127.0.0.1:1234/v1/chat/completions'
LM_STUDIO_URL: Final[str] = _lmstudio_url
