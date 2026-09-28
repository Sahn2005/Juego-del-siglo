import pytest
from src.deck import Deck

def test_deck_initialization():
    deck = Deck()
    assert deck.count() == 90
    
    # Check uniqueness and range
    values = [ball.value for ball in deck.balls]
    assert len(set(values)) == 90
    assert min(values) == 1
    assert max(values) == 90

def test_deck_draw():
    deck = Deck()
    ball = deck.draw()
    assert ball is not None
    assert deck.count() == 89
    
    # Draw all remaining balls
    for _ in range(89):
        deck.draw()
        
    assert deck.count() == 0
    assert deck.draw() is None
