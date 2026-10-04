import pytest

from helpers import fixed_deck
from src.match import Match, MatchError
from src.protocol import PHASE_LOBBY, PHASE_PLAYING, PHASE_ROUND_END


def make_match(*values, **kwargs):
    return Match(deck_factory=fixed_deck(*values), **kwargs)


def sit(match, *names):
    return [match.join(n) for n in names]


def status(match, seat_id):
    return match._find(seat_id).player.status


# ---------------------------------------------------------------- entrar / salir

def test_first_player_is_host_and_names_are_unique():
    m = Match()
    a, b, c = sit(m, "Ana", "ana", "  Ana  ")
    assert m.host_id == a
    names = [s.player.name for s in m.seats]
    assert names == ["Ana", "ana 2", "Ana 3"]


def test_name_is_cleaned_and_truncated():
    m = Match()
    m.join("  Nombre   larguisimo\n\t")
    assert m.seats[0].player.name == "Nombre lar"
    m.join("")
    m.join(None)
    assert m.seats[1].player.name == "Jugador"
    assert m.seats[2].player.name == "Jugador 2"


def test_table_full():
    m = Match(max_players=2)
    sit(m, "A", "B")
    with pytest.raises(MatchError, match="llena"):
        m.join("C")


def test_cannot_join_during_a_round():
    m = make_match(1, 2, 3, 4)
    a, b = sit(m, "A", "B")
    m.start_round(a)
    with pytest.raises(MatchError, match="en curso"):
        m.join("C")


def test_leaving_lobby_frees_seat_and_moves_host():
    m = Match()
    a, b, c = sit(m, "A", "B", "C")
    m.leave(a)
    assert [s.id for s in m.seats] == [b, c]
    assert m.host_id == b


def test_everyone_leaves_resets_table():
    m = make_match(1, 2, 3, 4)
    a, b = sit(m, "A", "B")
    m.start_round(a)
    m.leave(a)
    m.leave(b)
    assert m.seats == []
    assert m.phase == PHASE_LOBBY
    assert m.host_id is None
    assert m.round_number == 0


# ---------------------------------------------------------------- iniciar ronda

def test_only_host_can_start_and_needs_two_players():
    m = make_match(1, 2, 3, 4)
    a, b = sit(m, "A", "B")
    with pytest.raises(MatchError, match="anfitrión"):
        m.start_round(b)

    solo = make_match(1, 2)
    (only,) = sit(solo, "Solo")
    with pytest.raises(MatchError, match="al menos"):
        solo.start_round(only)


def test_start_deals_one_vira_each_and_first_player_starts():
    m = make_match(10, 20, 30)
    a, b, c = sit(m, "A", "B", "C")
    m.start_round(a)
    assert m.phase == PHASE_PLAYING
    assert [s.player.score for s in m.seats] == [10, 20, 30]
    assert all(s.player.status == "PLAYING" for s in m.seats)
    assert m.current_seat().id == a
    assert m.deadline is not None


def test_cannot_start_while_playing():
    m = make_match(1, 2)
    a, b = sit(m, "A", "B")
    m.start_round(a)
    with pytest.raises(MatchError, match="en curso"):
        m.start_round(a)


# ---------------------------------------------------------------- turnos

def test_only_current_player_can_stay():
    m = make_match(10, 20, 5)
    a, b = sit(m, "A", "B")
    m.start_round(a)
    with pytest.raises(MatchError, match="turno"):
        m.stay(b)


def test_only_host_can_draw():
    m = make_match(10, 20, 5)
    a, b = sit(m, "A", "B")
    m.start_round(a)
    # A es el anfitrión/repartidor; B no puede repartir aunque sea su propio turno más tarde.
    with pytest.raises(MatchError, match="repartidor"):
        m.draw(b)
    m.stay(a)
    assert m.current_seat().id == b
    with pytest.raises(MatchError, match="repartidor"):
        m.draw(b)
    m.draw(a)  # el anfitrión reparte aunque el turno sea de B


def test_actions_need_a_running_round():
    m = Match()
    a, b = sit(m, "A", "B")
    with pytest.raises(MatchError, match="ronda"):
        m.draw(a)


def test_player_keeps_turn_while_below_99():
    m = make_match(10, 20, 5, 6)   # viras 10 y 20; luego 5, 6
    a, b = sit(m, "A", "B")
    m.start_round(a)
    m.draw(a)                       # 15
    assert m.current_seat().id == a
    m.draw(a)                       # 21
    assert m.current_seat().id == a
    assert m.seats[0].player.score == 21


def test_stay_passes_turn():
    m = make_match(10, 20)
    a, b = sit(m, "A", "B")
    m.start_round(a)
    m.stay(a)
    assert status(m, a) == "ME_QUEDO"
    assert m.current_seat().id == b


def test_siglo_ends_turn_and_bust_ends_turn():
    # A: vira 50 + 49 = 99 (SIGLO). B: vira 60 + 45 = 105 (ME_FUI).
    # A es el anfitrión/repartidor: reparte en ambos turnos.
    m = make_match(50, 60, 49, 45)
    a, b = sit(m, "A", "B")
    m.start_round(a)
    m.draw(a)
    assert status(m, a) == "SIGLO"
    assert m.current_seat().id == b
    m.draw(a)
    assert status(m, b) == "ME_FUI"


# ---------------------------------------------------------------- fin de ronda

def test_round_ends_and_winner_is_closest_to_100():
    m = make_match(50, 60, 49, 45)
    a, b = sit(m, "A", "B")
    m.start_round(a)
    m.draw(a)   # A reparte para sí mismo: SIGLO 99
    m.draw(a)   # A reparte para B (es su turno): se pasa
    assert m.phase == PHASE_ROUND_END
    assert m.winner_ids == [a]
    assert m.seats[0].wins == 1
    assert m.seats[1].wins == 0
    assert m.current_seat() is None
    assert m.deadline is None


def test_tie_gives_a_win_to_everyone_tied():
    m = make_match(40, 40)
    a, b = sit(m, "A", "B")
    m.start_round(a)
    m.stay(a)
    m.stay(b)
    assert m.winner_ids == [a, b]
    assert [s.wins for s in m.seats] == [1, 1]


def test_everyone_busts_no_winners():
    m = make_match(90, 90 - 1, 80, 80 - 1)
    a, b = sit(m, "A", "B")
    m.start_round(a)
    m.draw(a)   # 90 + 80 = 170
    m.draw(a)   # 89 + 79 = 168 (A reparte para B)
    assert m.phase == PHASE_ROUND_END
    assert m.winner_ids == []


def test_new_round_resets_hands_keeps_wins_and_rotates_starter():
    m = make_match(40, 30, 40, 30, 5, 6, 7, 8)
    a, b = sit(m, "A", "B")
    m.start_round(a)
    assert m.current_seat().id == a
    m.stay(a)
    m.stay(b)
    assert m.winner_ids == [a]

    m.start_round(a)
    assert m.round_number == 2
    assert m.current_seat().id == b            # ahora sale B
    assert [s.player.score for s in m.seats] == [40, 30]  # mazo nuevo, manos nuevas
    assert m.seats[0].wins == 1                # las victorias se conservan
    assert m.winner_ids == []


# ---------------------------------------------------------------- tiempo

def test_timeout_makes_current_player_stay():
    clock = [0.0]
    m = make_match(10, 20, turn_seconds=30, clock=lambda: clock[0])
    a, b = sit(m, "A", "B")
    m.start_round(a)
    seq = m.turn_seq
    clock[0] = 31
    assert m.timeout(seq) is True
    assert status(m, a) == "ME_QUEDO"
    assert m.current_seat().id == b


def test_stale_timeout_is_ignored():
    m = make_match(10, 20, 5)
    a, b = sit(m, "A", "B")
    m.start_round(a)
    old_seq = m.turn_seq
    m.draw(a)                      # A actuó a tiempo: nueva ventana de decisión
    assert m.turn_seq != old_seq
    assert m.timeout(old_seq) is False
    assert status(m, a) == "PLAYING"


def test_snapshot_reports_time_left():
    clock = [100.0]
    m = make_match(10, 20, turn_seconds=30, clock=lambda: clock[0])
    a, b = sit(m, "A", "B")
    m.start_round(a)
    clock[0] = 110
    assert m.snapshot()["time_left"] == 20.0


# ---------------------------------------------------------------- desconexiones

def test_current_player_disconnects_turn_moves_on():
    m = make_match(10, 20, 30, 1)
    a, b, c = sit(m, "A", "B", "C")
    m.start_round(a)
    m.leave(a)
    assert status(m, a) == "ME_QUEDO"
    assert m._find(a).connected is False
    assert m.current_seat().id == b
    assert m.host_id == b            # el anfitrión se transfiere


def test_waiting_player_disconnects_does_not_change_turn():
    m = make_match(10, 20, 30)
    a, b, c = sit(m, "A", "B", "C")
    m.start_round(a)
    m.leave(c)
    assert m.current_seat().id == a
    assert status(m, c) == "ME_QUEDO"


def test_last_active_player_disconnecting_ends_round():
    m = make_match(10, 20)
    a, b = sit(m, "A", "B")
    m.start_round(a)
    m.stay(a)
    m.leave(b)                       # B era el único que seguía jugando
    assert m.phase == PHASE_ROUND_END
    assert m.winner_ids == [b]       # 20 > 10; su asiento sigue en el resultado


def test_disconnected_seat_is_purged_on_next_round():
    m = make_match(10, 20, 30, 40, 5, 6)
    a, b, c = sit(m, "A", "B", "C")
    m.start_round(a)
    m.leave(c)
    m.stay(a)
    m.stay(b)
    assert m.phase == PHASE_ROUND_END
    m.start_round(a)
    assert [s.id for s in m.seats] == [a, b]


def test_next_round_with_only_one_player_goes_back_to_lobby():
    m = make_match(10, 20)
    a, b = sit(m, "A", "B")
    m.start_round(a)
    m.stay(a)
    m.leave(b)
    assert m.phase == PHASE_ROUND_END
    with pytest.raises(MatchError, match="al menos"):
        m.start_round(a)
    assert m.phase == PHASE_LOBBY


def test_join_after_round_when_full_reuses_disconnected_seat():
    m = make_match(10, 20, 30, 40, max_players=2)
    a, b = sit(m, "A", "B")
    m.start_round(a)
    m.leave(b)
    m.stay(a)
    assert m.phase == PHASE_ROUND_END
    m.join("Nuevo")                  # no lanza "mesa llena"
    assert [s.player.name for s in m.seats] == ["A", "Nuevo"]


# ---------------------------------------------------------------- snapshot

def test_snapshot_shape():
    m = make_match(10, 20)
    a, b = sit(m, "A", "B")
    m.start_round(a)
    snap = m.snapshot()
    assert snap["type"] == "state"
    assert snap["phase"] == PHASE_PLAYING
    assert snap["turn_id"] == a
    assert snap["host_id"] == a
    assert snap["players"][0] == {
        "id": a, "name": "A", "score": 10, "status": "PLAYING",
        "balls": [10], "hidden": False, "wins": 0, "connected": True,
    }


def test_snapshot_without_viewer_is_fully_visible_for_everyone():
    """Compatibilidad hacia atrás: sin viewer_id, nadie se oculta."""
    m = make_match(10, 20)
    a, b = sit(m, "A", "B")
    m.start_round(a)
    snap = m.snapshot()
    for p in snap["players"]:
        assert p["hidden"] is False
        assert p["score"] is not None


def test_snapshot_hides_opponents_while_playing():
    m = make_match(10, 20)
    a, b = sit(m, "A", "B")
    m.start_round(a)

    # A ve su propia mano completa, pero no la de B.
    snap_a = m.snapshot(viewer_id=a)
    me = next(p for p in snap_a["players"] if p["id"] == a)
    opp = next(p for p in snap_a["players"] if p["id"] == b)
    assert me["hidden"] is False
    assert me["score"] == 10
    assert me["balls"] == [10]
    assert opp["hidden"] is True
    assert opp["score"] is None
    assert opp["balls"] == []
    assert opp["status"] == "PLAYING"
    # wins/connected nunca se ocultan
    assert opp["wins"] == 0
    assert opp["connected"] is True

    # B, simétricamente, no ve la mano de A.
    snap_b = m.snapshot(viewer_id=b)
    opp_from_b = next(p for p in snap_b["players"] if p["id"] == a)
    assert opp_from_b["hidden"] is True
    assert opp_from_b["score"] is None


def test_snapshot_hides_me_quedo_but_reveals_me_fui():
    # A: vira 50 + 49 = 99 (SIGLO, mostrado como ME_QUEDO a los demás).
    # B: vira 60 + 45 = 105 (ME_FUI, siempre visible).
    m = make_match(50, 60, 49, 45)
    a, b = sit(m, "A", "B")
    m.start_round(a)
    m.draw(a)   # A: SIGLO
    m.draw(a)   # B: ME_FUI

    snap = m.snapshot(viewer_id=a)
    siglo_seat = next(p for p in snap["players"] if p["id"] == a)
    busted_seat = next(p for p in snap["players"] if p["id"] == b)
    # A es el viewer: su propia tarjeta siempre es visible, aunque tenga SIGLO.
    assert siglo_seat["hidden"] is False
    assert siglo_seat["status"] == "SIGLO"
    # B se pasó: se revela aunque A no sea B.
    assert busted_seat["hidden"] is False
    assert busted_seat["status"] == "ME_FUI"
    assert busted_seat["score"] == 105


def test_snapshot_fully_visible_at_round_end():
    m = make_match(40, 40)
    a, b = sit(m, "A", "B")
    m.start_round(a)
    m.stay(a)
    m.stay(b)
    assert m.phase == PHASE_ROUND_END

    snap = m.snapshot(viewer_id=a)
    for p in snap["players"]:
        assert p["hidden"] is False
        assert p["score"] is not None
