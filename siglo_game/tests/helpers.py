from src.ball import Ball
from src.deck import Deck


def fixed_deck(*values):
    """Mazo que entrega las fichas exactamente en el orden dado (para pruebas)."""
    def factory():
        deck = Deck.__new__(Deck)
        deck.balls = [Ball(v) for v in reversed(values)]  # draw() saca del final
        return deck
    return factory
