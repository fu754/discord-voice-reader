import asyncio
import json
import aiohttp
from typing import Final
import os
from enum import Enum, auto
from dotenv import load_dotenv
load_dotenv()

class Env(Enum):
    dev = auto()
    prod = auto()

_env: Env
if os.environ.get('ENV') == 'prod':
    _env = Env.prod
elif os.environ.get('ENV') == 'dev':
    _env = Env.prod
else:
    raise ValueError('ENV is invalid value (set prod or dev)')
ENV: Final[Env] = _env

SPEAKER_ID: Final[int] = 8 # 春日部つむぎ
_url: str
if ENV == Env.prod:
    _url = 'http://voicevox:50021'
elif Env == Env.dev:
    _url = 'http://127.0.0.1:50021'
else:
    _url = 'http://127.0.0.1:50021'
URL: Final[str] = _url

CHUNK_SIZE: Final[int] = 10

async def create_wav_sound(text: str) -> bool:
    # クエリの取得
    endpoint: str = f'{URL}/audio_query'
    params = {
        'style_id': SPEAKER_ID,
        'text': text
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url=endpoint, params=params) as r:
            query = await r.json()
    with open('query.json', mode='w', encoding='utf_8_sig') as fp:
        fp.write(json.dumps(query, indent=4))

    # 音声の取得
    endpoint: str = f'{URL}/synthesis'
    params2 = {
        'style_id': SPEAKER_ID
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url=endpoint, params=params2, json=query) as r:
            if r.status == 200:
                with open('out.wav', mode='wb') as fp:
                    while(True):
                        chunk = await r.content.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        fp.write(chunk)
                return True
            else:
                res = await r.json()
                print(res.json())
                return False

if __name__ == '__main__':
    text: str = "こんにちは"
    asyncio.run(create_wav_sound(text))
