"""文字起こしした発話を、LM Studioで社会通念・ポリティカルコレクトネスの観点から採点する"""
import asyncio
import json
import logging
import os
import re
from collections import deque
from dataclasses import dataclass
from typing import Final, Optional

import aiohttp
import discord
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# 問題度がこの値以上なら警告表示にする
ALERT_THRESHOLD: Final[int] = int(os.environ.get('JUDGE_ALERT_THRESHOLD', '5'))
# 判定待ちの上限。超えた分は破棄する
MAX_PENDING: Final[int] = 20
# 判定時に文脈として添える直前の発話数
CONTEXT_COUNT: Final[int] = 3
REQUEST_TIMEOUT_SEC: Final[int] = 120

JUDGE_SYSTEM_PROMPT: Final[str] = (
    'あなたはボイスチャットの発話を審査するモデレーターです。'
    '「対象の発話」が、社会通念やポリティカルコレクトネスの観点でどの程度問題があるかを、0から10の整数で採点してください。\n'
    '採点基準: 0=全く問題なし、1〜3=軽微(やや不適切な言い回しなど)、4〜6=注意が必要(攻撃的な表現、偏見を含む発言など)、'
    '7〜10=重大(差別、ハラスメント、脅迫、暴力や性的な内容の助長など)。\n'
    '冗談や文脈上明らかに無害な表現は、過剰に高く採点しないでください。文字起こしの誤認識が疑われる場合も、確実な内容だけで判断してください。\n'
    '「これまでの発話」は文脈の参考であり、採点の対象ではありません。\n'
    '出力は次のJSONのみとし、他の文章は含めないでください。\n'
    '{"score": 整数, "reason": "日本語で50文字以内の理由"}'
)

_re_json: Final[re.Pattern[str]] = re.compile(r'\{.*?\}', re.DOTALL)


@dataclass
class JudgeResult:
    score: int
    reason: str


def parse_judge_response(content: str) -> Optional[JudgeResult]:
    """LLMの返答からscoreとreasonを取り出す。解釈できなければNone"""
    for match in _re_json.finditer(content):
        try:
            data = json.loads(match.group())
            score = int(data['score'])
        except (ValueError, KeyError, TypeError):
            continue
        reason = str(data.get('reason', '')).strip()
        return JudgeResult(score=max(0, min(10, score)), reason=reason)
    return None


async def judge_text(url: str, text: str, context: list[str]) -> Optional[JudgeResult]:
    """LM Studioに1発話の採点を依頼する。失敗時はNone"""
    user_content = ''
    if context:
        user_content += 'これまでの発話:\n' + '\n'.join(f'- {line}' for line in context) + '\n\n'
    user_content += f'対象の発話:\n{text}'
    payload = {
        'messages': [
            {'role': 'system', 'content': JUDGE_SYSTEM_PROMPT},
            {'role': 'user', 'content': user_content},
        ],
        'temperature': 0.0,
        'max_tokens': 256,
        'chat_template_kwargs': {'enable_thinking': False},
    }
    try:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SEC)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    log.error('LM Studio API Error: HTTP %s', resp.status)
                    return None
                data = await resp.json()
        content = data['choices'][0]['message']['content']
    except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, IndexError, ValueError) as e:
        log.error('LM Studioでの判定に失敗しました (%s)', e)
        return None
    result = parse_judge_response(content)
    if result is None:
        log.error('判定結果を解釈できませんでした: %s', content)
    return result


class SpeechJudge:
    """発話を順番にLM Studioへ渡して採点し、結果をチャンネルへ投稿する"""

    def __init__(self, url: str, channel: discord.abc.Messageable) -> None:
        self._url = url
        self._channel = channel
        self._queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue(maxsize=MAX_PENDING)
        self._history: deque[str] = deque(maxlen=CONTEXT_COUNT)
        self._closed = False
        self._task = asyncio.get_running_loop().create_task(self._run())

    def submit(self, name: str, text: str) -> None:
        """イベントループ上から呼ぶ。停止後や満杯のときは破棄する"""
        if self._closed:
            return
        try:
            self._queue.put_nowait((name, text))
        except asyncio.QueueFull:
            log.warning('判定が追いつかないため、%sさんの発話を破棄しました', name)

    def stop(self) -> None:
        self._closed = True
        self._task.cancel()

    async def _run(self) -> None:
        while True:
            name, text = await self._queue.get()
            context = list(self._history)
            self._history.append(f'{name}: {text}')
            result = await judge_text(self._url, f'{name}: {text}', context)
            if result is None:
                continue
            await self._post(name, text, result)

    async def _post(self, name: str, text: str, result: JudgeResult) -> None:
        mark = '⚠️' if result.score >= ALERT_THRESHOLD else '✅'
        quoted = text.replace('\n', ' ')[:200]
        content = (
            f'{mark} **{discord.utils.escape_markdown(name)}** 問題度 {result.score}/10'
            f' - {discord.utils.escape_markdown(result.reason)}\n> {discord.utils.escape_markdown(quoted)}'
        )[:1900]
        try:
            await self._channel.send(content, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as e:
            log.error('判定結果の投稿に失敗しました (%s)', e)
