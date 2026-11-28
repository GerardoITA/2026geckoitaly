"""Aggiunge 1 MIL alle sole history Gecko dell'India, esclusa Burma.

Anteprima: python rebalance_province_dev.py
Applica:   python rebalance_province_dev.py --apply

Richiede analyze_province_dev.py nella stessa cartella. Nessuna dipendenza esterna.
Selezione: india_superregion, esclusa burma_region, secondo la mappa del mod.
ADM e DIP restano invariati; ogni provincia idonea guadagna esattamente 1 MIL.
Le province presenti soltanto nel vanilla non vengono modificate.
Ogni esecuzione --apply applica una nuova modifica cumulativa.
"""

import argparse
import csv
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from analyze_province_dev import (
    DATE, FIELDS, TOKEN, UNKNOWN, as_date, geography, history_index, load, province_state,
)


def decode(data):
    try:
        return data.decode("utf-8-sig"), "utf-8-sig" if data.startswith(b"\xef\xbb\xbf") else "utf-8"
    except UnicodeDecodeError:
        return data.decode("cp1252"), "cp1252"


def initial_fields(text):
    """Localizza solo i valori numerici iniziali, fuori da blocchi e commenti."""
    tokens = [m for m in TOKEN.finditer(text) if not m.group().startswith("#")]
    depth = 0
    result = {}
    for index, token in enumerate(tokens):
        value = token.group()
        if value == "{":
            depth += 1
        elif value == "}":
            depth -= 1
        elif depth == 0 and value in FIELDS:
            if (index + 2 >= len(tokens) or tokens[index + 1].group() != "="
                    or not re.fullmatch(r"\d+", tokens[index + 2].group())):
                raise ValueError(f"Valore iniziale non intero per {value}")
            if value in result:
                raise ValueError(f"Assegnazione iniziale duplicata: {value}")
            number = tokens[index + 2]
            result[value] = (int(number.group()), number.start(), number.end())
    return result


def transform(data):
    text, encoding = decode(data)
    fields = initial_fields(text)
    if any(key not in fields for key in FIELDS):
        raise ValueError("Dev iniziale incompleto")
    old = {key: fields[key][0] for key in FIELDS}
    if any(value < 1 for value in old.values()):
        raise ValueError("Dev iniziale inferiore a 1")
    new = dict(old)
    new["base_manpower"] += 1
    changes = [(fields[key][1], fields[key][2], str(new[key]))
               for key in FIELDS if new[key] != old[key]]
    for start, end, value in sorted(changes, reverse=True):
        text = text[:start] + value + text[end:]
    return text.encode(encoding), old, new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mod", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--vanilla", type=Path, default=Path(
        "C:/Program Files (x86)/Steam/steamapps/common/Europa Universalis IV"))
    parser.add_argument("--apply", action="store_true", help="Scrive le history e salva prima un backup")
    args = parser.parse_args()
    target = as_date("1444.11.11")
    warnings = []
    index, conflicts = history_index(args.mod, target, warnings)
    areas, regions, supers, continents, nonland, _, _ = geography(args.mod, args.vanilla, warnings)
    # Anche duplicati con dev identico richiedono una scelta esplicita prima di editarli.
    counts = Counter(int(re.match(r"\d+", p.name)[0])
                     for p in (args.mod / "history/provinces").glob("*.txt") if p.stat().st_size)
    planned = []
    skipped = []
    for ident, path in sorted(index.items()):
        area = areas.get(ident, UNKNOWN)
        region = regions.get(area, UNKNOWN)
        continent = continents.get(ident, UNKNOWN)
        reason = ""
        if region == "burma_region":
            reason = "Burma esclusa"
        elif supers.get(region) != "india_superregion":
            reason = "Fuori dall'India"
        elif ident in nonland or area.startswith("X_unused") or continent.startswith("X_unused"):
            reason = "Mare/lago/random/inutilizzata"
        elif ident in conflicts or counts[ident] > 1:
            reason = "History duplicate per lo stesso ID"
        if reason:
            skipped.append((ident, str(path), reason))
            continue
        original = path.read_bytes()
        try:
            fields = initial_fields(decode(original)[0])
            state = province_state(path, target)
            if any(key in fields and fields[key][0] != state.get(key) for key in FIELDS):
                raise ValueError("Dev al 1444 diverso dal dev iniziale: richiede gestione history datata")
            # Gli override datati sono lasciati intatti. Non editarne il valore iniziale
            # se verrebbe subito sostituito, anche quando il valore numerico e' uguale.
            for key, value in load(path):
                if key and DATE.fullmatch(key) and as_date(key) <= target and isinstance(value, list):
                    if any(k in FIELDS or (k and k.startswith("add_base_")) for k, _ in value):
                        raise ValueError("Blocco dev datato precedente al 1444")
            updated, old, new = transform(original)
        except ValueError as error:
            skipped.append((ident, str(path), str(error)))
            continue
        planned.append((path, original, updated, {"id": ident, "file": str(path), "regione": region,
                        **{key + "_prima": old[key] for key in FIELDS},
                        **{key + "_dopo": new[key] for key in FIELDS},
                        "mil_aggiunto": 1}))
    folder = args.mod / "tools" / "dev_rebalance" / (
        datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ("_apply" if args.apply else "_preview"))
    folder.mkdir(parents=True, exist_ok=False)
    with (folder / "modifiche.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        if planned:
            writer = csv.DictWriter(handle, fieldnames=list(planned[0][3]), delimiter=";")
            writer.writeheader()
            writer.writerows(item[3] for item in planned)
    with (folder / "escluse.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(("id", "file", "motivo"))
        writer.writerows(skipped)
    (folder / "avvisi.txt").write_text("\n".join(warnings) + "\n", encoding="utf-8")
    if args.apply:
        for path, original, _, _ in planned:
            if path.read_bytes() != original:
                raise RuntimeError(f"File cambiato durante la pianificazione: {path}")
        # Tutti gli originali sono salvati prima della prima modifica.
        for path, original, _, _ in planned:
            backup = folder / "backup" / path.relative_to(args.mod)
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(original)
        for path, _, updated, _ in planned:
            path.write_bytes(updated)
    print(f"{'APPLICATO' if args.apply else 'ANTEPRIMA'}; India senza Burma; province: {len(planned)}")
    print(f"MIL +1: {len(planned)}; ADM e DIP invariati; escluse: {len(skipped)}")
    print(f"Dev totale aggiunto: {len(planned)}")
    print(f"Report e backup: {folder}")


if __name__ == "__main__":
    main()
