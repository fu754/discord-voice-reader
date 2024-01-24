import json
from typedef.Valorant import Member, Team
from LogController import get_logger
from logging import Logger
from typing import Final

logger: Final[Logger] = get_logger(__name__)

def load_team_member_json() -> list[Member]:
    """
    team_members.jsonを読み込んで返す

    Returns:
        list[Member] : メンバー一覧
    """
    with open('./src/valorant/team_members.json', mode='r', encoding='utf_8_sig') as fp:
        member_list = json.load(fp)
    return member_list

def assign_team(member_list: list[Member]) -> Team:
    return {}
