import json
from typedef.Valorant import Member, Team, Rank
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
        __member_list = json.load(fp)
    member_list = []
    for member in __member_list['members']:
        name = member['name']
        rank = member['rank']

        m = Member(
            name=name,
            rank=Rank[rank]
        )
        member_list.append(m)
    return member_list

def assign_team(member_list: list[Member]) -> Team:
    return {}


if __name__ == '__main__':
    member_list: list[Member] = load_team_member_json()
    for m in member_list:
        print(m.__dict__)