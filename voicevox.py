import asyncio
import json
import aiohttp
from typing import Final, Union
import os
from enum import Enum, auto
from typedef.Speaker import Speaker
from dotenv import load_dotenv
load_dotenv()

class Env(Enum):
    dev = auto()
    prod = auto()

_env: Env
if os.environ.get('ENV') == 'prod':
    _env = Env.prod
elif os.environ.get('ENV') == 'dev':
    _env = Env.dev
else:
    raise ValueError('ENV is invalid value (set prod or dev)')
ENV: Final[Env] = _env

_url: str
if ENV == Env.prod:
    _url = 'http://voicevox:50021'
elif ENV == Env.dev:
    _url = 'http://127.0.0.1:50021'
else:
    _url = 'http://127.0.0.1:50021'
URL: Final[str] = _url

CHUNK_SIZE: Final[int] = 10

async def create_wav_sound(style_id: int, text: str) -> bool:
    """
    voicevox engineのAPIを呼び出して音声を生成する

    Args:
        style_id(int): style_idを指定する
        text(str): 音声生成するテキスト
    Returns:
        bool : 生成に成功したか
    """
    # クエリの取得
    endpoint: str = f'{URL}/audio_query'
    params = {
        'style_id': style_id,
        'text': text
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url=endpoint, params=params) as r:
            if r.status == 200:
                query = await r.json()
            else:
                res = await r.json()
                print(res)
                return False
    # with open('query.json', mode='w', encoding='utf_8_sig') as fp:
    #     fp.write(json.dumps(query, indent=4))

    # 音声の取得
    endpoint: str = f'{URL}/synthesis'
    params2 = {
        'style_id': style_id
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url=endpoint, params=params2, json=query) as r:
            if r.status == 200:
                # 受信したストリームをCHUNK_SIZEごとに書き込んでいく
                with open('out.wav', mode='wb') as fp:
                    while(True):
                        chunk = await r.content.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        fp.write(chunk)
                return True
            else:
                res = await r.json()
                print(res)
                return False

async def get_style_list() -> Union[list[Speaker], None]:
    """
    スタイル一覧を取得する

    Returns:
        list[Speaker]: スタイル一覧
    """
    endpoint: str = f'{URL}/speakers'
    async with aiohttp.ClientSession() as session:
        async with session.get(url=endpoint) as r:
            if r.status == 200:
                res = await r.json()
            else:
                res = await r.json()
                print(res)
                return None
    result: list[Speaker] = (Speaker(**r) for r in res)
    return result

if __name__ == '__main__':
    text: str = "こんにちは"
    # asyncio.run(create_wav_sound(8, text))
    speakers: list[Speaker] = asyncio.run(get_style_list())
