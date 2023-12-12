import json
import requests
from typing import Final, Union

SPEAKER_ID: Final[int] = 1
URL: Final[str] = 'http://127.0.0.1:50021'

def get_sound() -> Union[bytes, None]:
    # クエリの取得
    endpoint: str = f'{URL}/audio_query'
    params = {
        'speaker': SPEAKER_ID,
        'text': 'こんにちは'
    }
    res = requests.post(
        url=endpoint,
        params=params
    )
    query = res.json()
    with open('query.json', mode='w') as fp:
        fp.write(json.dumps(query, indent=4))

    # 音声の取得
    endpoint: str = f'{URL}/synthesis'
    params2 = {
        'speaker': SPEAKER_ID
    }
    res2 = requests.post(
        url=endpoint,
        params=params2,
        json=query
    )
    print(res2)
    if res2.status_code == 200:
        sound_data: Final[bytes] = res2.content
        with open('out.wav', mode='wb') as fp:
            fp.write(sound_data)
        return sound_data
    else:
        print(res2.json())
        return None

if __name__ == '__main__':
    get_sound()
