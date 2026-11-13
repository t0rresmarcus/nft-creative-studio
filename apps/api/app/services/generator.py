"""Deterministic NFT combination generator.

The generator refuses invalid combinations. Exclusion and dependency rules are
applied while tokens are built, then checked again before a token is kept.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


class GenerationError(Exception):
    def __init__(self, message: str, suggestions: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.suggestions = suggestions or []


@dataclass(frozen=True)
class CategoryIn:
    id: str
    name: str
    z_index: int
    optional: bool = False
    none_weight: float = 1


@dataclass(frozen=True)
class TraitIn:
    id: str
    category_id: str
    name: str
    weight: float = 1
    exact_count: int | None = None
    always_include: bool = False


@dataclass(frozen=True)
class RuleIn:
    rule_type: str
    trait_a_id: str
    trait_b_id: str


@dataclass
class GeneratedToken:
    token_id: int
    selection: dict[str, str | None]
    combination_key: str


@dataclass
class PlanResult:
    tokens: list[GeneratedToken]
    stats: dict
    attempts: int = 0
    warnings: list[str] = field(default_factory=list)


def combination_key(selection: dict[str, str | None]) -> str:
    parts = [f"{category_id}:{trait_id}" for category_id, trait_id in sorted(selection.items()) if trait_id]
    return "|".join(parts)


def _ordered_categories(categories: list[CategoryIn]) -> list[CategoryIn]:
    return sorted(categories, key=lambda category: (category.z_index, category.id))


def _traits_for(category_id: str, traits: list[TraitIn]) -> list[TraitIn]:
    return sorted(
        [trait for trait in traits if trait.category_id == category_id],
        key=lambda trait: (trait.name.lower(), trait.id),
    )


def _trait_category_map(traits: list[TraitIn]) -> dict[str, str]:
    return {trait.id: trait.category_id for trait in traits}


def selection_violations(
    selection: dict[str, str | None],
    rules: list[RuleIn],
    trait_category: dict[str, str],
    *,
    partial: bool = False,
) -> list[str]:
    present = {trait_id for trait_id in selection.values() if trait_id}
    assigned = set(selection)
    messages: list[str] = []
    for rule in rules:
        category_a = trait_category.get(rule.trait_a_id)
        category_b = trait_category.get(rule.trait_b_id)
        if category_a is None or category_b is None:
            continue
        if partial and not ({category_a, category_b} <= assigned):
            continue
        a_on = rule.trait_a_id in present
        b_on = rule.trait_b_id in present
        if rule.rule_type == "exclude" and a_on and b_on:
            messages.append("Those traits are marked incompatible")
        elif rule.rule_type == "require" and a_on and not b_on:
            messages.append("A required companion trait is missing")
    return messages


def _valid(selection: dict[str, str | None], rules: list[RuleIn], trait_category: dict[str, str]) -> bool:
    return not selection_violations(selection, rules, trait_category, partial=False)


def allocate_counts(weights: list[float], supply: int) -> list[int]:
    if supply < 0:
        raise GenerationError("Supply cannot be negative")
    if not weights:
        return []
    if supply == 0:
        return [0 for _ in weights]
    safe = [max(weight, 0) for weight in weights]
    total = sum(safe)
    if total <= 0:
        safe = [1.0 for _ in weights]
        total = float(len(weights))
    raw = [weight / total * supply for weight in safe]
    counts = [int(math.floor(value)) for value in raw]
    remainder = supply - sum(counts)
    order = sorted(range(len(raw)), key=lambda index: (raw[index] - counts[index], safe[index]), reverse=True)
    for index in range(remainder):
        counts[order[index % len(order)]] += 1
    return counts


def _upper_bound(categories: list[CategoryIn], traits: list[TraitIn]) -> int | None:
    product = 1
    for category in categories:
        options = len(_traits_for(category.id, traits)) + (1 if category.optional else 0)
        product *= max(options, 1)
        if product > 250_000:
            return None
    return product


def count_valid_space(
    categories: list[CategoryIn],
    traits: list[TraitIn],
    rules: list[RuleIn],
    cap: int = 20_000,
) -> int | None:
    categories = _ordered_categories(categories)
    bound = _upper_bound(categories, traits)
    if bound is None or bound > cap:
        return None
    trait_category = _trait_category_map(traits)
    grouped = {category.id: _traits_for(category.id, traits) for category in categories}
    found = 0

    def walk(index: int, selection: dict[str, str | None]) -> None:
        nonlocal found
        if found > cap:
            return
        if index == len(categories):
            if _valid(selection, rules, trait_category):
                found += 1
            return
        category = categories[index]
        options: list[str | None] = [trait.id for trait in grouped[category.id]]
        if category.optional:
            options.append(None)
        for option in options:
            selection[category.id] = option
            if not selection_violations(selection, rules, trait_category, partial=True):
                walk(index + 1, selection)
        selection.pop(category.id, None)

    walk(0, {})
    if found > cap:
        return None
    return found


def _validate_basics(
    categories: list[CategoryIn],
    traits: list[TraitIn],
    rules: list[RuleIn],
    supply: int,
) -> None:
    if supply < 1:
        raise GenerationError("Collection supply must be at least 1")
    if not categories:
        raise GenerationError("Add at least one trait category before generating", ["Create a layer such as Background"])
    trait_ids = {trait.id for trait in traits}
    for category in categories:
        group = _traits_for(category.id, traits)
        if not group and not category.optional:
            raise GenerationError(f'Layer "{category.name}" has no traits', [f"Upload artwork for {category.name}"])
        includes = [trait for trait in group if trait.always_include]
        if len(includes) > 1:
            raise GenerationError(f'Layer "{category.name}" can only have one always-included trait')
        for trait in group:
            if trait.weight < 0:
                raise GenerationError(f'Weight for "{trait.name}" cannot be negative')
    for rule in rules:
        if rule.rule_type not in {"exclude", "require"}:
            raise GenerationError("Rules must be exclude or require")
        if rule.trait_a_id == rule.trait_b_id:
            raise GenerationError("A trait cannot rule itself")
        if rule.trait_a_id not in trait_ids or rule.trait_b_id not in trait_ids:
            raise GenerationError("A rule points at a trait that no longer exists")
        if _trait_category_map(traits)[rule.trait_a_id] == _trait_category_map(traits)[rule.trait_b_id]:
            raise GenerationError("Rules must connect traits from different layers")


def _resolve_exact_counts(
    categories: list[CategoryIn],
    traits: list[TraitIn],
    supply: int,
) -> dict[str, int]:
    resolved: dict[str, int] = {}
    for category in _ordered_categories(categories):
        group = _traits_for(category.id, traits)
        explicit = [trait.exact_count is not None for trait in group]
        if any(explicit) and not all(explicit):
            raise GenerationError(
                f'Set an exact count on every trait in "{category.name}", or leave them all blank to use weights'
            )
        none_slots = 0
        includes = [trait for trait in group if trait.always_include]
        if includes and not all(explicit):
            counts = [supply if trait.always_include else 0 for trait in group]
            none_slots = 0
        elif all(explicit) and group:
            counts = [int(trait.exact_count or 0) for trait in group]
            if any(count < 0 for count in counts):
                raise GenerationError(f'Exact counts in "{category.name}" cannot be negative')
            total = sum(counts)
            if category.optional:
                if total > supply:
                    raise GenerationError(
                        f'Exact counts in optional layer "{category.name}" add up to {total}, which is more than the supply of {supply}'
                    )
                none_slots = supply - total
            elif total != supply:
                raise GenerationError(
                    f'Exact counts in "{category.name}" add up to {total}. They must add up to the supply of {supply}',
                    ["Match the layer total to the collection size, or clear exact counts and use weights"],
                )
        else:
            weights = [trait.weight for trait in group]
            buckets = list(weights)
            if category.optional:
                buckets.append(max(category.none_weight, 0))
            allocated = allocate_counts(buckets, supply)
            counts = allocated[: len(group)]
            none_slots = allocated[-1] if category.optional else 0
        for trait, count in zip(group, counts):
            if trait.always_include and count != supply:
                raise GenerationError(
                    f'"{trait.name}" is always included, so its count must equal the supply ({supply})'
                )
            resolved[trait.id] = count
        if category.optional:
            resolved[f"none:{category.id}"] = none_slots
        elif not group:
            raise GenerationError(f'Layer "{category.name}" has no traits')
    return resolved


def _check_exact_rules(
    categories: list[CategoryIn],
    traits: list[TraitIn],
    rules: list[RuleIn],
    counts: dict[str, int],
    supply: int,
) -> None:
    trait_map = {trait.id: trait for trait in traits}
    for rule in rules:
        count_a = counts.get(rule.trait_a_id, 0)
        count_b = counts.get(rule.trait_b_id, 0)
        name_a = trait_map[rule.trait_a_id].name
        name_b = trait_map[rule.trait_b_id].name
        if rule.rule_type == "exclude" and count_a + count_b > supply:
            raise GenerationError(
                f'"{name_a}" ({count_a}) and "{name_b}" ({count_b}) cannot both fit without overlapping. Supply is {supply}',
                ["Lower one of those exact counts, or remove the exclusion"],
            )
        if rule.rule_type == "require" and count_a > count_b:
            raise GenerationError(
                f'"{name_a}" requires "{name_b}", but {name_a} is requested {count_a} times and {name_b} only {count_b}',
                [f"Raise the count of {name_b} to at least {count_a}"],
            )


def _check_space(categories: list[CategoryIn], traits: list[TraitIn], rules: list[RuleIn], supply: int) -> int | None:
    space = count_valid_space(categories, traits, rules)
    if space is not None and space < supply:
        raise GenerationError(
            f"Only {space} unique valid combinations exist, which is fewer than the supply of {supply}",
            [f"Lower the supply to {space} or fewer", "Add traits or relax a rule"],
        )
    upper = _upper_bound(categories, traits)
    if upper is not None and upper < supply:
        raise GenerationError(
            f"The layers can produce at most {upper} combinations",
            [f"Lower the supply to {upper} or fewer", "Add another trait"],
        )
    return space


def _weighted_tokens(
    categories: list[CategoryIn],
    traits: list[TraitIn],
    rules: list[RuleIn],
    supply: int,
    seed: int,
) -> tuple[list[dict[str, str | None]], int]:
    rng = random.Random(seed)
    categories = _ordered_categories(categories)
    trait_category = _trait_category_map(traits)
    grouped = {category.id: _traits_for(category.id, traits) for category in categories}
    seen: set[str] = set()
    tokens: list[dict[str, str | None]] = []
    attempts = 0
    limit = max(supply * 200, 500)
    while len(tokens) < supply and attempts < limit:
        attempts += 1
        selection: dict[str, str | None] = {}
        failed = False
        for category in categories:
            options = []
            for trait in grouped[category.id]:
                trial = dict(selection)
                trial[category.id] = trait.id
                if selection_violations(trial, rules, trait_category, partial=True):
                    continue
                options.append(trait)
            forced = [trait for trait in options if trait.always_include]
            if forced:
                options = forced
            elif category.optional:
                trial = dict(selection)
                trial[category.id] = None
                if not selection_violations(trial, rules, trait_category, partial=True):
                    options.append(None)  # type: ignore[arg-type]
            if not options:
                failed = True
                break
            weights = []
            for option in options:
                if option is None:
                    weights.append(max(category.none_weight, 0.0001))
                else:
                    weights.append(max(option.weight, 0.0001))
            choice = rng.choices(options, weights=weights, k=1)[0]
            selection[category.id] = None if choice is None else choice.id
        if failed or not _valid(selection, rules, trait_category):
            continue
        key = combination_key(selection)
        if not key or key in seen:
            continue
        seen.add(key)
        tokens.append(selection)
    if len(tokens) < supply:
        raise GenerationError(
            f"Could only build {len(tokens)} unique valid tokens after {attempts} attempts",
            ["Lower the supply", "Add traits", "Relax exclusion rules", "Try a different seed"],
        )
    return tokens, attempts


def _repair(tokens: list[dict[str, str | None]], rules: list[RuleIn], trait_category: dict[str, str]) -> None:
    category_ids = list(tokens[0].keys()) if tokens else []
    for _ in range(80):
        broken = [index for index, token in enumerate(tokens) if not _valid(token, rules, trait_category)]
        if not broken:
            return
        progressed = False
        for index in broken:
            problems = selection_violations(tokens[index], rules, trait_category)
            if not problems:
                continue
            involved: set[str] = set()
            present = {trait_id for trait_id in tokens[index].values() if trait_id}
            for rule in rules:
                if rule.trait_a_id in present or rule.trait_b_id in present:
                    if rule.rule_type == "exclude" and rule.trait_a_id in present and rule.trait_b_id in present:
                        involved.update([rule.trait_a_id, rule.trait_b_id])
                    if rule.rule_type == "require" and rule.trait_a_id in present and rule.trait_b_id not in present:
                        involved.update([rule.trait_a_id, rule.trait_b_id])
            categories_to_try = []
            for trait_id in involved:
                category_id = trait_category.get(trait_id)
                if category_id and category_id not in categories_to_try:
                    categories_to_try.append(category_id)
            if not categories_to_try:
                categories_to_try = list(category_ids)
            swapped = False
            for category_id in categories_to_try:
                for other in range(len(tokens)):
                    if other == index:
                        continue
                    left = dict(tokens[index])
                    right = dict(tokens[other])
                    left[category_id], right[category_id] = right[category_id], left[category_id]
                    if _valid(left, rules, trait_category) and _valid(right, rules, trait_category):
                        tokens[index] = left
                        tokens[other] = right
                        swapped = True
                        progressed = True
                        break
                if swapped:
                    break
            if progressed:
                break
        if not progressed:
            break
    if any(not _valid(token, rules, trait_category) for token in tokens):
        raise GenerationError(
            "Exact counts cannot satisfy the compatibility rules",
            ["Adjust exact counts", "Remove a conflicting rule"],
        )


def _break_duplicate_keys(
    tokens: list[dict[str, str | None]],
    rules: list[RuleIn],
    trait_category: dict[str, str],
    rng: random.Random,
) -> None:
    for _ in range(1000):
        keys = [combination_key(token) for token in tokens]
        if len(set(keys)) == len(keys) and all(keys):
            return
        seen: dict[str, int] = {}
        pair: tuple[int, int] | None = None
        for index, key in enumerate(keys):
            if key in seen:
                pair = (seen[key], index)
                break
            seen[key] = index
        if pair is None:
            return
        left_index, right_index = pair
        category_ids = list(tokens[left_index].keys())
        rng.shuffle(category_ids)
        swapped = False
        for category_id in category_ids:
            for other in range(len(tokens)):
                if other == left_index:
                    continue
                if tokens[left_index][category_id] == tokens[other][category_id]:
                    continue
                proposal_left = dict(tokens[left_index])
                proposal_other = dict(tokens[other])
                proposal_left[category_id], proposal_other[category_id] = (
                    proposal_other[category_id],
                    proposal_left[category_id],
                )
                if not (_valid(proposal_left, rules, trait_category) and _valid(proposal_other, rules, trait_category)):
                    continue
                tokens[left_index] = proposal_left
                tokens[other] = proposal_other
                swapped = True
                break
            if swapped:
                break
        if not swapped:
            break
    keys = [combination_key(token) for token in tokens]
    if len(set(keys)) != len(keys) or any(not key for key in keys):
        raise GenerationError(
            "These exact counts force duplicate combinations",
            ["Add another layer or trait", "Lower the supply"],
        )


def _exact_tokens(
    categories: list[CategoryIn],
    traits: list[TraitIn],
    rules: list[RuleIn],
    supply: int,
    seed: int,
    counts: dict[str, int],
) -> list[dict[str, str | None]]:
    rng = random.Random(seed)
    categories = _ordered_categories(categories)
    columns: dict[str, list[str | None]] = {}
    for category in categories:
        group = _traits_for(category.id, traits)
        bag: list[str | None] = []
        for trait in group:
            bag.extend([trait.id] * counts.get(trait.id, 0))
        if category.optional:
            bag.extend([None] * counts.get(f"none:{category.id}", 0))
        if len(bag) != supply:
            raise GenerationError(f'Layer "{category.name}" produced {len(bag)} slots instead of {supply}')
        rng.shuffle(bag)
        columns[category.id] = bag
    tokens = [{category.id: columns[category.id][index] for category in categories} for index in range(supply)]
    trait_category = _trait_category_map(traits)
    _repair(tokens, rules, trait_category)
    _break_duplicate_keys(tokens, rules, trait_category, rng)
    return tokens


def _distribution(
    categories: list[CategoryIn],
    traits: list[TraitIn],
    tokens: list[dict[str, str | None]],
    counts: dict[str, int] | None,
    mode: str,
) -> list[dict]:
    supply = max(len(tokens), 1)
    layers = []
    for category in _ordered_categories(categories):
        group = _traits_for(category.id, traits)
        weight_total = sum(max(trait.weight, 0) for trait in group)
        if category.optional:
            weight_total += max(category.none_weight, 0)
        rows = []
        options: list[tuple[str | None, str, float]] = [
            (trait.id, trait.name, trait.weight) for trait in group
        ]
        if category.optional:
            options.append((None, "None", category.none_weight))
        for trait_id, name, weight in options:
            count = sum(1 for token in tokens if token.get(category.id) == trait_id)
            if mode == "exact":
                target = (counts or {}).get(trait_id if trait_id else f"none:{category.id}", 0) / supply * 100
            else:
                target = (max(weight, 0) / weight_total * 100) if weight_total else 0
            rows.append(
                {
                    "trait_id": trait_id,
                    "name": name,
                    "count": count,
                    "percent": round(count / supply * 100, 2),
                    "target_percent": round(target, 2),
                }
            )
        layers.append({"category_id": category.id, "name": category.name, "traits": rows})
    return layers


def generate(
    categories: list[CategoryIn],
    traits: list[TraitIn],
    rules: list[RuleIn],
    supply: int,
    seed: int,
    mode: str,
) -> PlanResult:
    mode = mode if mode in {"weighted", "exact"} else "weighted"
    categories = _ordered_categories(categories)
    _validate_basics(categories, traits, rules, supply)
    space = _check_space(categories, traits, rules, supply)
    counts = None
    attempts = 0
    if mode == "exact":
        counts = _resolve_exact_counts(categories, traits, supply)
        _check_exact_rules(categories, traits, rules, counts, supply)
        raw = _exact_tokens(categories, traits, rules, supply, seed, counts)
    else:
        raw, attempts = _weighted_tokens(categories, traits, rules, supply, seed)
    trait_category = _trait_category_map(traits)
    for selection in raw:
        if not _valid(selection, rules, trait_category):
            raise GenerationError("Generator produced an invalid combination")
    keys = [combination_key(selection) for selection in raw]
    if len(keys) != len(set(keys)):
        raise GenerationError("Generator produced duplicate combinations")
    tokens = [
        GeneratedToken(token_id=index + 1, selection=selection, combination_key=keys[index])
        for index, selection in enumerate(raw)
    ]
    warnings = []
    if space is None:
        warnings.append("Combination space is large, so feasibility was checked while generating rather than by full enumeration")
    stats = {
        "supply": supply,
        "mode": mode,
        "seed": seed,
        "unique": len(tokens),
        "attempts": attempts,
        "valid_space": space,
        "distribution": _distribution(categories, traits, raw, counts, mode),
        "exact_counts": counts,
    }
    return PlanResult(tokens=tokens, stats=stats, attempts=attempts, warnings=warnings)


def pick_one(
    categories: list[CategoryIn],
    traits: list[TraitIn],
    rules: list[RuleIn],
    seed: int,
    blocked_keys: set[str],
) -> dict[str, str | None]:
    """Pick a single new combination that is not in blocked_keys."""
    for offset in range(40):
        try:
            result = generate(categories, traits, rules, supply=min(12, max(len(blocked_keys) + 1, 1)), seed=seed + offset, mode="weighted")
        except GenerationError:
            continue
        for token in result.tokens:
            if token.combination_key not in blocked_keys:
                return token.selection
    raise GenerationError("No remaining unique combination is available for this token", ["Add traits or free up a conflicting rule"])
