"""Match evidence to content fields, including extractor indexed paths."""
import re


def normalize(value):
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def matching_bindings(fact, fields):
    wanted = {normalize(field) for field in fields}
    for binding in fact.field_evidence:
        path = re.sub(r"^(?:(?:methods|experiment_settings|measurements)\[\d+\]\.)+", "", binding.field_path)
        names = {normalize(path)}
        indexed = re.fullmatch(r"(resources|hyperparameters)\[(\d+)\](?:\.(?:name|value|unit))?", path)
        if indexed:
            items = getattr(fact, indexed[1], [])
            index = int(indexed[2])
            if index < len(items):
                names.add(normalize(items[index].name))
        elif path in {"resources", "hyperparameters"}:
            names.update(normalize(item.name) for item in getattr(fact, path, []))
        elif path.startswith(("resources.", "hyperparameters.")):
            names.add(normalize(path.split(".", 1)[1]))
        if names & wanted:
            yield binding


def evidence_ids_for(fact, fields):
    return sorted({eid for binding in matching_bindings(fact, fields) for eid in binding.evidence_ids})
