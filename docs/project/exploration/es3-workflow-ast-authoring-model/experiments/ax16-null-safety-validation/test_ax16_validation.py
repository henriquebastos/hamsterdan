"""AX16 focused tests — absorption semantics, then the validator built on them.

The runtime facts come first and run on Petrus's own `compile_guard`
path: they are the ground truth the validator's securing rules encode.
Then the validator is proven against v1's three demonstrated holes, the
dual Or rule, and finally AX15's real recovery guards.
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from ax11_fragment import _intent
from ax11_predicates import (
    PredicateTypeError,
    holds,
    on,
    validate_null_safety,
)
from ax15_recovery import (
    CONVERSATION_RECOVERABLE,
    DASHBOARD_RECOVERABLE,
    READINESS_RECOVERABLE,
    RECOVERY_INTENT,
)
from ax16_validation import validate_guard
from test_ax15_recovery import parked_conversation

from hamsterdan.contracts.readiness import (
    Authority,
    ConversationPublicationState,
    DashboardPublicationState,
    Intent,
    ReadinessPublicationState,
)

_CPS = on(ConversationPublicationState)
_RECOVERY = _CPS.conversation_recovery


class _GuardHarness:
    """Compile a rendered predicate through Petrus and evaluate it over a
    single ConversationPublicationState token — the exact runtime path."""

    SCOPE: ClassVar[dict[str, str]] = {"ConversationPublicationState": "conversation_publication_state[0].data"}

    @classmethod
    def evaluate(cls, predicate, state: ConversationPublicationState) -> bool:
        from petrus.impetus.binding.cel import compile_guard
        from petrus.impetus.petrinet import Binding, Cel, NetPath, Token

        place = NetPath("conversation_publication_state")
        guard = compile_guard(Cel(predicate.cel(cls.SCOPE)), NetPath("probe"), (place,))
        return guard(
            Binding(
                NetPath("probe"),
                consumed=(),
                read=((place, (Token("ConversationPublicationState", state.dump()),)),),
            )
        )


# -- the ground truth: CEL logic operators are commutative and error-absorbing


class TestAbsorptionSemantics:
    def test_error_and_false_is_false_in_both_orders(self) -> None:
        # The risky read FIRST, the presence check LAST — v1's forbidden
        # order — evaluates fine: when recovery is absent the read errors,
        # present() is false, and commutative && absorbs the error.
        reversed_order = (_RECOVERY.operation == "op-r") & _RECOVERY.present()
        assert _GuardHarness.evaluate(reversed_order, ConversationPublicationState()) is False
        assert _GuardHarness.evaluate(reversed_order, parked_conversation("op-r")) is True
        forward_order = _RECOVERY.present() & (_RECOVERY.operation == "op-r")
        assert _GuardHarness.evaluate(forward_order, ConversationPublicationState()) is False

    def test_error_and_true_raises_the_silent_parking_mode(self) -> None:
        # Nothing absorbs: every other conjunct is true, the read errors,
        # the guard raises, enabledness reads not-satisfied, the token
        # parks with only a diagnostic. This is what the validator exists
        # to prevent.
        import celpy

        unsecured = (_RECOVERY.operation == "op-r") & (_CPS.conversation_capability_blocking == False)
        with pytest.raises(celpy.CELEvalError):
            _GuardHarness.evaluate(unsecured, ConversationPublicationState())

    def test_true_or_error_is_true(self) -> None:
        dual = _RECOVERY.is_null() | (_RECOVERY.operation == "op-r")
        assert _GuardHarness.evaluate(dual, ConversationPublicationState()) is True
        assert _GuardHarness.evaluate(dual, parked_conversation("op-r")) is True
        assert _GuardHarness.evaluate(dual, parked_conversation("other")) is False

    def test_false_or_error_raises(self) -> None:
        import celpy

        unsecured = (_CPS.conversation_capability_blocking == True) | (_RECOVERY.operation == "op-r")
        with pytest.raises(celpy.CELEvalError):
            _GuardHarness.evaluate(unsecured, ConversationPublicationState())


# -- the v1 holes, now closed --------------------------------------------------


class TestClosedHoles:
    def test_nested_access_through_optional_parent_is_refused(self) -> None:
        naked = _RECOVERY.epoch == 3
        validate_null_safety(naked)  # v1 hole: child refs do not inherit parent optionality
        with pytest.raises(PredicateTypeError, match="conversation_recovery"):
            validate_guard(naked, ConversationPublicationState)

    def test_right_hand_optional_reference_is_refused(self) -> None:
        asymmetric = on(Authority).head == _CPS.conversation_operation
        validate_null_safety(asymmetric)  # v1 hole: only the left side is checked
        with pytest.raises(PredicateTypeError, match="conversation_operation"):
            validate_guard(asymmetric, Authority, ConversationPublicationState)

    def test_presence_check_itself_needs_its_prefixes_secured(self) -> None:
        # present(recovery.intent) still SELECTS through recovery to reach
        # the leaf — the check decides the leaf, not the path to it.
        with pytest.raises(PredicateTypeError, match="conversation_recovery"):
            validate_guard(_RECOVERY.intent.present(), ConversationPublicationState)
        validate_guard(_RECOVERY.present() & _RECOVERY.intent.present(), ConversationPublicationState)

    def test_unknown_root_is_named(self) -> None:
        with pytest.raises(PredicateTypeError, match="binds no such root"):
            validate_guard(_RECOVERY.present(), Authority)


# -- securing is a sibling-set property, not a position -------------------------


class TestSiblingSecuring:
    def test_position_is_irrelevant(self) -> None:
        # v1's ordering rule only fires on leaf-optional refs at all (its
        # hole 1 means the nested form is never checked), so the contrast
        # case uses one: v1 demands present() FIRST, v2 accepts any
        # position — the absorption tests above prove the runtime agrees.
        reversed_order = (_CPS.conversation_operation == "op-r") & _CPS.conversation_operation.present()
        with pytest.raises(PredicateTypeError):
            validate_null_safety(reversed_order)
        validate_guard(reversed_order, ConversationPublicationState)
        # The nested variant from TestAbsorptionSemantics validates too.
        validate_guard((_RECOVERY.operation == "op-r") & _RECOVERY.present(), ConversationPublicationState)

    def test_a_distant_conjunct_secures(self) -> None:
        chain = (_CPS.conversation_capability_blocking == True) & (_RECOVERY.operation == "op-r") & _RECOVERY.present()
        validate_guard(chain, ConversationPublicationState)

    def test_securing_is_per_path_not_per_root(self) -> None:
        # present(conversation_recovery) says nothing about the *other*
        # optional field on the same token.
        wrong_path = _RECOVERY.present() & (_CPS.conversation_operation == "op-r")
        with pytest.raises(PredicateTypeError, match="conversation_operation"):
            validate_guard(wrong_path, ConversationPublicationState)
        validate_guard(
            _CPS.conversation_operation.present() & (_CPS.conversation_operation == "op-r"),
            ConversationPublicationState,
        )

    def test_map_keys_are_risk_points(self) -> None:
        with pytest.raises(PredicateTypeError, match="target"):
            validate_guard(_intent.arguments["target"] == "conversation", Intent)
        validate_guard(
            (_intent.arguments["target"] == "conversation") & _intent.arguments["target"].present(),
            Intent,
        )


# -- the dual rule inside an any-of ---------------------------------------------


class TestOrSecuring:
    def test_absence_secures_a_disjunct(self) -> None:
        validate_guard(_RECOVERY.is_null() | (_RECOVERY.operation == "op-r"), ConversationPublicationState)

    def test_presence_has_the_wrong_polarity_for_or(self) -> None:
        # present() is FALSE when the path is absent — false || error is
        # an error, so it secures nothing inside an Or.
        with pytest.raises(PredicateTypeError):
            validate_guard(_RECOVERY.present() | (_RECOVERY.operation == "op-r"), ConversationPublicationState)

    def test_an_unrelated_disjunct_does_not_secure(self) -> None:
        with pytest.raises(PredicateTypeError):
            validate_guard(
                (_CPS.conversation_capability_blocking == True) | (_RECOVERY.operation == "op-r"),
                ConversationPublicationState,
            )


# -- the real AX15 guards validate clean; the broken variant is caught ----------


class TestRealGuards:
    def test_recovery_intent_prelude_validates(self) -> None:
        validate_guard(RECOVERY_INTENT, Authority, Intent)

    def test_all_three_recovery_predicates_validate(self) -> None:
        validate_guard(CONVERSATION_RECOVERABLE, Authority, Intent, ConversationPublicationState)
        validate_guard(DASHBOARD_RECOVERABLE, Authority, Intent, DashboardPublicationState)
        validate_guard(READINESS_RECOVERABLE, Authority, Intent, ReadinessPublicationState)

    def test_dropping_the_presence_conjunct_is_caught(self) -> None:
        broken = (
            RECOVERY_INTENT
            & (_intent.arguments["target"] == "conversation")
            & (_CPS.conversation_capability_blocking == True)
            # recovery.present() deliberately omitted
            & (_RECOVERY.epoch == 3)
        )
        with pytest.raises(PredicateTypeError, match="conversation_recovery"):
            validate_guard(broken, Authority, Intent, ConversationPublicationState)

    def test_the_error_says_how_to_fix_it(self) -> None:
        with pytest.raises(PredicateTypeError, match=r"conversation_recovery\.present\(\)"):
            validate_guard(_RECOVERY.epoch == 3, ConversationPublicationState)


# -- the second finding: the two evaluators disagree on optional leaves ----------


class TestEvaluatorDivergence:
    def test_celpy_equality_on_a_null_leaf_is_total(self) -> None:
        # `null == "op"` is false in celpy — no error. The refusal of
        # unguarded optional-leaf equality is therefore conservative for
        # CEL guards...
        unguarded = _CPS.conversation_operation == "op-r"
        assert _GuardHarness.evaluate(unguarded, ConversationPublicationState()) is False

    def test_holds_crashes_on_the_same_predicate(self) -> None:
        # ...but `holds()` — the Python evaluator the compiler uses for
        # scatter-lane routing — CRASHES on the identical predicate and
        # data, and not even with its own domain error: it distinguishes
        # a missing map key (_MISSING → PredicateEvaluationError) from a
        # present-but-None field, and its comparison table evaluates all
        # six operators eagerly, so `None > str` raises a raw TypeError
        # before `==` is ever looked up. Until the evaluators agree,
        # relaxing the validator would make a predicate's legality depend
        # on where the compiler happens to place it.
        with pytest.raises(TypeError, match="not supported"):
            holds(
                _CPS.conversation_operation == "op-r",
                {"ConversationPublicationState": ConversationPublicationState()},
            )
