"""Analisi dello sviluppo EU4: history Gecko con fallback vanilla per ID.

Uso: python analyze_province_dev.py [--vanilla PERCORSO] [--date 1444.11.11]
Output predefinito: tools/dev_analysis (report Markdown e CSV per Excel).
Solo libreria standard; nessun file del gioco o del mod viene modificato.
"""

import argparse
import csv
import re
from collections import defaultdict
from datetime import date
from pathlib import Path


FIELDS = ("base_tax", "base_production", "base_manpower")
TOKEN = re.compile(r'#[^\n]*|"(?:\\.|[^"\\])*"|[{}=]|[^\s{}=#"]+')
DATE = re.compile(r"\d+\.\d+\.\d+\Z")
UNKNOWN = "NON_ASSEGNATA"


def read_text(path):
    data = path.read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")


def parse(text):
    """Mantiene ordine, chiavi ripetute e blocchi; ignora commenti e stringhe."""
    tokens = [m.group() for m in TOKEN.finditer(text) if not m.group().startswith("#")]
    position = 0

    def block(nested=False):
        nonlocal position
        result = []
        while position < len(tokens):
            key = tokens[position]
            position += 1
            if key == "}":
                if not nested:
                    raise ValueError("Chiusura di blocco inattesa")
                return result
            if key in ("{", "="):
                raise ValueError(f"Token inatteso: {key}")
            if position < len(tokens) and tokens[position] == "=":
                position += 1
                if position == len(tokens):
                    raise ValueError(f"Valore mancante: {key}")
                value = tokens[position]
                position += 1
                if value == "{":
                    value = block(True)
                elif value in ("}", "="):
                    raise ValueError(f"Valore non valido: {key}")
                result.append((key, value))
            else:
                result.append((None, key))
        if nested:
            raise ValueError("Blocco non chiuso")
        return result

    return block()


def load(path):
    try:
        return parse(read_text(path))
    except ValueError as error:
        raise ValueError(f"{path}: {error}") from error


def as_date(value):
    try:
        return date(*map(int, value.split(".")))
    except (ValueError, TypeError):
        raise argparse.ArgumentTypeError("Data non valida: usare anno.mese.giorno")


def history_index(root, target, warnings):
    result = {}
    conflicts = set()
    for path in sorted((root / "history" / "provinces").glob("*.txt")):
        match = re.match(r"(\d+)", path.name)
        if not match:
            raise ValueError(f"ID provincia assente nel nome: {path}")
        ident = int(match[1])
        if ident in result:
            previous = result[ident]
            if not read_text(path).strip():
                warnings.append(f"ID {ident}: duplicato vuoto ignorato: {path}")
                continue
            if not read_text(previous).strip():
                warnings.append(f"ID {ident}: duplicato vuoto ignorato: {previous}")
            elif province_state(previous, target) == province_state(path, target):
                warnings.append(f"ID {ident}: duplicati con dev identico: {previous} e {path}; contato una volta")
                continue
            else:
                conflicts.add(ident)
                warnings.append(f"ID {ident}: dev discordante, escluso dai calcoli: {previous} e {path}")
                continue
        result[ident] = path
    if not result:
        raise ValueError(f"Nessuna history delle province trovata in {root}")
    return result, conflicts


def province_state(path, target):
    entries = load(path)
    state = {}

    def apply(items):
        for key, value in items:
            if key in FIELDS and isinstance(value, str):
                state[key] = float(value)
            elif key and key.startswith("add_base_") and key[4:] in FIELDS:
                field = key[4:]
                if field not in state:
                    raise ValueError(f"{path}: {key} senza valore base")
                state[field] += float(value)

    apply(entries)
    dated = [(as_date(key), value) for key, value in entries
             if key and DATE.fullmatch(key) and isinstance(value, list)]
    for when, items in sorted(dated, key=lambda item: item[0]):
        if when <= target:
            apply(items)
    return state


def geography(mod, vanilla, warnings):
    paths = {}
    blocks = {}
    for name in ("area.txt", "region.txt", "superregion.txt", "continent.txt", "default.map"):
        relative = Path("map") / name
        path = mod / relative if (mod / relative).is_file() else vanilla / relative
        paths[name] = str(path)
        blocks[name] = dict(load(path))

    def membership(pairs, label):
        result = {}
        for group, members in pairs:
            for member in members:
                if member in result and result[member] != group:
                    warnings.append(f"{label}: {member} in {result[member]} e {group}; usata ultima definizione")
                result[member] = group
        return result

    def atoms(items):
        return [value for key, value in items if key is None and isinstance(value, str)]

    areas = membership(((key, [int(v) for v in atoms(value) if v.isdigit()])
                        for key, value in blocks["area.txt"].items() if isinstance(value, list)), "area")
    regions = membership(((key, atoms(dict(value).get("areas", [])))
                          for key, value in blocks["region.txt"].items() if isinstance(value, list)), "regione")
    supers = membership(((key, [v for v in atoms(value) if v in blocks["region.txt"]])
                         for key, value in blocks["superregion.txt"].items() if isinstance(value, list)), "superregione")
    continents = membership(((key, [int(v) for v in atoms(value) if v.isdigit()])
                             for key, value in blocks["continent.txt"].items()
                             if isinstance(value, list) and key not in ("island_check_provinces", "new_world")), "continente")
    excluded = set()
    for key in ("sea_starts", "lakes", "only_used_for_random"):
        excluded.update(int(v) for v in atoms(blocks["default.map"].get(key, [])) if v.isdigit())
    # Gecko svuota le regioni Cina/Giappone: usa anche le loro aree vanilla
    # per riconoscerle, senza ripristinare la geografia vanilla nel rapporto.
    blocked_regions = {"north_china_region", "south_china_region", "xinan_region", "japan_region"}
    blocked_areas = set()
    for definitions in (blocks["region.txt"], dict(load(vanilla / "map" / "region.txt"))):
        for name in blocked_regions:
            blocked_areas.update(atoms(dict(definitions.get(name, [])).get("areas", [])))
    return areas, regions, supers, continents, excluded, blocked_areas, paths


def aggregate(rows, dimension):
    groups = defaultdict(list)
    for row in rows:
        groups[row[dimension]].append(row)
    result = []
    for name, members in sorted(groups.items()):
        totals = {field: sum(row[field] for row in members) for field in FIELDS}
        total = sum(totals.values())
        result.append({"gruppo": name, "province": len(members),
                       "province_gecko": sum(row["fonte"] == "gecko" for row in members),
                       "province_vanilla": sum(row["fonte"] == "vanilla" for row in members),
                       "dev_totale": total, "dev_medio": total / len(members), **totals,
                       **{field + "_pct": 100 * value / total for field, value in totals.items()}})
    return result


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def table(rows):
    lines = ["| Gruppo | Province | Dev totale | Dev medio | Tax % | Produzione % | Manpower % |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for row in sorted(rows, key=lambda r: r["base_manpower_pct"], reverse=True):
        lines.append(f'| {row["gruppo"]} | {row["province"]} | {row["dev_totale"]:g} | '
                     f'{row["dev_medio"]:.2f} | {row["base_tax_pct"]:.2f} | '
                     f'{row["base_production_pct"]:.2f} | {row["base_manpower_pct"]:.2f} |')
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mod", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--vanilla", type=Path, default=Path(
        "C:/Program Files (x86)/Steam/steamapps/common/Europa Universalis IV"))
    parser.add_argument("--date", type=as_date, default=as_date("1444.11.11"))
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    output = args.output or args.mod / "tools" / "dev_analysis"
    warnings = []
    mod, mod_conflicts = history_index(args.mod, args.date, warnings)
    vanilla, vanilla_conflicts = history_index(args.vanilla, args.date, warnings)
    conflicts = mod_conflicts | (vanilla_conflicts - mod.keys())
    areas, regions, supers, continents, nonland, blocked_areas, map_paths = geography(args.mod, args.vanilla, warnings)
    # Una history mod sostituisce l'intera history vanilla dello stesso ID.
    merged = {**vanilla, **mod}
    rows = []
    for ident, path in sorted(merged.items()):
        area = areas.get(ident, UNKNOWN)
        region = regions.get(area, UNKNOWN)
        superregion = supers.get(region, UNKNOWN)
        continent = continents.get(ident, UNKNOWN)
        state = province_state(path, args.date)
        missing = [field for field in FIELDS if field not in state]
        reason = ""
        if (superregion == "china_superregion" or region == "japan_region"
                or (region == UNKNOWN and area in blocked_areas)):
            reason = "cina_giappone"
        elif ident in nonland:
            reason = "mare_lago_random"
        elif continent.startswith("X_unused") or area.startswith("X_unused"):
            reason = "provincia_inutilizzata"
        elif ident in conflicts:
            reason = "history_ambigua"
        elif missing:
            reason = "dev_incompleto"
            warnings.append(f"Provincia {ident}: campi mancanti {', '.join(missing)}")
        elif any(value < 0 for value in state.values()) or sum(state.values()) <= 0:
            reason = "dev_non_valido"
            warnings.append(f"Provincia {ident}: dev non positivo o componenti negative")
        if not reason and UNKNOWN in (area, region, superregion, continent):
            warnings.append(f"Provincia {ident}: geografia incompleta; conservata nei gruppi {UNKNOWN}")
        rows.append({"id": ident, "nome": path.stem, "fonte": "gecko" if ident in mod else "vanilla",
                     "extra_gecko": ident in mod and ident not in vanilla,
                     "area": area, "regione": region, "superregione": superregion,
                     "continente": continent, "esclusione": reason,
                     **{field: state.get(field, "") for field in FIELDS},
                     "dev_totale": sum(state.values()) if not missing else "", "file": str(path)})
    included = [row for row in rows if not row["esclusione"]]
    if not included:
        raise ValueError("Nessuna provincia valida da analizzare")
    summaries = {dim: aggregate(included, dim) for dim in ("regione", "continente", "superregione", "fonte")}
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "province.csv", rows)
    for dim, summary in summaries.items():
        write_csv(output / f"{dim}.csv", summary)
    lines = ["# Ripartizione dello sviluppo delle province", "",
             f"Data history: {args.date.year}.{args.date.month}.{args.date.day}.", "",
             f"History Gecko: {len(mod)}; vanilla non presenti in Gecko: {len(vanilla.keys() - mod.keys())}; "
             f"ID extra Gecko: {len(mod.keys() - vanilla.keys())}.",
             f"Province incluse nei calcoli: {len(included)}; escluse: {len(rows) - len(included)}.", "",
             "## Metodo", "",
             "Quota pesata di una componente = 100 * somma(componente) / somma(dev totale). "
             "Equivale alla media delle quote provinciali pesata per dev totale; "
             "non alla media semplice delle percentuali o a una seconda pesatura dei totali.",
             "Il dev medio e' invece somma(dev totale) / numero di province.",
             "Le province sono unite per ID, comprese tutte le extra Gecko. "
             "Una history Gecko sostituisce completamente quella vanilla dello stesso ID. "
             "Si applicano le assegnazioni iniziali e poi i blocchi datati fino alla data richiesta, "
             "in ordine cronologico (solo campi dev e add_base_*). "
             "Non si simulano eventi, effetti di avvio o modificatori: manpower dev non e' manpower effettivo.",
             "Geografia presa dal mod, con fallback vanilla solo se il rispettivo file map manca. "
             "Sono incluse anche province non colonizzate con dev completo e positivo. "
             "Mari, laghi, province solo random, gruppi X_unused e history con dev incompleto/non valido "
             "sono esclusi. island_check_provinces e new_world sono metadati, non continenti.",
             "Gli ID duplicati con dev discordante sono esclusi e dettagliati negli avvisi: "
             "la scelta effettiva del motore tra history duplicate non viene presunta. "
             "I duplicati con dev identico contano una sola volta; i duplicati vuoti sono ignorati.",
             "Cina e Giappone esclusi: china_superregion e japan_region, comprese le aree "
             "delle regioni vanilla north_china, south_china, xinan e japan se prive di regione Gecko, "
             "poiche' Gecko svuota tali regioni. Le aree riassegnate dal mod mantengono la loro regione. "
             "India = india_superregion, incluse tutte le regioni che il mod le assegna (anche Burma). "
             "I gruppi di una dimensione sono disgiunti; superregioni e continenti sono viste alternative.", ""]
    europe = next((r for r in summaries["continente"] if r["gruppo"] == "europe"), None)
    india = next((r for r in summaries["superregione"] if r["gruppo"] == "india_superregion"), None)
    if europe and india:
        delta = europe["base_manpower_pct"] - india["base_manpower_pct"]
        lines += ["## Europa e India", "",
                  f'Europa: manpower {europe["base_manpower"]:g} / dev {europe["dev_totale"]:g} '
                  f'= {europe["base_manpower_pct"]:.2f}%.',
                  f'India: manpower {india["base_manpower"]:g} / dev {india["dev_totale"]:g} '
                  f'= {india["base_manpower_pct"]:.2f}%.',
                  f"Differenza Europa - India: {delta:+.2f} punti percentuali.", ""]
    for dim in ("regione", "continente", "superregione", "fonte"):
        lines += [f"## Ripartizione per {dim}", "", *table(summaries[dim]), ""]
    counts = defaultdict(int)
    for row in rows:
        if row["esclusione"]:
            counts[row["esclusione"]] += 1
    lines += ["## Controlli e provenienza", "", f"Esclusioni: {dict(counts)}.", "",
              *[f"- {name}: {path}" for name, path in map_paths.items()], "",
              "Il CSV province.csv comprende anche le esclusioni, la fonte e gli ID extra. "
              "I CSV usano separatore punto e virgola, decimali con punto e UTF-8 BOM.", "",
              f"Avvisi: {len(warnings)} (vedi avvisi.txt)."]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output / "avvisi.txt").write_text("\n".join(warnings) + "\n", encoding="utf-8")
    print("\n".join(lines[:7]))
    if europe and india:
        print(f'Quota manpower Europa: {europe["base_manpower_pct"]:.2f}%; '
              f'India: {india["base_manpower_pct"]:.2f}%; differenza: {delta:+.2f} pp')
    print(f"Avvisi: {len(warnings)}. Report: {output / 'report.md'}")


if __name__ == "__main__":
    main()
