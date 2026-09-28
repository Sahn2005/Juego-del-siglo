import pytest
from src.player import Player
from src.ball import Ball

def test_player_initialization():
    p = Player("Juan")
    assert p.name == "Juan"
    assert p.score == 0
    assert len(p.hand) == 0
    assert not p.is_ai

def test_player_add_ball():
    p = Player("Maria")
    p.add_ball(Ball(10))
    p.add_ball(Ball(25))
    
    assert p.score == 35
    assert len(p.hand) == 2
    assert p.hand[0].value == 10
    assert p.hand[1].value == 25

def test_player_reset():
    p = Player("Luis")
    p.add_ball(Ball(90))
    p.status = "ME_QUEDO"
    
    p.reset_round()
    
    assert p.score == 0
    assert len(p.hand) == 0
    assert p.status == "WAITING"
