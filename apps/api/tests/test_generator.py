import pytest

from app.services.generator import CategoryIn, GenerationError, RuleIn, TraitIn, generate


def layers():
    categories = [CategoryIn("bg", "Background", 0), CategoryIn("hat", "Hat", 1)]
    traits = [
        TraitIn("red", "bg", "Red", weight=1, exact_count=2),
        TraitIn("blue", "bg", "Blue", weight=1, exact_count=2),
        TraitIn("crown", "hat", "Crown", weight=1, exact_count=2),
        TraitIn("cap", "hat", "Cap", weight=1, exact_count=2),
    ]
    return categories, traits


def test_weighted_is_deterministic_and_unique():
    categories, traits = layers()
    first = generate(categories, traits, [], 4, 7, "weighted")
    second = generate(categories, traits, [], 4, 7, "weighted")
    assert [token.combination_key for token in first.tokens] == [token.combination_key for token in second.tokens]
    assert len({token.combination_key for token in first.tokens}) == 4


def test_supply_above_the_unique_space_is_rejected():
    categories, traits = layers()
    with pytest.raises(GenerationError) as caught:
        generate(categories, traits, [], 5, 1, "weighted")
    assert "unique" in caught.value.message.lower() or "at most" in caught.value.message.lower()


def test_exclusion_is_never_rendered():
    categories, traits = layers()
    result = generate(categories, traits, [RuleIn("exclude", "red", "crown")], 3, 3, "weighted")
    assert len(result.tokens) == 3
    for token in result.tokens:
        chosen = set(token.selection.values())
        assert not ({"red", "crown"} <= chosen)


def test_dependency_is_enforced_for_exact_counts():
    categories = [
        CategoryIn("bg", "Background", 0),
        CategoryIn("hat", "Hat", 1),
        CategoryIn("eyes", "Eyes", 2),
    ]
    traits = [
        TraitIn("red", "bg", "Red", exact_count=2),
        TraitIn("blue", "bg", "Blue", exact_count=2),
        TraitIn("crown", "hat", "Crown", exact_count=2),
        TraitIn("cap", "hat", "Cap", exact_count=2),
        TraitIn("open", "eyes", "Open", exact_count=2),
        TraitIn("shut", "eyes", "Shut", exact_count=2),
    ]
    result = generate(categories, traits, [RuleIn("require", "crown", "blue")], 4, 11, "exact")
    crowns = 0
    for token in result.tokens:
        if token.selection["hat"] == "crown":
            crowns += 1
            assert token.selection["bg"] == "blue"
    assert crowns == 2
    assert len({token.combination_key for token in result.tokens}) == 4


def test_impossible_exact_dependency_explains_why():
    categories = [
        CategoryIn("bg", "Background", 0),
        CategoryIn("hat", "Hat", 1),
        CategoryIn("ex", "Extra", 2),
    ]
    traits = [
        TraitIn("red", "bg", "Red", exact_count=3),
        TraitIn("blue", "bg", "Blue", exact_count=1),
        TraitIn("crown", "hat", "Crown", exact_count=3),
        TraitIn("cap", "hat", "Cap", exact_count=1),
        TraitIn("a", "ex", "A", exact_count=2),
        TraitIn("b", "ex", "B", exact_count=1),
        TraitIn("c", "ex", "C", exact_count=1),
    ]
    with pytest.raises(GenerationError) as caught:
        generate(categories, traits, [RuleIn("require", "crown", "blue")], 4, 1, "exact")
    assert "requires" in caught.value.message
