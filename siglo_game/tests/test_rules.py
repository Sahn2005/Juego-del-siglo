import pytest
from src.player import Player
from src.ball import Ball
from src.rules import Rules

def test_rules_evaluate_status():
    p1 = Player("P1")
    p1.add_ball(Ball(50))
    p1.add_ball(Ball(49))
    Rules.evaluate_player_status(p1)
    assert p1.status == "SIGLO"
    
    p2 = Player("P2")
    p2.add_ball(Ball(101))
    Rules.evaluate_player_status(p2)
    assert p2.status == "ME_FUI"
    
    p3 = Player("P3")
    p3.add_ball(Ball(50))
    Rules.evaluate_player_status(p3)
    assert p3.status == "WAITING"

def test_determine_winners():
    p1 = Player("P1")
    p1.score = 90
    p1.status = "ME_QUEDO"
    
    p2 = Player("P2")
    p2.score = 95
    p2.status = "ME_QUEDO"
    
    p3 = Player("P3")
    p3.score = 105
    p3.status = "ME_FUI"
    
    winners = Rules.determine_round_winners([p1, p2, p3])
    assert len(winners) == 1
    assert winners[0] == p2
    
def test_determine_winners_tie():
    p1 = Player("P1")
    p1.score = 95
    p1.status = "ME_QUEDO"
    
    p2 = Player("P2")
    p2.score = 95
    p2.status = "ME_QUEDO"
    
    winners = Rules.determine_round_winners([p1, p2])
    assert len(winners) == 2
    assert p1 in winners
    assert p2 in winners
