import asyncio
import json
import aiohttp
from typing import Final

SPEAKER_ID: Final[int] = 8 # 春日部つむぎ
URL: Final[str] = 'http://127.0.0.1:50021'

CHUNK_SIZE: Final[int] = 10

async def create_wav_sound(text: str) -> bool:
    # クエリの取得
    endpoint: str = f'{URL}/audio_query'
    params = {
        'speaker': SPEAKER_ID,
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
        'speaker': SPEAKER_ID
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
