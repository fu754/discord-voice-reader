from enum import Enum, auto

class Rank(Enum):
    Iron1:      1
    Iron2:      2
    Iron3:      3
    Bronze1:    4
    Bronze2:    5
    Bronze3:    6
    Silver1:    7
    Silver2:    8
    Silver3:    9
    Gold1:      10
    Gold2:      11
    Gold3:      12
    Platinum1:  13
    Platinum2:  14
    Platinum3:  15
    Diamond1:   16
    Diamond2:   17
    Diamond3:   18
    Ascendant1: 19
    Ascendant2: 20
    Ascendant3: 21
    Immortal1:  22
    Immortal2:  23
    Immortal3:  24
    Radiant:    25

class Member():
    name: str
    rank: Rank

    def __init__(self, name: str, rank: Rank) -> None:
        self.name = name
        self.rank = rank

class TeamMember(Member):
    is_leader: bool

    def __init__(self, is_leader: bool, member: Member) -> None:
        self.is_leader = is_leader
        super().__init__(member)

class Team():
    attacker: list[Member]
    defender: list[Member]

    def __init__(self, attacker: list[Member], defender: list[Member]) -> None:
        self.attacker = attacker
        self.defender = defender

