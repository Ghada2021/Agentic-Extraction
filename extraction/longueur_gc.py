"""Colonne « Longueur génie civil ».
Code repris tel quel de pmv_api.py (aucune modification)."""
from ._base import *  # noqa: F401,F403


# ====================================================================
#                         LONGUEUR GC
# ====================================================================
def _load_cases(path="gc_cases.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _format_cases(cases, max_cases=None):
    lines = []
    for c in cases[:max_cases]:
        lines.append(
            f"Texte : '{c['texte']}'\n"
            f"→ {c['resultat']}\n"
            f"→ Raison : {c['raison']}"
        )
    return "\n\n".join(lines)


NUM_UNIT_RE = re.compile(
    r'(?P<num>\d[\d.,]*(?:\s?\d{3})*)\s*'
    r'(?P<unit>m|ml|mL|ML|mI|m\||m1|mètres?|metres?|métres?)\b'
    r'(?![0-9²³])'
)

NUM_KM_RE = re.compile(r'(?P<num>\d[\d\s.,]*)\s*(?P<unit>km)\b', re.IGNORECASE)

PR_RD_CTX_RE = re.compile(r'\b(?:pr|pk|point\s+rep[èe]re|point\s+kilom[ée]trique|rd)\b', re.IGNORECASE)
CHAINAGE_RE = re.compile(r'(?:\b(?:pr|pk)\b\s*)?\d+\s*\+\s*\d+\b', re.IGNORECASE)
AERIAL_CONTEXT_RE = re.compile(r'\ba[ée]rienne?s?\b', re.IGNORECASE)
UNDERGROUND_CONTEXT_RE = re.compile(r'\bsouterraines?\b', re.IGNORECASE)
PARTIAL_CONTEXT_RE = re.compile(r'\b(extension|ajout|supplémentaire|additionnel|nouveau|nouvelle)\b', re.IGNORECASE)

DEPTH_CONTEXT_RE = re.compile(
    r'\b(profondeur|distance|hauteur|génératrice|supérieure|inférieure|enfouissement|recouvrement|épaisseur|diamètre|diam[eè]tre|largeur|section)\b',
    re.IGNORECASE
)

TECHNICAL_CONSTRAINT_RE = re.compile(
    r'\b('
    r'sous\s+chauss[ée]e|sous\s+accotement|sous\s+trottoir'
    r'|ne\s+soit\s+pas|pas\s+inf[ée]rieure?|pas\s+sup[ée]rieure?'
    r'|au\s+moins|minimum|maximum|maximale?'
    r'|ne\s+d[ée]passera\s+jamais|ne\s+d[ée]passera\s+pas|ne\s+devra\s+pas\s+d[ée]passer'
    r'|ne\s+pourra\s+exc[ée]der|ne\s+pourra\s+pas\s+d[ée]passer'
    r'|sera\s+[ée]gale?\s+[àa]|sera\s+limit[ée]e?\s+[àa]'
    r'|passage\s+minimum|circulation\s+pi[ée]tonne'
    r'|capable\s+de\s+refermer'
    r')\b',
    re.IGNORECASE
)

TYPICAL_DEPTH_VALUES = [
    "0,30", "0.30", "0,40", "0.40", "0,50", "0.50",
    "0,60", "0.60", "0,70", "0.70", "0,80", "0.80", "0,90", "0.90",
]


def _normalize_unit(unit: str) -> str:
    u = unit.strip()
    u_low = u.lower()
    if u_low in ["ml", "ml.", "ml", "mi", "m1", "m|"]:
        return "ml"
    if u_low in ["m", "m.", "metre", "metres", "mètre", "mètres", "métre", "métres"]:
        return "m"
    if u_low == "km":
        return "km"
    if u_low.startswith("m") and "l" not in u_low:
        return "m"
    return u


def _km_to_m(num_str: str):
    num_clean = num_str.replace(" ", "").replace("\u202f", "")
    num_clean = num_clean.replace(",", ".")
    try:
        val = float(num_clean)
        val_m = val * 1000
        if val_m == int(val_m):
            return str(int(val_m))
        else:
            return str(val_m).replace(".", ",")
    except:
        return None


def _is_aerial_line(line: str) -> bool:
    lower = line.lower()
    if AERIAL_CONTEXT_RE.search(lower) and not UNDERGROUND_CONTEXT_RE.search(lower):
        return True
    return False


def _is_underground_line(line: str) -> bool:
    lower = line.lower()
    return UNDERGROUND_CONTEXT_RE.search(lower) is not None


def _is_partial_line(line: str) -> bool:
    lower = line.lower()
    return PARTIAL_CONTEXT_RE.search(lower) is not None


def _is_depth_or_constraint_line(line: str) -> bool:
    lower = line.lower()
    if DEPTH_CONTEXT_RE.search(lower):
        return True
    if TECHNICAL_CONSTRAINT_RE.search(lower):
        return True
    return False


def _is_depth_value(num: str) -> bool:
    num_clean = num.replace(" ", "").replace("\u202f", "")
    if num_clean in TYPICAL_DEPTH_VALUES:
        return True
    try:
        val = float(num_clean.replace(",", "."))
        if val < 1.0 and val > 0:
            return True
    except:
        pass
    return False


def _extract_chainage_numbers(text: str) -> set:
    chainage_nums = set()
    for match in CHAINAGE_RE.finditer(text):
        nums_in_match = re.findall(r'\d+', match.group())
        chainage_nums.update(nums_in_match)
    return chainage_nums


def _value_exists_in_text(num: str, unit: str, texte: str) -> bool:
    num_clean = num.replace(" ", "").replace("\u202f", "").replace(",", ".").strip()

    for match in NUM_UNIT_RE.finditer(texte):
        found_num = match.group("num").replace(" ", "").replace("\u202f", "").replace(",", ".").strip()
        found_unit = _normalize_unit(match.group("unit"))
        if found_num == num_clean and found_unit == unit:
            return True

    for match in NUM_KM_RE.finditer(texte):
        found_num = match.group("num").replace(" ", "").replace("\u202f", "").replace(",", ".").strip()
        converted = _km_to_m(found_num)
        if converted:
            converted_clean = converted.replace(" ", "").replace(",", ".").strip()
            if converted_clean == num_clean:
                return True

    num_comma = num_clean.replace(".", ",")
    if re.search(rf'\b{re.escape(num_clean)}\b', texte):
        return True
    if re.search(rf'\b{re.escape(num_comma)}\b', texte):
        return True

    return False


def _extract_value_from_line(line: str, chainage_numbers: set, debug: bool = False):
    m = NUM_UNIT_RE.search(line)
    if not m:
        return None

    lower = line.lower()

    if _is_depth_or_constraint_line(line):
        return None

    if PR_RD_CTX_RE.search(lower) and CHAINAGE_RE.search(lower):
        return None

    if "m²" in line or "m³" in line or "m2" in lower:
        clean_line = re.sub(r'\d[\d\s.,]*\s*m[²³2]', '', line)
        if not NUM_UNIT_RE.search(clean_line):
            return None

    num = m.group("num").strip()

    if "+" in num:
        return None

    unit_raw = m.group("unit")
    unit = _normalize_unit(unit_raw)

    num_clean = num.replace(" ", "").replace("\u202f", "")
    if num_clean in ["0", "0.0", "0,0"]:
        return None

    if _is_depth_value(num):
        if "longueur" not in lower and "total" not in lower and "linéaire" not in lower:
            return None

    if re.search(rf"{re.escape(num)}\s*mm\b", line, re.I):
        return None

    try:
        if float(num_clean.replace(",", ".")) > 100000:
            return None
    except:
        pass

    if num_clean in chainage_numbers:
        return None

    return num, unit


def _call_llm(texte: str, client, deployment, gc_cases_path="gc_cases.json", debug: bool = False) -> str:
    try:
        cases = _load_cases(gc_cases_path)
        cases_block = _format_cases(cases)
    except:
        cases_block = ""
    system_prompt = """Extrais uniquement la longueur de génie civil EXPLICITEMENT indiquée.
Réponds uniquement : Longueur génie civil : <valeur> m/ml,
ou : Longueur génie civil : non trouvée.

REGLES PRIORITAIRES, avant tous les exemples :
- Exige un lien explicite avec le GC, génie civil, tranchée, réseau ou artère souterraine.
- Une valeur dans la colonne Longueur (m) d'un tableau Génie Civil est admissible.
- Ne prends jamais le maximum ni une valeur arbitraire parmi plusieurs longueurs.
- Aucun calcul : ni somme, multiplication, ni différence de points routiers.
- Des longueurs de fourreaux seules ne prouvent pas une longueur GC.
  3 fourreaux sur 124 ml et 2 fourreaux sur 76 ml -> non trouvée.
  Ne retourne ni 124, ni 76, ni 200, ni 524 comme longueur GC dans cet exemple.
- Ignore profondeurs, largeurs, diamètres, surfaces, prescriptions et réseaux aériens.
- Plusieurs longueurs GC sans total explicitement écrit -> non trouvée.
- Une conversion km vers m est permise, sans calculer de nouveau total.
- Ignore tout exemple contraire à ces règles.

EXEMPLES :
""" + cases_block

    try:
        response = traced_completion(client.chat.completions.create, 
            model=deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "TEXTE OCR : " + texte},
            ],
            max_completion_tokens=2000,  # GPT-5 : inclut les tokens de réflexion
        )
        completion = (response.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[_call_llm] Azure OpenAI error: {e}")
        completion = ""

    if debug:
        print("===== COMPLETION LLM =====")
        print(completion)
        print("==========================")

    return completion


def _parse_llm_response(completion: str, chainage_numbers: set, debug: bool = False):
    prefix = "Longueur génie civil :"
    chosen_line = None
    for line in completion.splitlines():
        l = line.strip()
        if l.lower().startswith(prefix.lower()):
            chosen_line = " ".join(l.split())
            break

    if chosen_line is None:
        match = re.search(r'Longueur\s+g[ée]nie\s+civil\s*:\s*(?P<num>\d[\d\s.,]*)\s*(?P<unit>m|ml)\b', completion, re.IGNORECASE)
        if match:
            num = match.group("num").strip()
            unit = _normalize_unit(match.group("unit"))
            if not _is_depth_value(num):
                return num, unit
        return None

    content = chosen_line[len(prefix):].strip()

    if CHAINAGE_RE.search(content):
        return None

    if content.lower() == "non trouvée":
        return None

    m = NUM_UNIT_RE.search(content)
    if not m:
        return None

    num = m.group("num").strip()
    unit = _normalize_unit(m.group("unit"))

    if _is_depth_value(num):
        return None

    num_clean = num.replace(" ", "").replace("\u202f", "")
    if num_clean in chainage_numbers:
        return None

    return num, unit


def _find_longueur_totale_km(texte: str, chainage_numbers: set, debug: bool = False):
    texte_normalized = re.sub(r'[\n\r]+', ' ', texte)
    texte_normalized = re.sub(r'\s+', ' ', texte_normalized)

    patterns = [
        re.compile(
            r'l[oa]ngueur\s+total[e]?\s+(?:d[\'e]\s*)?(?:art[èe]res?\s+)?(?:souterraines?\s+)?(?:de\s+)?(?P<num>\d[\d\s.,]*)\s*(?P<unit>km)\b',
            re.IGNORECASE
        ),
        re.compile(r'l[oa]ngueur\s+total[e]?\s+(?:de\s+)?(?P<num>\d[\d\s.,]*)\s*(?P<unit>km)\b', re.IGNORECASE),
        re.compile(r'\btotal[e]?\s+(?:de\s+)?(?P<num>\d[\d\s.,]*)\s*(?P<unit>km)\b', re.IGNORECASE),
    ]

    all_matches = []
    for pattern in patterns:
        for match in pattern.finditer(texte_normalized):
            num = match.group("num").strip()
            num_clean = num.replace(" ", "").replace("\u202f", "")
            if num_clean in chainage_numbers or num_clean in ["0", "0.0", "0,0"]:
                continue
            num_m = _km_to_m(num)
            if num_m:
                all_matches.append((match.start(), num_m, "m", num))

    if all_matches:
        all_matches.sort(key=lambda x: x[0], reverse=True)
        best = all_matches[0]
        return best[1], best[2]

    return None


def _find_underground_value_multiline(texte: str, chainage_numbers: set, debug: bool = False):
    lines = texte.splitlines()

    for i, line in enumerate(lines):
        lower = line.lower()

        if UNDERGROUND_CONTEXT_RE.search(lower) and not AERIAL_CONTEXT_RE.search(lower):
            if _is_partial_line(line):
                continue
            if _is_depth_or_constraint_line(line):
                continue

            m = NUM_UNIT_RE.search(line)
            if m:
                num = m.group("num").strip()
                unit = _normalize_unit(m.group("unit"))
                num_clean = num.replace(" ", "").replace("\u202f", "")
                if "m²" in line or "m³" in line or "m2" in lower:
                    continue
                if _is_depth_value(num) and "longueur" not in lower and "total" not in lower:
                    continue
                if num_clean not in chainage_numbers and num_clean not in ["0", "0.0", "0,0"]:
                    return num, unit

            m_km = NUM_KM_RE.search(line)
            if m_km and "longueur totale" in lower:
                num = m_km.group("num").strip()
                num_m = _km_to_m(num)
                if num_m:
                    return num_m, "m"

            if i + 1 < len(lines):
                next_line = lines[i + 1]
                next_lower = next_line.lower()

                if AERIAL_CONTEXT_RE.search(next_lower):
                    continue
                if _is_partial_line(next_line):
                    continue
                if _is_depth_or_constraint_line(next_line):
                    continue

                m = NUM_UNIT_RE.search(next_line)
                if m:
                    num = m.group("num").strip()
                    unit = _normalize_unit(m.group("unit"))
                    num_clean = num.replace(" ", "").replace("\u202f", "")
                    if "m²" in next_line or "m³" in next_line or "m2" in next_lower:
                        continue
                    if _is_depth_value(num):
                        continue
                    if num_clean not in chainage_numbers and num_clean not in ["0", "0.0", "0,0"]:
                        return num, unit

    return None


def _find_total_in_text(texte: str, chainage_numbers: set, debug: bool = False):
    texte_normalized = re.sub(r'[\n\r]+', ' ', texte)
    texte_normalized = re.sub(r'\s+', ' ', texte_normalized)

    unit_pattern = r'(?P<unit>m|ml|mL|ML|mI|m\||m1|mètres?|metres?|métres?)\b(?!\s*[²³2])'

    total_patterns = [
        re.compile(r'soit\s+un\s+total\s+(?:de\s+)?(?P<num>\d[\d\s.,]*)\s*' + unit_pattern, re.IGNORECASE),
        re.compile(r'soit\s+un[e]?\s+l[oa]ngueur\s+total[e]?\s+(?:de\s+)?(?P<num>\d[\d\s.,]*)\s*' + unit_pattern, re.IGNORECASE),
        re.compile(r'l[oa]ngueur\s+total[e]?\s*[:.]?\s*(?:de\s+)?(?P<num>\d[\d\s.,]*)\s*' + unit_pattern, re.IGNORECASE),
        re.compile(r'total\s+des\s+canalisations\s*[:.]?\s*(?P<num>\d[\d\s.,]*)\s*' + unit_pattern, re.IGNORECASE),
        re.compile(r'(?P<num>\d[\d\s.,]*)\s*' + unit_pattern + r'\s+de\s+cr[ée]ation\s+de\s+gc', re.IGNORECASE),
        re.compile(r'cr[ée]ation\s+de\s+gc\s*[:.]?\s*(?:de\s+)?(?P<num>\d[\d\s.,]*)\s*' + unit_pattern, re.IGNORECASE),
    ]

    for pattern in total_patterns:
        match = pattern.search(texte_normalized)
        if match:
            num = match.group("num").strip()
            unit = _normalize_unit(match.group("unit"))
            num_clean = num.replace(" ", "").replace("\u202f", "")
            if _is_depth_value(num):
                continue
            if num_clean not in chainage_numbers and num_clean not in ["0", "0.0", "0,0"]:
                return num, unit

    return None


def _find_value_after_header(texte: str, chainage_numbers: set, debug: bool = False):
    lines = texte.splitlines()

    HEADER_PATTERNS = [
        (re.compile(r'art[èeé]re[s]?\s+souterraine', re.IGNORECASE), "ml"),
        (re.compile(r'longueur\s+(?:totale?)?\s*\(en\s+(?:m|ml)\)', re.IGNORECASE), "ml"),
        (re.compile(r'souterrain[e]?\s*\(en\s+(?:m|ml)\)', re.IGNORECASE), "ml"),
    ]

    for i, line in enumerate(lines):
        for pattern, default_unit in HEADER_PATTERNS:
            if pattern.search(line):
                for j in range(i + 1, min(i + 3, len(lines))):
                    next_line = lines[j].strip()
                    m = re.match(r'^(\d[\d\s.,]*)$', next_line)
                    if m:
                        num = m.group(1).strip()
                        num_clean = num.replace(" ", "").replace("\u202f", "")
                        if num_clean in chainage_numbers or num_clean in ["0", "0.0", "0,0"]:
                            continue
                        if _is_depth_value(num):
                            continue
                        return num, default_unit
    return None


def _find_with_heuristics(texte_extrait: str, chainage_numbers: set, debug: bool = False):
    lines = texte_extrait.splitlines()

    def pick_from_line(line: str):
        if _is_aerial_line(line):
            return None
        if _is_partial_line(line):
            return None
        if _is_depth_or_constraint_line(line):
            return None
        return _extract_value_from_line(line, chainage_numbers, debug)

    result = _find_longueur_totale_km(texte_extrait, chainage_numbers, debug)
    if result:
        return result

    result = _find_underground_value_multiline(texte_extrait, chainage_numbers, debug)
    if result:
        return result

    result = _find_value_after_header(texte_extrait, chainage_numbers, debug)
    if result:
        return result

    result = _find_total_in_text(texte_extrait, chainage_numbers, debug)
    if result:
        return result

    for line in lines:
        lower = line.lower()
        if ("linéaire total" in lower or "lineaire total" in lower) and not _is_partial_line(line):
            cand = pick_from_line(line)
            if cand:
                return cand

    TOTAL_KEYWORDS = [
        "au total", "pour un total", "totalisant", "total :", "total:",
        "soit un total", "soit un linéaire", "équivaut à",
        "longueur totale", "longueur total", "langueur totale", "langueur total",
        "total des canalisations", "création de gc", "creation de gc",
        "réseau souterrain", "reseau souterrain",
    ]
    for line in lines:
        lower = line.lower()
        if any(kw in lower for kw in TOTAL_KEYWORDS) and not _is_partial_line(line):
            cand = pick_from_line(line)
            if cand:
                return cand

    for line in lines:
        lower = line.lower()
        if ("longueur" in lower or "langueur" in lower) and "total" in lower and not _is_partial_line(line):
            cand = pick_from_line(line)
            if cand:
                return cand

    for line in lines:
        lower = line.lower()
        if "longueur" in lower or "langueur" in lower:
            if " x " in lower or "=" in line or "fourreau" in lower:
                continue
            if _is_partial_line(line):
                continue
            cand = pick_from_line(line)
            if cand:
                return cand

    for line in lines:
        lower = line.lower()
        if ("gc" in lower or "génie civil" in lower or "genie civil" in lower) and not _is_aerial_line(line) and not _is_partial_line(line):
            cand = pick_from_line(line)
            if cand:
                return cand

    return None


def _explicit_gc_evidence(text):
    """Keep measured GC statements/table rows, excluding unrelated dimensions."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    evidence = []
    marker = re.compile(r"(?i)\b(?:g[ée]nie\s+civil|gc|tranch[ée]es?|r[ée]seau\s+souterrain|art[èe]res?\s+souterraines?)\b")
    for i, line in enumerate(lines):
        if not marker.search(line) or _is_aerial_line(line) or _is_depth_or_constraint_line(line):
            continue
        if NUM_UNIT_RE.search(line) or NUM_KM_RE.search(line):
            evidence.append(line)
        elif re.search(r"(?i)longueur|lin[ée]aire|\(\s*(?:m|ml)\s*\)", line) and i + 1 < len(lines):
            row = lines[i + 1]
            if re.match(r"^\d", row) and (NUM_UNIT_RE.search(row) or NUM_KM_RE.search(row)):
                evidence.append(line + "\n" + row)
    return "\n".join(evidence)


# « 2 artères souterraines de 10 ml chacune » : chaque artère a sa longueur,
# le génie civil est le linéaire total des artères (2 × 10 = 20 ml).
_ARTERES_CHACUNE_RE = re.compile(
    r"(?i)\b(\d+)\s+art[èe]res?(?:\s+souterraines?)?[^.\n;]{0,30}?"
    r"\bde\s+(\d+(?:[.,]\d+)?)\s*(?:ml|m|mètres?|metres?)\b\s*chacun(?:e)?s?\b"
)


@trace_step('texte_extrait')
def extract_longueur_gc(texte_extrait: str, client, deployment, debug: bool = False) -> str:
    """Longueur GC. Cas « N artères de X ml chacune » : GC = N × X, sauf si une autre
    longueur GC (différente de X) a été trouvée explicitement dans le document."""
    resultat = _extract_longueur_gc_base(texte_extrait, client, deployment, debug=debug)
    m_art = _ARTERES_CHACUNE_RE.search(_texte_nombres_en_chiffres(texte_extrait or ""))
    if m_art and int(m_art.group(1)) > 1:
        x_txt = m_art.group(2)
        x = float(x_txt.replace(",", "."))
        val = resultat.split(":", 1)[1].strip() if ":" in resultat else ""
        nums = [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", val)]
        if val.lower().startswith("non trouv") or nums == [x]:
            total = int(m_art.group(1)) * x
            resultat = "Longueur génie civil : " + f"{total:g}".replace(".", ",") + " ml"
    return resultat


def _extract_longueur_gc_base(texte_extrait: str, client, deployment, debug: bool = False) -> str:
    chainage_numbers = _extract_chainage_numbers(texte_extrait)

    heur_result = _find_with_heuristics(texte_extrait, chainage_numbers, debug)

    completion = _call_llm(texte_extrait, client, deployment, debug=debug)
    llm_result = _parse_llm_response(completion, chainage_numbers, debug)

    # Validate against explicit GC evidence, never mere occurrence of a number.
    evidence = _explicit_gc_evidence(texte_extrait)
    if not evidence:
        return "Longueur génie civil : non trouvée"

    if llm_result:
        if _value_exists_in_text(llm_result[0], llm_result[1], evidence):
            return f"Longueur génie civil : {llm_result[0]} {llm_result[1]}"

    if heur_result and _value_exists_in_text(heur_result[0], heur_result[1], evidence):
        return f"Longueur génie civil : {heur_result[0]} {heur_result[1]}"

    return "Longueur génie civil : non trouvée"


def longueur_gc_to_df(output: str, none_for_missing: bool = False) -> pd.DataFrame:
    m = re.search(r"(?i)Longueur\s+g[ée]nie\s+civil\s*:\s*(.+)", output or "")
    val = m.group(1).strip() if m else "non trouvée"
    if none_for_missing and val.lower().startswith("non trouv"):
        val = None
    return pd.DataFrame({"Longueur génie civil": [val]})


# --- dépendances utilisées seulement à l'appel des fonctions (importées en fin de module : évite les imports circulaires) ---
from .normalisation import _texte_nombres_en_chiffres  # noqa: E402,F401