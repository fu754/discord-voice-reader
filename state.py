"""複数のCogから参照・更新される実行時の状態"""
from collections import deque

from config import STYLE_ID
from speech_judge import SpeechJudge
from voice_transcribe import TranscribeSink

# VOICEVOXのスタイル一覧 { style_id : 表示名 }
STYLE_LIST: dict = {}
# 現在のスタイル。再代入されるため、参照するときは state.current_style_id とモジュール経由で読むこと
current_style_id: int = STYLE_ID

# チャンネルごとの会話履歴を保存する辞書 { channel_id : deque }
chat_histories: dict[int, deque] = {}

# 受信テストの音声はstop実行までメモリに保持し、stop後にWAVとして書き出す { guild_id : ReceiveTestSink }
receive_test_sinks: dict[int, object] = {}
# 文字起こし中のsink { guild_id : TranscribeSink }
transcribe_sinks: dict[int, TranscribeSink] = {}
# サーバーごとの発話判定(LM Studioでの採点) { guild_id : SpeechJudge }
speech_judges: dict[int, SpeechJudge] = {}


def stop_speech_judge(guild_id: int) -> bool:
    """発話判定を止める。実行中だった場合はTrueを返す"""
    judge = speech_judges.pop(guild_id, None)
    sink = transcribe_sinks.get(guild_id)
    if sink is not None:
        sink.on_text = None
    if judge is None:
        return False
    judge.stop()
    return True
